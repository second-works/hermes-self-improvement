#!/usr/bin/env python3
"""Ledger CLI tests (#107): PUBLIC synthetic data in temporary directories only."""
import ast
import copy
from datetime import datetime, timedelta, timezone
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
from skill_improvement import ledger as ledger_module  # noqa: E402
from skill_improvement.ledger import Ledger, LedgerError, Manifest, load_contract, summary  # noqa: E402

FIXTURES = ROOT / 'fixtures' / 'skill_improvement'
CLI = ROOT / 'scripts' / 'record_skill_experience.py'
NOW = datetime(2026, 11, 5, 3, 0, 0, tzinfo=timezone.utc)
CORRECTION = {'type': 'CORRECTION', 'summary': 'レビュー前に変更範囲の確認を飛ばした',
              'refs': ['input:利用者の訂正'], 'cause': 'MISSING_PROCEDURE'}


def manifest_data(kind='PUBLIC_FIXTURE', label='skill-ledger'):
    data = json.loads((FIXTURES / 'manifest.example.json').read_text(encoding='utf-8'))
    data['ledger_location'] = {'kind': kind, 'label': label}
    return data


class Clock:
    def __init__(self, moment=NOW):
        self.moment = moment

    def __call__(self):
        self.moment += timedelta(seconds=1)
        return self.moment


class LedgerTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.contract = load_contract()

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(os.path.realpath(self.temp.name))
        self.directory = self.base / 'skill-ledger'
        self.directory.mkdir()
        self.manifest = Manifest(manifest_data(), self.contract, NOW)
        self.clock = Clock()
        self.ledger = Ledger(self.directory, self.manifest, self.contract, self.clock)

    def tearDown(self):
        self.temp.cleanup()

    def file(self):
        return self.directory / 'ledger.jsonl'

    def raw(self):
        return self.file().read_bytes() if self.file().exists() else b''

    def refused(self, code, call, *args, **kwargs):
        before = self.raw()
        with self.assertRaises(LedgerError) as caught:
            call(*args, **kwargs)
        self.assertEqual(caught.exception.code, code, caught.exception)
        self.assertEqual(self.raw(), before, 'a refusal must leave the ledger unchanged')

    # --- Done 1: four experience types, no candidate and undetermined across two repositories ---

    def test_records_all_results_and_types_across_two_repositories_and_reloads(self):
        types = ['CORRECTION', 'REWORK', 'REPEATED_FEEDBACK', 'BETTER_METHOD']
        found = self.ledger.record_end('demo-app', 'wu-app-1', 'CANDIDATE_FOUND', '2026-11-04', experiences=[
            dict(CORRECTION, type=kind, summary=f'{kind}の合成例') for kind in types[:2]])
        self.ledger.record_end('demo-cli', 'wu-cli-1', 'CANDIDATE_FOUND', '2026-11-04', experiences=[
            {'type': kind, 'summary': f'{kind}の合成例', 'refs': ['pr-review:7']} for kind in types[2:]])
        self.ledger.record_end('demo-app', 'wu-app-2', 'NO_CANDIDATE', '2026-11-04')
        self.ledger.record_end('demo-cli', 'wu-cli-2', 'UNDETERMINED', '2026-11-05', reason='途中で終わり判断できない')
        self.assertEqual(found['status'], 'RECORDED')
        self.assertEqual(len(found['experience_ids']), 2)
        rows = Ledger(self.directory, self.manifest, self.contract).read()
        self.assertEqual({row['record']['experience_type'] for row in rows if row['record']['kind'] == 'experience'},
                         set(types))
        self.assertEqual({row['repository_id'] for row in rows}, {'demo-app', 'demo-cli'})
        counts = summary(rows)
        # Two experiences in one end record still count that end record once.
        self.assertEqual(counts['session_ends'], {'CANDIDATE_FOUND': 2, 'NO_CANDIDATE': 1, 'UNDETERMINED': 1})
        self.assertEqual(counts['experiences'], 4)
        unclassified = [row for row in rows if row['record'].get('cause') == 'UNCLASSIFIED']
        self.assertEqual(len(unclassified), 2)
        for row in rows:
            self.assertEqual((row['schema_version'], row['timezone'], row['classification']), (1, 'Asia/Tokyo', 'PUBLIC'))
        self.assertEqual(oct(os.stat(self.file()).st_mode & 0o777), '0o600')

    def test_short_inputs_need_no_experience_details(self):
        self.refused('NO_CANDIDATE_TAKES_NO_DETAILS', self.ledger.record_end, 'demo-app', 'wu-1', 'NO_CANDIDATE',
                     '2026-11-04', experiences=[CORRECTION])
        self.refused('REASON_REQUIRED', self.ledger.record_end, 'demo-app', 'wu-1', 'UNDETERMINED', '2026-11-04')
        self.refused('EXPERIENCE_REQUIRED', self.ledger.record_end, 'demo-app', 'wu-1', 'CANDIDATE_FOUND', '2026-11-04')
        self.refused('REFS_INVALID', self.ledger.record_end, 'demo-app', 'wu-1', 'CANDIDATE_FOUND', '2026-11-04',
                     experiences=[dict(CORRECTION, refs=[])])
        self.refused('SUMMARY_INVALID', self.ledger.record_end, 'demo-app', 'wu-1', 'CANDIDATE_FOUND', '2026-11-04',
                     experiences=[dict(CORRECTION, summary='一行目\n二行目')])
        self.refused('SUMMARY_INVALID', self.ledger.record_end, 'demo-app', 'wu-1', 'CANDIDATE_FOUND', '2026-11-04',
                     experiences=[dict(CORRECTION, summary='長' * 121)])
        result = self.ledger.record_end('demo-app', 'wu-1', 'NO_CANDIDATE')
        self.assertEqual(self.ledger.read()[0]['work_date'], '2026-11-05')
        self.assertEqual(result['status'], 'RECORDED')

    # --- Done 2: re-sends and same-basis candidates do not multiply; same-day records stay distinct ---

    def test_resend_is_a_no_op_and_changed_resend_is_refused(self):
        first = self.ledger.record_end('demo-app', 'wu-1', 'CANDIDATE_FOUND', '2026-11-04', experiences=[CORRECTION])
        before = self.raw()
        again = self.ledger.record_end('demo-app', 'wu-1', 'CANDIDATE_FOUND', '2026-11-04', experiences=[CORRECTION])
        self.assertEqual(again['status'], 'ALREADY_RECORDED')
        self.assertEqual(again['event_ids'], first['event_ids'])
        self.assertEqual(self.raw(), before)
        self.refused('WORK_UNIT_ALREADY_ENDED', self.ledger.record_end, 'demo-app', 'wu-1', 'NO_CANDIDATE', '2026-11-04')
        # Same day, same repository, different work units: two distinct end records.
        self.ledger.record_end('demo-app', 'wu-2', 'NO_CANDIDATE', '2026-11-04')
        self.ledger.record_end('demo-app', 'wu-3', 'NO_CANDIDATE', '2026-11-04')
        ends = [row for row in self.ledger.read() if row['record']['kind'] == 'session_end']
        self.assertEqual(len({row['event_id'] for row in ends}), 3)
        self.assertEqual({row['work_date'] for row in ends}, {'2026-11-04'})

    def test_same_basis_candidates_link_to_the_original(self):
        app = self.ledger.record_end('demo-app', 'wu-app', 'CANDIDATE_FOUND', '2026-11-04', experiences=[
            dict(CORRECTION, refs=['input:共通の指摘'])])['experience_ids']
        cli = self.ledger.record_end('demo-cli', 'wu-cli', 'CANDIDATE_FOUND', '2026-11-04', experiences=[
            dict(CORRECTION, type='REPEATED_FEEDBACK', refs=['input:共通の指摘'])])['experience_ids']
        original = self.ledger.propose('demo-app', 'triage', app, 'pr-review', 'MISSING_PROCEDURE')
        self.assertEqual(original['state'], {'status': 'OPEN'})
        resent = self.ledger.propose('demo-app', 'triage', app, 'pr-review', 'MISSING_PROCEDURE')
        self.assertEqual((resent['status'], resent['candidate_id']), ('ALREADY_RECORDED', original['candidate_id']))
        # A second proposal citing the same evidence becomes a DUPLICATE of the first, not a new OPEN one.
        duplicate = self.ledger.propose('demo-cli', 'triage', cli, 'pr-review', 'MISSING_PROCEDURE')
        self.assertEqual(duplicate['state']['status'], 'DUPLICATE')
        self.assertEqual(duplicate['state']['duplicate_of'], original['candidate_id'])
        rows = self.ledger.read()
        record = [row for row in rows if row['record'].get('candidate_id') == duplicate['candidate_id']][0]['record']
        self.assertTrue(set(app) & set(record['experience_ids']))
        self.assertEqual(summary(rows)['candidates'], {'OPEN': 1, 'DUPLICATE': 1})
        # A different skill is a different candidate.
        other = self.ledger.propose('demo-cli', 'triage', cli, 'ci-triage', 'MISSING_PROCEDURE')
        self.assertEqual(other['state'], {'status': 'OPEN'})
        self.refused('CANDIDATE_CONFLICT', self.ledger.propose, 'demo-app', 'triage', app, 'pr-review', 'NOT_LOADED')

    def test_cause_sets_the_initial_state_and_state_changes_follow_the_table(self):
        ids = self.ledger.record_end('demo-app', 'wu-1', 'CANDIDATE_FOUND', '2026-11-04', experiences=[
            dict(CORRECTION, refs=[f'input:例{index}']) for index in range(3)])['experience_ids']
        temporary = self.ledger.propose('demo-app', 'triage', [ids[0]], 'ci-triage', 'TEMPORARY')
        self.assertEqual(temporary['state']['status'], 'DECLINED')
        held = self.ledger.propose('demo-app', 'triage', [ids[1]], 'pr-review', 'CONFLICT_OR_UNVERIFIED')
        self.assertEqual(held['state']['status'], 'HOLD')
        opened = self.ledger.set_state(held['candidate_id'], 'OPEN', None)
        self.assertEqual(opened['state'], {'status': 'OPEN'})
        self.assertEqual(self.ledger.set_state(held['candidate_id'], 'OPEN', None)['status'], 'ALREADY_RECORDED')
        self.refused('NEW_ROW_REJECTED', self.ledger.set_state, temporary['candidate_id'], 'OPEN', None)
        self.refused('STATE_NOT_ALLOWED_HERE', self.ledger.set_state, held['candidate_id'], 'DEPLOYED', 'x')
        self.refused('STATE_NOT_ALLOWED_HERE', self.ledger.set_state, held['candidate_id'], 'MAYBE', 'x')
        self.refused('CANDIDATE_NOT_FOUND', self.ledger.set_state, 'c-missing', 'HOLD', '理由')
        self.refused('DUPLICATE_BASIS_MISSING', self.ledger.set_state, held['candidate_id'], 'DUPLICATE', '重複',
                     duplicate_of=temporary['candidate_id'])
        self.refused('EXPERIENCE_NOT_FOUND', self.ledger.propose, 'demo-app', 'triage', ['x-missing'], 'pr-review',
                     'MISSING_PROCEDURE')
        self.refused('DUPLICATE_TARGET_REQUIRED', self.ledger.propose, 'demo-app', 'triage', [ids[2]], 'pr-review',
                     'DUPLICATE')

    def test_shared_scope_needs_an_experience_in_each_listed_repository(self):
        app = self.ledger.record_end('demo-app', 'wu-a', 'CANDIDATE_FOUND', '2026-11-04',
                                     experiences=[CORRECTION])['experience_ids']
        cli = self.ledger.record_end('demo-cli', 'wu-c', 'CANDIDATE_FOUND', '2026-11-04', experiences=[
            dict(CORRECTION, refs=['pr-review:8'])])['experience_ids']
        repeated = {'type': 'SHARED', 'basis': 'REPEATED_IN_REPOSITORIES', 'repository_ids': ['demo-app', 'demo-cli'],
                    'decided_by': 'example-owner'}
        self.refused('SHARED_BASIS_NOT_SHOWN', self.ledger.propose, 'demo-app', 'triage', app, 'pr-review',
                     'MISSING_PROCEDURE', repeated)
        result = self.ledger.propose('demo-app', 'triage', app + cli, 'pr-review', 'MISSING_PROCEDURE', repeated)
        self.assertEqual(result['state'], {'status': 'OPEN'})

    # --- Done 3: refuse unknown states, outside repositories and paths, bad JSON and partial writes ---

    def test_boundary_inputs_are_refused_without_writing(self):
        self.refused('RESULT_UNKNOWN', self.ledger.record_end, 'demo-app', 'wu-1', 'MAYBE', '2026-11-04')
        self.refused('EXPERIENCE_TYPE_UNKNOWN', self.ledger.record_end, 'demo-app', 'wu-1', 'CANDIDATE_FOUND',
                     '2026-11-04', experiences=[dict(CORRECTION, type='OTHER')])
        self.refused('CAUSE_UNKNOWN', self.ledger.record_end, 'demo-app', 'wu-1', 'CANDIDATE_FOUND', '2026-11-04',
                     experiences=[dict(CORRECTION, cause='GUESS')])
        self.refused('REPOSITORY_NOT_IN_MANIFEST', self.ledger.record_end, 'demo-other', 'wu-1', 'NO_CANDIDATE',
                     '2026-11-04')
        self.refused('WORK_UNIT_INVALID', self.ledger.record_end, 'demo-app', '../wu', 'NO_CANDIDATE', '2026-11-04')
        self.refused('OUTSIDE_PERIOD', self.ledger.record_end, 'demo-app', 'wu-1', 'NO_CANDIDATE', '2026-11-01')
        self.refused('WORK_DATE_IN_FUTURE', self.ledger.record_end, 'demo-app', 'wu-1', 'NO_CANDIDATE', '2026-11-06')
        self.refused('WORK_DATE_INVALID', self.ledger.record_end, 'demo-app', 'wu-1', 'NO_CANDIDATE', '2026-02-30')
        for ref, code in (('path:docs/../secret', 'REF_PATH_OUTSIDE_ROOTS'), ('path:src/app.py', 'REF_PATH_OUTSIDE_ROOTS'),
                          ('path:/etc/passwd', 'REF_PATH_OUTSIDE_ROOTS'), ('https://example.com/x', 'REF_KIND_NOT_ALLOWED'),
                          ('pr-review:3', 'REF_NOT_ALLOWED_BY_MANIFEST'), ('commit:abc1234', 'REF_NOT_ALLOWED_BY_MANIFEST'),
                          ('input:token ' + 'gh' + 'p_' + 'a' * 16, 'SECRET_LIKE_INPUT')):
            self.refused(code, self.ledger.record_end, 'demo-app', 'wu-1', 'CANDIDATE_FOUND', '2026-11-04',
                         experiences=[dict(CORRECTION, refs=[ref])])
        accepted = self.ledger.record_end('demo-app', 'wu-1', 'CANDIDATE_FOUND', '2026-11-04', experiences=[
            dict(CORRECTION, refs=['path:.claude/skills/review/SKILL.md', 'synthetic:demo-app/pr-1'])])
        self.assertEqual(accepted['status'], 'RECORDED')

    def test_classification_unknown_is_held_and_public_fixture_stays_public(self):
        self.refused('CLASSIFICATION_UNKNOWN', self.ledger.record_end, 'demo-app', 'wu-1', 'NO_CANDIDATE',
                     '2026-11-04', classification='UNKNOWN')
        self.refused('CLASSIFICATION_NOT_PUBLIC', self.ledger.record_end, 'demo-app', 'wu-1', 'NO_CANDIDATE',
                     '2026-11-04', classification='INTERNAL')
        data = manifest_data(kind='APPROVED_LOCAL_DIRECTORY')
        data['repositories'][0]['classification'] = 'INTERNAL'
        local = Ledger(self.directory, Manifest(data, self.contract, NOW), self.contract, self.clock)
        self.refused('CLASSIFICATION_DOWNGRADE', local.record_end, 'demo-app', 'wu-1', 'NO_CANDIDATE', '2026-11-04',
                     classification='PUBLIC')
        self.refused('REF_KIND_NOT_ALLOWED', local.record_end, 'demo-app', 'wu-1', 'CANDIDATE_FOUND', '2026-11-04',
                     experiences=[dict(CORRECTION, refs=['synthetic:demo-app/pr-1'])])
        local.record_end('demo-app', 'wu-1', 'NO_CANDIDATE', '2026-11-04', classification='CONFIDENTIAL')
        self.assertEqual(local.read()[0]['classification'], 'CONFIDENTIAL')

    def test_manifest_and_ledger_location_are_checked(self):
        data = manifest_data()
        data['approval']['approved_at'] = '2026-11-06T00:00:00Z'
        with self.assertRaises(LedgerError) as caught:
            Manifest(data, self.contract, NOW)
        self.assertEqual(caught.exception.code, 'MANIFEST_NOT_APPROVED')
        data = manifest_data()
        data['repositories'][1]['repository_id'] = 'demo-app'
        with self.assertRaises(LedgerError) as caught:
            Manifest(data, self.contract, NOW)
        self.assertEqual(caught.exception.code, 'MANIFEST_DUPLICATE_REPOSITORY')
        data = manifest_data()
        data['repositories'][0]['allowed_roots'] = ['docs/../..']
        with self.assertRaises(LedgerError) as caught:
            Manifest(data, self.contract, NOW)
        self.assertEqual(caught.exception.code, 'MANIFEST_INVALID')
        link = self.base / 'link'
        link.mkdir()
        (link / 'skill-ledger').symlink_to(self.directory)
        cases = [(self.base / 'link' / 'skill-ledger', self.manifest, 'LEDGER_PATH_INVALID'),
                 (Path('skill-ledger'), self.manifest, 'LEDGER_PATH_INVALID'),
                 (self.base, self.manifest, 'LEDGER_LABEL_MISMATCH'),
                 (Path.home() / '.hermes' / 'skill-ledger', self.manifest, 'LEDGER_IN_HERMES_HOME'),
                 (ROOT / 'skill-ledger', Manifest(manifest_data('APPROVED_LOCAL_DIRECTORY'), self.contract, NOW),
                  'LEDGER_INSIDE_REPOSITORY')]
        for path, manifest, code in cases:
            with self.assertRaises(LedgerError, msg=str(path)) as caught:
                Ledger(path, manifest, self.contract)
            self.assertEqual(caught.exception.code, code)
        self.assertFalse((ROOT / 'skill-ledger').exists())
        missing = Ledger(self.directory, self.manifest, self.contract)
        self.directory.rmdir()
        with self.assertRaises(LedgerError) as caught:
            missing.read()
        self.assertEqual(caught.exception.code, 'LEDGER_DIRECTORY_UNAVAILABLE')

    def test_corrupt_ledgers_stop_every_command_and_stay_untouched(self):
        self.ledger.record_end('demo-app', 'wu-1', 'CANDIDATE_FOUND', '2026-11-04', experiences=[CORRECTION])
        good = self.raw()
        lines = good.splitlines(keepends=True)
        row = json.loads(lines[0])
        unknown = copy.deepcopy(row)
        unknown['record']['status'] = 'MAYBE'
        changed = copy.deepcopy(row)
        changed['event_id'] = 'e-other'
        corrupt = {
            'partial line': good + b'{"schema_version": 1',
            'not json': good + b'not json\n',
            'duplicate key': good + b'{"a": 1, "a": 2}\n',
            'unknown state': good + json.dumps(unknown).encode() + b'\n',
            'duplicate event': good + lines[0],
            'second end for unit': good + json.dumps(changed).encode() + b'\n',
            'missing experience': lines[0],
        }
        for name, data in corrupt.items():
            with self.subTest(name):
                self.file().write_bytes(data)
                self.refused('LEDGER_CORRUPT', self.ledger.read)
                self.refused('LEDGER_CORRUPT', self.ledger.record_end, 'demo-cli', 'wu-9', 'NO_CANDIDATE', '2026-11-04')
        self.file().unlink()
        (self.directory / 'ledger.jsonl').symlink_to(self.base / 'elsewhere.jsonl')
        self.refused('LEDGER_CORRUPT', self.ledger.record_end, 'demo-cli', 'wu-9', 'NO_CANDIDATE', '2026-11-04')
        self.assertFalse((self.base / 'elsewhere.jsonl').exists())

    def test_failed_or_short_write_is_reported_and_rolled_back(self):
        self.ledger.record_end('demo-app', 'wu-1', 'NO_CANDIDATE', '2026-11-04')
        before = self.raw()
        real_write = os.write

        def short(fd, data):
            return real_write(fd, data[:len(data) // 2])

        for fake, code in ((short, 'WRITE_FAILED'), (mock.Mock(side_effect=OSError(28, 'No space left')), 'WRITE_FAILED')):
            with self.subTest(code=code), mock.patch.object(ledger_module.os, 'write', fake):
                self.refused(code, self.ledger.record_end, 'demo-app', 'wu-2', 'CANDIDATE_FOUND', '2026-11-04',
                             experiences=[CORRECTION])
            self.assertEqual(self.raw(), before)
        with mock.patch.object(ledger_module.os, 'write', short), \
                mock.patch.object(ledger_module.os, 'ftruncate', mock.Mock(side_effect=OSError(5, 'I/O'))):
            with self.assertRaises(LedgerError) as caught:
                self.ledger.record_end('demo-app', 'wu-3', 'NO_CANDIDATE', '2026-11-04')
        self.assertEqual(caught.exception.code, 'WRITE_FAILED_RECOVERY_REQUIRED')
        # The next command sees the partial line and stops instead of appending after it.
        self.refused('LEDGER_CORRUPT', self.ledger.record_end, 'demo-app', 'wu-4', 'NO_CANDIDATE', '2026-11-04')

    def test_clock_never_goes_back(self):
        self.ledger.record_end('demo-app', 'wu-1', 'NO_CANDIDATE', '2026-11-04')
        self.clock.moment = NOW - timedelta(hours=1)
        self.refused('CLOCK_REGRESSION', self.ledger.record_end, 'demo-app', 'wu-2', 'NO_CANDIDATE', '2026-11-04')

    def test_contract_example_ledger_is_readable(self):
        manifest = Manifest(json.loads((FIXTURES / 'manifest.example.json').read_text(encoding='utf-8')),
                            self.contract, NOW)
        example = (FIXTURES / 'ledger.example.jsonl').read_bytes()
        directory = self.base / 'skill-improvement-example'
        directory.mkdir()
        rows = Ledger(directory, manifest, self.contract).parse(example)
        self.assertEqual(len(rows), len(example.splitlines()))
        self.assertEqual(summary(rows)['session_ends'], {'CANDIDATE_FOUND': 3, 'NO_CANDIDATE': 1, 'UNDETERMINED': 1})

    def test_review_findings_on_boundaries_are_refused(self):
        local = Manifest(manifest_data('APPROVED_LOCAL_DIRECTORY'), self.contract, NOW)
        checkout = self.base / 'other-checkout'
        (checkout / '.git').mkdir(parents=True)
        (checkout / 'nested' / 'skill-ledger').mkdir(parents=True)
        for path, manifest, code in (
                (Path.home() / '.HERMES' / 'skill-ledger', self.manifest, 'LEDGER_IN_HERMES_HOME'),
                (Path(str(ROOT).upper()) / 'skill-ledger', local, 'LEDGER_INSIDE_REPOSITORY'),
                (checkout / 'nested' / 'skill-ledger', local, 'LEDGER_INSIDE_REPOSITORY'),
                (Path('/System/Volumes/Data') / str(Path.home() / '.hermes' / 'skill-ledger').lstrip('/'),
                 self.manifest, 'LEDGER_PATH_INVALID')):
            with self.subTest(path=str(path)), self.assertRaises(LedgerError) as caught:
                Ledger(path, manifest, self.contract)
            self.assertEqual(caught.exception.code, code)
        for text in ('risk-assessment desk-research ask-questions mask-sensitive-values', 'task-planning'):
            accepted = self.ledger.record_end('demo-app', f'wu-{len(text)}', 'CANDIDATE_FOUND', '2026-11-04',
                                              experiences=[dict(CORRECTION, summary=text,
                                                                refs=[f'path:.claude/skills/{text.split()[0]}/SKILL.md'])])
            self.assertEqual(accepted['status'], 'RECORDED')
        # Fake values are assembled at run time so the repository secret scan does not flag this file.
        for text in ('s' + 'k-ant-api03-' + 'a' * 12, 's' + 'k-proj-' + 'b' * 14, 'gl' + 'pat-' + 'c' * 10,
                     'pass' + 'word=hunter2', 'API' + '_KEY: abc'):
            with self.subTest(text=text):
                self.refused('SECRET_LIKE_INPUT', self.ledger.record_end, 'demo-app', 'wu-s', 'UNDETERMINED',
                             '2026-11-04', reason=f'理由 {text}')

    def test_candidates_through_a_duplicate_still_link_instead_of_opening(self):
        ids = self.ledger.record_end('demo-app', 'wu-1', 'CANDIDATE_FOUND', '2026-11-04', experiences=[
            dict(CORRECTION, refs=['input:一']), dict(CORRECTION, refs=['input:二'])])['experience_ids']
        first = self.ledger.propose('demo-app', 'triage', [ids[0]], 'pr-review', 'MISSING_PROCEDURE')
        second = self.ledger.propose('demo-app', 'triage', ids, 'pr-review', 'MISSING_PROCEDURE')
        third = self.ledger.propose('demo-app', 'triage', [ids[1]], 'pr-review', 'MISSING_PROCEDURE')
        self.assertEqual(second['state']['duplicate_of'], first['candidate_id'])
        self.assertEqual(third['state']['status'], 'DUPLICATE')
        self.assertEqual(summary(self.ledger.read())['candidates'], {'OPEN': 1, 'DUPLICATE': 2})
        self.refused('CANDIDATE_CONFLICT', self.ledger.propose, 'demo-app', 'triage', [ids[1]], 'pr-review',
                     'DUPLICATE', duplicate_of=first['candidate_id'])

    def test_unusual_ledger_files_stop_without_hanging_or_tracebacks(self):
        self.file().write_bytes(b'[' * 200000 + b'\n')
        self.refused('LEDGER_CORRUPT', self.ledger.read)
        self.file().unlink()
        os.mkfifo(self.file())
        # The test helper cannot read a FIFO either, so check the code directly.
        with self.assertRaises(LedgerError) as caught:
            self.ledger.record_end('demo-app', 'wu-1', 'NO_CANDIDATE', '2026-11-04')
        self.assertEqual(caught.exception.code, 'LEDGER_CORRUPT')
        self.file().unlink()
        self.ledger.record_end('demo-app', 'wu-1', 'NO_CANDIDATE', '2026-11-04')
        with mock.patch.object(ledger_module, 'MAX_LEDGER_BYTES', len(self.raw()) + 10):
            self.refused('LEDGER_FULL', self.ledger.record_end, 'demo-app', 'wu-2', 'NO_CANDIDATE', '2026-11-04')
        row = json.loads(self.raw())
        row.update(event_id='e-utc', work_unit_id='wu-utc', timezone='UTC')
        self.file().write_bytes(self.raw() + json.dumps(row).encode() + b'\n')
        self.refused('LEDGER_CORRUPT', self.ledger.read)

    # --- Done 4: no model, HTTP or outside writes; CLI behaviour ---

    def test_ledger_code_imports_no_network_model_or_process_modules(self):
        forbidden = {'socket', 'http', 'urllib', 'requests', 'subprocess', 'ssl', 'asyncio', 'openai', 'anthropic'}
        for path in (ROOT / 'src' / 'skill_improvement').glob('*.py'):
            tree = ast.parse(path.read_text(encoding='utf-8'))
            names = {alias.name.split('.')[0] for node in ast.walk(tree) if isinstance(node, ast.Import)
                     for alias in node.names}
            names |= {node.module.split('.')[0] for node in ast.walk(tree)
                      if isinstance(node, ast.ImportFrom) and node.module}
            self.assertFalse(names & forbidden, path)

    def run_cli(self, *args, manifest=None):
        manifest_path = self.base / 'manifest.json'
        data = manifest or manifest_data()
        today = datetime.now(timezone.utc).date()
        data['period'] = {'start_date': (today - timedelta(days=3)).isoformat(),
                          'end_date': (today + timedelta(days=3)).isoformat()}
        manifest_path.write_text(json.dumps(data), encoding='utf-8')
        command = [sys.executable, '-I', '-B', str(CLI), '--manifest', str(manifest_path),
                   '--ledger', str(self.directory), *args]
        return subprocess.run(command, capture_output=True, text=True, timeout=60, check=False)

    def test_cli_records_verifies_and_refuses_with_exit_code(self):
        experience = json.dumps(CORRECTION, ensure_ascii=False)
        done = self.run_cli('end', '--repository', 'demo-app', '--work-unit', 'wu-1', '--result', 'CANDIDATE_FOUND',
                            '--experience', experience)
        self.assertEqual(done.returncode, 0, done.stderr)
        experience_id = json.loads(done.stdout)['experience_ids'][0]
        proposed = self.run_cli('propose', '--repository', 'demo-app', '--work-unit', 'triage', '--experience-id',
                                experience_id, '--target-skill', 'pr-review', '--cause', 'MISSING_PROCEDURE')
        self.assertEqual(json.loads(proposed.stdout)['state'], {'status': 'OPEN'})
        refused = self.run_cli('end', '--repository', 'demo-other', '--work-unit', 'wu-2', '--result', 'NO_CANDIDATE')
        self.assertEqual(refused.returncode, 2)
        self.assertEqual(refused.stdout, '')
        self.assertEqual(json.loads(refused.stderr)['error'], 'REPOSITORY_NOT_IN_MANIFEST')
        verified = self.run_cli('verify')
        self.assertEqual(json.loads(verified.stdout)['session_ends'], {'CANDIDATE_FOUND': 1})
        self.file().write_bytes(self.raw() + b'{')
        broken = self.run_cli('verify')
        self.assertEqual((broken.returncode, json.loads(broken.stderr)['error']), (2, 'LEDGER_CORRUPT'))

    def test_concurrent_appends_are_serialised_and_all_kept(self):
        manifest_path = self.base / 'manifest.json'
        data = manifest_data()
        today = datetime.now(timezone.utc).date()
        data['period'] = {'start_date': (today - timedelta(days=3)).isoformat(),
                          'end_date': (today + timedelta(days=3)).isoformat()}
        manifest_path.write_text(json.dumps(data), encoding='utf-8')
        processes = [subprocess.Popen(
            [sys.executable, '-I', '-B', str(CLI), '--manifest', str(manifest_path), '--ledger', str(self.directory),
             'end', '--repository', 'demo-app' if index % 2 else 'demo-cli', '--work-unit', f'wu-{index}',
             '--result', 'CANDIDATE_FOUND', '--experience', json.dumps(dict(CORRECTION, summary=f'同時{index}'))],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True) for index in range(8)]
        results = [process.communicate(timeout=60) + (process.returncode,) for process in processes]
        self.assertTrue(all(code == 0 for _, _, code in results), results)
        rows = Ledger(self.directory, Manifest(data, self.contract, datetime.now(timezone.utc)), self.contract).read()
        self.assertEqual(summary(rows)['session_ends'], {'CANDIDATE_FOUND': 8})
        self.assertEqual(summary(rows)['experiences'], 8)


if __name__ == '__main__':
    unittest.main()
