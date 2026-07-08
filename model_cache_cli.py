from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

BASE_DIR = Path(__file__).resolve().parent
DIAGNOSTICS_DIR = BASE_DIR / "diagnostics"
MODEL_REPORT = DIAGNOSTICS_DIR / "model_cache.json"

MODELS = {
    "omnivoice": "k2-fsa/OmniVoice",
    "whisper": "openai/whisper-large-v3-turbo",
    "wavlm": "microsoft/wavlm-base-plus-sv",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class CacheEntry:
    key: str
    repo_id: str
    status: str
    path: str = ""
    error: str = ""

    def to_dict(self) -> dict:
        return {
            "key": self.key,
            "repo_id": self.repo_id,
            "status": self.status,
            "path": self.path,
            "error": self.error,
        }


def selected_models(values: list[str]) -> list[tuple[str, str]]:
    if not values or "all" in values:
        return list(MODELS.items())
    results: list[tuple[str, str]] = []
    for value in values:
        key = value.casefold().strip()
        if key not in MODELS:
            raise SystemExit(f"Unknown model key: {value}. Valid: all, {', '.join(MODELS)}")
        item = (key, MODELS[key])
        if item not in results:
            results.append(item)
    return results


def snapshot(repo_id: str, *, local_files_only: bool) -> str:
    from huggingface_hub import snapshot_download

    return snapshot_download(
        repo_id=repo_id,
        local_files_only=local_files_only,
        resume_download=True,
    )


def inspect_cache(items: list[tuple[str, str]], *, download: bool) -> list[CacheEntry]:
    entries: list[CacheEntry] = []
    os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")
    os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
    for key, repo_id in items:
        try:
            path = snapshot(repo_id, local_files_only=not download)
            entries.append(CacheEntry(key=key, repo_id=repo_id, status="ready", path=path))
        except Exception as exc:
            status = "missing" if not download else "failed"
            entries.append(CacheEntry(key=key, repo_id=repo_id, status=status, error=f"{type(exc).__name__}: {exc}"))
    return entries


def write_report(entries: list[CacheEntry]) -> None:
    DIAGNOSTICS_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "generated_at_utc": utc_now(),
        "models": [entry.to_dict() for entry in entries],
    }
    MODEL_REPORT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def print_entries(entries: list[CacheEntry]) -> None:
    for entry in entries:
        marker = "OK" if entry.status == "ready" else ("MISS" if entry.status == "missing" else "FAIL")
        print(f"[{marker:4}] {entry.key:9} {entry.repo_id}")
        if entry.path:
            print(f"       {entry.path}")
        if entry.error:
            print(f"       {entry.error}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Download or inspect Hugging Face model cache for Multilingual TTS Tool.")
    sub = parser.add_subparsers(dest="command", required=True)

    status = sub.add_parser("status", help="Check whether required models are already cached.")
    status.add_argument("model", nargs="*", help="all, omnivoice, whisper, wavlm")

    download = sub.add_parser("download", help="Download required models into the Hugging Face cache.")
    download.add_argument("model", nargs="*", help="all, omnivoice, whisper, wavlm")

    args = parser.parse_args()
    items = selected_models(args.model)
    do_download = args.command == "download"

    if do_download:
        print("Downloading model cache. This can take a while on the first run.")
        print("The package stays lightweight; files are stored in the normal Hugging Face cache.")
    entries = inspect_cache(items, download=do_download)
    write_report(entries)
    print_entries(entries)
    print(f"Report: {MODEL_REPORT}")

    return 1 if any(entry.status == "failed" for entry in entries) else 0


if __name__ == "__main__":
    raise SystemExit(main())
