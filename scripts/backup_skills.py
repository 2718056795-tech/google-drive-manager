#!/usr/bin/env python3
"""Mirror /var/minis/skills directly to Google Drive in the same directory layout."""
import argparse, json, os, shutil, subprocess, sys, tempfile
from pathlib import Path

SOURCE = Path('/var/minis/skills')
CONFIG_DIR = Path('/root/.config/minis-google-drive')
TOKEN_FILE = CONFIG_DIR / 'token.json'
RCLONE_CONFIG = CONFIG_DIR / 'rclone.conf'
FILTER_FILE = CONFIG_DIR / 'skills-filter.txt'
REMOTE = 'skillsdrive:'
FOLDER_ID = '1fFUem6aSMyf9HBxG9RMmlyCQONtFkBrZ'
FILTERS = [
    '- **/.git/**', '- **/__pycache__/**', '- **/node_modules/**',
    '- **/auth_cookies.txt', '- **/credentials.json', '- **/token.json',
    '- **/google_drive_service.json', '- **/.DS_Store', '+ **',
]


def die(message, code=2):
    print(json.dumps({'ok': False, 'error': message}, ensure_ascii=False), file=sys.stderr)
    raise SystemExit(code)


def ensure_runtime():
    if not shutil.which('rclone'):
        die('缺少 rclone；请先运行 apk add rclone')
    if not TOKEN_FILE.is_file():
        die(f'未找到 Google Drive OAuth token: {TOKEN_FILE}')
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    token_data = json.loads(TOKEN_FILE.read_text(encoding='utf-8'))
    token = {
        'access_token': token_data['token'], 'token_type': 'Bearer',
        'refresh_token': token_data['refresh_token'], 'expiry': token_data['expiry'],
    }
    config = '[skillsdrive]\n' + '\n'.join([
        'type = drive', f"client_id = {token_data['client_id']}",
        f"client_secret = {token_data['client_secret']}", 'scope = drive',
        f'root_folder_id = {FOLDER_ID}',
        'token = ' + json.dumps(token, separators=(',', ':')), '',
    ])
    RCLONE_CONFIG.write_text(config, encoding='utf-8')
    FILTER_FILE.write_text('\n'.join(FILTERS) + '\n', encoding='utf-8')
    os.chmod(RCLONE_CONFIG, 0o600); os.chmod(FILTER_FILE, 0o600)


def base_cmd(command):
    return [
        'rclone', command, str(SOURCE), REMOTE,
        '--config', str(RCLONE_CONFIG), '--filter-from', str(FILTER_FILE),
        '--checksum', '--fast-list', '--local-no-check-updated',
        '--checkers', '16',
    ]


def run_sync(dry_run=False):
    cmd = base_cmd('sync') + [
        '--transfers', '4', '--drive-chunk-size', '8M', '--retries', '8',
        '--low-level-retries', '20', '--delete-excluded', '--stats', '0',
    ]
    if dry_run:
        cmd += ['--dry-run', '--verbose']
    cp = subprocess.run(cmd, text=True, capture_output=True)
    if cp.returncode:
        raise RuntimeError((cp.stderr or cp.stdout)[-4000:])
    return cp


def verify():
    with tempfile.NamedTemporaryFile(prefix='skills-check-', delete=False) as fh:
        combined = Path(fh.name)
    try:
        cmd = base_cmd('check') + ['--one-way', '--combined', str(combined)]
        cp = subprocess.run(cmd, text=True, capture_output=True)
        statuses = {}
        lines = combined.read_text(encoding='utf-8', errors='replace').splitlines()
        for line in lines:
            key = line[:1]
            statuses[key] = statuses.get(key, 0) + 1
        nonmatching = sum(v for k, v in statuses.items() if k != '=')
        if cp.returncode or nonmatching:
            raise RuntimeError(f"镜像校验失败: statuses={statuses}; " + (cp.stderr or '')[-2000:])
        return {'file_count': statuses.get('=', 0), 'status_counts': statuses}
    finally:
        combined.unlink(missing_ok=True)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--dry-run', action='store_true')
    args = ap.parse_args()
    ensure_runtime()
    run_sync(args.dry_run)
    if args.dry_run:
        print(json.dumps({'ok': True, 'dry_run': True, 'strategy': 'direct-expanded-mirror'}, ensure_ascii=False, indent=2))
        return
    checked = verify()
    print(json.dumps({
        'ok': True, 'strategy': 'direct-expanded-mirror',
        'remote_folder_id': FOLDER_ID, 'archive_used': False,
        'intermediate_overlay_used': False, **checked,
    }, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
