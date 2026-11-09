"""Weekly work-day coverage and burden for the skill improvement MVP (#108).

Coverage counts work days, not sessions: the denominator is the set of (repository_id, local date)
pairs seen in commits on allowed branches or registered as work days without commits; the numerator
is the part of that set with a session end record. Nothing here approves or starts any automation.
"""
from datetime import date, timedelta
import hashlib
import json
import os
import stat

from skill_improvement import schema
from skill_improvement.commits import branch_tips, commit_dates
from skill_improvement.ledger import LedgerError, require

REPORT_VERSION = 1
CACHE_FILE = 'report-cache.json'
COVERAGE_TARGET = 0.8
MIN_PERIOD_DAYS = 14
MIN_INDEPENDENT_CANDIDATES = 4
WEEKLY_MINUTES_THRESHOLD = 30
RECORDING_MINUTES_PER_END = 5
UNCONFIRMED_EFFECT_STATES = ('DEPLOYED_EFFECT_UNCONFIRMED', 'IMPROVEMENT_UNCONFIRMED')
LIMITS = [
    'commitのない作業は、作業日登録（work_day）がなければ検出できない。全セッションの網羅率ではない。',
    '作業日はcommitのcommitter日時をmanifestのtimezoneで日付にしたもの。merge commitとbot（名前かメールに[bot]）は数えない。',
    'ローカルのbranchだけを読む。fetchやAPI取得はしないため、未取得のcommitは数えない。',
    '条件の達成は自動化の検討開始の目安で、承認ではない。削減できる時間・自動化後に残る時間・開発保守の負担は人が比べる。',
]


def parse_day(value, code):
    try:
        parsed = date.fromisoformat(value)
    except (TypeError, ValueError):
        raise LedgerError(code, 'YYYY-MM-DD') from None
    require(parsed.isoformat() == value, code, 'YYYY-MM-DD')
    return parsed


def rate(numerator, denominator):
    return None if denominator == 0 else round(numerator / denominator, 4)


def in_period(row, start, end):
    return start.isoformat() <= row['work_date'] <= end.isoformat()


def week_start(day):
    return day - timedelta(days=day.weekday())


def coverage(work_days, end_keys, keys_filter=lambda key: True):
    denominator = {key for key in work_days if keys_filter(key)}
    numerator = denominator & {key for key in end_keys if keys_filter(key)}
    return denominator, numerator


def compute(manifest, rows, start, end, commit_days, commit_stats):
    """Pure aggregation over ledger rows and already-read commit days."""
    kinds = {}
    for row in rows:
        if in_period(row, start, end):
            kinds.setdefault(row['record']['kind'], []).append(row)
    registered = {(row['repository_id'], row['work_date']) for row in kinds.get('work_day', [])}
    committed = {(repository, day.isoformat()) for repository, days in commit_days.items() for day in days}
    work_days = committed | registered
    ends = kinds.get('session_end', [])
    end_keys = {(row['repository_id'], row['work_date']) for row in ends}
    denominator, numerator = coverage(work_days, end_keys)
    undetermined = sum(row['record']['status'] == 'UNDETERMINED' for row in ends)

    efforts = kinds.get('effort', [])
    minutes = {}
    for row in efforts:
        minutes[row['record']['activity']] = minutes.get(row['record']['activity'], 0) + row['record']['minutes']
    total_minutes = sum(minutes.values())
    period_days = (end - start).days + 1
    weekly_average = total_minutes * 7 / period_days
    displayed_weekly_average = round(weekly_average, 1)

    weeks = []
    first = week_start(start)
    while first <= end:
        last = first + timedelta(days=6)
        lo, hi = max(first, start).isoformat(), min(last, end).isoformat()
        inside_week = lambda key, lo=lo, hi=hi: lo <= key[1] <= hi  # noqa: E731
        week_den, week_num = coverage(work_days, end_keys, inside_week)
        weeks.append({'week_start': first.isoformat(), 'from': lo, 'to': hi, 'work_days': len(week_den),
                      'recorded_work_days': len(week_num), 'coverage': rate(len(week_num), len(week_den)),
                      'effort_minutes': sum(row['record']['minutes'] for row in efforts if lo <= row['work_date'] <= hi)})
        first += timedelta(days=7)

    histories = {}
    for row in rows:
        if row['record']['kind'] == 'candidate':
            histories.setdefault(row['record']['candidate_id'], []).append(row)
    by_state, independent = {}, 0
    for history in histories.values():
        if not in_period(history[0], start, end):
            continue
        status = history[-1]['record']['state']['status']
        by_state[status] = by_state.get(status, 0) + 1
        independent += status != 'DUPLICATE'

    reviews = kinds.get('size_review', [])
    observations = kinds.get('effect_observation', [])
    deployment_state = {}
    for row in rows:
        if row['record']['kind'] == 'deployment_event':
            deployment_state[row['record']['deployment_id']] = row['record']['state']['status']

    coverage_ratio = len(numerator) / len(denominator) if denominator else None
    coverage_rate = round(coverage_ratio, 4) if coverage_ratio is not None else None
    conditions = {
        'period_days': {'value': period_days, 'threshold': MIN_PERIOD_DAYS,
                        'result': 'MET' if period_days >= MIN_PERIOD_DAYS else 'NOT_MET'},
        'coverage': {'value': coverage_rate, 'threshold': COVERAGE_TARGET,
                     'result': 'UNDETERMINED' if coverage_ratio is None else
                     'MET' if coverage_ratio >= COVERAGE_TARGET else 'NOT_MET'},
        'independent_candidates': {'value': independent, 'threshold': MIN_INDEPENDENT_CANDIDATES,
                                   'result': 'MET' if independent >= MIN_INDEPENDENT_CANDIDATES else 'NOT_MET'},
        'weekly_minutes': {'value': displayed_weekly_average, 'threshold': WEEKLY_MINUTES_THRESHOLD,
                           'result': 'UNDETERMINED' if not efforts else
                           'MET' if weekly_average > WEEKLY_MINUTES_THRESHOLD else 'NOT_MET'},
    }
    results = {item['result'] for item in conditions.values()}
    verdict = 'NOT_MET' if 'NOT_MET' in results else 'UNDETERMINED' if 'UNDETERMINED' in results else 'CONDITIONS_MET'

    # Only end records that have their recording time are averaged; the others are unknown, not zero.
    recording = [row['record'] for row in efforts if row['record']['activity'] == 'RECORD']
    timed = {record['subject_id'] for record in recording}
    per_end = sum(record['minutes'] for record in recording) / len(timed) if timed else None
    if coverage_ratio is not None and coverage_ratio < COVERAGE_TARGET:
        aid = 'SUGGESTED'
    elif per_end is not None and per_end > RECORDING_MINUTES_PER_END:
        aid = 'SUGGESTED'
    elif coverage_ratio is None or per_end is None:
        aid = 'UNDETERMINED'
    else:
        aid = 'NOT_SUGGESTED'

    limits = list(LIMITS)
    without = sorted(item['repository_id'] for item in manifest.data['repositories'] if 'local_checkout' not in item)
    if without:
        limits.append('commitを読まないrepo（作業日登録だけで分母を作る）: ' + ', '.join(without))
    missing = sorted(f'{repository}:{branch}' for repository, stats in commit_stats.items()
                     for branch in stats.get('missing_branches', []))
    if missing:
        limits.append('ローカルに存在しないbranch: ' + ', '.join(missing))

    return {
        'report_version': REPORT_VERSION,
        'period': {'start': start.isoformat(), 'end': end.isoformat(), 'days': period_days,
                   'timezone': manifest.data['timezone']},
        'coverage': {
            'unit': 'WORK_DAY',
            'work_days': len(denominator), 'recorded_work_days': len(numerator), 'rate': coverage_rate,
            'unrecorded_work_days': [list(key) for key in sorted(denominator - numerator)],
            'end_records': len(ends),
            'end_records_outside_work_days': sum((row['repository_id'], row['work_date']) not in denominator
                                                 for row in ends),
            'undetermined_rate': rate(undetermined, len(ends)),
            'sources': {'commit_days': len(committed), 'registered_days': len(registered),
                        'registered_only_days': len(registered - committed)},
        },
        'weeks': weeks,
        'candidates': {'independent': independent, 'by_state': by_state},
        'effort_minutes': {'by_activity': minutes, 'total': total_minutes, 'weekly_average': displayed_weekly_average},
        'size_reviews': {'count': len(reviews),
                         'net_added_lines': sum(row['record']['net_added_lines'] for row in reviews),
                         'with_reference_moves': sum(bool(row['record']['moved_to']) for row in reviews),
                         'exceptions': sum(row['record']['verdict'] == 'EXCEPTION_RECORDED' for row in reviews)},
        'effects': {'recurred': sum(row['record']['issue_recurred'] for row in observations),
                    'worsened': sum(row['record']['adverse'] is not None for row in observations),
                    'effect_unconfirmed_deployments': sum(state in UNCONFIRMED_EFFECT_STATES
                                                          for state in deployment_state.values())},
        'automation': {'verdict': verdict, 'conditions': conditions,
                       'note': '条件の達成は検討開始の目安で、承認でも自動実行でもない'},
        'recording_aid': {'verdict': aid, 'coverage': coverage_rate,
                          'record_minutes_per_end': round(per_end, 1) if per_end is not None else None,
                          'note': '記録補助フックは自動化の3条件とは別に判断する。提案は配備の承認ではない'},
        'commits': commit_stats,
        'limits': limits,
    }


def _digest(data):
    return hashlib.sha256(data).hexdigest()


def _code_digest():
    """Changing how the report is computed must not return a report cached by older code."""
    here = os.path.dirname(os.path.abspath(__file__))
    parts = []
    for name in ('metrics.py', 'commits.py'):
        with open(os.path.join(here, name), 'rb') as handle:
            parts.append(handle.read())
    return _digest(b'\0'.join(parts))


CODE_DIGEST = _code_digest()


def build_report(manifest, manifest_bytes, ledger, start=None, end=None):
    """Read inputs, reuse the cached report when nothing changed, otherwise recompute and cache it."""
    period = manifest.data['period']
    start = parse_day(start or period['start_date'], 'PERIOD_INVALID')
    end = parse_day(end or period['end_date'], 'PERIOD_INVALID')
    require(start <= end, 'PERIOD_INVALID', 'start after end')
    require(period['start_date'] <= start.isoformat() and end.isoformat() <= period['end_date'],
            'OUTSIDE_PERIOD', 'the report period must be inside the manifest period')
    readable = [item for item in manifest.data['repositories'] if 'local_checkout' in item]
    # A PUBLIC_FIXTURE ledger may sit inside a repository, so its cache may only hold PUBLIC data.
    require(manifest.data['ledger_location']['kind'] != 'PUBLIC_FIXTURE' or
            all(item['classification'] == 'PUBLIC' for item in readable), 'CLASSIFICATION_NOT_PUBLIC',
            'a PUBLIC_FIXTURE ledger reads only PUBLIC checkouts')
    data, rows = ledger.snapshot()
    state = {item['repository_id']: branch_tips(item) for item in readable}
    tips = {repository: value[0] for repository, value in state.items()}
    fingerprint = _digest(schema.canonical({
        'version': REPORT_VERSION, 'code': CODE_DIGEST, 'manifest': _digest(manifest_bytes), 'ledger': _digest(data),
        'tips': tips, 'shallow': {repository: value[1] for repository, value in state.items()},
        'start': start.isoformat(), 'end': end.isoformat()}))
    cached = read_cache(ledger)
    if cached and cached.get('fingerprint') == fingerprint:
        return dict(cached['report'], status='UNCHANGED', fingerprint=fingerprint)
    commit_days, stats = {}, {}
    for item in manifest.data['repositories']:
        if 'local_checkout' not in item:
            continue
        repository = item['repository_id']
        commit_days[repository], stats[repository] = commit_dates(item, tips[repository], manifest.zone, start, end)
        stats[repository]['missing_branches'] = sorted(branch for branch, sha in tips[repository].items() if not sha)
    report = compute(manifest, rows, start, end, commit_days, stats)
    try:
        write_cache(ledger, {'fingerprint': fingerprint, 'report': report})
        cache = 'SAVED'
    except (OSError, LedgerError):
        # The report is still correct; only the next run cannot skip the work.
        cache = 'NOT_SAVED'
    return dict(report, status='COMPUTED', fingerprint=fingerprint, cache=cache)


def read_cache(ledger):
    """The cache is derived data: anything unexpected means recompute, never trust."""
    with ledger.open_directory() as dirfd:
        try:
            fd = os.open(CACHE_FILE, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=dirfd)
        except OSError:
            return None
        try:
            info = os.fstat(fd)
            if not stat.S_ISREG(info.st_mode) or info.st_size > 4 * 1024 * 1024:
                return None
            value = json.loads(os.read(fd, info.st_size + 1).decode('utf-8'))
            return value if type(value) is dict and type(value.get('report')) is dict else None
        except (ValueError, UnicodeDecodeError, RecursionError, OSError):
            return None
        finally:
            os.close(fd)


def write_cache(ledger, value):
    payload = schema.canonical(value) + b'\n'
    temp = f'.{CACHE_FILE}.{os.getpid()}.tmp'
    with ledger.open_directory() as dirfd:
        fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=dirfd)
        try:
            try:
                require(os.write(fd, payload) == len(payload), 'CACHE_WRITE_FAILED')
                os.fsync(fd)
            finally:
                os.close(fd)
            os.replace(temp, CACHE_FILE, src_dir_fd=dirfd, dst_dir_fd=dirfd)
        except BaseException:
            try:
                os.unlink(temp, dir_fd=dirfd)
            except OSError:
                pass
            raise
        os.fsync(dirfd)
