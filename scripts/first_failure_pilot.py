#!/usr/bin/env python3
"""PUBLIC read-only pilot: stop at the first failed required check, before any inference."""
import argparse
from contextlib import contextmanager
import fcntl
import hashlib
import os
from pathlib import Path
import re
import signal
import stat
import subprocess
import sys
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from adoption.core import save, syncdir
from evaluation.core import EvaluationError, canonical, digest, load_json, regular, require, write_new
from github_work_guide.core import complete, Invalid, load_run, source_url

REQUIRED = ('ci', 'Security Preflight', 'Analyze (python)')
FAILED = {'failure', 'timed_out', 'cancelled', 'action_required', 'startup_failure', 'stale'}
MAX_CHECKS, MAX_BYTES, INTERVAL = 168, 512 * 1024 * 1024, 3600
CYCLE = re.compile(r'[0-9]{3}-[0-9a-f]{32}\Z')
SIGNALLED = False


def failures(snapshot):
    """Observation only. Live revalidation, reproduction and mapping are still required."""
    complete(snapshot)
    result = []
    for item in sorted(snapshot['items'].values(), key=lambda x: x['number']):
        if item['kind'] != 'pr' or item['state'] != 'OPEN':
            continue
        raw, n = item['raw'], item['number']
        head = raw['detail']['head']['sha']
        for name in REQUIRED:
            for kind, rows in (
                ('check-run', [r for r in raw['checks'] if r['name'] == name and r['head_sha'] == head]),
                ('commit-status', [r for r in raw['statuses'] if r['context'] == name]),
            ):
                require(all(type(r['id']) is int and r['id'] > 0 for r in rows)
                        and len({r['id'] for r in rows}) == len(rows), 'CHECK_ID_INVALID')
                row = max(rows, key=lambda r: r['id'], default=None)
                if row is None:
                    continue
                bad = (row['status'] == 'completed' and row.get('conclusion') in FAILED if kind == 'check-run'
                       else row['state'] in ('failure', 'error'))
                if bad:
                    result.append({'pr_number': n, 'pr_url': source_url('pr', n), 'head_sha': head,
                                   'kind': kind, 'name': name, 'id': row['id'],
                                   'conclusion': row.get('conclusion') if kind == 'check-run' else row['state']})
    return result


def report_text(value):
    title = '# 初回障害の確認待ち' if value['status'] == 'AWAITING_REVIEW' else '# 点検停止の確認票'
    lines = [title, '', f"状態: {value['status']} / {value['reason']}", '',
             'この監視は推論・Hermes認証読取・候補採用を行いません。', '']
    if value['status'] == 'AWAITING_REVIEW':
        f = value['failure']
        lines += [f"- PR: [#{f['pr_number']}]({f['pr_url']})", f"- head: {f['head_sha']}",
                  f"- check: {f['name']} / {f['kind']} / ID {f['id']} / {f['conclusion']}",
                  f"- 取得: {value['captured_at']}", f"- 保存点検: {value['snapshot_run']}",
                  f"- snapshot hash: {value['snapshot_hash']}", '',
                  '## 確認する内容', '',
                  '保存点検のsnapshot.json・manifest.json・report.mdで原文と判断根拠を確認してください。',
                  '検出時点の観測です。現在のPR/head/check、独立した再現根拠、登録profileとの対応は未確認です。',
                  'モデルへ送る前に、最新状態の再照合と対象入力・回数・利用枠・費用条件の個別承認が必要です。']
    else:
        lines += ['取得や保存の不確実性を解消するまで、新しい点検を実行しません。',
                  'cycles/の実行記録と部分的な点検を保全し、停止理由を確認してください。']
    lines += ['', 'この初回記録は上書きせず、以後の定期起動もネットワーク処理なしで待機します。', '']
    return '\n'.join(lines)


class Pilot:
    def __init__(self, root=ROOT):
        self.root = Path(root).absolute()
        self.state = self.root / 'runs/first-failure-pilot'

    def path_check(self):
        require(not any(p.is_symlink() for p in (self.state, *self.state.parents)), 'PATH_SYMLINK')
        if self.state.exists():
            info = self.state.stat()
            require(stat.S_ISDIR(info.st_mode) and info.st_uid == os.getuid()
                    and stat.S_IMODE(info.st_mode) == 0o700, 'STATE_PERMISSIONS')

    def read(self, path):
        raw = regular(path, self.state, 16384)
        info = path.stat()
        require(info.st_uid == os.getuid() and stat.S_IMODE(info.st_mode) == 0o600
                and info.st_nlink == 1, 'RECORD_PERMISSIONS')
        return load_json(raw)

    def block_unverified(self):
        """Best-effort durable stop even when the private directory mode is incorrect."""
        if not self.state.is_dir() or any(x.is_symlink() for x in (self.state, *self.state.parents)):
            return
        fd = os.open(self.state, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            if os.fstat(fd).st_uid != os.getuid():
                return
            try:
                marker = os.open('unverified.stop', os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW,
                                 0o600, dir_fd=fd)
            except FileExistsError:
                return
            with os.fdopen(marker, 'wb') as stream:
                stream.write(b'PILOT_UNVERIFIED\n');stream.flush();os.fsync(stream.fileno())
            os.fsync(fd)
        finally:
            os.close(fd)

    def config(self):
        value = self.read(self.state / 'config.json')
        require(type(value) is dict and set(value) == {'schema_version', 'enabled', 'runtime_sha'}
                and type(value['schema_version']) is int and value['schema_version'] == 1
                and type(value['enabled']) is bool and type(value['runtime_sha']) is str
                and re.fullmatch('[0-9a-f]{40}', value['runtime_sha']), 'CONFIG_INVALID')
        return value

    def runtime(self, expected):
        env = {k: os.environ[k] for k in ('PATH', 'LANG', 'LC_ALL') if k in os.environ}
        def git(*args, binary=False):
            p = subprocess.run(['git', '--no-optional-locks', '-c', 'core.fsmonitor=false',
                                '-c', 'core.hooksPath=/dev/null', '-C', str(self.root), *args],
                               capture_output=True, timeout=10, env=env, check=False)
            require(p.returncode == 0, 'RUNTIME_UNVERIFIED')
            return p.stdout if binary else p.stdout.decode('ascii').strip()
        require(git('rev-parse', 'HEAD') == expected and not git('status', '--porcelain',
                '--untracked-files=all'), 'RUNTIME_CHANGED')
        # Git status alone can hide assume-unchanged/skip-worktree files.
        for entry in git('ls-tree', '-rz', '--full-tree', 'HEAD', binary=True).split(b'\0'):
            if not entry:
                continue
            header, name = entry.split(b'\t', 1)
            relative = name.decode('utf-8')
            if relative.split('/', 1)[0] not in ('src', 'scripts'):
                continue
            mode, kind, oid = header.split()
            require(mode in (b'100644', b'100755') and kind == b'blob', 'RUNTIME_FILE_TYPE')
            raw = regular(self.root / relative, self.root, 1024 * 1024)
            actual = hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest()
            require(actual == oid.decode(), 'RUNTIME_CHANGED')

    def configure(self, expected):
        require(type(expected) is str and re.fullmatch('[0-9a-f]{40}', expected), 'RUNTIME_SHA')
        self.path_check()
        self.runtime(expected)
        require(not os.path.lexists(self.state), 'EXISTING_PILOT_PRESERVED')
        self.state.mkdir(parents=True, mode=0o700)
        (self.state / 'cycles').mkdir(mode=0o700)
        save(self.state / 'config.json', {'schema_version': 1, 'enabled': True, 'runtime_sha': expected})
        return {'status': 'CONFIGURED', 'interval_seconds': INTERVAL, 'max_checks': MAX_CHECKS,
                'max_bytes': MAX_BYTES, 'model_calls': 0}

    @contextmanager
    def lock(self):
        fd = os.open(self.state / 'monitor.lock', os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        try:
            info = os.fstat(fd)
            require(stat.S_ISREG(info.st_mode) and info.st_nlink == 1 and info.st_uid == os.getuid()
                    and stat.S_IMODE(info.st_mode) == 0o600, 'LOCK_PERMISSIONS')
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise EvaluationError('CONCURRENT_RUN') from None
            yield
        finally:
            os.close(fd)

    def capacity(self):
        total = 0
        for path in (self.root / 'runs').rglob('*'):
            require(not path.is_symlink(), 'PATH_SYMLINK')
            if path.is_file():
                total += path.stat().st_size
        require(total < MAX_BYTES, 'STORAGE_LIMIT')

    def cycles(self):
        parent = self.state / 'cycles'
        require(parent.is_dir() and not parent.is_symlink(), 'CYCLES_INVALID')
        rows = sorted(parent.iterdir())
        for i, path in enumerate(rows, 1):
            require(path.is_dir() and not path.is_symlink() and CYCLE.fullmatch(path.name)
                    and int(path.name[:3]) == i, 'CYCLES_INVALID')
            require(os.path.lexists(path / 'result.json'), 'RECOVERY_REQUIRED')
            row = self.read(path / 'result.json')
            require(row.get('cycle') == path.name and row.get('status') == 'CLEAR', 'RECOVERY_REQUIRED')
            require(row.get('snapshot_run') == 'pilot-' + path.name, 'SNAPSHOT_PATH')
            snapshot = load_run(self.root / 'runs' / row['snapshot_run'])
            require(snapshot['hash'] == row.get('snapshot_hash') and not failures(snapshot), 'OBSERVATION_CHANGED')
        return rows

    def terminal(self):
        value = self.read(self.state / 'terminal.json')
        require(type(value) is dict and value.get('status') in ('AWAITING_REVIEW', 'STOPPED'), 'TERMINAL_INVALID')
        fields = {'schema_version', 'status', 'reason', 'model_calls', 'hermes_auth_reads', 'report_sha256'}
        if value['status'] == 'AWAITING_REVIEW':
            fields |= {'cycle', 'snapshot_run', 'snapshot_hash', 'runtime_sha', 'captured_at', 'failure'}
        require(set(value) == fields and type(value['schema_version']) is int and value['schema_version'] == 1
                and all(type(value[k]) is int and value[k] == 0 for k in ('model_calls', 'hermes_auth_reads'))
                and type(value['reason']) is str and re.fullmatch('[A-Z_]{1,80}', value['reason']), 'TERMINAL_INVALID')
        raw = regular(self.state / 'first-report.md', self.state, 16384)
        require(digest(raw) == value.get('report_sha256') and raw.decode() == report_text(value), 'REPORT_CHANGED')
        if value['status'] == 'AWAITING_REVIEW':
            require(CYCLE.fullmatch(value['cycle']) and value['snapshot_run'] == 'pilot-' + value['cycle'], 'SNAPSHOT_PATH')
            snapshot = load_run(self.root / 'runs' / value['snapshot_run'])
            require(value['reason'] == 'FIRST_FAILURE' and snapshot['hash'] == value['snapshot_hash']
                    and value['captured_at'] == snapshot['captured_at']
                    and value['runtime_sha'] == self.config()['runtime_sha']
                    and failures(snapshot)[0] == value['failure'], 'OBSERVATION_CHANGED')
        return value

    def pause(self, status, reason, **fields):
        value = {'schema_version': 1, 'status': status, 'reason': reason, 'model_calls': 0,
                 'hermes_auth_reads': 0, **fields}
        raw = report_text(value).encode()
        write_new(self.state / 'first-report.md', raw)
        syncdir(self.state)
        value['report_sha256'] = digest(raw)
        save(self.state / 'terminal.json', value)
        self.notify()
        return value

    def notify(self):
        status = 'UNAVAILABLE'
        try:
            if sys.platform == 'darwin':
                result = subprocess.run(['/usr/bin/osascript', '-e', 'on run argv', '-e',
                    'display notification (item 1 of argv) with title "Hermes 初回点検"', '-e', 'end run',
                    '--', '点検を停止しました。確認: ' + str(self.state / 'first-report.md')],
                    capture_output=True, timeout=5, check=False)
                status = 'SUBMITTED' if result.returncode == 0 else 'FAILED'
        except (OSError, subprocess.TimeoutExpired):
            status = 'FAILED'
        # Notification delivery is not acceptance; the immutable report is the source of truth.
        save(self.state / 'notification.json', {'status': status})

    def stop_requested(self):
        return SIGNALLED or os.path.lexists(self.state / 'stop.requested')

    def terminate(self, child):
        try:
            require(os.getpgid(child.pid) == child.pid, 'CHILD_IDENTITY_UNCONFIRMED')
            os.killpg(child.pid, signal.SIGTERM)
            # Keep the leader unreaped until the final group signal: its PID cannot be reused.
            time.sleep(0.25)
            try:
                os.killpg(child.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            child.wait(timeout=5)
        except (OSError, subprocess.TimeoutExpired):
            raise EvaluationError('CHILD_CLEANUP_UNCONFIRMED') from None

    def collect(self, output, cycle):
        log = cycle / 'collect.log'
        fd = os.open(log, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
        child = None
        try:
            with os.fdopen(fd, 'wb') as stream:
                child = subprocess.Popen([sys.executable, '-I', '-B', str(self.root / 'scripts/report_github_work_guide.py'),
                                          'collect', '--out', str(output)], cwd=self.root,
                                         stdout=stream, stderr=stream, start_new_session=True)
                deadline = time.monotonic() + 210
                try:
                    while child.poll() is None:
                        require(not self.stop_requested(), 'STOP_REQUESTED')
                        self.capacity()
                        require(time.monotonic() < deadline, 'COLLECT_TIMEOUT')
                        time.sleep(0.25)
                    require(child.returncode == 0, 'COLLECT_FAILED')
                finally:
                    if child.poll() is None:
                        self.terminate(child)
                stream.flush()
                os.fsync(stream.fileno())
        finally:
            syncdir(cycle)

    def tick(self):
        self.path_check()
        if os.path.lexists(self.state / 'unverified.stop'):
            return {'status': 'STOPPED', 'reason': 'PILOT_UNVERIFIED'}
        if not os.path.lexists(self.state / 'config.json'):
            return {'status': 'NOT_CONFIGURED'}
        with self.lock():
            try:
                if os.path.lexists(self.state / 'terminal.json'):
                    return self.terminal()
                require(not os.path.lexists(self.state / 'first-report.md'), 'RECOVERY_REQUIRED')
                cfg = self.config()
                if not cfg['enabled']:
                    return {'status': 'DISABLED'}
                require(not self.stop_requested(), 'STOP_REQUESTED')
                rows = self.cycles()
                require(len(rows) < MAX_CHECKS, 'CHECK_LIMIT')
                self.capacity()
                self.runtime(cfg['runtime_sha'])
                identity = f'{len(rows)+1:03d}-' + uuid.uuid4().hex
                cycle = self.state / 'cycles' / identity
                cycle.mkdir(mode=0o700)
                syncdir(cycle.parent)
                output = self.root / 'runs' / ('pilot-' + identity)
                self.collect(output, cycle)
                require(not self.stop_requested(), 'STOP_REQUESTED')
                require(self.config() == cfg, 'CONFIG_CHANGED')
                self.capacity()
                self.runtime(cfg['runtime_sha'])
                snapshot = load_run(output)
                complete(snapshot)
                observed = failures(snapshot)
                value = {'cycle': identity, 'snapshot_run': output.name, 'snapshot_hash': snapshot['hash'],
                         'runtime_sha': cfg['runtime_sha'], 'captured_at': snapshot['captured_at']}
                if observed:
                    return self.pause('AWAITING_REVIEW', 'FIRST_FAILURE', failure=observed[0], **value)
                value.update(status='CLEAR', model_calls=0, hermes_auth_reads=0)
                save(cycle / 'result.json', value)
                return value
            except (EvaluationError, Invalid, OSError, ValueError, KeyError, TypeError, AttributeError, IndexError):
                error = sys.exc_info()[1]
                reason = str(error) if isinstance(error, EvaluationError) and re.fullmatch('[A-Z_]{1,80}', str(error)) else 'INSPECTION_UNVERIFIED'
                if not os.path.lexists(self.state / 'terminal.json') and not os.path.lexists(self.state / 'first-report.md'):
                    return self.pause('STOPPED', reason)
                return {'status': 'STOPPED', 'reason': reason}

    def status(self):
        self.path_check()
        if not self.state.exists():
            return {'status': 'NOT_CONFIGURED'}
        if os.path.lexists(self.state / 'unverified.stop'):
            return {'status': 'STOPPED', 'reason': 'PILOT_UNVERIFIED'}
        with self.lock():
            if os.path.lexists(self.state / 'terminal.json'):
                return self.terminal()
            cfg = self.config()
            rows = self.cycles()
            status = 'STOP_REQUESTED' if self.stop_requested() else 'MONITORING' if cfg['enabled'] else 'DISABLED'
            return {'status': status,
                    'completed_checks': len(rows), 'model_calls': 0, 'hermes_auth_reads': 0}

    def stop(self):
        self.path_check()
        if not self.state.exists():
            return {'status': 'NOT_CONFIGURED', 'model_calls': 0}
        try:
            save(self.state / 'stop.requested', {'reason': 'USER_STOP'})
        except FileExistsError:
            pass  # Concurrent/repeated stop requests preserve the first marker.
        return {'status': 'STOP_REQUESTED', 'model_calls': 0}


def main(argv=None):
    global SIGNALLED
    SIGNALLED = False
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('configure', 'tick', 'status', 'stop'))
    parser.add_argument('--runtime-sha')
    args = parser.parse_args(argv)
    pilot = Pilot()
    signal.signal(signal.SIGCHLD, signal.SIG_DFL)
    for kind in (signal.SIGTERM, signal.SIGINT):
        signal.signal(kind, lambda *_: globals().__setitem__('SIGNALLED', True))
    try:
        if args.action == 'configure':
            value = pilot.configure(args.runtime_sha)
        else:
            require(args.runtime_sha is None, 'UNEXPECTED_RUNTIME_OPTION')
            value = getattr(pilot, args.action)()
    except (EvaluationError, Invalid, OSError, ValueError, KeyError, TypeError, AttributeError, IndexError) as error:
        if isinstance(error, EvaluationError) and str(error) == 'CONCURRENT_RUN':
            value = {'status': 'RUNNING' if args.action == 'status' else 'BUSY', 'reason': 'CONCURRENT_RUN'}
        else:
            if args.action == 'tick':
                try:
                    pilot.block_unverified()
                except OSError:
                    pass  # A read-only/full filesystem cannot persist a marker; no request was authorized.
            value = {'status': 'STOPPED', 'reason': 'PILOT_UNVERIFIED'}
    value.setdefault('model_calls', 0)
    value.setdefault('hermes_auth_reads', 0)
    print(canonical(value).decode())
    return 2 if value['status'] == 'STOPPED' else 0


if __name__ == '__main__':
    raise SystemExit(main())
