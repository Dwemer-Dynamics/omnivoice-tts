from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from doctor_cli import build_report
from language_profiles import load_profiles, load_runtime_config, resolve_profile
from library_cli import summarize
from voice_library import audit_language_library, utc_now


BASE_DIR = Path(__file__).resolve().parent
CONFIG_PATH = BASE_DIR / "config.json"
PROFILES_DIR = BASE_DIR / "languages"
VOICES_ROOT = BASE_DIR / "voices"
REPORTS_ROOT = BASE_DIR / "reports"
DEFAULT_REPORT = BASE_DIR / "diagnostics" / "verify_latest.json"
DEFAULT_BASE_URL = "http://127.0.0.1:8021"


@dataclass
class VerifyCheck:
    name: str
    status: str
    detail: str = ""
    data: dict[str, Any] | None = None

    @property
    def failed(self) -> bool:
        return self.status == "fail"


def read_json(url: str, timeout: float = 10.0) -> tuple[Any | None, str]:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            body = response.read().decode("utf-8", errors="replace")
        decoded = json.loads(body)
        return decoded, ""
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
        return None, f"{type(exc).__name__}: {exc}"


def json_get(url: str, timeout: float = 10.0) -> tuple[dict[str, Any] | None, str]:
    decoded, error = read_json(url, timeout)
    if error:
        return None, error
    if not isinstance(decoded, dict):
        return None, f"non-object JSON response: {str(decoded)[:200]}"
    return decoded, ""


def post_json(url: str, payload: dict[str, Any], timeout: float = 20.0) -> tuple[Any | None, str, int]:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read().decode("utf-8", errors="replace")
            status = int(response.status)
        decoded = json.loads(body)
        return decoded, "", status
    except urllib.error.HTTPError as exc:
        try:
            body = exc.read().decode("utf-8", errors="replace")
        except Exception:
            body = ""
        try:
            decoded = json.loads(body)
        except json.JSONDecodeError:
            decoded = None
        return decoded, f"HTTP {exc.code}: {body[:300]}", int(exc.code)
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
        return None, f"{type(exc).__name__}: {exc}", 0


def post_tts(base_url: str, text: str, voice: str, language: str, endpoint: str = "/tts_to_audio") -> tuple[bytes | None, str, int]:
    payload = json.dumps(
        {
            "text": text,
            "speaker_wav": voice,
            "language": language,
        },
        ensure_ascii=False,
    ).encode("utf-8")
    request = urllib.request.Request(
        f"{base_url.rstrip('/')}{endpoint}",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            content_type = response.headers.get("Content-Type", "")
            status = int(response.status)
            body = response.read()
        if status < 200 or status >= 300:
            return None, f"HTTP {status}: {body[:200]!r}", status
        if "audio/wav" not in content_type.lower():
            return None, f"unexpected content-type {content_type}", status
        if len(body) <= 44 or body[:4] != b"RIFF":
            return None, f"response was not a valid-looking WAV; bytes={len(body)}", status
        return body, "", status
    except urllib.error.HTTPError as exc:
        try:
            body = exc.read().decode("utf-8", errors="replace")
        except Exception:
            body = ""
        return None, f"HTTP {exc.code}: {body[:300]}", int(exc.code)
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return None, f"{type(exc).__name__}: {exc}", 0


def active_language_id() -> str:
    profiles = load_profiles(PROFILES_DIR)
    config = load_runtime_config(CONFIG_PATH)
    return resolve_profile(str(config.get("active_language", "sk")), PROFILES_DIR, profiles).id


def check_doctor() -> VerifyCheck:
    report = build_report(include_imports=True)
    bad = [asdict(check) for check in report.checks if check.status == "error"]
    warnings = [asdict(check) for check in report.checks if check.status == "warning"]
    status = "pass" if not bad else "fail"
    return VerifyCheck(
        "doctor",
        status,
        report.recommendation,
        {
            "bad_checks": bad,
            "warning_checks": warnings,
            "gpu": report.gpu,
        },
    )


def check_service(base_url: str) -> tuple[VerifyCheck, dict[str, Any] | None, dict[str, Any] | None]:
    health, health_error = json_get(f"{base_url.rstrip('/')}/health")
    provider, provider_error = json_get(f"{base_url.rstrip('/')}/provider_info")
    if health_error:
        return VerifyCheck("service_health", "fail", health_error), health, provider
    if provider_error:
        return VerifyCheck("service_health", "fail", provider_error), health, provider
    if str(health.get("status", "")).lower() != "ok":
        return VerifyCheck("service_health", "fail", f"unexpected status: {health.get('status')}", {"health": health}), health, provider
    if provider.get("honor_request_language") is not False:
        return VerifyCheck(
            "service_health",
            "fail",
            "provider_info must expose honor_request_language=false for current active-language-only runtime",
            {"provider_info": provider},
        ), health, provider
    return VerifyCheck(
        "service_health",
        "pass",
        f"voice_count={health.get('voice_count')} default_voice={health.get('default_voice')}",
        {
            "health": {
                "status": health.get("status"),
                "device": health.get("device"),
                "gpu": health.get("gpu"),
                "voice_count": health.get("voice_count"),
                "default_voice": health.get("default_voice"),
                "active_language": health.get("active_language"),
            },
            "provider_info": {
                "honor_request_language": provider.get("honor_request_language"),
                "fallback_male": provider.get("fallback_male"),
                "fallback_female": provider.get("fallback_female"),
                "voice_count": provider.get("voice_count"),
            },
        },
    ), health, provider


def check_bind_address(port: int) -> VerifyCheck:
    try:
        result = subprocess.run(
            ["ss", "-H", "-ltn"],
            text=True,
            capture_output=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return VerifyCheck("bind_address", "warn", f"unable to run ss: {type(exc).__name__}: {exc}")

    if result.returncode != 0:
        return VerifyCheck("bind_address", "warn", (result.stderr or result.stdout).strip())

    listeners = [line.strip() for line in result.stdout.splitlines() if f":{port}" in line]
    if not listeners:
        return VerifyCheck("bind_address", "fail", f"no listener found on port {port}")

    wildcard = [
        line
        for line in listeners
        if f"0.0.0.0:{port}" in line or f"*:{port}" in line or f"[::]:{port}" in line or f":::{port}" in line
    ]
    if wildcard:
        return VerifyCheck("bind_address", "pass", "LAN listener enabled", {"listeners": listeners})

    loopback = [line for line in listeners if f"127.0.0.1:{port}" in line or f"[::1]:{port}" in line]
    if loopback:
        return VerifyCheck("bind_address", "pass", "loopback listener only", {"listeners": listeners})
    return VerifyCheck("bind_address", "warn", "listener found, but its bind address could not be classified", {"listeners": listeners})


def listening_tcp_ports() -> tuple[dict[int, list[str]], str]:
    try:
        result = subprocess.run(
            ["ss", "-H", "-ltn"],
            text=True,
            capture_output=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {}, f"{type(exc).__name__}: {exc}"
    if result.returncode != 0:
        return {}, (result.stderr or result.stdout).strip()

    by_port: dict[int, list[str]] = {}
    for line in result.stdout.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        parts = stripped.split()
        if len(parts) < 4:
            continue
        local = parts[3]
        try:
            port = int(local.rsplit(":", 1)[1])
        except (IndexError, ValueError):
            continue
        by_port.setdefault(port, []).append(stripped)
    return by_port, ""


def check_dwemer_service_ports() -> VerifyCheck:
    by_port, error = listening_tcp_ports()
    if error:
        return VerifyCheck("dwemer_service_ports", "fail", error)

    required = {
        5432: "PostgreSQL",
        8081: "CHIM / HerikaServer",
        8082: "Minime / TXT2VEC",
        8083: "StobeServer",
        8021: "OmniVoice TTS",
        8022: "Parakeet STT",
        3100: "CHIM MCP",
    }
    optional = {
        8020: "Legacy local TTS engine",
        8086: "PocketTTS audio.cpp",
    }
    missing = [name for port, name in required.items() if port not in by_port]
    data = {
        "required": {
            str(port): {
                "name": name,
                "listeners": by_port.get(port, []),
            }
            for port, name in required.items()
        },
        "optional": {
            str(port): {
                "name": name,
                "listeners": by_port.get(port, []),
            }
            for port, name in optional.items()
            if port in by_port
        },
    }
    if missing:
        return VerifyCheck("dwemer_service_ports", "fail", f"missing required service ports: {', '.join(missing)}", data)
    return VerifyCheck("dwemer_service_ports", "pass", "required DwemerDistro service ports are listening", data)


def check_voice_library(language: str, write_report: bool) -> VerifyCheck:
    audits = audit_language_library(VOICES_ROOT / language, language)
    summary = summarize(audits)
    report_path: Path | None = None
    if write_report:
        report_dir = REPORTS_ROOT / language
        report_dir.mkdir(parents=True, exist_ok=True)
        report_path = report_dir / "library_audit.json"
        report_path.write_text(
            json.dumps(
                {
                    "generated_at_utc": utc_now(),
                    "language_profile_id": language,
                    "voice_directory": str(VOICES_ROOT / language),
                    "summary": summary,
                    "voices": [item.to_dict() for item in audits],
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
    failed = bool(summary["invalid_id"] or summary["broken"] or summary["runtime_ready"] == 0)
    return VerifyCheck(
        "voice_library",
        "fail" if failed else "pass",
        (
            "total={total_directories} runtime_ready={runtime_ready} calibrated={calibrated} "
            "invalid_id={invalid_id} broken={broken} warnings={with_warnings}"
        ).format(**summary),
        {"summary": summary, "report": str(report_path) if report_path else None},
    )


def check_synthesis(base_url: str, language: str, voices: list[str]) -> VerifyCheck:
    results: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    for voice in voices:
        audio, error, status = post_tts(base_url, f"OmniVoice verification for {voice}.", voice, language)
        item = {
            "voice": voice,
            "http_status": status,
            "bytes": len(audio) if audio is not None else 0,
            "error": error,
        }
        results.append(item)
        if audio is None:
            failures.append(item)
    if failures:
        return VerifyCheck("synthesis", "fail", f"{len(failures)} synthesis request(s) failed", {"results": results})
    return VerifyCheck("synthesis", "pass", f"{len(results)} synthesis request(s) returned audio/wav", {"results": results})


def check_service_contract(base_url: str, language: str, voice: str) -> VerifyCheck:
    base = base_url.rstrip("/")
    results: list[dict[str, Any]] = []
    failures: list[str] = []

    def record(name: str, ok: bool, detail: str = "", data: Any | None = None) -> None:
        results.append({"name": name, "ok": ok, "detail": "ok" if ok else detail, "data": data})
        if not ok:
            failures.append(f"{name}: {detail}")

    speakers, error = read_json(f"{base}/speakers_list")
    record(
        "GET /speakers_list",
        isinstance(speakers, list) and voice in speakers,
        error or f"expected list containing {voice!r}",
        {"count": len(speakers) if isinstance(speakers, list) else None},
    )

    speakers_extended, error = read_json(f"{base}/speakers_list_extended")
    extended_entry: dict[str, Any] | None = None
    if isinstance(speakers_extended, list):
        for item in speakers_extended:
            if isinstance(item, dict) and item.get("voice_id") == voice:
                extended_entry = item
                break
    extended_ok = (
        isinstance(extended_entry, dict)
        and extended_entry.get("language") == language
        and extended_entry.get("language_profile_id") == language
        and str(extended_entry.get("reference_wav") or "").endswith("/reference.wav")
        and str(extended_entry.get("reference_text") or "").endswith("/reference.txt")
        and isinstance(extended_entry.get("metadata"), dict)
        and bool(extended_entry.get("calibration_status"))
    )
    record(
        "GET /speakers_list_extended",
        extended_ok,
        error or f"expected complete metadata entry for {voice!r}",
        {
            "count": len(speakers_extended) if isinstance(speakers_extended, list) else None,
            "entry": extended_entry,
        },
    )

    languages, error = read_json(f"{base}/languages")
    record(
        "GET /languages",
        isinstance(languages, list) and language in [str(item) for item in languages],
        error or f"expected active language {language!r}",
        {"languages": languages if isinstance(languages, list) else None},
    )

    active, error = json_get(f"{base}/active_language")
    active_id = ""
    if isinstance(active, dict) and isinstance(active.get("active"), dict):
        active_id = str(active["active"].get("id") or "")
    record(
        "GET /active_language",
        active_id == language,
        error or f"expected active language {language!r}, got {active_id!r}",
        active,
    )

    switched, error, status = post_json(f"{base}/active_language", {"language": language})
    switched_id = ""
    if isinstance(switched, dict) and isinstance(switched.get("active"), dict):
        switched_id = str(switched["active"].get("id") or "")
    record(
        "POST /active_language",
        status == 200 and switched_id == language,
        error or f"expected HTTP 200 and active language {language!r}, got status={status} active={switched_id!r}",
        switched,
    )

    missing_language_id = "zz_omnivoice_verify_missing"
    missing_language, error, status = post_json(f"{base}/active_language", {"language": missing_language_id})
    record(
        "POST /active_language unknown language",
        status == 404 and isinstance(missing_language, dict) and "detail" in missing_language,
        error or f"expected JSON 404 for unknown language, got status={status}",
        missing_language,
    )

    reloaded, error, status = post_json(f"{base}/reload_voices", {})
    record(
        "POST /reload_voices",
        status == 200
        and isinstance(reloaded, dict)
        and reloaded.get("status") == "reloaded"
        and str(reloaded.get("active_language") or "") == language
        and int(reloaded.get("voice_count") or 0) > 0,
        error or f"expected reload success, got status={status}",
        reloaded,
    )

    settings, error, status = post_json(f"{base}/set_tts_settings", {"temperature": 0.9, "speed": 1.0})
    record(
        "POST /set_tts_settings",
        status == 200 and isinstance(settings, dict) and settings.get("status") == "ok",
        error or f"expected compatibility success, got status={status}",
        settings,
    )

    audio, error, status = post_tts(base_url, "OmniVoice trailing slash contract verification.", voice, language, "/tts_to_audio/")
    record(
        "POST /tts_to_audio/",
        audio is not None and status == 200,
        error or f"expected audio/wav from trailing slash endpoint, got status={status}",
        {"bytes": len(audio) if audio is not None else 0},
    )

    path_style_voice = f"/tmp/{voice}.wav"
    audio, error, status = post_tts(
        base_url,
        "OmniVoice path-style speaker_wav contract verification.",
        path_style_voice,
        language,
    )
    record(
        "POST /tts_to_audio path-style speaker_wav",
        audio is not None and status == 200,
        error or f"expected path-style speaker_wav {path_style_voice!r} to resolve as VoiceID, got status={status}",
        {"speaker_wav": path_style_voice, "bytes": len(audio) if audio is not None else 0},
    )

    if failures:
        return VerifyCheck("service_contract", "fail", f"{len(failures)} contract check(s) failed", {"results": results})
    return VerifyCheck("service_contract", "pass", "XTTS-compatible service contract endpoints responded correctly", {"results": results})


def run_php_smoke(script: str, args: list[str]) -> tuple[dict[str, Any] | None, str, int]:
    with tempfile.NamedTemporaryFile("w", suffix=".php", encoding="utf-8", delete=False) as handle:
        handle.write(script)
        script_path = Path(handle.name)
    try:
        result = subprocess.run(
            ["php", str(script_path), *args],
            text=True,
            capture_output=True,
            timeout=180,
            check=False,
        )
    finally:
        script_path.unlink(missing_ok=True)

    output = result.stdout.strip().splitlines()
    last_line = output[-1] if output else ""
    try:
        decoded = json.loads(last_line)
    except json.JSONDecodeError:
        decoded = None
    error = (result.stderr or "").strip()
    if decoded is None:
        error = (error + "\n" + result.stdout).strip()
    return decoded, error, int(result.returncode)


def psql_query(database: str, sql: str) -> tuple[list[str], str, int]:
    env = {**os.environ, "PGPASSWORD": os.environ.get("PGPASSWORD") or "dwemer"}
    try:
        result = subprocess.run(
            ["psql", "-h", "127.0.0.1", "-U", "dwemer", "-d", database, "-At", "-F", "\t", "-c", sql],
            text=True,
            capture_output=True,
            timeout=20,
            check=False,
            env=env,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return [], f"{type(exc).__name__}: {exc}", 1
    rows = [line for line in result.stdout.splitlines() if line.strip()]
    return rows, (result.stderr or "").strip(), int(result.returncode)


def check_herika_connector_row(database: str, target_name: str) -> dict[str, Any]:
    rows, error, exit_code = psql_query(
        database,
        """
        WITH connector AS (
            SELECT id, driver, label, url, voice_field
            FROM core_tts_connector
            WHERE label = 'ddistro omnivoice'
            ORDER BY id
            LIMIT 1
        )
        SELECT c.id,
               c.driver,
               c.label,
               c.url,
               c.voice_field,
               (SELECT COUNT(*) FROM core_profiles),
               (SELECT COUNT(*) FROM core_profiles WHERE tts_connector_id = c.id),
               (SELECT COUNT(*) FROM core_profiles WHERE COALESCE(default_npc, '') = '1' OR COALESCE(default_narrator, '') = '1'),
               (SELECT COUNT(*) FROM core_profiles WHERE (COALESCE(default_npc, '') = '1' OR COALESCE(default_narrator, '') = '1') AND tts_connector_id = c.id)
        FROM connector c;
        """,
    )
    item: dict[str, Any] = {
        "target": target_name,
        "database": database,
        "exit_code": exit_code,
        "stderr": error,
        "row": rows[0].split("\t") if rows else [],
        "ok": False,
    }
    if exit_code != 0 or not rows:
        return item
    fields = item["row"]
    item["ok"] = (
        len(fields) >= 9
        and fields[1] == "xtts-fastapi"
        and fields[2] == "ddistro omnivoice"
        and fields[3] == "http://127.0.0.1:8021"
        and fields[4] == "voiceid"
        and int(fields[7] or "0") == int(fields[8] or "0")
    )
    return item


def check_stobe_connector_row() -> dict[str, Any]:
    rows, error, exit_code = psql_query(
        "stobe",
        """
        SELECT id,
               name,
               connector_type,
               base_url,
               is_default,
               COALESCE(config->>'language', ''),
               COALESCE(config->>'fallback_male', ''),
               COALESCE(config->>'fallback_female', ''),
               (SELECT COUNT(*) FROM core_profiles),
               (SELECT COUNT(*) FROM core_profiles WHERE tts_connector_id = core_tts_connector.id)
        FROM core_tts_connector
        WHERE LOWER(name) = LOWER('OmniVoice Default')
        ORDER BY id
        LIMIT 1;
        """,
    )
    item: dict[str, Any] = {
        "target": "STOBE / Kenshi",
        "database": "stobe",
        "exit_code": exit_code,
        "stderr": error,
        "row": rows[0].split("\t") if rows else [],
        "ok": False,
    }
    if exit_code != 0 or not rows:
        return item
    fields = item["row"]
    item["ok"] = (
        len(fields) >= 10
        and fields[1] == "OmniVoice Default"
        and fields[2] == "omnivoice"
        and fields[3] == "http://127.0.0.1:8021"
        and fields[4] == "t"
        and fields[5] != ""
        and fields[6] == "default_male"
        and fields[7] == "default_female"
        and (int(fields[8] or "0") == 0 or int(fields[9] or "0") > 0)
    )
    return item


def check_dwemer_database_connectors() -> VerifyCheck:
    if not shutil_which("psql"):
        return VerifyCheck("dwemer_databases", "fail", "psql executable not found")
    results = [
        check_herika_connector_row("dwemer", "CHIM / Skyrim"),
        check_herika_connector_row("dialectic", "Dialectic / Fallout NV"),
        check_stobe_connector_row(),
    ]
    failures = [item for item in results if not item.get("ok")]
    if failures:
        return VerifyCheck("dwemer_databases", "fail", f"{len(failures)} connector row check(s) failed", {"results": results})
    return VerifyCheck("dwemer_databases", "pass", "CHIM, Dialectic, and Stobe connector rows and profile assignments point at OmniVoice", {"results": results})


HERIKA_STYLE_PHP_SMOKE = r"""<?php
if ($argc < 5) {
    fwrite(STDERR, "usage: php smoke.php <server_dir> <name_global> <voiceid> <language>\n");
    exit(2);
}
$serverDir = rtrim($argv[1], '/');
$nameGlobal = $argv[2];
$voiceId = $argv[3];
$language = $argv[4];
$connector = $serverDir . '/tts/tts-xtts-fastapi.php';
if (!is_file($connector)) {
    fwrite(STDERR, "missing connector: $connector\n");
    exit(2);
}
if (!class_exists('Logger')) {
    class Logger {
        public static function error($message) { fwrite(STDERR, "ERROR: $message\n"); }
        public static function warn($message) { fwrite(STDERR, "WARN: $message\n"); }
        public static function info($message) { }
    }
}
$GLOBALS['TTS'] = [
    'XTTSFASTAPI' => [
        'endpoint' => 'http://127.0.0.1:8021',
        'voiceid' => $voiceId,
        'language' => $language,
        'RESET' => false,
    ],
    'FORCED_VOICE_DEV' => '',
    'FORCED_LANG_DEV' => '',
];
$GLOBALS['TTS_FFMPEG_FILTERS'] = [];
$GLOBALS['DEBUG_DATA'] = [];
$GLOBALS['AVOID_TTS_CACHE'] = true;
$GLOBALS['PATCH_OVERRIDE_VOICE'] = $voiceId;
$GLOBALS['PATCH_OVERRIDE_TTS_LANGUAGE'] = $language;
$GLOBALS[$nameGlobal] = 'Codex Verification';
require $connector;
if (!isset($GLOBALS['TTS_IN_USE']) || !is_callable($GLOBALS['TTS_IN_USE'])) {
    fwrite(STDERR, "TTS_IN_USE not registered\n");
    exit(2);
}
$hash = 'omnivoice-verify-' . strtolower($nameGlobal) . '-' . time();
$result = call_user_func($GLOBALS['TTS_IN_USE'], 'OmniVoice connector verification line.', '', $hash);
$path = is_string($result) ? $serverDir . '/' . $result : '';
$ok = is_file($path) && filesize($path) > 44 && file_get_contents($path, false, null, 0, 4) === 'RIFF';
echo json_encode([
    'server_dir' => $serverDir,
    'requested_voice' => $voiceId,
    'requested_language' => $language,
    'result' => $result,
    'path' => $path,
    'bytes' => is_file($path) ? filesize($path) : 0,
    'riff' => is_file($path) ? (file_get_contents($path, false, null, 0, 4) === 'RIFF') : false,
    'debug' => $GLOBALS['DEBUG_DATA'],
    'ok' => $ok,
], JSON_UNESCAPED_SLASHES) . PHP_EOL;
exit($ok ? 0 : 1);
"""


STOBE_PHP_SMOKE = r"""<?php
$serverDir = '/var/www/html/StobeServer';
$bootstrap = $serverDir . '/lib/bootstrap.php';
if (!is_file($bootstrap)) {
    fwrite(STDERR, "missing bootstrap: $bootstrap\n");
    exit(2);
}
chdir($serverDir);
require_once($bootstrap);
$db = $GLOBALS['db'] ?? null;
if (!$db) {
    fwrite(STDERR, "database handle not available\n");
    exit(2);
}
$connector = $db->fetchOne("SELECT * FROM core_tts_connector WHERE LOWER(name)=LOWER($1) ORDER BY id LIMIT 1", ['OmniVoice Default']);
if (!$connector) {
    fwrite(STDERR, "OmniVoice Default connector not found\n");
    exit(2);
}
$result = stobeSynthesizeTtsFromConnector($connector, 'OmniVoice Stobe connector verification line.', 'default_male');
$path = !empty($result['audio_path']) ? $serverDir . '/' . $result['audio_path'] : '';
$ok = is_file($path) && filesize($path) > 44 && file_get_contents($path, false, null, 0, 4) === 'RIFF';
echo json_encode([
    'connector_type' => $connector['connector_type'] ?? null,
    'base_url' => $connector['base_url'] ?? null,
    'provider' => $result['provider'] ?? null,
    'voiceid' => $result['voiceid'] ?? null,
    'audio_path' => $result['audio_path'] ?? null,
    'path' => $path,
    'bytes' => is_file($path) ? filesize($path) : 0,
    'riff' => is_file($path) ? (file_get_contents($path, false, null, 0, 4) === 'RIFF') : false,
    'ok' => $ok && (($result['provider'] ?? '') === 'omnivoice'),
], JSON_UNESCAPED_SLASHES) . PHP_EOL;
exit(($ok && (($result['provider'] ?? '') === 'omnivoice')) ? 0 : 1);
"""


def check_dwemer_sites() -> VerifyCheck:
    if not shutil_which("php"):
        return VerifyCheck("dwemer_sites", "fail", "php executable not found")

    targets = [
        ("CHIM / Skyrim", HERIKA_STYLE_PHP_SMOKE, ["/var/www/html/HerikaServer", "HERIKA_NAME", "malenord", "sk"]),
        ("Dialectic / Fallout NV", HERIKA_STYLE_PHP_SMOKE, ["/var/www/html/DialecticServer", "DIALECTIC_NAME", "default_male", "sk"]),
        ("STOBE / Kenshi", STOBE_PHP_SMOKE, []),
    ]
    results: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    for name, script, args in targets:
        decoded, error, exit_code = run_php_smoke(script, args)
        item = {
            "target": name,
            "exit_code": exit_code,
            "result": decoded,
            "stderr": error,
        }
        results.append(item)
        if exit_code != 0 or not isinstance(decoded, dict) or not decoded.get("ok"):
            failures.append(item)

    if failures:
        return VerifyCheck("dwemer_sites", "fail", f"{len(failures)} site connector smoke test(s) failed", {"results": results})
    return VerifyCheck("dwemer_sites", "pass", "CHIM Skyrim VoiceID plus Dialectic/Stobe generic voice connector smoke tests wrote WAV files", {"results": results})


def shutil_which(command: str) -> str | None:
    try:
        result = subprocess.run(
            ["sh", "-lc", f"command -v {command}"],
            text=True,
            capture_output=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    value = result.stdout.strip()
    return value or None


def print_checks(checks: list[VerifyCheck]) -> None:
    print("OmniVoice DwemerDistro verification")
    print(f"Base: {BASE_DIR}")
    print("")
    for check in checks:
        marker = {"pass": "PASS", "warn": "WARN", "fail": "FAIL"}.get(check.status, check.status.upper())
        print(f"[{marker:4}] {check.name}: {check.detail}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run end-to-end OmniVoice component smoke verification.")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--language", default="", help="Language profile id or alias. Defaults to active language.")
    parser.add_argument("--port", type=int, default=8021)
    parser.add_argument("--json", type=Path, default=DEFAULT_REPORT, help="Write verification JSON report.")
    parser.add_argument("--write-library-report", action="store_true", help="Refresh reports/<language>/library_audit.json.")
    parser.add_argument("--skip-synthesis", action="store_true", help="Skip audio generation requests.")
    parser.add_argument("--with-sites", action="store_true", help="Also synthesize through CHIM, Dialectic, and Stobe PHP connector paths.")
    parser.add_argument(
        "--voice",
        action="append",
        default=[],
        help="VoiceID to synthesize. May be repeated. Defaults to provider fallbacks.",
    )
    args = parser.parse_args()

    try:
        language = resolve_profile(args.language, PROFILES_DIR, load_profiles(PROFILES_DIR)).id if args.language else active_language_id()
    except Exception as exc:
        checks = [VerifyCheck("active_language", "fail", f"{type(exc).__name__}: {exc}")]
        print_checks(checks)
        return 1

    checks: list[VerifyCheck] = []
    checks.append(check_doctor())
    service_check, _health, provider = check_service(args.base_url)
    checks.append(service_check)
    checks.append(check_bind_address(args.port))
    checks.append(check_voice_library(language, args.write_library_report))

    voices = [voice.strip() for voice in args.voice if voice.strip()]
    if not voices and provider:
        for key in ("fallback_male", "fallback_female"):
            value = str(provider.get(key) or "").strip()
            if value and value not in voices:
                voices.append(value)
        for generic in ("default_male", "default_female"):
            if generic not in voices:
                voices.append(generic)

    if voices and not args.skip_synthesis:
        checks.append(check_service_contract(args.base_url, language, voices[0]))
    elif not args.skip_synthesis:
        checks.append(VerifyCheck("service_contract", "fail", "no voice available for contract verification"))

    if not args.skip_synthesis:
        if voices:
            checks.append(check_synthesis(args.base_url, language, voices))
        else:
            checks.append(VerifyCheck("synthesis", "fail", "no fallback voices discovered"))
    if args.with_sites:
        checks.append(check_dwemer_service_ports())
        checks.append(check_dwemer_database_connectors())
        checks.append(check_dwemer_sites())

    report = {
        "generated_at_utc": utc_now(),
        "base_dir": str(BASE_DIR),
        "base_url": args.base_url,
        "language": language,
        "checks": [asdict(check) for check in checks],
    }
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print_checks(checks)
    if args.json:
        print("")
        print(f"Report: {args.json}")

    return 1 if any(check.failed for check in checks) else 0


if __name__ == "__main__":
    raise SystemExit(main())
