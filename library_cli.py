from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from language_profiles import load_profiles, resolve_profile
from voice_library import (
    VoiceAudit,
    audit_language_library,
    quarantine_invalid_directories,
    utc_now,
)


BASE_DIR = Path(__file__).resolve().parent
PROFILES_DIR = BASE_DIR / "languages"
VOICES_ROOT = BASE_DIR / "voices"
REPORTS_ROOT = BASE_DIR / "reports"
QUARANTINE_ROOT = VOICES_ROOT / "_quarantine"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Audit and safely quarantine invalid Multilingual TTS Tool voice folders."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    audit_parser = subparsers.add_parser(
        "audit",
        help="Check VoiceIDs, runtime reference pairs, WAV format and metadata.",
    )
    audit_parser.add_argument(
        "--language",
        default="all",
        help="Language profile id/alias, or 'all' (default: all).",
    )
    audit_parser.add_argument(
        "--write-report",
        action="store_true",
        help="Write JSON reports to reports/<language>/library_audit.json.",
    )
    audit_parser.add_argument(
        "--strict",
        action="store_true",
        help="Return exit code 1 when invalid or broken folders are found.",
    )

    quarantine_parser = subparsers.add_parser(
        "quarantine-invalid",
        help=(
            "Move folders with impossible/file-like VoiceIDs into voices/_quarantine. "
            "Nothing is deleted."
        ),
    )
    quarantine_parser.add_argument(
        "--language",
        default="all",
        help="Language profile id/alias, or 'all' (default: all).",
    )
    quarantine_parser.add_argument(
        "--yes",
        action="store_true",
        help="Actually move folders. Without this flag the command is a dry run.",
    )
    return parser


def select_language_ids(value: str, profiles_dir: Path) -> list[str]:
    profiles = load_profiles(profiles_dir)
    if value.strip().casefold() == "all":
        return sorted(profiles)
    return [resolve_profile(value, profiles_dir, profiles).id]


def summarize(audits: list[VoiceAudit]) -> dict:
    return {
        "total_directories": len(audits),
        "runtime_ready": sum(1 for item in audits if item.runtime_ready),
        "calibrated": sum(1 for item in audits if item.runtime_ready and item.calibrated),
        "invalid_id": sum(1 for item in audits if not item.valid_id),
        "broken": sum(1 for item in audits if item.valid_id and item.errors),
        "with_warnings": sum(1 for item in audits if item.warnings),
    }


def print_audit(language_id: str, audits: list[VoiceAudit]) -> dict:
    summary = summarize(audits)
    print("")
    print(f"[{language_id}] {VOICES_ROOT / language_id}")
    print(
        "  total={total_directories} runtime_ready={runtime_ready} "
        "calibrated={calibrated} invalid_id={invalid_id} "
        "broken={broken} warnings={with_warnings}".format(**summary)
    )

    for item in audits:
        if not item.errors and not item.warnings:
            continue
        print(f"  {item.status.upper():13} {item.name}")
        for error in item.errors:
            print(f"    ERROR:   {error}")
        for warning in item.warnings:
            print(f"    WARNING: {warning}")
    return summary


def write_report(language_id: str, audits: list[VoiceAudit], summary: dict) -> Path:
    report_dir = REPORTS_ROOT / language_id
    report_dir.mkdir(parents=True, exist_ok=True)
    report_path = report_dir / "library_audit.json"
    report_path.write_text(
        json.dumps(
            {
                "generated_at_utc": utc_now(),
                "language_profile_id": language_id,
                "voice_directory": str(VOICES_ROOT / language_id),
                "summary": summary,
                "voices": [item.to_dict() for item in audits],
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return report_path


def main() -> int:
    args = build_parser().parse_args()
    try:
        language_ids = select_language_ids(args.language, PROFILES_DIR)
    except (FileNotFoundError, ValueError, KeyError, RuntimeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    if args.command == "audit":
        has_strict_issue = False
        for language_id in language_ids:
            audits = audit_language_library(VOICES_ROOT / language_id, language_id)
            summary = print_audit(language_id, audits)
            if summary["invalid_id"] or summary["broken"]:
                has_strict_issue = True
            if args.write_report:
                path = write_report(language_id, audits, summary)
                print(f"  report={path}")
        return 1 if args.strict and has_strict_issue else 0

    invalid_found = 0
    moved_total = 0
    for language_id in language_ids:
        language_dir = VOICES_ROOT / language_id
        audits = audit_language_library(language_dir, language_id)
        invalid = [item for item in audits if not item.valid_id]
        invalid_found += len(invalid)
        if not invalid:
            print(f"[{language_id}] no invalid VoiceID folders found")
            continue

        print(f"[{language_id}] invalid VoiceID folders:")
        for item in invalid:
            print(f"  {item.name}: {'; '.join(item.errors)}")

        if not args.yes:
            print("  DRY RUN: add --yes to move them into voices/_quarantine.")
            continue

        moved = quarantine_invalid_directories(
            language_dir=language_dir,
            language_id=language_id,
            quarantine_root=QUARANTINE_ROOT,
        )
        for source, destination in moved:
            print(f"  MOVED {source.name} -> {destination}")
        moved_total += len(moved)

    if invalid_found and not args.yes:
        return 0
    print(f"Invalid found: {invalid_found}; moved: {moved_total}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
