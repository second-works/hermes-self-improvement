"""Mock-only provider and controller contracts. No API key lookup or network."""
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from delegation.catalog import catalog
from delegation.openai_provider import Config, Provider, connect_fixed, post
from delegation.openai_run import run_openai
from delegation.patch import OPERATION_IDS, apply_operations
from evaluation.core import EvaluationError, canonical

SETTINGS = {'model': 'explicit-test-model', 'input_usd_per_million': '2.5',
            'output_usd_per_million': '10', 'max_cost_usd': '1', 'max_calls': 2,
            'model_context_tokens': 16000, 'max_input_tokens': 16000, 'max_output_tokens': 256,
            'max_total_input_tokens': 32000, 'max_total_output_tokens': 512,
            'deadline_seconds': 60, 'timeout_seconds': 30, 'max_response_bytes': 8192}
STATE = {'available_operations': list(OPERATION_IDS)}
SOURCE = (ROOT / 'fixtures/delegation/registered-operations/review.py').read_bytes()


def response(selection=None):
    return {'model': 'explicit-test-model', 'object': 'chat.completion',
        'choices': [{'index': 0, 'finish_reason': 'stop', 'message': {
        'role': 'assistant', 'content': json.dumps(selection if selection is not None else
                                                 {'operations': list(OPERATION_IDS)})}}],
        'usage': {'prompt_tokens': 100, 'completion_tokens': 20, 'total_tokens': 120}}


class ProviderTests(unittest.TestCase):
    def setUp(self):
        # This synthetic key exists only in the test double, never inspect the real env.
        self.env = patch('delegation.openai_provider.os.environ', {'OPENAI_API_KEY': 'synthetic-key'})
        self.env.start()
        self.addCleanup(self.env.stop)
        network = patch('socket.create_connection', side_effect=AssertionError('network forbidden'))
        network.start()
        self.addCleanup(network.stop)

    def provider(self, value=None, settings=None, **kwargs):
        transport = Mock(return_value=canonical(response() if value is None else value))
        return Provider(Config.parse(settings or SETTINGS), allow_api=True,
                        transport=transport, **kwargs)

    def test_config_requires_every_field_rejects_unknown_and_secret_fields(self):
        for field in SETTINGS:
            value = dict(SETTINGS)
            del value[field]
            with self.subTest(field=field), self.assertRaisesRegex(EvaluationError, 'API_CONFIG'):
                Config.parse(value)
        for field in ('base_url', 'proxy', 'api_key', 'method'):
            with self.subTest(field=field), self.assertRaisesRegex(EvaluationError, 'API_CONFIG'):
                Config.parse(dict(SETTINGS, **{field: 'untrusted'}))

    def test_invalid_prices_models_limits_and_cross_limits(self):
        for field in ('input_usd_per_million', 'output_usd_per_million', 'max_cost_usd'):
            for invalid in ('NaN', 'Infinity', '-1', '0', '1e2', 1, True, None, '0.0000000000001'):
                with self.subTest(field=field, invalid=invalid), self.assertRaises(EvaluationError):
                    Config.parse(dict(SETTINGS, **{field: invalid}))
        for field in ('max_calls', 'model_context_tokens', 'max_input_tokens', 'max_output_tokens', 'deadline_seconds',
                      'timeout_seconds', 'max_response_bytes', 'max_total_input_tokens',
                      'max_total_output_tokens'):
            for invalid in (True, 0, -1, '30', 1000000000):
                with self.subTest(field=field, invalid=invalid), self.assertRaises(EvaluationError):
                    Config.parse(dict(SETTINGS, **{field: invalid}))
        for changes in ({'model': 'abc\nsecret'}, {'model': ''}, {'timeout_seconds': 61},
                        {'max_total_input_tokens': 1}, {'max_total_output_tokens': 1}):
            with self.subTest(changes=changes), self.assertRaises(EvaluationError):
                Config.parse(dict(SETTINGS, **changes))

    def test_no_opt_in_does_not_read_key_or_call_transport(self):
        provider = self.provider()
        provider.allow_api = False
        with patch('delegation.openai_provider.os.environ') as env:
            with self.assertRaisesRegex(EvaluationError, 'API_OPT_IN_REQUIRED'):
                provider.select(STATE)
            env.get.assert_not_called()
        provider.transport.assert_not_called()

    def test_success_request_schema_state_and_usage_cost(self):
        provider = self.provider()
        self.assertEqual(provider.select(STATE), {'operations': list(OPERATION_IDS)})
        body, key, timeout, limit = provider.transport.call_args.args
        request = json.loads(body)
        self.assertEqual(request['model'], SETTINGS['model'])
        self.assertEqual(key, 'synthetic-key')
        self.assertEqual((timeout, limit), (30, 8192))
        self.assertEqual(request['max_completion_tokens'], 256)
        self.assertFalse(request['store'])
        self.assertFalse(request['stream'])
        self.assertEqual(request['service_tier'], 'default')
        schema = request['response_format']['json_schema']
        self.assertTrue(schema['strict'])
        self.assertFalse(schema['schema']['additionalProperties'])
        self.assertNotIn('uniqueItems', schema['schema']['properties']['operations'])
        self.assertTrue(catalog()['selection_schema']['properties']['operations']['uniqueItems'])
        self.assertNotIn('tools', request)
        self.assertNotIn('source', json.loads(request['messages'][1]['content']))
        meta = provider.metadata()
        self.assertEqual((meta['calls'], meta['input_tokens'], meta['output_tokens']), (1, 100, 20))
        self.assertEqual(meta['cost_usd'], '0.00045')
        self.assertEqual(meta['unsettled_reserved_usd'], '0')
        self.assertEqual(meta['status'], 'SELECTED_NOT_EXECUTED')

    def test_noop_and_unavailable_operation(self):
        provider = self.provider(response({'operations': []}))
        self.assertEqual(provider.select({'available_operations': []}), {'operations': []})
        provider = self.provider()
        with self.assertRaisesRegex(EvaluationError, 'OPERATION_NOT_AVAILABLE'):
            provider.select({'available_operations': []})

    def test_public_state_does_not_accept_arbitrary_text_or_fields(self):
        for value in ({'source': 'private'}, {'available_operations': ['shell']},
                      {'available_operations': [], 'prompt': 'private'}, {'available_operations': 'text'}):
            provider = self.provider()
            with self.subTest(value=value), self.assertRaises(EvaluationError):
                provider.select(value)
            provider.transport.assert_not_called()

    def test_budget_equality_input_deadline_and_key_fail_before_transport(self):
        # Entire input/output ceilings are reserved; equality must refuse.
        price = '0.04256'
        for changes, code in (({'max_cost_usd': price}, 'API_BUDGET'),
                              ({'model_context_tokens': 1000}, 'API_INPUT_LIMIT')):
            provider = self.provider(settings=dict(SETTINGS, **changes))
            with self.assertRaisesRegex(EvaluationError, code):
                provider.select(STATE)
            provider.transport.assert_not_called()
        provider = self.provider(clock=Mock(side_effect=[0, 60]))
        with self.assertRaisesRegex(EvaluationError, 'API_DEADLINE'):
            provider.select(STATE)
        provider.transport.assert_not_called()
        for key in (None, '', 'a\r\nAuthorization: bad'):
            with patch('delegation.openai_provider.os.environ', {'OPENAI_API_KEY': key}):
                provider = self.provider()
                with self.assertRaisesRegex(EvaluationError, 'API_KEY_REQUIRED'):
                    provider.select(STATE)
                provider.transport.assert_not_called()

    def test_calls_and_total_token_reservations_stop_subsequent_calls(self):
        for changes in ({'max_calls': 1}, {'max_total_input_tokens': 16000},
                        {'max_total_output_tokens': 256}):
            provider = self.provider(settings=dict(SETTINGS, **changes))
            provider.select(STATE)
            with self.subTest(changes=changes), self.assertRaisesRegex(EvaluationError, 'API_BUDGET'):
                provider.select(STATE)
            self.assertEqual(provider.transport.call_count, 1)

    def test_usage_missing_malformed_mismatched_or_over_limit_halts_and_keeps_reservation(self):
        for usage in (None, {}, {'prompt_tokens': True, 'completion_tokens': 20, 'total_tokens': 21},
                      {'prompt_tokens': 100, 'completion_tokens': 20, 'total_tokens': 119},
                      {'prompt_tokens': 16001, 'completion_tokens': 20, 'total_tokens': 16021},
                      {'prompt_tokens': 100, 'completion_tokens': 257, 'total_tokens': 357}):
            value = response()
            value['usage'] = usage
            provider = self.provider(value)
            with self.subTest(usage=usage), self.assertRaisesRegex(EvaluationError, 'API_USAGE'):
                provider.select(STATE)
            self.assertEqual(provider.metadata()['unsettled_reserved_usd'], '0.04256')
            with self.assertRaisesRegex(EvaluationError, 'API_RUN_HALTED'):
                provider.select(STATE)
            self.assertEqual(provider.transport.call_count, 1)

    def test_bad_selections_refusals_truncation_tools_and_choices_never_succeed(self):
        values = [response({'operations': ['shell']}), response({'operations': [OPERATION_IDS[0]] * 2}),
                  response({'operations': [], 'code': 'print(1)'})]
        for key, value in (('finish_reason', 'length'), ('finish_reason', 'tool_calls'),
                           ('index', 1)):
            data = response()
            data['choices'][0][key] = value
            values.append(data)
        for key, value in (('refusal', 'no'), ('tool_calls', [{}]), ('function_call', {}),
                           ('content', '```json\n{}\n```'), ('content', '{"operations":[],"operations":[]}'),
                           ('content', None), ('role', 'user')):
            data = response()
            data['choices'][0]['message'][key] = value
            if key == 'function_call':
                data['choices'][0]['message'][key] = {'name': 'shell'}
            values.append(data)
        for choice in ([], [{}], [response()['choices'][0]] * 2):
            data = response()
            data['choices'] = choice
            values.append(data)
        for data in values:
            provider = self.provider(data)
            with self.subTest(data=data), self.assertRaises(EvaluationError):
                provider.select(STATE)
            self.assertEqual(provider.status, 'FAILED')

    def test_transport_errors_redact_secrets_preserve_unknown_cost_and_never_retry(self):
        provider = self.provider()
        provider.transport.side_effect = RuntimeError('synthetic-key PRIVATE PROMPT RESPONSE')
        with self.assertRaisesRegex(EvaluationError, '^API_FAILED$'):
            provider.select(STATE)
        self.assertEqual(provider.calls, 1)
        self.assertEqual(provider.metadata()['unsettled_reserved_usd'], '0.04256')
        self.assertNotIn('synthetic-key', json.dumps(provider.metadata()))
        with self.assertRaisesRegex(EvaluationError, 'API_RUN_HALTED'):
            provider.select(STATE)
        self.assertEqual(provider.transport.call_count, 1)

    def test_size_invalid_json_and_late_response_are_failures(self):
        for raw in (b'x' * 8193, b'{', b'{"usage":null,"usage":null}', b'NaN'):
            provider = self.provider()
            provider.transport.return_value = raw
            with self.subTest(raw=raw[:20]), self.assertRaises(EvaluationError):
                provider.select(STATE)
        provider = self.provider(clock=Mock(side_effect=[0, 1, 60]))
        with self.assertRaisesRegex(EvaluationError, 'API_DEADLINE'):
            provider.select(STATE)

    def test_response_model_object_and_boolean_choice_index_are_rejected(self):
        for field, value in (('model', 'different-model'), ('object', 'chat.completion.chunk')):
            data = response()
            data[field] = value
            with self.subTest(field=field), self.assertRaisesRegex(EvaluationError, 'API_RESPONSE'):
                self.provider(data).select(STATE)
        data = response()
        data['choices'][0]['index'] = False
        with self.assertRaisesRegex(EvaluationError, 'API_SELECTION'):
            self.provider(data).select(STATE)

    def test_transport_timeout_bad_content_type_and_no_length_size_cap(self):
        with patch('delegation.openai_provider.DeadlineHTTPSConnection') as https:
            connection = https.return_value
            reply = connection.getresponse.return_value
            reply.status = 200
            reply.getheader.side_effect = lambda name, default=None: (
                'text/html' if name == 'Content-Type' else None)
            with self.assertRaisesRegex(EvaluationError, 'API_CONTENT_TYPE'):
                post(b'{}', 'synthetic-key', 1, 64)
            reply.getheader.side_effect = lambda name, default=None: (
                'application/json' if name == 'Content-Type' else None)
            reply.read.return_value = b'x' * 65
            with self.assertRaisesRegex(EvaluationError, 'API_RESPONSE_SIZE'):
                post(b'{}', 'synthetic-key', 1, 64)
            reply.read.side_effect = TimeoutError('private timeout message')
            provider = self.provider()
            provider.transport = post
            with self.assertRaisesRegex(EvaluationError, '^API_FAILED$'):
                provider.select(STATE)
            self.assertEqual(provider.calls, 1)

    def test_dns_and_connect_are_bounded_without_alternate_destination_or_retry(self):
        address = ('api.openai.com', 443)
        answer = (2, 1, 6, '', ('192.0.2.1', 443))
        with patch('delegation.openai_provider.socket.getaddrinfo', return_value=[answer]) as dns, \
                patch('delegation.openai_provider.socket.socket') as sockets:
            self.assertIs(connect_fixed(address, 1), sockets.return_value)
            dns.assert_called_once_with('api.openai.com', 443, type=1)
            sockets.return_value.connect.assert_called_once_with(('192.0.2.1', 443))
            sockets.return_value.connect.side_effect = OSError('private connect failure')
            with self.assertRaises(OSError):
                connect_fixed(address, 1)
            sockets.return_value.close.assert_called_once()
        with patch('delegation.openai_provider.socket.getaddrinfo', side_effect=OSError('private')):
            with self.assertRaisesRegex(EvaluationError, '^API_FAILED$'):
                connect_fixed(address, 1)
        with patch('delegation.openai_provider.queue.Queue') as queue, \
                patch('delegation.openai_provider.threading.Thread'):
            import queue as standard_queue
            queue.return_value.get.side_effect = standard_queue.Empty()
            with self.assertRaisesRegex(EvaluationError, '^API_TIMEOUT$'):
                connect_fixed(address, 0.01)
        with self.assertRaisesRegex(EvaluationError, '^API_FAILED$'):
            connect_fixed(('localhost', 8081), 1)

    def test_tls_handshake_is_published_and_receives_only_remaining_deadline(self):
        # No network or timing sleeps: simulate TCP consuming 75% of the budget.
        from delegation.openai_provider import DeadlineHTTPSConnection
        context = Mock()
        raw = Mock()
        connection = DeadlineHTTPSConnection('api.openai.com', 443, timeout=0.2, context=context)
        def wrap(sock, **kwargs):
            self.assertIs(sock, raw)
            self.assertFalse(kwargs['do_handshake_on_connect'])
            return context.wrap_socket.return_value
        context.wrap_socket.side_effect = wrap
        def handshake():
            self.assertIs(connection.sock, context.wrap_socket.return_value)
            self.assertAlmostEqual(connection.sock.settimeout.call_args.args[0], 0.05)
        context.wrap_socket.return_value.do_handshake.side_effect = handshake
        with patch('delegation.openai_provider.connect_fixed', return_value=raw), \
                patch('delegation.openai_provider.time.monotonic', side_effect=[0, 0.15]):
            connection.connect()
        context.wrap_socket.return_value.do_handshake.assert_called_once()

    def test_response_socket_ownership_does_not_disable_deadline_cancellation(self):
        with patch('delegation.openai_provider.DeadlineHTTPSConnection') as https, \
                patch('delegation.openai_provider.threading.Timer') as timer:
            connection = https.return_value
            sock = connection.sock
            reply = Mock()
            reply.status = 200
            reply.getheader.side_effect = lambda name, default=None: (
                'application/json' if name == 'Content-Type' else '2')
            def getresponse():
                # http.client does this when the response owns a closing socket.
                connection.sock = None
                return reply
            connection.getresponse.side_effect = getresponse
            def read(limit):
                timer.call_args.args[1]()
                return b'{}'
            reply.read.side_effect = read
            post(b'{}', 'synthetic-key', 1, 64)
            sock.shutdown.assert_called_once()
            reply.close.assert_called_once()

    def test_disabled_example_cannot_read_key_or_call_api(self):
        example = json.loads((ROOT / 'fixtures/delegation/registered-operations/openai-config.example.json').read_text())
        with patch('delegation.openai_provider.os.environ') as env:
            with self.assertRaises(EvaluationError):
                Config.parse(example)
            env.get.assert_not_called()

    def test_transport_has_fixed_tls_destination_method_no_proxy_redirect_or_retry(self):
        with patch('delegation.openai_provider.DeadlineHTTPSConnection') as https:
            connection = https.return_value
            reply = connection.getresponse.return_value
            reply.status = 200
            reply.getheader.side_effect = lambda name, default=None: (
                'application/json' if name == 'Content-Type' else '2')
            reply.read.return_value = b'{}'
            self.assertEqual(post(b'{}', 'synthetic-key', 1, 64), b'{}')
            self.assertEqual(https.call_args.args, ('api.openai.com', 443))
            context = https.call_args.kwargs['context']
            self.assertTrue(context.check_hostname)
            self.assertEqual(connection.request.call_args.args[:2], ('POST', '/v1/chat/completions'))
            reply.read.assert_called_once_with(65)
            for status in (301, 302, 401, 429, 500):
                reply.status = status
                reply.read.reset_mock()
                with self.subTest(status=status), self.assertRaisesRegex(EvaluationError, 'API_HTTP_ERROR'):
                    post(b'{}', 'synthetic-key', 1, 64)
                reply.read.assert_not_called()
            reply.status = 200
            reply.getheader.side_effect = lambda name, default=None: (
                'application/json' if name == 'Content-Type' else '65')
            with self.assertRaisesRegex(EvaluationError, 'API_RESPONSE_SIZE'):
                post(b'{}', 'synthetic-key', 1, 64)


class ControllerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        (self.root / 'runs').mkdir()
        self.source = self.root / 'fixtures/delegation/registered-operations/review.py'
        self.source.parent.mkdir(parents=True)
        self.source.write_bytes(SOURCE)
        self.config = self.root / 'config.json'
        self.config.write_bytes(canonical(SETTINGS))
        self.output = self.root / 'runs/test'
        self.transport = Mock(return_value=canonical(response()))
        self.factory = lambda config, **kw: Provider(config, transport=self.transport, **kw)
        self.env = patch('delegation.openai_provider.os.environ', {'OPENAI_API_KEY': 'synthetic-key'})
        self.env.start()
        self.addCleanup(self.env.stop)

    def run_controller(self, **kw):
        return run_openai(self.root, self.source, self.config, self.output,
                          provider_factory=self.factory, **kw)

    def test_mock_selection_prepares_candidate_preserves_original_and_redacts_reports(self):
        with patch('evaluation.sandbox.Sandbox', side_effect=AssertionError('Docker forbidden')):
            report = self.run_controller(allow_api=True)
        self.assertEqual(report['status'], 'PREPARED_NOT_EXECUTED')
        self.assertEqual(self.source.read_bytes(), SOURCE)
        expected = apply_operations(SOURCE.decode(), {'operations': list(OPERATION_IDS)})
        self.assertEqual((self.output / 'candidate/candidate.py').read_text(), expected)
        for path in self.output.rglob('*.json'):
            data = path.read_text()
            for secret in ('synthetic-key', 'messages', 'choices', 'Bearer'):
                self.assertNotIn(secret, data)
        with self.assertRaises(FileExistsError):
            self.run_controller(allow_api=True)
        self.assertEqual(self.transport.call_count, 1)

    def test_opt_in_config_and_source_boundaries_stop_before_network(self):
        with self.assertRaisesRegex(EvaluationError, 'API_OPT_IN_REQUIRED'):
            self.run_controller()
        self.source.write_bytes(SOURCE + b'# arbitrary\n')
        with self.assertRaises(EvaluationError):
            self.run_controller(allow_api=True)
        self.transport.assert_not_called()
        self.assertFalse(self.output.exists())

    def test_output_aliases_outside_and_existing_outputs_stop_before_network(self):
        for output in (self.root / 'outside', self.root / 'runs'):
            with self.subTest(output=output), self.assertRaises((EvaluationError, FileExistsError)):
                run_openai(self.root, self.source, self.config, output, allow_api=True,
                           provider_factory=self.factory)
        alias = self.root / 'runs/alias'
        alias.symlink_to(self.root / 'runs', target_is_directory=True)
        with self.assertRaisesRegex(EvaluationError, 'RUN_PARENT'):
            run_openai(self.root, self.source, self.config, alias / 'child', allow_api=True,
                       provider_factory=self.factory)
        self.transport.assert_not_called()

    def test_failure_records_metadata_without_candidate_or_raw_response(self):
        self.transport.side_effect = RuntimeError('synthetic-key private response')
        with self.assertRaisesRegex(EvaluationError, 'API_FAILED'):
            self.run_controller(allow_api=True)
        report = json.loads((self.output / 'provider-report.json').read_text())
        self.assertEqual(report['status'], 'FAILED')
        self.assertEqual(report['provider']['calls'], 1)
        self.assertFalse((self.output / 'candidate').exists())
        self.assertNotIn('synthetic-key', json.dumps(report))

    def test_changed_source_after_api_refused(self):
        def change(*args):
            self.source.write_bytes(SOURCE + b'# changed\n')
            return canonical(response())
        self.transport.side_effect = change
        with self.assertRaisesRegex(EvaluationError, 'SOURCE_CHANGED'):
            self.run_controller(allow_api=True)
        self.assertFalse((self.output / 'candidate').exists())

    def test_api_to_existing_runner_uses_stdout_and_preserves_rejection(self):
        # Reuse the existing runner test double; no candidate code or Docker runs.
        from test_registered_operations import FakeSandbox
        result = self.run_controller(allow_api=True, execute=True, sandbox_factory=FakeSandbox)
        self.assertEqual(result['status'], 'VERIFIED')
        actual = json.loads((self.output / 'candidate/execution-results.json').read_text())
        self.assertEqual([row['findings'][0]['line'] for row in actual], [23, 62])
        self.output = self.root / 'runs/rejected'
        class Wrong(FakeSandbox):
            wrong = True
        with self.assertRaisesRegex(EvaluationError, 'CANDIDATE_REJECTED'):
            self.run_controller(allow_api=True, execute=True, sandbox_factory=Wrong)
        self.assertFalse((self.output / 'candidate/execution-results.json').exists())
        report = json.loads((self.output / 'provider-report.json').read_text())
        self.assertEqual(report['status'], 'FAILED')

    def test_cli_requires_config_opt_in_and_mutually_exclusive_manual_selection(self):
        spec = importlib.util.spec_from_file_location('openai_cli', ROOT / 'scripts/run_registered_operations.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with patch('builtins.print'), patch.object(module, 'run_openai') as api:
            for args in (['--catalog', '--allow-api'], ['--allow-api'],
                         ['--source', 'x', '--selection', 'y', '--openai-config', 'z', '--output', 'out'],
                         ['--source', 'x', '--selection', 'y', '--allow-api', '--output', 'out']):
                self.assertEqual(module.main(args), 2)
            api.assert_not_called()


if __name__ == '__main__':
    unittest.main()
