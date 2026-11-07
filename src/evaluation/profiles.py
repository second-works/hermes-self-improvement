"""Registered PUBLIC skill contracts. Candidate text is data, never host code."""
from dataclasses import asdict, dataclass
import difflib
import re
import secrets

from .core import EvaluationError, canonical, digest, findings, judge, load_json, require
from delegation.generated import git


@dataclass(frozen=True)
class Profile:
    id: str
    skill: str
    artifacts: tuple
    entrypoint: str
    reproduction_index: int

    @property
    def hash(self):
        return digest(canonical(asdict(self)))


REVIEW = 'fixtures/skills/github-code-review/review.py'
COUNTS = 'fixtures/skills/event-status-counts/'
PROFILES = {
    'review-multiline-shell-v1': Profile('review-multiline-shell-v1', 'review-builtin',
        (REVIEW,), REVIEW, 10),
    'event-status-counts-v1': Profile('event-status-counts-v1', 'event-status-counts',
        (COUNTS + 'SKILL.md', COUNTS + 'scripts/aggregate.py', COUNTS + 'scripts/helpers.py'),
        COUNTS + 'scripts/aggregate.py', 2),
}


def public_text(value):
    # Same known-key families as Security Preflight, checked before forming a prompt.
    pattern = (r'ghp_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|sk-[A-Za-z0-9-]{20,}|'
               r'AKIA[0-9A-Z]{16}|xox[baprs]-[A-Za-z0-9-]{20,}|'
               r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----')
    require(not re.search(pattern, value, re.IGNORECASE), 'PROFILE_SENSITIVE_SOURCE')
    return value


def profile(name):
    require(type(name) is str and name in PROFILES, 'NEEDS_PROFILE')
    return PROFILES[name]


def artifacts(repo, sha, selected):
    require(type(sha) is str and re.fullmatch('[a-f0-9]{40}', sha), 'BASELINE_SHA')
    require(git(repo, 'cat-file', '-t', sha).strip() == b'commit', 'BASELINE_COMMIT')
    result = {}
    for path in selected.artifacts:
        tree = git(repo, 'ls-tree', sha, '--', path).split()
        require(len(tree) == 4 and tree[:2] == [b'100644', b'blob'], 'SOURCE_TYPE')
        size = git(repo, 'cat-file', '-s', sha + ':' + path).strip()
        require(size.isdigit() and 0 < int(size) <= 65536, 'SOURCE_SIZE')
        result[path] = public_text(git(repo, 'show', sha + ':' + path).decode('utf-8'))
    require(sum(len(s.encode()) for s in result.values()) <= 65536, 'SOURCE_SIZE')
    return result


def hashes(files):
    return {p: digest(s.encode()) for p, s in files.items()}


def count_cases(hidden=False):
    category = secrets.token_hex(4) if hidden else 'build'
    event = {'category': category, 'status': 'ok'}
    values = [[], [event], [event, event], [event, {'category': category, 'status': 'failed'}]]
    rows = []
    for events in values:
        counts = {}
        for row in events:
            counts.setdefault(row['category'], {'ok': 0, 'failed': 0})[row['status']] += 1
        rows.append({'stdin': canonical({'events': events}).decode(), 'expected': {'counts': counts}, 'exit': 0})
    invalid = ['{"events":[],"events":[]}', canonical({'events': [{'category': category, 'status': 'other'}]}).decode()]
    rows.extend({'stdin': raw, 'expected': {'error': 'INVALID_INPUT'}, 'exit': 2} for raw in invalid)
    return rows


def cases(selected, review_cases, hidden=False):
    if selected.id == 'event-status-counts-v1':
        return count_cases(hidden)
    return [{'stdin': canonical(c['input']).decode(), 'expected': c['expected'], 'exit': 0}
            for c in review_cases(hidden, multiline=True)]


def observe(selected, outcome, case):
    failure = bool(outcome['error'] or outcome['stderr'] or outcome['oom']
                   or outcome['exit'] != case['exit'] or outcome['container_exit'] != case['exit'])
    answer = None
    if not failure:
        try:
            answer = load_json(outcome['stdout'])
            if selected.id == 'review-multiline-shell-v1':
                answer, _ = findings(answer)
                answer = [list(row) for row in answer]
        except (EvaluationError, ValueError, TypeError, KeyError):
            # Never expose a candidate's output or exception text.
            failure = True
    correct = not failure and canonical(answer) == canonical(case['expected'])
    return {'correct': correct, 'failed': failure, 'safety_failure': bool(outcome['error'] or outcome['oom']),
            'answer_hash': digest(canonical(answer)),
            'wall_seconds': outcome['wall_seconds'], 'reported_cpu_seconds': None}


def response(value, selected):
    require(type(value) is dict and type(value.get('schema_version')) is int
            and value['schema_version'] == 1, 'PROFILE_RESPONSE_SCHEMA')
    decision = value.get('decision')
    require(decision in ('PROPOSE', 'HOLD', 'NO_CHANGE'), 'PROFILE_DECISION')
    required = {'schema_version', 'decision', 'reason', 'evidence_refs'}
    require(set(value) == required | ({'edits'} if decision == 'PROPOSE' else set()), 'PROFILE_RESPONSE_SCHEMA')
    require(type(value['reason']) is str and bool(value['reason'].strip())
            and len(value['reason']) <= 1024, 'PROFILE_REASON')
    refs = value['evidence_refs']
    require(type(refs) is list and refs and all(type(r) is str for r in refs)
            and len(refs) == len(set(refs)) and set(refs) <= {
                '/reproduction_sha256', '/profile_context/manifest_hash'}, 'PROFILE_EVIDENCE')
    if decision == 'PROPOSE':
        edits = value['edits']
        require(type(edits) is list and 1 <= len(edits) <= 4, 'PROFILE_EDITS')
        paths, total = set(), 0
        for edit in edits:
            require(type(edit) is dict and set(edit) == {'path', 'before', 'after'}, 'PROFILE_EDIT_SCHEMA')
            path, before, after = (edit[k] for k in ('path', 'before', 'after'))
            require(type(path) is str and path in selected.artifacts and path not in paths, 'PROFILE_EDIT_PATH')
            require(type(before) is str and bool(before.strip()) and type(after) is str
                    and before != after and '\x00' not in before + after, 'PROFILE_EDIT_TEXT')
            public_text(before + after)
            total += len(before.encode()) + len(after.encode())
            require(total <= 16384, 'PROFILE_EDIT_SIZE')
            paths.add(path)
    require(len(canonical(value)) <= 32768, 'PROFILE_RESPONSE_SIZE')
    return {k: v for k, v in value.items() if k != 'schema_version'}


def apply(files, edits):
    result = dict(files)
    for edit in edits:
        path = edit['path']
        require(path in files and files[path].count(edit['before']) == 1, 'PROFILE_EDIT_BINDING')
        result[path] = files[path].replace(edit['before'], edit['after'], 1)
    require(sum(len(s.encode()) for s in result.values()) <= 65536, 'CANDIDATE_SIZE')
    return result


def diff(before, after):
    return ''.join(''.join(difflib.unified_diff(before[p].splitlines(True), after[p].splitlines(True),
                   fromfile='a/' + p, tofile='b/' + p)) for p in sorted(before) if before[p] != after[p])


def decision(metrics, *, safety, unstable, public_count, hidden_count, edits):
    kwargs = {'safety': safety, 'contaminated': unstable,
              'public_count': public_count, 'hidden_count': hidden_count}
    result = judge(metrics['baseline'], metrics['candidate'], **kwargs)
    control = judge(metrics['baseline'], metrics['degraded'], **kwargs)
    state = 'REJECTED' if result['status'] == 'FAIL' else 'HOLD'
    if result['status'] == 'PASS' and control['status'] == 'FAIL' and all(metrics['candidate']['correct']):
        state = 'AWAITING_HUMAN_APPROVAL'
    elif result['status'] == 'PASS':
        result = {'status': 'HOLD', 'reasons': ['PROFILE_REQUIRED_CASES_OR_CONTROL_INVALID']}
    if any(edit['path'].endswith('.md') for edit in edits):
        state = 'HOLD'
        result = {'status': 'HOLD', 'reasons': ['STRUCTURE_ONLY_SEMANTIC_EVALUATION_REQUIRED']}
    return state, result, control


def launcher(files, selected):
    """Package PUBLIC files into one read-only sandbox mount, with no evaluator data."""
    require(set(files) == set(selected.artifacts), 'PROFILE_FILES')
    source = ("import json, pathlib, runpy, sys\n"
              "root = pathlib.Path('/run/work/skill')\n"
              "files = json.loads(" + repr(canonical(files)) + ")\n"
              "for path, text in files.items():\n"
              "    target = root / path\n"
              "    target.parent.mkdir(parents=True, exist_ok=True)\n"
              "    target.write_text(text)\n"
              "    target.chmod(0o444)\n"
              "entry = root / " + repr(selected.entrypoint) + "\n"
              "sys.path.insert(0, str(entry.parent))\n"
              "sys.argv = [str(entry)]\n"
              "runpy.run_path(str(entry), run_name='__main__')\n")
    require(len(source.encode()) <= 65536, 'BUNDLE_SIZE')
    return source.encode()
