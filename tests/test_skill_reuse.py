"""Controller regressions use inert traces; real fresh-session proof is separate."""
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from delegation.skill_reuse import Controller, SKILL, PROGRAM, SCRIPT_HASH, request, observe
from delegation.generated import git
from evaluation.core import EvaluationError, canonical, digest, write_new


class BoundaryTests(unittest.TestCase):
    def test_requests_reject_commands_external_fetch_and_extra_fields(self):
        for value in [{'operation': 'sh'}, {'operation': 'curl https://example.invalid'},
                      {'operation': 'run_review', 'command': 'anything'}, [], None]:
            with self.subTest(value=value), self.assertRaises(EvaluationError):
                request(value)
        self.assertEqual(request({'operation': 'run_review'}), 'run_review')

    def test_output_rejects_faults_and_non_schema_actual_stdout(self):
        good = {'exit': 0, 'container_exit': 0, 'error': None, 'oom': False,
                'stderr': b'', 'stdout': b'{"findings":[],"cpu_seconds":0}'}
        self.assertEqual(observe(good), [])
        for change in [{'exit': 1}, {'container_exit': 1}, {'error': 'TIMEOUT'},
                       {'oom': True}, {'stderr': b'error'}, {'stdout': b'Looks good'},
                       {'stdout': b'[]'}]:
            with self.subTest(change=change), self.assertRaises(EvaluationError):
                observe(dict(good, **change))


class IntakeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve(); self.work = self.root / ('runs/skill-' + 'a'*24)
        self.packet = self.work / 'packet'; (self.packet / 'github-code-review/scripts').mkdir(parents=True)
        for name in (SKILL, PROGRAM, 'catalog.json', 'public.json'):
            write_new(self.packet / name, (ROOT / 'fixtures/generated_skills' / name).read_bytes())
        git(self.packet, 'init', '--template=', '--initial-branch=test')
        git(self.packet, 'add', '.')
        self.commit()
        self.base = git(self.packet, 'rev-parse', 'HEAD').decode().strip()
        self.c = Controller(self.root)
        self.manifest = {'baseline_sha': self.base,
                         'packet_git_hash': digest((self.packet / '.git/config').read_bytes())}
        self.frozen = patch.object(self.c, 'frozen', return_value=self.manifest)
        self.frozen.start(); self.addCleanup(self.frozen.stop)

    def commit(self):
        git(self.packet, 'add', '.')
        git(self.packet, '-c', 'user.name=Test', '-c', 'user.email=test@example.invalid',
            'commit', '-m', 'inert test bytes')

    def candidate(self):
        with (self.packet / SKILL).open('ab') as stream: stream.write(b'\nInert test addition.\n')
        self.commit()
        return git(self.packet, 'rev-parse', 'HEAD').decode().strip()

    def test_one_skill_only_and_unchanged_script(self):
        sha = self.candidate()
        _, value = self.c.intake(self.work, sha)
        self.assertTrue(value.endswith(b'Inert test addition.\n'))
        self.assertEqual(digest((self.packet / PROGRAM).read_bytes()), SCRIPT_HASH)
        with self.assertRaises(EvaluationError): self.c.intake(self.work, self.base)
        (self.packet / PROGRAM).write_bytes(b'inert forbidden edit')
        self.commit()
        with self.assertRaises(EvaluationError):
            self.c.intake(self.work, git(self.packet, 'rev-parse', 'HEAD').decode().strip())

    def test_dirty_symlink_oversize_and_old_sha_rejected(self):
        sha = self.candidate()
        (self.packet / 'extra').write_bytes(b'x')
        with self.assertRaises(EvaluationError): self.c.intake(self.work, sha)
        (self.packet / 'extra').unlink()
        (self.packet / SKILL).unlink(); (self.packet / SKILL).symlink_to('/nonexistent')
        self.commit()
        with self.assertRaises(EvaluationError):
            self.c.intake(self.work, git(self.packet, 'rev-parse', 'HEAD').decode().strip())
        (self.packet / SKILL).unlink(); (self.packet / SKILL).write_bytes(b'x'*16385)
        self.commit()
        with self.assertRaises(EvaluationError):
            self.c.intake(self.work, git(self.packet, 'rev-parse', 'HEAD').decode().strip())

    def test_denied_missing_and_arbitrary_requests_never_reach_sandbox(self):
        sha = self.candidate()
        self.c.save(self.work, 'accepted.json', {'candidate_sha': sha, 'candidate_hash': 'unused'})
        self.c.save(self.work, 'budget.json', {'seconds': 1, 'started_at': time.time()})
        tasks = [{scenario: {'task': {'path': 'case_public00.py'} if scenario == 'missing' else
                                        {'path': 'case_public00.py', 'patch': '+safe(x)'}}
                  for scenario in ('denied', 'missing', 'baseline', 'primary')}]*3
        self.c.save(self.work, 'trials.private.json', tasks)
        with patch.object(self.c, 'accepted', return_value={'candidate_hash': 'unused'}), \
                patch('delegation.skill_reuse.Sandbox') as sandbox:
            for scenario, value in [('denied', {'operation':'run_review'}),
                                    ('missing', {'operation':'run_review'}),
                                    ('baseline', {'operation':'run_review'}),
                                    ('primary', {'operation':'curl'})]:
                self.c.save(self.work, '0-' + scenario + '.read.json', {})
                with self.assertRaises(EvaluationError):
                    self.c.use(self.work.name, 0, scenario, value)
                self.assertTrue((self.work / 'active.lock').exists())
                (self.work / 'active.lock').unlink()  # disposable mock fixture only
                (self.work / 'stopped.json').unlink()
            sandbox.assert_not_called()

    def test_mock_batch_audits_actual_stdout_and_rejects_trace_tampering(self):
        from delegation.skill_reuse import SCENARIOS
        candidate_sha = self.candidate()
        candidate = (self.packet / SKILL).read_bytes()
        write_new(self.work / 'candidate.md', candidate)
        accepted = {'candidate_sha': candidate_sha, 'candidate_hash': digest(candidate),
                    'baseline_sha': self.base, 'manifest_hash': 'frozen', 'script_hash': SCRIPT_HASH}
        self.c.save(self.work, 'accepted.json', accepted)
        self.c.save(self.work, 'budget.json', {'seconds': 1, 'started_at': time.time()})
        source = self.root / 'fixtures/generated_skills' / PROGRAM
        source.parent.mkdir(parents=True); source.write_bytes((self.packet / PROGRAM).read_bytes())
        cases = []
        for i in range(3):
            row = {}
            for scenario in SCENARIOS:
                task = {'path': 'case_public00.py', 'patch': '@@ -7,1 +7,1 @@\n+safe(x)'}
                operation = {'denied': 'stop_permission', 'missing': 'stop_evidence',
                             'baseline': 'stop_no_procedure'}.get(scenario, 'run_review')
                if scenario == 'missing': task.pop('patch')
                row[scenario] = {'task': task, 'expected_operation': operation, 'expected': []}
            cases.append(row)
        self.c.save(self.work, 'trials.private.json', cases)
        self.c.save(self.work, 'sessions.json', ['00000000-0000-0000-0000-' + str(i).zfill(12) for i in range(3)])
        events = [{'state': state, 'hash': str(i)} for i, state in enumerate(
            ['ENVIRONMENT_PINNED', 'ISOLATION_VERIFIED', 'EVALUATION_FROZEN', 'EVALUATING'])]
        class Gate:
            def event(_, work, state, payload_hash):
                events.append({'state': state, 'hash': 'last', 'payload_hash': payload_hash})
            def verify_events(_, work): return events
        outcome = {'exit': 0, 'container_exit': 0, 'error': None, 'oom': False,
                   'stderr': b'', 'stdout': b'{"findings":[],"cpu_seconds":0}', 'wall_seconds': .1}
        with patch.object(self.c, 'accepted', return_value=accepted), \
                patch.object(self.c, 'legacy', return_value=Gate()), \
                patch('delegation.skill_reuse.Sandbox') as sandbox:
            sandbox.return_value.run.side_effect = lambda *a, **kw: dict(outcome)
            for i, row in enumerate(cases):
                for scenario in SCENARIOS:
                    self.c.handoff(self.work.name, i, scenario)
                    self.c.use(self.work.name, i, scenario, {'operation': row[scenario]['expected_operation']})
            report = self.c.evaluate(self.work.name)
            self.assertEqual(report['status'], 'PASS')
            self.assertEqual(sandbox.return_value.run.call_count, 6)
            self.assertEqual(self.c.audit(self.work.name)['audit'], 'VERIFIED')
            trace = self.work / '0-primary.trace.json'
            trace.write_bytes(b'{}')
            with self.assertRaisesRegex(EvaluationError, 'AUDIT_TRACE'):
                self.c.audit(self.work.name)

    def test_evaluation_requires_all_three_real_session_receipts(self):
        with patch.object(self.c, 'accepted', return_value={}):
            self.c.save(self.work, 'budget.json', {'seconds': 1, 'started_at': time.time()})
            self.c.save(self.work, 'trials.private.json', [{}, {}, {}])
            self.c.save(self.work, 'sessions.json', [])
            with self.assertRaisesRegex(EvaluationError, 'FRESH_SESSIONS_MISSING'):
                self.c.evaluate(self.work.name)



class LegacyBindingTests(unittest.TestCase):
    def test_real_freeze_accept_and_audit_bindings_without_docker(self):
        """Real legacy verifier and event bindings; only container observations are mocked."""
        import shutil
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            original = Controller(ROOT)
            for name in original.sources():
                target = root / name
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(ROOT / name, target)
            (root / '.gitignore').write_text('runs/\n')
            git(root, 'init', '--template=', '--initial-branch=test')
            git(root, 'add', '.')
            git(root, '-c', 'user.name=Test', '-c', 'user.email=test@example.invalid', 'commit', '-m', 'test source')
            c = Controller(root)
            c.runs.mkdir()
            work = c.runs / ('skill-' + 'b'*24); work.mkdir()
            c.save(c.runs, 'skill-reuse.lock', {'run_id': work.name})
            c.save(work, 'environment.json', {'synthetic': True})
            gate = c.legacy()
            c.save(work, 'gate.json', {'status': 'VERIFIED', 'sources': gate.source_hashes(),
                'environment_hash': digest((work / 'environment.json').read_bytes()),
                'probes': {name: 'VERIFIED' for name in (*gate.PROBE_FIELDS, 'timeout', 'output')}})
            c.save(work, 'budget.json', {'seconds': 1, 'started_at': time.time()})
            gate.event(work, 'ENVIRONMENT_PINNED', digest((work / 'environment.json').read_bytes()))
            gate.event(work, 'ISOLATION_VERIFIED', digest((work / 'gate.json').read_bytes()))
            c.freeze(work.name)
            packet = work / 'packet'
            with (packet / SKILL).open('ab') as stream: stream.write(b'\nInert mock candidate.\n')
            git(packet, 'add', SKILL)
            git(packet, '-c', 'user.name=Test', '-c', 'user.email=test@example.invalid', 'commit', '-m', 'mock candidate')
            candidate = git(packet, 'rev-parse', 'HEAD').decode().strip()
            c.accept(work.name, candidate)
            self.assertEqual(len(c.legacy().verify_events(work)), 4)
            cases = c.read_json(work, 'trials.private.json')
            c.save(work, 'sessions.json', ['00000000-0000-0000-0000-' + str(i).zfill(12) for i in range(3)])
            answers = {digest(canonical(case['task'])): case['expected']
                       for row in cases for case in row.values()}
            def observed(program, data, **kwargs):
                rows = answers[digest(data)]
                return {'exit': 0, 'container_exit': 0, 'error': None, 'oom': False,
                        'stdout': canonical({'findings': [dict(zip(['path','line','rule'], row)) for row in rows],
                                             'cpu_seconds': 0}), 'stderr': b'', 'wall_seconds': .1}
            with patch('delegation.skill_reuse.Sandbox') as sandbox:
                sandbox.return_value.run.side_effect = observed
                for i, row in enumerate(cases):
                    for scenario, case in row.items():
                        c.handoff(work.name, i, scenario)
                        c.use(work.name, i, scenario, {'operation': case['expected_operation']})
            self.assertEqual(c.evaluate(work.name)['status'], 'PASS')
            self.assertEqual(c.audit(work.name)['audit'], 'VERIFIED')
            (work / 'candidate.md').chmod(0o600)  # disposable tamper fixture
            (work / 'candidate.md').write_bytes(b'changed')
            with self.assertRaises(EvaluationError): c.audit(work.name)


if __name__ == '__main__': unittest.main()
