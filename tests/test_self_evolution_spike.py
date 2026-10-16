"""Issue #6 controller failure and isolation contracts; no upstream code runs here."""
import copy
import importlib.util
import contextlib
import io
import json
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from evaluation.core import EvaluationError, canonical
from self_evolution.sandbox import SpikeSandbox, TMPFS, stored_bytes

spec = importlib.util.spec_from_file_location('self_evolution_spike', ROOT / 'scripts/self_evolution_spike.py')
controller = importlib.util.module_from_spec(spec)
spec.loader.exec_module(controller)


def outcome(payload):
    return {'exit': 0, 'error': None, 'stderr': b'', 'stdout': canonical(payload)}


class GateContracts(unittest.TestCase):
    def test_boundary_gate_rejects_missing_extra_false_and_integer_checks(self):
        payload = {k: True for k in controller.BOUNDARIES}
        payload['python'] = '3.12.15'
        self.assertEqual(controller.validate_gate('boundaries', outcome(payload))['status'], 'VERIFIED')
        for changed in ({**payload, 'network_denied': False}, {**payload, 'memory_limit': 1},
                        {**payload, 'extra': True}, {k: v for k, v in payload.items() if k != 'seccomp'}):
            with self.assertRaises(EvaluationError):
                controller.validate_gate('boundaries', outcome(changed))

    def test_zero_exit_is_not_timeout_or_output_denial(self):
        for mode in ('timeout', 'output'):
            with self.assertRaises(EvaluationError):
                controller.validate_gate(mode, outcome({}))

    def test_startup_timeout_without_child_handshake_is_not_verified(self):
        result = outcome({})
        result['error'] = 'TIMEOUT'
        result['stdout'] = b''
        with self.assertRaises(EvaluationError):
            controller.validate_gate('timeout', result)

    def test_timeout_requires_well_formed_child_start_evidence(self):
        result = outcome({'probe': 'timeout-child-started', 'pid': 8, 'parent_pid': 1})
        result['error'] = 'TIMEOUT'
        self.assertEqual(controller.validate_gate('timeout', result)['status'], 'VERIFIED')
        for payload in ({'probe': 'timeout-child-started', 'pid': True, 'parent_pid': 1},
                        {'probe': 'timeout-child-started', 'pid': 1, 'parent_pid': 1},
                        {'probe': 'parent-started', 'pid': 8, 'parent_pid': 1}):
            with self.assertRaises(EvaluationError):
                controller.validate_gate('timeout', {**result, 'stdout': canonical(payload)})

    def test_output_limit_requires_probe_output_not_daemon_error(self):
        result = {'exit': -9, 'error': 'OUTPUT_LIMIT', 'stdout': b'x' * 1024, 'stderr': b''}
        self.assertEqual(controller.validate_gate('output', result)['status'], 'VERIFIED')
        with self.assertRaises(EvaluationError):
            controller.validate_gate('output', {**result, 'stdout': b'', 'stderr': b'error' * 1024})

    def test_initialization_and_source_hash_failures_leave_blocked_reports(self):
        for reason in ('docker', 'source'):
            with tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                with patch.object(controller, 'ROOT', root), \
                     patch.object(controller, 'SOURCES', [] if reason == 'docker' else ['missing.py']), \
                     patch.object(controller, 'SpikeSandbox', side_effect=EvaluationError('DOCKER_UNAVAILABLE')), \
                     contextlib.redirect_stdout(io.StringIO()):
                    with self.assertRaises((EvaluationError, OSError)):
                        controller.run(root / 'public-source')
                reports = list((root / 'runs').glob('*/report.json'))
                self.assertEqual(len(reports), 1)
                report = json.loads(reports[0].read_text())
                self.assertEqual(report['status'], 'BLOCKED')
                self.assertTrue(report['reason'])
                self.assertEqual(report['probes'], {})

    def test_probe_crash_or_error_cannot_pass_on_valid_payload(self):
        for field, value in [('exit', 1), ('error', 'TIMEOUT'), ('stderr', b'error')]:
            result = outcome({'memory_denied': True})
            result[field] = value
            with self.assertRaises(EvaluationError):
                controller.validate_gate('memory', result)

    def test_wrong_upstream_stops_before_materializing_source(self):
        with tempfile.TemporaryDirectory() as temporary, patch.object(controller, 'git', return_value=b'bad\n'):
            with self.assertRaisesRegex(EvaluationError, 'UPSTREAM_MISMATCH'):
                controller.snapshot(Path(temporary), Path(temporary) / 'source')
            self.assertEqual(list(Path(temporary).iterdir()), [])


class IsolationContracts(unittest.TestCase):
    def setUp(self):
        (ROOT / 'runs').mkdir(exist_ok=True)
        self.temporary = tempfile.TemporaryDirectory(dir=ROOT / 'runs')
        self.work = Path(self.temporary.name)
        for name in ('source', 'prepare', 'prepare/site'):
            (self.work / name).mkdir(exist_ok=True)
        self.box = SpikeSandbox(ROOT, self.work, 'sha256:' + 'a' * 64, deadline=time.monotonic() + 60)
        self.program = ROOT / 'fixtures/self-evolution/worker.py'

    def tearDown(self):
        self.temporary.cleanup()

    def info(self):
        args = self.box.options('fixture-container', self.program)
        return {'Image': self.box.image,
                'Mounts': [{'Source': str(p), 'Destination': t, 'RW': w}
                           for p, t, w in self.box.mounts(self.program)],
                'Config': {'User': '65532:65532', 'WorkingDir': '/run/work', 'Entrypoint': None,
                           'Cmd': args[args.index(self.box.image) + 1:]},
                'HostConfig': {'NetworkMode': 'none', 'IpcMode': 'none', 'ReadonlyRootfs': True,
                    'CapDrop': ['ALL'], 'CapAdd': None, 'SecurityOpt': ['no-new-privileges=true'],
                    'Privileged': False, 'NanoCpus': 1000000000, 'Memory': 1073741824,
                    'MemorySwap': 1073741824, 'PidsLimit': 64, 'LogConfig': {'Type': 'none'},
                    'PidMode': '', 'Devices': [], 'Binds': None, 'Tmpfs': {'/run/work': TMPFS}}}

    def test_candidate_network_writable_mount_and_resource_drift_are_rejected(self):
        original = self.info()
        self.box.verify_config(original, self.program)
        for field, value in [('NetworkMode', 'bridge'), ('MemorySwap', 2147483648),
                             ('PidsLimit', 0), ('Privileged', True), ('CapAdd', ['NET_ADMIN'])]:
            changed = copy.deepcopy(original)
            changed['HostConfig'][field] = value
            with self.assertRaises(EvaluationError):
                self.box.verify_config(changed, self.program)
        changed = copy.deepcopy(original)
        changed['Mounts'][1]['RW'] = True
        with self.assertRaises(EvaluationError):
            self.box.verify_config(changed, self.program)

    def test_network_only_in_download_and_prepare_mount_never_reaches_probe(self):
        for phase in ('download', 'install', 'gate', 'probe'):
            self.box.phase = phase
            args = self.box.options('fixture-container', self.program)
            self.assertIn('--network=' + ('bridge' if phase == 'download' else 'none'), args)
            writable = [(str(p), t) for p, t, w in self.box.mounts(self.program) if w]
            self.assertEqual(writable, [(str(self.work / 'prepare'), '/prepare')]
                             if phase in ('download', 'install') else [])

    def test_image_command_drift_and_injected_socket_mount_are_rejected(self):
        for kind in ('image', 'command', 'socket'):
            changed = self.info()
            if kind == 'image':
                changed['Image'] = 'sha256:' + 'b' * 64
            elif kind == 'command':
                changed['Config']['Cmd'] += ['--eval-source=sessiondb']
            else:
                changed['Mounts'].append({'Source': '/var/run/docker.sock',
                                         'Destination': '/var/run/docker.sock', 'RW': True})
            with self.assertRaises(EvaluationError):
                self.box.verify_config(changed, self.program)

    def test_mount_symlink_and_storage_symlink_are_rejected(self):
        (self.work / 'source').rmdir()
        (self.work / 'source').symlink_to(ROOT)
        with self.assertRaises(EvaluationError):
            self.box.options('fixture-container', self.program)
        with self.assertRaises(EvaluationError):
            stored_bytes(self.work)

    def test_expired_budget_does_not_create_container(self):
        self.box.deadline = time.monotonic() - 1
        with self.assertRaisesRegex(EvaluationError, 'SANDBOX_STOPPED'):
            self.box.options('fixture-container', self.program)

    def test_storage_limit_never_blocks_safety_reconciliation(self):
        with patch('self_evolution.sandbox.stored_bytes', return_value=3 * 1024**3), \
             patch('evaluation.sandbox.Sandbox.command', return_value={'exit': 0}) as command:
            for operation in ('inspect', 'kill', 'rm'):
                self.box.command(operation, 'owned-container', timeout=5)
            self.assertEqual(command.call_count, 3)
            with self.assertRaisesRegex(EvaluationError, 'PERSISTENT_DISK_LIMIT'):
                self.box.command('create', 'owned-container')
            self.assertEqual(command.call_count, 3)


if __name__ == '__main__':
    unittest.main()
