from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

import omnivoice_cli
import verify_cli


class ServerBindingTests(unittest.TestCase):
    def test_dwemer_startup_enables_lan_binding(self) -> None:
        startup = (REPO_ROOT / "start-gpu.sh").read_text(encoding="utf-8")

        self.assertIn("server --listen --port 8021", startup)

    def test_direct_cli_defaults_to_loopback(self) -> None:
        args = omnivoice_cli.build_parser().parse_args(["server"])

        self.assertEqual(omnivoice_cli.resolve_server_host(args), "127.0.0.1")

    def test_listen_flag_enables_lan_binding(self) -> None:
        args = omnivoice_cli.build_parser().parse_args(["server", "--listen"])

        self.assertEqual(omnivoice_cli.resolve_server_host(args), "0.0.0.0")

    def test_explicit_host_is_preserved_without_listen(self) -> None:
        args = omnivoice_cli.build_parser().parse_args(["server", "--host", "192.168.1.20"])

        self.assertEqual(omnivoice_cli.resolve_server_host(args), "192.168.1.20")

    @mock.patch("omnivoice_cli.subprocess.call", return_value=0)
    def test_server_command_forwards_lan_host_to_uvicorn(self, call: mock.Mock) -> None:
        args = omnivoice_cli.build_parser().parse_args(["server", "--listen", "--port", "8121"])

        result = omnivoice_cli.command_server(args)

        self.assertEqual(result, 0)
        command = call.call_args.args[0]
        self.assertEqual(command[command.index("--host") + 1], "0.0.0.0")
        self.assertEqual(command[command.index("--port") + 1], "8121")

    @mock.patch("verify_cli.subprocess.run")
    def test_verify_accepts_wildcard_listener(self, run: mock.Mock) -> None:
        run.return_value = subprocess.CompletedProcess(
            args=["ss", "-H", "-ltn"],
            returncode=0,
            stdout="LISTEN 0 2048 0.0.0.0:8021 0.0.0.0:*\n",
            stderr="",
        )

        result = verify_cli.check_bind_address(8021)

        self.assertEqual(result.status, "pass")
        self.assertEqual(result.detail, "LAN listener enabled")

    @mock.patch("verify_cli.subprocess.run")
    def test_verify_accepts_loopback_listener(self, run: mock.Mock) -> None:
        run.return_value = subprocess.CompletedProcess(
            args=["ss", "-H", "-ltn"],
            returncode=0,
            stdout="LISTEN 0 2048 127.0.0.1:8021 0.0.0.0:*\n",
            stderr="",
        )

        result = verify_cli.check_bind_address(8021)

        self.assertEqual(result.status, "pass")
        self.assertEqual(result.detail, "loopback listener only")


if __name__ == "__main__":
    unittest.main()
