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
                            60.0, NOW, True)
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

    def test_first_run_follows_previous_not_items(self):
        self.assertTrue(pc.analyse(snapshot([item(1)]), plan({}), [], 1.0, NOW)['first'])
        self.assertFalse(pc.analyse(snapshot([]), plan({}), [], 1.0, NOW, True)['first'])

    def test_naive_update_time_is_unknown_not_a_crash(self):
        result = pc.analyse(snapshot([item(1, updated='2026-01-01T00:00:00')]), plan({}), [], 1.0, NOW)
        self.assertEqual(result['stale'][0][2], '不明')


sys.path.insert(0, str(ROOT / 'tests'))
from test_github_work_guide import item as gw_item, snapshot as gw_snapshot  # noqa: E402
from github_work_guide.core import build_plan, save_run  # noqa: E402


class PreviousRunTests(unittest.TestCase):
    def save(self, runs, name):
        value = gw_snapshot(gw_item(7))
        save_run(runs / name, {'snapshot.json': value, 'plan.json': build_plan(value)})
        return runs / name

    def test_newest_loadable_periodic_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            runs = Path(tmp).resolve() / 'runs'
            older = self.save(runs, 'periodic-20261023-0900')
            newest = self.save(runs, 'periodic-20261030-0900')
            self.save(runs, 'wg-20261101-0900')  # not a periodic run
            (runs / 'periodic-summaries').mkdir()
            (runs / 'periodic-20261102-0900').mkdir()  # interrupted: no manifest
            self.assertEqual(pc.previous_run(runs), newest)
            # a run the harness cannot load (here: altered after saving) is skipped
            snap = newest / 'snapshot.json'
            snap.write_text(snap.read_text().replace('Synthetic', 'Altered', 1))
            self.assertEqual(pc.previous_run(runs), older)

    def test_no_previous(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertIsNone(pc.previous_run(Path(tmp)))
            self.assertIsNone(pc.previous_run(Path(tmp) / 'missing'))


class RunTests(unittest.TestCase):
    def test_timeout_and_missing_command_do_not_raise(self):
        self.assertEqual(pc.run(['sleep', '5'], timeout=1)[0], -1)
        self.assertEqual(pc.run(['no-such-command-for-periodic-check'])[0], -1)

    def test_notification_text_is_an_argument(self):
        calls = []
        with patch.object(pc, 'run', lambda args, **kw: calls.append(args) or (0, '', '')), \
                patch.object(pc.shutil, 'which', lambda name: '/usr/bin/osascript'):
            pc.notify('停止: "x" & do shell script "id"')
        args = calls[0]
        script = ' '.join(args[:args.index('--')])
        self.assertNotIn('do shell script', script)
        self.assertEqual(args[-1], '停止: "x" & do shell script "id"')


class UpdateGuardTests(unittest.TestCase):
    def git(self, cwd, *args):
        return subprocess.run(['git', '-c', 'user.name=t', '-c', 'user.email=t@example.invalid', *args],
                              cwd=cwd, check=True, capture_output=True, text=True).stdout.strip()

    def checkout(self, tmp, marker=True):
        """A detached clone of a bare 'origin' with two commits on main, sitting on the first one."""
        tmp = Path(tmp)
        seed = tmp / 'seed'
        seed.mkdir()
        self.git(seed, 'init', '-q', '-b', 'main')
        (seed / '.gitignore').write_text('runs/\n')
        self.git(seed, 'add', '.gitignore')
        self.git(seed, 'commit', '-q', '-m', 'one')
        self.git(seed, 'commit', '-q', '--allow-empty', '-m', 'two')
        self.git(tmp, 'clone', '-q', '--bare', str(seed), 'origin.git')
        work = tmp / 'work'
        self.git(tmp, 'clone', '-q', str(tmp / 'origin.git'), 'work')
        self.git(work, 'checkout', '-q', '--detach', 'HEAD~1')
        if marker:
            (work / 'runs').mkdir()
            (work / pc.MARKER).write_text('')
        return work

    def update(self, work):
        with patch.object(pc, 'ROOT', work):
            return pc.update_checkout()

    def test_moves_dedicated_checkout_to_origin_main(self):
        with tempfile.TemporaryDirectory() as tmp:
            work = self.checkout(tmp)
            self.assertIsNone(self.update(work))
            self.assertEqual(self.git(work, 'rev-parse', 'HEAD'), self.git(work, 'rev-parse', 'origin/main'))

    def test_refuses_without_marker(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertIn('is missing', self.update(self.checkout(tmp, marker=False)))

    def test_refuses_branch_checkout(self):
        with tempfile.TemporaryDirectory() as tmp:
            work = self.checkout(tmp)
            self.git(work, 'switch', '-q', 'main')
            self.assertIn('on branch', self.update(work))

    def test_refuses_changed_or_untracked_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            work = self.checkout(tmp)
            (work / 'note.txt').write_text('mine')
            self.assertIn('untracked', self.update(work))
            before = self.git(work, 'rev-parse', 'HEAD')
            (work / 'note.txt').unlink()
            (work / '.gitignore').write_text('changed\n')
            self.assertIn('changed', self.update(work))
            self.assertEqual(self.git(work, 'rev-parse', 'HEAD'), before)

    def test_refuses_commits_not_on_main(self):
        with tempfile.TemporaryDirectory() as tmp:
            work = self.checkout(tmp)
            self.git(work, 'commit', '-q', '--allow-empty', '-m', 'local only')
            local = self.git(work, 'rev-parse', 'HEAD')
            self.assertIn('not on origin/main', self.update(work))
            self.assertEqual(self.git(work, 'rev-parse', 'HEAD'), local)


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
