"""Pure, deterministic contracts shared by the controller and its tests."""
import hashlib
import json
import math
import os
from pathlib import Path
import re
import stat


class EvaluationError(Exception):
    """Only fixed reason codes may cross the reporting boundary."""


def require(condition, code):
    if not condition:
        raise EvaluationError(code)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'),
                      ensure_ascii=True, allow_nan=False).encode()


def digest(data):
    return hashlib.sha256(data).hexdigest()


def regular(path, root, limit=262144):
    """Reject aliases and special files before reading trusted controller inputs."""
    path, root = Path(path).absolute(), Path(root).absolute()
    require(path.is_relative_to(root) and '..' not in path.parts, 'PATH_BOUNDARY')
    for part in [root, *path.relative_to(root).parents]:
        target = part if part == root else root / part
        require(not target.is_symlink(), 'PATH_SYMLINK')
    require(not path.is_symlink(), 'PATH_SYMLINK')
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        info = os.fstat(fd)
        require(stat.S_ISREG(info.st_mode) and info.st_size <= limit, 'FILE_BOUNDARY')
        data = os.read(fd, limit + 1)
        require(len(data) <= limit, 'FILE_BOUNDARY')
        return data
    finally:
        os.close(fd)


def write_new(path, data):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'wb') as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())


def load_json(data):
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, 'JSON_DUPLICATE')
            result[key] = value
        return result
    try:
        return json.loads(data, object_pairs_hook=pairs,
                          parse_constant=lambda _: (_ for _ in ()).throw(EvaluationError('JSON_NUMBER')))
    except (ValueError, UnicodeError, RecursionError):
        raise EvaluationError('JSON_INVALID') from None


def findings(value):
    require(type(value) is dict and set(value) == {'findings', 'cpu_seconds'}, 'OUTPUT_SCHEMA')
    cpu = value['cpu_seconds']
    require(type(cpu) in (int, float) and math.isfinite(cpu) and 0 <= cpu <= 30, 'OUTPUT_CPU')
    rows = value['findings']
    require(type(rows) is list and len(rows) <= 32, 'OUTPUT_FINDINGS')
    result = []
    for row in rows:
        require(type(row) is dict and set(row) == {'path', 'line', 'rule'}, 'OUTPUT_FINDING_SCHEMA')
        require(type(row['path']) is str and re.fullmatch(r'case_[a-z0-9]{8,32}\.py', row['path']),
                'OUTPUT_PATH')
        require(type(row['line']) is int and 1 <= row['line'] <= 1000, 'OUTPUT_LINE')
        require(row['rule'] in ('dynamic-eval', 'shell-execution'), 'OUTPUT_RULE')
        result.append((row['path'], row['line'], row['rule']))
    require(len(set(result)) == len(result), 'OUTPUT_DUPLICATE')
    return sorted(result), cpu


def policy():
    return {'version': 1, 'public_cases': 10, 'hidden_cases': 10, 'repeats': 3,
            'minimum_gain': 1, 'maximum_latency_ratio': 1.2, 'maximum_cost_ratio': 1.2,
            'case_timeout_seconds': 30, 'run_timeout_seconds': 1200,
            'candidate_count': 1, 'api_calls': 0, 'api_cost_usd': 0,
            'quality': 'exact finding set; case median; no regression',
            'claim': 'finite deterministic fixture only'}


def judge(baseline, candidate, *, safety, same_artifact=False, contaminated=False):
    """Known failures dominate missing evidence; neither can be promoted to PASS."""
    failed = []
    held = []
    if safety is False:
        failed.append('SAFETY_VIOLATION')
    elif safety is not True:
        held.append('SAFETY_NOT_VERIFIED')
    expected = {'correct', 'failures', 'latency', 'cost_usd'}
    if not (type(baseline) is dict and type(candidate) is dict and
            set(baseline) == expected and set(candidate) == expected):
        held.append('METRICS_MISSING')
    else:
        b, c = baseline, candidate
        valid = all(type(x['correct']) is list and len(x['correct']) == 20 and
                    all(type(v) is bool for v in x['correct']) and
                    type(x['failures']) is int and 0 <= x['failures'] <= 60 and
                    type(x['latency']) in (int, float) and math.isfinite(x['latency']) and x['latency'] > 0 and
                    type(x['cost_usd']) in (int, float) and math.isfinite(x['cost_usd']) and x['cost_usd'] >= 0
                    for x in (b, c))
        if not valid:
            held.append('METRICS_INVALID')
        else:
            if any(old and not new for old, new in zip(b['correct'], c['correct'])):
                failed.append('REGRESSION')
            if c['failures'] > b['failures']:
                failed.append('FAILURE_RATE_INCREASE')
            if c['latency'] > b['latency'] * 1.2:
                failed.append('LATENCY_LIMIT')
            if c['cost_usd'] > b['cost_usd'] * 1.2 or c['cost_usd'] != 0:
                failed.append('COST_LIMIT')
            if sum(c['correct'][10:]) < sum(b['correct'][10:]) + 1:
                held.append('INSUFFICIENT_GAIN')
    if same_artifact:
        held.append('UNCHANGED_ARTIFACT')
    if contaminated:
        held.append('EVALUATION_CONTAMINATED')
    return {'status': 'FAIL' if failed else 'HOLD' if held else 'PASS',
            'reasons': failed + held}
