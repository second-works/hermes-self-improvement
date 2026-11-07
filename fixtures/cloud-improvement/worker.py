"""Fixed Hermes worker. Secrets enter on stdin and remain in container tmpfs."""
import base64
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import time

REVISION = 'b200f5bc60e31588ba2cb60e288029c4a54ba5fa'

# This hook runs in both the gateway and CLI, sharing a single durable send gate.
HOOK = r"""
import fcntl
import json
import os
import sys
import threading
import time
from pathlib import Path
import httpx

root = Path(os.environ['HERMES_HOME'])
original = httpx.HTTPTransport.handle_request
permit = threading.local()

def audit(event, args):
    if event == 'socket.getaddrinfo':
        if args[0] not in ('localhost', '127.0.0.1', '::1'):
            if not getattr(permit, 'active', False) or args[0] != 'chatgpt.com':
                raise RuntimeError('DNS_BLOCKED')
    if event == 'socket.connect':
        address = args[1]
        local = (isinstance(address, tuple) and address[0] in ('127.0.0.1', '::1')
                 or isinstance(address, str) and address.startswith('/tmp/cloud/'))
        if not local and not getattr(permit, 'active', False):
            raise RuntimeError('SOCKET_BLOCKED')

sys.addaudithook(audit)

def intercept(self, request):
    if request.method != 'POST' or str(request.url) != 'https://chatgpt.com/backend-api/codex/responses':
        raise RuntimeError('OUTBOUND_BLOCKED')
    if time.time() >= float(os.environ['HERMES_APPROVAL_UNTIL']):
        raise RuntimeError('APPROVAL_EXPIRED')
    with (root / 'send.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if time.time() >= float(os.environ['HERMES_APPROVAL_UNTIL']):
            raise RuntimeError('APPROVAL_EXPIRED')
        if (root / 'sent').exists():
            raise RuntimeError('RETRY_BLOCKED')
        raw = request.read()
        encoding = request.headers.get('content-encoding', 'identity')
        if encoding == 'zstd':
            from compression import zstd
            raw = zstd.decompress(raw)
        elif encoding == 'gzip':
            import gzip
            raw = gzip.decompress(raw)
        elif encoding != 'identity':
            raise RuntimeError('ENCODING_BLOCKED')
        if len(raw) > 262144:
            raise RuntimeError('PAYLOAD_LIMIT')
        data = json.loads(raw)
        inputs = data.get('input', [])
        users = [row['content'] for row in inputs if row.get('role') == 'user']
        texts = [''.join(p.get('text', '') for p in content) if isinstance(content, list) else content
                 for content in users]
        prompt = (root / 'query.txt').read_text()
        if (texts != [prompt] or data.get('tools') or data.get('model') != 'gpt-6-luna'
                or data.get('store') is not False
                or any(row.get('role') not in ('system','developer','user')
                       or row.get('type','message') != 'message' for row in inputs)):
            raise RuntimeError('PAYLOAD_BLOCKED')
        with (root / 'sent').open('x'):
            pass
    if os.environ.get('HERMES_OFFLINE_TEST') == '1':
        events = [{'type':'response.output_text.delta','delta':'HERMES_OFFLINE_OK'},
                  {'type':'response.completed','response':{'id':'fixture','status':'completed'}}]
        body = ''.join('event: '+row['type']+'\ndata: '+json.dumps(row)+'\n\n' for row in events)
        result = httpx.Response(200, headers={'content-type':'text/event-stream'}, text=body)
    else:
        permit.active = True
        try:
            result = original(self, request)
        finally:
            permit.active = False
    (root / 'http-status').write_text(str(result.status_code))
    return result

httpx.HTTPTransport.handle_request = intercept
"""


def main():
    if len(sys.argv) > 1 and sys.argv[1] == 'child':
        sys.path.insert(0, '/opt/hermes')
        from hermes_cli.main import main as cli
        sys.argv = ['hermes', 'chat', '--oneshot', '--format', 'stream-json',
                    '--query-file', str(Path(os.environ['HERMES_HOME']) / 'query.txt'),
                    '--provider', 'openai-codex', '--model', 'gpt-6-luna',
                    '--toolsets', ',', '--max-turns', '1']
        cli()
        return
    provenance = json.loads(Path('/etc/hermes/image-provenance.json').read_text())
    if provenance.get('revision') != REVISION:
        raise ValueError('IMAGE_REVISION_MISMATCH')
    raw = sys.stdin.buffer.read(65537)
    if len(raw) > 65536:
        raise ValueError('INPUT_LIMIT')
    request = json.loads(raw)
    if set(request) != {'auth', 'prompt', 'offline_test', 'approved_until'} or type(request['offline_test']) is not bool:
        raise ValueError('REQUEST_SCHEMA')
    if (type(request['approved_until']) not in (int, float)
            or not math.isfinite(request['approved_until']) or request['approved_until'] <= time.time()):
        raise ValueError('APPROVAL_EXPIRED')
    prompt = request['prompt']
    if not isinstance(prompt, str) or not 0 < len(prompt.encode()) <= 8192:
        raise ValueError('PROMPT_LIMIT')
    auth = request['auth']
    if set(auth.get('providers', {})) != {'openai-codex'}:
        raise ValueError('AUTH_SCOPE')
    token = auth['providers']['openai-codex']['tokens']['access_token'].split('.')[1]
    claims = json.loads(base64.urlsafe_b64decode(token + '=' * (-len(token) % 4)))
    if (type(claims['exp']) not in (int, float)
            or not math.isfinite(claims['exp']) or claims['exp'] <= time.time() + 180):
        raise ValueError('AUTH_EXPIRED')
    os.umask(0o077)
    root = Path('/tmp/cloud')
    home, profile, empty, hook = [root / part for part in ('home', 'profile', 'empty', 'hook')]
    for directory in (home, profile, empty, hook):
        directory.mkdir(parents=True)
    (profile / 'auth.json').write_text(json.dumps(auth))
    (profile / 'query.txt').write_text(prompt)
    (profile / 'config.yaml').write_text(
        'auxiliary:\n  title_generation:\n    enabled: false\nmemory:\n'
        '  memory_enabled: false\n  user_profile_enabled: false\nauth:\n'
        '  adopt_external_logins: false\nfallback_providers: []\n')
    (hook / 'sitecustomize.py').write_text(HOOK)
    env = {
        'PATH': '/opt/hermes/.venv/bin:/usr/local/bin:/usr/bin:/bin',
        'HOME': str(home), 'HERMES_HOME': str(profile), 'LANG': 'C.UTF-8',
        'PYTHONDONTWRITEBYTECODE': '1', 'PYTHONPATH': str(hook),
        'HERMES_BUNDLED_PLUGINS': str(empty), 'HERMES_BUNDLED_SKILLS': str(empty),
        'HERMES_APPROVAL_UNTIL': str(request['approved_until']),
        'HERMES_OFFLINE_TEST': '1' if request['offline_test'] else '0',
    }
    gateway = subprocess.Popen(
        [sys.executable, '-B', '-m', 'hermes_cli.main', '--profile', 'default', 'gateway', 'run', '--quiet'],
        env=env, cwd='/opt/hermes', stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        time.sleep(4)
        answer = subprocess.run([sys.executable, '-B', __file__, 'child'], env=env,
                                cwd=home, capture_output=True, timeout=24)
        events = [json.loads(line) for line in answer.stdout.splitlines() if line.startswith(b'{')]
        results = [row for row in events if row.get('type') == 'result']
        status_file = profile / 'http-status'
        status = int(status_file.read_text()) if status_file.exists() else 0
        if answer.returncode or len(results) != 1 or results[0].get('exit_code') != 0 or status != 200:
            code = 'AUTH_FAILED' if status in (401, 403) else 'QUOTA_EXHAUSTED' if status == 429 else 'CLOUD_FAILED'
            print(json.dumps({'status': code}))
            return
        text = results[0]['text']
        if not isinstance(text, str) or len(text.encode()) > 32768 or not (profile / 'sent').exists():
            raise ValueError('RESPONSE_BOUNDARY')
        print(json.dumps({'status': 'COMPLETED', 'requests': 1, 'tools': 0, 'text': text}))
    finally:
        gateway.terminate()
        try:
            gateway.wait(timeout=2)
        except subprocess.TimeoutExpired:
            gateway.kill()
            gateway.wait()


if __name__ == '__main__':
    try:
        main()
    except Exception:
        print('{"status":"CLOUD_FAILED"}')
        sys.exit(2)
