import json
import shutil
from pathlib import Path

from voice_library import voice_id_problem


class VoiceNotFoundError(FileNotFoundError):
    pass


class ProtectedVoiceError(PermissionError):
    pass


def normalize_voice_id(value: str) -> str:
    voice_id = str(value or "").strip()
    if voice_id.lower().endswith(".wav"):
        voice_id = voice_id[:-4]
    problem = voice_id_problem(voice_id)
    if problem is not None:
        raise ValueError(problem)
    return voice_id


def delete_custom_voice(voices_root: Path, language_id: str, voice_id: str) -> list[str]:
    normalized = normalize_voice_id(voice_id)
    voice_dir = voices_root / language_id / normalized
    if not voice_dir.is_dir():
        raise VoiceNotFoundError(normalized)

    metadata_path = voice_dir / "voice.json"
    metadata: dict = {}
    if metadata_path.is_file():
        try:
            loaded = json.loads(metadata_path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                metadata = loaded
        except (OSError, json.JSONDecodeError):
            metadata = {}

    if not bool(metadata.get("custom_voice", False)):
        raise ProtectedVoiceError(normalized)

    removed = [
        str(path.relative_to(voice_dir)).replace("\\", "/")
        for path in sorted(voice_dir.rglob("*"))
        if path.is_file()
    ]
    shutil.rmtree(voice_dir)
    return removed
