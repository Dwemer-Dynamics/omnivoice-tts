from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

from language_profiles import load_profiles, resolve_profile
from voice_library import REFERENCE_WAV, runtime_voice_directories


BASE_DIR = Path(__file__).resolve().parent
DEFAULT_SERVER_HOST = "127.0.0.1"
LISTEN_SERVER_HOST = "0.0.0.0"
DEFAULT_SERVER_PORT = "8021"
EXPORT_TARGETS = {
    "chatterbox": Path(os.environ.get("OMNIVOICE_CHATTERBOX_VOICES_DIR", "/home/dwemer/chatterbox/voices")),
    "pockettts": Path(os.environ.get("OMNIVOICE_POCKETTTS_SPEAKERS_DIR", "/home/dwemer/pocket-tts/speakers")),
    "xtts": Path(os.environ.get("OMNIVOICE_XTTS_SPEAKERS_DIR", "/home/dwemer/xtts-api-server/speakers")),
}
XTTS_LANGUAGE_IDS = {
    "ar",
    "cs",
    "de",
    "en",
    "es",
    "fr",
    "hi",
    "hu",
    "it",
    "ja",
    "ko",
    "nl",
    "pl",
    "pt",
    "ru",
    "tr",
    "zh-cn",
}


def run_script(script_name: str, args: list[str]) -> int:
    script = BASE_DIR / script_name
    if not script.is_file():
        print(f"ERROR: missing script: {script}", file=sys.stderr)
        return 2
    return subprocess.call([sys.executable, str(script), *args], cwd=str(BASE_DIR))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Manage the DwemerDistro OmniVoice TTS component.")
    sub = parser.add_subparsers(dest="command", required=True)

    doctor = sub.add_parser("doctor", help="Run diagnostics and write diagnostics/latest.json.")
    doctor.add_argument("--json", type=Path, default=None, help="Write diagnostics JSON to this path.")
    doctor.add_argument("--quick", action="store_true", help="Compatibility flag for quick diagnostics.")

    languages = sub.add_parser("languages", help="List configured language profiles.")
    languages.add_argument("extra", nargs=argparse.REMAINDER, help=argparse.SUPPRESS)

    set_language = sub.add_parser("set-language", help="Set the active language.")
    set_language.add_argument("language", help="Language profile id or alias.")
    set_language.add_argument("--live-if-running", action="store_true", help="Switch the running server if available.")

    voices = sub.add_parser("voices", help="Audit prepared voices.")
    voices.add_argument("--language", default="all")
    voices.add_argument("--write-report", action="store_true")
    voices.add_argument("--strict", action="store_true")

    verify = sub.add_parser("verify", help="Run end-to-end component smoke verification.")
    verify.add_argument("--base-url", default=f"http://{DEFAULT_SERVER_HOST}:{DEFAULT_SERVER_PORT}")
    verify.add_argument("--language", default="")
    verify.add_argument("--port", default=DEFAULT_SERVER_PORT)
    verify.add_argument("--json", type=Path, default=None)
    verify.add_argument("--write-library-report", action="store_true")
    verify.add_argument("--skip-synthesis", action="store_true")
    verify.add_argument("--with-sites", action="store_true", help="Also verify DwemerDistro service listeners, database rows, and PHP connector paths.")
    verify.add_argument("--voice", action="append", default=[])

    lifecycle = sub.add_parser("verify-lifecycle", help="Verify installer/uninstall behavior in temporary directories.")
    lifecycle.add_argument("--python", default=sys.executable)

    import_chim = sub.add_parser("import-chim", help="Import CHIM VoiceID WAVs into a language library.")
    import_chim.add_argument("--source", type=Path, default=None)
    import_chim.add_argument("--language", required=True)
    import_chim.add_argument("--voice", action="append", default=[])
    import_chim.add_argument("--all", action="store_true")
    import_chim.add_argument("--force", action="store_true")
    import_chim.add_argument("--asr-model", default=None)

    add_custom = sub.add_parser("add-custom-voice", help="Add a user-provided custom voice sample.")
    add_custom.add_argument("--language", default=None)
    add_custom.add_argument("--profiles-dir", type=Path, default=None)
    add_custom.add_argument("--voices-root", type=Path, default=None)
    add_custom.add_argument("--voice", required=True, help="Custom VoiceID/folder name.")
    add_custom.add_argument("--wav", type=Path, required=True, help="Reference audio file.")
    add_custom.add_argument("--display-name", default="")
    add_custom.add_argument("--text", default="")
    add_custom.add_argument("--text-file", type=Path, default=None)
    add_custom.add_argument("--source-language", default=None)
    add_custom.add_argument("--asr-model", default=None)
    add_custom.add_argument("--force", action="store_true")
    add_custom.add_argument("--make-default", action="store_true")

    calibrate = sub.add_parser("calibrate", help="Calibrate one or more prepared voices.")
    calibrate.add_argument("--language", required=True)
    calibrate.add_argument("--voice", action="append", default=[])
    calibrate.add_argument("--limit", type=int, default=None)
    calibrate.add_argument("--all", action="store_true")
    calibrate.add_argument("--force", action="store_true")

    build_library = sub.add_parser("build-library", help="Calibrate the selected language library.")
    build_library.add_argument("--language", required=True)
    build_library.add_argument("--voice", action="append", default=[])
    build_library.add_argument("--limit", type=int, default=None)
    build_library.add_argument("--all", action="store_true")
    build_library.add_argument("--force", action="store_true")

    export = sub.add_parser("export", help="Export prepared voice references.")
    export.add_argument("--language", required=True, help="Language profile id or alias to export.")
    export.add_argument(
        "--target",
        choices=["zip", "chatterbox", "pockettts", "xtts"],
        default="zip",
        help="Export destination. Engine exports copy reference WAVs into that engine's speaker folder.",
    )
    export.add_argument("--output", type=Path, default=None, help="Destination zip path.")
    export.add_argument("--voice", action="append", default=[], help="Export one VoiceID. May be repeated.")
    export.add_argument("--all", action="store_true", help="Export every runtime-ready voice in the selected language.")
    export.add_argument("--force", action="store_true", help="Overwrite files previously exported by OmniVoice.")
    export.add_argument("--symlink", action="store_true", help="Use symlinks instead of copying when exporting to engines.")

    uninstall = sub.add_parser("uninstall", help="Remove runtime files while preserving voices by default.")
    uninstall.add_argument("--yes", action="store_true", help="Actually remove files.")
    uninstall.add_argument("--remove-voices", action="store_true", help="Also remove voices, reports, and diagnostics.")

    server = sub.add_parser("server", help="Run the FastAPI server.")
    server.add_argument("--host", default=DEFAULT_SERVER_HOST)
    server.add_argument("--port", default=DEFAULT_SERVER_PORT)
    server.add_argument(
        "--listen",
        action="store_true",
        help="Allow connections from outside this computer by binding to 0.0.0.0.",
    )

    return parser


def command_doctor(args: argparse.Namespace) -> int:
    diagnostics = args.json or (BASE_DIR / "diagnostics" / "latest.json")
    forwarded = ["--json", str(diagnostics)]
    if args.quick:
        forwarded.append("--quick")
    return run_script("doctor_cli.py", forwarded)


def command_import_chim(args: argparse.Namespace) -> int:
    forwarded = ["--language", args.language]
    if args.source is not None:
        forwarded.extend(["--source", str(args.source)])
    for voice in args.voice:
        forwarded.extend(["--voice", voice])
    if args.all:
        forwarded.append("--all")
    if args.force:
        forwarded.append("--force")
    if args.asr_model:
        forwarded.extend(["--asr-model", args.asr_model])
    return run_script("prepare_chim_voices.py", forwarded)


def command_calibrate(args: argparse.Namespace) -> int:
    forwarded = ["--language", args.language]
    for voice in args.voice:
        forwarded.extend(["--voice", voice])
    if args.limit is not None:
        forwarded.extend(["--limit", str(args.limit)])
    if args.all:
        forwarded.append("--all")
    if args.force:
        forwarded.append("--force")
    return run_script("auto_calibrate_chim_voices.py", forwarded)


def command_add_custom(args: argparse.Namespace) -> int:
    forwarded = ["add", "--voice", args.voice, "--wav", str(args.wav)]
    if args.language:
        forwarded.extend(["--language", args.language])
    if args.profiles_dir is not None:
        forwarded.extend(["--profiles-dir", str(args.profiles_dir)])
    if args.voices_root is not None:
        forwarded.extend(["--voices-root", str(args.voices_root)])
    if args.display_name:
        forwarded.extend(["--display-name", args.display_name])
    if args.text:
        forwarded.extend(["--text", args.text])
    if args.text_file is not None:
        forwarded.extend(["--text-file", str(args.text_file)])
    if args.source_language:
        forwarded.extend(["--source-language", args.source_language])
    if args.asr_model:
        forwarded.extend(["--asr-model", args.asr_model])
    if args.force:
        forwarded.append("--force")
    if args.make_default:
        forwarded.append("--make-default")
    return run_script("custom_voice_cli.py", forwarded)


def resolve_server_host(args: argparse.Namespace) -> str:
    return LISTEN_SERVER_HOST if args.listen else args.host


def command_server(args: argparse.Namespace) -> int:
    return subprocess.call(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "server:app",
            "--host",
            resolve_server_host(args),
            "--port",
            str(args.port),
            "--workers",
            "1",
        ],
        cwd=str(BASE_DIR),
        env={**os.environ, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"},
    )


def selected_voice_dirs(profile_id: str, requested: list[str], include_all: bool) -> list[Path]:
    language_dir = BASE_DIR / "voices" / profile_id
    voices = runtime_voice_directories(language_dir, profile_id)
    if requested:
        wanted = {value.strip().casefold() for value in requested if value.strip()}
        selected = [path for path in voices if path.name.casefold() in wanted]
        missing = sorted(wanted - {path.name.casefold() for path in selected})
        if missing:
            print(f"ERROR: requested voice(s) not runtime-ready: {', '.join(missing)}", file=sys.stderr)
            return []
        return selected
    if include_all:
        return voices
    print("ERROR: use --voice VoiceID for a pilot export, or explicitly use --all.", file=sys.stderr)
    return []


def write_zip_export(profile_id: str, source_dir: Path, output: Path) -> int:
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(source_dir.rglob("*")):
            if path.is_file():
                archive.write(path, path.relative_to(BASE_DIR))
    print(f"Exported {profile_id} voice library to {output}")
    return 0


def export_warnings(target: str, profile_id: str) -> list[str]:
    if target == "xtts" and profile_id not in XTTS_LANGUAGE_IDS:
        return [
            f"XTTS does not natively support language profile {profile_id!r}; exported WAVs are speaker references only.",
        ]
    if target == "chatterbox" and profile_id != "en":
        return [
            f"Chatterbox exports for {profile_id!r} are speaker-reference exports only; Chatterbox language support is not equivalent to OmniVoice.",
        ]
    if target == "pockettts":
        return [
            "PocketTTS export only copies speaker references; synthesis quality depends on the selected PocketTTS model/language.",
        ]
    return []


def engine_export(args: argparse.Namespace, profile_id: str) -> int:
    selected = selected_voice_dirs(profile_id, args.voice, args.all)
    if not selected:
        return 2

    warnings = export_warnings(args.target, profile_id)
    for warning in warnings:
        print(f"WARNING: {warning}", file=sys.stderr)

    target_dir = EXPORT_TARGETS[args.target]
    target_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = target_dir / f".omnivoice-{profile_id}-export.json"
    existing_manifest = {}
    if manifest_path.is_file():
        try:
            loaded = json.loads(manifest_path.read_text(encoding="utf-8"))
            existing_manifest = loaded if isinstance(loaded, dict) else {}
        except Exception:
            existing_manifest = {}

    exported: list[dict] = []
    for voice_dir in selected:
        source = voice_dir / REFERENCE_WAV
        destination = target_dir / f"{voice_dir.name}.wav"
        previous = existing_manifest.get("files", {}).get(destination.name) if isinstance(existing_manifest.get("files"), dict) else None
        owns_existing = isinstance(previous, dict) and str(previous.get("source")) == str(source)
        if destination.exists() and not args.force and not owns_existing:
            print(f"ERROR: refusing to overwrite existing voice: {destination}", file=sys.stderr)
            print("Use --force only after confirming it is safe to replace.", file=sys.stderr)
            return 1
        if destination.exists() or destination.is_symlink():
            destination.unlink()
        if args.symlink:
            os.symlink(source, destination)
            mode = "symlink"
        else:
            shutil.copy2(source, destination)
            mode = "copy"
        exported.append({"voice_id": voice_dir.name, "source": str(source), "destination": str(destination), "mode": mode})

    manifest = {
        "language_profile_id": profile_id,
        "target": args.target,
        "target_directory": str(target_dir),
        "warnings": warnings,
        "files": {
            Path(item["destination"]).name: item for item in exported
        },
    }
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Exported {len(exported)} voice(s) to {target_dir}")
    print(f"Manifest: {manifest_path}")
    print("To reverse, remove the files listed in the manifest.")
    return 0


def command_export(args: argparse.Namespace) -> int:
    profiles_dir = BASE_DIR / "languages"
    profile = resolve_profile(args.language, profiles_dir, load_profiles(profiles_dir))
    source_dir = BASE_DIR / "voices" / profile.id
    if not source_dir.is_dir():
        print(f"ERROR: no prepared voice library found at {source_dir}", file=sys.stderr)
        return 2

    if args.target != "zip":
        return engine_export(args, profile.id)

    output = args.output or (BASE_DIR / "reports" / f"omnivoice-{profile.id}-voices.zip")
    return write_zip_export(profile.id, source_dir, output)


def command_uninstall(args: argparse.Namespace) -> int:
    targets = [BASE_DIR / "start.sh", BASE_DIR / "venv"]
    if args.remove_voices:
        targets.extend([BASE_DIR / "voices", BASE_DIR / "reports", BASE_DIR / "diagnostics"])
    print("The following paths will be removed:")
    for target in targets:
        print(f"  {target}")
    if not args.yes:
        print("Dry run only. Add --yes to remove these paths.")
        return 0
    for target in targets:
        if target.is_symlink() or target.is_file():
            target.unlink(missing_ok=True)
        elif target.is_dir():
            shutil.rmtree(target)
    for directory in ("voices", "reports", "logs", "diagnostics"):
        (BASE_DIR / directory).mkdir(exist_ok=True)
    print("Uninstall complete.")
    return 0


def main() -> int:
    args = build_parser().parse_args()

    if args.command == "doctor":
        return command_doctor(args)
    if args.command == "languages":
        return run_script("language_cli.py", args.extra if args.extra else ["list"])
    if args.command == "set-language":
        forwarded = ["set", args.language]
        if args.live_if_running:
            forwarded.append("--live-if-running")
        return run_script("language_cli.py", forwarded)
    if args.command == "voices":
        forwarded = ["audit", "--language", args.language]
        if args.write_report:
            forwarded.append("--write-report")
        if args.strict:
            forwarded.append("--strict")
        return run_script("library_cli.py", forwarded)
    if args.command == "verify":
        forwarded = ["--base-url", args.base_url, "--language", args.language, "--port", str(args.port)]
        if args.json is not None:
            forwarded.extend(["--json", str(args.json)])
        if args.write_library_report:
            forwarded.append("--write-library-report")
        if args.skip_synthesis:
            forwarded.append("--skip-synthesis")
        if args.with_sites:
            forwarded.append("--with-sites")
        for voice in args.voice:
            forwarded.extend(["--voice", voice])
        return run_script("verify_cli.py", forwarded)
    if args.command == "verify-lifecycle":
        return run_script("lifecycle_cli.py", ["--python", args.python])
    if args.command == "import-chim":
        return command_import_chim(args)
    if args.command == "add-custom-voice":
        return command_add_custom(args)
    if args.command == "calibrate":
        return command_calibrate(args)
    if args.command == "build-library":
        return command_calibrate(args)
    if args.command == "export":
        return command_export(args)
    if args.command == "uninstall":
        return command_uninstall(args)
    if args.command == "server":
        return command_server(args)

    print(f"ERROR: unknown command: {args.command}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
