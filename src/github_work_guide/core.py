"""Strict snapshots, deterministic instructions and conservative preflight."""
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path

REPO = 'second-works/hermes-self-improvement'
VERSION = 1
REQUIRED = ('ci', 'Security Preflight', 'Analyze (python)')
KINDS = {
    'completion': ('完了範囲確認', 'IssueのDoneと関連PRの実装範囲を人が照合する。'),
    'review': ('レビュー対応準備', '現headのレビューと未解決threadを人が確認する。'),
    'dependency': ('依存確認', '依存先と開始条件を人が確認する。'),
    'plan': ('計画整理', 'GoalとScopeを人が照合して計画を整理する。'),
    'scope': ('対象範囲確認', '対象範囲と保留理由を人が確認する。'),
    'none': ('今回対応不要', '現在状態を確認し、再実装を開始しない。'),
}


class Invalid(ValueError):
    """Untrusted input, incomplete acquisition or unsupported contract."""


def require(ok, message):
    if not ok:
        raise Invalid(message)


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                     separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def now():
    return datetime.now(timezone.utc).isoformat()


def strict_json(text):
    def pairs(entries):
        result = {}
        for key, value in entries:
            require(key not in result, 'duplicate JSON key')
            result[key] = value
        return result
    def constant(_):
        raise Invalid('non-finite JSON')
    try:
        return json.loads(text, object_pairs_hook=pairs, parse_constant=constant)
    except (ValueError, TypeError, RecursionError) as exc:
        raise Invalid('invalid JSON') from exc


def read_json(path):
    path = Path(path)
    require(not path.is_symlink() and path.is_file(), 'input must be a regular file')
    require(path.stat().st_size <= 32_000_000, 'input too large')
    return strict_json(path.read_text(encoding='utf-8'))


def number(value):
    require(type(value) is int and 0 < value < 1_000_000_000, 'invalid number')
    return value


def source_url(kind, n):
    return f'https://github.com/{REPO}/{"issues" if kind == "issue" else "pull"}/{n}'


def seal(items, coverage):
    value = {'version': VERSION, 'repo': REPO, 'classification': 'PUBLIC',
             'captured_at': now(), 'coverage': coverage, 'items': items}
    value['hash'] = digest(value)
    return value


def validate(snapshot):
    require(isinstance(snapshot, dict) and set(snapshot) == {
        'version', 'repo', 'classification', 'captured_at', 'coverage', 'items', 'hash'}, 'snapshot schema')
    require(type(snapshot['version']) is int and snapshot['version'] == VERSION, 'snapshot version')
    require(snapshot['repo'] == REPO and snapshot['classification'] == 'PUBLIC', 'repo/classification')
    try:
        stamp = datetime.fromisoformat(snapshot['captured_at'])
        require(stamp.utcoffset() is not None, 'timestamp timezone')
    except (ValueError, TypeError):
        raise Invalid('invalid timestamp') from None
    require(snapshot['hash'] == digest({k: v for k, v in snapshot.items() if k != 'hash'}), 'snapshot hash')
    cov = snapshot['coverage']
    require(isinstance(cov, dict) and cov.get('status') in ('COMPLETE', 'INCOMPLETE'), 'coverage schema')
    require(isinstance(cov.get('connections'), list) and isinstance(cov.get('errors'), list), 'coverage details')
    require(type(cov.get('calls')) is int and isinstance(cov.get('limits'), dict), 'coverage limits')
    require(isinstance(snapshot['items'], dict), 'items schema')
    for key, item in snapshot['items'].items():
        require(isinstance(item, dict) and set(item) == {
            'kind', 'number', 'state', 'title', 'body', 'url', 'raw', 'hash'}, 'item schema')
        n = number(item['number'])
        require(item['kind'] in ('issue', 'pr') and key == f'{item["kind"]}:{n}', 'item identity')
        require(item['state'] in (('OPEN', 'CLOSED') if item['kind'] == 'issue'
                                  else ('OPEN', 'CLOSED', 'MERGED')), 'item state')
        require(item['url'] == source_url(item['kind'], n), 'item URL')
        require(isinstance(item['title'], str) and isinstance(item['body'], str), 'item text')
        require(item['hash'] == digest(item['raw']), 'source hash')
        require(isinstance(item['raw'], dict), 'source schema')
        raw = item['raw']
        detail = raw['detail']
        require(isinstance(detail, dict), 'detail schema')
        number(detail['number'])
        require(detail['state'] in ('open', 'closed'), 'source state enum')
        require(detail['body'] is None or isinstance(detail['body'], str), 'source body type')
        require(type(detail['comments']) is int and detail['comments'] >= 0, 'source comments count')
        if item['kind'] == 'pr':
            require(type(detail['merged']) is bool, 'merged must be boolean')
        require(detail['number'] == n and detail['html_url'] == item['url'], 'source identity')
        require(detail['title'] == item['title'] and (detail['body'] or '') == item['body'], 'source text')
        state = ('MERGED' if item['kind'] == 'pr' and detail['merged'] else detail['state'].upper())
        require(state == item['state'], 'source state')
        require(isinstance(raw['comments'], list), 'comments missing')
        for comment in raw['comments']:
            require(isinstance(comment, dict) and isinstance(comment.get('body'), str), 'comment schema')
        if item['kind'] == 'pr':
            require(re.fullmatch(r'[0-9a-f]{40}', detail['head']['sha']) is not None, 'head SHA')
            for field in ('checks', 'statuses', 'reviews', 'review_comments', 'threads', 'closing'):
                require(isinstance(raw[field], list), f'{field} missing')
            for check in raw['checks']:
                require(type(check.get('id')) is int and isinstance(check.get('name'), str)
                        and isinstance(check.get('head_sha'), str), 'check identity')
                require(check.get('status') in ('queued', 'in_progress', 'completed', 'waiting', 'requested', 'pending'), 'check state')
            for status in raw['statuses']:
                require(type(status.get('id')) is int and isinstance(status.get('context'), str)
                        and status.get('state') in ('error', 'failure', 'pending', 'success'), 'status schema')
            for review in raw['reviews']:
                require(review.get('state') in ('APPROVED', 'COMMENTED', 'CHANGES_REQUESTED', 'DISMISSED', 'PENDING')
                        and isinstance(review.get('commit_id'), str) and isinstance(review.get('user'), dict), 'review schema')
            for thread in raw['threads']:
                require(type(thread.get('isResolved')) is bool, 'thread schema')
            for closing in raw['closing']:
                number(closing['number'])
                require(isinstance(closing['repository']['nameWithOwner'], str), 'closing relation schema')
    if cov['status'] == 'COMPLETE':
        require(not cov['errors'] and cov['connections'] and
                all(x.get('complete') is True for x in cov['connections']), 'incomplete pagination')
    return snapshot


def complete(snapshot):
    validate(snapshot)
    require(snapshot['coverage']['status'] == 'COMPLETE', 'incomplete acquisition')


def diff(current, previous=None):
    validate(current)
    if previous is not None:
        validate(previous)
    old = previous['items'] if previous else {}
    changes = []
    for key in sorted(old.keys() | current['items'].keys()):
        a, b = old.get(key), current['items'].get(key)
        status = ('UNAVAILABLE' if b is None else 'FIRST' if previous is None else
                  'ADDED' if a is None else 'UNCHANGED' if a['hash'] == b['hash'] else 'CHANGED')
        fields = []
        if a and b and status == 'CHANGED':
            fields = [k for k in ('state', 'title', 'body') if a[k] != b[k]]
            fields += [k for k in sorted(a['raw'].keys() | b['raw'].keys())
                       if a['raw'].get(k) != b['raw'].get(k)]
        changes.append({'target': key, 'status': status, 'fields': fields})
    return changes


def dependencies(item):
    """Only an explicit machine-readable line is actionable; prose stays on hold."""
    sections = re.findall(r'^#+\s+Dependencies\s*\n(.*?)(?=^#+\s|\Z)', item['body'], re.M | re.S | re.I)
    if len(sections) != 1:
        return [], '依存欄がない、または複数ある'
    text = sections[0].strip()
    if text.lower() in ('none', 'なし', '依存なし'):
        return [], None
    values = re.findall(r'^- depends-on: #([1-9][0-9]*)\s*$', text, re.M)
    remainder = re.sub(r'^- depends-on: #[1-9][0-9]*\s*$', '', text, flags=re.M).strip()
    if not values or remainder:
        return [], '依存の自然文は未確定（明示形式での確認が必要）'
    return sorted(set(int(x) for x in values)), None


def gate(item):
    if item['kind'] != 'pr':
        return []
    raw, failures = item['raw'], []
    head = raw['detail']['head']['sha']
    for name in REQUIRED:
        matches = [c for c in raw['checks'] if c.get('name') == name]
        states = [c for c in raw['statuses'] if c.get('context') == name]
        # Keep each check provider independent; another provider cannot hide failure.
        providers = {}
        for check in matches:
            app = check.get('app') or {}
            provider = app.get('id')
            if provider not in providers or providers[provider]['id'] < check['id']:
                providers[provider] = check
        if any(c.get('head_sha') != head or c.get('status') != 'completed'
               or c.get('conclusion') != 'success' for c in providers.values()):
            failures.append(f'{name}: 未成功/旧head')
        if states and max(states, key=lambda c: c['id']).get('state') != 'success':
            failures.append(f'{name}: 未成功status')
        if not matches and not states:
            failures.append(f'{name}: 未取得')
    formal = [r for r in raw['reviews'] if r.get('user', {}).get('login') == 'chatgpt-codex-connector[bot]'
              and r.get('commit_id') == head and r.get('state') in ('APPROVED', 'COMMENTED')]
    if not formal:
        failures.append('現headの正式Codexレビュー未確認')
    if any(r.get('state') == 'CHANGES_REQUESTED' for r in raw['reviews']):
        failures.append('変更要求レビューあり（人の分類が必要）')
    if any(t['isResolved'] is not True for t in raw['threads']):
        failures.append('未解決threadあり')
    return failures


def evidence(item):
    return [{'id': f'{item["kind"]}:{item["number"]}:body', 'url': item['url'],
             'quote': item['body'], 'source_hash': item['hash']},
            {'id': f'{item["kind"]}:{item["number"]}:state', 'url': item['url'],
             'quote': item['state'], 'source_hash': item['hash']}]


def build_plan(snapshot, priority=()):
    complete(snapshot)
    items = snapshot['items']
    priority = list(priority)
    require(len(set(priority)) == len(priority) and all(k in items for k in priority), 'invalid priority')
    candidates, deps = {}, {}
    for key, item in sorted(items.items()):
        reasons = []
        linked = []
        if item['kind'] == 'issue':
            linked = [p for p in items.values() if p['kind'] == 'pr' and any(
                c['number'] == item['number'] and c['repository']['nameWithOwner'] == REPO
                for c in p['raw']['closing'])]
        if item['state'] != 'OPEN':
            kind, nums = 'none', []
        elif item['kind'] == 'pr':
            kind, nums = 'review', []
            reasons += gate(item)
        else:
            nums, unknown = dependencies(item)
            if unknown:
                reasons.append(unknown)
            if len(re.findall(r'^#+\s+Goal\s*$', item['body'], re.M | re.I)) != 1:
                reasons.append('現行Goalを一意に確認できない')
            if any(re.search(r'Goal|目標|方針', c.get('body') or '', re.I) for c in item['raw']['comments']):
                reasons.append('コメントのGoal/方針変更は人の確認が必要')
            kind = 'dependency' if nums else 'scope' if reasons else 'completion' if any(
                p['state'] == 'MERGED' for p in linked) else 'plan'
        deps[key] = [f'issue:{n}' for n in nums]
        for dep in deps[key]:
            if dep not in items:
                reasons.append(f'{dep}: 未取得')
            elif items[dep]['state'] != 'CLOSED':
                reasons.append(f'{dep}: 依存完了/採用の確認待ち')
            else:
                # CLOSED is not proof of acceptance or successful delivery.
                reasons.append(f'{dep}: CLOSED、依存の成功条件は人が確認')
        label, action = KINDS[kind]
        candidates[key] = {
            'target': key, 'kind': kind, 'label': label, 'evidence': evidence(item) +
            [e for p in linked for e in evidence(p)], 'dependencies': deps[key],
            'start_condition': '取得完了、状態不変、保留なしを再取得で確認する。',
            'next_step': action, 'success_condition': '人が原文と受入条件を照合する（実行・承認・検収の完了ではない）。',
            'stop_condition': '状態/head/依存/check/レビューの変化、欠落、取得失敗なら停止する。',
            'hold_reasons': reasons, 'fingerprint': item['hash'],
        }
    ordered, visiting, visited = [], set(), set()
    for root in priority + sorted(items):
        stack = [(root, False)]
        while stack:
            key, expanded = stack.pop()
            if key in visited:
                continue
            if expanded:
                visiting.remove(key)
                visited.add(key)
                ordered.append(key)
            elif key in visiting:
                for member in visiting:
                    if '依存循環' not in candidates[member]['hold_reasons']:
                        candidates[member]['hold_reasons'].append('依存循環')
            else:
                visiting.add(key)
                stack.append((key, True))
                stack.extend((dep, False) for dep in reversed(deps[key]) if dep in candidates)
    return {'version': VERSION, 'repo': REPO, 'snapshot_hash': snapshot['hash'],
            'priority': priority, 'order': ordered, 'candidates': candidates}


def validate_plan(snapshot, plan):
    require(plan == build_plan(snapshot, plan.get('priority', [])), 'untrusted or altered plan/evidence')


def recheck(snapshot, plan, target, fresh):
    validate_plan(snapshot, plan)
    require(target in plan['candidates'], 'unknown candidate')
    validate(fresh)
    if fresh['coverage']['status'] != 'COMPLETE':
        return {'target': target, 'status': 'BLOCKED', 'reasons': ['再取得が不完全']}
    if target not in fresh['items']:
        return {'target': target, 'status': 'BLOCKED', 'reasons': ['対象が未取得']}
    # Compare the whole bounded scope: dependencies, relations, comments and checks included.
    before = {k: v['hash'] for k, v in snapshot['items'].items()}
    after = {k: v['hash'] for k, v in fresh['items'].items()}
    if before != after:
        return {'target': target, 'status': 'STALE', 'reasons': ['取得範囲の状態/根拠が計画時と変化']}
    reasons = plan['candidates'][target]['hold_reasons']
    return {'target': target, 'status': 'BLOCKED' if reasons else 'CONFIRMED', 'reasons': reasons,
            'meaning': '読取dry-runのみ。実行・承認・完了を意味しない。', 'fresh_hash': fresh['hash']}


def markdown(snapshot, changes, plan=None, result=None):
    # Render untrusted source only inside JSON-escaped inline text; no active raw HTML/links.
    def safe(value):
        text = json.dumps(value, ensure_ascii=False)
        return text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;').replace('`', '&#96;').replace('[', '&#91;').replace(']', '&#93;')
    lines = ['# GitHub作業指針', '', f'取得: {snapshot["captured_at"]}',
             f'coverage: {snapshot["coverage"]["status"]} / API呼出 {snapshot["coverage"]["calls"]}',
             f'上限: {safe(snapshot["coverage"]["limits"])}',
             '新規モデル通信0、GitHub書込0。意味精度・人の確認時間・有用性検収は未確認。',
             '', '## 今回の変更', '']
    lines += [f'- {x["target"]}: {x["status"]} {safe(x["fields"])}' for x in changes]
    if plan:
        for key in plan['order']:
            c = plan['candidates'][key]
            lines += ['', f'## {key} — {c["label"]}', '', f'次操作: {c["next_step"]}',
                      f'開始条件: {c["start_condition"]}', f'成功判定: {c["success_condition"]}',
                      f'停止条件: {c["stop_condition"]}', f'保留理由: {safe(c["hold_reasons"])}']
            lines += [f'- [{e["id"]}]({e["url"]}) / hash {e["source_hash"]}: {safe(e["quote"])}'
                      for e in c['evidence']]
    else:
        lines += ['', '取得不完全。手順は生成しない。', safe(snapshot['coverage']['errors'])]
    if result:
        lines += ['', '## 再確認', '', safe(result)]
    return '\n'.join(lines) + '\n'


def save_run(path, documents):
    """Exclusive new directory; manifest is written last. Partial runs cannot be loaded."""
    path = Path(path)
    require(path.parent.name == 'runs' and path.name not in ('', '.', '..'), 'output must be a new runs child')
    require(not any(p.is_symlink() for p in (path, *path.parents)), 'symlink output')
    path.parent.mkdir(parents=True, exist_ok=True)
    path.mkdir(exist_ok=False)
    manifest = {}
    for name, value in documents.items():
        require(name in ('snapshot.json', 'diff.json', 'plan.json', 'recheck.json', 'report.md'), 'output name')
        content = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n'
        with (path / name).open('x', encoding='utf-8') as stream:
            stream.write(content)
        manifest[name] = hashlib.sha256(content.encode()).hexdigest()
    with (path / 'manifest.json').open('x', encoding='utf-8') as stream:
        json.dump({'version': VERSION, 'status': 'SAVED', 'files': manifest}, stream)


def load_run(path):
    path = Path(path)
    require(not any(p.is_symlink() for p in (path, *path.parents)), 'symlink run')
    manifest = read_json(path / 'manifest.json')
    require(manifest.get('version') == VERSION and manifest.get('status') == 'SAVED', 'incomplete run')
    require(set(manifest['files']) <= {'snapshot.json', 'diff.json', 'plan.json', 'recheck.json', 'report.md'}
            and 'snapshot.json' in manifest['files'], 'manifest files')
    for name, expected in manifest['files'].items():
        file = path / name
        require(not file.is_symlink() and file.is_file() and file.stat().st_size <= 32_000_000, 'run file')
        require(hashlib.sha256(file.read_bytes()).hexdigest() == expected, 'run modified')
    snapshot = validate(read_json(path / 'snapshot.json'))
    return snapshot
