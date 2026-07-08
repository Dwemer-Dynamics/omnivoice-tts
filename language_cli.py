from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

from language_profiles import (
    PROFILE_ID_RE,
    LanguageProfile,
    load_profiles,
    load_runtime_config,
    resolve_profile,
    save_runtime_config,
)
from language_catalog import RECOMMENDED_LANGUAGE_PRESETS, find_preset, preset_label, searchable_catalog_text
from voice_library import count_runtime_ready


BASE_DIR = Path(__file__).resolve().parent
PROFILES_DIR = BASE_DIR / "languages"
VOICES_ROOT = BASE_DIR / "voices"
CONFIG_PATH = BASE_DIR / "config.json"
DEFAULT_SERVER = "http://127.0.0.1:8021"


def voice_count(profile_id: str) -> int:
    return count_runtime_ready(VOICES_ROOT / profile_id, profile_id)


def post_json(url: str, payload: dict) -> dict:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=10) as response:
        raw = response.read().decode("utf-8")
    value = json.loads(raw)
    return value if isinstance(value, dict) else {"response": value}


def open_in_editor(path: Path) -> None:
    try:
        if os.name == "nt":
            os.startfile(path)  # type: ignore[attr-defined]
        else:
            subprocess.Popen(["xdg-open", str(path)])
    except (OSError, AttributeError) as exc:
        print(f"WARNING: profile was created, but the editor could not be opened: {exc}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Manage Multilingual TTS Tool language profiles and active voice libraries."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("list", help="List language profiles and runtime-ready voice counts.")
    subparsers.add_parser("show", help="Show the configured active language.")
    subparsers.add_parser("validate", help="Validate every enabled language JSON profile.")
    presets_parser = subparsers.add_parser("presets", help="List the 96 recommended OmniVoice+Whisper language presets.")
    presets_parser.add_argument("--json", action="store_true", help="Print preset metadata as JSON.")

    profile_parser = subparsers.add_parser(
        "profile", help="Show a complete language profile including calibration sentences."
    )
    profile_parser.add_argument("language", help="Profile id or alias.")

    set_parser = subparsers.add_parser("set", help="Set the active language.")
    set_parser.add_argument("language", help="Profile id or alias, for example sk, cs, es or en.")
    set_parser.add_argument(
        "--live",
        action="store_true",
        help="Also switch a currently running server without restarting it. Fails if the server is not reachable.",
    )
    set_parser.add_argument(
        "--live-if-running",
        action="store_true",
        help="Switch the running server if it is reachable, but do not fail when it is stopped.",
    )
    set_parser.add_argument(
        "--server",
        default=DEFAULT_SERVER,
        help=f"Server base URL used with --live (default: {DEFAULT_SERVER}).",
    )

    clone_parser = subparsers.add_parser(
        "clone",
        help=(
            "Create an editable custom profile by cloning a working profile. "
            "Aliases are cleared to avoid conflicts."
        ),
    )
    clone_parser.add_argument("source", help="Existing profile id or alias to clone.")
    clone_parser.add_argument("new_id", help="New lowercase profile id, e.g. cs_custom.")
    clone_parser.add_argument(
        "--display-name",
        help="Display name for the new profile (default: '<source> Custom').",
    )
    clone_parser.add_argument(
        "--open",
        action="store_true",
        help="Open the newly created JSON file in the default editor.",
    )
    clone_parser.add_argument(
        "--force",
        action="store_true",
        help="Replace an existing JSON file with the same id.",
    )

    enable_preset_parser = subparsers.add_parser(
        "enable-preset",
        help="Create an enabled language JSON profile from the recommended preset catalog.",
    )
    enable_preset_parser.add_argument("preset", help="Preset id, display name, OmniVoice id, or alias.")
    enable_preset_parser.add_argument(
        "--force",
        action="store_true",
        help="Replace an existing JSON file with the same profile id.",
    )
    enable_preset_parser.add_argument(
        "--allow-placeholder",
        action="store_true",
        help="Allow presets whose calibration sentences must be edited before building voices.",
    )
    enable_preset_parser.add_argument(
        "--open",
        action="store_true",
        help="Open the created JSON file in the default editor.",
    )
    return parser


def clone_profile(
    *,
    source: LanguageProfile,
    new_id: str,
    display_name: str | None,
    force: bool,
) -> Path:
    normalized_id = new_id.strip().casefold()
    if not PROFILE_ID_RE.fullmatch(normalized_id):
        raise ValueError(
            f"Invalid profile id {normalized_id!r}; use lowercase letters, digits, _ or -."
        )
    target_path = PROFILES_DIR / f"{normalized_id}.json"
    if target_path.exists() and not force:
        raise FileExistsError(f"Profile already exists: {target_path}")

    data = source.editable_dict()
    data["id"] = normalized_id
    data["display_name"] = display_name.strip() if display_name else f"{source.display_name} Custom"
    data["aliases"] = []

    # Validate before writing.  The cloned profile keeps the proven 3+6/64
    # factory settings but the tester may then edit language values and texts.
    LanguageProfile.from_dict(data, target_path)
    temporary = target_path.with_suffix(".json.tmp")
    temporary.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(target_path)
    return target_path


def enable_preset_profile(*, value: str, force: bool, allow_placeholder: bool) -> tuple[Path, dict[str, object]]:
    preset = find_preset(value)
    if preset is None:
        raise KeyError(f"Unknown preset {value!r}. Use `languages presets` to list available presets.")
    if not bool(preset.get("has_native_samples")) and not allow_placeholder:
        raise ValueError(
            f"Preset {preset['id']!r} uses placeholder calibration text. "
            "Use --allow-placeholder, then edit both calibration sentences before building voices."
        )

    profile_id = str(preset["id"]).strip().casefold()
    target_path = PROFILES_DIR / f"{profile_id}.json"
    if target_path.exists() and not force:
        raise FileExistsError(f"Profile already exists: {target_path}")

    data = {
        key: preset[key]
        for key in (
            "id",
            "display_name",
            "omnivoice_language",
            "omnivoice_language_id",
            "whisper_language",
            "aliases",
            "bootstrap_text",
            "master_text",
        )
    }
    data.update(
        {
            "bootstrap_count": 3,
            "master_count": 6,
            "bootstrap_num_step": 32,
            "master_num_step": 64,
            "bootstrap_speed": 1.0,
            "master_speed": 0.75,
        }
    )
    LanguageProfile.from_dict(data, target_path)
    temporary = target_path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(target_path)
    return target_path, preset


def main() -> int:
    args = build_parser().parse_args()
    try:
        profiles = load_profiles(PROFILES_DIR)
        config = load_runtime_config(CONFIG_PATH)
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    if args.command == "presets":
        if args.json:
            print(json.dumps(RECOMMENDED_LANGUAGE_PRESETS, ensure_ascii=False, indent=2))
        else:
            print(searchable_catalog_text(), end="")
        return 0

    if args.command == "list":
        active = str(config.get("active_language", "sk")).casefold()
        for profile in sorted(profiles.values(), key=lambda item: item.id):
            marker = "*" if profile.id == active else " "
            print(
                f"{marker} {profile.id:12} {profile.display_name:18} "
                f"voices={voice_count(profile.id):3d} "
                f"factory={profile.bootstrap_count}+{profile.master_count}"
            )
        return 0

    if args.command == "validate":
        for profile in sorted(profiles.values(), key=lambda item: item.id):
            print(
                f"OK  {profile.id:12} {profile.display_name:18} "
                f"OmniVoice={profile.omnivoice_language!r} "
                f"Whisper={profile.whisper_language!r} "
                f"factory={profile.bootstrap_count}+{profile.master_count}"
            )
        print(f"Validated profiles: {len(profiles)}")
        return 0

    if args.command == "show":
        try:
            profile = resolve_profile(
                str(config.get("active_language", "sk")), PROFILES_DIR, profiles
            )
        except KeyError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 2
        print(f"{profile.id} ({profile.display_name}), voices={voice_count(profile.id)}")
        return 0

    if args.command == "profile":
        try:
            profile = resolve_profile(args.language, PROFILES_DIR, profiles)
        except KeyError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 2
        print(json.dumps(profile.editable_dict(), ensure_ascii=False, indent=2))
        return 0

    if args.command == "clone":
        try:
            source = resolve_profile(args.source, PROFILES_DIR, profiles)
            target_path = clone_profile(
                source=source,
                new_id=args.new_id,
                display_name=args.display_name,
                force=args.force,
            )
            # Reload all profiles so duplicate IDs/aliases and malformed output
            # are caught immediately rather than at server startup.
            refreshed = load_profiles(PROFILES_DIR)
            created = refreshed[target_path.stem.casefold()]
        except (KeyError, ValueError, FileExistsError, OSError) as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 2

        print(f"Created profile: {created.id} ({created.display_name})")
        print(f"File: {target_path}")
        print("Edit OmniVoice/Whisper values and both calibration sentences as needed.")
        print("After sentence or generation-setting changes, recalibrate affected voices with --force.")
        if args.open:
            open_in_editor(target_path)
        return 0

    if args.command == "enable-preset":
        try:
            target_path, preset = enable_preset_profile(
                value=args.preset,
                force=args.force,
                allow_placeholder=args.allow_placeholder,
            )
            refreshed = load_profiles(PROFILES_DIR)
            created = refreshed[target_path.stem.casefold()]
        except (KeyError, ValueError, FileExistsError, OSError) as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 2

        print(f"Enabled preset: {preset_label(preset)}")
        print(f"Profile: {created.id} ({created.display_name})")
        print(f"File: {target_path}")
        if not bool(preset.get("has_native_samples")):
            print("WARNING: edit both calibration sentences before importing or building voices.")
        if args.open:
            open_in_editor(target_path)
        return 0

    try:
        profile = resolve_profile(args.language, PROFILES_DIR, profiles)
    except KeyError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    config["active_language"] = profile.id
    save_runtime_config(CONFIG_PATH, config)
    print(f"Configured active language: {profile.id} ({profile.display_name})")
    print(f"Prepared voices: {voice_count(profile.id)}")

    if args.live or args.live_if_running:
        try:
            result = post_json(
                args.server.rstrip("/") + "/active_language",
                {"language": profile.id},
            )
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            if args.live_if_running:
                print(f"Live server was not reachable; config is saved and will apply on next server start: {exc}")
                return 0
            print(f"ERROR: config was saved, but live server switch failed: {exc}", file=sys.stderr)
            return 1
        print(
            "Running server switched: "
            f"{result.get('active', {}).get('id', profile.id)}, "
            f"voices={result.get('voice_count', '?')}"
        )
    else:
        print("Restart the server to apply it, or use --live/--live-if-running while the server is running.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
