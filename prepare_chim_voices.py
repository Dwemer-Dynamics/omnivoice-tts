from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

import librosa
import numpy as np
import soundfile as sf
import torch
from transformers import pipeline

from language_profiles import load_profiles, load_runtime_config, resolve_profile
from voice_library import voice_id_problem


BASE_DIR = Path(__file__).resolve().parent
DEFAULT_PROFILES_DIR = BASE_DIR / "languages"
DEFAULT_VOICES_ROOT = BASE_DIR / "voices"
DEFAULT_CONFIG = BASE_DIR / "config.json"
DEFAULT_ASR_MODEL = "openai/whisper-large-v3-turbo"
DEFAULT_CHIM_VOICES_DIR = Path("/var/www/html/HerikaServer/data/voices")


def configured_source_path() -> Path:
    configured = os.environ.get("CHIM_VOICES_DIR", "").strip()
    return Path(configured).expanduser() if configured else DEFAULT_CHIM_VOICES_DIR


def parse_args() -> argparse.Namespace:
    config = load_runtime_config(DEFAULT_CONFIG)
    active_language = str(config.get("active_language", "sk"))

    parser = argparse.ArgumentParser(
        description=(
            "Prepare CHIM Skyrim VoiceID samples for one OmniVoice language library: "
            "copy each source WAV, normalize it, transcribe the original English line "
            "with Whisper, and write reproducible metadata."
        )
    )
    parser.add_argument(
        "--source",
        type=Path,
        default=configured_source_path(),
        help=(
            "CHIM HerikaServer/data/voices directory. Default priority: "
            "CHIM_VOICES_DIR environment variable, then "
            "/var/www/html/HerikaServer/data/voices."
        ),
    )
    parser.add_argument(
        "--language",
        default=active_language,
        help=f"Target language profile id or alias (default: active {active_language!r}).",
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
        "--voice",
        action="append",
        default=[],
        help=(
            "VoiceID/file stem to process, case-insensitive. May be supplied repeatedly, "
            "for example --voice malenord --voice femalenord."
        ),
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Process every WAV in the CHIM source directory.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Rebuild profiles and remove stale derived calibration data.",
    )
    parser.add_argument(
        "--asr-model",
        default=DEFAULT_ASR_MODEL,
        help=f"Whisper model used for English Skyrim source transcription (default: {DEFAULT_ASR_MODEL}).",
    )
    return parser.parse_args()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def discover_wavs(source_dir: Path) -> list[Path]:
    return sorted(
        (
            p
            for p in source_dir.iterdir()
            if p.is_file()
            and p.suffix.casefold() == ".wav"
            and voice_id_problem(p.stem) is None
        ),
        key=lambda p: p.name.casefold(),
    )


def discover_invalid_wavs(source_dir: Path) -> list[tuple[Path, str]]:
    invalid: list[tuple[Path, str]] = []
    for path in source_dir.iterdir():
        if not path.is_file() or path.suffix.casefold() != ".wav":
            continue
        problem = voice_id_problem(path.stem)
        if problem is not None:
            invalid.append((path, problem))
    return sorted(invalid, key=lambda item: item[0].name.casefold())


def select_wavs(all_wavs: list[Path], requested: list[str], process_all: bool) -> list[Path]:
    if process_all:
        return all_wavs

    if not requested:
        raise SystemExit(
            "Safety stop: specify one or more --voice values for a pilot test, "
            "or explicitly use --all."
        )

    by_stem = {p.stem.casefold(): p for p in all_wavs}
    selected: list[Path] = []
    missing: list[str] = []

    for voice_id in requested:
        match = by_stem.get(voice_id.casefold())
        if match is None:
            missing.append(voice_id)
        elif match not in selected:
            selected.append(match)

    if missing:
        examples = ", ".join(p.stem for p in all_wavs[:20])
        raise SystemExit(
            f"VoiceID not found: {', '.join(missing)}\n"
            f"First available examples: {examples}"
        )

    return selected


def load_audio(path: Path, target_sr: int) -> tuple[np.ndarray, int, float]:
    audio, sample_rate = sf.read(path, always_2d=False, dtype="float32")

    if audio.ndim == 2:
        audio = audio.mean(axis=1)
    if audio.size == 0:
        raise ValueError("Audio file is empty.")

    duration = float(audio.shape[0] / sample_rate)
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

    return np.asarray(audio, dtype=np.float32), sample_rate, duration


def build_asr(model_name: str):
    if not torch.cuda.is_available():
        raise RuntimeError("CUDA is not available; the OmniVoice factory requires NVIDIA CUDA.")

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


def transcribe_english(asr, audio_16k: np.ndarray) -> str:
    result = asr(
        {"raw": audio_16k, "sampling_rate": 16000},
        generate_kwargs={"language": "english", "task": "transcribe"},
        return_timestamps=False,
    )
    text = str(result.get("text", "") if isinstance(result, dict) else result).strip()
    text = " ".join(text.split())
    if not text:
        raise RuntimeError("Whisper returned an empty transcript.")
    if text[-1] not in ".!?":
        text += "."
    return text


def load_metadata(path: Path) -> dict:
    if not path.is_file():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def existing_profile_is_current(profile_dir: Path, source_hash: str, language_id: str) -> bool:
    metadata = load_metadata(profile_dir / "voice.json")
    required = (
        profile_dir / "source.wav",
        profile_dir / "reference_en.wav",
        profile_dir / "reference_en.txt",
        profile_dir / "reference.wav",
        profile_dir / "reference.txt",
    )
    return (
        all(path.is_file() for path in required)
        and metadata.get("source_sha256") == source_hash
        and metadata.get("language_profile_id") == language_id
    )


def reset_derived_calibration(profile_dir: Path) -> None:
    for directory_name in ("calibration",):
        directory = profile_dir / directory_name
        if directory.exists():
            shutil.rmtree(directory)

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


def prepare_voice(
    *,
    asr,
    asr_model: str,
    source_wav: Path,
    output_root: Path,
    language_id: str,
    language_name: str,
    force: bool,
) -> str:
    voice_id = source_wav.stem
    profile_dir = output_root / voice_id
    profile_dir.mkdir(parents=True, exist_ok=True)

    source_hash = sha256_file(source_wav)
    if not force and existing_profile_is_current(profile_dir, source_hash, language_id):
        return f"SKIP  {voice_id}: unchanged and already prepared for {language_id}"

    print(f"\nPreparing: {voice_id}")
    print(f"Source:    {source_wav}")
    print(f"Library:   {language_id} ({language_name})")

    reset_derived_calibration(profile_dir)

    source_copy = profile_dir / "source.wav"
    reference_en_wav = profile_dir / "reference_en.wav"
    reference_en_txt = profile_dir / "reference_en.txt"
    active_wav = profile_dir / "reference.wav"
    active_txt = profile_dir / "reference.txt"
    metadata_path = profile_dir / "voice.json"

    shutil.copy2(source_wav, source_copy)

    audio_24k, _, original_duration = load_audio(source_wav, target_sr=24000)
    for destination in (reference_en_wav, active_wav):
        sf.write(destination, audio_24k, 24000, format="WAV", subtype="PCM_16")

    audio_16k, _, _ = load_audio(source_wav, target_sr=16000)
    transcript = transcribe_english(asr, audio_16k)
    for destination in (reference_en_txt, active_txt):
        destination.write_text(transcript + "\n", encoding="utf-8")

    metadata = {
        "voice_id": voice_id,
        "language_profile_id": language_id,
        "target_language": language_name,
        "active_reference_language": "English source (not calibrated yet)",
        "source_filename": source_wav.name,
        "source_path": str(source_wav),
        "source_sha256": source_hash,
        "source_size_bytes": source_wav.stat().st_size,
        "source_duration_seconds": round(original_duration, 3),
        "reference_sample_rate": 24000,
        "reference_channels": 1,
        "reference_subtype": "PCM_16",
        "reference_text": transcript,
        "asr_model": asr_model,
        "asr_language": "english",
        "prepared_at_utc": datetime.now(timezone.utc).isoformat(),
        "calibration": {"status": "not_calibrated"},
    }
    metadata_path.write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    warning = ""
    if original_duration < 2.0:
        warning = " [WARNING: very short reference]"
    elif original_duration > 15.0:
        warning = " [WARNING: long reference]"

    return (
        f"DONE  {voice_id}: {original_duration:.2f}s{warning}\n"
        f"      Transcript: {transcript}"
    )


def main() -> int:
    args = parse_args()
    if args.source is None:
        print(
            "ERROR: CHIM voice source is not configured. Run `python chim_cli.py setup`, "
            "or use --source PATH / CHIM_VOICES_DIR.",
            file=sys.stderr,
        )
        return 2

    source_dir = args.source.expanduser()
    profiles_dir = args.profiles_dir.expanduser()
    voices_root = args.voices_root.expanduser()

    try:
        profiles = load_profiles(profiles_dir)
        language = resolve_profile(args.language, profiles_dir, profiles)
    except (FileNotFoundError, ValueError, KeyError, RuntimeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    output_root = voices_root / language.id
    if not source_dir.is_dir():
        print(f"ERROR: CHIM voice directory not found:\n{source_dir}", file=sys.stderr)
        return 2

    all_wavs = discover_wavs(source_dir)
    invalid_wavs = discover_invalid_wavs(source_dir)
    if not all_wavs:
        print(f"ERROR: No valid VoiceID WAV files found in:\n{source_dir}", file=sys.stderr)
        return 2

    selected = select_wavs(all_wavs, args.voice, args.all)
    output_root.mkdir(parents=True, exist_ok=True)

    print(f"CHIM source:     {source_dir}")
    print(f"Target language: {language.id} ({language.display_name})")
    print(f"Output library:  {output_root}")
    print(f"Valid VoiceID WAVs: {len(all_wavs)}")
    print(f"Invalid WAVs ignored: {len(invalid_wavs)}")
    for invalid_path, reason in invalid_wavs:
        print(f"  IGNORE {invalid_path.name}: {reason}")
    print(f"Selected:           {len(selected)}")

    asr = build_asr(args.asr_model)
    completed = 0
    failed = 0

    for source_wav in selected:
        try:
            print(
                prepare_voice(
                    asr=asr,
                    asr_model=args.asr_model,
                    source_wav=source_wav,
                    output_root=output_root,
                    language_id=language.id,
                    language_name=language.display_name,
                    force=args.force,
                )
            )
            completed += 1
        except Exception as exc:
            failed += 1
            print(f"FAIL  {source_wav.stem}: {type(exc).__name__}: {exc}", file=sys.stderr)

    print("\n============================================================")
    print(f"Prepared/skipped successfully: {completed}")
    print(f"Failed:                       {failed}")
    print("============================================================")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
