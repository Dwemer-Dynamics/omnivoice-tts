from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any


PROFILE_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]*$")


@dataclass(frozen=True)
class LanguageProfile:
    id: str
    display_name: str
    omnivoice_language: str
    omnivoice_language_id: str
    whisper_language: str
    aliases: tuple[str, ...]
    bootstrap_text: str
    master_text: str
    bootstrap_count: int = 3
    master_count: int = 6
    bootstrap_num_step: int = 32
    master_num_step: int = 64
    bootstrap_speed: float = 1.0
    master_speed: float = 0.75

    @classmethod
    def from_dict(cls, data: dict[str, Any], source: Path) -> "LanguageProfile":
        required = (
            "id",
            "display_name",
            "omnivoice_language",
            "whisper_language",
            "bootstrap_text",
            "master_text",
        )
        missing = [key for key in required if not str(data.get(key, "")).strip()]
        if missing:
            raise ValueError(f"{source}: missing required field(s): {', '.join(missing)}")

        profile_id = str(data["id"]).strip().casefold()
        if not PROFILE_ID_RE.fullmatch(profile_id):
            raise ValueError(
                f"{source}: invalid id {profile_id!r}; use lowercase letters, digits, _ or -."
            )

        aliases_raw = data.get("aliases", [])
        if not isinstance(aliases_raw, list):
            raise ValueError(f"{source}: aliases must be a JSON array.")
        aliases = tuple(
            dict.fromkeys(
                str(item).strip().casefold()
                for item in aliases_raw
                if str(item).strip()
            )
        )

        profile = cls(
            id=profile_id,
            display_name=str(data["display_name"]).strip(),
            omnivoice_language=str(data["omnivoice_language"]).strip(),
            omnivoice_language_id=str(
                data.get("omnivoice_language_id", profile_id)
            ).strip(),
            whisper_language=str(data["whisper_language"]).strip(),
            aliases=aliases,
            bootstrap_text=str(data["bootstrap_text"]).strip(),
            master_text=str(data["master_text"]).strip(),
            bootstrap_count=int(data.get("bootstrap_count", 3)),
            master_count=int(data.get("master_count", 6)),
            bootstrap_num_step=int(data.get("bootstrap_num_step", 32)),
            master_num_step=int(data.get("master_num_step", 64)),
            bootstrap_speed=float(data.get("bootstrap_speed", 1.0)),
            master_speed=float(data.get("master_speed", 0.75)),
        )
        profile.validate(source)
        return profile

    def validate(self, source: Path | str = "language profile") -> None:
        if self.bootstrap_count < 1:
            raise ValueError(f"{source}: bootstrap_count must be at least 1.")
        if self.master_count < 1:
            raise ValueError(f"{source}: master_count must be at least 1.")
        if self.bootstrap_num_step < 1 or self.master_num_step < 1:
            raise ValueError(f"{source}: num_step values must be positive.")
        if self.bootstrap_speed <= 0 or self.master_speed <= 0:
            raise ValueError(f"{source}: speed values must be positive.")
        if len(self.bootstrap_text) < 10 or len(self.master_text) < 10:
            raise ValueError(f"{source}: calibration texts are implausibly short.")

    def public_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "display_name": self.display_name,
            "omnivoice_language": self.omnivoice_language,
            "omnivoice_language_id": self.omnivoice_language_id,
            "whisper_language": self.whisper_language,
            "aliases": list(self.aliases),
            "bootstrap_count": self.bootstrap_count,
            "master_count": self.master_count,
            "bootstrap_num_step": self.bootstrap_num_step,
            "master_num_step": self.master_num_step,
            "bootstrap_speed": self.bootstrap_speed,
            "master_speed": self.master_speed,
        }

    def editable_dict(self) -> dict[str, Any]:
        """Full JSON representation suitable for cloning/editing a profile."""
        data = self.public_dict()
        data["bootstrap_text"] = self.bootstrap_text
        data["master_text"] = self.master_text
        return data


def load_profiles(profiles_dir: Path) -> dict[str, LanguageProfile]:
    profiles_dir = profiles_dir.expanduser().resolve()
    if not profiles_dir.is_dir():
        raise FileNotFoundError(f"Language profiles directory not found: {profiles_dir}")

    profiles: dict[str, LanguageProfile] = {}

    for path in sorted(profiles_dir.glob("*.json"), key=lambda item: item.name.casefold()):
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid JSON in {path}: {exc}") from exc
        if not isinstance(raw, dict):
            raise ValueError(f"{path}: profile root must be a JSON object.")

        profile = LanguageProfile.from_dict(raw, path)
        if profile.id in profiles:
            raise ValueError(f"Duplicate language profile id: {profile.id}")
        profiles[profile.id] = profile

    if not profiles:
        raise RuntimeError(f"No language JSON profiles found in {profiles_dir}")

    # Profile ids and explicit aliases are strict and must be unique.  Display
    # names and model language values are soft aliases: custom profiles are
    # allowed to target the same OmniVoice/Whisper language as a built-in
    # profile, so ambiguous soft aliases are simply not registered.
    aliases: dict[str, str] = {}
    for profile in profiles.values():
        for name in (profile.id, *profile.aliases):
            normalized = name.strip().casefold()
            if not normalized:
                continue
            owner = aliases.get(normalized)
            if owner is not None and owner != profile.id:
                raise ValueError(
                    f"Language alias {normalized!r} is shared by {owner!r} and {profile.id!r}."
                )
            aliases[normalized] = profile.id

    soft_candidates: dict[str, set[str]] = {}
    for profile in profiles.values():
        for name in (
            profile.display_name,
            profile.omnivoice_language,
            profile.omnivoice_language_id,
        ):
            normalized = name.strip().casefold()
            if normalized:
                soft_candidates.setdefault(normalized, set()).add(profile.id)

    for normalized, owners in soft_candidates.items():
        if len(owners) != 1 or normalized in aliases:
            continue
        aliases[normalized] = next(iter(owners))

    _PROFILE_ALIAS_CACHE[str(profiles_dir)] = aliases
    return profiles


_PROFILE_ALIAS_CACHE: dict[str, dict[str, str]] = {}


def resolve_profile(
    value: str,
    profiles_dir: Path,
    profiles: dict[str, LanguageProfile] | None = None,
) -> LanguageProfile:
    profiles_dir = profiles_dir.expanduser().resolve()
    profiles = profiles or load_profiles(profiles_dir)
    aliases = _PROFILE_ALIAS_CACHE.get(str(profiles_dir))
    if aliases is None:
        load_profiles(profiles_dir)
        aliases = _PROFILE_ALIAS_CACHE[str(profiles_dir)]

    normalized = value.strip().casefold()
    profile_id = aliases.get(normalized)
    if profile_id is None:
        available = ", ".join(sorted(profiles))
        raise KeyError(f"Unknown language {value!r}. Available profile ids: {available}")
    return profiles[profile_id]


def load_runtime_config(config_path: Path) -> dict[str, Any]:
    config_path = config_path.expanduser().resolve()
    if not config_path.is_file():
        return {
            "active_language": "sk",
            "honor_request_language": False,
            "model_id": "k2-fsa/OmniVoice",
            "device": "cuda:0",
            "preferred_default_voice": "",
            "fallback_male": "malenord",
            "fallback_female": "femalenord",
        }

    try:
        data = json.loads(config_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid runtime config {config_path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError(f"{config_path}: config root must be a JSON object.")
    return data


def save_runtime_config(config_path: Path, data: dict[str, Any]) -> None:
    config_path = config_path.expanduser().resolve()
    config_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = config_path.with_suffix(config_path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(config_path)
