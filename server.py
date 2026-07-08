from __future__ import annotations

import io
import json
import logging
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from threading import Lock, RLock

import soundfile as sf
import torch
from fastapi import FastAPI, HTTPException
from fastapi.responses import Response
from omnivoice import OmniVoice, OmniVoiceGenerationConfig
from pydantic import BaseModel, Field

from language_profiles import (
    LanguageProfile,
    load_profiles,
    load_runtime_config,
    resolve_profile,
    save_runtime_config,
)
from voice_library import voice_id_problem


BASE_DIR = Path(__file__).resolve().parent
VOICES_ROOT = BASE_DIR / "voices"
PROFILES_DIR = BASE_DIR / "languages"
CONFIG_PATH = BASE_DIR / "config.json"
SAMPLE_RATE_FALLBACK = 24000
API_VERSION = "0.3.1"


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger("chim-omnivoice")


@dataclass
class VoiceProfile:
    name: str
    directory: Path
    reference_wav: Path
    reference_txt: Path
    metadata: dict = field(default_factory=dict)
    prompt: object | None = None
    prompt_lock: Lock = field(default_factory=Lock)


def normalize_voice_id(value: str) -> str:
    stem = Path(value.strip()).stem
    return re.sub(r"[^a-z0-9]+", "", stem.casefold())


def discover_voices(language_dir: Path) -> tuple[dict[str, VoiceProfile], dict[str, str]]:
    profiles: dict[str, VoiceProfile] = {}
    aliases: dict[str, str] = {}

    if not language_dir.is_dir():
        log.warning("Language voice library does not exist yet: %s", language_dir)
        return profiles, aliases

    for directory in sorted(language_dir.iterdir(), key=lambda path: path.name.casefold()):
        if not directory.is_dir():
            continue

        id_problem = voice_id_problem(directory.name)
        if id_problem is not None:
            log.warning(
                "Skipping invalid VoiceID folder %s: %s",
                directory.name,
                id_problem,
            )
            continue

        reference_wav = directory / "reference.wav"
        reference_txt = directory / "reference.txt"
        if not reference_wav.is_file() or not reference_txt.is_file():
            log.warning(
                "Skipping voice folder %s: reference.wav or reference.txt is missing.",
                directory.name,
            )
            continue

        try:
            reference_text = reference_txt.read_text(encoding="utf-8").strip()
        except OSError as exc:
            log.warning("Skipping unreadable voice %s: %s", directory.name, exc)
            continue
        if not reference_text:
            log.warning("Skipping voice folder %s: reference.txt is empty.", directory.name)
            continue

        metadata = {}
        for metadata_path in (directory / "voice.json", directory / "metadata.json"):
            if not metadata_path.is_file():
                continue
            try:
                loaded_metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
                if isinstance(loaded_metadata, dict):
                    metadata = loaded_metadata
                    break
            except (OSError, json.JSONDecodeError) as exc:
                log.warning(
                    "Ignoring unreadable metadata file %s for voice %s: %s",
                    metadata_path.name,
                    directory.name,
                    exc,
                )

        name = directory.name
        profiles[name] = VoiceProfile(
            name=name,
            directory=directory,
            reference_wav=reference_wav,
            reference_txt=reference_txt,
            metadata=metadata,
        )
        aliases[normalize_voice_id(name)] = name

    return profiles, aliases


class RuntimeState:
    def __init__(self) -> None:
        self.lock = RLock()
        self.config = load_runtime_config(CONFIG_PATH)
        self.language_profiles = load_profiles(PROFILES_DIR)
        self.active_language = resolve_profile(
            str(self.config.get("active_language", "sk")),
            PROFILES_DIR,
            self.language_profiles,
        )
        self.voices: dict[str, VoiceProfile] = {}
        self.voice_aliases: dict[str, str] = {}
        self.voice_names: list[str] = []
        self.default_voice: str | None = None
        self.reload_voices_unlocked()

    @property
    def active_voice_dir(self) -> Path:
        return VOICES_ROOT / self.active_language.id

    def reload_voices_unlocked(self) -> None:
        voices, aliases = discover_voices(self.active_voice_dir)
        names = list(voices.keys())
        preferred = str(self.config.get("preferred_default_voice", "")).strip()

        self.voices = voices
        self.voice_aliases = aliases
        self.voice_names = names
        self.default_voice = self.first_available_voice(
            preferred,
            str(self.config.get("fallback_female", "")).strip(),
            str(self.config.get("fallback_male", "")).strip(),
        )

        log.info(
            "Active language: %s (%s); discovered %d voice(s).",
            self.active_language.id,
            self.active_language.display_name,
            len(names),
        )
        if self.default_voice:
            log.info("Default voice: %s", self.default_voice)

    def reload_voices(self) -> None:
        with self.lock:
            self.reload_voices_unlocked()

    def first_available_voice(self, *candidates: str) -> str | None:
        for candidate in candidates:
            if candidate in self.voices:
                return candidate
            canonical = self.voice_aliases.get(normalize_voice_id(candidate))
            if canonical is not None:
                return canonical
        return self.voice_names[0] if self.voice_names else None

    def fallback_voice_for_request(self, requested: str | None) -> str:
        requested_norm = normalize_voice_id(requested or "")
        if "female" in requested_norm:
            candidate = self.first_available_voice(str(self.config.get("fallback_female", "")))
            if candidate is not None:
                return candidate
        if "male" in requested_norm:
            candidate = self.first_available_voice(str(self.config.get("fallback_male", "")))
            if candidate is not None:
                return candidate
        if self.default_voice is not None:
            return self.default_voice
        raise HTTPException(
            status_code=503,
            detail={
                "error": "no_voices",
                "language": self.active_language.id,
                "voice_directory": str(self.active_voice_dir),
                "hint": "Prepare and calibrate at least one VoiceID for this language.",
            },
        )

    def switch_language(self, requested: str) -> LanguageProfile:
        with self.lock:
            profile = resolve_profile(requested, PROFILES_DIR, self.language_profiles)
            self.active_language = profile
            self.config["active_language"] = profile.id
            save_runtime_config(CONFIG_PATH, self.config)
            self.reload_voices_unlocked()
            return profile

    def resolve_voice(self, requested: str | None) -> VoiceProfile:
        with self.lock:
            if not self.voices or self.default_voice is None:
                raise HTTPException(
                    status_code=503,
                    detail={
                        "error": "no_voices",
                        "language": self.active_language.id,
                        "voice_directory": str(self.active_voice_dir),
                        "hint": "Prepare and calibrate at least one VoiceID for this language.",
                    },
                )

            if requested is None or not requested.strip():
                return self.voices[self.default_voice]

            canonical = self.voice_aliases.get(normalize_voice_id(requested))
            if canonical is None:
                # CHIM can keep sending the NPC's original VoiceID even when the
                # tester has prepared only one voice for the active language.
                # Returning 404 makes the game go silent; falling back keeps TTS
                # usable and logs the mismatch for debugging. Full libraries will
                # still resolve the exact VoiceID normally.
                fallback_voice = self.fallback_voice_for_request(requested)
                log.warning(
                    "Requested voice %r is not available in language %s; falling back to %s. Available voices: %s",
                    requested,
                    self.active_language.id,
                    fallback_voice,
                    ", ".join(self.voice_names[:20]),
                )
                return self.voices[fallback_voice]
            return self.voices[canonical]


runtime = RuntimeState()

MODEL_ID = str(runtime.config.get("model_id", "k2-fsa/OmniVoice"))
DEVICE = str(runtime.config.get("device", "cuda:0"))

if not torch.cuda.is_available():
    raise RuntimeError("CUDA is not available. Chapter 1 supports NVIDIA CUDA only.")

log.info("Loading OmniVoice model %s on %s ...", MODEL_ID, DEVICE)
model = OmniVoice.from_pretrained(
    MODEL_ID,
    device_map=DEVICE,
    dtype=torch.float16,
    load_asr=False,
)
log.info("OmniVoice model loaded.")

runtime_generation_config = OmniVoiceGenerationConfig(
    num_step=32,
    guidance_scale=2.0,
    denoise=True,
    preprocess_prompt=True,
    postprocess_output=True,
)
sampling_rate = int(getattr(model, "sampling_rate", SAMPLE_RATE_FALLBACK))
generation_lock = Lock()


def get_or_create_prompt(profile: VoiceProfile) -> object:
    if profile.prompt is not None:
        return profile.prompt

    with profile.prompt_lock:
        if profile.prompt is not None:
            return profile.prompt

        reference_text = profile.reference_txt.read_text(encoding="utf-8").strip()
        log.info("Preparing voice prompt for %s ...", profile.name)
        with generation_lock, torch.inference_mode():
            profile.prompt = model.create_voice_clone_prompt(
                ref_audio=str(profile.reference_wav),
                ref_text=reference_text,
            )
        log.info("Voice prompt ready: %s", profile.name)
        return profile.prompt


app = FastAPI(
    title="Multilingual TTS API",
    version=API_VERSION,
    description=(
        "XTTS-compatible multilingual OmniVoice backend for CHIM. "
        "One language library is active at a time; the model remains loaded while libraries switch."
    ),
)


class TTSRequest(BaseModel):
    text: str = Field(min_length=1)
    speaker_wav: str | None = None
    language: str | None = None
    speed: float = Field(default=1.0, ge=0.5, le=1.5)


class LanguageSwitchRequest(BaseModel):
    language: str = Field(min_length=1)


class TTSSettingsRequest(BaseModel):
    stream_chunk_size: int | None = None
    temperature: float | None = None
    speed: float | None = None
    length_penalty: float | None = None
    repetition_penalty: float | None = None
    top_p: float | None = None
    top_k: int | None = None
    enable_text_splitting: bool | None = None


@app.get("/")
def root() -> dict:
    with runtime.lock:
        return {
            "service": "Multilingual TTS API",
            "version": API_VERSION,
            "status": "ready" if runtime.voice_names else "ready_without_voices",
            "active_language": runtime.active_language.public_dict(),
            "voice_count": len(runtime.voice_names),
            "default_voice": runtime.default_voice,
            "xtts_endpoint": "/tts_to_audio",
            "honor_request_language": False,
        }


@app.get("/health")
def health() -> dict:
    with runtime.lock:
        cached = [
            profile.name for profile in runtime.voices.values() if profile.prompt is not None
        ]
        return {
            "status": "ok" if runtime.voice_names else "no_voices",
            "model": MODEL_ID,
            "device": DEVICE,
            "cuda": torch.cuda.is_available(),
            "gpu": torch.cuda.get_device_name(0) if torch.cuda.is_available() else None,
            "sample_rate": sampling_rate,
            "active_language": runtime.active_language.public_dict(),
            "voice_directory": str(runtime.active_voice_dir),
            "voice_count": len(runtime.voice_names),
            "voices": runtime.voice_names,
            "cached_voice_prompts": cached,
            "default_voice": runtime.default_voice,
        }


@app.get("/provider_info")
def provider_info() -> dict:
    with runtime.lock:
        return {
            "provider": "omnivoice",
            "api_version": API_VERSION,
            "model": MODEL_ID,
            "active_language": runtime.active_language.public_dict(),
            "available_languages": [
                profile.public_dict()
                for profile in sorted(
                    runtime.language_profiles.values(), key=lambda item: item.id
                )
            ],
            "voices": runtime.voice_names,
            "default_voice": runtime.default_voice,
            "fallback_male": runtime.config.get("fallback_male", ""),
            "fallback_female": runtime.config.get("fallback_female", ""),
            "honor_request_language": False,
            "output": {
                "media_type": "audio/wav",
                "sample_rate": sampling_rate,
                "subtype": "PCM_16",
            },
        }


@app.get("/speakers_list")
def speakers_list() -> list[str]:
    with runtime.lock:
        return list(runtime.voice_names)


@app.get("/speakers_list_extended")
def speakers_list_extended() -> list[dict]:
    with runtime.lock:
        return [
            {
                "voice_id": profile.name,
                "display_name": profile.metadata.get("display_name", profile.name),
                "language": runtime.active_language.id,
                "language_profile_id": profile.metadata.get(
                    "language_profile_id", runtime.active_language.id
                ),
                "custom_voice": bool(profile.metadata.get("custom_voice", False)),
                "calibration_status": (
                    profile.metadata.get("calibration", {}).get("status")
                    if isinstance(profile.metadata.get("calibration"), dict)
                    else None
                ),
                "reference_wav": str(profile.reference_wav),
                "reference_text": str(profile.reference_txt),
                "metadata": dict(profile.metadata),
                "cached_prompt": profile.prompt is not None,
            }
            for profile in runtime.voices.values()
        ]


@app.get("/languages")
def languages() -> list[str]:
    # XTTS compatibility: expose the currently active library only. Switching is
    # handled by /active_language so a CHIM request cannot accidentally select a
    # different, uncalibrated library.
    with runtime.lock:
        return [runtime.active_language.id, runtime.active_language.display_name]


@app.get("/active_language")
def active_language() -> dict:
    with runtime.lock:
        return {
            "active": runtime.active_language.public_dict(),
            "voice_count": len(runtime.voice_names),
            "voice_directory": str(runtime.active_voice_dir),
        }


@app.post("/active_language")
def set_active_language(request: LanguageSwitchRequest) -> dict:
    try:
        # Do not replace a voice library while the GPU is generating or creating a prompt.
        with generation_lock:
            profile = runtime.switch_language(request.language)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (OSError, ValueError, RuntimeError) as exc:
        raise HTTPException(status_code=500, detail=f"{type(exc).__name__}: {exc}") from exc

    return {
        "status": "switched",
        "active": profile.public_dict(),
        "voice_count": len(runtime.voice_names),
        "voices": runtime.voice_names,
    }


@app.post("/reload_voices")
def reload_voices() -> dict:
    with generation_lock:
        runtime.reload_voices()
    return {
        "status": "reloaded",
        "active_language": runtime.active_language.id,
        "voice_count": len(runtime.voice_names),
        "voices": runtime.voice_names,
    }


@app.post("/set_tts_settings")
def set_tts_settings(_: TTSSettingsRequest) -> dict:
    # XTTS/Chatterbox/PocketTTS-compatible endpoint. OmniVoice generation is
    # driven by language profiles and calibration metadata, so the current
    # component accepts these settings without changing runtime state.
    return {"status": "ok", "applied": False, "reason": "settings endpoint is compatibility-only"}


@app.post("/tts_to_audio/")
@app.post("/tts_to_audio")
def tts_to_audio(request: TTSRequest) -> Response:
    text = request.text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="Text must not be empty.")

    voice = runtime.resolve_voice(request.speaker_wav)
    with runtime.lock:
        language = runtime.active_language

    # The active language deliberately wins over the XTTS request language. This
    # keeps old CHIM connectors (which may send cs for Slovak) from selecting the
    # wrong voice library. A future native provider can switch /active_language.
    prompt = get_or_create_prompt(voice)
    started = time.perf_counter()

    try:
        with generation_lock, torch.inference_mode():
            audio = model.generate(
                text=text,
                language=language.omnivoice_language,
                voice_clone_prompt=prompt,
                generation_config=runtime_generation_config,
                speed=request.speed,
            )

        if not audio:
            raise RuntimeError("OmniVoice returned no audio.")

        wav_buffer = io.BytesIO()
        sf.write(
            wav_buffer,
            audio[0],
            sampling_rate,
            format="WAV",
            subtype="PCM_16",
        )
        wav_bytes = wav_buffer.getvalue()
        elapsed = time.perf_counter() - started

        log.info(
            "Generated %.2f s request | voice=%s | language=%s | chars=%d | bytes=%d",
            elapsed,
            voice.name,
            language.id,
            len(text),
            len(wav_bytes),
        )
        return Response(
            content=wav_bytes,
            media_type="audio/wav",
            headers={
                "X-OmniVoice-Voice": voice.name,
                "X-OmniVoice-Language": language.id,
                "X-Generation-Seconds": f"{elapsed:.3f}",
            },
        )

    except HTTPException:
        raise
    except Exception as exc:
        log.exception("TTS generation failed for voice %s.", voice.name)
        raise HTTPException(
            status_code=500,
            detail=f"{type(exc).__name__}: {exc}",
        ) from exc
