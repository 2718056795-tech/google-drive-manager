#!/usr/bin/env python3
import importlib.util
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts' / 'backup_skills.py'
spec = importlib.util.spec_from_file_location('backup_skills', SCRIPT)
mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)


def main():
    cmd = mod.base_cmd('sync')
    assert cmd[:4] == ['rclone', 'sync', '/var/minis/skills', 'skillsdrive:']
    assert '--checksum' in cmd and '--local-no-check-updated' in cmd
    assert any('auth_cookies.txt' in x for x in mod.FILTERS)
    assert any('token.json' in x for x in mod.FILTERS)
    assert mod.REMOTE == 'skillsdrive:'
    print('PASS: direct expanded mirror command and secret filters')


if __name__ == '__main__':
    main()
