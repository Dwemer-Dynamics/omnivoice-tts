import json
import tempfile
import unittest
from pathlib import Path

from voice_management import ProtectedVoiceError, delete_custom_voice, normalize_voice_id


class VoiceManagementTest(unittest.TestCase):
    def test_deletes_complete_custom_voice_directory(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            voice_dir = root / "en" / "sample"
            (voice_dir / "calibration").mkdir(parents=True)
            (voice_dir / "reference.wav").write_bytes(b"wav")
            (voice_dir / "calibration" / "result.json").write_text("{}", encoding="utf-8")
            (voice_dir / "voice.json").write_text(
                json.dumps({"custom_voice": True, "voice_origin": "tts_studio_upload"}),
                encoding="utf-8",
            )

            removed = delete_custom_voice(root, "en", "sample")

            self.assertIn("reference.wav", removed)
            self.assertIn("calibration/result.json", removed)
            self.assertFalse(voice_dir.exists())

    def test_protects_managed_library_voice(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            voice_dir = root / "en" / "sample"
            voice_dir.mkdir(parents=True)
            (voice_dir / "voice.json").write_text(
                json.dumps({"custom_voice": False}), encoding="utf-8"
            )

            with self.assertRaises(ProtectedVoiceError):
                delete_custom_voice(root, "en", "sample")
            self.assertTrue(voice_dir.exists())

    def test_rejects_path_traversal(self):
        with self.assertRaises(ValueError):
            normalize_voice_id("../sample")


if __name__ == "__main__":
    unittest.main()
