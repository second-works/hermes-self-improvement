"""One evaluated PUBLIC candidate, durable intents and explicit recovery approval.

The supervisor owns registry/approvals/journal. Candidate workers receive none of
these paths. This is a fixture harness, not a same-OS-user authorization system.
"""
from contextlib import contextmanager
from datetime import datetime, timezone
import difflib
import fcntl
import os
from pathlib import Path, PurePosixPath
import re
import stat
import subprocess
import tempfile
import uuid

from evaluation.core import EvaluationError, canonical, digest, load_json, regular, require, write_new

CANDIDATE = 'e3153fec973051b28178df0656db05d2a3ffae84'
BASELINE = '65c53babda8f31405d54941e900c2d3987efa4b1'
EVALUATION = 'e15519cd9488daa211d51fedb1d7f2a804eb38952a9e915211fc3d3934874183'
BUNDLE = '4d373fca8040eea381c6266eb3d469e04699fee4413a02bbb3b5bc79448bc048'
ARTIFACT = 'scripts/review.py'
IMAGE = 'sha256:eb7d16fec874f15b584063275012ac719885a2b87574d124c0da9c156d504629'
LIMIT = 65536
DIRECTORY = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW


def utc():
    return datetime.now(timezone.utc).isoformat()


def stamp(value):
    require(type(value) is str and len(value) <= 40, 'APPROVAL_TIME')
    try:
        result = datetime.fromisoformat(value.replace('Z', '+00:00'))
        require(result.tzinfo is not None, 'APPROVAL_TIME')
        return result.timestamp()
    except ValueError:
        raise EvaluationError('APPROVAL_TIME') from None


def identifier(value):
    require(type(value) is str and re.fullmatch(r'[a-z0-9][a-z0-9-]{0,63}', value), 'IDENTIFIER')
    return value


def relative(value):
    require(type(value) is str and len(value) <= 160, 'ARTIFACT_PATH')
    parts = PurePosixPath(value).parts
    require(parts and not value.startswith('/') and all(re.fullmatch(r'[a-zA-Z0-9_.-]+', p)
            and p not in ('.', '..') for p in parts) and '/'.join(parts) == value, 'ARTIFACT_PATH')
    return parts


def syncdir(path):
    fd = os.open(path, DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def save(path, value):
    write_new(path, canonical(value) + b'\n')
    syncdir(path.parent)


def read(path):
    return load_json(regular(path, path.parent, 2 * 1024 * 1024))


def source_packet(repo):
    """Verify pinned independent evidence and extract bytes without importing code."""
    art = repo / 'artifacts/generated-repair/issue-33'
    report_bytes = regular(art / 'report.json', repo)
    report, audit = load_json(report_bytes), read(art / 'audit.json')
    require(digest(report_bytes) == EVALUATION == audit['report_hash'] and
            audit['audit'] == 'VERIFIED' and report['decision']['status'] == 'PASS' and
            report['candidate_sha'] == CANDIDATE and report['baseline_sha'] == BASELINE and
            report['manifest_hash'] == audit['manifest_hash'], 'EVALUATION_IDENTITY')
    require(digest(regular(art / 'candidate.bundle', repo, 2 * 1024 * 1024)) == BUNDLE, 'BUNDLE_HASH')
    with tempfile.TemporaryDirectory() as directory:
        def git(*args):
            try:
                return subprocess.check_output(['git', '-c', 'core.hooksPath=/dev/null', '-C', directory,
                    *args], stderr=subprocess.PIPE, timeout=15,
                    env={'PATH': '/usr/bin:/bin:/opt/homebrew/bin', 'GIT_CONFIG_NOSYSTEM': '1',
                         'GIT_CONFIG_GLOBAL': '/dev/null', 'GIT_TERMINAL_PROMPT': '0'})
            except (subprocess.SubprocessError, OSError):
                raise EvaluationError('BUNDLE_INVALID') from None
        git('init', '--template=', '--initial-branch=inspection')
        git('fetch', '--no-tags', str(art / 'candidate.bundle'), CANDIDATE)
        git('merge-base', '--is-ancestor', BASELINE, CANDIDATE)
        require(git('diff', '--name-only', BASELINE, CANDIDATE).decode().splitlines() == [ARTIFACT], 'DIFF_SCOPE')
        versions = {}
        for label, sha in [('baseline', BASELINE), ('candidate', CANDIDATE)]:
            require(git('ls-tree', sha, ARTIFACT).startswith(b'100644 blob '), 'ARTIFACT_TYPE')
            data = git('show', sha + ':' + ARTIFACT)
            require(len(data) <= LIMIT and digest(data) == report['artifact_hashes'][label], 'ARTIFACT_HASH')
            versions[label] = data
        require(git('show', BASELINE + ':public.json') == regular(art / 'public.json', repo), 'PUBLIC_CHANGED')
    patch = ''.join(difflib.unified_diff(versions['baseline'].decode().splitlines(True),
        versions['candidate'].decode().splitlines(True), fromfile='a/' + ARTIFACT, tofile='b/' + ARTIFACT, n=0))
    packet = {'schema_version': 1, 'classification': 'PUBLIC', 'issue': 8,
        'repository': 'second-works/hermes-self-improvement', 'baseline_sha': BASELINE,
        'candidate_sha': CANDIDATE, 'evaluation_hash': EVALUATION, 'bundle_hash': BUNDLE,
        'artifact_path': ARTIFACT, 'before_hash': digest(versions['baseline']),
        'after_hash': digest(versions['candidate']), 'diff_hash': digest(patch.encode()),
        'public_hash': digest(regular(art / 'public.json', repo)), 'allowlist': [ARTIFACT], 'evaluation': report['decision'], 'counts': report['counts'],
        'unverified': ['Human fixture adoption and recovery acceptance', 'General quality and production'],
        'merge_is_adoption': False}
    return packet, versions, patch


class Controller:
    def __init__(self, repo, area):
        self.repo, self.area = Path(repo).resolve(), Path(area).absolute()
        require(self.area.is_relative_to(self.repo / 'runs') and
                self.area != self.repo / 'runs' and '..' not in self.area.parts, 'CONTROL_BOUNDARY')
        # Reject symlink ancestors, including runs and the control area.
        for p in [self.repo, *reversed(self.area.relative_to(self.repo).parents), self.area.relative_to(self.repo)]:
            target = p if p == self.repo else self.repo / p
            require(not target.is_symlink(), 'CONTROL_SYMLINK')

    def initialize(self):
        require(not self.area.exists(), 'CONTROL_EXISTS')
        self.area.mkdir(parents=True, mode=0o700)
        for name in ('targets', 'approvals', 'snapshots'):
            (self.area / name).mkdir(mode=0o700)
        packet, versions, patch = source_packet(self.repo)
        save(self.area / 'packet.json', packet)
        for label, data in versions.items():
            write_new(self.area / (label + '.py'), data)
        write_new(self.area / 'diff.patch', patch.encode())
        syncdir(self.area)
        return packet

    def packet(self):
        expected, _, _ = source_packet(self.repo)
        require(read(self.area / 'packet.json') == expected, 'PACKET_CHANGED')
        for label, field in [('baseline', 'before_hash'), ('candidate', 'after_hash')]:
            require(digest(regular(self.area / (label + '.py'), self.area, LIMIT)) == expected[field], 'ARTIFACT_HASH')
        return expected

    def register(self, environment, target, root):
        identifier(environment); identifier(target)
        root = Path(root).absolute()
        require(root.is_relative_to(self.area / 'fixtures') and root != self.area / 'fixtures', 'ROOT_BOUNDARY')
        relative(root.relative_to(self.area).as_posix())
        with self.guard():
            with self.open_directory(root) as fd:
                info = os.fstat(fd)
                binding = {'environment_id': environment, 'target_id': target, 'root': str(root),
                           'device': info.st_dev, 'inode': info.st_ino, 'version': 1}
            for file in (self.area / 'targets').glob('*.json'):
                if file.name.endswith('.intent-lock.json'):
                    continue
                row = read(file)
                require(row['root'] != str(root) and
                        (row['device'], row['inode']) != (info.st_dev, info.st_ino), 'ROOT_ALREADY_REGISTERED')
            bound = dict(binding, root_binding_hash=digest(canonical(binding)))
            # The human can inspect this concrete snapshot before approving.
            # Registration is not adoption and never changes destination bytes.
            with self.open_directory(root):
                original = regular(root / ARTIFACT, self.area, LIMIT)
            require(digest(original) == self.packet()['before_hash'], 'BASELINE_CHANGED')
            write_new(self.area / 'snapshots' / (target + '.baseline.py'), original)
            syncdir(self.area / 'snapshots')
            save(self.area / 'targets' / (target + '.json'), binding)
            return bound

    @contextmanager
    def guard(self):
        # OS lock serializes commands; durable journal lock remains across process death.
        fd = os.open(self.area / 'supervisor.lock', os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
        try:
            require(stat.S_ISREG(os.fstat(fd).st_mode), 'LOCK_TYPE')
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise EvaluationError('CONCURRENT_OPERATION') from None
            yield
        finally:
            os.close(fd)

    @contextmanager
    def open_directory(self, path):
        require(path.is_relative_to(self.area), 'ROOT_BOUNDARY')
        relative(path.relative_to(self.area).as_posix())
        fd = os.open(self.area, DIRECTORY)
        try:
            for part in path.relative_to(self.area).parts:
                child = os.open(part, DIRECTORY, dir_fd=fd)
                os.close(fd); fd = child
            yield fd
        finally:
            os.close(fd)

    def binding(self, target):
        row = read(self.area / 'targets' / (identifier(target) + '.json'))
        require(set(row) == {'environment_id','target_id','root','device','inode','version'} and
                row['target_id'] == target and row['version'] == 1, 'REGISTRY_INVALID')
        root = Path(row['root'])
        require(root.is_absolute() and root.is_relative_to(self.area / 'fixtures'), 'ROOT_BOUNDARY')
        with self.open_directory(root) as fd:
            info = os.fstat(fd)
            require(root.resolve() == root and (info.st_dev, info.st_ino) ==
                    (row['device'], row['inode']), 'ROOT_REPLACED')
        return dict(row, root_binding_hash=digest(canonical(row)))

    @contextmanager
    def destination(self, binding, path):
        parts = relative(path)
        require(self.binding(binding['target_id']) == binding, 'ROOT_REPLACED')
        with self.open_directory(Path(binding['root'])) as rootfd:
            fd = os.dup(rootfd)
            try:
                for part in parts[:-1]:
                    child = os.open(part, DIRECTORY, dir_fd=fd)
                    os.close(fd); fd = child
                yield fd, parts[-1]
            finally:
                os.close(fd)

    def actual(self, binding, path):
        with self.destination(binding, path) as (parent, name):
            try:
                fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
            except FileNotFoundError:
                return None, None
            try:
                info = os.fstat(fd)
                require(stat.S_ISREG(info.st_mode) and info.st_nlink == 1 and info.st_size <= LIMIT, 'DESTINATION_TYPE')
                data = os.read(fd, LIMIT + 1)
                require(len(data) <= LIMIT, 'DESTINATION_SIZE')
                return digest(data), data
            finally:
                os.close(fd)

    def events(self, target):
        file = self.area / 'targets' / (identifier(target) + '.journal')
        if not file.exists():
            require(not file.is_symlink(), 'JOURNAL_TYPE')
            return []
        rows = [load_json(line) for line in regular(file, self.area, 2 * 1024 * 1024).splitlines()]
        previous = '0' * 64
        for i, row in enumerate(rows):
            body = {k:v for k,v in row.items() if k != 'hash'}
            require(row.get('previous') == previous and row.get('sequence') == i and
                    digest(canonical(body)) == row.get('hash'), 'JOURNAL_INVALID')
            previous = row['hash']
        require(rows, 'JOURNAL_INVALID')
        return rows

    def event(self, target, state, details):
        rows = self.events(target)
        row = {'sequence': len(rows), 'previous': rows[-1]['hash'] if rows else '0' * 64,
               'at': utc(), 'state': state, 'details': details}
        row['hash'] = digest(canonical(row))
        file = self.area / 'targets' / (target + '.journal')
        fd = os.open(file, os.O_WRONLY | os.O_APPEND | os.O_CREAT | os.O_NOFOLLOW, 0o600)
        try:
            data = canonical(row) + b'\n'
            require(os.write(fd, data) == len(data), 'JOURNAL_WRITE')
            os.fsync(fd)
        finally:
            os.close(fd)
        syncdir(file.parent)
        return row

    def state(self, target):
        rows = self.events(target)
        if not rows:
            lock = self.area / 'targets' / (identifier(target) + '.intent-lock.json')
            return 'RECOVERY_REQUIRED' if lock.exists() or lock.is_symlink() else 'AWAITING_APPROVAL'
        state = rows[-1]['state']
        return 'RECOVERY_REQUIRED' if state in ('ADOPTING', 'ROLLING_BACK') else state

    def request(self, target, operation, expires_at, actor):
        require(operation in ('ADOPT', 'ROLLBACK'), 'OPERATION')
        require(type(actor) is str and re.fullmatch(r'[A-Za-z0-9_.@-]{1,80}', actor), 'ACTOR')
        packet, binding = self.packet(), self.binding(target)
        current, _ = self.actual(binding, packet['artifact_path'])
        require(operation == 'ADOPT' and self.state(target) == 'AWAITING_APPROVAL' or
                operation == 'ROLLBACK' and self.state(target) == 'RECOVERY_REQUIRED', 'STATE')
        request = {k:packet[k] for k in ('baseline_sha','candidate_sha','evaluation_hash',
                   'artifact_path','before_hash','after_hash')}
        request.update({k:binding[k] for k in ('environment_id','target_id','root','root_binding_hash')})
        request.update(schema_version=1, operation=operation, current_hash=current,
                       actor=actor, issued_at=utc(), expires_at=expires_at)
        if operation == 'ADOPT':
            backup = target + '.baseline.py'
            data = regular(self.area / 'snapshots' / backup, self.area, LIMIT)
            require(digest(data) == packet['before_hash'], 'BACKUP_CHANGED')
            request['backup'] = backup
            request['backup_hash'] = digest(data)
        if operation == 'ROLLBACK':
            intent = self.intent(target)
            request['backup_hash'] = intent['backup_hash']
            request['intent_hash'] = digest(canonical(intent))
            request['observation_event_hash'] = self.events(target)[-1]['hash']
        require(0 < stamp(expires_at) - stamp(request['issued_at']) <= 86400, 'APPROVAL_TIME')
        return request

    def approve(self, request, *, confirmation):
        # The explicit supervisor action, never a worker/PR-merge side effect.
        require(confirmation == digest(canonical(request)), 'CONFIRMATION')
        with self.guard():
            self.validate(request)
            key = digest(canonical(request))
            save(self.area / 'approvals' / (key + '.json'), request)
        return key

    def validate(self, approval):
        require(type(approval) is dict, 'APPROVAL_SCHEMA')
        expected = self.request(approval['target_id'], approval['operation'], approval['expires_at'], approval['actor'])
        expected['issued_at'] = approval['issued_at']
        require(approval == expected, 'APPROVAL_BINDING')
        now = datetime.now(timezone.utc).timestamp()
        require(stamp(approval['issued_at']) <= now < stamp(approval['expires_at']) and
                0 < stamp(approval['expires_at']) - stamp(approval['issued_at']) <= 86400, 'APPROVAL_EXPIRED')
        if approval['operation'] == 'ADOPT':
            require(approval['current_hash'] == approval['before_hash'], 'BASELINE_CHANGED')
        else:
            self.backup(self.intent(approval['target_id']))
        return self.binding(approval['target_id'])

    def intent(self, target):
        rows = [r for r in self.events(target) if r['state'] == 'ADOPTING']
        require(len(rows) == 1, 'INTENT_MISSING')
        intent = rows[0]['details']
        require(read(self.area / 'targets' / (identifier(target) + '.intent-lock.json')) == intent, 'INTENT_LOCK_MISMATCH')
        return intent

    def backup(self, intent):
        path = self.area / 'snapshots' / intent['backup']
        relative(intent['backup'])
        data = regular(path, self.area, LIMIT)
        require(digest(data) == intent['backup_hash'] == self.packet()['before_hash'], 'BACKUP_CHANGED')
        return data

    def replace(self, binding, path, data, expected):
        require(self.actual(binding, path)[0] == expected, 'CURRENT_CHANGED')
        with self.destination(binding, path) as (parent, name):
            temp = '.adoption-' + uuid.uuid4().hex
            fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=parent)
            try:
                with os.fdopen(fd, 'wb') as stream:
                    stream.write(data); stream.flush(); os.fsync(stream.fileno())
                # Recheck registry and all path components immediately before rename.
                require(self.binding(binding['target_id']) == binding and
                        self.actual(binding, path)[0] == expected, 'CURRENT_CHANGED')
                os.rename(temp, name, src_dir_fd=parent, dst_dir_fd=parent)
                os.fsync(parent)
            finally:
                try:
                    os.unlink(temp, dir_fd=parent)
                except FileNotFoundError:
                    pass
        require(self.actual(binding, path)[0] == digest(data), 'WRITE_HASH')

    def execute(self, approval_hash, regression):
        require(type(approval_hash) is str and re.fullmatch('[a-f0-9]{64}', approval_hash), 'APPROVAL_HASH')
        with self.guard():
            approval = read(self.area / 'approvals' / (approval_hash + '.json'))
            require(digest(canonical(approval)) == approval_hash, 'APPROVAL_HASH')
            binding = self.validate(approval)
            target, operation = approval['target_id'], approval['operation']
            packet = self.packet()
            # Every attempt consumes a ticket; failed recovery needs a new observation/approval.
            save(self.area / 'approvals' / (approval_hash + '.used'),
                 {'approval_hash':approval_hash, 'attempted_at':utc()})
            if operation == 'ADOPT':
                _, original = self.actual(binding, packet['artifact_path'])
                backup = approval['backup']
                require(digest(regular(self.area / 'snapshots' / backup, self.area, LIMIT)) ==
                        digest(original) == approval['backup_hash'], 'BACKUP_CHANGED')
                intent = dict(approval, approval_hash=approval_hash, backup=backup, backup_hash=digest(original))
                save(self.area / 'targets' / (target + '.intent-lock.json'), intent)
                self.event(target, 'ADOPTING', intent)
                data = regular(self.area / 'candidate.py', self.area, LIMIT)
            else:
                intent = self.intent(target)
                data = self.backup(intent)
                self.event(target, 'ROLLING_BACK', dict(approval, approval_hash=approval_hash))
            # Any exception/kill after the durable intent is recovery-required.
            try:
                self.replace(binding, packet['artifact_path'], data, approval['current_hash'])
                require(regression(Path(binding['root']) / packet['artifact_path'], operation) is True,
                        'REGRESSION_FAILED')
                require(self.actual(binding, packet['artifact_path'])[0] == digest(data), 'WRITE_HASH')
                return self.event(target, 'ADOPTED' if operation == 'ADOPT' else 'ROLLED_BACK',
                    {'approval_hash': approval_hash, 'actual_hash': digest(data),
                     'regression': 'PASS', 'operation': operation})
            except Exception:
                self.event(target, 'RECOVERY_REQUIRED', {'approval_hash': approval_hash, 'reason': 'WRITE_OR_REGRESSION_FAILED'})
                raise

    def observe(self, target, regression):
        with self.guard():
            require(self.state(target) == 'ADOPTED', 'STATE')
            try:
                packet, binding = self.packet(), self.binding(target)
                require(self.actual(binding, packet['artifact_path'])[0] == packet['after_hash'], 'DRIFT')
                require(regression(Path(binding['root']) / packet['artifact_path'], 'ADOPT') is True, 'REGRESSION_FAILED')
                # Snapshot success must still agree with the live root and bytes.
                require(self.actual(binding, packet['artifact_path'])[0] == packet['after_hash'], 'DRIFT')
            except Exception:
                self.event(target, 'RECOVERY_REQUIRED', {'reason': 'DRIFT_OR_REGRESSION'})
                raise
            return 'ADOPTED'
