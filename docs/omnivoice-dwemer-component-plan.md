# Multilingual OmniVoice TTS DwemerDistro Component Plan

## Objective

Implement Multilingual OmniVoice TTS as a first-class optional DwemerDistro component.

The component must install and run inside the `DwemerAI4Skyrim3` WSL distro, expose a CHIM-compatible local TTS API on `127.0.0.1:8021`, integrate with the DwemerDistro launcher install/status/config flows, and support CHIM/Skyrim first while providing a credible path for Stobe/Kenshi and Dialectic/Fallout.

This plan is intentionally written as a milestone checklist. The final implementation is not complete until every milestone has either been implemented and verified, or explicitly documented as blocked by an external dependency such as repository permissions, licensing uncertainty, or model availability.

## Current Implementation Status

Implemented locally:

- `omnivoice-tts/` component source directory with Linux installer, config menu, startup script, CLI wrapper, runtime requirements, docs, and ignored data folders.
- User-facing DwemerDistro guide at `docs/omnivoice-tts-user-guide.md`.
- Release-readiness and licensing gate documentation at `docs/omnivoice-release-readiness.md`.
- Third-party notices draft at `omnivoice-tts/THIRD_PARTY_NOTICES.md`; it records current upstream signals but does not grant release approval.
- End-to-end `verify` smoke command that writes `diagnostics/verify_latest.json`.
- Temporary-directory `verify-lifecycle` command for installer, uninstall, and export safety checks.
- DwemerDistro startup support in `dwemerdistro/etc/start_env`, gated by `/home/dwemer/omnivoice-tts/start.sh`.
- DwemerDistro component config menu registration in `dwemerdistro/bin/conf_services`.
- Launcher install card and install command for `Dwemer-Dynamics/omnivoice-tts`.
- Launcher OmniVoice install card includes runtime status detail, configure action, and log action.
- Launcher voice-engine detection and apply routing for OmniVoice across CHIM/Skyrim, Stobe/Kenshi, and Dialectic/Fallout.
- Native Stobe `connector_type=omnivoice` routing through Stobe's local TTS provider core.
- OmniVoice server compatibility endpoints for `/speakers_list_extended` and `/set_tts_settings`.
- Language catalog commands expose 96 recommended OmniVoice+Whisper presets and can enable selected presets as editable JSON profiles.
- `conf.sh` exposes the 96-preset listing and preset-enable flow for launcher Configure users.
- The verifier now checks the runtime contract endpoints: `/speakers_list`, `/speakers_list_extended`, `/languages`, `/active_language`, `POST /active_language`, `POST /reload_voices`, `POST /set_tts_settings`, and trailing-slash `POST /tts_to_audio/`.
- The verifier also checks unknown-language JSON error responses and path-shaped `speaker_wav` values such as `/tmp/malenord.wav`, proving they are treated as VoiceIDs by basename rather than arbitrary file paths.
- `verify-lifecycle` checks the 96-preset language catalog, native preset enablement, placeholder preset safety, and calibration refusal while placeholder text remains.
- Lightweight CLI commands that work before the full audio stack is installed.

Verified locally:

- `python -m py_compile` passes for `omnivoice-tts/*.py`.
- `omnivoice_cli.py languages` and `omnivoice_cli.py voices --language all` run without full audio dependencies.
- `omnivoice_cli.py export --language sk` fails cleanly when no prepared language library exists.
- `ddistro_install.sh`, `conf.sh`, `conf_services`, and the LF-normalized `start_env` pass `bash -n`.
- `dotnet build DwemerDistro-Launcher/DwemerDistroLauncherWpf.sln --no-restore` succeeds with zero warnings and zero errors.
- WSL reports CUDA visibility through `nvidia-smi`.
- Live `DwemerAI4Skyrim3` currently has OmniVoice listening on `127.0.0.1:8021`.
- `/var/www/html/HerikaServer/data/voices` and `/var/www/html/StobeServer` exist in the live distro.
- Private GitHub staging repo `Dwemer-Dynamics/omnivoice-tts` exists and is populated. Keep it private until publication permission and model/tokenizer license review are complete.
- Upstream `k2-fsa/OmniVoice` exists on Hugging Face, and the pinned Python packages are currently discoverable by `pip index`.
- Local WSL install from the unpublished checkout succeeded at `/home/dwemer/omnivoice-tts`.
- OmniVoice venv dependency install completed and `python -m pip check` reported no broken requirements.
- `doctor` reports `ready` with CUDA, model cache, writable folders, CHIM source, active Slovak language, one prepared voice, and a healthy `/health` service.
- One CHIM VoiceID, `femalenord`, was imported from `/var/www/html/HerikaServer/data/voices`.
- `femalenord` calibrated successfully and audits as `runtime_ready=1` and `calibrated=1`.
- Service enablement through `start.sh` was verified. `start-gpu.sh` now uses `setsid -f` so the server survives the launcher shell.
- `conf.sh` disable removes `start.sh`; enable recreates it even when a healthy OmniVoice listener is already running.
- `start-gpu.sh` now treats an already healthy OmniVoice listener on `127.0.0.1:8021` as success, while still rejecting unrelated port conflicts.
- `/health`, `/speakers_list`, `/speakers_list_extended`, `/active_language`, `/provider_info`, missing-speaker fallback, and `/tts_to_audio` were verified on `127.0.0.1:8021`.
- `/tts_to_audio` returned `audio/wav` for a Slovak test sentence and wrote `/tmp/omnivoice-test.wav`.
- The running service is bound to `127.0.0.1:8021`, not `0.0.0.0`.
- `/speakers_list_extended` exposes per-voice `voice.json` metadata, language profile, calibration status, and custom voice flag.
- `/provider_info` exposes `honor_request_language=false`, configured male/female fallbacks, and the active 144-voice library.
- Missing female VoiceIDs fall back to `femalenord`; missing male VoiceIDs fall back to `malenord`.
- `/set_tts_settings` returns success as a compatibility-only endpoint.
- Export to Chatterbox copied `femalenord.wav` into `/home/dwemer/chatterbox/voices/` and wrote `.omnivoice-sk-export.json`.
- Temporary custom voice add through `omnivoice_cli.py add-custom-voice`, service reload, synthesis, and cleanup were verified.
- Full Slovak CHIM import completed: 144 valid source WAVs, 144 prepared/skipped successfully, 0 failed.
- Full Slovak CHIM build/calibration completed: 144 runtime-ready calibrated voices. The calibration report contains 143 `auto_accepted` voices and 1 `review_required` voice (`fslefemale1`, transcript score 0.842, overall 0.897).
- Service health after full build reports `voice_count=144`.
- Launcher OmniVoice install-card status probe was verified against live WSL state and returned: `Healthy`, `enabled; healthy; language sk; 144 voices; CUDA yes; NVIDIA GeForce RTX 4090; default femalenord`.
- Launcher OmniVoice card now exposes Configure (`/home/dwemer/omnivoice-tts/conf.sh`) and View Logs (`logs/server.log`) actions.
- Launcher apply script was executed with `omnivoice`; CHIM, Stobe, and Dialectic all reported applied.
- Compiled launcher `VoiceEngineService.ApplyVoiceEngineAsync("omnivoice")` was exercised from a temporary harness. It returned applied results for CHIM/Skyrim, Stobe/Kenshi, and Dialectic/Fallout after replacing PostgreSQL dollar-quoted `DO` blocks with plain SQL statements that are safe to pass through `wsl.exe`.
- Full `--with-sites` verification now confirms required DwemerDistro listeners are active for PostgreSQL `5432`, CHIM/HerikaServer `8081`, Minime/TXT2VEC `8082`, StobeServer `8083`, OmniVoice `8021`, Parakeet STT `8022`, and CHIM MCP `3100`.
- Read-only database checks confirmed:
  - CHIM `core_tts_connector`: `label=ddistro omnivoice`, `driver=xtts-fastapi`, `url=http://127.0.0.1:8021`, `voice_field=voiceid`, default profiles assigned `1/1`.
  - Dialectic `core_tts_connector`: `label=ddistro omnivoice`, `driver=xtts-fastapi`, `url=http://127.0.0.1:8021`, `voice_field=voiceid`, default profiles assigned `1/1`.
  - Stobe `core_tts_connector`: `name=OmniVoice Default`, `connector_type=omnivoice`, `base_url=http://127.0.0.1:8021`, `is_default=true`, profiles assigned `2/2`.
  - Full-library import/build commands refuse to run without explicit `--all`, `--voice`, or `--limit`.
- Stobe code-level TTS path now supports a native `omnivoice` provider. Its local-provider core posts `text`, `speaker_wav`, and `language` to `/tts_to_audio`, matching OmniVoice.
- Dialectic and CHIM `xtts-fastapi` connector paths were inspected and use the same compatible `/tts_to_audio` payload shape.
- First-run launcher setup source was inspected: the recommended presets install CUDA, Chatterbox or Pocket-TTS, Minime/TXT2VEC, and Parakeet only. OmniVoice is not part of the default first-run install presets; it remains an optional component plus a detectable/applicable voice engine when already installed.

Not verified yet:

- Fresh public-user install from GitHub, because the component repo is private until publication and license gates are resolved.
- Fresh public-user install directly from the launcher button, because the launcher command clones the GitHub repo and the repo must remain private until release gates are resolved.
- In-game CHIM, Stobe, and Dialectic speech playback, although the shared local API and database connector rows are verified.
- Public package release from GitHub/Nexus.

Release blockers:

- The submitted archive did not include an explicit license or publication permission. Do not publish a public repo or Nexus package until this is resolved with the original author.
- `Dwemer-Dynamics/omnivoice-tts` now exists as a private staging repo, but it must not be made public or used for public launcher installs until release gates are resolved.
- Upstream OmniVoice/model/dependency licenses must be reviewed before public release.
- Release-readiness details are recorded in `docs/omnivoice-release-readiness.md`.

## Non-Goals

- Do not merge OmniVoice into the existing XTTS runtime or reuse `/home/dwemer/python-tts`.
- Do not make OmniVoice a required first-run component.
- Do not silently install it as part of XTTS.
- Do not bundle downloaded models, generated voice libraries, Skyrim assets, CHIM data, or user-created voices in the repo.
- Do not expose the service on `0.0.0.0` unless a later remote-access feature explicitly requires it.

## Target Component Shape

The Linux component should install to:

```text
/home/dwemer/omnivoice-tts/
  venv/
  server.py
  ddistro_install.sh
  conf.sh
  start-gpu.sh
  start.sh
  config.json
  requirements_torch_cuda128.txt
  requirements_runtime.txt
  languages/
  voices/
  reports/
  logs/
  diagnostics/
```

`start.sh` is a symlink created by `conf.sh` when the service is enabled. Removing `start.sh` disables startup. This follows the existing XTTS, Chatterbox, and PocketTTS component pattern.

## Public Repo Decision

Create a separate public-ready repo unless an existing suitable repo is discovered:

```text
Dwemer-Dynamics/omnivoice-tts
```

Rationale:

- Existing DwemerDistro optional TTS engines are separate component repos.
- OmniVoice has its own dependency stack and should not destabilize XTTS, Chatterbox, or PocketTTS.
- A separate repo gives clean versioning, issue tracking, release packaging, and Nexus-facing documentation.
- The monorepo should only contain integration points and, optionally, a local development checkout.

Before public release:

- Confirm license compatibility for `omnivoice`, `k2-fsa/OmniVoice`, PyTorch wheels, Transformers, Whisper, WavLM, and any copied code from the submitted tool.
- Preserve attribution from the submitted tool where required.
- Remove all user-generated voices, reports, model caches, logs, and CHIM-derived data.

## Runtime Contract

The service must provide an XTTS-compatible API:

```text
GET  /health
GET  /provider_info
GET  /speakers_list
GET  /speakers_list_extended
GET  /languages
GET  /active_language
POST /active_language
POST /reload_voices
POST /set_tts_settings
POST /tts_to_audio
POST /tts_to_audio/
```

Required `/tts_to_audio` request body:

```json
{
  "text": "Line to speak",
  "speaker_wav": "VoiceID",
  "language": "sk"
}
```

Required behavior:

- Return `audio/wav` on success.
- Treat `speaker_wav` as a VoiceID, not as an arbitrary filesystem path.
- Use local prepared voice libraries under `voices/<language>/<VoiceID>/`.
- Use the active language as the default language.
- Either honor the request `language` when that language library exists, or document and expose the active-language-only behavior clearly in `/provider_info`.
- Return clear JSON errors for missing language, missing voice, missing CUDA, and unloaded model states.
- Provide fallback voices via config, for example `fallback_male` and `fallback_female`.
- Implement `/set_tts_settings` as either a real settings endpoint or a no-op compatibility endpoint that returns success.

## Milestone 1: Repo And Source Extraction

Deliverables:

- New repo or component source directory named `omnivoice-tts`.
- Linux-compatible source extracted from `Multilingual tool/Multilingual_TTS_Tool_Files`.
- Windows-only launchers, Tkinter GUI paths, WSL UNC discovery, and `.bat` dependencies removed from the core service path.
- Package contains no generated voice libraries, no model weights, no CHIM files, and no user logs.

Verification:

- `Get-ChildItem` or `find` shows no model cache, generated WAV libraries, CHIM voice source data, or large bundled binary assets.
- README states that models and voices are downloaded/generated locally by the user.
- License and attribution status is documented.

## Milestone 2: Linux Installer

Deliverables:

- `ddistro_install.sh` that runs as user `dwemer`.
- Creates `/home/dwemer/omnivoice-tts/venv`.
- Installs Torch CUDA requirements into the OmniVoice venv only.
- Installs runtime requirements into the OmniVoice venv only.
- Creates `voices`, `reports`, `logs`, and `diagnostics`.
- Runs a quick doctor check after install.
- Does not enable startup unless the user explicitly chooses to enable it.

Expected launcher command:

```text
wsl -d DwemerAI4Skyrim3 -u dwemer -- /home/dwemer/omnivoice-tts/ddistro_install.sh
```

Verification:

- Fresh install succeeds on the target WSL distro.
- Re-run is idempotent and updates or repairs the component.
- `venv/bin/python -m pip check` passes or known non-fatal conflicts are documented.
- Doctor output confirms Python, CUDA visibility, package imports, and writable data folders.

## Milestone 3: Service Enable/Disable

Deliverables:

- `conf.sh` with explicit options:
  - enable service
  - disable service
  - show status
  - select active language
  - import one CHIM VoiceID
  - calibrate one VoiceID
  - build full selected-language CHIM library
  - run doctor
  - run end-to-end verification smoke test
- `start-gpu.sh` binds to `127.0.0.1:8021`.
- `start.sh` symlink is created only when enabled.
- `logs/server.log` captures startup and runtime errors.

Verification:

- Enabling creates `/home/dwemer/omnivoice-tts/start.sh`.
- Disabling removes `/home/dwemer/omnivoice-tts/start.sh`.
- Running `start.sh` starts a listener on `127.0.0.1:8021`.
- `/health` returns success after startup.
- Disabled service is skipped by distro startup.

## Milestone 4: DwemerDistro Startup Integration

Deliverables:

- Add an OmniVoice startup block to `dwemerdistro/etc/start_env`.
- The block starts only when `/home/dwemer/omnivoice-tts/start.sh` exists.
- Startup output prints the OmniVoice URL only when the service is running.
- Failure does not prevent Apache, PostgreSQL, Minime, Parakeet, PocketTTS, Chatterbox, XTTS, or MCP startup.

Verification:

- With service disabled, distro startup prints a skip message and no `8021` listener exists.
- With service enabled, distro startup starts OmniVoice and `check_port 8021` passes.
- Existing service ports still work:
  - `8081` CHIM/HerikaServer
  - `8083` StobeServer
  - `8082` Minime
  - `8022` Parakeet
  - existing selected TTS engine port, if enabled

## Milestone 5: Voice Library Manager

Deliverables:

- CLI entrypoint, for example `omnivoice_cli.py`.
- Commands:
  - `doctor`
  - `verify`
  - `verify-lifecycle`
  - `languages`
  - `set-language`
  - `voices`
  - `import-chim`
  - `add-custom-voice`
  - `calibrate`
  - `build-library`
  - `export`
  - `server`
- Uses CHIM source path `/var/www/html/HerikaServer/data/voices` directly inside WSL.
- Supports safe single-voice pilot generation before full-library generation.
- Requires explicit `--all` for full voice library generation.
- Writes per-voice metadata and reports.

Verification:

- One CHIM VoiceID can be imported into `voices/<language>/<VoiceID>/`.
- One custom voice can be added without CHIM.
- One voice can be calibrated and promoted to active `reference.wav`.
- Full-library generation refuses to run without explicit `--all`.
- Report files identify completed, skipped, failed, and review-needed voices.

## Milestone 6: CHIM/Skyrim Integration

Deliverables:

- Launcher can apply OmniVoice to CHIM by creating or updating a `core_tts_connector` row.
- CHIM connector should use existing XTTS FastAPI driver:

```text
driver = xtts-fastapi
label = ddistro omnivoice
url = http://127.0.0.1:8021
voice_field = voiceid
metadata.language = selected language
metadata.voicelogic = voicetype
metadata.fallback_male = malenord
metadata.fallback_female = femalenord
```

- Profiles and player settings are updated consistently with the current `VoiceEngineService` behavior.
- CHIM should not require the existing XTTS service to be installed or enabled.

Verification:

- CHIM UI can see/select the connector.
- CHIM TTS test can synthesize via `http://127.0.0.1:8021/tts_to_audio`.
- NPC voice resolution passes a Skyrim VoiceID as `speaker_wav`.
- Missing speaker falls back predictably.
- Existing XTTS, Chatterbox, and PocketTTS connector apply still works.

## Milestone 7: Stobe/Kenshi Integration

Deliverables:

- Launcher can apply OmniVoice to Stobe.
```text
connector_type = omnivoice
name = OmniVoice Default
base_url = http://127.0.0.1:8021
config.language = selected language
config.fallback_male = default_male
config.fallback_female = default_female
```

- Stobe TTS normalization routes `connector_type = omnivoice` through the same local provider core as `xtts` and `chatterbox`.
- Stobe setup must include generic male/female default voices because Kenshi does not provide Skyrim VoiceIDs.

Verification:

- Stobe connector row is created and marked default when selected.
- Stobe TTS test sends `text`, `speaker_wav`, and `language` to `8021`.
- Generic fallback voice synthesis works.
- Per-character custom voices work when created.
- Existing Stobe `pocket_tts`, `xtts`, and `chatterbox` behavior does not regress.

## Milestone 8: Dialectic/Fallout Integration

Deliverables:

- Launcher can apply OmniVoice to Dialectic.
- Dialectic can use the Herika-style `xtts-fastapi` connector:

```text
driver = xtts-fastapi
label = ddistro omnivoice
url = http://127.0.0.1:8021
voice_field = voiceid
metadata.language = selected language
metadata.fallback_male = default_male
metadata.fallback_female = default_female
```

- Dialectic setup must provide generic default voices or custom voice import, because Fallout voice naming will not match Skyrim VoiceIDs.

Verification:

- Dialectic connector row is created and profiles are assigned.
- Dialectic TTS test synthesizes via `8021`.
- Generic fallback voice synthesis works.
- Per-character custom voices work when created.
- Existing Dialectic TTS connectors do not regress.

## Milestone 9: Launcher Integration

Deliverables:

- Add `Multilingual OmniVoice TTS` under Text-to-Speech Engines.
- Add install, configure, start/status, logs, and apply connector actions.
- Status checks:
  - installed
  - enabled
  - process/listener running
  - `/health` result
  - active language
  - prepared voice count
  - CUDA available
  - last install/server error
- Voice engine apply supports `omnivoice` for CHIM, Stobe, and Dialectic.
- First-run wizard does not select OmniVoice by default.
- Advanced path can expose OmniVoice as a recommended multilingual option.

Verification:

- Component card appears with correct status.
- Install button runs the Linux installer.
- Configure button opens `conf.sh` or a launcher-native flow.
- Apply connector button updates the right databases.
- Launcher quickstart paths for PocketTTS and Chatterbox still work.

## Milestone 10: Export To Other Engines

Deliverables:

- Optional export command that can copy or symlink active-language voice references into:

```text
/home/dwemer/chatterbox/voices/
/home/dwemer/pocket-tts/speakers/
/home/dwemer/xtts-api-server/speakers/
```

- Export must be explicit and reversible.
- Export should report unsupported or risky language/engine combinations.

Compatibility expectations:

- PocketTTS may benefit most because it has language/model switching.
- Chatterbox may use the WAV samples, but its current API treats `language` mostly as compatibility metadata.
- XTTS supports only its own language set and should not be described as 96-language capable.

Verification:

- Exported sample is visible in target engine `/speakers_list`.
- Target engine can synthesize with exported voice when the engine supports the selected language.
- Export does not overwrite existing custom voices without confirmation.

## Milestone 11: Diagnostics, Safety, And Updates

Deliverables:

- `doctor` command checks:
  - Python version
  - venv existence
  - package imports
  - CUDA availability
  - GPU name
  - port `8021`
  - model cache availability
  - writable folders
  - active language profile
  - prepared voice count
  - CHIM voice source presence
- Update path for repo and dependencies.
- Uninstall path that removes venv and service symlink but preserves user voice libraries unless explicitly requested.
- No LAN exposure by default.
- Clear failure messages for 4 GB VRAM uncertainty, missing CUDA, missing model access, and unsupported languages.

Verification:

- `doctor --json` emits machine-readable status for launcher consumption.
- Running uninstall preserves voices by default.
- Port conflict is detected before enabling service.
- Service binds only to `127.0.0.1`.

## Milestone 12: Documentation And Release

Deliverables:

- README for `omnivoice-tts`.
- DwemerDistro docs update.
- User guide:
  - install
  - enable/disable
  - select language
  - build one voice
  - build full CHIM library
  - add custom voice
  - apply connector
  - troubleshooting
  - hardware requirements
  - limitations
- Release notes.
- Public repo cleanup.

Verification:

- Docs match actual commands and paths.
- No docs claim all 96 languages are equally evaluated.
- Docs distinguish `96 presets` from fully quality-tested language support.
- Docs state NVIDIA CUDA requirement and recommended VRAM.

## End-To-End Acceptance Gates

The implementation is feature-ready only when all of these are true:

1. Clean WSL install succeeds from the launcher.
2. Service can be enabled and disabled without manual file edits.
3. Distro startup starts OmniVoice only when enabled.
4. `/health` works on `127.0.0.1:8021`.
5. One CHIM VoiceID can be imported, calibrated, listed, and synthesized.
6. Full CHIM library generation is available behind explicit confirmation.
7. CHIM can speak through the OmniVoice connector.
8. Stobe can either speak through OmniVoice or has a documented blocker with code-level reason.
9. Dialectic can either speak through OmniVoice or has a documented blocker with code-level reason.
10. Launcher status accurately reflects install, enablement, health, active language, and voice count.
11. Existing XTTS, Chatterbox, PocketTTS, Minime, Parakeet, CHIM, Stobe, and Dialectic startup behavior is not regressed.
12. No service binds to `0.0.0.0` by default.
13. No generated voices, model weights, CHIM data, or user logs are committed.
14. Tests or manual verification commands are recorded in the final implementation summary.

## Final Local Verification Record

Recorded on the local Windows/WSL development machine after the full Slovak build:

- `python -m py_compile` passed for every `omnivoice-tts/*.py` file.
- `bash -n` passed for `omnivoice-tts/ddistro_install.sh`, `omnivoice-tts/conf.sh`, `omnivoice-tts/start-gpu.sh`, and `dwemerdistro/bin/conf_services`.
- `dwemerdistro/etc/start_env` passed `bash -n` after LF normalization.
- `dotnet build DwemerDistro-Launcher/DwemerDistroLauncherWpf.sln --no-restore` succeeded with 0 warnings and 0 errors.
- Launcher install component cards support structured status detail. The OmniVoice card reports installed/enabled/health/active language/voice count/CUDA/GPU/default voice and provides Configure plus View Logs actions.
- Live WSL `/home/dwemer/omnivoice-tts` install passed `venv/bin/python -m pip check`.
- Live WSL `omnivoice_cli.py doctor --json` returned `recommendation=ready` with no bad checks.
- Live WSL `omnivoice_cli.py voices --language sk --write-report` returned `total=144 runtime_ready=144 calibrated=144 invalid_id=0 broken=0 warnings=0`.
- Live WSL `/health` returned `status=ok`, CUDA on `NVIDIA GeForce RTX 4090`, `voice_count=144`, and `default_voice=femalenord`.
- Live WSL `/tts_to_audio` returned `audio/wav` for exact `malenord`, missing female fallback, missing male fallback, and a temporary custom voice.
- Live WSL `/speakers_list_extended` returned 144 voices with `voice.json` metadata, language profile id, calibration status, and custom voice flag.
- Live WSL `/provider_info` returned 144 voices, `honor_request_language=false`, and configured fallbacks.
- Live WSL `/set_tts_settings` returned HTTP 200 JSON success as a compatibility no-op.
- Live WSL `conf.sh` disable/enable was exercised with piped menu input; disable removed `start.sh`, enable recreated it, and `start-gpu.sh` returned success while an already healthy listener was running.
- Live WSL PostgreSQL checks confirmed CHIM and Dialectic `ddistro omnivoice` connector rows use `xtts-fastapi` at `http://127.0.0.1:8021` with `voice_field=voiceid`.
- Live WSL PostgreSQL checks confirmed Stobe `OmniVoice Default` is default, uses `connector_type=omnivoice`, and points to `http://127.0.0.1:8021`.
- `git status --short --ignored -- omnivoice-tts` shows only the untracked source directory; ignored generated caches were removed from the local source tree.
- Source-package audit found no files larger than 5 MB and no generated voice, report, log, or diagnostic files under `omnivoice-tts`.
- `docs/omnivoice-tts-user-guide.md` covers install, configure, enable/disable, one-voice build, full library build, custom voices, connector apply, health checks, exports, hardware requirements, and limitations.
- `docs/omnivoice-release-readiness.md` records the submitted-tool permission gap, upstream OmniVoice model/tokenizer license concerns, runtime package license snapshot, and public launcher/repo release gates.
- `omnivoice-tts/THIRD_PARTY_NOTICES.md` records a public-repo preparation notice draft for submitted-tool permission, OmniVoice code/model/tokenizer signals, and the local runtime package snapshot.
- First-run setup source confirms OmniVoice is not selected by default: `DistroSetupService` presets reference only CUDA, Chatterbox or Pocket-TTS, Minime/TXT2VEC, and Parakeet, while OmniVoice is only detected by `VoiceEngineService` when present.

Verification refresh on July 8, 2026:

- `python -m py_compile` passed for every `omnivoice-tts/*.py` file.
- `bash -n` passed for `omnivoice-tts/ddistro_install.sh`, `omnivoice-tts/conf.sh`, `omnivoice-tts/start-gpu.sh`, and `dwemerdistro/bin/conf_services`.
- `dwemerdistro/etc/start_env` passed `bash -n` after LF normalization.
- `dotnet build DwemerDistro-Launcher/DwemerDistroLauncherWpf.sln --no-restore` succeeded with 0 warnings and 0 errors.
- Source audit found `LargeFileCount=0` and `GeneratedFileCount=0` under `omnivoice-tts`.
- Live WSL `/health` returned `status=ok`, `device=cuda:0`, `gpu=NVIDIA GeForce RTX 4090`, `voice_count=144`, `active_language=sk`, and `default_voice=femalenord`.
- Live WSL `doctor_cli.py --json /tmp/omnivoice-doctor-codex.json --quick` returned `Result: ready` with no bad checks.
- Live WSL `omnivoice_cli.py voices --language sk --write-report` returned `total=144 runtime_ready=144 calibrated=144 invalid_id=0 broken=0 warnings=0`.
- Live WSL `POST /tts_to_audio` with `speaker_wav=malenord` returned HTTP 200, `audio/wav`, and a 103724-byte WAV response.
- Native Stobe OmniVoice implementation was deployed to the local WSL runtime for verification. `core_tts_connector` readback returned `OmniVoice Default|omnivoice|http://127.0.0.1:8021|default|sk|default_male|default_female`.
- Stobe PHP `stobeSynthesizeTtsFromConnector()` with `connector_type=omnivoice` and `voiceOverride=default_male` returned `provider=omnivoice`, `audio_path=soundcache/e3a3bda0dc250a4055cddeffdbcb0540.wav`, `duration_ms=4750`, `cached=false`, and `ok=true`.
- Direct OmniVoice `default_female` fallback synthesis returned HTTP 200, `audio/wav`, and a 115724-byte WAV response.
- Live WSL `omnivoice_cli.py verify --language sk --write-library-report` passed and wrote `/home/dwemer/omnivoice-tts/diagnostics/verify_latest.json`. Checks passed: `doctor=ready`, service health `voice_count=144 default_voice=femalenord`, loopback-only `127.0.0.1:8021` listener, `total=144 runtime_ready=144 calibrated=144 invalid_id=0 broken=0 warnings=0`, XTTS-compatible service contract endpoints, and four WAV syntheses for `malenord`, `femalenord`, `default_male`, and `default_female`.
- Service contract verification covered `/speakers_list`, complete `/speakers_list_extended` metadata, `/languages`, `GET /active_language`, `POST /active_language`, unknown-language JSON error handling, `POST /reload_voices`, `POST /set_tts_settings`, trailing-slash `POST /tts_to_audio/`, and path-shaped `speaker_wav` VoiceID normalization.
- Live WSL `/speakers_list_extended` verification confirmed `malenord` exposes language profile `sk`, reference paths, metadata, and calibration status `auto_master_selected`.
- Live WSL `POST /active_language` with `zz_omnivoice_verify_missing` returned JSON 404 detail, and `POST /tts_to_audio` with `speaker_wav=/tmp/malenord.wav` returned HTTP 200 `audio/wav` with a 220844-byte WAV response.
- Live WSL `conf.sh` option 4 was verified with Windows-piped input. The menu strips Windows BOM/CR input, runs `omnivoice_cli.py verify --write-library-report`, returns to the menu, and exits cleanly.
- Live WSL `omnivoice_cli.py verify --language sk --write-library-report --with-sites --json diagnostics/verify_with_sites_latest.json` passed. Required service listener results:
  - PostgreSQL `5432`, CHIM/HerikaServer `8081`, Minime/TXT2VEC `8082`, StobeServer `8083`, OmniVoice `8021`, Parakeet STT `8022`, and CHIM MCP `3100` were listening.
- Site connector results:
  - Database `dwemer`: `9|xtts-fastapi|ddistro omnivoice|http://127.0.0.1:8021|voiceid|1|1|1|1`.
  - Database `dialectic`: `4|xtts-fastapi|ddistro omnivoice|http://127.0.0.1:8021|voiceid|1|1|1|1`.
  - Database `stobe`: `6|OmniVoice Default|omnivoice|http://127.0.0.1:8021|t|sk|default_male|default_female|2|2`.
  - CHIM/Skyrim `tts-xtts-fastapi.php` requested Skyrim VoiceID `malenord` and wrote `/var/www/html/HerikaServer/soundcache/4e6ed6b460d0207c2a748349b2f86ed6.wav` with `bytes=162798`, `riff=true`, and no stderr.
  - Dialectic/Fallout `tts-xtts-fastapi.php` requested generic VoiceID `default_male` and wrote `/var/www/html/DialecticServer/soundcache/5c3ac41e2e3190508a7b851039114931.wav` with `bytes=157038`, `riff=true`, and no stderr.
  - Stobe/Kenshi native `connector_type=omnivoice` wrote `/var/www/html/StobeServer/soundcache/6554c0d36b21933ac912f330aecb6808.wav` with `bytes=161324`, `riff=true`, `provider=omnivoice`, and no stderr.
- CHIM and Dialectic `tts-xtts-fastapi.php` now suppress false non-XTTS language warnings when the configured endpoint is OmniVoice on port `8021`; normal XTTS endpoints still use the existing language whitelist.
- Live WSL `omnivoice_cli.py verify-lifecycle` passed in temporary directories: `uninstall_preserves_voices`, `uninstall_remove_voices`, `installer_idempotent`, and `export_safety`.
- Live WSL `omnivoice_cli.py languages presets` reported `Recommended OmniVoice+Whisper profile presets: 96`.
- Live WSL `omnivoice_cli.py verify-lifecycle` passed the `language_catalog` check, covering 96-preset listing, `de` preset enablement, placeholder-preset refusal by default, explicit `haw --allow-placeholder` enablement, and calibration refusal until placeholder text is edited.
- `auto_calibrate_chim_voices.py` now lazy-loads Torch, Transformers, OmniVoice, librosa, and soundfile only after lightweight profile validation, so placeholder-profile safety checks do not allocate model/GPU resources.
- Live WSL scripted `conf.sh` smoke tests verified option 6 lists the 96-preset catalog and option 7 refuses the placeholder `haw` preset by default without creating `languages/haw.json`.
- Export lifecycle verification covers Chatterbox, PocketTTS, and XTTS target directory overrides, compatibility warnings in stderr and manifests, manifest creation, reruns of OmniVoice-owned files, refusal to overwrite unowned existing speaker WAVs, explicit `--force`, and zip export creation.
- `ddistro_install.sh` now supports test-only environment overrides `OMNIVOICE_BASE_DIR`, `OMNIVOICE_SKIP_DEPENDENCIES`, and `OMNIVOICE_SKIP_DOCTOR`; default user install behavior remains `/home/dwemer` with dependency install and doctor enabled.
- Public-repo preparation now includes `omnivoice-tts/THIRD_PARTY_NOTICES.md`, a non-release-approval draft covering submitted-tool permission, OmniVoice code/model/tokenizer signals checked on July 8, 2026, and the local runtime package snapshot.
- Live WSL controlled startup-gate verification passed: with `/home/dwemer/omnivoice-tts/start.sh` removed, `/etc/start_env` printed `Skipping OmniVoice TTS (not enabled)` and left port `8021` closed; after restoring `start.sh`, `/etc/start_env` printed `Starting OmniVoice TTS`, opened only `127.0.0.1:8021`, and `omnivoice_cli.py verify --language sk --with-sites --json diagnostics/verify_startup_gate_latest.json` passed.
- Compiled launcher `VoiceEngineService` verification passed from a temporary console harness: `GetStatusAsync` detected `engine=omnivoice`, and `ApplyVoiceEngineAsync("omnivoice")` returned `applied=True` for CHIM/Skyrim (`dwemer`), Stobe/Kenshi (`stobe`), and Dialectic/Fallout (`dialectic`). This caught and fixed a launcher-only SQL quoting bug where `DO $$` blocks were expanded before PostgreSQL saw them.
- Post-launcher-apply live verification passed with `omnivoice_cli.py verify --language sk --write-library-report --with-sites --json diagnostics/verify_launcher_apply_latest.json`; CHIM, Dialectic, and Stobe site smoke tests wrote valid WAV files through the OmniVoice connector after the compiled launcher apply path ran.
- Compiled launcher install-components card verification passed from a temporary STA WPF harness. The actual `InstallComponentsWindowViewModel` OmniVoice item reported `installed=True`, `status=Healthy`, `detail=enabled; healthy; language sk; 144 voices; CUDA yes; NVIDIA GeForce RTX 4090; default femalenord`, and exposed both Configure and View Logs actions.

Still blocked or not proven:

- Fresh public-user launcher install from GitHub is blocked because `Dwemer-Dynamics/omnivoice-tts` is intentionally private until publication permission and license review are resolved.
- Public release is blocked until original-author publication permission/license and upstream model/dependency license compatibility are confirmed.
- In-game CHIM, Stobe, and Dialectic playback is not proven in the games; the local API, connector rows, and PHP code paths are verified.
