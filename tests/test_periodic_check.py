"""#59: scripts/periodic_check.py analysis and safety guards. No network/model; uses a temporary git repo."""
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import periodic_check as pc  # noqa: E402

NOW = datetime(2026, 10, 30, tzinfo=timezone.utc)


def item(n, state='OPEN', updated='2026-10-29T00:00:00Z', title=None):
    return {'kind': 'issue', 'number': n, 'state': state, 'title': title or f'Issue {n}',
            'raw': {'detail': {'updated_at': updated}}}


def snapshot(items, calls=120, status='COMPLETE'):
    return {'items': {f'issue:{i["number"]}': i for i in items},
            'coverage': {'status': status, 'calls': calls, 'omitted': 'x'}}


def plan(kinds):
    return {'candidates': {k: {'kind': v, 'label': v} for k, v in kinds.items()}}


class AnalyseTests(unittest.TestCase):
    def test_kinds_changes_and_stale(self):
        snap = snapshot([item(1), item(2, updated='2026-10-01T00:00:00Z'), item(3, state='CLOSED', updated='2026-01-01T00:00:00Z')])
        result = pc.analyse(snap, plan({'issue:1': 'acceptance', 'issue:2': 'completion', 'issue:3': 'none'}),
                            [{'target': 'issue:1', 'status': 'CHANGED'}, {'target': 'issue:2', 'status': 'UNCHANGED'}],
                            60.0, NOW)
        self.assertEqual(result['acceptance'], [('issue:1', 'acceptance')])
        self.assertEqual(result['completion'], [('issue:2', 'completion')])
        self.assertEqual([k for k, _, _ in result['stale']], ['issue:2'])  # closed items are not stale
        self.assertEqual(result['moved'], [('issue:1', 'CHANGED')])
        self.assertFalse(result['first'])
        self.assertEqual(result['warnings'], [])

    def test_limits_warn_at_eighty_percent(self):
        result = pc.analyse(snapshot([item(1)], calls=400), plan({}), [], 144.0, NOW)
        self.assertEqual(len(result['warnings']), 2)
        result = pc.analyse(snapshot([item(1)], calls=399), plan({}), [], 143.0, NOW)
        self.assertEqual(result['warnings'], [])

    def test_unknown_update_time_is_reported(self):
        result = pc.analyse(snapshot([item(1, updated=None)]), plan({}), [], 1.0, NOW)
        self.assertEqual(result['stale'][0][2], '不明')

    def test_first_run(self):
        result = pc.analyse(snapshot([item(1)]), plan({}), [{'target': 'issue:1', 'status': 'FIRST'}], 1.0, NOW)
        self.assertTrue(result['first'])


class PreviousRunTests(unittest.TestCase):
    def make(self, runs, name, files=('snapshot.json', 'plan.json')):
        path = runs / name
        path.mkdir(parents=True)
        (path / 'manifest.json').write_text(json.dumps({'files': {f: 'x' for f in files}}))
        return path

    def test_newest_complete_periodic_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            runs = Path(tmp)
            self.make(runs, 'periodic-20261023-0900')
            newest = self.make(runs, 'periodic-20261030-0900')
            self.make(runs, 'periodic-20261031-0900', files=('snapshot.json',))  # no plan: incomplete
            self.make(runs, 'wg-20261101-0900')  # not a periodic run
            (runs / 'periodic-summaries').mkdir()
            (runs / 'periodic-20261102-0900').mkdir()  # no manifest: interrupted
            self.assertEqual(pc.previous_run(runs), newest)

    def test_no_previous(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertIsNone(pc.previous_run(Path(tmp)))
            self.assertIsNone(pc.previous_run(Path(tmp) / 'missing'))


class UpdateGuardTests(unittest.TestCase):
    def git(self, cwd, *args):
        subprocess.run(['git', *args], cwd=cwd, check=True, capture_output=True)

    def repo(self, tmp):
        path = Path(tmp)
        self.git(path, 'init', '-q', '-b', 'main')
        self.git(path, '-c', 'user.name=t', '-c', 'user.email=t@example.invalid', 'commit', '-q', '--allow-empty', '-m', 'x')
        (path / 'f.txt').write_text('a')
        self.git(path, 'add', 'f.txt')
        self.git(path, '-c', 'user.name=t', '-c', 'user.email=t@example.invalid', 'commit', '-q', '-m', 'f')
        return path

    def test_refuses_branch_checkout(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self.repo(tmp)
            with patch.object(pc, 'ROOT', path):
                self.assertIn('on branch', pc.update_checkout())

    def test_refuses_tracked_changes_on_detached_checkout(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self.repo(tmp)
            self.git(path, 'checkout', '-q', '--detach')
            (path / 'f.txt').write_text('changed')
            with patch.object(pc, 'ROOT', path):
                self.assertIn('tracked changes', pc.update_checkout())

    def test_detached_clean_checkout_without_remote_reports_fetch_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self.repo(tmp)
            self.git(path, 'checkout', '-q', '--detach')
            with patch.object(pc, 'ROOT', path):
                self.assertIn('git fetch failed', pc.update_checkout())


class RenderTests(unittest.TestCase):
    def test_render_reports_stop_and_no_write_statement(self):
        text = pc.render('20261030-0900', None, None, None, 'gh なし', None, 0, stop='checkout is on branch x')
        self.assertIn('## 停止', text)
        self.assertIn('GitHubへの書き込み・削除・モデルの使用はしていない', text)
        self.assertIn('取得できない: gh なし', text)

    def test_render_flags_failed_main_ci(self):
        result = pc.analyse(snapshot([item(1)]), plan({'issue:1': 'scope'}), [], 10.0, NOW)
        ci = [{'name': 'CI', 'status': 'completed', 'conclusion': 'failure', 'headSha': 'a' * 40}]
        text = pc.render('20261030-0900', result, None, ci, None, ['claude-code'], 2_000_000)
        self.assertIn('mainで成功していないrunがある', text)
        self.assertIn('claude-code', text)
        self.assertIn('2.0 MB', text)


if __name__ == '__main__':
    unittest.main()
