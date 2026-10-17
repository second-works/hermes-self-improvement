"""Bounded source intake, physical-line evidence, and conservative rule baseline."""
from dataclasses import dataclass, asdict
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat

STATES = ('needs_check', 'awaiting_approval', 'investigating', 'resolved_in_log', 'hold')
REASONS = ('explicit_open', 'explicit_approval', 'explicit_investigation',
           'linked_success', 'insufficient_context', 'conflicting_evidence',
           'invalid_response', 'missing_response', 'unsupported_format')
MAX_FILE = 262144
MAX_TOTAL = 2097152
MAX_RECORD = 8192


class ContractError(Exception):
    """Only fixed diagnostic codes cross the CLI boundary."""


def require(condition, code):
    if not condition:
        raise ContractError(code)


def canonical(value):
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(',', ':'),
                      allow_nan=False).encode('ascii')


def digest(data):
    return hashlib.sha256(data).hexdigest()


def identifier(prefix, value):
    return prefix + digest(canonical(value))


def decode(data):
    def pairs(items):
        out = {}
        for key, value in items:
            require(key not in out, 'JSON_DUPLICATE')
            out[key] = value
        return out
    try:
        return json.loads(data, object_pairs_hook=pairs,
                          parse_constant=lambda _: require(False, 'JSON_NUMBER'))
    except (ValueError, UnicodeError, RecursionError):
        raise ContractError('JSON_INVALID') from None


def fields(value, names):
    require(type(value) is dict and set(value) == set(names.split()), 'SCHEMA_FIELDS')


def ident(value):
    require(type(value) is str and re.fullmatch(r'[a-z][a-z0-9-]{0,63}', value), 'IDENTIFIER')


def read_relative(root, relative, limit=MAX_FILE):
    """Walk via directory descriptors; never follow symlinks, even during races."""
    require(type(relative) is str and len(relative) <= 240 and '\x00' not in relative, 'PATH_BOUNDARY')
    p = PurePosixPath(relative)
    require(not p.is_absolute() and p.parts and
            all(part not in ('', '.', '..') for part in relative.split('/')) and
            '\\' not in relative, 'PATH_BOUNDARY')
    root = Path(root).absolute()
    fd = os.open('/', os.O_RDONLY | os.O_DIRECTORY)
    try:
        for part in root.parts[1:] + p.parts[:-1]:
            new = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = new
        source = os.open(p.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
        try:
            info = os.fstat(source)
            require(stat.S_ISREG(info.st_mode) and info.st_size <= limit, 'FILE_BOUNDARY')
            data = b''
            while len(data) <= limit:
                piece = os.read(source, min(65536, limit + 1 - len(data)))
                if not piece:
                    break
                data += piece
            require(len(data) <= limit, 'FILE_BOUNDARY')
            return data
        finally:
            os.close(source)
    finally:
        os.close(fd)


@dataclass(frozen=True)
class Record:
    record_id: str
    source_id: str
    path: str
    file_sha256: str
    line_start: int
    line_end: int
    text: str
    kind: str
    sequence: int


def parse_records(entry, data):
    try:
        text = data.decode('utf-8')
    except UnicodeError:
        raise ContractError('SOURCE_ENCODING') from None
    # split on LF only: physical line numbers must match the original bytes.
    lines = text.split('\n')
    if len(lines) > 1 and lines[-1] == '':
        lines.pop()
    source = identifier('s-', [entry['path'], entry['sha256']])
    records, pending, start, fence = [], [], 1, None
    unsupported = False

    def line_kind(line):
        if line.startswith(('    ', '\t')):
            return 'code'
        return 'quote' if line.lstrip().startswith('>') else 'narrative'

    def flush(end):
        nonlocal pending
        if not pending:
            return
        body = '\n'.join(pending)
        require(len(body.encode('utf-8')) <= MAX_RECORD, 'RECORD_LIMIT')
        kind = 'code' if fence else line_kind(pending[0])
        records.append(Record(identifier('r-', [source, start, end]), source,
                              entry['path'], entry['sha256'], start, end, body,
                              kind, entry['sequence']))
        pending = []

    for number, line in enumerate(lines, 1):
        marker = re.match(r'^ {0,3}(`{3,}|~{3,})(.*)$', line)
        if fence:
            pending.append(line)
            if marker and marker[1][0] == fence[0] and len(marker[1]) >= len(fence) and not marker[2].strip():
                flush(number)
                fence = None
            continue
        if marker:
            flush(number - 1)
            start, fence, pending = number, marker[1], [line]
        elif re.match(r'^ {0,3}#{1,6}(?:[ \t]|$)', line):
            flush(number - 1)
        elif not line.strip():
            flush(number - 1)
        else:
            if pending and line_kind(pending[0]) != line_kind(line):
                flush(number - 1)
            if not pending:
                start = number
            pending.append(line)
    if fence:
        unsupported = True
    flush(len(lines))
    # A heading-only or empty source has no usable claim, and remains visible.
    if not records:
        body = '\n'.join(lines)
        require(len(body.encode('utf-8')) <= MAX_RECORD, 'RECORD_LIMIT')
        records.append(Record(identifier('r-', [source, 1, len(lines)]), source,
                              entry['path'], entry['sha256'], 1, len(lines), body,
                              'unsupported', entry['sequence']))
        unsupported = True
    return records, unsupported


def load_snapshot(root, manifest_path):
    require(manifest_path.endswith('.json'), 'MANIFEST_PATH')
    raw = read_relative(root, manifest_path)
    manifest = decode(raw)
    fields(manifest, 'schema_version classification source_kind files')
    require(type(manifest['schema_version']) is int and manifest['schema_version'] == 1 and
            manifest['classification'] == 'PUBLIC' and
            manifest['source_kind'] == 'synthetic-fixture', 'SOURCE_BOUNDARY')
    rows = manifest['files']
    require(type(rows) is list and 1 <= len(rows) <= 40, 'FILE_COUNT')
    total, paths, scenarios, grouped = 0, set(), set(), {}
    for entry in rows:
        fields(entry, 'path sha256 session_id task_id scenario_id sequence')
        for name in ('session_id', 'task_id', 'scenario_id'):
            ident(entry[name])
        require(type(entry['sequence']) is int and 0 <= entry['sequence'] <= 10000, 'SEQUENCE')
        require(type(entry['sha256']) is str and re.fullmatch('[a-f0-9]{64}', entry['sha256']), 'HASH_SCHEMA')
        path = entry['path']
        require(type(path) is str and path.startswith('logs/') and path.endswith('.md') and
                path not in paths, 'SOURCE_PATH')
        paths.add(path)
        scenarios.add(entry['scenario_id'])
        require(len(scenarios) <= 20, 'SCENARIO_COUNT')
        data = read_relative(root, path)
        total += len(data)
        require(total <= MAX_TOTAL, 'TOTAL_LIMIT')
        require(digest(data) == entry['sha256'], 'SOURCE_HASH')
        records, unsupported = parse_records(entry, data)
        key = (entry['session_id'], entry['task_id'])
        candidate = grouped.setdefault(key, {'candidate_id': identifier('c-', key),
                                  'session_id': key[0], 'task_id': key[1],
                                  'scenario_id': entry['scenario_id'],
                                  'records': [], 'unsupported': False})
        require(candidate['scenario_id'] == entry['scenario_id'], 'TASK_CONFLICT')
        candidate['records'].extend(records)
        candidate['unsupported'] |= unsupported
    candidates = sorted(grouped.values(), key=lambda c: c['candidate_id'])
    require(len(candidates) <= 64, 'CANDIDATE_LIMIT')
    for candidate in candidates:
        candidate['records'].sort(key=lambda r: (r.sequence, r.path, r.line_start))
        # No silent context truncation. One task is one bounded selection packet.
        require(len(candidate['records']) <= 128, 'RECORD_COUNT')
        require(sum(len(r.text.encode('utf-8')) for r in candidate['records']) <= 32768,
                'CONTEXT_LIMIT')
    return {'manifest_sha256': digest(raw), 'files': rows, 'input_bytes': total,
            'candidates': candidates}


def evidence(candidate):
    return [asdict(r) for r in candidate['records']]


def baseline(candidate):
    """Small explicit phrase baseline; does not claim general semantic accuracy."""
    if candidate['unsupported']:
        return 'hold', 'unsupported_format'
    # Different snapshots at the same declared sequence have no trustworthy order.
    positions, originals = {}, {}
    for r in candidate['records']:
        positions.setdefault(r.sequence, set()).add(r.file_sha256)
        originals.setdefault(r.file_sha256, r.source_id)
    if any(len(hashes) > 1 for hashes in positions.values()):
        return 'hold', 'conflicting_evidence'
    state, reason, had_open = 'hold', 'insufficient_context', False
    seen, per_position = set(), {}
    for record in candidate['records']:
        if record.kind != 'narrative' or record.source_id != originals[record.file_sha256]:
            continue
        text = record.text
        # Exact duplicate claims are counted once, retaining all source references.
        signature = (record.sequence, text)
        if signature in seen:
            continue
        seen.add(signature)
        if re.search(r'文脈不足|ログ欠落|矛盾|別(?:の)?(?:作業|Issue)|命令データ', text):
            return 'hold', 'conflicting_evidence'
        signals = []
        if re.search(r'承認待ち|承認は未取得', text):
            signals.append(('awaiting_approval', 'explicit_approval'))
        if re.search(r'継続調査|原因は未確定', text):
            signals.append(('investigating', 'explicit_investigation'))
        if re.search(r'未確認|未対応|再発|テスト失敗', text):
            signals.append(('needs_check', 'explicit_open'))
        if re.search(r'修正後の再テスト成功|同じ作業の修正と再テストが成功', text):
            signals.append(('resolved_in_log', 'linked_success'))
        if len(signals) > 1:
            return 'hold', 'conflicting_evidence'
        if not signals:
            continue
        next_state, next_reason = signals[0]
        # Conflicting sources at the same declared time are not ordered by filename.
        position = (record.sequence, record.line_start)
        if position in per_position and per_position[position] != next_state:
            return 'hold', 'conflicting_evidence'
        per_position[position] = next_state
        if next_state == 'resolved_in_log' and not had_open:
            return 'hold', 'insufficient_context'
        had_open |= next_state in ('needs_check', 'investigating')
        state, reason = next_state, next_reason
    return state, reason
