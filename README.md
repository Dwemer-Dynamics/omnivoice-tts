# OmniVoice TTS for DwemerDistro

OmniVoice TTS is an optional DwemerDistro component that runs inside the
`DwemerAI4Skyrim3` WSL distro and exposes an XTTS-compatible local TTS API on
`127.0.0.1:8021`.

The component is intended to support multilingual CHIM voice libraries first,
with Stobe and Dialectic integration handled through their local TTS connector
systems.

## Scope

This repo does not include model weights, generated voice libraries, Skyrim
voices, CHIM files, user logs, or calibration reports. Those are downloaded or
generated on the user's machine.

## Install

From inside the distro as user `dwemer`:

```bash
cd /home/dwemer
git clone https://github.com/Dwemer-Dynamics/omnivoice-tts
cd /home/dwemer/omnivoice-tts
./ddistro_install.sh
```

The installer creates an isolated venv at:

```text
/home/dwemer/omnivoice-tts/venv
```

When the Apache web root is available, the installer also publishes the local
web control panel at:

```text
http://127.0.0.1/OmniVoice/
```

Do not install these dependencies into XTTS' `/home/dwemer/python-tts` venv.

## Enable Or Disable

Run:

```bash
/home/dwemer/omnivoice-tts/conf.sh
```

The service is enabled by creating:

```text
/home/dwemer/omnivoice-tts/start.sh
```

and disabled by removing that symlink. DwemerDistro startup should only start
OmniVoice when `start.sh` exists.

The menu also exposes language preset listing and preset enablement, including
the 96 recommended OmniVoice+Whisper presets. The same main workflows are
available in the browser control panel.

## Service

Start manually:

```bash
/home/dwemer/omnivoice-tts/start-gpu.sh
```

Health check:

```bash
curl http://127.0.0.1:8021/health
```

TTS endpoint:

```text
POST http://127.0.0.1:8021/tts_to_audio
```

Expected JSON:

```json
{
  "text": "Hello.",
  "speaker_wav": "malenord",
  "language": "sk"
}
```

## CLI

Use the wrapper:

```bash
source /home/dwemer/omnivoice-tts/venv/bin/activate
python omnivoice_cli.py doctor
python omnivoice_cli.py languages
python omnivoice_cli.py languages presets
python omnivoice_cli.py languages enable-preset de
python omnivoice_cli.py languages enable-preset haw --allow-placeholder
python omnivoice_cli.py set-language sk
python omnivoice_cli.py import-chim --language sk --voice malenord
python omnivoice_cli.py add-custom-voice --language sk --voice my_custom_voice --wav /path/to/reference.wav --text "Exact spoken reference text."
python omnivoice_cli.py calibrate --language sk --voice malenord
python omnivoice_cli.py voices --language sk
python omnivoice_cli.py verify --language sk --write-library-report
python omnivoice_cli.py verify-lifecycle
python omnivoice_cli.py export --language sk
```

Full CHIM library generation requires explicit confirmation:

```bash
python omnivoice_cli.py import-chim --language sk --all
python omnivoice_cli.py build-library --language sk --all
```

The enabled `languages/*.json` profiles are the active, buildable profile set.
`languages presets` lists the 96 recommended OmniVoice+Whisper presets from the
catalog. `languages enable-preset <id>` creates an enabled JSON profile from the
catalog. Presets without native calibration samples require `--allow-placeholder`
and must be edited before import/build; calibration refuses profiles that still
contain `REPLACE THIS` placeholder text.

Export prepared reference WAVs to another local TTS engine:

```bash
python omnivoice_cli.py export --language sk --target chatterbox --voice malenord
python omnivoice_cli.py export --language sk --target pockettts --all
python omnivoice_cli.py export --language sk --target xtts --all
```

Engine exports refuse to overwrite existing speaker WAVs unless `--force` is
used. Each export writes a `.omnivoice-<language>-export.json` manifest in the
target speaker directory so the exported files can be identified and removed.
Engine exports also print and record compatibility warnings when the target
engine should not be treated as having OmniVoice's full language coverage.

Remove the runtime without deleting generated voices:

```bash
python omnivoice_cli.py uninstall --yes
```

The `verify` command is the release/smoke-test entrypoint. It runs doctor,
checks `/health` and `/provider_info`, confirms the service is loopback-bound,
audits the selected language library, verifies the XTTS-compatible service
contract endpoints and extended speaker metadata, and synthesizes fallback
voices. It writes `diagnostics/verify_latest.json` by default.

For a full DwemerDistro connector check, add site synthesis:

```bash
python omnivoice_cli.py verify --language sk --write-library-report --with-sites --json diagnostics/verify_with_sites_latest.json
```

`--with-sites` also verifies required DwemerDistro service ports are listening,
checks that CHIM/Skyrim, Dialectic/Fallout, and Stobe/Kenshi database connector
rows and profile assignments point at OmniVoice, then confirms their PHP
connector paths write valid WAV files through OmniVoice. CHIM is tested with a
Skyrim VoiceID; Dialectic and Stobe are tested with generic `default_male` voice
routing.

`verify-lifecycle` checks installer reruns, uninstall behavior, and export
overwrite safety in temporary directories. It does not remove the live runtime or
write into the real Chatterbox, PocketTTS, or XTTS speaker folders.

## CHIM Connector

CHIM can use the existing XTTS FastAPI connector:

```text
driver = xtts-fastapi
url = http://127.0.0.1:8021
voice_field = voiceid
```

OmniVoice does not require the old XTTS service to be installed or enabled.

Missing VoiceIDs fall back through `config.json`:

```json
{
  "fallback_male": "malenord",
  "fallback_female": "femalenord"
}
```

The service stays active-language-only for now. `/provider_info` exposes
`honor_request_language=false` so clients know to switch language libraries via
`/active_language` rather than per-request language selection.

`speaker_wav` is normalized as a VoiceID. Path-shaped values such as
`/tmp/malenord.wav` resolve by basename and do not cause the service to read an
arbitrary file path.

## Current Limitations

- NVIDIA CUDA is required for the OmniVoice runtime.
- The component is designed for local WSL use and binds to `127.0.0.1`.
- Language profiles are presets. Not every preset has been quality evaluated.
- Stobe and Dialectic need generic/custom voice setup because their voice IDs
  do not map directly to Skyrim VoiceIDs.

## License And Attribution

This component is derived from the submitted "Multilingual 96-Language TTS Tool
v1.1" Windows package by ErikErix. ErikErix granted Dwemer Dynamics permission
to publish and adapt the submitted tool as this component.

Original tool author credit:

- Discord: ErikErix
- NexusMods: erikholik

This repository's component source and documentation are licensed under the MIT
License. See `LICENSE`.

The MIT license applies to this repository's code only. It does not relicense
downloaded third-party models, tokenizers, or Python packages.

The installed `omnivoice` Python package and the upstream `k2-fsa/OmniVoice`
code currently report Apache-2.0, but the upstream Hugging Face model page
states that the pretrained model is CC-BY-NC, and the tokenizer has separate
license terms. Treat use of the downloaded pretrained OmniVoice model/tokenizer
stack as non-commercial.

See `THIRD_PARTY_NOTICES.md` for attribution and upstream notices.

This repo must continue to exclude model weights, generated voice libraries,
Skyrim assets, CHIM files, logs, diagnostics, and user-created voices.
