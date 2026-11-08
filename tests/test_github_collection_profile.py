"""Profiling keeps fixed transport, bounded collection and manifest-backed evidence."""
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from github_work_guide.core import Invalid, load_run
from test_github_work_guide import snapshot, item

spec = importlib.util.spec_from_file_location('collection_profile', ROOT / 'scripts/profile_github_collection.py')
profile = importlib.util.module_from_spec(spec)
spec.loader.exec_module(profile)


class ProfileTests(unittest.TestCase):
    def test_fixed_operation_timing_success_and_sanitized_failure(self):
        transport = profile.ProfiledReadOnly()
        with patch.object(profile.GhReadOnly, 'get', return_value={'ok': True}), \
             patch.object(profile.time, 'monotonic', side_effect=[1, 2]):
            self.assertEqual(transport.get(profile.PREFIX + '/issues', 1, 1), {'ok': True})
        def fail():
            raise Invalid('synthetic-secret')
        with self.assertRaises(Invalid):
            transport.measure('closing_batch', fail)
        self.assertEqual(transport.operations['inventory'], {'requests': 1, 'seconds': 1.0, 'failures': 0})
        self.assertEqual(transport.operations['closing_batch']['failures'], 1)
        self.assertNotIn('synthetic-secret', str(transport.operations))

    def test_output_rejection_precedes_any_collection(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(profile, 'ROOT', Path(tmp).resolve()), \
             patch.object(profile, 'Collector') as collector, contextlib.redirect_stderr(io.StringIO()):
            outside = Path(tmp) / 'outside'
            self.assertEqual(profile.main(['--out', str(outside)]), 2)
            run = Path(tmp) / 'runs/existing'
            run.mkdir(parents=True)
            self.assertEqual(profile.main(['--out', str(run)]), 2)
            collector.assert_not_called()

    def test_snapshot_and_metrics_saved_under_one_manifest_failure_exit_preserved(self):
        for status in ('COMPLETE', 'INCOMPLETE'):
            with tempfile.TemporaryDirectory() as tmp, patch.object(profile, 'ROOT', Path(tmp).resolve()), \
                 patch.object(profile, 'Collector') as collector, contextlib.redirect_stdout(io.StringIO()):
                s = snapshot(item(7))
                if status == 'INCOMPLETE':
                    from github_work_guide.core import seal
                    cov = dict(s['coverage'], status=status, errors=['fixed failure'])
                    s = seal(s['items'], cov)
                collector.return_value.collect.return_value = s
                out = Path(tmp).resolve() / 'runs/profile'
                self.assertEqual(profile.main(['--out', str(out)]), 0 if status == 'COMPLETE' else 2)
                self.assertEqual(load_run(out), s)
                manifest = json.loads((out / 'manifest.json').read_text())
                self.assertEqual(set(manifest['files']), {'snapshot.json', 'report.md'})
                self.assertEqual(json.loads((out / 'report.md').read_text())['status'], status)


if __name__ == '__main__':
    unittest.main()
