from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import re
import shutil
import sys
import time
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from language_profiles import (
    LanguageProfile,
    load_profiles,
    load_runtime_config,
    resolve_profile,
)
from voice_library import voice_id_problem


BASE_DIR = Path(__file__).resolve().parent
DEFAULT_VOICES_ROOT = BASE_DIR / "voices"
DEFAULT_PROFILES_DIR = BASE_DIR / "languages"
DEFAULT_CONFIG = BASE_DIR / "config.json"
DEFAULT_REPORTS_ROOT = BASE_DIR / "reports"

OMNIVOICE_MODEL = "k2-fsa/OmniVoice"
WHISPER_MODEL = "openai/whisper-large-v3-turbo"
SPEAKER_MODEL = "microsoft/wavlm-base-plus-sv"

DEVICE = "cuda:0"
SAMPLE_RATE = 24000
ASR_SAMPLE_RATE = 16000

TRANSCRIPT_WEIGHT = 0.50
SOURCE_SPEAKER_WEIGHT = 0.28
STAGE1_SPEAKER_WEIGHT = 0.12
AUDIO_QUALITY_WEIGHT = 0.10

REVIEW_OVERALL_BELOW = 0.82
REVIEW_TRANSCRIPT_BELOW = 0.94
REVIEW_SOURCE_SPEAKER_BELOW = 0.62
REVIEW_AUDIO_QUALITY_BELOW = 0.82

librosa = None
np = None
sf = None
torch = None
F = None
OmniVoice = None
OmniVoiceGenerationConfig = None
AutoFeatureExtractor = None
AutoModelForAudioXVector = None
pipeline = None


def load_heavy_dependencies() -> None:
    global librosa, np, sf, torch, F, OmniVoice, OmniVoiceGenerationConfig
    global AutoFeatureExtractor, AutoModelForAudioXVector, pipeline

    if torch is not None:
        return

    import librosa as librosa_module
    import numpy as np_module
    import soundfile as sf_module
    import torch as torch_module
    import torch.nn.functional as functional_module
    from omnivoice import OmniVoice as OmniVoiceClass
    from omnivoice import OmniVoiceGenerationConfig as OmniVoiceGenerationConfigClass
    from transformers import AutoFeatureExtractor as AutoFeatureExtractorClass
    from transformers import pipeline as pipeline_function

    try:
        from transformers import AutoModelForAudioXVector as AutoModelClass
    except ImportError:
        from transformers import WavLMForXVector as AutoModelClass

    librosa = librosa_module
    np = np_module
    sf = sf_module
    torch = torch_module
    F = functional_module
    OmniVoice = OmniVoiceClass
    OmniVoiceGenerationConfig = OmniVoiceGenerationConfigClass
    AutoFeatureExtractor = AutoFeatureExtractorClass
    AutoModelForAudioXVector = AutoModelClass
    pipeline = pipeline_function


@dataclass
class CandidateScore:
    number: int
    wav_path: Path
    intended_text: str
    transcript: str
    transcript_similarity: float
    source_speaker_similarity: float
    stage1_speaker_similarity: float | None
    audio_quality: float
    overall: float
    duration_seconds: float
    peak: float
    rms_dbfs: float
    clipping_ratio: float
    silence_ratio: float
    spike_ratio: float
    generation_seconds: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "number": self.number,
            "wav": self.wav_path.name,
            "intended_text": self.intended_text,
            "transcript": self.transcript,
            "transcript_similarity": round(self.transcript_similarity, 6),
            "source_speaker_similarity": round(
                self.source_speaker_similarity, 6
            ),
            "stage1_speaker_similarity": (
                round(self.stage1_speaker_similarity, 6)
                if self.stage1_speaker_similarity is not None
                else None
            ),
            "audio_quality": round(self.audio_quality, 6),
            "overall": round(self.overall, 6),
            "duration_seconds": round(self.duration_seconds, 3),
            "peak": round(self.peak, 6),
            "rms_dbfs": round(self.rms_dbfs, 3),
            "clipping_ratio": round(self.clipping_ratio, 8),
            "silence_ratio": round(self.silence_ratio, 6),
            "spike_ratio": round(self.spike_ratio, 8),
            "generation_seconds": round(self.generation_seconds, 3),
        }


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def save_json(path: Path, data: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def write_text(path: Path, text: str) -> None:
    path.write_text(text.strip() + "\n", encoding="utf-8")


def read_text(path: Path) -> str:
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        raise ValueError(f"Text file is empty: {path}")
    return text


def _same_path(source: Path, destination: Path) -> bool:
    try:
        return source.resolve() == destination.resolve()
    except OSError:
        return str(source.absolute()).casefold() == str(destination.absolute()).casefold()


def copy_file_if_different(source: Path, destination: Path) -> None:
    if _same_path(source, destination):
        return
    shutil.copy2(source, destination)


def copy_pair(
    source_wav: Path,
    source_txt: Path,
    destination_wav: Path,
    destination_txt: Path,
) -> None:
    copy_file_if_different(source_wav, destination_wav)
    copy_file_if_different(source_txt, destination_txt)


def normalize_text(text: str) -> str:
    # Generic Unicode normalization. It preserves letters and numbers from any
    # script while removing punctuation, symbols and underscores.
    text = unicodedata.normalize("NFKC", text.casefold())
    text = re.sub(r"[\W_]+", " ", text, flags=re.UNICODE)
    return " ".join(text.split())


def levenshtein_distance(a: str, b: str) -> int:
    if len(a) < len(b):
        a, b = b, a
    previous = list(range(len(b) + 1))
    for i, char_a in enumerate(a, start=1):
        current = [i]
        for j, char_b in enumerate(b, start=1):
            current.append(
                min(
                    current[-1] + 1,
                    previous[j] + 1,
                    previous[j - 1] + (char_a != char_b),
                )
            )
        previous = current
    return previous[-1]


def text_similarity(expected: str, actual: str) -> float:
    expected_norm = normalize_text(expected)
    actual_norm = normalize_text(actual)
    denominator = max(len(expected_norm), len(actual_norm), 1)
    distance = levenshtein_distance(expected_norm, actual_norm)
    return max(0.0, 1.0 - distance / denominator)


def load_audio(path: Path, target_sr: int) -> np.ndarray:
    load_heavy_dependencies()
    audio, sample_rate = sf.read(path, always_2d=False, dtype="float32")
    if audio.ndim == 2:
        audio = audio.mean(axis=1)
    if audio.size == 0:
        raise ValueError(f"Audio file is empty: {path}")
    if sample_rate != target_sr:
        audio = librosa.resample(
            audio,
            orig_sr=sample_rate,
            target_sr=target_sr,
            res_type="soxr_hq",
        )
    return np.asarray(audio, dtype=np.float32)


def audio_metrics(path: Path) -> dict[str, float]:
    audio = load_audio(path, SAMPLE_RATE)
    absolute = np.abs(audio)
    peak = float(np.max(absolute))
    rms = float(np.sqrt(np.mean(np.square(audio)) + 1e-12))
    rms_dbfs = 20.0 * math.log10(max(rms, 1e-9))
    clipping_ratio = float(np.mean(absolute >= 0.995))
    silence_ratio = float(np.mean(absolute <= 0.003))
    differences = np.abs(np.diff(audio))
    spike_ratio = float(np.mean(differences >= 0.50)) if differences.size else 0.0
    duration = float(audio.size / SAMPLE_RATE)

    score = 1.0
    if clipping_ratio > 0.0001:
        score -= min(0.40, clipping_ratio * 300.0)
    if spike_ratio > 0.00002:
        score -= min(0.35, spike_ratio * 500.0)
    if silence_ratio > 0.45:
        score -= min(0.30, (silence_ratio - 0.45) * 1.5)
    if silence_ratio < 0.002:
        score -= 0.05
    if rms_dbfs < -34.0:
        score -= min(0.25, (-34.0 - rms_dbfs) / 30.0)
    if rms_dbfs > -7.0:
        score -= min(0.25, (rms_dbfs + 7.0) / 12.0)
    if peak < 0.08:
        score -= 0.20
    if duration < 3.0 or duration > 20.0:
        score -= 0.25

    return {
        "score": max(0.0, min(1.0, score)),
        "duration": duration,
        "peak": peak,
        "rms_dbfs": rms_dbfs,
        "clipping_ratio": clipping_ratio,
        "silence_ratio": silence_ratio,
        "spike_ratio": spike_ratio,
    }


class Models:
    def __init__(self) -> None:
        load_heavy_dependencies()
        if not torch.cuda.is_available():
            raise RuntimeError("CUDA is not available.")

        print(f"GPU: {torch.cuda.get_device_name(0)}")
        print(f"Loading OmniVoice: {OMNIVOICE_MODEL}")
        self.omnivoice = OmniVoice.from_pretrained(
            OMNIVOICE_MODEL,
            device_map=DEVICE,
            dtype=torch.float16,
            load_asr=False,
        )
        self.omnivoice_sample_rate = int(
            getattr(self.omnivoice, "sampling_rate", SAMPLE_RATE)
        )

        print(f"Loading Whisper: {WHISPER_MODEL}")
        common = {
            "task": "automatic-speech-recognition",
            "model": WHISPER_MODEL,
            "device": 0,
        }
        try:
            self.asr = pipeline(**common, dtype=torch.float16)
        except TypeError:
            self.asr = pipeline(**common, torch_dtype=torch.float16)

        print(f"Loading speaker verifier: {SPEAKER_MODEL}")
        self.speaker_extractor = AutoFeatureExtractor.from_pretrained(
            SPEAKER_MODEL
        )
        self.speaker_model = AutoModelForAudioXVector.from_pretrained(
            SPEAKER_MODEL
        ).to("cuda:0")
        self.speaker_model.eval()

        print("All models loaded.")

    def transcribe(self, wav_path: Path, whisper_language: str) -> str:
        audio = load_audio(wav_path, ASR_SAMPLE_RATE)
        result = self.asr(
            {"raw": audio, "sampling_rate": ASR_SAMPLE_RATE},
            generate_kwargs={"language": whisper_language, "task": "transcribe"},
            return_timestamps=False,
        )
        if isinstance(result, dict):
            text = str(result.get("text", "")).strip()
        else:
            text = str(result).strip()

        text = " ".join(text.split())
        if not text:
            raise RuntimeError(f"Whisper returned empty text for {wav_path}")
        if text[-1] not in ".!?":
            text += "."
        return text

    def speaker_embedding(self, wav_path: Path) -> torch.Tensor:
        audio = load_audio(wav_path, ASR_SAMPLE_RATE)
        inputs = self.speaker_extractor(
            audio,
            sampling_rate=ASR_SAMPLE_RATE,
            return_tensors="pt",
            padding=True,
        )
        inputs = {
            key: value.to("cuda:0")
            for key, value in inputs.items()
            if isinstance(value, torch.Tensor)
        }
        with torch.inference_mode():
            embedding = self.speaker_model(**inputs).embeddings
        return F.normalize(embedding.float(), p=2, dim=-1).squeeze(0).cpu()

    @staticmethod
    def cosine_similarity(a: torch.Tensor, b: torch.Tensor) -> float:
        value = F.cosine_similarity(a.unsqueeze(0), b.unsqueeze(0)).item()
        return max(0.0, min(1.0, (value + 1.0) / 2.0))


def discover_voice_dirs(voices_dir: Path) -> list[Path]:
    results: list[Path] = []
    for directory in sorted(voices_dir.iterdir(), key=lambda p: p.name.casefold()):
        if not directory.is_dir():
            continue
        if voice_id_problem(directory.name) is not None:
            continue
        if not (directory / "voice.json").is_file():
            continue
        if not (directory / "reference.wav").is_file():
            continue
        if not (directory / "reference.txt").is_file():
            continue
        results.append(directory)
    return results


def is_complete(voice_dir: Path, profile: LanguageProfile) -> bool:
    metadata = load_json(voice_dir / "voice.json")
    calibration = metadata.get("calibration")
    return (
        metadata.get("language_profile_id") == profile.id
        and isinstance(calibration, dict)
        and calibration.get("status") in {
            "master_selected",
            "auto_master_selected",
        }
        and calibration.get("language_profile_id") == profile.id
        and (voice_dir / "reference_master.wav").is_file()
        and (voice_dir / "reference_master.txt").is_file()
    )


def ensure_english_backup(voice_dir: Path) -> tuple[Path, Path]:
    en_wav = voice_dir / "reference_en.wav"
    en_txt = voice_dir / "reference_en.txt"
    if en_wav.is_file() and en_txt.is_file():
        return en_wav, en_txt

    # Prepared multilingual libraries always carry reference_en.*, but keep
    # this fallback for migrated legacy profiles.
    metadata = load_json(voice_dir / "voice.json")
    calibration = metadata.get("calibration")
    if isinstance(calibration, dict) and calibration.get("status") in {"master_selected", "auto_master_selected"}:
        raise RuntimeError(
            f"{voice_dir.name}: already calibrated, but reference_en.* is missing."
        )

    metadata = load_json(voice_dir / "voice.json")
    asr_language = str(metadata.get("asr_language", "")).casefold()
    if asr_language not in {"english", "en"}:
        raise RuntimeError(
            f"{voice_dir.name}: cannot safely identify active reference as English."
        )

    copy_pair(
        voice_dir / "reference.wav",
        voice_dir / "reference.txt",
        en_wav,
        en_txt,
    )
    return en_wav, en_txt


def prepare_stage_dir(stage_dir: Path, force: bool) -> None:
    if stage_dir.exists() and force:
        shutil.rmtree(stage_dir)
    if stage_dir.exists() and any(stage_dir.iterdir()):
        raise FileExistsError(
            f"Existing candidate data found in {stage_dir}. Use --force to replace it."
        )
    stage_dir.mkdir(parents=True, exist_ok=True)


def candidate_from_manifest(stage_dir: Path, data: dict[str, Any]) -> CandidateScore:
    wav_name = str(data.get("wav", ""))
    if not wav_name:
        raise ValueError(f"Missing candidate WAV name in {stage_dir / 'manifest.json'}")

    wav_path = stage_dir / wav_name
    if not wav_path.is_file():
        raise FileNotFoundError(f"Missing resumed candidate WAV: {wav_path}")

    return CandidateScore(
        number=int(data["number"]),
        wav_path=wav_path,
        intended_text=str(data.get("intended_text", "")),
        transcript=str(data.get("transcript", "")),
        transcript_similarity=float(data.get("transcript_similarity", 0.0)),
        source_speaker_similarity=float(data.get("source_speaker_similarity", 0.0)),
        stage1_speaker_similarity=(
            float(data["stage1_speaker_similarity"])
            if data.get("stage1_speaker_similarity") is not None
            else None
        ),
        audio_quality=float(data.get("audio_quality", 0.0)),
        overall=float(data.get("overall", 0.0)),
        duration_seconds=float(data.get("duration_seconds", 0.0)),
        peak=float(data.get("peak", 0.0)),
        rms_dbfs=float(data.get("rms_dbfs", 0.0)),
        clipping_ratio=float(data.get("clipping_ratio", 0.0)),
        silence_ratio=float(data.get("silence_ratio", 0.0)),
        spike_ratio=float(data.get("spike_ratio", 0.0)),
        generation_seconds=float(data.get("generation_seconds", 0.0)),
    )


def load_existing_stage(
    stage_dir: Path,
) -> tuple[CandidateScore, list[CandidateScore]] | None:
    manifest_path = stage_dir / "manifest.json"
    manifest = load_json(manifest_path)
    raw_candidates = manifest.get("candidates_ranked")
    winner_number = manifest.get("winner")

    if not manifest or not isinstance(raw_candidates, list) or winner_number is None:
        return None

    candidates = [
        candidate_from_manifest(stage_dir, item)
        for item in raw_candidates
        if isinstance(item, dict)
    ]
    if not candidates:
        return None

    winner = next(
        (item for item in candidates if item.number == int(winner_number)),
        None,
    )
    if winner is None:
        raise ValueError(f"Winner #{winner_number} is missing in {manifest_path}")

    print(
        f"  RESUME {stage_dir.name}: reusing {len(candidates)} scored candidate(s), "
        f"winner #{winner.number}"
    )
    return winner, candidates


def score_candidate(
    *,
    models: Models,
    profile: LanguageProfile,
    number: int,
    wav_path: Path,
    intended_text: str,
    source_embedding: torch.Tensor,
    stage1_embedding: torch.Tensor | None,
    generation_seconds: float,
) -> CandidateScore:
    transcript = models.transcribe(wav_path, profile.whisper_language)
    transcript_score = text_similarity(intended_text, transcript)

    candidate_embedding = models.speaker_embedding(wav_path)
    source_similarity = models.cosine_similarity(
        source_embedding, candidate_embedding
    )
    stage1_similarity = (
        models.cosine_similarity(stage1_embedding, candidate_embedding)
        if stage1_embedding is not None
        else None
    )

    metrics = audio_metrics(wav_path)
    stage1_component = (
        stage1_similarity if stage1_similarity is not None else source_similarity
    )
    overall = (
        TRANSCRIPT_WEIGHT * transcript_score
        + SOURCE_SPEAKER_WEIGHT * source_similarity
        + STAGE1_SPEAKER_WEIGHT * stage1_component
        + AUDIO_QUALITY_WEIGHT * metrics["score"]
    )

    return CandidateScore(
        number=number,
        wav_path=wav_path,
        intended_text=intended_text,
        transcript=transcript,
        transcript_similarity=transcript_score,
        source_speaker_similarity=source_similarity,
        stage1_speaker_similarity=stage1_similarity,
        audio_quality=metrics["score"],
        overall=overall,
        duration_seconds=metrics["duration"],
        peak=metrics["peak"],
        rms_dbfs=metrics["rms_dbfs"],
        clipping_ratio=metrics["clipping_ratio"],
        silence_ratio=metrics["silence_ratio"],
        spike_ratio=metrics["spike_ratio"],
        generation_seconds=generation_seconds,
    )


def generate_and_rank(
    *,
    models: Models,
    profile: LanguageProfile,
    voice_dir: Path,
    stage_name: str,
    reference_wav: Path,
    reference_txt: Path,
    intended_text: str,
    count: int,
    num_step: int,
    speed: float,
    source_embedding: torch.Tensor,
    stage1_embedding: torch.Tensor | None,
    force: bool,
) -> tuple[CandidateScore, list[CandidateScore]]:
    stage_dir = voice_dir / "calibration" / f"auto_{stage_name}"

    if not force:
        resumed = load_existing_stage(stage_dir)
        if resumed is not None:
            return resumed

    prepare_stage_dir(stage_dir, force=force)

    prompt_text = read_text(reference_txt)
    with torch.inference_mode():
        prompt = models.omnivoice.create_voice_clone_prompt(
            ref_audio=str(reference_wav),
            ref_text=prompt_text,
        )

    config = OmniVoiceGenerationConfig(
        num_step=num_step,
        guidance_scale=2.0,
        denoise=True,
        preprocess_prompt=True,
        postprocess_output=True,
    )

    candidates: list[CandidateScore] = []
    for number in range(1, count + 1):
        wav_path = stage_dir / f"candidate_{number:02d}.wav"
        started = time.perf_counter()

        with torch.inference_mode():
            audio = models.omnivoice.generate(
                text=intended_text,
                language=profile.omnivoice_language,
                voice_clone_prompt=prompt,
                generation_config=config,
                speed=speed,
            )

        if not audio:
            raise RuntimeError(
                f"{voice_dir.name}/{stage_name}/{number}: no audio returned."
            )

        sf.write(
            wav_path,
            audio[0],
            models.omnivoice_sample_rate,
            format="WAV",
            subtype="PCM_16",
        )
        generation_seconds = time.perf_counter() - started

        score = score_candidate(
            models=models,
            profile=profile,
            number=number,
            wav_path=wav_path,
            intended_text=intended_text,
            source_embedding=source_embedding,
            stage1_embedding=stage1_embedding,
            generation_seconds=generation_seconds,
        )
        candidates.append(score)

        write_text(
            stage_dir / f"candidate_{number:02d}.txt",
            score.transcript,
        )

        print(
            f"  {stage_name} {number:02d}/{count:02d} | "
            f"overall={score.overall:.4f} | "
            f"text={score.transcript_similarity:.4f} | "
            f"speaker={score.source_speaker_similarity:.4f} | "
            f"quality={score.audio_quality:.4f}"
        )

    candidates.sort(key=lambda item: item.overall, reverse=True)
    winner = candidates[0]

    save_json(
        stage_dir / "manifest.json",
        {
            "voice_id": voice_dir.name,
            "language_profile_id": profile.id,
            "target_language": profile.display_name,
            "stage": stage_name,
            "created_at_utc": utc_now(),
            "reference_wav": str(reference_wav),
            "reference_txt": str(reference_txt),
            "intended_text": intended_text,
            "settings": {
                "count": count,
                "num_step": num_step,
                "speed": speed,
                "guidance_scale": 2.0,
                "denoise": True,
                "preprocess_prompt": True,
                "postprocess_output": True,
            },
            "winner": winner.number,
            "candidates_ranked": [item.to_dict() for item in candidates],
        },
    )

    return winner, candidates


def review_reasons(score: CandidateScore) -> list[str]:
    reasons: list[str] = []
    if score.overall < REVIEW_OVERALL_BELOW:
        reasons.append(f"overall {score.overall:.3f}")
    if score.transcript_similarity < REVIEW_TRANSCRIPT_BELOW:
        reasons.append(f"text {score.transcript_similarity:.3f}")
    if score.source_speaker_similarity < REVIEW_SOURCE_SPEAKER_BELOW:
        reasons.append(f"speaker {score.source_speaker_similarity:.3f}")
    if score.audio_quality < REVIEW_AUDIO_QUALITY_BELOW:
        reasons.append(f"audio {score.audio_quality:.3f}")
    return reasons


def promote_master(
    *,
    profile: LanguageProfile,
    voice_dir: Path,
    english_wav: Path,
    english_txt: Path,
    bootstrap: CandidateScore,
    master: CandidateScore,
) -> dict[str, Any]:
    copy_pair(
        english_wav,
        english_txt,
        voice_dir / "reference_en.wav",
        voice_dir / "reference_en.txt",
    )

    bootstrap_txt = (
        voice_dir
        / "calibration"
        / "auto_bootstrap"
        / f"candidate_{bootstrap.number:02d}.txt"
    )
    master_txt = (
        voice_dir
        / "calibration"
        / "auto_master"
        / f"candidate_{master.number:02d}.txt"
    )

    copy_pair(
        bootstrap.wav_path,
        bootstrap_txt,
        voice_dir / "reference_stage1.wav",
        voice_dir / "reference_stage1.txt",
    )
    copy_pair(
        master.wav_path,
        master_txt,
        voice_dir / "reference_master.wav",
        voice_dir / "reference_master.txt",
    )
    copy_pair(
        master.wav_path,
        master_txt,
        voice_dir / "reference.wav",
        voice_dir / "reference.txt",
    )

    reasons = review_reasons(master)
    status = "review_required" if reasons else "auto_accepted"

    save_json(
        voice_dir / "auto_calibration.json",
        {
            "voice_id": voice_dir.name,
            "language_profile_id": profile.id,
            "target_language": profile.display_name,
            "status": status,
            "selected_at_utc": utc_now(),
            "bootstrap_candidate": bootstrap.number,
            "master_candidate": master.number,
            "master_scores": master.to_dict(),
            "review_reasons": reasons,
            "active_reference": {
                "wav": "reference.wav",
                "txt": "reference.txt",
                "language": profile.display_name,
                "language_profile_id": profile.id,
            },
        },
    )

    voice_json_path = voice_dir / "voice.json"
    metadata = load_json(voice_json_path)
    metadata["active_reference_language"] = profile.display_name
    metadata["reference_text"] = read_text(voice_dir / "reference.txt")
    metadata["calibration"] = {
        "status": "auto_master_selected",
        "quality_status": status,
        "language": profile.display_name,
        "language_profile_id": profile.id,
        "omnivoice_language": profile.omnivoice_language,
        "omnivoice_language_id": profile.omnivoice_language_id,
        "whisper_language": profile.whisper_language,
        "master_wav": "reference_master.wav",
        "master_txt": "reference_master.txt",
        "master_sha256": sha256_file(voice_dir / "reference_master.wav"),
        "selected_at_utc": utc_now(),
        "review_reasons": reasons,
    }
    save_json(voice_json_path, metadata)

    return {
        "voice_id": voice_dir.name,
        "status": status,
        "bootstrap_candidate": bootstrap.number,
        "master_candidate": master.number,
        "overall": master.overall,
        "transcript_similarity": master.transcript_similarity,
        "source_speaker_similarity": master.source_speaker_similarity,
        "stage1_speaker_similarity": master.stage1_speaker_similarity,
        "audio_quality": master.audio_quality,
        "review_reasons": "; ".join(reasons),
    }


def calibrate_voice(
    *,
    models: Models,
    profile: LanguageProfile,
    voice_dir: Path,
    force: bool,
) -> dict[str, Any]:
    print("")
    print("=" * 72)
    print(f"VOICE: {voice_dir.name}")
    print("=" * 72)

    english_wav, english_txt = ensure_english_backup(voice_dir)
    source_embedding = models.speaker_embedding(english_wav)

    bootstrap_winner, _ = generate_and_rank(
        models=models,
        profile=profile,
        voice_dir=voice_dir,
        stage_name="bootstrap",
        reference_wav=english_wav,
        reference_txt=english_txt,
        intended_text=profile.bootstrap_text,
        count=profile.bootstrap_count,
        num_step=profile.bootstrap_num_step,
        speed=profile.bootstrap_speed,
        source_embedding=source_embedding,
        stage1_embedding=None,
        force=force,
    )

    bootstrap_txt = (
        voice_dir
        / "calibration"
        / "auto_bootstrap"
        / f"candidate_{bootstrap_winner.number:02d}.txt"
    )
    stage1_embedding = models.speaker_embedding(bootstrap_winner.wav_path)

    master_winner, _ = generate_and_rank(
        models=models,
        profile=profile,
        voice_dir=voice_dir,
        stage_name="master",
        reference_wav=bootstrap_winner.wav_path,
        reference_txt=bootstrap_txt,
        intended_text=profile.master_text,
        count=profile.master_count,
        num_step=profile.master_num_step,
        speed=profile.master_speed,
        source_embedding=source_embedding,
        stage1_embedding=stage1_embedding,
        force=force,
    )

    result = promote_master(
        profile=profile,
        voice_dir=voice_dir,
        english_wav=english_wav,
        english_txt=english_txt,
        bootstrap=bootstrap_winner,
        master=master_winner,
    )

    print(
        f"SELECTED: bootstrap #{bootstrap_winner.number}, "
        f"master #{master_winner.number}, "
        f"status={result['status']}"
    )
    return result


def save_summary(
    report_dir: Path,
    profile: LanguageProfile,
    rows: list[dict[str, Any]],
) -> None:
    report_dir.mkdir(parents=True, exist_ok=True)
    summary_json = report_dir / "auto_calibration_summary.json"
    summary_csv = report_dir / "auto_calibration_summary.csv"
    review_txt = report_dir / "AUTO_REVIEW_REQUIRED.txt"

    existing = load_json(summary_json)
    merged_by_voice: dict[str, dict[str, Any]] = {}
    old_rows = existing.get("rows_lowest_confidence_first", [])
    if isinstance(old_rows, list):
        for row in old_rows:
            if isinstance(row, dict) and row.get("voice_id"):
                merged_by_voice[str(row["voice_id"]).casefold()] = row
    for row in rows:
        merged_by_voice[str(row["voice_id"]).casefold()] = row

    rows_sorted = sorted(
        merged_by_voice.values(),
        key=lambda row: float(row["overall"]),
    )
    save_json(
        summary_json,
        {
            "created_at_utc": utc_now(),
            "language_profile": profile.public_dict(),
            "count": len(rows_sorted),
            "rows_lowest_confidence_first": rows_sorted,
        },
    )

    fieldnames = [
        "voice_id",
        "status",
        "bootstrap_candidate",
        "master_candidate",
        "overall",
        "transcript_similarity",
        "source_speaker_similarity",
        "stage1_speaker_similarity",
        "audio_quality",
        "review_reasons",
    ]
    with summary_csv.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows_sorted)

    review_rows = [row for row in rows_sorted if row["status"] == "review_required"]
    lines = [
        "Multilingual TTS automatic calibration - voices requiring review",
        f"Generated: {utc_now()}",
        "",
        (
            "The selector checks transcript fidelity, waveform integrity and "
            f"speaker similarity. It does NOT directly judge subtle {profile.display_name} accent or prosody."
        ),
        "",
    ]
    if not review_rows:
        lines.append("No voices crossed the conservative review thresholds.")
    else:
        for row in review_rows:
            lines.append(
                f"{row['voice_id']}: {row['review_reasons']} "
                f"(overall={float(row['overall']):.3f})"
            )
    review_txt.write_text("\n".join(lines) + "\n", encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    config = load_runtime_config(DEFAULT_CONFIG)
    active_language = str(config.get("active_language", "sk"))

    parser = argparse.ArgumentParser(
        description=(
            "Fully automatic two-stage multilingual calibration for prepared CHIM voices. "
            "The language JSON profile controls OmniVoice, Whisper, calibration text and "
            "the fixed 3 bootstrap + 6 master factory defaults."
        )
    )
    parser.add_argument(
        "--language",
        default=active_language,
        help=f"Language profile id or alias (default: active {active_language!r}).",
    )
    parser.add_argument(
        "--profiles-dir",
        type=Path,
        default=DEFAULT_PROFILES_DIR,
        help=f"Language profile directory (default: {DEFAULT_PROFILES_DIR}).",
    )
    parser.add_argument(
        "--voices-root",
        type=Path,
        default=DEFAULT_VOICES_ROOT,
        help=f"Multilingual voice library root (default: {DEFAULT_VOICES_ROOT}).",
    )
    parser.add_argument(
        "--reports-root",
        type=Path,
        default=DEFAULT_REPORTS_ROOT,
        help=f"Per-language report root (default: {DEFAULT_REPORTS_ROOT}).",
    )
    parser.add_argument(
        "--voice",
        action="append",
        default=[],
        help="Process a specific VoiceID. May be supplied repeatedly.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        help="Process only the first N uncalibrated voices (safe pilot mode).",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Process every uncalibrated prepared voice in the selected language library.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help=(
            "Rebuild selected voices and replace existing candidate directories. "
            "Use this after changing calibration sentences or generation settings."
        ),
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    profiles_dir = args.profiles_dir.expanduser()
    voices_root = args.voices_root.expanduser()
    reports_root = args.reports_root.expanduser()

    try:
        profiles = load_profiles(profiles_dir)
        profile = resolve_profile(args.language, profiles_dir, profiles)
    except (FileNotFoundError, ValueError, KeyError, RuntimeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    placeholder_fields = [
        name
        for name, value in (
            ("bootstrap_text", profile.bootstrap_text),
            ("master_text", profile.master_text),
        )
        if "REPLACE THIS" in value
    ]
    if placeholder_fields:
        print(
            "ERROR: language profile contains placeholder calibration text: "
            f"{', '.join(placeholder_fields)}. Edit {profiles_dir / (profile.id + '.json')} "
            "before importing or building voices.",
            file=sys.stderr,
        )
        return 2

    voices_dir = voices_root / profile.id
    report_dir = reports_root / profile.id

    if not voices_dir.is_dir():
        print(
            f"ERROR: language voice library not found: {voices_dir}\n"
            f"Run prepare_chim_voices.py --language {profile.id} first.",
            file=sys.stderr,
        )
        return 2

    all_dirs = discover_voice_dirs(voices_dir)
    by_name = {directory.name.casefold(): directory for directory in all_dirs}

    selected: list[Path] = []
    if args.voice:
        missing: list[str] = []
        for requested in args.voice:
            directory = by_name.get(requested.casefold())
            if directory is None:
                missing.append(requested)
            elif directory not in selected:
                selected.append(directory)
        if missing:
            print(
                f"ERROR: prepared VoiceID not found in {profile.id}: {', '.join(missing)}",
                file=sys.stderr,
            )
            return 2
    else:
        uncalibrated = [
            directory for directory in all_dirs if not is_complete(directory, profile)
        ]
        if args.limit is not None:
            if args.limit < 1:
                print("ERROR: --limit must be at least 1.", file=sys.stderr)
                return 2
            selected = uncalibrated[: args.limit]
        elif args.all:
            selected = uncalibrated
        else:
            print(
                "Safety stop: use --limit N for a pilot, --voice VoiceID, or --all.",
                file=sys.stderr,
            )
            return 2

    if not args.force:
        selected = [
            directory for directory in selected if not is_complete(directory, profile)
        ]

    print(f"Language profile: {profile.id} ({profile.display_name})")
    print(f"OmniVoice value:  {profile.omnivoice_language}")
    print(f"Whisper language: {profile.whisper_language}")
    print(
        f"Factory:          {profile.bootstrap_count} bootstrap @ {profile.bootstrap_num_step} "
        f"+ {profile.master_count} master @ {profile.master_num_step}"
    )
    print(f"Prepared profiles found: {len(all_dirs)}")
    print(f"Selected for automatic calibration: {len(selected)}")

    if not selected:
        print("Nothing to do.")
        return 0

    models = Models()
    rows: list[dict[str, Any]] = []
    failed: list[str] = []

    for index, voice_dir in enumerate(selected, start=1):
        print(f"\nQUEUE {index}/{len(selected)}")
        try:
            row = calibrate_voice(
                models=models,
                profile=profile,
                voice_dir=voice_dir,
                force=args.force,
            )
            rows.append(row)
            save_summary(report_dir, profile, [row])
        except Exception as exc:
            failed.append(f"{voice_dir.name}: {type(exc).__name__}: {exc}")
            print(f"FAILED: {failed[-1]}", file=sys.stderr)
            report_dir.mkdir(parents=True, exist_ok=True)
            failure_path = report_dir / "auto_calibration_failures.txt"
            failure_path.write_text("\n".join(failed) + "\n", encoding="utf-8")

    print("")
    print("=" * 72)
    print(f"Completed:   {len(rows)}")
    print(f"Failed:      {len(failed)}")
    print(f"Review list: {report_dir / 'AUTO_REVIEW_REQUIRED.txt'}")
    print(f"CSV report:  {report_dir / 'auto_calibration_summary.csv'}")
    print("=" * 72)

    if failed:
        failure_path = report_dir / "auto_calibration_failures.txt"
        failure_path.write_text("\n".join(failed) + "\n", encoding="utf-8")
        print(f"Failure log: {failure_path}")
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
