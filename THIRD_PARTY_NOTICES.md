# Third-Party Notices

This file records source attribution and upstream runtime/model notices for the
optional DwemerDistro OmniVoice TTS component.

The component source in this repository is licensed under the MIT License. The
MIT license applies to this repository's code and documentation only. It does
not relicense downloaded third-party models, tokenizers, or Python packages.

## Submitted Companion Tool

The component is derived from the submitted "Multilingual 96-Language TTS Tool
for CHIM v1.1.0 CustomVoices" package.

Current status:

- ErikErix granted Dwemer Dynamics permission to publish and adapt the
  submitted tool as this DwemerDistro component.
- Attribution: original submitted Windows companion tool by ErikErix.
- Dwemer Dynamics publishes this adapted component source under the MIT License.

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

- Treat this component as non-commercial when used with the downloaded
  pretrained OmniVoice model/tokenizer stack.
- Do not claim commercial-use compatibility for the downloaded pretrained model
  or tokenizer.
- The installer downloads models onto the user's machine; those upstream terms
  continue to apply independently from this repository's MIT source license.

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
