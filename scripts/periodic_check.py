#!/usr/bin/env python3
"""Weekly read-only check (#59): no model, no GitHub writes, no deletion.

Run it from the dedicated check checkout (a detached git worktree of this repository).
With --update it first moves that checkout to origin/main; it refuses when the checkout
is on a branch or has tracked changes, so it never moves someone's working branch.
It collects with scripts/report_github_work_guide.py into runs/periodic-<YYYYMMDD-HHMM>
and writes runs/periodic-summaries/<YYYYMMDD-HHMM>.md. Exit 0 when the check finished,
1 when it stopped (see the summary for why), 2 for usage errors.
"""
import argparse
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
REPO = 'second-works/hermes-self-improvement'
RUN_NAME = re.compile(r'periodic-\d{8}-\d{4}\Z')
LIMIT_SECONDS, LIMIT_CALLS = 180, 500
WARN_RATIO = 0.8
STALE_DAYS = 14


def run(args, cwd=None, timeout=300):
    proc = subprocess.run(args, cwd=cwd or ROOT, capture_output=True, text=True, timeout=timeout)
    return proc.returncode, proc.stdout, proc.stderr


def update_checkout():
    """Move the dedicated checkout to origin/main. Returns an error text or None."""
    code, out, _ = run(['git', 'symbolic-ref', '-q', 'HEAD'])
    if code == 0:
        return f'checkout is on branch {out.strip()}; only a detached check checkout is updated'
    code, out, _ = run(['git', 'status', '--porcelain', '--untracked-files=no'])
    if code != 0 or out.strip():
        return 'checkout has tracked changes or git status failed'
    for args in (['git', 'fetch', '--quiet', 'origin', 'main'], ['git', 'checkout', '--quiet', '--detach', 'origin/main']):
        code, _, _ = run(args)
        if code != 0:
            return f'{" ".join(args[:2])} failed'
    return None


def previous_run(runs):
    """Newest earlier periodic collect run that finished saving (has a manifest with a snapshot)."""
    found = []
    for path in runs.iterdir() if runs.is_dir() else []:
        if RUN_NAME.fullmatch(path.name) and not path.is_symlink() and (path / 'manifest.json').is_file():
            try:
                files = json.loads((path / 'manifest.json').read_text(encoding='utf-8'))['files']
            except (OSError, ValueError, KeyError, TypeError):
                continue
            if 'snapshot.json' in files and 'plan.json' in files:
                found.append(path)
    return max(found, key=lambda p: p.name) if found else None


def stale_open(snapshot, now, days=STALE_DAYS):
    rows = []
    for key, item in sorted(snapshot['items'].items()):
        if item['state'] != 'OPEN':
            continue
        updated = item['raw']['detail'].get('updated_at')
        try:
            when = datetime.fromisoformat(updated.replace('Z', '+00:00'))
        except (AttributeError, ValueError):
            rows.append((key, item['title'], '不明'))
            continue
        if now - when >= timedelta(days=days):
            rows.append((key, item['title'], updated))
    return rows


def analyse(snapshot, plan, changes, seconds, now):
    """Pure summary of one collect run (all values come from the saved files)."""
    coverage = snapshot['coverage']
    candidates = plan['candidates'] if plan else {}
    by_kind = {}
    for key, c in sorted(candidates.items()):
        by_kind.setdefault(c['kind'], []).append((key, c['label']))
    moved = [(x['target'], x['status']) for x in changes if x['status'] in ('ADDED', 'CHANGED', 'UNAVAILABLE')]
    warnings = []
    if seconds is not None and seconds >= LIMIT_SECONDS * WARN_RATIO:
        warnings.append(f'取得時間 {seconds:.0f}秒が上限{LIMIT_SECONDS}秒の8割以上')
    if coverage.get('calls', 0) >= LIMIT_CALLS * WARN_RATIO:
        warnings.append(f'API呼出 {coverage["calls"]}回が上限{LIMIT_CALLS}回の8割以上')
    return {'status': coverage['status'], 'items': len(snapshot['items']), 'calls': coverage.get('calls'),
            'seconds': seconds, 'omitted': coverage.get('omitted', ''), 'moved': moved,
            'first': all(x['status'] == 'FIRST' for x in changes) if changes else True,
            'acceptance': by_kind.get('acceptance', []), 'completion': by_kind.get('completion', []),
            'open': [(k, c['kind']) for k, c in sorted(candidates.items()) if c['kind'] != 'none'],
            'stale': stale_open(snapshot, now), 'warnings': warnings}


def main_ci():
    if not shutil.which('gh'):
        return None, 'gh が見つからない'
    code, out, _ = run(['gh', 'run', 'list', '--repo', REPO, '--branch', 'main', '--limit', '6',
                        '--json', 'name,status,conclusion,headSha'], timeout=60)
    if code != 0:
        return None, 'gh run list に失敗（認証・通信を確認）'
    try:
        return json.loads(out), None
    except ValueError:
        return None, 'gh run list の出力を読めない'


def review_setting():
    code, out, _ = run(['git', 'show', 'origin/main:.github/pr-gate-review'])
    if code != 0:
        return None
    return [line.strip() for line in out.splitlines() if line.strip() and not line.lstrip().startswith('#')]


def runs_size(runs):
    total = 0
    for path in runs.rglob('*'):
        if path.is_file() and not path.is_symlink():
            total += path.stat().st_size
    return total


def render(stamp, result, previous, ci, ci_error, setting, size, stop=None):
    lines = [f'# 定期点検 {stamp}', '', '読み取りと報告だけ（#59）。GitHubへの書き込み・削除・モデルの使用はしていない。', '']
    if stop:
        lines += ['## 停止', '', f'- {stop}', '']
    if result:
        lines += ['## 取得', '',
                  f'- coverage: {result["status"]} / {result["items"]}件 / API呼出 {result["calls"]}回 / '
                  f'{result["seconds"]:.0f}秒（上限 {LIMIT_SECONDS}秒・{LIMIT_CALLS}回）',
                  f'- 前回のrun: {previous.name if previous else "なし（初回）"}',
                  f'- 取得対象外: {result["omitted"] or "なし"}', '']
        lines += ['## 前回からの変化', '']
        if result['first']:
            lines.append('- 前回のrunがないため、差分は次回から')
        elif result['moved']:
            lines += [f'- {key}: {status}' for key, status in result['moved']]
        else:
            lines.append('- 変化なし（取得範囲内）')
        lines += ['', '## 要対応の候補', '']
        lines += [f'- 親の検収待ち: {key}（人の最終検収）' for key, _ in result['acceptance']]
        lines += [f'- 完了範囲確認: {key}（関連PRはMerge済み。Closeは人が判断）' for key, _ in result['completion']]
        lines += [f'- {STALE_DAYS}日以上動いていないOPEN: {key}（最終更新 {when}）' for key, _, when in result['stale']]
        lines += [f'- 警告: {w}' for w in result['warnings']]
        if not (result['acceptance'] or result['completion'] or result['stale'] or result['warnings']):
            lines.append('- なし')
        lines += ['', '## 案内の対象（OPEN）', '']
        lines += [f'- {key}: {kind}' for key, kind in result['open']] or ['- なし']
        lines.append('')
    lines += ['## mainのCI', '']
    if ci_error:
        lines.append(f'- 取得できない: {ci_error}')
    else:
        for row in ci or []:
            lines.append(f'- {row.get("name")}: {row.get("status")}/{row.get("conclusion") or "-"} ({str(row.get("headSha"))[:7]})')
        bad = [r for r in ci or [] if r.get('status') == 'completed' and r.get('conclusion') not in ('success', 'skipped', 'neutral')]
        if bad:
            lines.append('- 警告: mainで成功していないrunがある')
    lines += ['', '## 正式レビューの設定（origin/main の .github/pr-gate-review）', '',
              f'- {", ".join(setting) if setting else "読めない、またはファイルなし（codex のみ）"}', '',
              '## runs/ の容量', '', f'- {size / 1_000_000:.1f} MB（自動で削除しない）', '']
    return '\n'.join(lines) + '\n'


def notify(text):
    if shutil.which('osascript'):
        subprocess.run(['osascript', '-e', f'display notification {json.dumps(text)} with title "hermes 定期点検"'],
                       capture_output=True, timeout=30)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--update', action='store_true', help='move this detached check checkout to origin/main first')
    parser.add_argument('--notify', action='store_true', help='show a macOS notification with the result')
    args = parser.parse_args(argv)
    runs = ROOT / 'runs'
    stamp = datetime.now().strftime('%Y%m%d-%H%M')
    summaries = runs / 'periodic-summaries'
    summaries.mkdir(parents=True, exist_ok=True)
    summary_path = summaries / f'{stamp}.md'
    if summary_path.exists():
        print(f'summary already exists: {summary_path}', file=sys.stderr)
        return 2
    stop = update_checkout() if args.update else None
    result = previous = None
    if not stop:
        previous = previous_run(runs)
        out_dir = runs / f'periodic-{stamp}'
        command = [sys.executable, '-I', '-B', str(ROOT / 'scripts/report_github_work_guide.py'), 'collect', '--out', str(out_dir)]
        if previous:
            command[-2:-2] = ['--previous', str(previous)]
        start = time.monotonic()
        code, _, _ = run(command, timeout=600)
        seconds = time.monotonic() - start
        try:
            snapshot = json.loads((out_dir / 'snapshot.json').read_text(encoding='utf-8'))
            changes = json.loads((out_dir / 'diff.json').read_text(encoding='utf-8'))
            plan_file = out_dir / 'plan.json'
            plan = json.loads(plan_file.read_text(encoding='utf-8')) if plan_file.is_file() else None
            result = analyse(snapshot, plan, changes, seconds, datetime.now(timezone.utc))
        except (OSError, ValueError, KeyError, TypeError):
            stop = f'取得の結果を読めない（collect の終了コード {code}）'
        if result and (code != 0 or result['status'] != 'COMPLETE'):
            stop = f'取得が {result["status"]}（collect の終了コード {code}）。再試行はしない'
    ci, ci_error = main_ci()
    text = render(stamp, result, previous, ci, ci_error, review_setting(), runs_size(runs), stop)
    with summary_path.open('x', encoding='utf-8') as stream:
        stream.write(text)
    print(f'summary={summary_path}')
    if args.notify:
        attention = 0 if not result else len(result['acceptance']) + len(result['completion']) + len(result['stale']) + len(result['warnings'])
        notify(f'停止: {stop}' if stop else f'完了。要対応の候補 {attention}件。{summary_path.name}')
    return 1 if stop else 0


if __name__ == '__main__':
    sys.exit(main())
