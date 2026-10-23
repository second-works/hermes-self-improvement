"""Strict snapshots, deterministic instructions and conservative preflight."""
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path

from . import guide

REPO = 'second-works/hermes-self-improvement'
VERSION = 1
PLAN_VERSION = 2  # v2: per-item guidance, excerpt evidence, work fingerprint
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


def work_view(raw):
    """Source minus repository-wide metadata that changes without any change to this item."""
    detail = dict(raw['detail'])
    for side in ('head', 'base'):
        if isinstance(detail.get(side), dict) and 'repo' in detail[side]:
            ref = dict(detail[side])
            repo = ref['repo']
            ref['repo'] = repo.get('full_name') if isinstance(repo, dict) else repo
            detail[side] = ref
    return {**raw, 'detail': detail}


def fingerprint(item):
    """Work fingerprint for diff/recheck. The source hash stays the integrity check of the original."""
    return digest(work_view(item['raw']))


def diff(current, previous=None):
    validate(current)
    if previous is not None:
        validate(previous)
    old = previous['items'] if previous else {}
    changes = []
    for key in sorted(old.keys() | current['items'].keys()):
        a, b = old.get(key), current['items'].get(key)
        status = ('UNAVAILABLE' if b is None else 'FIRST' if previous is None else
                  'ADDED' if a is None else 'UNCHANGED' if fingerprint(a) == fingerprint(b) else 'CHANGED')
        fields = []
        if a and b and status == 'CHANGED':
            va, vb = work_view(a['raw']), work_view(b['raw'])
            fields = [k for k in ('state', 'title', 'body') if a[k] != b[k]]
            fields += [k for k in sorted(va.keys() | vb.keys()) if va.get(k) != vb.get(k)]
        changes.append({'target': key, 'status': status, 'fields': fields,
                        'metadata_only': bool(status == 'UNCHANGED' and a['hash'] != b['hash'])})
    return changes


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


def hold(code, category, reason, evidence, check, question, release, **extra):
    return {'code': code, 'category': category, 'reason': reason, 'evidence': evidence,
            'check': check, 'question': question, 'release': release, **extra}


class Analysis:
    """Per-snapshot text index shared by all candidates."""

    def __init__(self, items):
        self.items = items
        self.texts, self.refs, self.external = {}, {}, {}
        for key, item in items.items():
            texts = [guide.Text(key, 'body', item['body'])]
            texts += [guide.Text(key, f'c{i}', c['body']) for i, c in enumerate(item['raw']['comments'], 1)]
            self.texts[key] = texts
            self.refs[key], self.external[key] = [], []
            for text in texts:
                internal, external = guide.references(text, REPO)
                for r in internal:
                    r['target'] = guide.resolve(items, r['kind'], r['number'])
                self.refs[key] += [r for r in internal if r['target'] != key]
                self.external[key] += external


def analyze(key, item, a):
    """Sections, holds, relations and evidence for one OPEN Issue (all from quoted source)."""
    items, body = a.items, a.texts[key][0]
    found = guide.sections(body)
    named = [s for s in found if s['name']]
    evidence, holds, notes = {}, [], []

    def cite(entry):
        owner = items[':'.join(entry['id'].split(':')[:2])]
        evidence.setdefault(entry['id'], {**entry, 'url': owner['url'], 'source_hash': owner['hash']})
        return entry['id']

    def section_excerpt(s, lines=4):
        return cite(body.excerpt(s['line'], min(s['end'], s['line'] + lines)))

    recognised = ', '.join(guide.LABELS[s['name']] for s in named) or 'なし'
    goals = [s for s in named if s['name'] == 'goal']
    if not goals:
        first = [section_excerpt(named[0], 2)] if named else ([cite(body.excerpt(0, 2))] if item['body'].strip() else [])
        holds.append(hold('format_missing', 'format', '目的/Goal欄がない', first,
                          f'{key} 本文（認識した欄: {recognised}）', 'このIssueで達成することは何か。本文のどの記載が目的に当たるか。',
                          '目的/Goal欄を本文に1つ書く、または目的を人が判断して記録する。', section='goal'))
    elif len(goals) > 1:
        ids = []
        for s in goals:
            if s['parent'] is not None:
                ids.append(cite(body.excerpt(s['parent'], s['parent'] + 1)))
            ids.append(section_excerpt(s))
        holds.append(hold('goal_multiple', 'semantic', f'目的/Goalの欄が{len(goals)}箇所ある', ids,
                          f'{key} の各目的欄（' + '、'.join(f'L{s["line"] + 1}' for s in goals) + '）と、上位の見出し',
                          'どの欄が現行の目的か。後の欄は前の欄を置き換えるか。',
                          '現行の目的を1つに決め、本文に反映するか人の判断として記録する。'))
    elif not guide.subtree_content(body, goals[0]):
        holds.append(hold('goal_empty', 'format', '目的/Goal欄が空', [section_excerpt(goals[0], 2)],
                          f'{key} L{goals[0]["line"] + 1} の目的欄', 'このIssueで達成することは何か。',
                          '目的/Goal欄に内容を書く、または目的を人が判断して記録する。'))

    sources = [(s['line'], s['content'], body.excerpt(s['line'], s['end']))
               for s in named if s['name'] == 'dependencies']
    sources += [(x['line'], x['value'], body.excerpt(x['line'], x['line'] + 1)) for x in guide.labels(body, found)]
    sources.sort(key=lambda x: x[0])
    numbers = []
    if not sources:
        holds.append(hold('format_missing', 'format', '依存欄がない', [],
                          f'{key} 本文（認識した欄: {recognised}）', '先に終わっている必要があるIssue/PRはあるか。',
                          '依存/Dependencies欄に番号（- depends-on: #N）か「なし」を書く、または人が判断して記録する。',
                          section='dependencies'))
    if len(sources) > 1:
        holds.append(hold('dependency_multiple', 'semantic', f'依存の記載が{len(sources)}箇所ある',
                          [cite(x[2]) for x in sources], f'{key} の依存の記載（' + '、'.join(f'L{x[0] + 1}' for x in sources) + '）',
                          'どの記載が現行の依存か。', '現行の依存を1つに決め、本文に反映するか人の判断として記録する。'))
    for line, value, quote in sources:
        explicit, terms = guide.dependency_value(value)
        if explicit is not None:
            numbers += explicit
            continue
        mentioned = []
        end = next((s['end'] for s in found if s['line'] == line), line + 1)
        for r in a.refs[key]:
            if r['evidence']['id'].startswith(f'{key}:L') and line <= r['line'] < end:
                target = r['target']
                if target not in [m['target'] for m in mentioned]:
                    mentioned.append({'target': target, 'state': items[target]['state'] if target in items else 'UNFETCHED'})
        holds.append(hold('dependency_prose', 'semantic', '依存が自然文で書かれ、Issue/PR番号が確定していない', [cite(quote)],
                          f'{key} L{line + 1} の依存の各項目と、名称が近いIssue（未確定の候補）',
                          '各項目はどのIssue/PRか。先に完了している必要があるか。',
                          '依存を番号（- depends-on: #N）か「なし」で確定する、または人が判断して記録する。',
                          terms=[{'term': t, 'candidates': [] if guide.SHORT.search(t) else guide.name_candidates(t, items, key)}
                                 for t in terms], mentioned=mentioned))
    numbers = sorted(set(numbers)) if not any(h['code'] == 'dependency_prose' for h in holds) else []

    for c_text in a.texts[key][1:]:
        for i, line in enumerate(c_text.lines):
            m = re.search(r'Goal|目標|方針', line, re.I)
            if m:
                holds.append(hold('comment_change', 'semantic', 'コメントのGoal/方針変更は人の確認が必要',
                                  [cite(c_text.window(i, m.start(), m.end()))], f'{key} {c_text.where} L{i + 1}',
                                  'コメントは本文の目的・方針・範囲を変更するか。',
                                  '変更を本文に反映するか、変更なしと人が判断して記録する。'))
                break

    related = {}
    def relate(target, relation, direction, ev):
        k = (target, relation, direction)
        if k in related:
            return
        entry = {'target': target, 'relation': relation, 'direction': direction, 'evidence': ev,
                 'state': items[target]['state'] if target in items else 'UNFETCHED'}
        if target in items and items[target]['kind'] == 'pr':
            d = items[target]['raw']['detail']
            entry.update(head=d['head']['sha'], merged_at=guide.valid_time(d.get('merged_at')))
        related[k] = entry
    for p in items.values():
        if p['kind'] == 'pr' and any(c['number'] == item['number'] and c['repository']['nameWithOwner'] == REPO
                                     for c in p['raw']['closing']):
            relate(f'pr:{p["number"]}', 'closing', 'in', None)
    for r in a.refs[key]:
        relate(r['target'], 'mention', 'out', cite(r['evidence']))
    for other, refs in a.refs.items():
        for r in refs:
            if r['target'] == key:
                relate(other, r['relation'], 'in', cite(r['evidence']))
    related = sorted(related.values(), key=lambda r: (r['target'], r['relation'], r['direction']))
    external, seen = [], set()
    for x in a.external[key]:
        if x['url'] not in seen:
            seen.add(x['url'])
            external.append({'url': x['url'], 'evidence': cite(x['evidence']),
                             'note': f'対象外repo（{x["repo"]}）のため取得しない。必要なら人が確認する。'})

    done = []
    for s in named:
        if s['name'] == 'done':
            checked, total = guide.done_counts(body, s)
            done.append({'line': s['line'] + 1, 'checked': checked, 'total': total, 'evidence': section_excerpt(s, 6)})

    merged = [r for r in related if r['state'] == 'MERGED' and (r['relation'] == 'closing' or
              (r['relation'] == 'refs' and r['direction'] == 'in'))]
    merged_targets = sorted({r['target'] for r in merged})
    if merged and not any(r['relation'] == 'closing' for r in merged):
        holds.append(hold('relation_not_closing', 'semantic', 'MERGEDの関連PRは参照（Refs）だけで、closing関係ではない',
                          [r['evidence'] for r in merged if r['evidence']],
                          f'{key} の完了条件と ' + '、'.join(merged_targets) + ' の変更内容',
                          'このPRでIssueのどの完了条件を満たしたか。残りはあるか。',
                          'PRとIssueの対応範囲を人が確定する（Issue Closeは人間が判断）。'))
    updated = guide.valid_time(item['raw']['detail'].get('updated_at'))
    for r in merged:
        if r.get('merged_at') and updated and r['merged_at'] > updated:
            notes.append(f'{r["target"]} のMerge（{r["merged_at"]}）はIssueの最終更新（{updated}）より後。'
                         '本文の状態の記述はMerge前の時点として読む。')
    notes = sorted(set(notes))
    gaps = [n for n in guide.EXPECTED if n not in {s['name'] for s in named}
            and not (n == 'dependencies' and sources)]
    other = [{'line': s['line'] + 1, 'heading': s['heading']} for s in found if not s['name']]
    return {'sections': [{'name': s['name'], 'line': s['line'] + 1} for s in named], 'gaps': gaps, 'done': done,
            'related': related, 'external': external, 'holds': holds, 'notes': notes, 'other_headings': other,
            'numbers': numbers, 'merged': merged_targets, 'evidence': evidence}


def steps_for(key, kind, item, info, deps, items):
    if kind == 'none':
        return [f'{item["state"]}のため再実装を開始しない。']
    if kind == 'review':
        head = item['raw']['detail']['head']['sha']
        steps = [f'現head {head} で必須check（{", ".join(REQUIRED)}）・正式レビュー・threadを確認する。']
        return steps + [f'保留 gate: {h["reason"]}' for h in info['holds']] + [
            f'scripts/check-pr-head.sh {item["number"]} が PR_GATE_STATUS=READY を返すまでマージを依頼しない。']
    steps = []
    if kind == 'completion':
        for r in info['related']:
            if r['target'] in info['merged'] and r['relation'] in ('closing', 'refs') and r['direction'] == 'in':
                how = 'closing' if r['relation'] == 'closing' else 'Refs（closingではない）'
                steps.append(f'{r["target"]}（MERGED、head {r["head"]}、Merge {r["merged_at"] or "日時不明"}、関係: {how}）'
                             'の変更内容と検証記録を確認する。')
        if info['done']:
            summary = '、'.join(f'L{d["line"]}: ' + (f'{d["checked"]}/{d["total"]}チェック' if d['total'] else 'チェック項目なし')
                               for d in info['done'])
            steps.append(f'完了条件の欄（{summary}）を、上記PRの実装範囲と照合する。')
        else:
            steps.append('完了条件の欄がないため、目的と作業範囲を上記PRの変更と照合する。')
    elif kind == 'dependency':
        states = '、'.join(f'{d}: {items[d]["state"] if d in items else "未取得"}' for d in deps)
        steps.append(f'依存 {states} の完了条件を確認する。CLOSEDでも成功・採用は推定しない。')
    elif kind == 'scope':
        steps.append(f'保留{len(info["holds"])}件を解除するまで実装を始めない。')
    else:
        steps.append('目的と作業範囲を照合し、実装Issueとして計画を整理する。')
    for r in info['related']:
        if r['direction'] == 'out' and r['state'] == 'OPEN':
            steps.append(f'本文が言及するOPENの {r["target"]} との境界を引用（{r["evidence"]}）で確認する（範囲の重複・変更の有無）。')
    if info['external']:
        steps.append(f'対象外repoへの参照{len(info["external"])}件は取得しない。親計画などの内容が必要なら人が確認する。')
    for h in info['holds']:
        where = f'（{h["evidence"][0]}）' if h['evidence'] else ''
        steps.append(f'保留 {h["code"]}{where}: {h["release"]}')
    if info['gaps']:
        if 'verification' in info['gaps'] and info['done']:
            steps.append('検証/Verification欄がない: 完了条件をどう確認するかが未定義。確認方法を決める。')
        missing = [guide.LABELS[g] for g in info['gaps'] if g not in ('goal', 'dependencies')]
        if missing:
            steps.append('未定義の欄: ' + '、'.join(missing) + '。Issueに追記するか、不要と人が判断して記録する。')
    if kind == 'completion':
        steps.append('Issue Close・採用・本番適用は人間が判断する（ハーネスは推定しない）。')
    return steps


def state_evidence(item):
    key = f'{item["kind"]}:{item["number"]}'
    return {'id': f'{key}:state', 'url': item['url'], 'quote': item['state'], 'truncated': False,
            'source_hash': item['hash']}


def build_plan(snapshot, priority=()):
    complete(snapshot)
    items = snapshot['items']
    priority = list(priority)
    require(len(set(priority)) == len(priority) and all(k in items for k in priority), 'invalid priority')
    a = Analysis(items)
    candidates, deps = {}, {}
    for key, item in sorted(items.items()):
        info = {'sections': [], 'gaps': [], 'done': [], 'related': [], 'external': [], 'holds': [], 'notes': [],
                'other_headings': [], 'numbers': [], 'merged': [], 'evidence': {}}
        if item['state'] != 'OPEN':
            kind = 'none'
        elif item['kind'] == 'pr':
            kind = 'review'
            head = item['raw']['detail']['head']['sha']
            info['holds'] = [hold('gate', 'gate', reason, [f'{key}:head'], f'{key} 現head {head}',
                                  '必須check・正式レビュー・threadが現headでそろっているか。',
                                  f'scripts/check-pr-head.sh {item["number"]} が PR_GATE_STATUS=READY を返し、未解決の指摘がない。')
                             for reason in gate(item)]
            info['evidence'][f'{key}:head'] = {'id': f'{key}:head', 'url': item['url'], 'quote': head,
                                               'truncated': False, 'source_hash': item['hash']}
        else:
            kind = 'issue'  # decided below from dependencies, related PRs and holds
            info = analyze(key, item, a)
        deps[key] = [f'issue:{n}' for n in info['numbers']]
        for dep in deps[key]:
            if dep not in items:
                reason, release = f'{dep}: 未取得', '依存先の番号を確認し、取得範囲で状態を確認できるようにする。'
            elif items[dep]['state'] != 'CLOSED':
                reason, release = f'{dep}: 依存完了/採用の確認待ち', '依存先がCLOSEDになり、その完了条件を人が確認する。'
            else:
                # CLOSED is not proof of acceptance or successful delivery.
                reason, release = f'{dep}: CLOSED、依存の成功条件は人が確認', 'CLOSEDの依存先の完了条件と採用を人が確認して記録する。'
            info['holds'].append(hold('dependency_state', 'state', reason, [], f'{dep} の状態と完了条件',
                                      '依存先は成功条件を満たしているか。', release))
        if kind not in ('none', 'review'):
            kind = 'dependency' if deps[key] else 'completion' if info['merged'] else 'scope' if info['holds'] else 'plan'
        label, action = KINDS[kind]
        related_ev = {}
        for r in info['related']:
            if r['target'] in info['merged']:
                pr = items[r['target']]
                related_ev[f'{r["target"]}:state'] = state_evidence(pr)
                related_ev[f'{r["target"]}:head'] = {'id': f'{r["target"]}:head', 'url': pr['url'], 'quote': r['head'],
                                                     'truncated': False, 'source_hash': pr['hash']}
        evidence = [state_evidence(item)] + list(info['evidence'].values()) + list(related_ev.values())
        candidates[key] = {
            'target': key, 'kind': kind, 'label': label,
            'status': {'state': item['state'], 'updated_at': guide.valid_time(item['raw']['detail'].get('updated_at')),
                       'comments': len(item['raw']['comments'])},
            'sections': info['sections'], 'gaps': info['gaps'], 'done': info['done'], 'related': info['related'],
            'external': info['external'], 'holds': info['holds'], 'notes': info['notes'],
            'other_headings': info['other_headings'], 'evidence': evidence, 'dependencies': deps[key],
            'start_condition': '取得完了、状態不変、保留なしを再取得で確認する。',
            'next_step': action, 'steps': steps_for(key, kind, item, info, deps[key], items),
            'success_condition': '人が原文と受入条件を照合する（実行・承認・検収の完了ではない）。',
            'stop_condition': '状態/head/依存/check/レビューの変化、欠落、取得失敗なら停止する。',
            'hold_reasons': [h['reason'] for h in info['holds']],
            'fingerprint': fingerprint(item), 'source_hash': item['hash'],
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
                    c = candidates[member]
                    if '依存循環' not in c['hold_reasons']:
                        c['hold_reasons'].append('依存循環')
                        c['holds'].append(hold('dependency_cycle', 'state', '依存循環', [], f'{member} の依存',
                                               '依存の向きは正しいか。', '循環しないように依存を直す。'))
                        c['steps'].append('保留 dependency_cycle: 循環しないように依存を直す。')
            else:
                visiting.add(key)
                stack.append((key, True))
                stack.extend((dep, False) for dep in reversed(deps[key]) if dep in candidates)
    return {'version': PLAN_VERSION, 'repo': REPO, 'snapshot_hash': snapshot['hash'],
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
    # Repository-wide metadata is excluded by the work fingerprint; the source hash is still validated.
    before = {k: fingerprint(v) for k, v in snapshot['items'].items()}
    after = {k: fingerprint(v) for k, v in fresh['items'].items()}
    if before != after:
        return {'target': target, 'status': 'STALE', 'reasons': ['取得範囲の状態/根拠が計画時と変化']}
    reasons = plan['candidates'][target]['hold_reasons']
    return {'target': target, 'status': 'BLOCKED' if reasons else 'CONFIRMED', 'reasons': reasons,
            'meaning': '読取dry-runのみ。実行・承認・完了を意味しない。', 'fresh_hash': fresh['hash']}


RELATION_LABELS = {('closing', 'in'): 'closing関係', ('refs', 'in'): '相手がRefs等で参照', ('mention', 'in'): '相手が言及',
                   ('refs', 'out'): '本文がRefs等で参照', ('mention', 'out'): '本文が言及'}


def previous_given(changes):
    return any(x['status'] != 'FIRST' for x in changes) or not changes


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
    first = [x for x in changes if x['status'] == 'FIRST']
    moved = [x for x in changes if x['status'] not in ('UNCHANGED', 'FIRST')]
    if first:
        lines.append(f'- FIRST: {len(first)}件（前回runなし。差分は次回から）')
    lines += [f'- {x["target"]}: {x["status"]} {safe(x["fields"])}' for x in moved]
    same = sum(x['status'] == 'UNCHANGED' for x in changes)
    meta = sum(x['metadata_only'] for x in changes)
    if previous_given(changes):
        lines.append(f'- UNCHANGED: {same}件（うちrepo全体のメタデータだけが変化: {meta}件）')
    if plan:
        active = [k for k in plan['order'] if plan['candidates'][k]['kind'] != 'none']
        done = [k for k in plan['order'] if plan['candidates'][k]['kind'] == 'none']
        for key in active:
            c = plan['candidates'][key]
            ev = {e['id']: e for e in c['evidence']}
            def quote(i):
                e = ev[i]
                return f'[{i}]({e["url"]}) {safe(e["quote"])}' + ('（抜粋）' if e['truncated'] else '')
            s = c['status']
            lines += ['', f'## {key} — {c["label"]}', '',
                      f'- 現在: {s["state"]} / 最終更新 {s["updated_at"] or "不明"} / コメント{s["comments"]}件',
                      '- 認識した欄: ' + ('、'.join(f'{x["name"]}(L{x["line"]})' for x in c['sections']) or 'なし')]
            if c['done']:
                lines.append('- 完了条件: ' + '、'.join(
                    f'L{d["line"]} ' + (f'{d["checked"]}/{d["total"]}チェック' if d['total'] else 'チェック項目なし')
                    for d in c['done']))
            if c['other_headings']:
                lines.append('- 判断に使っていない見出し: ' + '、'.join(f'L{x["line"]}' for x in c['other_headings']))
            grouped = {}
            for r in c['related']:
                grouped.setdefault(r['target'], []).append(r)
            for target, rs in grouped.items():
                how = '、'.join(RELATION_LABELS[(r['relation'], r['direction'])] for r in rs)
                extra = f'、head {rs[0]["head"]}' if rs[0].get('head') else ''
                where = ', '.join(r['evidence'] for r in rs if r['evidence'])
                lines.append(f'- 関連候補: {target}（{rs[0]["state"]}{extra}）{how}' + (f' ← {where}' if where else ''))
            for x in c['external']:
                lines.append(f'- 対象外: {safe(x["url"])} — {x["note"]}')
            for n in c['notes']:
                lines.append(f'- 注意: {n}')
            lines += ['', '確認手順:']
            lines += [f'{i}. {step}' for i, step in enumerate(c['steps'], 1)]
            if c['holds']:
                lines += ['', '保留:']
                for h in c['holds']:
                    lines.append(f'- {h["code"]}（{h["category"]}）{h["reason"]} / 確認対象: {h["check"]} / '
                                 f'問い: {h["question"]} / 解除条件: {h["release"]}')
                    for t in h.get('terms', []):
                        cands = '、'.join(f'{x["target"]}({x["state"]}, 一致{x["score"]}, 未確定)' for x in t['candidates']) or '候補なし'
                        lines.append(f'  - 項目 {safe(t["term"])}: {cands}')
                    if h.get('mentioned'):
                        lines.append('  - 記載の番号: ' + '、'.join(f'{m["target"]}({m["state"]})' for m in h['mentioned']))
            lines += ['', f'進める条件: {c["start_condition"]} / 止める条件: {c["stop_condition"]}', '', '根拠:']
            lines += [f'- {quote(i)}' for i in ev if not i.endswith(':state')]
        if done:
            lines += ['', f'## 今回対応不要（CLOSED/MERGED） {len(done)}件', '',
                      '、'.join(f'{k}: {plan["candidates"][k]["status"]["state"]}' for k in done)]
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
