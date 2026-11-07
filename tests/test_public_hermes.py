"""Verify cloud admission and transport guards without real credentials or network."""
import importlib.util
import base64
import json
from pathlib import Path
import sys
import tempfile
import time
import types
import unittest
from unittest.mock import Mock, patch

import test_extract_public_failure as fixtures

sys.path.insert(0, str(fixtures.ROOT / 'scripts'))
import run_public_hermes as runner
from run_mock_improvement import canonical, control_intake, EvaluationError


class PublicHermesTest(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.PublicFailureTest()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.root = self.fixture.run.parent
        self.entry = fixtures.intake(self.fixture.run, 25, self.fixture)
        self.entry.update(status='AWAITING_HUMAN_REVIEW', reproduction_sha256='a' * 64)
        self.prompt = runner.request_prompt(self.entry)
        self.approval = self.root / 'approval.json'
        self.write_approval()
        self.state = self.root / 'runs/cloud'
        response = {'schema_version': 1, 'decision': 'HOLD',
                    'reason': 'More public evidence is required.', 'evidence_refs': ['/reproduction_sha256']}
        self.reply = canonical({'status': 'COMPLETED', 'requests': 1, 'tools': 0,
                                'text': json.dumps(response)})

    def write_approval(self, **changes):
        document = {**runner.plan(self.entry, self.prompt), 'expires_at': int(time.time()) + 300,
                    **changes}
        self.approval.write_text(json.dumps(document))
        self.approval.chmod(0o600)

    def execute(self):
        return runner.execute(self.entry, self.prompt, self.approval, self.state)

    def test_trial_auth_rejects_invalid_permissions_expiry_and_shape(self):
        directory = self.root / 'trial-parent' / 'trial-auth'
        directory.mkdir(parents=True, mode=0o700)
        directory.parent.chmod(0o700)
        path = directory / 'auth.json'
        def save(expiry):
            claims = base64.urlsafe_b64encode(json.dumps({'exp': expiry}).encode()).decode().rstrip('=')
            auth = {'providers': {'openai-codex': {'tokens': {
                'access_token': 'synthetic.' + claims + '.synthetic', 'refresh_token': 'synthetic'}}}}
            path.write_text(json.dumps(auth))
            path.chmod(0o600)
            return auth
        with patch.object(runner, 'AUTH_DIRECTORY', directory):
            expected = save(time.time() + 3600)
            self.assertEqual(runner.read_auth(), expected)
            path.chmod(0o644)
            with self.assertRaisesRegex(EvaluationError, 'PRIVATE_FILE_PERMISSIONS'):
                runner.read_auth()
            save(time.time() - 1)
            with self.assertRaisesRegex(EvaluationError, 'AUTH_EXPIRED'):
                runner.read_auth()
            path.write_text('{}')
            with self.assertRaisesRegex(EvaluationError, 'AUTH_SCOPE'):
                runner.read_auth()
            path.write_text('{broken')
            with self.assertRaises(EvaluationError):
                runner.read_auth()
            path.unlink()
            with self.assertRaisesRegex(EvaluationError, 'AUTH_INVALID_OR_UNAVAILABLE'):
                runner.read_auth()

    def test_one_approved_request_and_durable_duplicate(self):
        with patch.object(runner, 'read_auth', return_value={'synthetic': True}), \
                patch('delegation.hermes_cloud.response', return_value=self.reply) as cloud:
            result = json.loads(self.execute())
            self.assertEqual(result['decision'], 'HOLD')
            request = json.loads(cloud.call_args.args[1])
            self.assertFalse(request['offline_test'])
            self.assertEqual(request['prompt'], self.prompt)
            pending = self.state / 'isolation-pending.json'
            self.assertFalse(pending.exists())
            with self.assertRaisesRegex(EvaluationError, 'EVENT_ALREADY_CLAIMED'):
                self.execute()
            self.assertEqual(cloud.call_count, 1)
            self.entry['event_id'] = 'b' * 64
            self.prompt = runner.request_prompt(self.entry)
            self.write_approval()
            with self.assertRaisesRegex(EvaluationError, 'SNAPSHOT_ALREADY_CLAIMED'):
                self.execute()

    def test_wrong_or_expired_approval_never_reads_auth(self):
        for change in ({'additional_cost_yen': 1}, {'max_requests': 2}, {'max_retries': True},
                       {'prompt_hash': 'b' * 64}, {'expires_at': int(time.time()) - 1}):
            with self.subTest(change=change), patch.object(runner, 'read_auth') as auth:
                self.write_approval(**change)
                with self.assertRaises(EvaluationError):
                    self.execute()
                auth.assert_not_called()
                self.assertFalse(self.state.exists())
        self.write_approval()
        self.approval.chmod(0o644)
        with self.assertRaisesRegex(EvaluationError, 'PRIVATE_FILE_PERMISSIONS'):
            self.execute()

    def test_auth_rejection_stops_without_retry(self):
        with patch.object(runner, 'read_auth', return_value={}), \
                patch('delegation.hermes_cloud.response', return_value=canonical({'status': 'AUTH_FAILED'})) as cloud:
            with self.assertRaisesRegex(EvaluationError, 'AUTH_FAILED'):
                self.execute()
            receipt = json.loads((self.state / self.entry['event_id'] / 'finished.json').read_text())
            self.assertEqual(receipt['reason'], 'AUTH_FAILED')
            with self.assertRaisesRegex(EvaluationError, 'EVENT_ALREADY_CLAIMED'):
                self.execute()
            self.assertEqual(cloud.call_count, 1)

    def test_unconfirmed_cloud_cleanup_blocks_resume(self):
        error = EvaluationError('ISOLATION_CLEANUP_FAILED')
        error.pending_container = 'hermes-eval-' + 'a' * 32
        with patch.object(runner, 'read_auth', return_value={}), \
                patch('delegation.hermes_cloud.response', side_effect=error):
            with self.assertRaisesRegex(EvaluationError, 'ISOLATION_CLEANUP_FAILED'):
                self.execute()
        pending = json.loads((self.state / 'isolation-pending.json').read_text())
        self.assertEqual(pending['worker_kind'], 'hermes-cloud-v1')
        for action in ('stop', 'resume'):
            with self.assertRaisesRegex(EvaluationError, 'ISOLATION_PENDING'):
                control_intake(self.state, action)

    def test_changed_approval_before_auth_is_rejected(self):
        original = runner.approval
        calls = 0

        def check(path, expected):
            nonlocal calls
            calls += 1
            if calls == 2:
                self.write_approval(expires_at=int(time.time()) + 600)
            return original(path, expected)

        with patch.object(runner, 'approval', side_effect=check), patch.object(runner, 'read_auth') as auth:
            with self.assertRaisesRegex(EvaluationError, 'APPROVAL_CHANGED'):
                self.execute()
            auth.assert_not_called()

    def test_global_stop_prevents_credentials_and_execution(self):
        control_intake(self.state, 'stop')
        with patch.object(runner, 'read_auth') as auth:
            with self.assertRaisesRegex(EvaluationError, 'INTAKE_STOPPED'):
                self.execute()
            auth.assert_not_called()


class CloudTransportTest(unittest.TestCase):
    def test_endpoint_payload_and_retry_guard(self):
        spec = importlib.util.spec_from_file_location('cloud_worker', fixtures.ROOT / 'fixtures/cloud-improvement/worker.py')
        worker = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(worker)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'query.txt').write_text('PUBLIC fixed prompt')
            original = Mock(return_value=types.SimpleNamespace(status_code=200))
            transport = type('HTTPTransport', (), {'handle_request': original})
            httpx = types.SimpleNamespace(HTTPTransport=transport)
            env = {'HERMES_HOME': str(root), 'HERMES_APPROVAL_UNTIL': str(time.time() + 60)}
            with patch.dict(sys.modules, {'httpx': httpx}), patch.dict('os.environ', env), patch('sys.addaudithook'):
                namespace = {}
                exec(worker.HOOK, namespace)
                send = namespace['intercept']
                audit = namespace['audit']
                with self.assertRaisesRegex(RuntimeError, 'SOCKET_BLOCKED'):
                    audit('socket.connect', (None, ('203.0.113.1', 443)))
                with self.assertRaisesRegex(RuntimeError, 'DNS_BLOCKED'):
                    audit('socket.getaddrinfo', ('chatgpt.com',))
                audit('socket.connect', (None, ('127.0.0.1', 1234)))
                namespace['permit'].active = True
                with self.assertRaisesRegex(RuntimeError, 'DNS_BLOCKED'):
                    audit('socket.getaddrinfo', ('example.invalid',))
                namespace['permit'].active = False
                payload = {'model': 'gpt-6-luna', 'store': False, 'tools': [],
                           'input': [{'role': 'user', 'content': 'PUBLIC fixed prompt'}]}
                request = types.SimpleNamespace(method='POST', url=runner.ENDPOINT, headers={},
                                                read=lambda: json.dumps(payload).encode())
                for bad in ('https://auth.openai.com/oauth/token', 'https://example.invalid/'):
                    request.url = bad
                    with self.assertRaisesRegex(RuntimeError, 'OUTBOUND_BLOCKED'):
                        send(None, request)
                request.url = runner.ENDPOINT
                payload['tools'] = [{'type': 'function'}]
                with self.assertRaisesRegex(RuntimeError, 'PAYLOAD_BLOCKED'):
                    send(None, request)
                original.assert_not_called()
                payload['tools'] = []
                self.assertEqual(send(None, request).status_code, 200)
                with self.assertRaisesRegex(RuntimeError, 'RETRY_BLOCKED'):
                    send(None, request)
                self.assertEqual(original.call_count, 1)


if __name__ == '__main__':
    unittest.main()
