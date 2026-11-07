"""Check the data boundary with a saved snapshot and stubbed GitHub reads."""
from copy import deepcopy
import json
from pathlib import Path
import sys
import tempfile
import unittest

from test_github_work_guide import ROOT, change, save_run, seal

sys.path.insert(0, str(ROOT / 'scripts'))
from extract_public_failure import Invalid, PREFIX, extract
from intake_public_failure import failure_event_id, intake
from select_public_failure import select
from github_work_guide.core import digest
from bind_public_reproduction import BINDING, bind
from run_mock_improvement import EvaluationError, packet_refs


class PublicFailureTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.run = Path(tmp.name).resolve() / 'runs' / 'snapshot'
        fixture = json.loads((ROOT / 'fixtures/github_work_guide/synthetic.json').read_text())

        def failed(pr):
            pr['raw']['checks'][0]['conclusion'] = 'failure'
            pr['raw']['detail']['body'] = pr['body'] = 'SYNTHETIC_SECRET_MARKER'

        snapshot = change(fixture, 'pr:25', failed)
        self.snapshot = snapshot
        save_run(self.run, {'snapshot.json': snapshot})
        raw = snapshot['items']['pr:25']['raw']
        self.head = raw['detail']['head']['sha']
        self.check = dict(raw['checks'][0])
        self.routes = {
            (PREFIX, None): {'full_name': snapshot['repo'], 'private': False, 'visibility': 'public'},
            (PREFIX + '/pulls/25', None): raw['detail'],
            (f'{PREFIX}/commits/{self.head}/check-runs', 1): {
                'total_count': 1, 'check_runs': [self.check]},
        }

    def get(self, path, page, timeout):
        return self.routes[path, page]

    def test_projects_only_allowed_fields(self):
        result = extract(self.run, 25, self)
        self.assertEqual(result, {
            'pr_number': 25, 'pr_url': f'https://github.com/{self.snapshot["repo"]}/pull/25',
            'head_sha': self.head, 'check_id': self.check['id'], 'conclusion': 'failure',
            'snapshot_hash': self.snapshot['hash'],
        })

    def test_intake_provenance_stability_and_synthetic_boundary(self):
        first = intake(self.run, 25, self)
        self.assertEqual(set(first), {
            'schema_version', 'status', 'classification', 'source_kind', 'repo', 'event_id',
            'pr_url', 'pr_number', 'head_sha', 'check_id', 'conclusion', 'snapshot_hash',
        })
        self.assertEqual(first['source_kind'], 'public-github-check')
        self.assertEqual(first['status'], 'AWAITING_REPRODUCTION')
        self.assertNotIn('SYNTHETIC_SECRET_MARKER', json.dumps(first))
        def update_body(pr):
            pr['body'] = pr['raw']['detail']['body'] = 'A later collection of the same failure'

        updated = change(self.snapshot, 'pr:25', update_body)
        next_run = self.run.with_name('next-snapshot')
        save_run(next_run, {'snapshot.json': updated})
        second = intake(next_run, 25, self)
        self.assertNotEqual(first['snapshot_hash'], second['snapshot_hash'])
        self.assertEqual(first['event_id'], second['event_id'])
        with self.assertRaises(EvaluationError):
            packet_refs(first)

    def test_intake_propagates_refusal_or_skips_recovery(self):
        self.check['conclusion'] = 'success'
        self.assertEqual(intake(self.run, 25, self)['status'], 'SKIP')
        self.routes[PREFIX, None]['private'] = True
        with self.assertRaises(Invalid):
            intake(self.run, 25, self)

    def test_bind_requires_current_failure_and_matching_supervisor_record(self):
        entry = intake(self.run, 25, self)
        evidence = {'schema_version': 1, 'reproduction_sha256': 'a' * 64,
                    'observed': 'FAIL', 'expected': 'PASS',
                    **{field: entry[field] for field in BINDING}}
        path = self.run.parent / 'reproduction.json'
        self.assertEqual(bind(self.run, 25, None, self)['reason'], 'REPRODUCTION_EVIDENCE_REQUIRED')
        path.write_text(json.dumps(evidence))
        bound = bind(self.run, 25, path, self)
        self.assertEqual(bound, {**entry, 'status': 'AWAITING_HUMAN_REVIEW',
                                 'reproduction_sha256': 'a' * 64})
        with self.assertRaises(EvaluationError):
            packet_refs(bound)
        for invalid in ({'event_id': '0' * 64}, {'head_sha': '0' * 40}, {'check_id': True},
                        {'observed': 'PASS'}, {'log': 'SYNTHETIC_SECRET_MARKER'}):
            with self.subTest(invalid=invalid):
                path.write_text(json.dumps({**evidence, **invalid}))
                with self.assertRaises(Invalid):
                    bind(self.run, 25, path, self)
        path.write_text(json.dumps(evidence) + ' ' * 2048)
        with self.assertRaises(EvaluationError):
            bind(self.run, 25, path, self)
        path.write_text(json.dumps(evidence))
        self.check['conclusion'] = 'success'
        self.assertEqual(bind(self.run, 25, path, self)['status'], 'SKIP')
        self.routes[PREFIX, None]['private'] = True
        with self.assertRaises(Invalid):
            bind(self.run, 25, path, self)

    def test_select_at_most_one_and_skip_seen_or_stale(self):
        items = deepcopy(self.snapshot['items'])
        earlier = deepcopy(items['pr:25'])
        earlier.update(number=24, url=earlier['url'].replace('/25', '/24'))
        detail = earlier['raw']['detail']
        detail.update(number=24, html_url=earlier['url'])
        earlier['hash'] = digest(earlier['raw'])
        items['pr:24'] = earlier
        snapshot = seal(items, self.snapshot['coverage'])
        run = self.run.with_name('two-failures')
        save_run(run, {'snapshot.json': snapshot})
        directory = self.run.parent / 'evidence'
        directory.mkdir()
        self.routes[PREFIX + '/pulls/24', None] = detail

        events = {}
        for number in (24, 25):
            entry = intake(run, number, self)
            events[number] = entry['event_id']
            evidence = {'schema_version': 1, 'reproduction_sha256': 'a' * 64,
                        'observed': 'FAIL', 'expected': 'PASS',
                        **{field: entry[field] for field in BINDING}}
            (directory / (events[number] + '.json')).write_text(json.dumps(evidence))

        self.assertEqual(select(run, directory, [], self)['candidate']['pr_number'], 24)
        result = select(run, directory, [events[24]], self)
        self.assertEqual(result['candidate']['pr_number'], 25)
        self.assertEqual(result['skipped'], {'ALREADY_CLAIMED': 1})
        self.routes[PREFIX + '/pulls/24', None] = {**detail, 'head': {'sha': '0' * 40}}
        result = select(run, directory, [], self)
        self.assertEqual(result['candidate']['pr_number'], 25)
        self.assertEqual(result['skipped'], {'NO_CURRENT_CI_FAILURE': 1})
        self.assertEqual(select(run, directory, list(events.values()), self)['status'], 'SKIP')

    def test_select_missing_reproduction_and_untrusted_evidence(self):
        directory = self.run.parent / 'evidence'
        directory.mkdir()
        result = select(self.run, directory, [], self)
        self.assertEqual(result['skipped'], {'REPRODUCTION_EVIDENCE_REQUIRED': 1})
        event = failure_event_id(25, self.head, self.check['id'])
        (directory / (event + '.json')).write_text('{}')
        with self.assertRaises(Invalid):
            select(self.run, directory, [], self)
        self.routes[PREFIX, None]['private'] = True
        with self.assertRaises(Invalid):
            select(self.run, directory, [], self)
        with self.assertRaises(Invalid):
            select(self.run, directory, ['bad'], self)

    def test_rejects_private_unknown_and_wrong_repository(self):
        metadata = self.routes[PREFIX, None]
        for override in ({'private': True}, {'visibility': None}, {'full_name': 'other/repo'}):
            with self.subTest(override=override):
                self.routes[PREFIX, None] = {**metadata, **override}
                with self.assertRaises(Invalid):
                    extract(self.run, 25, self)

    def test_skips_changed_head_and_recovered_ci(self):
        detail = self.routes[PREFIX + '/pulls/25', None]
        self.routes[PREFIX + '/pulls/25', None] = {**detail, 'head': {'sha': '0' * 40}}
        self.assertIsNone(extract(self.run, 25, self))
        self.routes[PREFIX + '/pulls/25', None] = detail
        self.check['conclusion'] = 'success'
        self.assertIsNone(extract(self.run, 25, self))

    def test_rejects_modified_and_incomplete_runs(self):
        (self.run / 'snapshot.json').write_text('{}')
        with self.assertRaises(Invalid):
            extract(self.run, 25, self)
        incomplete = seal({}, {**self.snapshot['coverage'], 'status': 'INCOMPLETE'})
        self.run = self.run.with_name('incomplete')
        save_run(self.run, {'snapshot.json': incomplete})
        with self.assertRaises(Invalid):
            extract(self.run, 25, self)
