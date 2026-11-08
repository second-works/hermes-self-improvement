"""Local append-only JSONL ledger for skill improvement records (#107).

The ledger only stores what a person types in and what the approved manifest allows. It never
fetches evidence, calls a model or the network, or writes outside the approved ledger directory.
A corrupt ledger stops every command; nothing is repaired, dropped or appended silently.
"""
from contextlib import contextmanager
from datetime import date, datetime, timezone
import errno
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import time
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from skill_improvement import schema

ROOT = Path(__file__).resolve().parents[2]
SCHEMAS = ROOT / 'schemas' / 'skill-improvement'
LEDGER_FILE = 'ledger.jsonl'
LOCK_FILE = 'ledger.lock'
MAX_LEDGER_BYTES = 32 * 1024 * 1024
MAX_MANIFEST_BYTES = 1024 * 1024
LOCK_WAIT_SECONDS = 10
DIRECTORY = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
LEVELS = ('PUBLIC', 'INTERNAL', 'CONFIDENTIAL')
EXPERIENCE_TYPES = ('CORRECTION', 'REWORK', 'REPEATED_FEEDBACK', 'BETTER_METHOD')
CAUSES = ('MISSING_PROCEDURE', 'NOT_LOADED', 'NOT_FOLLOWED', 'TEMPORARY', 'CONFLICT_OR_UNVERIFIED', 'DUPLICATE')
# Evidence is stored as a reference string only. Each kind needs the manifest read item it names.
REF_KINDS = {'input': 'EXPLICIT_INPUT', 'end': 'END_RECORD', 'pr-review': 'PR_REVIEW_COMMENT',
             'commit': 'COMMIT_MESSAGE', 'path': None, 'synthetic': None}
SEGMENT = r'[A-Za-z0-9._-]+'
SECRET_LIKE = re.compile(r'(gh[pousr]_[A-Za-z0-9]|github_pat_|glpat-|(?<![A-Za-z0-9])sk-[A-Za-z0-9_-]{16}|AKIA[0-9A-Z]{16}'
                         r'|AIza[0-9A-Za-z_-]{20}|xox[abprs]-|-----BEGIN [A-Z ]*PRIVATE KEY'
                         r'|(password|passwd|secret|token|api[_-]?key|access[_-]?key)\s*[:=])', re.IGNORECASE)
# Initial candidate state follows the cause table in docs/skill-improvement-mvp.md section 4.
CAUSE_INITIAL_STATE = {
    'TEMPORARY': {'status': 'DECLINED', 'reason': '一時事情でありSkillを変更しない'},
    'CONFLICT_OR_UNVERIFIED': {'status': 'HOLD', 'reason': '既存規則との競合または根拠未確認のため確認まで保留'},
}


class LedgerError(Exception):
    def __init__(self, code, detail=''):
        super().__init__(code if not detail else f'{code}: {detail}')
        self.code = code
        self.detail = detail


def require(condition, code, detail=''):
    if not condition:
        raise LedgerError(code, detail)


def utc_now():
    return datetime.now(timezone.utc).replace(microsecond=0)


def utc_text(moment):
    return moment.astimezone(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


def short_hash(*parts):
    return hashlib.sha256(schema.canonical(list(parts))).hexdigest()[:16]


def _reject_duplicate_keys(pairs):
    keys = [key for key, _ in pairs]
    if len(keys) != len(set(keys)):
        raise ValueError('duplicate key')
    return dict(pairs)


def _reject_constant(name):
    raise ValueError(f'non-standard constant {name}')


def strict_json(text):
    return json.loads(text, object_pairs_hook=_reject_duplicate_keys, parse_constant=_reject_constant)


def load_contract():
    return {name: strict_json((SCHEMAS / file).read_text(encoding='utf-8')) for name, file in (
        ('ledger', 'ledger-record.schema.json'), ('manifest', 'repository-manifest.schema.json'),
        ('transitions', 'state-transitions.json'))}


def _read_regular(fd, limit, code):
    info = os.fstat(fd)
    require(stat.S_ISREG(info.st_mode) and info.st_nlink == 1, code, 'not a single regular file')
    require(info.st_size <= limit, code, 'too large')
    chunks, total = [], 0
    while True:
        chunk = os.read(fd, 1024 * 1024)
        if not chunk:
            break
        chunks.append(chunk)
        total += len(chunk)
        require(total <= limit, code, 'too large')
    return b''.join(chunks)


class Manifest:
    """An approved repository manifest, validated once at the boundary."""

    def __init__(self, data, contract, now):
        found = schema.errors(data, contract['manifest'])
        require(not found, 'MANIFEST_INVALID', '; '.join(found[:3]))
        listed = [item['repository_id'] for item in data['repositories']]
        require(len(listed) == len(set(listed)), 'MANIFEST_DUPLICATE_REPOSITORY')
        require(data['approval']['approved_at'] <= utc_text(now), 'MANIFEST_NOT_APPROVED')
        require(data['period']['start_date'] <= data['period']['end_date'], 'MANIFEST_INVALID', 'period')
        try:
            self.zone = ZoneInfo(data['timezone'])
        except (ZoneInfoNotFoundError, ValueError):
            raise LedgerError('MANIFEST_INVALID', 'timezone') from None
        self.data = data
        self.repositories = {item['repository_id']: item for item in data['repositories']}

    @classmethod
    def load(cls, path, contract, now):
        try:
            fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        except OSError as error:
            raise LedgerError('MANIFEST_UNREADABLE', error.strerror or '') from None
        try:
            data = _read_regular(fd, MAX_MANIFEST_BYTES, 'MANIFEST_UNREADABLE')
        finally:
            os.close(fd)
        try:
            return cls(strict_json(data.decode('utf-8')), contract, now)
        except (UnicodeDecodeError, ValueError, RecursionError):
            raise LedgerError('MANIFEST_INVALID', 'not strict JSON') from None

    def repository(self, repository_id):
        require(repository_id in self.repositories, 'REPOSITORY_NOT_IN_MANIFEST', repository_id)
        return self.repositories[repository_id]

    def today(self, now):
        return now.astimezone(self.zone).date().isoformat()

    def check_work_date(self, work_date, now):
        try:
            parsed = date.fromisoformat(work_date)
        except (TypeError, ValueError):
            raise LedgerError('WORK_DATE_INVALID', str(work_date)) from None
        require(parsed.isoformat() == work_date, 'WORK_DATE_INVALID', work_date)
        require(work_date <= self.today(now), 'WORK_DATE_IN_FUTURE', work_date)
        period = self.data['period']
        require(period['start_date'] <= work_date <= period['end_date'], 'OUTSIDE_PERIOD', work_date)

    def classification(self, repository_id, requested):
        """Records default to the repository's class; a request may only make it stricter."""
        base = self.repository(repository_id)['classification']
        if requested is None:
            return base
        require(requested != 'UNKNOWN', 'CLASSIFICATION_UNKNOWN',
                '分類が決まるまで台帳へ記録せず保留する')
        require(requested in LEVELS, 'CLASSIFICATION_INVALID', str(requested))
        require(LEVELS.index(requested) >= LEVELS.index(base), 'CLASSIFICATION_DOWNGRADE', requested)
        return requested

    def check_location(self, classification):
        if self.data['ledger_location']['kind'] == 'PUBLIC_FIXTURE':
            require(classification == 'PUBLIC', 'CLASSIFICATION_NOT_PUBLIC',
                    'PUBLIC_FIXTUREの台帳にはPUBLICの記録だけを置く')

    def check_ref(self, repository_id, ref):
        require(type(ref) is str and 1 <= len(ref) <= 200 and '\n' not in ref, 'REF_INVALID', repr(ref)[:40])
        kind, sep, value = ref.partition(':')
        require(sep and value and kind in REF_KINDS, 'REF_KIND_NOT_ALLOWED', kind)
        needed = REF_KINDS[kind]
        if needed:
            require(needed in self.repository(repository_id)['read_items'], 'REF_NOT_ALLOWED_BY_MANIFEST', kind)
        if kind == 'synthetic':
            require(self.data['ledger_location']['kind'] == 'PUBLIC_FIXTURE', 'REF_KIND_NOT_ALLOWED', kind)
        if kind == 'commit':
            require(re.fullmatch(r'[0-9a-f]{7,40}', value), 'REF_INVALID', 'commit')
        if kind == 'path':
            require(re.fullmatch(rf'{SEGMENT}(/{SEGMENT})*', value) and
                    not any(part in ('.', '..') for part in value.split('/')), 'REF_PATH_OUTSIDE_ROOTS', value)
            roots = self.repository(repository_id)['allowed_roots']
            require(any(value == root or value.startswith(root + '/') for root in roots),
                    'REF_PATH_OUTSIDE_ROOTS', value)


def check_text(value, code, limit, one_line=True):
    require(type(value) is str and 1 <= len(value) <= limit, code, 'length')
    require(not (one_line and ('\n' in value or '\r' in value)), code, 'must be one line')
    require(not SECRET_LIKE.search(value), 'SECRET_LIKE_INPUT', '秘密値らしい文字列は記録しない')


def ledger_directory(path, manifest):
    """The ledger directory must be the approved, symlink-free location named by the manifest."""
    location = manifest.data['ledger_location']
    directory = Path(path)
    require(directory.is_absolute(), 'LEDGER_PATH_INVALID', 'absolute path required')
    # macOS firmlinks make /System/Volumes/Data/<path> another name for /<path>; only the short form is accepted.
    require(not inside(directory, '/System/Volumes/Data'), 'LEDGER_PATH_INVALID',
            'use the path without /System/Volumes/Data')
    # Path comparison only, before anything touches the file system: the Hermes home is never opened,
    # listed or resolved. Case is folded because the default macOS file system ignores it.
    require(not inside(directory, Path.home() / '.hermes'), 'LEDGER_IN_HERMES_HOME')
    require(os.path.realpath(directory) == str(directory), 'LEDGER_PATH_INVALID',
            'symlinks and non-canonical paths are not allowed')
    require(directory.name == location['label'], 'LEDGER_LABEL_MISMATCH', directory.name)
    if location['kind'] == 'APPROVED_LOCAL_DIRECTORY':
        # Real data stays out of every git checkout, not only the one running this code.
        require(not inside(directory, ROOT) and
                not any(os.path.lexists(folder / '.git') for folder in (directory, *directory.parents)),
                'LEDGER_INSIDE_REPOSITORY', '実データの台帳を公開source/fixtureと混在させない')
    return directory


def inside(path, parent):
    path, parent = str(path).casefold(), str(parent).casefold().rstrip('/')
    return path == parent or path.startswith(parent + '/')


def durable_sync(fd):
    # On macOS fsync may leave data in the drive cache; F_FULLFSYNC asks the drive to flush it.
    if hasattr(fcntl, 'F_FULLFSYNC'):
        try:
            fcntl.fcntl(fd, fcntl.F_FULLFSYNC)
            return
        except OSError:
            pass
    os.fsync(fd)


class Ledger:
    def __init__(self, directory, manifest, contract, clock=utc_now):
        self.directory = ledger_directory(directory, manifest)
        self.manifest = manifest
        self.contract = contract
        self.clock = clock

    @contextmanager
    def _open_directory(self):
        # Walk from / one component at a time so no component can be swapped for a symlink.
        fd = os.open('/', DIRECTORY)
        try:
            for part in self.directory.parts[1:]:
                try:
                    child = os.open(part, DIRECTORY, dir_fd=fd)
                except OSError as error:
                    raise LedgerError('LEDGER_DIRECTORY_UNAVAILABLE', error.strerror or '') from None
                os.close(fd)
                fd = child
            yield fd
        finally:
            os.close(fd)

    @contextmanager
    def _locked(self, dirfd):
        try:
            fd = os.open(LOCK_FILE, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600, dir_fd=dirfd)
        except OSError as error:
            raise LedgerError('LOCK_UNAVAILABLE', error.strerror or '') from None
        try:
            require(stat.S_ISREG(os.fstat(fd).st_mode), 'LOCK_UNAVAILABLE', 'not a regular file')
            deadline = time.monotonic() + LOCK_WAIT_SECONDS
            while True:
                try:
                    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except BlockingIOError:
                    require(time.monotonic() < deadline, 'LOCK_TIMEOUT')
                    time.sleep(0.05)
            yield
        finally:
            os.close(fd)

    def _read_bytes(self, dirfd):
        try:
            fd = os.open(LEDGER_FILE, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=dirfd)
        except FileNotFoundError:
            return b''
        except OSError as error:
            raise LedgerError('LEDGER_CORRUPT', f'cannot open: {error.strerror}') from None
        try:
            return _read_regular(fd, MAX_LEDGER_BYTES, 'LEDGER_CORRUPT')
        finally:
            os.close(fd)

    def parse(self, data):
        """Parse and check every line. Any defect stops the command and leaves the file as is."""
        if not data:
            return []
        require(data.endswith(b'\n'), 'LEDGER_CORRUPT', 'last line is incomplete (partial write)')
        rows = []
        for number, line in enumerate(data.split(b'\n')[:-1], start=1):
            try:
                row = strict_json(line.decode('utf-8'))
            except (UnicodeDecodeError, ValueError, RecursionError):
                raise LedgerError('LEDGER_CORRUPT', f'line {number} is not strict JSON') from None
            rows.append(row)
        check_rows(rows, self.contract, self.manifest)
        return rows

    def read(self):
        with self._open_directory() as dirfd, self._locked(dirfd):
            return self.parse(self._read_bytes(dirfd))

    def append(self, build):
        """Under the lock: read, build new rows from the current rows, check, then append durably."""
        with self._open_directory() as dirfd, self._locked(dirfd):
            data = self._read_bytes(dirfd)
            rows = self.parse(data)
            new_rows, outcome = build(rows)
            if not new_rows:
                return outcome
            self._check_new(rows, new_rows)
            try:
                check_rows(rows + new_rows, self.contract, self.manifest)
            except LedgerError as error:
                raise LedgerError('NEW_ROW_REJECTED', error.detail) from None
            payload = b''.join(schema.canonical(row) + b'\n' for row in new_rows)
            require(len(data) + len(payload) <= MAX_LEDGER_BYTES, 'LEDGER_FULL',
                    'appending would exceed the readable size; start a new approved ledger')
            self._write(dirfd, len(data), payload)
            return outcome

    def _write(self, dirfd, expected_size, payload):
        fd = os.open(LEDGER_FILE, os.O_WRONLY | os.O_APPEND | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600,
                     dir_fd=dirfd)
        try:
            info = os.fstat(fd)
            require(stat.S_ISREG(info.st_mode) and info.st_nlink == 1 and info.st_size == expected_size,
                    'LEDGER_CHANGED', 'ledger changed outside the lock')
            try:
                written = os.write(fd, payload)
                require(written == len(payload), 'WRITE_FAILED', 'short write')
                durable_sync(fd)
            except (OSError, LedgerError) as error:
                # Restore the original length so a half-written line never stays behind.
                try:
                    os.ftruncate(fd, expected_size)
                    durable_sync(fd)
                except OSError:
                    raise LedgerError('WRITE_FAILED_RECOVERY_REQUIRED',
                                      'the ledger may end with a partial line; restore it by hand') from None
                code = error.code if isinstance(error, LedgerError) else 'WRITE_FAILED'
                raise LedgerError(code, getattr(error, 'detail', '') or str(error)) from None
        finally:
            os.close(fd)
        try:
            os.fsync(dirfd)
        except OSError as error:
            raise LedgerError('WRITE_UNCONFIRMED', f'rows were written but the directory sync failed: {error.strerror}') from None

    # ----- row construction -----

    def _check_new(self, rows, new_rows):
        now = self.clock()
        latest = max((row['recorded_at'] for row in rows), default='')
        for row in new_rows:
            # New rows never go back in time, so the append order and the recorded time agree.
            require(row['recorded_at'] >= latest, 'CLOCK_REGRESSION', f"{row['recorded_at']} < {latest}")
            self.manifest.check_work_date(row['work_date'], now)
            self.manifest.check_location(row['classification'])

    def _envelope(self, repository_id, work_unit_id, work_date, classification, event_id, record):
        return {'schema_version': 1, 'event_id': event_id, 'recorded_at': utc_text(self.clock()),
                'work_date': work_date,
                'timezone': self.manifest.data['timezone'], 'repository_id': repository_id,
                'work_unit_id': work_unit_id, 'classification': classification, 'record': record}

    def record_end(self, repository_id, work_unit_id, result, work_date=None, reason=None,
                   experiences=(), classification=None):
        """Record one session end. Re-sending the same input is a no-op; changed input is refused."""
        self.manifest.repository(repository_id)
        require(type(work_unit_id) is str and re.fullmatch(r'[a-z0-9][a-z0-9-]{0,63}', work_unit_id),
                'WORK_UNIT_INVALID', str(work_unit_id))
        level = self.manifest.classification(repository_id, classification)
        work_date = work_date or self.manifest.today(self.clock())
        experiences = list(experiences)
        if result == 'CANDIDATE_FOUND':
            require(1 <= len(experiences) <= 16, 'EXPERIENCE_REQUIRED', '候補ありは経験を1〜16件')
            require(reason is None, 'REASON_NOT_ALLOWED', 'CANDIDATE_FOUND')
        elif result == 'NO_CANDIDATE':
            require(not experiences and reason is None, 'NO_CANDIDATE_TAKES_NO_DETAILS')
        elif result == 'UNDETERMINED':
            require(not experiences, 'UNDETERMINED_TAKES_NO_EXPERIENCE')
            require(reason is not None, 'REASON_REQUIRED', '判定未完了は理由を残す')
            check_text(reason, 'REASON_INVALID', 200)
        else:
            raise LedgerError('RESULT_UNKNOWN', str(result))
        end_event = 'e-' + short_hash('end', repository_id, work_unit_id)
        planned = []
        for index, item in enumerate(experiences):
            require(type(item) is dict and set(item) <= {'type', 'summary', 'refs', 'cause'} and
                    {'type', 'summary', 'refs'} <= set(item), 'EXPERIENCE_INVALID', f'experience {index + 1}')
            require(item['type'] in EXPERIENCE_TYPES, 'EXPERIENCE_TYPE_UNKNOWN', str(item['type']))
            cause = item.get('cause', 'UNCLASSIFIED')
            require(cause == 'UNCLASSIFIED' or cause in CAUSES, 'CAUSE_UNKNOWN', str(cause))
            check_text(item['summary'], 'SUMMARY_INVALID', 120)
            refs = item['refs']
            require(type(refs) is list and 1 <= len(refs) <= 8 and len(set(map(str, refs))) == len(refs),
                    'REFS_INVALID', '根拠参照を1〜8件、重複なく')
            for ref in refs:
                self.manifest.check_ref(repository_id, ref)
                require(not SECRET_LIKE.search(ref), 'SECRET_LIKE_INPUT')
            experience_id = 'x-' + short_hash('experience', repository_id, work_unit_id, index)
            planned.append(('e-' + short_hash('experience-event', experience_id), {
                'kind': 'experience', 'experience_id': experience_id, 'end_event_id': end_event,
                'experience_type': item['type'], 'summary': item['summary'], 'evidence_refs': list(refs),
                'cause': cause}))
        end_record = {'kind': 'session_end', 'status': result}
        if result == 'CANDIDATE_FOUND':
            end_record['experience_ids'] = [record['experience_id'] for _, record in planned]
        if result == 'UNDETERMINED':
            end_record['reason'] = reason

        def build(rows):
            new = [self._envelope(repository_id, work_unit_id, work_date, level, end_event, end_record)]
            new += [self._envelope(repository_id, work_unit_id, work_date, level, event, record)
                    for event, record in planned]
            existing = [row for row in rows if row['event_id'] == end_event or
                        row['record'].get('end_event_id') == end_event]
            if existing:
                require([comparable(row) for row in existing] == [comparable(row) for row in new],
                        'WORK_UNIT_ALREADY_ENDED', f'{repository_id}/{work_unit_id}')
                return [], {'status': 'ALREADY_RECORDED', 'event_ids': [row['event_id'] for row in existing],
                            'experience_ids': end_record.get('experience_ids', [])}
            return new, {'status': 'RECORDED', 'event_ids': [row['event_id'] for row in new],
                         'experience_ids': end_record.get('experience_ids', [])}

        return self.append(build)

    def propose(self, repository_id, work_unit_id, experience_ids, target_skill_id, cause,
                scope=None, duplicate_of=None, work_date=None, classification=None):
        """Turn recorded experiences into one candidate, linking same-basis proposals as DUPLICATE."""
        self.manifest.repository(repository_id)
        require(type(work_unit_id) is str and re.fullmatch(r'[a-z0-9][a-z0-9-]{0,63}', work_unit_id),
                'WORK_UNIT_INVALID', str(work_unit_id))
        require(type(target_skill_id) is str and re.fullmatch(r'[a-z0-9][a-z0-9-]{0,63}', target_skill_id),
                'TARGET_SKILL_INVALID', str(target_skill_id))
        require(cause in CAUSES, 'CAUSE_UNKNOWN', str(cause))
        experience_ids = sorted(set(experience_ids))
        require(1 <= len(experience_ids) <= 16, 'EXPERIENCE_REQUIRED')
        scope = scope or {'type': 'REPOSITORY_LOCAL'}
        if 'contract_ref' in scope:
            check_text(scope['contract_ref'], 'SCOPE_INVALID', 200)
        require((cause == 'DUPLICATE') == (duplicate_of is not None), 'DUPLICATE_TARGET_REQUIRED',
                '原因がDUPLICATEのときだけ元候補を指定する')
        work_date = work_date or self.manifest.today(self.clock())
        candidate_id = 'c-' + short_hash('candidate', target_skill_id, experience_ids)

        def build(rows):
            experiences = {row['record']['experience_id']: row for row in rows
                           if row['record']['kind'] == 'experience'}
            missing = [item for item in experience_ids if item not in experiences]
            require(not missing, 'EXPERIENCE_NOT_FOUND', ', '.join(missing))
            if scope['type'] == 'SHARED' and scope.get('basis') == 'REPEATED_IN_REPOSITORIES':
                sources = {experiences[item]['repository_id'] for item in experience_ids}
                for listed in scope['repository_ids']:
                    self.manifest.repository(listed)
                require(set(scope['repository_ids']) <= sources, 'SHARED_BASIS_NOT_SHOWN',
                        '共通化の根拠repoそれぞれに経験が必要')
            requested_level = self.manifest.classification(repository_id, classification)

            def basis(item):
                # References are local to their repository: pr-review:7 in two repositories is two things.
                row = experiences[item]
                return {(row['repository_id'], ref) for ref in row['record']['evidence_refs']}
            candidates = candidate_rows(rows)
            if candidate_id in candidates:
                first = candidates[candidate_id][0]['record']
                same = (first['cause'], first['scope'], first['target_skill_id']) == (cause, scope, target_skill_id)
                same = same and (duplicate_of is None or first['state'].get('duplicate_of') == duplicate_of)
                require(same, 'CANDIDATE_CONFLICT', candidate_id)
                # A retry may not silently drop a stricter classification than the one recorded.
                recorded = candidates[candidate_id][-1]['classification']
                require(LEVELS.index(requested_level) <= LEVELS.index(recorded), 'CANDIDATE_CONFLICT',
                        f'{candidate_id} is recorded as {recorded}')
                return [], {'status': 'ALREADY_RECORDED', 'candidate_id': candidate_id,
                            'state': candidates[candidate_id][-1]['record']['state']}
            refs = set().union(*(basis(item) for item in experience_ids))
            original, shared = None, []
            if duplicate_of is not None:
                require(duplicate_of in candidates, 'DUPLICATE_TARGET_MISSING', duplicate_of)
                original = duplicate_of
            else:
                for other, history in candidates.items():
                    head = history[0]['record']
                    # DUPLICATE candidates count too: their own experiences are a basis already in use.
                    if head['target_skill_id'] != target_skill_id:
                        continue
                    overlap = [item for item in head['experience_ids'] if item in experience_ids or
                               basis(item) & refs]
                    if overlap:
                        original = other
                        break
            if original is not None:
                head = candidates[original][0]['record']
                shared = [item for item in head['experience_ids'] if item in experience_ids or
                          basis(item) & refs]
                require(shared, 'DUPLICATE_BASIS_MISSING', '元候補と同じ経験または根拠が必要')
                state = {'status': 'DUPLICATE', 'duplicate_of': original,
                         'reason': f'同じ根拠の候補{original}が既にある'}
            else:
                state = dict(CAUSE_INITIAL_STATE.get(cause, {'status': 'OPEN'}))
            linked = sorted(set(experience_ids) | set(shared))
            # The candidate is as strict as the strictest evidence it finally cites, including linked experiences.
            level = max([requested_level] + [experiences[item]['classification'] for item in linked], key=LEVELS.index)
            require(len(linked) <= 16, 'EXPERIENCE_REQUIRED', 'too many experiences')
            record = {'kind': 'candidate', 'candidate_id': candidate_id, 'experience_ids': linked,
                      'target_skill_id': target_skill_id, 'cause': cause, 'scope': scope, 'state': state}
            event = 'e-' + short_hash('candidate-event', candidate_id, None, state)
            row = self._envelope(repository_id, work_unit_id, work_date, level, event, record)
            return [row], {'status': 'RECORDED', 'candidate_id': candidate_id, 'state': state,
                           'event_ids': [event]}

        return self.append(build)

    def set_state(self, candidate_id, status, reason, duplicate_of=None, work_date=None,
                  repository_id=None, work_unit_id=None):
        """Append a candidate state change allowed by the #106 transition table."""
        require(status in ('OPEN', 'HOLD', 'DECLINED', 'DUPLICATE'), 'STATE_NOT_ALLOWED_HERE',
                'DEPLOYED / ROLLED_BACK は配備の記録で扱い、このCLIでは書かない')
        state = {'status': status}
        if status != 'OPEN':
            check_text(reason, 'REASON_INVALID', 200)
            state['reason'] = reason
        else:
            require(reason is None, 'REASON_NOT_ALLOWED', 'OPEN')
        if status == 'DUPLICATE':
            require(duplicate_of is not None, 'DUPLICATE_TARGET_REQUIRED')
            state = {'status': status, 'duplicate_of': duplicate_of, 'reason': reason}
        else:
            require(duplicate_of is None, 'DUPLICATE_TARGET_NOT_ALLOWED')
        work_date = work_date or self.manifest.today(self.clock())

        def build(rows):
            history = candidate_rows(rows).get(candidate_id)
            require(history, 'CANDIDATE_NOT_FOUND', candidate_id)
            latest = history[-1]
            if latest['record']['state'] == state:
                return [], {'status': 'ALREADY_RECORDED', 'candidate_id': candidate_id, 'state': state}
            record = dict(latest['record'], state=state)
            if status == 'DUPLICATE':
                others = candidate_rows(rows)
                require(duplicate_of in others and duplicate_of != candidate_id,
                        'DUPLICATE_TARGET_MISSING', duplicate_of)
                original = {item for entry in others[duplicate_of] for item in entry['record']['experience_ids']}
                require(original & set(record['experience_ids']), 'DUPLICATE_BASIS_MISSING',
                        '元候補と同じ経験を根拠に含む必要がある')
            repository = repository_id or latest['repository_id']
            level = self.manifest.classification(repository, None)
            level = max(level, latest['classification'], key=LEVELS.index)
            event = 'e-' + short_hash('candidate-event', candidate_id, latest['event_id'], state)
            row = self._envelope(repository, work_unit_id or latest['work_unit_id'], work_date,
                                 level, event, record)
            return [row], {'status': 'RECORDED', 'candidate_id': candidate_id, 'state': state,
                           'event_ids': [event]}

        return self.append(build)


def comparable(row):
    """A row without its append time, used to recognise a re-sent request."""
    return {key: value for key, value in row.items() if key != 'recorded_at'}


def candidate_rows(rows):
    found = {}
    for row in rows:
        if row['record']['kind'] == 'candidate':
            found.setdefault(row['record']['candidate_id'], []).append(row)
    return found


def check_rows(rows, contract, manifest):
    """Whole-ledger checks: schema, unique IDs, links between records, and candidate transitions."""
    seen, ends, ended, experiences, candidates = set(), {}, set(), {}, {}
    transitions = contract['transitions']['candidate']
    for number, row in enumerate(rows, start=1):
        where = f'line {number}'
        found = schema.errors(row, contract['ledger'])
        require(not found, 'LEDGER_CORRUPT', f'{where}: ' + '; '.join(found[:3]))
        require(row['event_id'] not in seen, 'LEDGER_CORRUPT', f'{where}: duplicate event_id')
        seen.add(row['event_id'])
        require(row['repository_id'] in manifest.repositories, 'LEDGER_CORRUPT',
                f'{where}: repository not in manifest')
        require(LEVELS.index(row['classification']) >=
                LEVELS.index(manifest.repositories[row['repository_id']]['classification']), 'LEDGER_CORRUPT',
                f'{where}: classification weaker than the manifest')
        require(row['timezone'] == manifest.data['timezone'], 'LEDGER_CORRUPT', f'{where}: timezone differs from manifest')
        require(manifest.data['ledger_location']['kind'] != 'PUBLIC_FIXTURE' or row['classification'] == 'PUBLIC',
                'LEDGER_CORRUPT', f'{where}: non-PUBLIC row in a PUBLIC_FIXTURE ledger')
        record = row['record']
        if record['kind'] == 'session_end':
            key = (row['repository_id'], row['work_unit_id'])
            require(key not in ended, 'LEDGER_CORRUPT', f'{where}: second session_end for one work unit')
            ended.add(key)
            ends[row['event_id']] = row
        elif record['kind'] == 'experience':
            end = ends.get(record['end_event_id'])
            require(end is not None and end['record']['status'] == 'CANDIDATE_FOUND' and
                    record['experience_id'] in end['record']['experience_ids'] and
                    (end['repository_id'], end['work_unit_id']) == (row['repository_id'], row['work_unit_id']),
                    'LEDGER_CORRUPT', f'{where}: experience not listed by its session_end')
            require(record['experience_id'] not in experiences, 'LEDGER_CORRUPT', f'{where}: duplicate experience')
            experiences[record['experience_id']] = row
        elif record['kind'] == 'candidate':
            missing = [item for item in record['experience_ids'] if item not in experiences]
            require(not missing, 'LEDGER_CORRUPT', f'{where}: unknown experience {missing[0] if missing else ""}')
            strictest = max((experiences[item]['classification'] for item in record['experience_ids']),
                            key=LEVELS.index)
            require(LEVELS.index(row['classification']) >= LEVELS.index(strictest), 'LEDGER_CORRUPT',
                    f'{where}: candidate weaker than its evidence classification')
            history = candidates.get(record['candidate_id'], [])
            status = record['state']['status']
            if history:
                previous = history[-1]['record']
                require({k: v for k, v in previous.items() if k != 'state'} ==
                        {k: v for k, v in record.items() if k != 'state'}, 'LEDGER_CORRUPT',
                        f'{where}: candidate fields changed outside its state')
                allowed = transitions['transitions'][previous['state']['status']]
            else:
                allowed = transitions['initial']
            require(status in allowed, 'LEDGER_CORRUPT', f'{where}: candidate transition to {status}')
            if status == 'DUPLICATE':
                target = record['state']['duplicate_of']
                require(target in candidates and target != record['candidate_id'], 'LEDGER_CORRUPT',
                        f'{where}: DUPLICATE points to an unknown candidate')
                original = {item for entry in candidates[target] for item in entry['record']['experience_ids']}
                require(original & set(record['experience_ids']), 'LEDGER_CORRUPT',
                        f'{where}: DUPLICATE shares no experience with its original')
            candidates.setdefault(record['candidate_id'], []).append(row)
    for event_id, end in ends.items():
        listed = end['record'].get('experience_ids', [])
        require(all(item in experiences and experiences[item]['record']['end_event_id'] == event_id
                    for item in listed), 'LEDGER_CORRUPT', f'session_end {event_id} lists a missing experience')


def summary(rows):
    """Counts for checking a reload. One session end counts once, however many experiences it has."""
    ends, states = {}, {}
    for row in rows:
        if row['record']['kind'] == 'session_end':
            ends[row['record']['status']] = ends.get(row['record']['status'], 0) + 1
    for history in candidate_rows(rows).values():
        status = history[-1]['record']['state']['status']
        states[status] = states.get(status, 0) + 1
    return {'rows': len(rows), 'session_ends': ends,
            'experiences': sum(row['record']['kind'] == 'experience' for row in rows),
            'candidates': states}
