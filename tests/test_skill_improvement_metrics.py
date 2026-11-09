#!/usr/bin/env python3
"""Work-day coverage and burden report tests (#108): temporary git repositories and PUBLIC synthetic data only."""
import ast
from datetime import date, datetime, timedelta, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from skill_improvement import commits, metrics  # noqa: E402
from skill_improvement.ledger import Ledger, LedgerError, Manifest, load_contract  # noqa: E402

FIXTURES = ROOT / 'fixtures' / 'skill_improvement'
REPORT_CLI = ROOT / 'scripts' / 'report_skill_improvement.py'
NOW = datetime(2026, 11, 15, 12, 0, 0, tzinfo=timezone.utc)
CORRECTION = {'type': 'CORRECTION', 'summary': '確認手順を飛ばした', 'refs': ['input:合成の訂正'],
              'cause': 'MISSING_PROCEDURE'}


class Clock:
    def __init__(self, moment=NOW):
        self.moment = moment

    def __call__(self):
        self.moment += timedelta(seconds=1)
        return self.moment


def jst(text):
    """'2026-11-02 10:00' in Asia/Tokyo as a git date in UTC."""
    moment = datetime.fromisoformat(text).replace(tzinfo=timezone(timedelta(hours=9)))
    return moment.astimezone(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


class Repo:
    """A throwaway git repository whose commit dates and authors are set explicitly."""

    def __init__(self, path, home):
        self.path, self.home = path, home
        path.mkdir()
        self.git('init', '-q', '-b', 'main')

    def git(self, *args, when='2026-11-02 09:00', name='Dev', email='dev@example.invalid'):
        env = {'PATH': os.environ.get('PATH', '/usr/bin:/bin'), 'HOME': str(self.home), 'LC_ALL': 'C',
               'GIT_CONFIG_NOSYSTEM': '1', 'GIT_CONFIG_GLOBAL': os.devnull,
               'GIT_AUTHOR_NAME': name, 'GIT_AUTHOR_EMAIL': email, 'GIT_COMMITTER_NAME': name,
               'GIT_COMMITTER_EMAIL': email, 'GIT_AUTHOR_DATE': jst(when), 'GIT_COMMITTER_DATE': jst(when)}
        done = subprocess.run(['git', '-C', str(self.path), *args], env=env, capture_output=True, text=True,
                              timeout=60, check=False)
        if done.returncode:
            raise AssertionError(done.stderr)
        return done.stdout.strip()

    def commit(self, when, name='Dev', email='dev@example.invalid', file='work.txt'):
        target = self.path / file
        target.write_text(target.read_text() + when + '\n' if target.exists() else when + '\n')
        self.git('add', file, when=when, name=name, email=email)
        self.git('commit', '-q', '-m', f'work {when}', when=when, name=name, email=email)
        return self.git('rev-parse', 'HEAD')


def manifest_data(checkout, branches=('main', 'feature/a', 'gone')):
    data = json.loads((FIXTURES / 'manifest.example.json').read_text(encoding='utf-8'))
    data['ledger_location'] = {'kind': 'PUBLIC_FIXTURE', 'label': 'skill-ledger'}
    data['period'] = {'start_date': '2026-11-02', 'end_date': '2026-11-15'}
    if checkout is not None:
        data['repositories'][0]['local_checkout'] = str(checkout)
        data['repositories'][0]['allowed_branches'] = list(branches)
    return data


class MetricsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.contract = load_contract()

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(os.path.realpath(self.temp.name))
        self.home = self.base / 'home'
        self.home.mkdir()
        self.directory = self.base / 'skill-ledger'
        self.directory.mkdir()
        self.repo = Repo(self.base / 'demo-app', self.home)
        self.build_history()
        self.use_manifest(manifest_data(self.repo.path))

    def tearDown(self):
        self.temp.cleanup()

    def use_manifest(self, data):
        self.data = data
        self.raw = json.dumps(data).encode('utf-8')
        self.manifest = Manifest(data, self.contract, NOW)
        self.ledger = Ledger(self.directory, self.manifest, self.contract, Clock())

    def build_history(self):
        repo = self.repo
        repo.commit('2026-11-01 23:00')                      # before the period
        repo.commit('2026-11-02 10:00')
        repo.commit('2026-11-02 18:00')                      # same day: one work day
        repo.commit('2026-11-03 11:00', name='helper[bot]', email='helper[bot]@example.invalid')
        repo.git('checkout', '-q', '-b', 'feature/a')
        repo.commit('2026-11-06 00:30', file='feature.txt')  # 2026-11-05 15:30 UTC: the JST date counts
        repo.git('checkout', '-q', 'main')
        repo.git('merge', '-q', '--no-ff', '-m', 'merge', 'feature/a', when='2026-11-04 12:00')  # merges do not count
        repo.git('checkout', '-q', '-b', 'other')
        picked = repo.commit('2026-11-07 10:00', file='other.txt')  # branch not allowed: 11-07 is not a work day
        repo.git('checkout', '-q', 'main')
        repo.git('cherry-pick', '-x', picked, when='2026-11-09 09:00')  # counts on the day it was applied

    def record_ledger(self):
        ledger = self.ledger
        ledger.record_end('demo-app', 'wu-1', 'NO_CANDIDATE', '2026-11-02')
        ledger.record_end('demo-app', 'wu-2', 'CANDIDATE_FOUND', '2026-11-02', experiences=[CORRECTION])
        ledger.record_end('demo-app', 'wu-3', 'UNDETERMINED', '2026-11-06', reason='合成: 判断できない')  # late record
        ledger.record_end('demo-app', 'wu-4', 'NO_CANDIDATE', '2026-11-12')   # no commit and no work_day
        ledger.record_work_day('demo-cli', 'wu-cli-doc', '設計メモだけ', '2026-11-10')
        end = ledger.record_end('demo-cli', 'wu-cli-doc', 'NO_CANDIDATE', '2026-11-10')
        ledger.record_effort('demo-cli', 'wu-cli-doc', 'RECORD', 3, end['event_ids'][0], '2026-11-10')

    def report(self, **kwargs):
        return metrics.build_report(self.manifest, self.raw, self.ledger, **kwargs)

    # --- Done 1: work-day coverage over commits and registered days ---

    def test_coverage_counts_work_days_across_branches_and_boundaries(self):
        self.record_ledger()
        report = self.report()
        self.assertEqual(report['status'], 'COMPUTED')
        coverage = report['coverage']
        # demo-app commit days: 11-02, 11-06, 11-09 (bot, merge, before-period and other-branch commits excluded).
        # demo-cli has no checkout; its registered work day 11-10 is the only source.
        self.assertEqual(coverage['sources'], {'commit_days': 3, 'registered_days': 1, 'registered_only_days': 1})
        self.assertEqual((coverage['work_days'], coverage['recorded_work_days'], coverage['rate']), (4, 3, 0.75))
        self.assertEqual(coverage['unrecorded_work_days'], [['demo-app', '2026-11-09']])
        self.assertEqual(coverage['end_records'], 5)
        self.assertEqual(coverage['end_records_outside_work_days'], 1)
        self.assertEqual(coverage['undetermined_rate'], 0.2)
        weeks = report['weeks']
        self.assertEqual([week['week_start'] for week in weeks], ['2026-11-02', '2026-11-09'])
        self.assertEqual([(week['work_days'], week['recorded_work_days'], week['coverage']) for week in weeks],
                         [(2, 2, 1.0), (2, 1, 0.5)])
        self.assertEqual(report['commits']['demo-app']['bot_commits_excluded'], 1)
        self.assertEqual(report['commits']['demo-app']['missing_branches'], ['gone'])
        self.assertTrue(any('demo-app:gone' in item for item in report['limits']))
        self.assertTrue(any('demo-cli' in item for item in report['limits']))
        self.assertEqual(report['cache'], 'SAVED')

    def test_empty_denominator_is_not_zero_and_missing_effort_is_undetermined(self):
        self.use_manifest(manifest_data(None))
        report = self.report()
        self.assertEqual(report['coverage']['work_days'], 0)
        self.assertIsNone(report['coverage']['rate'])
        self.assertIsNone(report['coverage']['undetermined_rate'])
        self.assertEqual(report['automation']['conditions']['coverage']['result'], 'UNDETERMINED')
        self.assertEqual(report['automation']['conditions']['weekly_minutes']['result'], 'UNDETERMINED')
        self.assertEqual(report['recording_aid']['verdict'], 'UNDETERMINED')

    def test_sub_period_and_period_errors(self):
        self.record_ledger()
        report = self.report(start='2026-11-09', end='2026-11-15')
        self.assertEqual((report['coverage']['work_days'], report['coverage']['recorded_work_days']), (2, 1))
        self.assertEqual(report['automation']['conditions']['period_days']['result'], 'NOT_MET')
        for start, end, code in (('2026-11-01', None, 'OUTSIDE_PERIOD'), (None, '2026-11-16', 'OUTSIDE_PERIOD'),
                                 ('2026-11-10', '2026-11-09', 'PERIOD_INVALID'), ('2026-11-2', None, 'PERIOD_INVALID')):
            with self.assertRaises(LedgerError) as caught:
                self.report(start=start, end=end)
            self.assertEqual(caught.exception.code, code)

    # --- Done 2: no change → no recompute; changes → recompute ---

    def test_unchanged_inputs_reuse_the_cache_without_reading_commits(self):
        self.record_ledger()
        first = self.report()
        with mock.patch.object(metrics, 'commit_dates', side_effect=AssertionError('git log must not run')):
            again = self.report()
        self.assertEqual(again['status'], 'UNCHANGED')
        self.assertEqual(again['fingerprint'], first['fingerprint'])
        self.assertEqual(again['coverage'], first['coverage'])
        self.ledger.record_end('demo-app', 'wu-5', 'NO_CANDIDATE', '2026-11-09')
        changed = self.report()
        self.assertEqual(changed['status'], 'COMPUTED')
        self.assertEqual(changed['coverage']['rate'], 1.0)
        self.repo.commit('2026-11-11 10:00')
        self.assertEqual(self.report()['status'], 'COMPUTED')
        self.assertEqual(self.report(start='2026-11-03')['status'], 'COMPUTED')

    def test_broken_cache_is_recomputed_not_trusted(self):
        first = self.report()
        (self.directory / metrics.CACHE_FILE).write_text('{"fingerprint": "' + first['fingerprint'] + '", "report": [')
        self.assertEqual(self.report()['status'], 'COMPUTED')
        (self.directory / metrics.CACHE_FILE).unlink()
        os.mkfifo(self.directory / metrics.CACHE_FILE)
        self.assertEqual(self.report()['status'], 'COMPUTED')

    # --- Boundaries: what may be read ---

    def test_checkout_must_be_canonical_git_tree_outside_hermes_home(self):
        link = self.base / 'link-app'
        link.symlink_to(self.repo.path)
        plain = self.base / 'plain'
        plain.mkdir()
        hermes = Path.home() / '.hermes' / 'repo'
        for path in (link, plain, self.base / 'missing', hermes, Path(str(Path.home()).upper()) / '.HERMES' / 'x',
                     Path('/System/Volumes/Data') / str(self.repo.path).lstrip('/'),
                     Path(str(self.repo.path) + '/../demo-app')):
            item = dict(self.data['repositories'][0], local_checkout=str(path))
            with mock.patch('os.path.realpath', wraps=os.path.realpath) as realpath:
                with self.assertRaises(LedgerError, msg=str(path)) as caught:
                    commits.git_directory(item)
            self.assertEqual(caught.exception.code, 'REPOSITORY_UNAVAILABLE')
            if 'hermes' in str(path).lower():
                realpath.assert_not_called()

    def test_only_local_rev_parse_and_log_run(self):
        self.assertEqual(commits.ALLOWED_SUBCOMMANDS, ('rev-parse', 'log'))
        for subcommand in ('fetch', 'pull', 'remote', 'clone', 'ls-remote', 'push', 'config'):
            with self.assertRaises(LedgerError):
                commits.run_git(self.repo.path, subcommand)
        tree = ast.parse((ROOT / 'src' / 'skill_improvement' / 'commits.py').read_text(encoding='utf-8'))
        calls = [node for node in ast.walk(tree) if isinstance(node, ast.Call)
                 and getattr(node.func, 'id', None) == 'run_git']
        self.assertTrue(calls)
        for call in calls:
            self.assertIsInstance(call.args[1], ast.Constant)
            self.assertIn(call.args[1].value, commits.ALLOWED_SUBCOMMANDS)
        environment = commits.git_environment()
        self.assertEqual((environment['GIT_CONFIG_GLOBAL'], environment['GIT_CONFIG_NOSYSTEM'],
                          environment['GIT_TERMINAL_PROMPT'], environment['GIT_NO_REPLACE_OBJECTS'],
                          environment['GIT_NO_LAZY_FETCH']), (os.devnull, '1', '0', '1', '1'))
        forbidden = {'socket', 'http', 'urllib', 'requests', 'ssl', 'asyncio', 'openai', 'anthropic'}
        for name in ('metrics.py', 'commits.py', 'cli.py'):
            tree = ast.parse((ROOT / 'src' / 'skill_improvement' / name).read_text(encoding='utf-8'))
            names = {alias.name.split('.')[0] for node in ast.walk(tree) if isinstance(node, ast.Import)
                     for alias in node.names}
            names |= {node.module.split('.')[0] for node in ast.walk(tree)
                      if isinstance(node, ast.ImportFrom) and node.module}
            self.assertFalse(names & forbidden, name)
            if name != 'commits.py':
                self.assertNotIn('subprocess', names, name)

    def test_repository_list_does_not_change_records(self):
        """The report never writes the ledger: only the cache file is added beside it."""
        self.record_ledger()
        before = (self.directory / 'ledger.jsonl').read_bytes()
        self.report()
        self.assertEqual((self.directory / 'ledger.jsonl').read_bytes(), before)
        self.assertEqual(sorted(path.name for path in self.directory.iterdir()),
                         ['ledger.jsonl', 'ledger.lock', metrics.CACHE_FILE])
        status = subprocess.run(['git', '-C', str(self.repo.path), 'status', '--porcelain'], capture_output=True,
                                text=True, timeout=60, check=False,
                                env={'PATH': os.environ.get('PATH', ''), 'HOME': str(self.home),
                                     'GIT_CONFIG_NOSYSTEM': '1', 'GIT_CONFIG_GLOBAL': os.devnull})
        self.assertEqual(status.stdout, '')

    def test_checkout_config_cannot_start_a_signature_program(self):
        marker = self.base / 'gpg-ran'
        script = self.base / 'fake-gpg'
        script.write_text('#!/bin/sh\ntouch "' + str(marker) + '"\nexit 1\n')
        script.chmod(0o755)
        body = self.repo.git('cat-file', 'commit', 'HEAD')
        head, _, message = body.partition('\n\n')
        signature = 'gpgsig -----BEGIN PGP SIGNATURE-----\n \n AAAA\n -----END PGP SIGNATURE-----'
        signed = head + '\n' + signature + '\n\n' + message + '\n'
        path = self.base / 'signed-commit'
        path.write_text(signed)
        sha = self.repo.git('hash-object', '-t', 'commit', '-w', str(path))
        self.repo.git('update-ref', 'refs/heads/main', sha)
        self.repo.git('config', 'log.showSignature', 'true')
        self.repo.git('config', 'gpg.program', str(script))
        # Positive control: plain git with this checkout's config does run the program.
        self.repo.git('log', '-1', '--format=%H', 'main')
        self.assertTrue(marker.exists())
        marker.unlink()
        report = self.report()
        self.assertEqual(report['status'], 'COMPUTED')
        self.assertFalse(marker.exists())

    def test_git_pointer_files_must_stay_outside_hermes_home(self):
        hermes_git = Path.home() / '.hermes' / 'r' / '.git'
        checkout = self.base / 'pointer-app'
        checkout.mkdir()
        (checkout / '.git').write_text(f'gitdir: {hermes_git}\n')
        with mock.patch('os.path.realpath', wraps=os.path.realpath) as realpath:
            with self.assertRaises(LedgerError) as caught:
                commits.git_directory(dict(self.data['repositories'][0], local_checkout=str(checkout)))
        self.assertEqual(caught.exception.code, 'REPOSITORY_UNAVAILABLE')
        self.assertFalse(any('.hermes' in str(call).lower() for call in realpath.call_args_list))
        # A worktree has a gitdir file and a commondir; both are followed and checked.
        worktree = self.base / 'worktree-app'
        self.repo.git('worktree', 'add', '-q', str(worktree), 'feature/a')
        item = dict(self.data['repositories'][0], local_checkout=str(worktree))
        gitdir, common = commits.git_directory(item)
        self.assertEqual(common, self.repo.path / '.git')
        self.assertIn('main', commits.branch_tips(item)[0])
        (gitdir / 'commondir').write_text(str(hermes_git) + '\n')
        with self.assertRaises(LedgerError):
            commits.git_directory(item)

    def test_alternates_and_config_includes_are_refused(self):
        item = self.data['repositories'][0]
        config = self.repo.path / '.git' / 'config'
        original = config.read_text()
        config.write_text(original + '[includeIf "gitdir:/"]\n\tpath = /elsewhere/config\n')
        with self.assertRaises(LedgerError):
            commits.git_directory(item)
        for header in ('[core] [include]\n\tpath = /elsewhere/config\n', '[ Include ]\n\tpath = /elsewhere\n'):
            config.write_text(original + header)
            with self.assertRaises(LedgerError, msg=header):
                commits.git_directory(item)
        config.write_text(original)
        alternates = self.repo.path / '.git' / 'objects' / 'info' / 'alternates'
        alternates.parent.mkdir(exist_ok=True)
        alternates.write_text('/elsewhere/objects\n')
        with self.assertRaises(LedgerError):
            commits.git_directory(item)

    def test_symlinks_inside_the_git_directory_are_refused(self):
        item = self.data['repositories'][0]
        elsewhere = self.base / 'elsewhere-refs'
        elsewhere.mkdir()
        heads = self.repo.path / '.git' / 'refs' / 'heads'
        (heads / 'linked').symlink_to(elsewhere)
        with self.assertRaises(LedgerError) as caught:
            commits.git_directory(item)
        self.assertEqual(caught.exception.code, 'REPOSITORY_UNAVAILABLE')
        (heads / 'linked').unlink()
        commits.git_directory(item)
        # hooks are not read by rev-parse or log, so a linked hook does not block the report.
        (self.repo.path / '.git' / 'hooks' / 'pre-commit').symlink_to(elsewhere)
        commits.git_directory(item)

    def test_pointer_files_may_use_dot_dot_only_at_the_start(self):
        worktree = self.base / 'worktree-dots'
        self.repo.git('worktree', 'add', '-q', str(worktree), 'feature/a')
        item = dict(self.data['repositories'][0], local_checkout=str(worktree))
        gitdir, _ = commits.git_directory(item)
        self.assertEqual((gitdir / 'commondir').read_text().strip(), '../..')
        (gitdir / 'commondir').write_text('x/../../..\n')
        with self.assertRaises(LedgerError):
            commits.git_directory(item)

    def test_unreadable_repository_stops_the_report_without_cache(self):
        broken = self.base / 'broken-app'
        (broken / '.git').mkdir(parents=True)
        data = manifest_data(broken)
        self.use_manifest(data)
        with self.assertRaises(LedgerError) as caught:
            self.report()
        self.assertEqual(caught.exception.code, 'REPOSITORY_UNAVAILABLE')
        self.assertFalse((self.directory / metrics.CACHE_FILE).exists())

    def test_public_fixture_ledger_reads_only_public_checkouts(self):
        data = manifest_data(self.repo.path)
        data['repositories'][0]['classification'] = 'INTERNAL'
        self.use_manifest(data)
        with self.assertRaises(LedgerError) as caught:
            self.report()
        self.assertEqual(caught.exception.code, 'CLASSIFICATION_NOT_PUBLIC')

    # --- Done 3: automation conditions over 14 days of synthetic data ---

    def synthetic(self, days, candidates, effort_minutes, recorded_ratio=1.0):
        """Rows shaped like ledger rows for compute(): one work day per date, one end per recorded day."""
        start = date(2026, 11, 2)
        rows, commit_days = [], {'demo-app': set()}

        def row(day, kind, **record):
            return {'repository_id': 'demo-app', 'work_unit_id': f'wu-{len(rows)}', 'work_date': day.isoformat(),
                    'event_id': f'e{len(rows)}', 'record': dict(record, kind=kind)}

        for offset in range(days):
            day = start + timedelta(days=offset)
            commit_days['demo-app'].add(day)
            if offset < round(days * recorded_ratio):
                rows.append(row(day, 'session_end', status='NO_CANDIDATE'))
        for index in range(candidates):
            rows.append(row(start, 'candidate', candidate_id=f'c{index}', state={'status': 'OPEN'}))
        if effort_minutes:
            rows.append(row(start, 'effort', activity='CANDIDATE', minutes=effort_minutes, subject_id='c0'))
        end = start + timedelta(days=days - 1)
        return metrics.compute(self.manifest, rows, start, end, commit_days, {})

    def test_automation_conditions_met_not_met_and_undetermined(self):
        met = self.synthetic(14, 4, 61)
        self.assertEqual(met['automation']['verdict'], 'CONDITIONS_MET')
        self.assertEqual(met['effort_minutes']['weekly_average'], 30.5)
        self.assertIn('承認ではない', ' '.join(met['limits']))
        self.assertEqual(self.synthetic(14, 4, 60)['automation']['verdict'], 'NOT_MET')   # 30 min/week is not > 30
        self.assertEqual(self.synthetic(14, 3, 120)['automation']['verdict'], 'NOT_MET')
        self.assertEqual(self.synthetic(13, 4, 120)['automation']['verdict'], 'NOT_MET')
        low = self.synthetic(14, 4, 120, recorded_ratio=0.5)
        self.assertEqual(low['automation']['conditions']['coverage']['result'], 'NOT_MET')
        self.assertEqual(low['recording_aid']['verdict'], 'SUGGESTED')
        self.assertEqual(self.synthetic(14, 4, 0)['automation']['verdict'], 'UNDETERMINED')

    def test_duplicates_do_not_count_as_independent_candidates(self):
        self.ledger.record_end('demo-app', 'wu-1', 'CANDIDATE_FOUND', '2026-11-02', experiences=[CORRECTION])
        self.ledger.record_end('demo-app', 'wu-2', 'CANDIDATE_FOUND', '2026-11-03', experiences=[CORRECTION])
        rows = self.ledger.read()
        experiences = [row['record']['experience_id'] for row in rows if row['record']['kind'] == 'experience']
        self.ledger.propose('demo-app', 'wu-1', [experiences[0]], 'pr-review', 'MISSING_PROCEDURE',
                            work_date='2026-11-02')
        duplicate = self.ledger.propose('demo-app', 'wu-2', [experiences[1]], 'pr-review', 'MISSING_PROCEDURE',
                                        work_date='2026-11-03')
        self.assertEqual(duplicate['state']['status'], 'DUPLICATE')
        report = self.report()
        self.assertEqual(report['candidates'], {'independent': 1, 'by_state': {'OPEN': 1, 'DUPLICATE': 1}})

    def test_recording_aid_uses_minutes_per_end(self):
        self.record_ledger()
        # Coverage 0.75 < 0.8 already suggests the aid; minutes per end alone also can.
        self.assertEqual(self.report()['recording_aid']['verdict'], 'SUGGESTED')
        self.ledger.record_end('demo-app', 'wu-5', 'NO_CANDIDATE', '2026-11-09')
        report = self.report()
        self.assertEqual(report['coverage']['rate'], 1.0)
        # Only the end record with a RECORD time is averaged (3 minutes for one end), not all six ends.
        self.assertEqual(report['recording_aid']['record_minutes_per_end'], 3.0)
        self.assertEqual(report['recording_aid']['verdict'], 'NOT_SUGGESTED')

    # --- CLI ---

    def test_cli_prints_report_and_refuses_without_echo(self):
        today = datetime.now(timezone.utc).date()
        data = manifest_data(self.repo.path)
        data['period'] = {'start_date': (today - timedelta(days=20)).isoformat(),
                          'end_date': (today + timedelta(days=3)).isoformat()}
        manifest_path = self.base / 'manifest.json'
        manifest_path.write_text(json.dumps(data), encoding='utf-8')

        def run(*args):
            return subprocess.run([sys.executable, '-I', '-B', str(REPORT_CLI), '--manifest', str(manifest_path),
                                   '--ledger', str(self.directory), *args], capture_output=True, text=True,
                                  timeout=60, check=False)

        first = run()
        self.assertEqual(first.returncode, 0, first.stderr)
        self.assertEqual(json.loads(first.stdout)['status'], 'COMPUTED')
        self.assertEqual(json.loads(run().stdout)['status'], 'UNCHANGED')
        leaked = 'ghp' + '_' + 'A' * 36
        for args in (('--start', leaked), ('--bogus', leaked)):
            done = run(*args)
            self.assertEqual(done.returncode, 2, args)
            self.assertIn('"error"', done.stderr)
            self.assertNotIn(leaked, done.stderr + done.stdout)


if __name__ == '__main__':
    unittest.main()
