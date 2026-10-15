"""Local Docker controller. Candidate bytes never run on the host."""
import json
import os
from pathlib import Path
import re
import selectors
import shutil
import subprocess
import time
import uuid

from .core import EvaluationError, load_json, regular, require


OUTPUT_LIMIT = 1048576


def capture(argv, *, env, timeout=30, data=b'', limit=OUTPUT_LIMIT):
    """Drain both pipes with a combined bound; never include raw errors in exceptions."""
    require(len(data) <= 65536, 'INPUT_LIMIT')
    process = subprocess.Popen(argv, env=env, stdin=subprocess.PIPE,
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               start_new_session=True)
    selector = selectors.DefaultSelector()
    output = {1: bytearray(), 2: bytearray()}
    code = None
    until = time.monotonic() + timeout
    try:
        for stream, key in [(process.stdout, 1), (process.stderr, 2)]:
            os.set_blocking(stream.fileno(), False)
            selector.register(stream, selectors.EVENT_READ, key)
        os.set_blocking(process.stdin.fileno(), False)
        pending = memoryview(data)
        if pending:
            selector.register(process.stdin, selectors.EVENT_WRITE, 0)
        else:
            process.stdin.close()
        while selector.get_map():
            if time.monotonic() >= until:
                code = 'TIMEOUT'
                break
            for key, _ in selector.select(min(0.1, max(0, until - time.monotonic()))):
                if key.data == 0:
                    try:
                        count = os.write(key.fileobj.fileno(), pending)
                        pending = pending[count:]
                    except BrokenPipeError:
                        pending = memoryview(b'')
                    if not pending:
                        selector.unregister(key.fileobj)
                        key.fileobj.close()
                    continue
                chunk = os.read(key.fileobj.fileno(), 65536)
                if not chunk:
                    selector.unregister(key.fileobj)
                elif sum(map(len, output.values())) + len(chunk) > limit:
                    code = 'OUTPUT_LIMIT'
                    break
                else:
                    output[key.data].extend(chunk)
            if code:
                break
        if code:
            process.kill()
        remaining = max(0.1, until - time.monotonic())
        try:
            process.wait(timeout=remaining)
        except subprocess.TimeoutExpired:
            code = 'TIMEOUT'
            process.kill()
            process.wait(timeout=5)
        return {'exit': process.returncode, 'stdout': bytes(output[1]),
                'stderr': bytes(output[2]), 'error': code}
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=5)
        selector.close()
        for stream in (process.stdin, process.stdout, process.stderr):
            if not stream.closed:
                stream.close()


class Sandbox:
    def __init__(self, root, work, image=None, deadline=None):
        self.root, self.work = Path(root).resolve(), Path(work).resolve()
        require(self.work.is_relative_to(self.root / 'runs'), 'RUN_BOUNDARY')
        self.config = self.work / 'docker-config'
        self.config.mkdir(mode=0o700, exist_ok=True)
        require(not self.config.is_symlink(), 'CONFIG_BOUNDARY')
        self.binary = shutil.which('docker') or '/usr/local/bin/docker'
        require(Path(self.binary).is_file(), 'DOCKER_UNAVAILABLE')
        desktop = Path.home() / '.docker/run/docker.sock'
        self.endpoint = 'unix://' + str(desktop if desktop.exists() else Path('/var/run/docker.sock'))
        self.env = {'PATH': '/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin',
                    'HOME': str(self.config), 'LANG': 'C.UTF-8'}
        self.image = image
        self.deadline = deadline or time.monotonic() + 1200
        self.broken = False

    def command(self, *args, timeout=30, data=b'', limit=OUTPUT_LIMIT):
        return capture([self.binary, '--config', str(self.config), '--host', self.endpoint, *args],
                       env=self.env, timeout=timeout, data=data, limit=limit)

    def checked(self, *args, timeout=30):
        result = self.command(*args, timeout=timeout)
        require(not result['error'] and result['exit'] == 0, 'DOCKER_COMMAND_FAILED')
        return result['stdout']

    def environment(self):
        info = load_json(self.checked('info', '--format', '{{json .}}'))
        require(info['OSType'] == 'linux' and info['Architecture'] in ('aarch64', 'arm64'),
                'DOCKER_PLATFORM')
        require(info['MemoryLimit'] and info['PidsLimit'] and info['CpuCfsQuota'], 'RESOURCE_UNAVAILABLE')
        require(info['ContainersRunning'] == 0, 'EXISTING_CONTAINERS')
        return {key: info[key] for key in ('ServerVersion', 'KernelVersion', 'Architecture',
                                          'NCPU', 'MemTotal', 'CgroupVersion')}

    def image_info(self, reference):
        info = load_json(self.checked('image', 'inspect', reference))[0]
        require(info['Os'] == 'linux' and info['Architecture'] == 'arm64' and
                type(info['Size']) is int and 0 < info['Size'] < 300 * 1024**2, 'IMAGE_BOUNDARY')
        require(re.fullmatch(r'sha256:[a-f0-9]{64}', info['Id']), 'IMAGE_ID')
        refs = info['RepoDigests'] or []
        require(all(re.fullmatch(r'(docker.io/library/)?python@sha256:[a-f0-9]{64}', v) for v in refs)
                and bool(refs), 'IMAGE_ORIGIN')
        return {'id': info['Id'], 'repo_digests': sorted(refs), 'bytes': info['Size'],
                'architecture': info['Architecture'], 'os': info['Os']}

    def options(self, name, program):
        require(not self.broken and time.monotonic() < self.deadline, 'SANDBOX_STOPPED')
        require(re.fullmatch(r'sha256:[a-f0-9]{64}', self.image or ''), 'IMAGE_NOT_PINNED')
        regular(program, self.root, 65536)
        require(',' not in str(program), 'MOUNT_PATH')
        return ['create', '--name', name, '--pull=never', '--platform=linux/arm64',
                '--network=none', '--ipc=none', '--user=65532:65532', '--read-only',
                '--cap-drop=ALL', '--security-opt=no-new-privileges=true',
                '--cpus=1', '--memory=268435456', '--memory-swap=268435456', '--pids-limit=32',
                '--ulimit=nofile=64:64', '--ulimit=core=0:0', '--log-driver=none',
                '--tmpfs=/run/work:rw,noexec,nosuid,nodev,size=16777216,uid=65532,gid=65532,mode=700',
                '--mount', 'type=bind,source=' + str(program) + ',target=/input/program.py,readonly',
                '--workdir=/run/work', '-i', self.image,
                '/usr/bin/env', '-i', 'PATH=/usr/local/bin:/usr/bin:/bin', 'HOME=/run/work',
                'TMPDIR=/run/work', 'LANG=C.UTF-8', 'python3', '-I', '-B', '/input/program.py']

    def inspect(self, name, *, timeout=30):
        return load_json(self.checked('inspect', name, timeout=timeout))[0]

    def container_exists(self, name):
        listed = self.checked('container', 'ls', '--all', '--filter', 'name=' + name,
                              '--format', '{{.Names}}', timeout=5).strip()
        require(listed in (b'', name.encode()), 'CONTAINER_IDENTITY_UNKNOWN')
        return bool(listed)

    def cleanup(self, name, *, ambiguous=False):
        if ambiguous:
            until = time.monotonic() + 5
            while not self.container_exists(name):
                remaining = until - time.monotonic()
                require(remaining > 0, 'CREATE_OUTCOME_UNKNOWN')
                time.sleep(min(0.1, remaining))
        elif not self.container_exists(name):
            return
        state = self.inspect(name, timeout=5)['State']
        if state['Running']:
            self.checked('kill', name, timeout=5)
            state = self.inspect(name, timeout=5)['State']
        require(not state['Running'], 'CONTAINER_NOT_STOPPED')
        self.checked('rm', name, timeout=5)
        require(not self.container_exists(name), 'CONTAINER_NOT_REMOVED')

    def verify_config(self, info, program):
        h, c = info['HostConfig'], info['Config']
        require(h['NetworkMode'] == 'none' and h['IpcMode'] == 'none' and c['User'] == '65532:65532' and
                h['ReadonlyRootfs'] and h['CapDrop'] == ['ALL'] and not h['CapAdd'] and
                h['SecurityOpt'] == ['no-new-privileges=true'] and
                h['NanoCpus'] == 1000000000 and h['Memory'] == 268435456 and
                h['MemorySwap'] == 268435456 and h['PidsLimit'] == 32 and
                h['LogConfig']['Type'] == 'none' and not h['Privileged'] and
                not h['PidMode'] and not h['Devices'] and not h['Binds'], 'CONFIG_MISMATCH')
        require(info['Image'] == self.image and len(info['Mounts']) == 1 and
                info['Mounts'][0]['Source'] == str(program) and
                info['Mounts'][0]['Destination'] == '/input/program.py' and
                not info['Mounts'][0]['RW'], 'MOUNT_MISMATCH')
        require(h['Tmpfs'] == {'/run/work': 'rw,noexec,nosuid,nodev,size=16777216,uid=65532,gid=65532,mode=700'},
                'TMPFS_MISMATCH')
        args = self.options('unused', program)
        require(c['WorkingDir'] == '/run/work' and c['Entrypoint'] is None and
                c['Cmd'] == args[args.index(self.image) + 1:], 'COMMAND_MISMATCH')

    def run(self, program, data=b'', *, timeout=30):
        program = Path(program).absolute()
        name = 'hermes-eval-' + uuid.uuid4().hex
        started = time.monotonic()
        case_deadline = min(started + timeout, self.deadline)
        def remaining():
            value = case_deadline - time.monotonic()
            require(value > 0, 'CASE_DEADLINE')
            return value
        args = self.options(name, program)
        attempted = False
        ambiguous = False
        try:
            attempted = True
            try:
                self.checked(*args, timeout=remaining())
            except Exception:
                # A failed client response cannot establish that the daemon did nothing.
                self.broken = True
                ambiguous = True
                raise
            self.verify_config(self.inspect(name, timeout=remaining()), program)
            result = self.command('start', '--attach', '--interactive', name, timeout=remaining(), data=data)
            # Safety reconciliation has its own bound even after the execution budget expires.
            state = self.inspect(name, timeout=5)['State']
            if state['Running']:
                self.checked('kill', name, timeout=5)
                state = self.inspect(name, timeout=5)['State']
            require(not state['Running'], 'CONTAINER_NOT_STOPPED')
            result['wall_seconds'] = time.monotonic() - started
            result['oom'] = state['OOMKilled']
            result['container_exit'] = state['ExitCode']
            return result
        finally:
            if attempted:
                try:
                    self.cleanup(name, ambiguous=ambiguous)
                except Exception:
                    self.broken = True
                    error = EvaluationError('ISOLATION_CLEANUP_FAILED')
                    error.pending_container = name
                    raise error from None
