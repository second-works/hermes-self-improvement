"""Pinned Docker contract for a single approved Hermes cloud request."""
from pathlib import Path

from evaluation.core import load_json, regular, require
from evaluation.sandbox import Sandbox

IMAGE = 'sha256:35fa8b0f5e93fa2471bcf11fe2ba45893512cbef2e6b5f4cbd2f7fe8b60b94ea'
KIND = 'hermes-cloud-v1'
MODEL = 'gpt-6-luna'
ENDPOINT = 'https://chatgpt.com/backend-api/codex/responses'
WORKER_PATH = 'fixtures/cloud-improvement/worker.py'
TMPFS = {
    '/tmp': 'rw,nosuid,nodev,size=134217728,mode=1777',
    '/opt/data': 'rw,nosuid,nodev,size=33554432,uid=65532,gid=65532,mode=700',
}


class CloudSandbox(Sandbox):
    """Retain the existing reconciliation while pinning the cloud-only profile."""
    def options(self, name, program):
        require(not self.broken, 'SANDBOX_STOPPED')
        require(self.image == IMAGE, 'IMAGE_NOT_PINNED')
        regular(program, self.root, 65536)
        require(',' not in str(program), 'MOUNT_PATH')
        require(Path(program).absolute() == self.root / WORKER_PATH, 'WORKER_BOUNDARY')
        return [
            'create', '--name', name, '--pull=never', '--platform=linux/arm64',
            '--network=bridge', '--ipc=none', '--user=65532:65532', '--read-only',
            '--cap-drop=ALL', '--security-opt=no-new-privileges=true',
            '--cpus=1', '--memory=768m', '--memory-swap=768m', '--pids-limit=128',
            '--log-driver=none',
            *['--tmpfs=' + path + ':' + value for path, value in TMPFS.items()],
            '--mount', 'type=bind,source=' + str(program) + ',target=/input/program.py,readonly',
            '--workdir=/tmp', '--entrypoint=/usr/bin/env', '-i', IMAGE,
            '-i', 'PATH=/opt/hermes/.venv/bin:/usr/local/bin:/usr/bin:/bin',
            'HOME=/tmp/home', 'LANG=C.UTF-8',
            '/opt/hermes/.venv/bin/python', '-I', '-B', '/input/program.py',
        ]

    def verify_config(self, info, program):
        h, c = info['HostConfig'], info['Config']
        require(info['Image'] == IMAGE and h['NetworkMode'] == 'bridge'
                and h['IpcMode'] == 'none' and c['User'] == '65532:65532'
                and h['ReadonlyRootfs'] and h['CapDrop'] == ['ALL'] and not h['CapAdd']
                and h['SecurityOpt'] == ['no-new-privileges=true']
                and h['NanoCpus'] == 1_000_000_000 and h['Memory'] == 805_306_368
                and h['MemorySwap'] == 805_306_368 and h['PidsLimit'] == 128
                and h['LogConfig']['Type'] == 'none' and not h['Privileged']
                and not h['PidMode'] and not h['Devices'] and not h['Binds']
                and h['Tmpfs'] == TMPFS, 'CLOUD_CONFIG_MISMATCH')
        require(len(info['Mounts']) == 1 and info['Mounts'][0]['Source'] == str(program)
                and info['Mounts'][0]['Destination'] == '/input/program.py'
                and not info['Mounts'][0]['RW'], 'CLOUD_MOUNT_MISMATCH')
        options = self.options('unused', program)
        require(c['WorkingDir'] == '/tmp' and c['Entrypoint'] == ['/usr/bin/env']
                and c['Cmd'] == options[options.index(IMAGE) + 1:], 'CLOUD_COMMAND_MISMATCH')


def response(root, data, event_dir, deadline, name):
    import time
    sandbox = CloudSandbox(root, event_dir, IMAGE, deadline=deadline)
    image = load_json(sandbox.checked('image', 'inspect', IMAGE, timeout=5))[0]
    require(image['Id'] == IMAGE and image['Os'] == 'linux'
            and image['Architecture'] == 'arm64', 'IMAGE_BOUNDARY')
    remaining = deadline - time.monotonic()
    require(remaining > 0, 'TIMEOUT')
    result = sandbox.run(root / WORKER_PATH, data, timeout=remaining, name=name)
    require(result['error'] != 'TIMEOUT' and time.monotonic() < deadline, 'TIMEOUT')
    require(not result['error'] and result['exit'] == result['container_exit'] == 0
            and not result['oom'] and not result['stderr'], 'CLOUD_WORKER_FAILED')
    return result['stdout']
