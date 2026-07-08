from __future__ import annotations

import json
import re
import shutil
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


REFERENCE_WAV = "reference.wav"
REFERENCE_TXT = "reference.txt"
VOICE_METADATA = "voice.json"
EXPECTED_SAMPLE_RATE = 24000

# A Skyrim VoiceID is a stem, not a plugin/script/audio filename.  We keep the
# rule intentionally conservative: custom IDs may contain spaces, +, _ or -,
# but folders that look like files are never exposed to CHIM as speakers.
NON_VOICE_SUFFIXES = {
    ".esp",
    ".esm",
    ".esl",
    ".wav",
    ".mp3",
    ".flac",
    ".ogg",
    ".txt",
    ".json",
    ".ini",
    ".toml",
    ".yaml",
    ".yml",
    ".exe",
    ".dll",
    ".bat",
    ".cmd",
    ".ps1",
    ".py",
    ".php",
}
SAFE_VOICE_ID_RE = re.compile(r"^[^\\/:*?\"<>|\x00-\x1f]+$")
CALIBRATED_STATUSES = {"master_selected", "auto_master_selected"}


@dataclass
class VoiceAudit:
    name: str
    directory: Path
    valid_id: bool
    runtime_ready: bool
    calibrated: bool
    calibration_status: str
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    sample_rate: int | None = None
    channels: int | None = None
    duration_seconds: float | None = None

    @property
    def status(self) -> str:
        if not self.valid_id:
            return "invalid_id"
        if self.errors:
            return "broken"
        if self.runtime_ready and self.calibrated:
            return "calibrated"
        if self.runtime_ready:
            return "runtime_ready"
        return "incomplete"

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "directory": str(self.directory),
            "status": self.status,
            "valid_id": self.valid_id,
            "runtime_ready": self.runtime_ready,
            "calibrated": self.calibrated,
            "calibration_status": self.calibration_status,
            "sample_rate": self.sample_rate,
            "channels": self.channels,
            "duration_seconds": (
                round(self.duration_seconds, 3)
                if self.duration_seconds is not None
                else None
            ),
            "errors": list(self.errors),
            "warnings": list(self.warnings),
        }


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def voice_id_problem(name: str) -> str | None:
    stripped = name.strip()
    if not stripped:
        return "empty VoiceID"
    if stripped in {".", ".."} or stripped.startswith("."):
        return "hidden/reserved folder name"
    if not SAFE_VOICE_ID_RE.fullmatch(stripped):
        return "contains a path separator, control character or Windows-reserved character"
    if Path(stripped).suffix.casefold() in NON_VOICE_SUFFIXES:
        return f"looks like a non-voice file ({Path(stripped).suffix})"
    return None


def is_valid_voice_id(name: str) -> bool:
    return voice_id_problem(name) is None


def _read_reference_text(path: Path) -> tuple[bool, str | None]:
    try:
        text = path.read_text(encoding="utf-8").strip()
    except OSError as exc:
        return False, f"cannot read {REFERENCE_TXT}: {exc}"
    if not text:
        return False, f"{REFERENCE_TXT} is empty"
    return True, None


def audit_voice_dir(directory: Path, expected_language_id: str | None = None) -> VoiceAudit:
    name = directory.name
    id_problem = voice_id_problem(name)
    errors: list[str] = []
    warnings: list[str] = []

    if id_problem:
        errors.append(f"invalid VoiceID: {id_problem}")

    wav_path = directory / REFERENCE_WAV
    txt_path = directory / REFERENCE_TXT

    if not wav_path.is_file():
        errors.append(f"missing {REFERENCE_WAV}")
    if not txt_path.is_file():
        errors.append(f"missing {REFERENCE_TXT}")

    text_ok = False
    if txt_path.is_file():
        text_ok, text_error = _read_reference_text(txt_path)
        if text_error:
            errors.append(text_error)

    sample_rate: int | None = None
    channels: int | None = None
    duration: float | None = None
    wav_ok = False
    if wav_path.is_file():
        try:
            import soundfile as sf

            info = sf.info(str(wav_path))
            sample_rate = int(info.samplerate)
            channels = int(info.channels)
            duration = float(info.duration)
            wav_ok = info.frames > 0 and sample_rate > 0 and channels > 0
            if not wav_ok:
                errors.append(f"{REFERENCE_WAV} contains no readable audio frames")
            if sample_rate != EXPECTED_SAMPLE_RATE:
                warnings.append(
                    f"sample rate is {sample_rate} Hz; expected {EXPECTED_SAMPLE_RATE} Hz"
                )
            if channels != 1:
                warnings.append(f"audio has {channels} channels; mono is recommended")
            if duration <= 0:
                errors.append(f"{REFERENCE_WAV} duration is zero")
            elif duration < 1.0:
                warnings.append(f"very short reference ({duration:.2f}s)")
            elif duration > 30.0:
                warnings.append(f"very long reference ({duration:.2f}s)")
        except (ImportError, RuntimeError, OSError, ValueError) as exc:
            errors.append(f"cannot read {REFERENCE_WAV}: {exc}")

    metadata_path = directory / VOICE_METADATA
    metadata = load_json(metadata_path)
    if not metadata_path.is_file():
        warnings.append(f"missing {VOICE_METADATA}")
    elif not metadata:
        warnings.append(f"invalid or unreadable {VOICE_METADATA}")

    calibration = metadata.get("calibration") if metadata else None
    if isinstance(calibration, dict):
        calibration_status = str(calibration.get("status", "unknown"))
    else:
        calibration_status = "unknown"

    calibrated = calibration_status in CALIBRATED_STATUSES
    if expected_language_id and metadata:
        metadata_language = str(metadata.get("language_profile_id", "")).casefold()
        if metadata_language and metadata_language != expected_language_id.casefold():
            warnings.append(
                f"voice.json language_profile_id={metadata_language!r}, "
                f"library={expected_language_id!r}"
            )
        calibration_language = ""
        if isinstance(calibration, dict):
            calibration_language = str(
                calibration.get("language_profile_id", "")
            ).casefold()
        if calibration_language and calibration_language != expected_language_id.casefold():
            warnings.append(
                f"calibration language_profile_id={calibration_language!r}, "
                f"library={expected_language_id!r}"
            )

    runtime_ready = id_problem is None and wav_ok and text_ok
    return VoiceAudit(
        name=name,
        directory=directory,
        valid_id=id_problem is None,
        runtime_ready=runtime_ready,
        calibrated=calibrated,
        calibration_status=calibration_status,
        errors=errors,
        warnings=warnings,
        sample_rate=sample_rate,
        channels=channels,
        duration_seconds=duration,
    )


def iter_voice_directories(language_dir: Path) -> Iterable[Path]:
    if not language_dir.is_dir():
        return ()
    return tuple(
        sorted(
            (path for path in language_dir.iterdir() if path.is_dir()),
            key=lambda path: path.name.casefold(),
        )
    )


def audit_language_library(language_dir: Path, language_id: str) -> list[VoiceAudit]:
    return [
        audit_voice_dir(directory, expected_language_id=language_id)
        for directory in iter_voice_directories(language_dir)
    ]


def runtime_voice_directories(language_dir: Path, language_id: str) -> list[Path]:
    return [
        item.directory
        for item in audit_language_library(language_dir, language_id)
        if item.runtime_ready
    ]


def count_runtime_ready(language_dir: Path, language_id: str) -> int:
    # Lightweight count for launcher/CLI display.  Full WAV integrity checks are
    # intentionally reserved for `library_cli.py audit`.
    count = 0
    for directory in iter_voice_directories(language_dir):
        if not is_valid_voice_id(directory.name):
            continue
        wav_path = directory / REFERENCE_WAV
        txt_path = directory / REFERENCE_TXT
        if not wav_path.is_file() or not txt_path.is_file():
            continue
        try:
            if not txt_path.read_text(encoding="utf-8").strip():
                continue
        except OSError:
            continue
        count += 1
    return count


def quarantine_invalid_directories(
    *,
    language_dir: Path,
    language_id: str,
    quarantine_root: Path,
) -> list[tuple[Path, Path]]:
    moved: list[tuple[Path, Path]] = []
    target_root = quarantine_root / language_id
    target_root.mkdir(parents=True, exist_ok=True)

    for audit in audit_language_library(language_dir, language_id):
        if audit.valid_id:
            continue
        source = audit.directory
        destination = target_root / source.name
        if destination.exists():
            stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            destination = target_root / f"{source.name}_{stamp}"
        shutil.move(str(source), str(destination))
        moved.append((source, destination))

    return moved
