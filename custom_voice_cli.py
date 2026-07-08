from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import librosa
import numpy as np
import soundfile as sf
from language_profiles import load_profiles, load_runtime_config, resolve_profile, save_runtime_config
from voice_library import voice_id_problem


BASE_DIR = Path(__file__).resolve().parent
DEFAULT_CONFIG = BASE_DIR / "config.json"
DEFAULT_PROFILES_DIR = BASE_DIR / "languages"
DEFAULT_VOICES_ROOT = BASE_DIR / "voices"
DEFAULT_ASR_MODEL = "openai/whisper-large-v3-turbo"
REFERENCE_SAMPLE_RATE = 24000
ASR_SAMPLE_RATE = 16000


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_text(path: Path) -> str:
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        raise ValueError(f"Text file is empty: {path}")
    return " ".join(text.split())


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def load_audio(path: Path, target_sr: int) -> tuple[np.ndarray, int, float]:
    audio, sample_rate = sf.read(path, always_2d=False, dtype="float32")
    if audio.ndim == 2:
        audio = audio.mean(axis=1)
    if audio.size == 0:
        raise ValueError("Audio file is empty.")
    original_duration = float(audio.shape[0] / sample_rate)
    if sample_rate != target_sr:
        audio = librosa.resample(
            audio,
            orig_sr=sample_rate,
            target_sr=target_sr,
            res_type="soxr_hq",
        )
        sample_rate = target_sr
    peak = float(np.max(np.abs(audio)))
    if peak > 1.0:
        audio = audio / peak
    return np.asarray(audio, dtype=np.float32), sample_rate, original_duration


def build_asr(model_name: str):
    import torch
    from transformers import pipeline

    if not torch.cuda.is_available():
        raise RuntimeError("CUDA is not available; automatic transcription requires NVIDIA CUDA.")
    print(f"Loading Whisper ASR: {model_name}")
    print(f"GPU: {torch.cuda.get_device_name(0)}")
    common = {
        "task": "automatic-speech-recognition",
        "model": model_name,
        "device": 0,
    }
    try:
        return pipeline(**common, dtype=torch.float16)
    except TypeError:
        return pipeline(**common, torch_dtype=torch.float16)


def transcribe_source(asr, audio_16k: np.ndarray, source_language: str) -> str:
    generate_kwargs: dict[str, str] = {"task": "transcribe"}
    language = source_language.strip().casefold()
    if language and language != "auto":
        generate_kwargs["language"] = language
    result = asr(
        {"raw": audio_16k, "sampling_rate": ASR_SAMPLE_RATE},
        generate_kwargs=generate_kwargs,
        return_timestamps=False,
    )
    text = str(result.get("text", "") if isinstance(result, dict) else result).strip()
    text = " ".join(text.split())
    if not text:
        raise RuntimeError("Whisper returned an empty transcript. Provide reference text manually.")
    if text[-1] not in ".!?。！？":
        text += "."
    return text


def reset_derived_calibration(profile_dir: Path) -> None:
    calibration_dir = profile_dir / "calibration"
    if calibration_dir.exists():
        shutil.rmtree(calibration_dir)
    for filename in (
        "reference_stage1.wav",
        "reference_stage1.txt",
        "reference_master.wav",
        "reference_master.txt",
        "auto_calibration.json",
    ):
        path = profile_dir / filename
        if path.exists():
            path.unlink()


def build_parser() -> argparse.ArgumentParser:
    config = load_runtime_config(DEFAULT_CONFIG)
    active_language = str(config.get("active_language", "sk"))

    parser = argparse.ArgumentParser(
        description=(
            "Add a user-provided custom voice sample to a Multilingual TTS language library. "
            "The prepared voice can then be calibrated with auto_calibrate_chim_voices.py."
        )
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    add = subparsers.add_parser("add", help="Prepare one custom voice from a local WAV/FLAC/MP3/OGG file.")
    add.add_argument("--language", default=active_language, help=f"Target language profile id/alias (default: active {active_language!r}).")
    add.add_argument("--profiles-dir", type=Path, default=DEFAULT_PROFILES_DIR, help=f"Language profile directory (default: {DEFAULT_PROFILES_DIR}).")
    add.add_argument("--voices-root", type=Path, default=DEFAULT_VOICES_ROOT, help=f"Voice library root (default: {DEFAULT_VOICES_ROOT}).")
    add.add_argument("--voice", required=True, help="Custom VoiceID/folder name, for example alica_custom.")
    add.add_argument("--wav", type=Path, required=True, help="Reference audio file for this custom voice.")
    add.add_argument("--display-name", default="", help="Optional human-readable name stored in metadata.")
    add.add_argument("--text", default="", help="Exact text spoken in the reference audio. Recommended when known.")
    add.add_argument("--text-file", type=Path, help="UTF-8 text file containing the exact text spoken in the reference audio.")
    add.add_argument("--source-language", default="auto", help="Whisper transcription language if --text/--text-file is not provided. Use auto, english, slovak, japanese, etc. Default: auto.")
    add.add_argument("--asr-model", default=DEFAULT_ASR_MODEL, help=f"Whisper model for automatic transcription (default: {DEFAULT_ASR_MODEL}).")
    add.add_argument("--force", action="store_true", help="Overwrite an existing custom voice and reset derived calibration data.")
    add.add_argument("--make-default", action="store_true", help="Set this voice as preferred fallback/default voice in config.json.")
    return parser


def reference_text_from_args(args: argparse.Namespace, source_wav: Path) -> tuple[str, str, str]:
    if args.text and args.text_file:
        raise ValueError("Use either --text or --text-file, not both.")
    if args.text:
        text = " ".join(str(args.text).split())
        if len(text) < 2:
            raise ValueError("Reference text is too short.")
        return text, "manual", "manual"
    if args.text_file:
        text = read_text(args.text_file.expanduser())
        return text, "manual_text_file", "manual"

    audio_16k, _, _ = load_audio(source_wav, ASR_SAMPLE_RATE)
    asr = build_asr(args.asr_model)
    text = transcribe_source(asr, audio_16k, args.source_language)
    return text, "whisper", args.source_language.strip().casefold() or "auto"


def add_custom_voice(args: argparse.Namespace) -> int:
    voice_id = args.voice.strip()
    problem = voice_id_problem(voice_id)
    if problem is not None:
        raise ValueError(f"Invalid custom VoiceID {voice_id!r}: {problem}")

    source_wav = args.wav.expanduser()
    if not source_wav.is_file():
        raise FileNotFoundError(f"Reference audio file not found: {source_wav}")

    profiles = load_profiles(args.profiles_dir.expanduser())
    language = resolve_profile(args.language, args.profiles_dir.expanduser(), profiles)
    output_root = args.voices_root.expanduser() / language.id
    voice_dir = output_root / voice_id
    metadata_path = voice_dir / "voice.json"

    if voice_dir.exists() and not args.force:
        raise FileExistsError(
            f"Voice already exists: {voice_dir}\n"
            "Use --force to overwrite and reset calibration."
        )

    output_root.mkdir(parents=True, exist_ok=True)
    voice_dir.mkdir(parents=True, exist_ok=True)
    reset_derived_calibration(voice_dir)

    source_hash = sha256_file(source_wav)
    reference_text, text_source, asr_language = reference_text_from_args(args, source_wav)

    audio_24k, _, original_duration = load_audio(source_wav, REFERENCE_SAMPLE_RATE)

    # Keep the original input as source.wav, and write normalized 24 kHz mono
    # references for runtime/calibration. reference_en.* is retained as a
    # compatibility backup used by the existing calibration pipeline; for custom
    # voices it simply means "original source reference", not necessarily English.
    shutil.copy2(source_wav, voice_dir / "source.wav")
    for wav_name in ("reference.wav", "reference_en.wav", "reference_source.wav"):
        sf.write(voice_dir / wav_name, audio_24k, REFERENCE_SAMPLE_RATE, format="WAV", subtype="PCM_16")
    for txt_name in ("reference.txt", "reference_en.txt", "reference_source.txt"):
        (voice_dir / txt_name).write_text(reference_text.strip() + "\n", encoding="utf-8")

    metadata = {
        "voice_id": voice_id,
        "voice_origin": "custom_user_voice",
        "custom_voice": True,
        "display_name": args.display_name.strip() or voice_id,
        "language_profile_id": language.id,
        "target_language": language.display_name,
        "active_reference_language": "Custom source reference (not calibrated yet)",
        "source_filename": source_wav.name,
        "source_path": str(source_wav),
        "source_sha256": source_hash,
        "source_size_bytes": source_wav.stat().st_size,
        "source_duration_seconds": round(original_duration, 3),
        "reference_sample_rate": REFERENCE_SAMPLE_RATE,
        "reference_channels": 1,
        "reference_subtype": "PCM_16",
        "reference_text": reference_text,
        "source_text_origin": text_source,
        "asr_model": args.asr_model if text_source == "whisper" else None,
        "asr_language": asr_language,
        "prepared_at_utc": utc_now(),
        "calibration": {"status": "not_calibrated"},
    }
    write_json(metadata_path, metadata)

    warning = ""
    if original_duration < 3.0:
        warning = " [WARNING: short reference; 5-15 seconds is usually better]"
    elif original_duration > 30.0:
        warning = " [WARNING: long reference; 5-15 seconds is usually better]"

    if args.make_default:
        config = load_runtime_config(DEFAULT_CONFIG)
        config["preferred_default_voice"] = voice_id
        save_runtime_config(DEFAULT_CONFIG, config)
        metadata["preferred_default_voice_set"] = True
        write_json(metadata_path, metadata)

    print("Custom voice prepared successfully.")
    print(f"  VoiceID:   {voice_id}")
    print(f"  Language:  {language.id} ({language.display_name})")
    print(f"  Folder:    {voice_dir}")
    print(f"  Duration:  {original_duration:.2f}s{warning}")
    print(f"  Text:      {reference_text}")
    if args.make_default:
        print("  Default:   set as preferred fallback voice")
    print("")
    print("Next step:")
    print(f"  python auto_calibrate_chim_voices.py --language {language.id} --voice {voice_id}")
    return 0


def main() -> int:
    args = build_parser().parse_args()
    try:
        if args.command == "add":
            return add_custom_voice(args)
        raise AssertionError(f"Unhandled command: {args.command}")
    except (FileNotFoundError, FileExistsError, ValueError, KeyError, RuntimeError, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
