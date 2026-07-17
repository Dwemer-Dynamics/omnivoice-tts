from __future__ import annotations

import argparse
import importlib
import json
import os
import platform
import socket
import sys
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from language_profiles import load_profiles, load_runtime_config, resolve_profile
from voice_library import count_runtime_ready

BASE_DIR = Path(__file__).resolve().parent
DIAGNOSTICS_DIR = BASE_DIR / "diagnostics"
DEFAULT_JSON = DIAGNOSTICS_DIR / "latest.json"
DEFAULT_CHIM_VOICES_DIR = Path("/var/www/html/HerikaServer/data/voices")
CONFIG_PATH = BASE_DIR / "config.json"
PROFILES_DIR = BASE_DIR / "languages"
VOICES_ROOT = BASE_DIR / "voices"
REQUIRED_IMPORTS = (
    "fastapi",
    "uvicorn",
    "pydantic",
    "soundfile",
    "librosa",
    "numpy",
    "torch",
    "transformers",
    "huggingface_hub",
    "omnivoice",
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class CheckResult:
    name: str
    status: str
    detail: str = ""

    @property
    def ok(self) -> bool:
        return self.status == "ok"

    @property
    def warning(self) -> bool:
        return self.status == "warning"


@dataclass
class DoctorReport:
    generated_at_utc: str
    base_dir: str
    python_executable: str
    python_version: str
    platform: str
    checks: list[CheckResult]
    gpu: dict[str, Any]
    recommendation: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "generated_at_utc": self.generated_at_utc,
            "base_dir": self.base_dir,
            "python_executable": self.python_executable,
            "python_version": self.python_version,
            "platform": self.platform,
            "checks": [asdict(check) for check in self.checks],
            "gpu": self.gpu,
            "recommendation": self.recommendation,
        }


def check_path(name: str, path: Path, *, kind: str = "file", required: bool = True) -> CheckResult:
    if kind == "file":
        exists = path.is_file()
    elif kind == "dir":
        exists = path.is_dir()
    else:
        exists = path.exists()

    if exists:
        return CheckResult(name, "ok", str(path))
    status = "error" if required else "warning"
    return CheckResult(name, status, f"missing: {path}")


def module_version(module: Any) -> str:
    return str(getattr(module, "__version__", "unknown"))


def check_imports() -> tuple[list[CheckResult], dict[str, Any]]:
    checks: list[CheckResult] = []
    modules: dict[str, Any] = {}
    for name in REQUIRED_IMPORTS:
        try:
            module = importlib.import_module(name)
            modules[name] = module
            checks.append(CheckResult(f"import:{name}", "ok", module_version(module)))
        except Exception as exc:
            checks.append(CheckResult(f"import:{name}", "error", f"{type(exc).__name__}: {exc}"))
    return checks, modules



def parse_version_tuple(value: str) -> tuple[int, int, int]:
    parts: list[int] = []
    for raw in str(value).split('.')[:3]:
        digits = ''.join(ch for ch in raw if ch.isdigit())
        parts.append(int(digits) if digits else 0)
    while len(parts) < 3:
        parts.append(0)
    return tuple(parts[:3])

def check_runtime_versions(modules: dict[str, Any]) -> list[CheckResult]:
    checks: list[CheckResult] = []
    transformers_module = modules.get("transformers")
    if transformers_module is not None:
        version = module_version(transformers_module)
        if parse_version_tuple(version) >= (5, 3, 0):
            checks.append(CheckResult("version:transformers", "ok", version))
        else:
            checks.append(CheckResult("version:transformers", "error", f"{version}; OmniVoice voice cloning needs >=5.3.0"))

    hf_module = modules.get("huggingface_hub")
    if hf_module is not None:
        version = module_version(hf_module)
        if parse_version_tuple(version) >= (1, 3, 0):
            checks.append(CheckResult("version:huggingface_hub", "ok", version))
        else:
            checks.append(CheckResult("version:huggingface_hub", "error", f"{version}; Transformers 5.3.0 needs >=1.3.0"))

    omnivoice_module = modules.get("omnivoice")
    if omnivoice_module is not None:
        checks.append(CheckResult("version:omnivoice", "ok", module_version(omnivoice_module)))
    return checks


def classify_gpu(total_gb: float | None, cuda_available: bool) -> str:
    if not cuda_available:
        return "unsupported: CUDA is not available"
    if total_gb is None:
        return "unknown: CUDA available but VRAM could not be read"
    if total_gb < 5.8:
        return "unsupported/experimental: less than 6 GB VRAM"
    if total_gb < 8.0:
        return "low_vram: use small batches and close other GPU apps"
    if total_gb < 10.0:
        return "normal_minimum: usable baseline"
    if total_gb < 16.0:
        return "recommended: good for normal calibration"
    return "excellent: comfortable for calibration and testing"


def inspect_torch(torch_module: Any | None) -> tuple[list[CheckResult], dict[str, Any]]:
    checks: list[CheckResult] = []
    gpu: dict[str, Any] = {
        "cuda_available": False,
        "name": None,
        "compute_capability": None,
        "total_vram_gb": None,
        "mode": "unknown",
    }
    if torch_module is None:
        checks.append(CheckResult("cuda", "error", "torch import failed"))
        gpu["mode"] = "unsupported: torch import failed"
        return checks, gpu

    try:
        cuda_available = bool(torch_module.cuda.is_available())
        gpu["cuda_available"] = cuda_available
        if not cuda_available:
            checks.append(CheckResult("cuda", "error", "torch.cuda.is_available() returned False"))
            gpu["mode"] = classify_gpu(None, False)
            return checks, gpu

        index = int(torch_module.cuda.current_device())
        props = torch_module.cuda.get_device_properties(index)
        total_gb = float(props.total_memory) / (1024 ** 3)
        name = str(torch_module.cuda.get_device_name(index))
        capability = tuple(int(x) for x in torch_module.cuda.get_device_capability(index))

        gpu.update(
            {
                "device_index": index,
                "name": name,
                "compute_capability": f"{capability[0]}.{capability[1]}",
                "total_vram_gb": round(total_gb, 2),
                "mode": classify_gpu(total_gb, True),
            }
        )
        status = "ok" if total_gb >= 5.8 else "warning"
        checks.append(CheckResult("cuda", status, f"{name}, {total_gb:.2f} GB VRAM, cc {capability[0]}.{capability[1]}"))
    except Exception as exc:
        checks.append(CheckResult("cuda", "error", f"{type(exc).__name__}: {exc}"))
        gpu["mode"] = "unsupported: CUDA inspection failed"
    return checks, gpu


def port_is_free(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.5)
        try:
            return sock.connect_ex(("127.0.0.1", port)) != 0
        except OSError:
            return False


def check_service_health() -> CheckResult:
    try:
        with urllib.request.urlopen("http://127.0.0.1:8021/health", timeout=2) as response:
            body = response.read().decode("utf-8", errors="replace")
        if '"model":"k2-fsa/OmniVoice"' in body or '"status":"ok"' in body:
            return CheckResult("service_health", "ok", "http://127.0.0.1:8021/health")
        return CheckResult("service_health", "warning", f"unexpected /health response: {body[:200]}")
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return CheckResult("service_health", "warning", f"not reachable: {exc}")


def check_chim_source() -> CheckResult:
    configured = os.environ.get("CHIM_VOICES_DIR", "").strip()
    source = Path(configured).expanduser() if configured else DEFAULT_CHIM_VOICES_DIR
    if not source.is_dir():
        return CheckResult("chim_source", "warning", f"missing: {source}")
    try:
        valid = 0
        invalid = 0
        for path in source.iterdir():
            if not path.is_file() or path.suffix.casefold() != ".wav":
                continue
            if path.stem.strip():
                valid += 1
            else:
                invalid += 1
        return CheckResult("chim_source", "ok", f"{source}, valid_wavs={valid}, invalid_wavs={invalid}")
    except OSError as exc:
        return CheckResult("chim_source", "warning", f"{type(exc).__name__}: {exc}")


def check_writable_dir(name: str, path: Path) -> CheckResult:
    if not path.is_dir():
        return CheckResult(name, "error", f"missing: {path}")
    probe = path / ".doctor_write_test"
    try:
        probe.write_text("ok\n", encoding="utf-8")
        probe.unlink(missing_ok=True)
        return CheckResult(name, "ok", str(path))
    except OSError as exc:
        return CheckResult(name, "error", f"{type(exc).__name__}: {exc}")


def check_active_language() -> list[CheckResult]:
    try:
        profiles = load_profiles(PROFILES_DIR)
        config = load_runtime_config(CONFIG_PATH)
        active = resolve_profile(str(config.get("active_language", "sk")), PROFILES_DIR, profiles)
        voice_count = count_runtime_ready(VOICES_ROOT / active.id, active.id)
        return [
            CheckResult("active_language", "ok", f"{active.id} ({active.display_name})"),
            CheckResult("prepared_voice_count", "ok" if voice_count else "warning", str(voice_count)),
        ]
    except Exception as exc:
        return [CheckResult("active_language", "error", f"{type(exc).__name__}: {exc}")]


def check_model_cache() -> CheckResult:
    candidates = [
        BASE_DIR / "model_cache",
        Path.home() / ".cache" / "huggingface" / "hub" / "models--k2-fsa--OmniVoice",
    ]
    existing = [path for path in candidates if path.exists()]
    if existing:
        return CheckResult("model_cache", "ok", ", ".join(str(path) for path in existing))
    return CheckResult("model_cache", "warning", "not found; first server start will download the model")


def build_report(*, include_imports: bool = True) -> DoctorReport:
    checks: list[CheckResult] = []
    checks.append(CheckResult("os", "ok" if os.name == "posix" else "error", platform.platform()))
    checks.append(
        CheckResult(
            "python_version",
            "ok" if (3, 10) <= sys.version_info[:2] <= (3, 12) else "error",
            platform.python_version(),
        )
    )
    checks.append(check_path("base_dir", BASE_DIR, kind="dir"))
    checks.append(check_path("config", BASE_DIR / "config.json"))
    checks.append(check_path("languages", BASE_DIR / "languages", kind="dir"))
    checks.append(check_path("server.py", BASE_DIR / "server.py"))
    checks.append(check_path("venv", BASE_DIR / "venv", kind="dir", required=False))
    checks.append(check_path("start-gpu.sh", BASE_DIR / "start-gpu.sh"))
    port_free = port_is_free(8021)
    health_check = check_service_health()
    if port_free:
        checks.append(CheckResult("port_8021", "ok", "free"))
    elif health_check.ok:
        checks.append(CheckResult("port_8021", "ok", "in use by healthy OmniVoice service"))
    else:
        checks.append(CheckResult("port_8021", "warning", "in use by another or unhealthy service"))
    checks.append(health_check)
    checks.append(CheckResult("bind_address", "ok", "0.0.0.0 via start-gpu.sh; direct CLI defaults to 127.0.0.1"))
    checks.append(check_chim_source())
    checks.append(check_model_cache())
    for folder in ("voices", "reports", "logs", "diagnostics"):
        checks.append(check_writable_dir(f"writable:{folder}", BASE_DIR / folder))
    checks.extend(check_active_language())

    modules: dict[str, Any] = {}
    if include_imports:
        import_checks, modules = check_imports()
        checks.extend(import_checks)
        checks.extend(check_runtime_versions(modules))

    torch_module = modules.get("torch")
    torch_checks, gpu = inspect_torch(torch_module)
    checks.extend(torch_checks)

    errors = [check for check in checks if check.status == "error"]
    warnings = [check for check in checks if check.status == "warning"]
    if errors:
        recommendation = "not_ready: fix error checks first"
    elif gpu.get("cuda_available") and gpu.get("total_vram_gb", 0) and gpu.get("total_vram_gb", 0) < 5.8:
        recommendation = "not_recommended: GPU VRAM is below the practical minimum"
    elif warnings:
        recommendation = "ready_with_warnings"
    else:
        recommendation = "ready"

    return DoctorReport(
        generated_at_utc=utc_now(),
        base_dir=str(BASE_DIR),
        python_executable=sys.executable,
        python_version=platform.python_version(),
        platform=platform.platform(),
        checks=checks,
        gpu=gpu,
        recommendation=recommendation,
    )


def print_report(report: DoctorReport) -> None:
    print("Multilingual TTS Tool Doctor")
    print(f"Base:   {report.base_dir}")
    print(f"Python: {report.python_executable}")
    print(f"GPU:    {report.gpu.get('name') or '(none)'}")
    if report.gpu.get("total_vram_gb") is not None:
        print(f"VRAM:   {report.gpu['total_vram_gb']} GB")
    print(f"Mode:   {report.gpu.get('mode')}")
    print(f"Result: {report.recommendation}")
    print("")
    for check in report.checks:
        marker = "OK" if check.status == "ok" else ("WARN" if check.status == "warning" else "FAIL")
        print(f"[{marker:4}] {check.name}: {check.detail}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Check local Multilingual TTS Tool installer/runtime health.")
    parser.add_argument("--quick", action="store_true", help="Run normal quick checks; kept for readable batch syntax.")
    parser.add_argument("--json", type=Path, help="Write machine-readable diagnostics JSON.")
    args = parser.parse_args()

    report = build_report(include_imports=True)
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(report.to_dict(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"Diagnostics JSON: {args.json}")
    print_report(report)

    return 1 if any(check.status == "error" for check in report.checks) else 0


if __name__ == "__main__":
    raise SystemExit(main())
