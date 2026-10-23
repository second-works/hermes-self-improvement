"""Inert service lifecycle tests; never touch a real launchd job."""
from pathlib import Path
import plistlib
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from evaluation.core import EvaluationError, digest
from delegation.context import TemporaryContext, resource_gate, resource_values, temporary_plist, MEMORY_OPTIONS


class ContextTests(unittest.TestCase):
    def fixture(self, directory):
        data = plistlib.dumps({'Label': 'local.llama-server', 'EnvironmentVariables': {'HOME': '/inert'},
                              'ProgramArguments': ['inert', '--ctx-size', '32768', '--host', '127.0.0.1',
                                                   '--port', '8081', '--alias', 'gemma-4-e4b']})
        path = Path(directory) / 'installed.plist'
        path.write_bytes(data)
        return path, data

    def test_only_context_changes_and_hash_is_required(self):
        with tempfile.TemporaryDirectory() as directory:
            _, data = self.fixture(directory)
            with patch('delegation.context.ORIGINAL_HASH', digest(data)):
                original = plistlib.loads(data)
                result = plistlib.loads(temporary_plist(data))
                result['ProgramArguments'][2] = '32768'
                self.assertEqual(result, original)
                with self.assertRaisesRegex(EvaluationError, 'ORIGINAL_SERVICE_CHANGED'):
                    temporary_plist(data + b' ')

    def test_memory_profile_preserves_nonallowlisted_settings(self):
        with tempfile.TemporaryDirectory() as directory:
            _, data = self.fixture(directory)
            original = plistlib.loads(data)
            original['ProgramArguments'][1:1] = ['--mmproj', '/inert/mmproj.gguf']
            data = plistlib.dumps(original)
            expected = plistlib.loads(data)
            args = expected['ProgramArguments']
            args[args.index('--ctx-size') + 1] = '65536'
            del args[1:3]
            args.extend(MEMORY_OPTIONS)
            with patch('delegation.context.ORIGINAL_HASH', digest(data)), patch(
                    'delegation.context.MEMORY_PLAN_HASH', digest(plistlib.dumps(expected, sort_keys=False))):
                self.assertEqual(plistlib.loads(temporary_plist(data, memory_saving=True)), expected)
                with patch('delegation.context.MEMORY_PLAN_HASH', '0' * 64):
                    with self.assertRaisesRegex(EvaluationError, 'MEMORY_PLAN_CHANGED'):
                        temporary_plist(data, memory_saving=True)

    def test_compact_profile_changes_only_three_memory_settings(self):
        with tempfile.TemporaryDirectory() as directory:
            _, data = self.fixture(directory)
            original = plistlib.loads(data)
            original['ProgramArguments'].extend(['--mmproj', '/inert/mmproj.gguf', '--cache-ram', '1024'])
            data = plistlib.dumps(original)
            memory = plistlib.loads(data)
            args = memory['ProgramArguments']
            args[args.index('--ctx-size') + 1] = '65536'
            index = args.index('--mmproj')
            del args[index:index + 2]
            args.extend(MEMORY_OPTIONS)
            compact = plistlib.loads(plistlib.dumps(memory))
            for flag, after in (('--cache-ram', '0'), ('--batch-size', '128'), ('--ubatch-size', '32')):
                compact['ProgramArguments'][args.index(flag) + 1] = after
            with patch('delegation.context.ORIGINAL_HASH', digest(data)), patch(
                    'delegation.context.MEMORY_PLAN_HASH', digest(plistlib.dumps(memory, sort_keys=False))), patch(
                    'delegation.context.COMPACT_PLAN_HASH', digest(plistlib.dumps(compact, sort_keys=False))):
                self.assertEqual(plistlib.loads(temporary_plist(data, memory_saving=True, compact_memory=True)), compact)
                with patch('delegation.context.COMPACT_PLAN_HASH', '0' * 64):
                    with self.assertRaisesRegex(EvaluationError, 'MEMORY_PLAN_CHANGED'):
                        temporary_plist(data, memory_saving=True, compact_memory=True)
                with self.assertRaisesRegex(EvaluationError, 'MEMORY_PROFILE_SCOPE'):
                    temporary_plist(data, compact_memory=True)

    def test_matrix_profile_is_hash_pinned_and_preserves_other_settings(self):
        with tempfile.TemporaryDirectory() as directory:
            _, data = self.fixture(directory)
            original = plistlib.loads(data)
            original['ProgramArguments'].extend(['--mmproj', '/inert/mmproj.gguf', '--reasoning', 'off'])
            data = plistlib.dumps(original)
            memory = plistlib.loads(data)
            args = memory['ProgramArguments']
            args[args.index('--ctx-size') + 1] = '65536'
            index = args.index('--mmproj'); del args[index:index + 2]
            args.extend(MEMORY_OPTIONS)
            matrix = plistlib.loads(plistlib.dumps(memory))
            matrix['ProgramArguments'][args.index('--reasoning') + 1] = 'on'
            matrix['ProgramArguments'].extend(['--reasoning-format', 'deepseek', '--reasoning-budget', '1024'])
            with patch('delegation.context.ORIGINAL_HASH', digest(data)), patch(
                    'delegation.context.MEMORY_PLAN_HASH', digest(plistlib.dumps(memory, sort_keys=False))), patch(
                    'delegation.context.MATRIX_PLAN_HASH', digest(plistlib.dumps(matrix, sort_keys=False))):
                actual = plistlib.loads(temporary_plist(data, memory_saving=True, matrix_profile=True))
                self.assertEqual(actual, matrix)
                del actual['ProgramArguments'][-4:]
                actual['ProgramArguments'][args.index('--reasoning') + 1] = 'off'
                self.assertEqual(actual, memory)
                with patch('delegation.context.MATRIX_PLAN_HASH', '0' * 64), self.assertRaisesRegex(
                        EvaluationError, 'MATRIX_PLAN_CHANGED'):
                    temporary_plist(data, memory_saving=True, matrix_profile=True)
                with self.assertRaisesRegex(EvaluationError, 'MATRIX_PROFILE_SCOPE'):
                    temporary_plist(data, memory_saving=True, matrix_profile=True, compact_memory=True)

    def lifecycle(self, *, fail_load=False, fail_unload=False, stop_guard=False):
        with tempfile.TemporaryDirectory() as directory:
            path, data = self.fixture(directory)
            state = {'context': 32768}
            calls = []
            def command(action, target):
                calls.append((action, target))
                if action == 'unload':
                    if fail_unload and target != path:
                        raise EvaluationError('UNLOAD_FAILED')
                    state['context'] = None
                elif target == path:
                    state['context'] = 32768
                elif fail_load:
                    raise EvaluationError('LOAD_FAILED')
                else:
                    state['context'] = 65536
            def guard():
                if stop_guard:
                    raise EvaluationError('SWAP_GROWTH')
            manager = TemporaryContext(directory, command=command, context=lambda: state['context'], guard=guard)
            with patch('delegation.context.PLIST', path), patch('delegation.context.ORIGINAL_HASH', digest(data)):
                if fail_load or stop_guard:
                    with self.assertRaises(EvaluationError):
                        manager.start(data)
                else:
                    manager.start(data)
                manager.restore()
                self.assertEqual(state['context'], 32768)
                self.assertEqual(path.read_bytes(), data)
                self.assertEqual(manager.report['restoration'], 'VERIFIED')
                self.assertEqual(calls[-1], ('load', path))
                with self.assertRaisesRegex(EvaluationError, 'RESTORATION_ALREADY_ATTEMPTED'):
                    manager.restore()

    def test_success_restores(self):
        self.lifecycle()

    def test_failed_temporary_load_still_loads_original(self):
        self.lifecycle(fail_load=True, fail_unload=True)

    def test_startup_resource_stop_restores(self):
        self.lifecycle(stop_guard=True)

    def test_resource_boundaries_fail_closed(self):
        baseline = {'swap_mib': 100, 'memory_free_percent': 50}
        resource_gate(baseline, {'swap_mib': 131.99, 'memory_free_percent': 10})
        for current in ({'swap_mib': 132, 'memory_free_percent': 50},
                        {'swap_mib': 100, 'memory_free_percent': 9}):
            with self.assertRaises(EvaluationError):
                resource_gate(baseline, current)
        self.assertEqual(resource_values('used = 1.5G', 'System-wide memory free percentage: 25%')['swap_mib'], 1536)
        with self.assertRaises(EvaluationError):
            resource_values('unknown', 'unknown')

    def test_no_mutation_needs_no_recovery(self):
        with tempfile.TemporaryDirectory() as directory:
            manager = TemporaryContext(directory, command=lambda *_: self.fail('service invoked'))
            manager.restore()
            self.assertEqual(manager.report['restoration'], 'NOT_REQUIRED')


if __name__ == '__main__':
    unittest.main()
