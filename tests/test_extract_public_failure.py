"""Check the data boundary with a saved snapshot and stubbed GitHub reads."""
import json
from pathlib import Path
import sys
import tempfile
import unittest

from test_github_work_guide import ROOT, change, save_run, seal

sys.path.insert(0, str(ROOT / 'scripts'))
from extract_public_failure import Invalid, PREFIX, extract


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
