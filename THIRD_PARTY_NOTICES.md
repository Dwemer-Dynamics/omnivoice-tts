# Third-Party Notices Draft

This file is a release-preparation draft for the optional DwemerDistro
OmniVoice TTS component. It is not legal approval to publish the component.

Do not publish a public repository, Nexus package, or launcher release that
installs this component until the submitted-tool author has granted explicit
publication permission and Dwemer Dynamics has completed a model/tokenizer
license review.

## Submitted Companion Tool

The component is derived from the submitted "Multilingual 96-Language TTS Tool
for CHIM v1.1.0 CustomVoices" package.

Current status:

- The submitted package did not include a license file or publication terms.
- Written permission is required before publishing adapted source.
- Any author-requested attribution must be added here before release.

## OmniVoice

Upstream project:

- GitHub: `https://github.com/k2-fsa/OmniVoice`
- Hugging Face model: `https://huggingface.co/k2-fsa/OmniVoice`

Current upstream signal checked on July 8, 2026:

- The GitHub repository license is Apache License 2.0.
- The Hugging Face model page states the project code is Apache 2.0.
- The Hugging Face model page states the pretrained model is CC-BY-NC due to
  training-data constraints.
- The Hugging Face tokenizer licensing discussion says the Higgs Audio
  tokenizer is not Apache 2.0 and that its license was added upstream.

Release implication:

- This DwemerDistro component must not claim commercial-use compatibility until
  the pretrained model and tokenizer terms are reviewed.
- If the component remains a code-only installer that downloads models onto the
  user's machine, the release notes and README still need to disclose model and
  tokenizer terms clearly.

## Runtime Dependencies

The installer downloads Python packages into
`/home/dwemer/omnivoice-tts/venv` at install time. The repository must not
bundle downloaded wheels, model weights, tokenizer assets, generated voices,
CHIM voice files, logs, reports, or diagnostics.

Runtime package snapshot from the local WSL venv:

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

This snapshot is not a complete transitive dependency audit.
