# OmniVoice DwemerDistro Release Readiness

This document records the current release-readiness state for the optional
DwemerDistro OmniVoice TTS component.

## Current Decision

Local DwemerDistro integration can continue, and the component source can be
published under MIT with ErikErix attribution. Public release must clearly state
that downloaded pretrained OmniVoice model/tokenizer use is non-commercial.

Before a public launcher/Nexus release, verify a fresh GitHub install and keep
the non-commercial model/tokenizer terms visible in user-facing docs.

## Local Submitted Tool

Reviewed local package:

```text
Multilingual tool/
```

Observed:

- `00_READ_ME_FIRST.txt` describes the Windows companion tool, runtime behavior,
  local voice generation, CHIM endpoint, custom voices, uninstall behavior, and
  the fact that generated voices are local.
- No file matching license, licence, notice, copying, credit, attribution, or
  similar publication terms was found under the submitted package.

Resolved publication status:

- ErikErix granted Dwemer Dynamics permission to publish and adapt the submitted
  tool as this component.
- Attribution is recorded in `README.md` and `THIRD_PARTY_NOTICES.md`.
- The component source is published under the MIT License.

Previously tracked in the private staging repo as
`Dwemer-Dynamics/omnivoice-tts#1`.

## Upstream OmniVoice

Relevant upstream sources checked on July 8, 2026:

- Hugging Face model page: `https://huggingface.co/k2-fsa/OmniVoice`
- GitHub repo: `https://github.com/k2-fsa/OmniVoice`
- GitHub license file: `https://github.com/k2-fsa/OmniVoice/blob/master/LICENSE`
- Hugging Face tokenizer-license discussion:
  `https://huggingface.co/k2-fsa/OmniVoice/discussions/1`

Current upstream signal:

- The installed `omnivoice` Python package reports `License-Expression:
  Apache-2.0`.
- The GitHub license file is Apache License 2.0.
- The Hugging Face model page states that project code is Apache 2.0, while the
  pretrained model is CC-BY-NC due to training-data constraints.
- A Hugging Face discussion records that the Higgs Audio tokenizer has a
  separate non-Apache license and that its license was added upstream.

Release implication:

- This component can be released as a non-commercial local optional component.
- Do not market the downloaded pretrained model/tokenizer stack as commercially
  usable.
- Public docs must distinguish this repository's MIT source license from the
  downloaded pretrained model/tokenizer terms.

Previously tracked in the private staging repo as
`Dwemer-Dynamics/omnivoice-tts#2`.

## Runtime Package Snapshot

Checked inside the live WSL venv at `/home/dwemer/omnivoice-tts/venv`:

```text
omnivoice 0.1.5: Apache-2.0
torch 2.8.0+cu128: BSD-3-Clause
transformers 5.3.0: Apache 2.0 License
huggingface_hub 1.22.0: Apache-2.0
librosa 0.11.0: ISC
soundfile 0.14.0: BSD 3-Clause License
fastapi 0.139.0: MIT
uvicorn 0.50.2: BSD-3-Clause
pydantic 2.13.4: MIT
```

This package snapshot is not a full dependency legal audit. It is enough to show
that the obvious Python runtime packages are not the main blocker; the submitted
tool permission and upstream pretrained-model/tokenizer terms are.

## Repo Readiness Checklist

Private staging status:

- `Dwemer-Dynamics/omnivoice-tts` exists as a private GitHub repo.
- The private staging repo is populated on `main`.
- The repo contains component source, docs, release-readiness notes, and empty
  runtime directories via `.gitkeep`.
- The repo does not contain generated voices, CHIM source WAVs, model weights,
  model cache, diagnostics, reports, or logs.

Before making or keeping `Dwemer-Dynamics/omnivoice-tts` public:

- Include the MIT `LICENSE`.
- Add `THIRD_PARTY_NOTICES.md` covering OmniVoice, tokenizer/model terms, and
  material runtime dependencies.
- Add `README.md` language that clearly distinguishes code license from model
  license.
- Add `RELEASE_NOTES.md`.
- Keep generated voices, CHIM source WAVs, model weights, model cache,
  diagnostics, reports, and logs out of git.
- Confirm `ddistro_install.sh` downloads dependencies at install time and does
  not bundle restricted model files.
- Confirm docs say "96 presets" or "many language presets" rather than implying
  every language has been quality-evaluated.

## Launcher Release Gate

The launcher can keep the optional install/config/status UI locally, but a public
launcher release should not expose a working install button until:

- The repo has license and third-party notice files.
- Author publication permission is recorded.
- Non-commercial model/tokenizer terms are reflected in user-facing docs.
- Fresh launcher/GitHub install has been verified.

Tracked in the staging repo as
`Dwemer-Dynamics/omnivoice-tts#3`.
