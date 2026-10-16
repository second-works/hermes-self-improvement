"""Trusted bounded denial probes. Only synthetic paths; no production path lookups."""
import errno
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time

mode = json.load(sys.stdin)['mode']
result = {}


def denied(operation):
    try:
        operation()
    except OSError as error:
        return error.errno in (errno.EACCES, errno.EPERM, errno.EROFS, errno.ENOENT)
    return False


if mode == 'boundaries':
    status = Path('/proc/self/status').read_text()
    fields = dict(row.split(':', 1) for row in status.splitlines() if ':' in row)
    result = {
        'non_root': os.getuid() == 65532 and os.getgid() == 65532,
        'capabilities': int(fields['CapEff'].strip(), 16) == 0 and int(fields['CapBnd'].strip(), 16) == 0,
        'no_new_privileges': fields['NoNewPrivs'].strip() == '1',
        'seccomp': fields['Seccomp'].strip() == '2',
        'env': set(os.environ) <= {'PATH', 'HOME', 'TMPDIR', 'LANG', 'LC_CTYPE'},
        'root_readonly': denied(lambda: Path('/probe-write-dummy').write_text('dummy')),
        'source_readonly': denied(lambda: Path('/source/dummy').write_text('dummy')),
        'lock_readonly': denied(lambda: Path('/input/requirements.lock').write_text('dummy')),
        'deps_readonly': denied(lambda: Path('/deps/dummy').write_text('dummy')),
        'skill_readonly': denied(lambda: Path('/fixture/hermes-agent/skills/github-code-review/SKILL.md').write_text('dummy')),
        'fixture_readonly': denied(lambda: Path('/input/program.py').write_text('dummy')),
        'canary_unmounted': denied(lambda: Path('/unmounted-dummy/canary').read_bytes()),
        'hidden_unmounted': not Path('/hidden').exists() and not Path('/evaluator').exists(),
        'socket_unmounted': not Path('/var/run/docker.sock').exists(),
        'no_shared_memory': not Path('/dev/shm').exists(),
        'cpu_quota': Path('/sys/fs/cgroup/cpu.max').read_text().strip() == '100000 100000',
        'memory_limit': Path('/sys/fs/cgroup/memory.max').read_text().strip() == '1073741824',
        'swap_limit': Path('/sys/fs/cgroup/memory.swap.max').read_text().strip() == '0',
        'pids_limit': Path('/sys/fs/cgroup/pids.max').read_text().strip() == '64',
        'tmpfs_size': os.statvfs('/run/work').f_blocks * os.statvfs('/run/work').f_frsize == 134217728,
        'python': sys.version.split()[0],
    }
    with socket.socket() as client:
        client.settimeout(0.25)
        try:
            client.connect(('192.0.2.1', 443))
            result['network_denied'] = False
        except OSError as error:
            result['network_denied'] = error.errno in (errno.ENETUNREACH, errno.EHOSTUNREACH)
    Path('/run/work/dummy').write_text('fixture')
    result['work_writable'] = Path('/run/work/dummy').read_text() == 'fixture'
elif mode == 'disk':
    try:
        with open('/run/work/bounded-dummy', 'wb') as stream:
            for _ in range(140):
                stream.write(b'x' * 1048576)
        result['disk_denied'] = False
    except OSError as error:
        result['disk_denied'] = error.errno == errno.ENOSPC
elif mode == 'memory':
    child = subprocess.run([sys.executable, '-I', '-c', 'x = bytearray(1200*1024*1024)'],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10)
    result['memory_denied'] = child.returncode in (-9, 1)
elif mode == 'pids':
    children = []
    result['pids_denied'] = False
    try:
        for _ in range(70):
            children.append(subprocess.Popen([sys.executable, '-I', '-c', 'import time; time.sleep(10)'],
                                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL))
    except OSError as error:
        result['pids_denied'] = error.errno == errno.EAGAIN
    finally:
        for child in children:
            child.kill()
        for child in children:
            child.wait(timeout=5)
elif mode == 'cpu':
    def throttled():
        fields = dict(row.split() for row in Path('/sys/fs/cgroup/cpu.stat').read_text().splitlines())
        return int(fields['nr_throttled'])
    before = throttled()
    children = [subprocess.Popen([sys.executable, '-I', '-c',
                'import time; end=time.monotonic()+2\nwhile time.monotonic()<end: pass'],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL) for _ in range(2)]
    for child in children:
        child.wait(timeout=10)
    result['cpu_throttled'] = throttled() > before
elif mode == 'timeout':
    subprocess.Popen([sys.executable, '-I', '-c',
        'import json,os,time; print(json.dumps({"probe":"timeout-child-started",'
        '"pid":os.getpid(),"parent_pid":os.getppid()}), flush=True); time.sleep(60)'])
    time.sleep(60)
elif mode == 'output':
    os.write(1, b'x' * (1048576 + 65536))
else:
    raise SystemExit(2)
print(json.dumps(result))
