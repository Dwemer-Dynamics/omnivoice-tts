from __future__ import annotations

import argparse
import os
import json
import wave
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from language_catalog import RECOMMENDED_LANGUAGE_PRESETS


BASE_DIR = Path(__file__).resolve().parent
COPY_FOR_UNINSTALL = [
    "omnivoice_cli.py",
    "language_profiles.py",
    "voice_library.py",
]
COPY_FOR_INSTALL = [
    "ddistro_install.sh",
    "conf.sh",
    "start-gpu.sh",
    "omnivoice_cli.py",
    "language_profiles.py",
    "voice_library.py",
    "doctor_cli.py",
    "requirements_torch_cuda128.txt",
    "requirements_runtime.txt",
    "config.json",
]
COPY_FOR_EXPORT = [
    "omnivoice_cli.py",
    "language_profiles.py",
    "voice_library.py",
]
COPY_FOR_LANGUAGE_CATALOG = [
    "omnivoice_cli.py",
    "language_cli.py",
    "language_profiles.py",
    "language_catalog.py",
    "voice_library.py",
    "auto_calibrate_chim_voices.py",
]


def copy_component_files(target: Path, names: list[str]) -> None:
    target.mkdir(parents=True, exist_ok=True)
    for name in names:
        source = BASE_DIR / name
        if source.is_file():
            shutil.copy2(source, target / name)
    languages_source = BASE_DIR / "languages"
    if languages_source.is_dir():
        shutil.copytree(languages_source, target / "languages", dirs_exist_ok=True)


def run(command: list[str], cwd: Path, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=str(cwd),
        env={**os.environ, **(env or {})},
        text=True,
        capture_output=True,
        timeout=120,
        check=False,
    )


def assert_condition(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def verify_uninstall_preserves_voices(python: str) -> None:
    with tempfile.TemporaryDirectory(prefix="omnivoice-uninstall-") as tmp:
        root = Path(tmp)
        copy_component_files(root, COPY_FOR_UNINSTALL)
        (root / "venv").mkdir()
        (root / "start.sh").write_text("#!/bin/sh\n", encoding="utf-8")
        for folder in ("voices/sk/femalenord", "reports/sk", "diagnostics", "logs"):
            (root / folder).mkdir(parents=True, exist_ok=True)
        (root / "voices/sk/femalenord/reference.wav").write_bytes(b"RIFFsentinel")
        (root / "reports/sk/library_audit.json").write_text("{}\n", encoding="utf-8")
        (root / "diagnostics/latest.json").write_text("{}\n", encoding="utf-8")

        result = run([python, "omnivoice_cli.py", "uninstall", "--yes"], root)
        assert_condition(result.returncode == 0, f"uninstall failed: {result.stderr}{result.stdout}")
        assert_condition(not (root / "venv").exists(), "uninstall did not remove venv")
        assert_condition(not (root / "start.sh").exists(), "uninstall did not remove start.sh")
        assert_condition((root / "voices/sk/femalenord/reference.wav").is_file(), "uninstall removed voices without --remove-voices")
        assert_condition((root / "reports/sk/library_audit.json").is_file(), "uninstall removed reports without --remove-voices")
        assert_condition((root / "diagnostics/latest.json").is_file(), "uninstall removed diagnostics without --remove-voices")


def verify_uninstall_remove_voices(python: str) -> None:
    with tempfile.TemporaryDirectory(prefix="omnivoice-uninstall-all-") as tmp:
        root = Path(tmp)
        copy_component_files(root, COPY_FOR_UNINSTALL)
        (root / "venv").mkdir()
        (root / "start.sh").write_text("#!/bin/sh\n", encoding="utf-8")
        for folder in ("voices/sk/femalenord", "reports/sk", "diagnostics", "logs"):
            (root / folder).mkdir(parents=True, exist_ok=True)
        (root / "voices/sk/femalenord/reference.wav").write_bytes(b"RIFFsentinel")

        result = run([python, "omnivoice_cli.py", "uninstall", "--yes", "--remove-voices"], root)
        assert_condition(result.returncode == 0, f"uninstall --remove-voices failed: {result.stderr}{result.stdout}")
        assert_condition(not (root / "venv").exists(), "uninstall --remove-voices did not remove venv")
        assert_condition(not (root / "start.sh").exists(), "uninstall --remove-voices did not remove start.sh")
        assert_condition(not (root / "voices/sk/femalenord/reference.wav").exists(), "uninstall --remove-voices kept old voice file")
        for folder in ("voices", "reports", "logs", "diagnostics"):
            assert_condition((root / folder).is_dir(), f"uninstall did not recreate {folder}")


def verify_installer_idempotent() -> None:
    with tempfile.TemporaryDirectory(prefix="omnivoice-install-") as tmp:
        base = Path(tmp)
        repo = base / "omnivoice-tts"
        copy_component_files(repo, COPY_FOR_INSTALL)
        env = {
            "OMNIVOICE_BASE_DIR": str(base),
            "OMNIVOICE_SKIP_DEPENDENCIES": "1",
            "OMNIVOICE_SKIP_DOCTOR": "1",
        }
        first = run(["bash", "ddistro_install.sh"], repo, env)
        assert_condition(first.returncode == 0, f"first installer run failed: {first.stderr}{first.stdout}")
        second = run(["bash", "ddistro_install.sh"], repo, env)
        assert_condition(second.returncode == 0, f"second installer run failed: {second.stderr}{second.stdout}")
        assert_condition((repo / "venv").is_dir(), "installer did not create venv")
        for folder in ("voices", "reports", "logs", "diagnostics"):
            assert_condition((repo / folder).is_dir(), f"installer did not create {folder}")
        assert_condition("Virtual environment already exists." in second.stdout, "second installer run did not use existing venv")


def write_fixture_wav(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(24000)
        wav.writeframes(b"\x00\x00" * 24000)


def create_runtime_ready_voice(root: Path) -> None:
    voice_dir = root / "voices" / "sk" / "codex_export_voice"
    write_fixture_wav(voice_dir / "reference.wav")
    (voice_dir / "reference.txt").write_text("Export verification reference.\n", encoding="utf-8")
    (voice_dir / "voice.json").write_text(
        json.dumps(
            {
                "language_profile_id": "sk",
                "calibration": {
                    "status": "auto_master_selected",
                    "language_profile_id": "sk",
                },
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def verify_export_safety(python: str) -> None:
    with tempfile.TemporaryDirectory(prefix="omnivoice-export-") as tmp:
        root = Path(tmp) / "component"
        copy_component_files(root, COPY_FOR_EXPORT)
        create_runtime_ready_voice(root)

        targets = {
            "chatterbox": Path(tmp) / "targets" / "chatterbox",
            "pockettts": Path(tmp) / "targets" / "pockettts",
            "xtts": Path(tmp) / "targets" / "xtts",
        }
        env = {
            "OMNIVOICE_CHATTERBOX_VOICES_DIR": str(targets["chatterbox"]),
            "OMNIVOICE_POCKETTTS_SPEAKERS_DIR": str(targets["pockettts"]),
            "OMNIVOICE_XTTS_SPEAKERS_DIR": str(targets["xtts"]),
        }

        for target, target_dir in targets.items():
            result = run(
                [python, "omnivoice_cli.py", "export", "--language", "sk", "--target", target, "--voice", "codex_export_voice"],
                root,
                env,
            )
            assert_condition(result.returncode == 0, f"{target} export failed: {result.stderr}{result.stdout}")
            exported = target_dir / "codex_export_voice.wav"
            manifest = target_dir / ".omnivoice-sk-export.json"
            assert_condition(exported.is_file(), f"{target} export did not create speaker wav")
            assert_condition(manifest.is_file(), f"{target} export did not create manifest")
            manifest_data = json.loads(manifest.read_text(encoding="utf-8"))
            assert_condition(isinstance(manifest_data.get("warnings"), list), f"{target} manifest warnings missing")
            assert_condition(manifest_data["warnings"], f"{target} export should report language/engine compatibility risk")
            assert_condition("WARNING:" in result.stderr, f"{target} export warning was not printed")

            rerun = run(
                [python, "omnivoice_cli.py", "export", "--language", "sk", "--target", target, "--voice", "codex_export_voice"],
                root,
                env,
            )
            assert_condition(rerun.returncode == 0, f"{target} rerun should be allowed for owned manifest file")

            exported.write_text("custom user voice\n", encoding="utf-8")
            manifest.unlink()
            refused = run(
                [python, "omnivoice_cli.py", "export", "--language", "sk", "--target", target, "--voice", "codex_export_voice"],
                root,
                env,
            )
            assert_condition(refused.returncode != 0, f"{target} export overwrote unowned existing voice")
            assert_condition("refusing to overwrite" in refused.stderr, f"{target} refusal message missing")

            forced = run(
                [python, "omnivoice_cli.py", "export", "--language", "sk", "--target", target, "--voice", "codex_export_voice", "--force"],
                root,
                env,
            )
            assert_condition(forced.returncode == 0, f"{target} forced export failed: {forced.stderr}{forced.stdout}")

        zip_path = Path(tmp) / "voices.zip"
        zip_result = run(
            [python, "omnivoice_cli.py", "export", "--language", "sk", "--target", "zip", "--output", str(zip_path)],
            root,
        )
        assert_condition(zip_result.returncode == 0, f"zip export failed: {zip_result.stderr}{zip_result.stdout}")
        assert_condition(zip_path.is_file() and zip_path.stat().st_size > 0, "zip export did not create archive")


def verify_language_catalog(python: str) -> None:
    with tempfile.TemporaryDirectory(prefix="omnivoice-language-catalog-") as tmp:
        root = Path(tmp) / "component"
        copy_component_files(root, COPY_FOR_LANGUAGE_CATALOG)
        presets = run([python, "omnivoice_cli.py", "languages", "presets"], root)
        assert_condition(presets.returncode == 0, f"preset listing failed: {presets.stderr}{presets.stdout}")
        expected_count = len(RECOMMENDED_LANGUAGE_PRESETS)
        assert_condition(
            f"Recommended OmniVoice+Whisper profile presets: {expected_count}" in presets.stdout,
            f"preset count was not reported as {expected_count}",
        )

        (root / "languages" / "de.json").unlink(missing_ok=True)
        enabled = run([python, "omnivoice_cli.py", "languages", "enable-preset", "de"], root)
        assert_condition(enabled.returncode == 0, f"native-sample preset enable failed: {enabled.stderr}{enabled.stdout}")
        assert_condition((root / "languages" / "de.json").is_file(), "de preset did not create de.json")

        refused = run([python, "omnivoice_cli.py", "languages", "enable-preset", "haw"], root)
        assert_condition(refused.returncode != 0, "placeholder preset should require --allow-placeholder")
        assert_condition("placeholder calibration text" in refused.stderr, "placeholder refusal message missing")

        allowed = run([python, "omnivoice_cli.py", "languages", "enable-preset", "haw", "--allow-placeholder"], root)
        assert_condition(allowed.returncode == 0, f"placeholder preset enable failed: {allowed.stderr}{allowed.stdout}")
        assert_condition((root / "languages" / "haw.json").is_file(), "haw placeholder profile did not create haw.json")

        blocked = run([python, "auto_calibrate_chim_voices.py", "--language", "haw", "--all"], root)
        assert_condition(blocked.returncode != 0, "placeholder profile should not be accepted for calibration")
        assert_condition("placeholder calibration text" in blocked.stderr, "placeholder calibration guard message missing")


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify OmniVoice installer/uninstall lifecycle behavior in temp directories.")
    parser.add_argument("--python", default=sys.executable)
    args = parser.parse_args()

    checks = [
        ("uninstall_preserves_voices", lambda: verify_uninstall_preserves_voices(args.python)),
        ("uninstall_remove_voices", lambda: verify_uninstall_remove_voices(args.python)),
        ("installer_idempotent", verify_installer_idempotent),
        ("export_safety", lambda: verify_export_safety(args.python)),
        ("language_catalog", lambda: verify_language_catalog(args.python)),
    ]

    failed = False
    for name, check in checks:
        try:
            check()
            print(f"[PASS] {name}")
        except Exception as exc:
            failed = True
            print(f"[FAIL] {name}: {type(exc).__name__}: {exc}", file=sys.stderr)

    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
