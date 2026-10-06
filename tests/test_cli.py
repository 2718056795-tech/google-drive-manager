#!/usr/bin/env python3
import json, os, subprocess, tempfile, unittest
from pathlib import Path

CLI = Path(__file__).parents[1] / "scripts" / "gdrive.py"

class TestGoogleDriveCLI(unittest.TestCase):
    def test_help_lists_core_commands(self):
        p = subprocess.run(["python3", str(CLI), "--help"], text=True, capture_output=True)
        self.assertEqual(p.returncode, 0, p.stderr)
        for command in ("status", "list", "search", "mkdir", "upload", "upload-tree", "download", "delete"):
            self.assertIn(command, p.stdout)

    def test_delete_requires_yes_before_network(self):
        p = subprocess.run(["python3", str(CLI), "delete", "fake-id"], text=True, capture_output=True)
        self.assertNotEqual(p.returncode, 0)
        self.assertIn("--yes", p.stderr)

    def test_default_excludes_include_secrets(self):
        text = CLI.read_text(encoding="utf-8")
        for secret in ("auth_cookies.txt", "credentials.json", "token.json", "google_drive_service.json"):
            self.assertIn(secret, text)

if __name__ == "__main__":
    unittest.main(verbosity=2)
