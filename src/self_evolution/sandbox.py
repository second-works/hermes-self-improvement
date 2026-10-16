"""Separate Issue #6 limits; preserve the Issue #5 controller's guarantees."""
import os
from pathlib import Path
import threading
import time

from evaluation.core import EvaluationError, require
from evaluation.sandbox import Sandbox

DISK_LIMIT = 2 * 1024**3
MEMORY = 1024**3
TMPFS = 'rw,noexec,nosuid,nodev,size=134217728,uid=65532,gid=65532,mode=700'


def stored_bytes(work):
    total = 0
    for base, directories, files in os.walk(work, followlinks=False):
        for name in directories + files:
            path = Path(base) / name
            require(not path.is_symlink(), 'RUN_SYMLINK')
        for name in files:
            try:
                total += (Path(base) / name).stat().st_size
            except FileNotFoundError:
                # pip may atomically rename temporary files during preparation.
                continue
    return total


class SpikeSandbox(Sandbox):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.phase = 'probe'

    def mounts(self, program):
        paths = [(program, '/input/program.py', False),
                 (self.root / 'fixtures/self-evolution/requirements.lock', '/input/requirements.lock', False)]
        if self.phase in ('download', 'install'):
            paths.append((self.work / 'prepare', '/prepare', True))
        else:
            paths.extend([(self.work / 'source', '/source', False),
                          (self.work / 'prepare/site', '/deps', False),
                          (self.root / 'fixtures/self-evolution/hermes-agent', '/fixture/hermes-agent', False)])
        return paths

    def options(self, name, program):
        require(self.phase in ('download', 'install', 'gate', 'probe'), 'PHASE')
        require(not self.broken and time.monotonic() < self.deadline, 'SANDBOX_STOPPED')
        # Validate program and pinned image through the unchanged base controller.
        base = super().options(name, program)
        end = base.index('--mount')
        args = base[:end]
        replacements = {'--memory=268435456': '--memory=1073741824',
                        '--memory-swap=268435456': '--memory-swap=1073741824',
                        '--pids-limit=32': '--pids-limit=64',
                        '--ulimit=nofile=64:64': '--ulimit=nofile=256:256'}
        args = [replacements.get(arg, arg) for arg in args]
        index = args.index('--tmpfs=/run/work:rw,noexec,nosuid,nodev,size=16777216,uid=65532,gid=65532,mode=700')
        args[index] = '--tmpfs=/run/work:' + TMPFS
        if self.phase == 'download':
            args[args.index('--network=none')] = '--network=bridge'
        for source, target, writable in self.mounts(program):
            source = Path(source).absolute()
            require(source.exists() and not source.is_symlink() and ',' not in str(source), 'MOUNT_BOUNDARY')
            require(source.resolve().is_relative_to(self.root), 'MOUNT_BOUNDARY')
            args.extend(['--mount', f'type=bind,source={source},target={target}' + ('' if writable else ',readonly')])
        args.extend(['--workdir=/run/work', '-i', self.image, '/usr/bin/env', '-i',
                     'PATH=/usr/local/bin:/usr/bin:/bin', 'HOME=/run/work', 'TMPDIR=/run/work',
                     'LANG=C.UTF-8', 'python3', '-I', '-B', '/input/program.py'])
        return args

    def verify_config(self, info, program):
        h, c = info['HostConfig'], info['Config']
        network = 'bridge' if self.phase == 'download' else 'none'
        require(h['NetworkMode'] == network and h['IpcMode'] == 'none' and
                c['User'] == '65532:65532' and h['ReadonlyRootfs'] and
                h['CapDrop'] == ['ALL'] and not h['CapAdd'] and
                h['SecurityOpt'] == ['no-new-privileges=true'] and not h['Privileged'] and
                h['NanoCpus'] == 1000000000 and h['Memory'] == MEMORY and
                h['MemorySwap'] == MEMORY and h['PidsLimit'] == 64 and
                h['LogConfig']['Type'] == 'none' and not h['PidMode'] and
                not h['Devices'] and not h['Binds'] and h['Tmpfs'] == {'/run/work': TMPFS},
                'CONFIG_MISMATCH')
        actual = sorted((m['Source'], m['Destination'], m['RW']) for m in info['Mounts'])
        expected = sorted((str(Path(p).absolute()), t, w) for p, t, w in self.mounts(program))
        require(actual == expected and info['Image'] == self.image, 'MOUNT_MISMATCH')
        args = self.options('unused', program)
        require(c['WorkingDir'] == '/run/work' and c['Entrypoint'] is None and
                c['Cmd'] == args[args.index(self.image) + 1:], 'COMMAND_MISMATCH')

    def command(self, *args, **kwargs):
        execution = bool(args and args[0] in ('create', 'start'))
        if execution:
            require(stored_bytes(self.work) <= DISK_LIMIT, 'PERSISTENT_DISK_LIMIT')
        finished = threading.Event()
        exceeded = threading.Event()
        uncertain = threading.Event()

        def monitor():
            while not finished.wait(0.2):
                try:
                    over = stored_bytes(self.work) > DISK_LIMIT
                except (OSError, EvaluationError):
                    over = True
                    uncertain.set()
                if over:
                    exceeded.set()
                    # Only the currently attached, controller-created container.
                    super(SpikeSandbox, self).command('kill', args[-1], timeout=5)
                    return

        watcher = None
        if args and args[0] == 'start':
            watcher = threading.Thread(target=monitor, daemon=True)
            watcher.start()
        try:
            result = super().command(*args, **kwargs)
        finally:
            finished.set()
            if watcher:
                watcher.join(timeout=6)
        if exceeded.is_set():
            self.broken = True
            raise EvaluationError('STORAGE_UNCERTAIN' if uncertain.is_set() else 'PERSISTENT_DISK_LIMIT')
        if execution:
            require(stored_bytes(self.work) <= DISK_LIMIT, 'PERSISTENT_DISK_LIMIT')
        return result
