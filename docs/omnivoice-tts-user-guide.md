# OmniVoice TTS For DwemerDistro

OmniVoice TTS is an optional DwemerDistro component for multilingual local TTS.
It runs inside `DwemerAI4Skyrim3` as user `dwemer` and serves an
XTTS-compatible API on `127.0.0.1:8021`.

The component does not include model weights, generated voice libraries, Skyrim
voice files, CHIM files, logs, or user-created voices. Those are downloaded or
generated locally on the user's PC.

## Requirements

- Windows host with the `DwemerAI4Skyrim3` WSL distro installed.
- NVIDIA CUDA-capable GPU.
- RTX 20-series or newer recommended.
- 8 GB VRAM recommended. 4 GB VRAM is not yet verified.
- Python inside WSL.

## Install

From the DwemerDistro launcher, open Install Components and install
`Multilingual OmniVoice TTS`.

Manual WSL install:

```bash
cd /home/dwemer
git clone https://github.com/Dwemer-Dynamics/omnivoice-tts omnivoice-tts
cd /home/dwemer/omnivoice-tts
./ddistro_install.sh
```

The installer creates an isolated virtual environment at:

```text
/home/dwemer/omnivoice-tts/venv
```

When the Apache web root is available, the installer also publishes the browser
control panel at:

```text
http://127.0.0.1/OmniVoice/
```

Do not install OmniVoice packages into XTTS, Chatterbox, or PocketTTS venvs.

## Configure

Open the configuration menu:

```bash
/home/dwemer/omnivoice-tts/conf.sh
```

The menu can:

- Enable or disable the service.
- Open the same workflows that are available in the browser control panel.
- Show doctor/status.
- Run the verification smoke test.
- List languages.
- List the 96 recommended language presets.
- Enable a language preset as an editable JSON profile.
- Set the active language.
- Import one CHIM VoiceID.
- Calibrate one VoiceID.
- Build the full selected-language CHIM library.
- Export prepared voices to another local TTS engine.
- Uninstall the runtime while preserving voices by default.

## Enable Or Disable Startup

Enabling creates:

```text
/home/dwemer/omnivoice-tts/start.sh
```

Disabling removes that symlink. DwemerDistro startup only starts OmniVoice when
`start.sh` exists.

## Build One CHIM Voice

```bash
cd /home/dwemer/omnivoice-tts
source venv/bin/activate
python omnivoice_cli.py import-chim --language sk --voice femalenord
python omnivoice_cli.py calibrate --language sk --voice femalenord
python omnivoice_cli.py voices --language sk --write-report
```

## Enable Another Language Preset

The active JSON profiles live in:

```text
/home/dwemer/omnivoice-tts/languages/
```

List the 96 recommended OmniVoice+Whisper presets:

```bash
python omnivoice_cli.py languages presets
```

Enable a preset with native calibration samples:

```bash
python omnivoice_cli.py languages enable-preset de
```

Some presets are included as editable templates with placeholder calibration
sentences. They require an explicit flag and must be edited before building
voices:

```bash
python omnivoice_cli.py languages enable-preset haw --allow-placeholder
```

Calibration refuses profiles that still contain `REPLACE THIS` placeholder text.

The same preset listing and enablement actions are available from
`/home/dwemer/omnivoice-tts/conf.sh`.

## Build A Full CHIM Library

Full-library work is explicit because it can take a long time and uses CUDA
heavily:

```bash
cd /home/dwemer/omnivoice-tts
source venv/bin/activate
python omnivoice_cli.py import-chim --language sk --all
python omnivoice_cli.py build-library --language sk --all
python omnivoice_cli.py voices --language sk --write-report
```

Review reports are written under:

```text
/home/dwemer/omnivoice-tts/reports/<language>/
```

`AUTO_REVIEW_REQUIRED.txt` lists voices that generated successfully but need
human listening review.

## Add A Custom Voice

Use a clean WAV/FLAC/MP3/OGG reference sample and provide the exact spoken text
when possible:

```bash
cd /home/dwemer/omnivoice-tts
source venv/bin/activate
python omnivoice_cli.py add-custom-voice \
  --language sk \
  --voice my_custom_voice \
  --wav /path/to/reference.wav \
  --text "Exact words spoken in the reference audio."
python omnivoice_cli.py calibrate --language sk --voice my_custom_voice
```

## Apply To CHIM, Stobe, Or Dialectic

Use the DwemerDistro first-run or voice-engine setup flow and select
`Multilingual OmniVoice`.

The launcher applies:

- CHIM/Skyrim: `xtts-fastapi` connector at `http://127.0.0.1:8021`.
- Dialectic/Fallout: `xtts-fastapi` connector at `http://127.0.0.1:8021`.
- Stobe/Kenshi: native `omnivoice` local-provider connector at
  `http://127.0.0.1:8021`, with generic `default_male` and `default_female`
  fallback VoiceIDs.

OmniVoice does not require the old XTTS service to be installed or running.

## Health Checks

```bash
curl http://127.0.0.1:8021/health
curl http://127.0.0.1:8021/provider_info
cd /home/dwemer/omnivoice-tts
source venv/bin/activate
python omnivoice_cli.py doctor --json diagnostics/latest.json
python omnivoice_cli.py verify --language sk --write-library-report
python omnivoice_cli.py verify --language sk --write-library-report --with-sites --json diagnostics/verify_with_sites_latest.json
python omnivoice_cli.py verify-lifecycle
```

Expected service binding is `127.0.0.1:8021`. The service should not bind to
`0.0.0.0` by default.

`verify` is the practical smoke test before release or support triage. It writes
`diagnostics/verify_latest.json` and checks doctor, service health,
`/provider_info`, loopback binding, selected-language voice audit,
XTTS-compatible service contract endpoints, extended speaker metadata, and
fallback voice synthesis.

Use `--with-sites` for a full DwemerDistro check. It validates the live
required DwemerDistro service listeners, CHIM/Skyrim, Dialectic/Fallout, and
Stobe/Kenshi database connector rows and profile assignments, then calls each
PHP connector path and verifies that each one writes a valid WAV through
OmniVoice. CHIM is tested with a Skyrim VoiceID; Dialectic and Stobe are tested
with generic `default_male` voice routing.

The verifier also confirms that path-shaped `speaker_wav` values are treated as
VoiceIDs by basename and that unknown language switches return JSON errors.

Use `verify-lifecycle` before packaging changes to the installer, uninstall, or
export flow. It creates temporary component copies and verifies that installer
reruns are idempotent, uninstall preserves voice libraries unless
`--remove-voices` is explicitly used, and engine exports refuse to overwrite
unowned speaker WAVs unless `--force` is used.

## Export To Other Engines

Exports are explicit and refuse to overwrite unrelated files unless `--force`
is supplied:

```bash
python omnivoice_cli.py export --language sk --target chatterbox --voice femalenord
python omnivoice_cli.py export --language sk --target pockettts --all
python omnivoice_cli.py export --language sk --target xtts --all
```

Each export writes a `.omnivoice-<language>-export.json` manifest in the target
speaker directory. Engine exports also print and record compatibility warnings
when the selected target should not be treated as having OmniVoice's full
language coverage.

## Limitations

- Language profiles are presets, not equal-quality guarantees.
- Slovak and Czech have had deeper quality review than most presets.
- The runtime is active-language-only. `/provider_info` reports
  `honor_request_language=false`.
- Chatterbox and XTTS exports are compatibility conveniences; they do not make
  those engines 96-language OmniVoice engines.
- Public release requires original-author publication permission and dependency
  license review.
