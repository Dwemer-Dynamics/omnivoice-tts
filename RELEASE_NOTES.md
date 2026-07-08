# OmniVoice TTS for DwemerDistro Release Notes

## 0.1.0-public-candidate

Initial DwemerDistro component candidate for Multilingual OmniVoice TTS.

Included:

- Linux/WSL installer for `/home/dwemer/omnivoice-tts`.
- Isolated Python virtual environment.
- Optional startup through `start.sh` symlink.
- FastAPI XTTS-compatible service on `127.0.0.1:8021`.
- CLI for doctor, language selection, CHIM import, custom voices, calibration, library audit, export, uninstall, and server startup.
- Language catalog commands for listing 96 recommended OmniVoice+Whisper presets and enabling selected presets as editable JSON profiles.
- `conf.sh` exposes the 96-preset listing and preset-enable flow for launcher Configure users.
- End-to-end `verify` command for doctor, service health, loopback binding, voice library audit, XTTS-compatible service contract checks, synthesis smoke checks, and optional DwemerDistro service listener/database/site connector checks.
- `verify-lifecycle` command for temporary-directory installer, uninstall, export safety, and engine compatibility-warning checks.
- `verify-lifecycle` also checks the language catalog flow: 96-preset listing, native preset enablement, placeholder-preset refusal by default, explicit placeholder enablement for editing, and calibration refusal while placeholder text remains.
- DwemerDistro launcher install card and connector apply support.
- CHIM/Dialectic Herika-style `xtts-fastapi` connector routing.
- Stobe native `omnivoice` connector routing through its local TTS provider core.

Known blockers before public release:

- The submitted source package needs explicit publication/license permission from the original author.
- Upstream OmniVoice/model/dependency license compatibility must be reviewed. The Python package/code currently report Apache-2.0, but the upstream pretrained model is currently documented as CC-BY-NC and tokenizer terms need review.
- `Dwemer-Dynamics/omnivoice-tts` exists as a private staging repo, but must remain private until publication permission and license review are complete.

Runtime verification completed in the local `DwemerAI4Skyrim3` distro:

- Local install from the unpublished checkout succeeded and `pip check` passed.
- CUDA/model load, `/health`, `/provider_info`, `/speakers_list`, `/speakers_list_extended`, `/set_tts_settings`, and `/tts_to_audio` were verified on `127.0.0.1:8021`.
- Full Slovak CHIM library import/build produced 144 runtime-ready calibrated voices; 143 auto-accepted and 1 was recorded in `AUTO_REVIEW_REQUIRED.txt`.
- `omnivoice_cli.py verify --language sk --write-library-report` passed against the live WSL runtime with doctor ready, 144 runtime-ready voices, loopback-only binding, and four successful fallback synthesis requests.
- `verify` now checks `/speakers_list`, complete `/speakers_list_extended` voice metadata, `/languages`, `/active_language`, `POST /active_language`, unknown-language JSON errors, `POST /reload_voices`, `POST /set_tts_settings`, trailing-slash `POST /tts_to_audio/`, and path-shaped `speaker_wav` VoiceID normalization.
- `omnivoice_cli.py verify --language sk --write-library-report --with-sites` passed against required DwemerDistro service listeners, live CHIM, Dialectic, and Stobe database connector rows/profile assignments, and PHP connector paths. CHIM wrote WAV with Skyrim VoiceID `malenord`; Dialectic and Stobe wrote WAV with generic `default_male` routing.
- `omnivoice_cli.py verify-lifecycle` passed in WSL, covering uninstall preservation, explicit voice removal, idempotent installer reruns, Chatterbox/PocketTTS/XTTS export manifests, engine compatibility warnings, overwrite refusal for unowned files, `--force`, and zip export.
- Exact VoiceID synthesis, missing male/female fallback synthesis, and temporary custom voice add/synthesize/cleanup were verified.
- The language catalog flow was verified through `verify-lifecycle`, including `languages presets` reporting 96 recommended presets.
- `conf.sh` scripted smoke tests verified option 6 lists the 96-preset catalog and option 7 refuses a placeholder preset by default without creating `haw.json`.
- `conf.sh` enable/disable and `start-gpu.sh` already-running behavior were verified.
- Launcher apply updated CHIM, Stobe, and Dialectic connector rows in the live WSL databases.

Still not verified:

- Fresh public-user install from the launcher/GitHub, because the repo is intentionally private until public-release gates are resolved.
- In-game CHIM, Stobe, and Dialectic playback.
