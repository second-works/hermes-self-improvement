"""Trusted wheel-only preparation; no upstream code or personal config is imported."""
import json
import os
from pathlib import Path
import subprocess
import sys

payload = json.load(sys.stdin)
common = [sys.executable, '-I', '-m', 'pip', '--disable-pip-version-check', '--no-cache-dir']
env = {'PATH': '/usr/local/bin:/usr/bin:/bin', 'HOME': '/run/work',
       'PIP_CONFIG_FILE': '/dev/null', 'LANG': 'C.UTF-8'}
if payload['mode'] == 'download':
    packages = payload['packages']
    if not all(type(v) is str and '==' in v and all(c.isalnum() or c in '-_.=[]' for c in v) for v in packages):
        raise SystemExit(2)
    args = common + ['download', '--only-binary=:all:', '--index-url', 'https://pypi.org/simple',
                     '--dest', '/prepare/wheels', *packages]
elif payload['mode'] == 'install':
    args = common + ['install', '--no-index', '--no-deps', '--require-hashes',
                     '--find-links', '/prepare/wheels', '--target', '/prepare/site',
                     '-r', '/input/requirements.lock']
else:
    raise SystemExit(2)
result = subprocess.run(args, env=env, capture_output=True, timeout=500)
Path('/prepare/pip-' + payload['mode'] + '.txt').write_bytes(result.stdout + result.stderr)
print(json.dumps({'exit': result.returncode, 'phase': payload['mode']}))
raise SystemExit(result.returncode)
