from __future__ import annotations

import io
import hashlib
import json
import logging
import os
import re
import shutil
import uuid
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock, RLock
from urllib import request as urllib_request
from urllib.error import HTTPError, URLError

import librosa
import numpy as np
import soundfile as sf
import torch
from fastapi import FastAPI, File, Form, HTTPException, Query, UploadFile
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
from voice_library import audit_voice_dir, voice_id_problem


BASE_DIR = Path(__file__).resolve().parent
VOICES_ROOT = BASE_DIR / "voices"
PROFILES_DIR = BASE_DIR / "languages"
CONFIG_PATH = BASE_DIR / "config.json"
SAMPLE_RATE_FALLBACK = 24000
API_VERSION = "0.3.2"
REFERENCE_SAMPLE_RATE = 24000
DEFAULT_STT_ENDPOINT = "http://127.0.0.1:8022/v1/audio/transcriptions"
FALLBACK_STT_ENDPOINTS = ("http://127.0.0.1:8082/v1/audio/transcriptions",)


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


def voice_library_signature(language_dir: Path) -> tuple | None:
    if not language_dir.is_dir():
        return None

    entries: list[tuple] = []
    try:
        directories = sorted(
            (path for path in language_dir.iterdir() if path.is_dir()),
            key=lambda path: path.name.casefold(),
        )
    except OSError:
        return None

    for directory in directories:
        files: list[tuple[str, int, int]] = []
        for filename in ("reference.wav", "reference.txt", "voice.json", "metadata.json"):
            path = directory / filename
            try:
                stat = path.stat()
            except OSError:
                continue
            files.append((filename, stat.st_mtime_ns, stat.st_size))
        try:
            directory_mtime = directory.stat().st_mtime_ns
        except OSError:
            directory_mtime = 0
        entries.append((directory.name, directory_mtime, tuple(files)))

    try:
        root_stat = language_dir.stat()
        root_mtime = root_stat.st_mtime_ns
    except OSError:
        root_mtime = 0
    return (str(language_dir), root_mtime, tuple(entries))


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def normalized_voice_id_from_upload(filename: str, explicit_name: str | None) -> str:
    raw = (explicit_name or "").strip()
    if raw == "":
        raw = Path(filename.strip()).stem
    raw = raw.strip()
    problem = voice_id_problem(raw)
    if problem is not None:
        raise HTTPException(
            status_code=400,
            detail={"error": "invalid_voice_id", "voice_id": raw, "reason": problem},
        )
    return raw


def normalize_reference_audio(audio_bytes: bytes) -> tuple[np.ndarray, float]:
    try:
        audio, sample_rate = sf.read(io.BytesIO(audio_bytes), always_2d=False, dtype="float32")
    except Exception as exc:
        raise HTTPException(
            status_code=400,
            detail={"error": "invalid_audio", "detail": f"{type(exc).__name__}: {exc}"},
        ) from exc

    if getattr(audio, "ndim", 1) == 2:
        audio = audio.mean(axis=1)
    if audio.size == 0:
        raise HTTPException(status_code=400, detail={"error": "empty_audio"})

    duration = float(audio.shape[0] / sample_rate)
    if sample_rate != REFERENCE_SAMPLE_RATE:
        audio = librosa.resample(
            audio,
            orig_sr=sample_rate,
            target_sr=REFERENCE_SAMPLE_RATE,
            res_type="soxr_hq",
        )

    peak = float(np.max(np.abs(audio)))
    if peak > 1.0:
        audio = audio / peak

    return np.asarray(audio, dtype=np.float32), duration


def wav_bytes_from_audio(audio: np.ndarray) -> bytes:
    wav_buffer = io.BytesIO()
    sf.write(
        wav_buffer,
        audio,
        REFERENCE_SAMPLE_RATE,
        format="WAV",
        subtype="PCM_16",
    )
    return wav_buffer.getvalue()


def parse_text_response(body: bytes) -> str:
    raw = body.decode("utf-8", errors="replace").strip()
    if raw == "":
        return ""
    try:
        decoded = json.loads(raw)
    except json.JSONDecodeError:
        return " ".join(raw.split())
    if isinstance(decoded, dict):
        for key in ("text", "transcript", "transcription"):
            text = str(decoded.get(key, "")).strip()
            if text:
                return " ".join(text.split())
    return ""


def post_multipart_for_transcription(endpoint: str, filename: str, audio_bytes: bytes, language: str) -> str:
    boundary = "----omnivoice-" + uuid.uuid4().hex
    parts: list[bytes] = []

    def add_field(name: str, value: str) -> None:
        parts.append(
            (
                f"--{boundary}\r\n"
                f'Content-Disposition: form-data; name="{name}"\r\n\r\n'
                f"{value}\r\n"
            ).encode("utf-8")
        )

    def add_file(name: str, upload_name: str, content: bytes) -> None:
        parts.append(
            (
                f"--{boundary}\r\n"
                f'Content-Disposition: form-data; name="{name}"; filename="{upload_name}"\r\n'
                "Content-Type: audio/wav\r\n\r\n"
            ).encode("utf-8")
        )
        parts.append(content)
        parts.append(b"\r\n")

    add_file("file", filename, audio_bytes)
    add_field("model", "parakeet-tdt-0.6b-v3")
    if language:
        add_field("language", language)
    add_field("response_format", "json")
    parts.append(f"--{boundary}--\r\n".encode("utf-8"))
    body = b"".join(parts)

    req = urllib_request.Request(
        endpoint,
        data=body,
        headers={
            "Content-Type": f"multipart/form-data; boundary={boundary}",
            "Accept": "application/json",
        },
        method="POST",
    )
    with urllib_request.urlopen(req, timeout=45) as response:
        return parse_text_response(response.read())


def auto_transcribe_reference(audio_bytes: bytes, filename: str, profile: LanguageProfile) -> tuple[str, str, str | None]:
    configured_endpoint = os.environ.get("OMNIVOICE_STT_ENDPOINT", DEFAULT_STT_ENDPOINT).strip()
    if configured_endpoint == "":
        return "", "unavailable", "OMNIVOICE_STT_ENDPOINT is empty"

    endpoints = [configured_endpoint]
    if configured_endpoint == DEFAULT_STT_ENDPOINT:
        endpoints.extend(endpoint for endpoint in FALLBACK_STT_ENDPOINTS if endpoint not in endpoints)

    errors: list[str] = []
    for endpoint in endpoints:
        try:
            text = post_multipart_for_transcription(
                endpoint,
                filename,
                audio_bytes,
                profile.whisper_language or profile.id,
            )
        except (HTTPError, URLError, TimeoutError, OSError, ValueError) as exc:
            errors.append(f"{endpoint}: {type(exc).__name__}: {exc}")
            continue

        if not text:
            errors.append(f"{endpoint}: STT returned an empty transcript")
            continue

        if text[-1] not in ".!?。！？":
            text += "."
        return text, "auto_transcribed", None

    return "", "failed", "; ".join(errors) if errors else "STT failed"


def write_imported_voice(
    *,
    profile: LanguageProfile,
    voice_id: str,
    source_filename: str,
    source_bytes: bytes,
    reference_text: str,
    reference_text_source: str,
    transcription_error: str | None,
    display_name: str,
    force: bool,
) -> dict:
    voice_dir = VOICES_ROOT / profile.id / voice_id
    if voice_dir.exists() and not force:
        raise HTTPException(
            status_code=409,
            detail={
                "error": "voice_exists",
                "voice_id": voice_id,
                "language": profile.id,
                "hint": "Use force=true to overwrite this voice.",
            },
        )
    if voice_dir.exists() and force:
        calibration_dir = voice_dir / "calibration"
        if calibration_dir.exists():
            shutil.rmtree(calibration_dir)
        for filename in (
            "reference_stage1.wav",
            "reference_stage1.txt",
            "reference_master.wav",
            "reference_master.txt",
            "auto_calibration.json",
        ):
            path = voice_dir / filename
            if path.exists():
                path.unlink()

    voice_dir.mkdir(parents=True, exist_ok=True)
    source_hash = sha256_bytes(source_bytes)
    audio_24k, duration = normalize_reference_audio(source_bytes)
    normalized_wav = wav_bytes_from_audio(audio_24k)

    source_path = voice_dir / "source.wav"
    reference_ready = reference_text.strip() != ""

    source_path.write_bytes(source_bytes)
    for wav_name in ("reference.wav", "reference_source.wav", "reference_en.wav"):
        (voice_dir / wav_name).write_bytes(normalized_wav)
    if reference_ready:
        for txt_name in ("reference.txt", "reference_source.txt", "reference_en.txt"):
            (voice_dir / txt_name).write_text(reference_text.strip() + "\n", encoding="utf-8")
    else:
        for txt_name in ("reference.txt", "reference_source.txt", "reference_en.txt"):
            path = voice_dir / txt_name
            if path.exists():
                path.unlink()

    status = "runtime_ready" if reference_ready else "needs_reference_text"
    metadata = {
        "voice_id": voice_id,
        "voice_origin": "tts_studio_upload",
        "custom_voice": True,
        "display_name": display_name.strip() or voice_id,
        "language_profile_id": profile.id,
        "target_language": profile.display_name,
        "source_filename": source_filename,
        "source_sha256": source_hash,
        "source_size_bytes": len(source_bytes),
        "source_duration_seconds": round(duration, 3),
        "reference_sample_rate": REFERENCE_SAMPLE_RATE,
        "reference_channels": 1,
        "reference_subtype": "PCM_16",
        "reference_text": reference_text.strip(),
        "reference_text_source": reference_text_source,
        "transcription_provider": (
            os.environ.get("OMNIVOICE_STT_ENDPOINT", DEFAULT_STT_ENDPOINT).strip()
            if reference_text_source == "auto_transcribed"
            else None
        ),
        "transcription_error": transcription_error,
        "status": status,
        "prepared_at_utc": utc_now(),
        "calibration": {"status": "not_calibrated"},
    }
    (voice_dir / "voice.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    return {
        "voice_id": voice_id,
        "language": profile.id,
        "voice_directory": str(voice_dir),
        "status": status,
        "reference_text_source": reference_text_source,
        "transcription_error": transcription_error,
        "duration_seconds": round(duration, 3),
        "source_sha256": source_hash,
    }


def resolve_optional_language(language: str | None) -> LanguageProfile:
    requested = str(language or "").strip()
    if requested == "":
        return runtime.active_language
    try:
        return resolve_profile(requested, PROFILES_DIR, runtime.language_profiles)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


def voice_library_items(profile: LanguageProfile) -> list[dict]:
    language_dir = VOICES_ROOT / profile.id
    if not language_dir.is_dir():
        return []

    items: list[dict] = []
    for directory in sorted(
        (path for path in language_dir.iterdir() if path.is_dir()),
        key=lambda path: path.name.casefold(),
    ):
        metadata: dict = {}
        metadata_path = directory / "voice.json"
        if metadata_path.is_file():
            try:
                loaded = json.loads(metadata_path.read_text(encoding="utf-8"))
                if isinstance(loaded, dict):
                    metadata = loaded
            except (OSError, json.JSONDecodeError):
                metadata = {}

        audit = audit_voice_dir(directory, expected_language_id=profile.id)
        status = str(metadata.get("status") or audit.status)
        if audit.runtime_ready:
            status = "ready" if audit.calibrated else "runtime_ready"
        elif status == "runtime_ready":
            status = "needs_reference_text"

        items.append(
            {
                "voice_id": directory.name,
                "display_name": metadata.get("display_name", directory.name),
                "language": profile.id,
                "language_profile_id": metadata.get("language_profile_id", profile.id),
                "status": status,
                "runtime_ready": audit.runtime_ready,
                "calibrated": audit.calibrated,
                "calibration_status": audit.calibration_status,
                "custom_voice": bool(metadata.get("custom_voice", False)),
                "reference_wav": str(directory / "reference.wav"),
                "reference_text": str(directory / "reference.txt"),
                "reference_text_source": metadata.get("reference_text_source"),
                "transcription_error": metadata.get("transcription_error"),
                "errors": list(audit.errors),
                "warnings": list(audit.warnings),
                "metadata": metadata,
            }
        )
    return items


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
        self.voice_library_signature: tuple | None = None
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
        self.voice_library_signature = voice_library_signature(self.active_voice_dir)
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

    def sync_voices_if_changed_unlocked(self) -> bool:
        current = voice_library_signature(self.active_voice_dir)
        if current == self.voice_library_signature:
            return False

        previous_count = len(self.voice_names)
        self.reload_voices_unlocked()
        log.info(
            "Voice library change detected for %s; reloaded %d -> %d voice(s).",
            self.active_language.id,
            previous_count,
            len(self.voice_names),
        )
        return True

    def sync_voices_if_changed(self) -> bool:
        with self.lock:
            return self.sync_voices_if_changed_unlocked()

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
            self.sync_voices_if_changed_unlocked()
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
        runtime.sync_voices_if_changed_unlocked()
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
        runtime.sync_voices_if_changed_unlocked()
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
        runtime.sync_voices_if_changed_unlocked()
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


@app.get("/voice_libraries")
def voice_libraries() -> list[dict]:
    with runtime.lock:
        runtime.sync_voices_if_changed_unlocked()
        libraries = []
        for profile in sorted(runtime.language_profiles.values(), key=lambda item: item.id):
            items = voice_library_items(profile)
            ready_count = sum(1 for item in items if bool(item.get("runtime_ready")))
            libraries.append(
                {
                    **profile.public_dict(),
                    "voice_directory": str(VOICES_ROOT / profile.id),
                    "voice_count": ready_count,
                    "total_voice_folders": len(items),
                    "active": profile.id == runtime.active_language.id,
                }
            )
        return libraries


@app.get("/speakers_list")
def speakers_list(language: str | None = Query(default=None)) -> list[str]:
    with runtime.lock:
        profile = resolve_optional_language(language)
        if profile.id == runtime.active_language.id:
            runtime.sync_voices_if_changed_unlocked()
            return list(runtime.voice_names)

    voices, _ = discover_voices(VOICES_ROOT / profile.id)
    return list(voices.keys())


@app.get("/speakers_list_extended")
def speakers_list_extended(language: str | None = Query(default=None)) -> list[dict]:
    with runtime.lock:
        profile = resolve_optional_language(language)
        if profile.id == runtime.active_language.id:
            runtime.sync_voices_if_changed_unlocked()
            cached = {item.name for item in runtime.voices.values() if item.prompt is not None}
        else:
            cached = set()

    items = voice_library_items(profile)
    for item in items:
        item["cached_prompt"] = str(item.get("voice_id", "")) in cached
    return items


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
        runtime.sync_voices_if_changed_unlocked()
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


@app.post("/upload_sample")
async def upload_sample(
    wavFile: UploadFile = File(...),
    language: str | None = Form(default=None),
    speaker_name: str | None = Form(default=None),
    speaker_id: str | None = Form(default=None),
    reference_text: str | None = Form(default=None),
    display_name: str | None = Form(default=None),
    force: bool = Form(default=False),
) -> dict:
    source_bytes = await wavFile.read()
    if not source_bytes:
        raise HTTPException(status_code=400, detail={"error": "empty_upload"})

    with runtime.lock:
        profile = resolve_optional_language(language)

    voice_id = normalized_voice_id_from_upload(
        wavFile.filename or "uploaded.wav",
        speaker_name or speaker_id,
    )

    text = " ".join(str(reference_text or "").split())
    text_source = "manual" if text else "missing"
    transcription_error: str | None = None
    if not text:
        text, text_source, transcription_error = auto_transcribe_reference(
            source_bytes,
            wavFile.filename or (voice_id + ".wav"),
            profile,
        )

    result = write_imported_voice(
        profile=profile,
        voice_id=voice_id,
        source_filename=wavFile.filename or (voice_id + ".wav"),
        source_bytes=source_bytes,
        reference_text=text,
        reference_text_source=text_source,
        transcription_error=transcription_error,
        display_name=str(display_name or "").strip() or voice_id,
        force=force,
    )

    if profile.id == runtime.active_language.id:
        with generation_lock:
            runtime.reload_voices()

    return {
        **result,
        "status": "ok" if result["status"] == "runtime_ready" else result["status"],
        "import_status": result["status"],
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
