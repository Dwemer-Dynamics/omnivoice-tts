from __future__ import annotations

import ast
import contextlib
import io
import logging
import re
import time
import unittest
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace


SERVER_PATH = Path(__file__).resolve().parents[1] / "server.py"
TOP_LEVEL = {"normalize_voice_id", "SynthesisTarget", "tts_to_audio"}


class SwitchOnReleaseLock:
    """Runs a library switch once, right after the first release of runtime.lock."""

    def __init__(self, on_release) -> None:
        self.on_release = on_release

    def __enter__(self):
        return self

    def __exit__(self, *exc) -> None:
        hook, self.on_release = self.on_release, None
        if hook is not None:
            hook()


def load_server_code(namespace: dict) -> type:
    """Execute only the resolution and synthesis code from server.py."""
    tree = ast.parse(SERVER_PATH.read_text(encoding="utf-8"))
    nodes = [n for n in tree.body if getattr(n, "name", None) in TOP_LEVEL]
    for node in nodes:
        if isinstance(node, ast.FunctionDef):
            node.decorator_list = []  # drop @app.post routing
    state = next(n for n in tree.body if getattr(n, "name", None) == "RuntimeState")
    state.body = [n for n in state.body if getattr(n, "name", "").startswith("resolve_")]
    future = ast.parse("from __future__ import annotations").body
    module = ast.Module(body=future + nodes + [state], type_ignores=[])
    exec(compile(module, str(SERVER_PATH), "exec"), namespace)
    return namespace["RuntimeState"]


def library(language_id: str, voice_name: str):
    voice = SimpleNamespace(name=voice_name, reference_wav=Path(language_id, voice_name, "reference.wav"))
    language = SimpleNamespace(id=language_id, omnivoice_language=f"omni-{language_id}")
    return {voice_name: voice}, language


class SynthesisSnapshotTest(unittest.TestCase):
    def test_switch_after_resolution_keeps_sample_and_language_together(self) -> None:
        generated: list[dict] = []
        namespace = {
            "dataclass": dataclass,
            "Path": Path,
            "re": re,
            "HTTPException": Exception,
            "Response": lambda content, media_type, headers: SimpleNamespace(headers=headers),
            "get_or_create_prompt": lambda voice: voice.reference_wav,
            "generation_lock": contextlib.nullcontext(),
            "torch": SimpleNamespace(inference_mode=contextlib.nullcontext),
            "model": SimpleNamespace(generate=lambda **kw: generated.append(kw) or [b"pcm"]),
            "sf": SimpleNamespace(write=lambda buffer, data, *a, **k: buffer.write(data)),
            "runtime_generation_config": None,
            "sampling_rate": 24000,
            "io": io,
            "time": time,
            "log": logging.getLogger(__name__),
        }
        RuntimeState = load_server_code(namespace)

        runtime = RuntimeState()
        runtime.voices, runtime.active_language = library("aa", "malenord")
        runtime.default_voice = "malenord"
        runtime.voice_aliases = {"malenord": "malenord"}
        runtime.sync_voices_if_changed_unlocked = lambda: False

        def switch_library() -> None:
            # Same VoiceID exists in the new library, but with a different sample.
            runtime.voices, runtime.active_language = library("bb", "malenord")

        runtime.lock = SwitchOnReleaseLock(switch_library)
        namespace["runtime"] = runtime

        response = namespace["tts_to_audio"](SimpleNamespace(text="Hello.", speaker_wav="malenord", speed=1.0))

        self.assertEqual(runtime.active_language.id, "bb", "library switch did not run")
        sample = generated[0]["voice_clone_prompt"]
        header_language = response.headers["X-OmniVoice-Language"]
        self.assertEqual(response.headers["X-OmniVoice-Voice"], "malenord")
        self.assertEqual(sample.parts[0], header_language)
        self.assertEqual(generated[0]["language"], f"omni-{header_language}")


if __name__ == "__main__":
    unittest.main()
