# OmniVoice TTS for DwemerDistro Release Notes

## 0.1.0-public-candidate

Initial DwemerDistro component candidate for Multilingual OmniVoice TTS.

Included:

- Linux/WSL installer for `/home/dwemer/omnivoice-tts`.
- Isolated Python virtual environment.
- Automatic DwemerDistro startup while the component is installed.
- FastAPI XTTS-compatible service on port `8021`, with LAN access enabled by
  the DwemerDistro startup script and loopback-only direct CLI startup by
  default.
- Active voice-library auto-sync on API requests after voice folders are added, updated, or removed.
- CLI for doctor, language selection, CHIM import, custom voices, calibration, library audit, export, uninstall, and server startup.
- Language catalog developer commands for listing recommended OmniVoice+Whisper presets and enabling selected presets as editable JSON profiles.
- `conf.sh` exposes installed-language selection, diagnostics, voice import/build workflows, exports, and uninstall for launcher Configure users.
- End-to-end `verify` command for doctor, service health, LAN or loopback
  binding, voice library audit, XTTS-compatible service contract checks,
  synthesis smoke checks, and optional DwemerDistro service
  listener/database/site connector checks.
- `verify-lifecycle` command for temporary-directory installer, uninstall, export safety, and engine compatibility-warning checks.
- `verify-lifecycle` also checks the language catalog developer flow: preset listing, native preset enablement, placeholder-preset refusal by default, explicit placeholder enablement for editing, and calibration refusal while placeholder text remains.
- DwemerDistro launcher install card and connector apply support.
- Local Apache web control panel published at `/OmniVoice/` during install when the web root is available.
- CHIM/Dialectic Herika-style `xtts-fastapi` connector routing.
- Stobe native `omnivoice` connector routing through its local TTS provider core.

Release constraints:

- ErikErix granted Dwemer Dynamics permission to publish and adapt the submitted Windows companion tool.
- This repository's component source is licensed under the MIT License.
- The MIT license applies to this repository's code and documentation only. It does not relicense downloaded third-party models, tokenizers, or Python packages.
- The Python package/code currently report Apache-2.0, but the upstream pretrained OmniVoice model is documented as CC-BY-NC and tokenizer terms are separate. Treat use of the downloaded pretrained model/tokenizer stack as non-commercial.

Runtime verification completed in the local `DwemerAI4Skyrim3` distro:

- Local install from the unpublished checkout succeeded and `pip check` passed.
- CUDA/model load, `/health`, `/provider_info`, `/speakers_list`, `/speakers_list_extended`, `/set_tts_settings`, and `/tts_to_audio` were verified on `127.0.0.1:8021`.
- Active-library auto-sync was verified by adding a temporary Spanish voice folder after startup, requesting `/speakers_list` and `/tts_to_audio` without calling `/reload_voices`, then removing it and confirming the speaker list updated again.
- Full Slovak CHIM library import/build produced 144 runtime-ready calibrated voices; 143 auto-accepted and 1 was recorded in `AUTO_REVIEW_REQUIRED.txt`.
- `omnivoice_cli.py verify --language sk --write-library-report` passed against the live WSL runtime with doctor ready, 144 runtime-ready voices, loopback-only binding, and four successful fallback synthesis requests.
- `verify` now checks `/speakers_list`, complete `/speakers_list_extended` voice metadata, `/languages`, `/active_language`, `POST /active_language`, unknown-language JSON errors, `POST /reload_voices`, `POST /set_tts_settings`, trailing-slash `POST /tts_to_audio/`, and path-shaped `speaker_wav` VoiceID normalization.
- `omnivoice_cli.py verify --language sk --write-library-report --with-sites` passed against required DwemerDistro service listeners, live CHIM, Dialectic, and Stobe database connector rows/profile assignments, and PHP connector paths. CHIM wrote WAV with Skyrim VoiceID `malenord`; Dialectic and Stobe wrote WAV with generic `default_male` routing.
- `omnivoice_cli.py verify-lifecycle` passed in WSL, covering uninstall preservation, explicit voice removal, idempotent installer reruns, Chatterbox/PocketTTS/XTTS export manifests, engine compatibility warnings, overwrite refusal for unowned files, `--force`, and zip export.
- Exact VoiceID synthesis, missing male/female fallback synthesis, and temporary custom voice add/synthesize/cleanup were verified.
- The language catalog flow was verified through `verify-lifecycle`, including `languages presets` reporting the expected recommended preset count.
- `conf.sh` scripted smoke tests verified installed-language listing and active-language selection prompts.
- `start-gpu.sh` already-running behavior was verified.
- Launcher apply updated CHIM, Stobe, and Dialectic connector rows in the live WSL databases.

Still not verified:

- Full clean launcher install with dependency download and post-install doctor.
- In-game CHIM, Stobe, and Dialectic playback.

Public repo verification completed:

- `Dwemer-Dynamics/omnivoice-tts` is public.
- Anonymous GitHub clone resolves `main`.
- Fresh public clone install dry-run passed with dependency and doctor skips, including idempotent rerun and executable script modes.
