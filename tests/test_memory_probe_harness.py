"""Harness boundary tests, independent of fetched source and protected CI assets."""
import contextlib
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('memory_probe', ROOT / 'scripts/memory_probe.py')
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)


class HarnessTests(unittest.TestCase):
    def setUp(self):
        # Keep synthetic fixtures under the approved retention boundary too.
        probe.safe_path(probe.RUNS).mkdir(exist_ok=True)
        self.root = Path(tempfile.mkdtemp(prefix='memory-harness-', dir=probe.RUNS)).resolve()
        self.runs = self.root / 'runs'
        self.source = self.runs / 'source'
        self.source.mkdir(parents=True)
        for name, value in [('ROOT', self.root), ('RUNS', self.runs), ('SOURCE', self.source)]:
            patcher = patch.object(probe, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_source_tampering_missing_and_extra_files_are_rejected(self):
        data = b'pass\n'
        path = self.source / 'fixture.py'
        info = {'bytes': len(data), 'sha256': probe.digest(data),
                'git_blob': hashlib.sha1(b'blob 5\0' + data).hexdigest()}
        lock = {'files': {'fixture.py': info}}
        with self.assertRaises(probe.ProbeError):
            probe.verify_source(lock)
        path.write_bytes(data)
        probe.verify_source(lock)
        path.write_bytes(b'FAIL\n')
        with self.assertRaises(probe.ProbeError):
            probe.verify_source(lock)
        path.write_bytes(data)
        (self.source / 'extra.py').write_bytes(data)
        with self.assertRaises(probe.ProbeError):
            probe.verify_source(lock)

    def test_path_traversal_and_symlink_are_rejected(self):
        for path in [self.runs / '../outside', self.root / 'outside']:
            with self.assertRaises(probe.ProbeError):
                probe.safe_path(path)
        (self.runs / 'link').symlink_to(self.source, target_is_directory=True)
        with self.assertRaises(probe.ProbeError):
            probe.safe_path(self.runs / 'link/fixture.py')

    def audit_fixture(self):
        work = self.runs / 'memory-fixture'
        work.mkdir()
        lock = self.root / 'lock.json'
        lock.write_text('{}')
        (work / 'manifest.json').write_bytes(probe.canonical({'run_id': work.name, 'retention_days': 30}) + b'\n')
        with patch.object(probe, 'LOCK', lock):
            prev = probe.append_event(work, work.name, 'STARTED', probe.ZERO)
            prev = probe.append_event(work, work.name, 'SOURCE_VERIFIED', prev)
            report = probe.canonical({'run_id': work.name, 'status': 'VERIFIED'})
            (work / 'report.json').write_bytes(report)
            probe.append_event(work, work.name, 'VERIFIED', prev, probe.digest(report))
        return work

    def test_audit_content_tampering_and_truncation_are_rejected(self):
        work = self.audit_fixture()
        self.assertEqual(probe.verify_events(work)['events'], 3)
        path = work / 'events.jsonl'
        before = path.read_bytes()
        path.write_bytes(before.replace(b'SOURCE_VERIFIED', b'SOURCE_MODIFIED'))
        with self.assertRaises(probe.ProbeError):
            probe.verify_events(work)
        path.write_bytes(b'\n'.join(before.splitlines()[:-1]) + b'\n')
        with self.assertRaises(probe.ProbeError):
            probe.verify_events(work)
        path.write_bytes(before)
        (work / 'report.json').write_bytes(b'{}')
        with self.assertRaises((probe.ProbeError, KeyError)):
            probe.verify_events(work)

    def test_manifest_tampering_and_missing_manifest_are_rejected(self):
        work = self.audit_fixture()
        manifest = work / 'manifest.json'
        original = manifest.read_bytes()
        self.assertEqual(probe.verify_events(work)['status'], 'VERIFIED')
        manifest.write_bytes(original.replace(b'30', b'90'))
        with self.assertRaises(probe.ProbeError):
            probe.verify_events(work)
        # Preserve the original fixture; simulate a missing name by moving it.
        manifest.write_bytes(original)
        manifest.rename(work / 'manifest.preserved.json')
        with self.assertRaises(probe.ProbeError):
            probe.verify_events(work)

    def test_worker_output_is_reconstructed_and_env_does_not_inherit_secrets(self):
        value = 'ghp_' + 'a' * 36
        process = subprocess.CompletedProcess([], 0, json.dumps({'status': 'VERIFIED', 'phase': 'seed',
                                                                'arbitrary': value}).encode(), b'')
        with patch.object(probe.subprocess, 'run', return_value=process) as call:
            result = probe.worker(self.runs, 'seed')
        self.assertNotIn(value, json.dumps(result))
        env = call.call_args.kwargs['env']
        self.assertNotIn('OPENAI_API_KEY', env)
        self.assertEqual(env['HERMES_HOME'], str(self.runs / 'home/hermes'))
        process.stderr = value.encode()
        with patch.object(probe.subprocess, 'run', return_value=process), self.assertRaises(probe.ProbeError) as raised:
            probe.worker(self.runs, 'seed')
        self.assertNotIn(value, str(raised.exception))

    def test_empty_or_skipped_worker_suite_cannot_pass(self):
        process = subprocess.CompletedProcess([], 0, b'{"status":"VERIFIED","tests_run":13,"passed_cases":[],"failures":[],"errors":[]}', b'')
        with patch.object(probe.subprocess, 'run', return_value=process), self.assertRaises(probe.ProbeError):
            probe.worker(self.runs, 'check')

    def test_failed_worker_keeps_only_known_case_names(self):
        name = probe.expected_cases()[0]
        canary = 'ghp_' + 'b' * 36
        payload = {'status': 'FAILED', 'errors': [name, canary], 'failures': [], 'message': canary}
        process = subprocess.CompletedProcess([], 1, json.dumps(payload).encode(), b'')
        with patch.object(probe.subprocess, 'run', return_value=process), self.assertRaises(probe.ProbeError) as raised:
            probe.worker(self.runs, 'check')
        self.assertEqual(raised.exception.cases, [name])
        self.assertNotIn(canary, str(raised.exception))

    def test_missing_source_keeps_blocked_report_and_audit(self):
        lock = self.root / 'lock.json'
        lock.write_text('{}')
        with patch.object(probe, 'LOCK', lock), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(probe.run({'files': {'missing.py': {}}}), 2)
        work = next(self.runs.glob('memory-*'))
        report = json.loads((work / 'report.json').read_bytes())
        self.assertEqual(report['status'], 'BLOCKED')
        self.assertEqual(probe.verify_events(work)['events'], 2)


if __name__ == '__main__':
    unittest.main()
