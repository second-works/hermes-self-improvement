"""PUBLIC profile boundaries and durable handoff; candidates never execute on host."""
from copy import deepcopy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
sys.path.insert(0, str(ROOT / 'scripts'))
from evaluation.core import EvaluationError, canonical, digest
from evaluation.profiles import (COUNTS, PROFILES, apply, artifacts, count_cases, hashes,
                                 launcher, observe, profile, response)
from delegation.generated import git
import evaluate_skill_candidate as controller
import run_public_hermes as runner
from intake_public_failure import failure_event_id


def entry(sha='a' * 40):
    return {'schema_version': 1, 'status': 'AWAITING_HUMAN_REVIEW', 'classification': 'PUBLIC',
            'source_kind': 'public-github-check', 'repo': 'second-works/hermes-self-improvement',
            'event_id': failure_event_id(25, sha, 100), 'pr_number': 25, 'head_sha': sha,
            'pr_url': 'https://github.com/second-works/hermes-self-improvement/pull/25',
            'check_id': 100, 'conclusion': 'failure', 'snapshot_hash': 'b' * 64,
            'reproduction_sha256': 'c' * 64}


class ProfileContractsTest(unittest.TestCase):
    def setUp(self):
        self.selected = profile('event-status-counts-v1')
        self.files = {p: (ROOT / p).read_text() for p in self.selected.artifacts}
        self.edit = {'path': COUNTS + 'scripts/helpers.py',
                     'before': '        if identity in seen:\n            continue\n', 'after': ''}
        self.proposal = {'schema_version': 1, 'decision': 'PROPOSE', 'reason': 'Preserve duplicate counts.',
                         'evidence_refs': ['/reproduction_sha256'], 'edits': [self.edit]}

    def test_only_registered_profiles_and_public_event_binding(self):
        self.assertEqual(len(PROFILES), 2)
        self.assertNotEqual(self.selected.hash, profile('review-multiline-shell-v1').hash)
        with self.assertRaisesRegex(EvaluationError, 'NEEDS_PROFILE'):
            profile('../anything')
        controller.check_entry(entry())
        for changes in ({'event_id': 'd' * 64}, {'source_kind': 'synthetic-fixture'},
                        {'check_id': True}, {'repo': 'other/repo'}, {'private': True}):
            with self.subTest(changes=changes), self.assertRaises(EvaluationError):
                controller.check_entry({**entry(), **changes})

    def test_multifile_edits_and_invalid_boundaries(self):
        second = {'path': COUNTS + 'scripts/aggregate.py', 'before': 'json.load(sys.stdin)',
                  'after': 'json.load(sys.stdin, object_pairs_hook=pairs)'}
        proposal = {**self.proposal, 'edits': [self.edit, second]}
        checked = response(proposal, self.selected)
        after = apply(self.files, checked['edits'])
        self.assertNotEqual(hashes(after), hashes(self.files))
        self.assertEqual(after[COUNTS + 'SKILL.md'], self.files[COUNTS + 'SKILL.md'])
        for invalid in ([self.edit, self.edit], [{**self.edit, 'path': '../outside.py'}],
                        [{**self.edit, 'after': '\x00'}], [{**self.edit, 'before': ''}],
                        [{**self.edit, 'after': 'x' * 16385}]):
            with self.subTest(invalid=invalid), self.assertRaises(EvaluationError):
                response({**self.proposal, 'edits': invalid}, self.selected)
        for replacement in ('missing before', 'import json'):
            before = {p: s for p, s in self.files.items()}
            if replacement == 'import json':
                before[self.edit['path']] = 'import json\nimport json\n'
            with self.assertRaisesRegex(EvaluationError, 'PROFILE_EDIT_BINDING'):
                apply(before, [{**self.edit, 'before': replacement}])

    def test_payload_size_evidence_and_decision_scope(self):
        for changes in ({'schema_version': True}, {'decision': 'REUSE'}, {'extra': 'command'},
                        {'evidence_refs': ['/hidden/0']}, {'evidence_refs': ['/reproduction_sha256'] * 2}):
            with self.subTest(changes=changes), self.assertRaises(EvaluationError):
                response({**self.proposal, **changes}, self.selected)
        with self.assertRaisesRegex(EvaluationError, 'PROFILE_PROMPT_LIMIT'):
            runner.request_prompt(entry(), {'artifacts': {'p': 'x' * 8192}})

    def test_launcher_packages_only_public_files_without_host_execution(self):
        with patch('runpy.run_path', side_effect=AssertionError('host execution')):
            code = launcher(self.files, self.selected)
        compile(code, '<trusted-bundle>', 'exec')
        self.assertNotIn(b'hidden.json', code)
        self.assertNotIn(b'profile-manifest', code)
        self.assertIn(b"/run/work/skill", code)
        with self.assertRaisesRegex(EvaluationError, 'PROFILE_FILES'):
            launcher({**self.files, '../escape': 'pass'}, self.selected)

    def test_outcomes_distinguish_expected_exit_and_isolation_failure(self):
        case = count_cases()[2]
        result = {'exit': 0, 'container_exit': 0, 'error': None, 'stderr': b'', 'oom': False,
                  'stdout': canonical(case['expected']), 'wall_seconds': 0.1}
        self.assertTrue(observe(self.selected, result, case)['correct'])
        wrong = deepcopy(case['expected'])
        wrong['counts']['build']['ok'] = True
        result['stdout'] = canonical(wrong)
        self.assertFalse(observe(self.selected, result, case)['correct'])
        case = count_cases()[-1]
        result.update(exit=2, container_exit=2, stdout=canonical(case['expected']))
        self.assertTrue(observe(self.selected, result, case)['correct'])
        result['error'] = 'TIMEOUT'
        self.assertTrue(observe(self.selected, result, case)['safety_failure'])

    def test_git_freezes_commit_blobs_and_rejects_symlink(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            git(root, 'init', '--template=', '--initial-branch=fixture')
            for p, value in self.files.items():
                path = root / p; path.parent.mkdir(parents=True, exist_ok=True); path.write_text(value)
            git(root, 'add', '--', 'fixtures')
            git(root, '-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid', 'commit', '-m', 'baseline')
            sha = git(root, 'rev-parse', 'HEAD').decode().strip()
            self.assertEqual(artifacts(root, sha, self.selected), self.files)
            path = root / self.selected.entrypoint
            path.unlink(); path.symlink_to('/nonexistent')
            git(root, 'add', '--', self.selected.entrypoint)
            git(root, '-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid', 'commit', '-m', 'bad source')
            bad = git(root, 'rev-parse', 'HEAD').decode().strip()
            with self.assertRaisesRegex(EvaluationError, 'SOURCE_TYPE'):
                artifacts(root, bad, self.selected)


class ProfileHandoffTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.work = self.root / 'runs/evaluation-20261107T000000Z-aaaaaaaaaaaa'
        self.work.mkdir(parents=True)
        for obj, name, value in ((controller, 'ROOT', self.root), (controller, 'STATE', self.root / 'runs/profile-evaluation'),
                                 (controller.gate, 'RUNS', self.root / 'runs'), (runner, 'ROOT', self.root)):
            p = patch.object(obj, name, value); p.start(); self.addCleanup(p.stop)
        self.entry = entry()
        self.selected = profile('event-status-counts-v1')
        self.m = {'entry': self.entry, 'profile_id': self.selected.id,
                  'mapping': {'artifact_hashes': {'file.py': 'd' * 64}}}
        (self.work / 'profile-manifest.json').write_text('{}')
        controller.gate.save(self.work, 'environment.json', {'synthetic': True})
        controller.gate.event(self.work, 'ENVIRONMENT_PINNED', digest((self.work / 'environment.json').read_bytes()))
        self.value = {'schema_version': 1, 'event_id': self.entry['event_id'],
                      'packet_hash': digest(canonical(self.entry)), 'classification': 'PUBLIC',
                      'source_kind': 'public-github-check', 'baseline_sha': self.entry['head_sha'],
                      'context_run': self.work.name, 'context_manifest_hash': digest(b'{}'),
                      'approval_hash': 'e' * 64, 'decision': 'HOLD', 'reason': 'Evidence insufficient.',
                      'evidence_refs': ['/reproduction_sha256']}
        self.receipt(self.value)

    def receipt(self, value):
        directory = self.root / 'runs/public-hermes' / self.entry['event_id']; directory.mkdir(parents=True, exist_ok=True)
        (directory / 'finished.json').write_bytes(canonical({'event_id': self.entry['event_id'],
            'packet_hash': digest(canonical(self.entry)), 'status': 'COMPLETED',
            'decision': value['decision'], 'result_hash': digest(canonical(value))}))

    def test_hold_is_receipted_audited_and_never_adopted_or_replayed(self):
        with patch.object(controller, 'manifest', return_value=self.m):
            result = controller.evaluate(self.work.name, canonical(self.value))
            self.assertEqual(result['state'], 'HOLD')
            self.assertEqual(controller.audit(self.work.name)['status'], 'VERIFIED')
            memory = json.loads((self.work / 'profile-memory.json').read_text())
            self.assertEqual(memory['approval']['status'], 'NOT_REQUESTED')
            self.assertIsNone(memory['candidate'])
            with self.assertRaisesRegex(EvaluationError, 'PROFILE_RUN_USED'):
                controller.evaluate(self.work.name, canonical(self.value))
            (self.work / 'profile-report.json').write_text('{}')
            with self.assertRaises(EvaluationError):
                controller.audit(self.work.name)

    def test_proposal_substitution_is_rejected_and_recorded(self):
        changed = {**self.value, 'reason': 'Substituted response'}
        with patch.object(controller, 'manifest', return_value=self.m):
            result = controller.evaluate(self.work.name, canonical(changed))
        self.assertEqual(result['state'], 'REJECTED')
        self.assertEqual(result['reason'], 'PROFILE_PROPOSAL_RECEIPT')

    def test_recovery_pending_blocks_cloud_before_authentication(self):
        pending = controller.STATE / 'pending.json'; pending.parent.mkdir(parents=True); pending.write_text('{}')
        with patch.object(runner, 'read_auth') as auth:
            with self.assertRaisesRegex(EvaluationError, 'PROFILE_RECOVERY_REQUIRED'):
                runner.execute(self.entry, 'PUBLIC', self.root / 'unused-approval', self.root / 'state')
            auth.assert_not_called()

    def test_unknown_cleanup_blocks_further_evaluation(self):
        value = {**self.value, 'decision': 'PROPOSE', 'edits': [{'path': self.selected.entrypoint, 'before': 'a', 'after': 'b'}]}
        self.receipt(value)
        error = EvaluationError('ISOLATION_CLEANUP_FAILED'); error.pending_container = 'hermes-eval-' + 'a' * 32
        with patch.object(controller, 'manifest', return_value=self.m), patch.object(controller, 'evaluate_edits', side_effect=error):
            with self.assertRaisesRegex(EvaluationError, 'ISOLATION_CLEANUP_FAILED'):
                controller.evaluate(self.work.name, canonical(value))
            self.assertTrue((controller.STATE / 'pending.json').exists())
            with self.assertRaisesRegex(EvaluationError, 'PROFILE_RECOVERY_REQUIRED'):
                controller.evaluate(self.work.name, canonical(value))

    def test_cloud_profile_response_is_bound_to_context_and_actual_receipt(self):
        event = {**self.entry, 'check_id': 101}
        event['event_id'] = failure_event_id(25, event['head_sha'], 101)
        context = {'profile_id': self.selected.id, 'manifest_hash': digest(b'{}')}
        prompt = runner.request_prompt(event, context)
        approval = self.root / 'approval.json'
        import time
        approval.write_bytes(canonical({**runner.plan(event, prompt), 'expires_at': int(time.time())+300}))
        approval.chmod(0o600)
        proposal = {'schema_version':1, 'decision':'PROPOSE', 'reason':'PUBLIC test',
                    'evidence_refs':['/reproduction_sha256'],
                    'edits':[{'path':self.selected.entrypoint, 'before':'old', 'after':'new'}]}
        reply = canonical({'status':'COMPLETED','requests':1,'tools':0,'text':json.dumps(proposal)})
        with patch.object(controller, 'context', return_value=context), \
             patch.object(runner, 'read_auth', return_value={'synthetic': True}), \
             patch('delegation.hermes_cloud.response', return_value=reply) as send:
            raw = runner.execute(event, prompt, approval, self.root/'runs/public-hermes', context_run=self.work.name)
        self.assertEqual(send.call_count, 1)
        parsed = controller.verify_proposal(self.work, {**self.m, 'entry':event}, raw)
        self.assertEqual(parsed['decision'], 'PROPOSE')

    def test_context_substitution_is_refused_before_auth(self):
        event = {**self.entry, 'check_id': 102}
        event['event_id'] = failure_event_id(25, event['head_sha'], 102)
        context = {'profile_id': self.selected.id, 'manifest_hash': digest(b'{}')}
        prompt = runner.request_prompt(event, context)
        approval = self.root / 'approval.json'
        import time
        approval.write_bytes(canonical({**runner.plan(event, prompt), 'expires_at': int(time.time())+300}))
        approval.chmod(0o600)
        with patch.object(controller, 'context', side_effect=[context, {**context,'manifest_hash':'d'*64}]), \
             patch.object(runner, 'read_auth') as auth:
            with self.assertRaisesRegex(EvaluationError, 'PROFILE_CONTEXT_CHANGED'):
                runner.execute(event, prompt, approval, self.root/'runs/public-hermes', context_run=self.work.name)
            auth.assert_not_called()


if __name__ == '__main__':
    unittest.main()
