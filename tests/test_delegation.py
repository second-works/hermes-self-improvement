"""Boundary and failure tests; real Hermes/model acceptance remains a separate run."""
import copy
import ast
from pathlib import Path
import sys
import time
import unittest
from unittest.mock import patch
import tempfile
import importlib.util
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from evaluation.core import EvaluationError, canonical
from delegation.core import candidate_files, handoff, request_body, safe_tool_calls
from delegation.relay import LocalModel, live_context, local_http
from delegation.sandbox import DelegationSandbox, dialogue

MARKDOWN = '---\nname: delegated-patch-review\ndescription: Public fixture review\n---\n' + 'Read a unified patch and report unsafe added lines with their new line numbers.\n'
FILES = {'SKILL.md': MARKDOWN, 'scripts/review.py': 'print(1)\n'}
REQUEST = {'model': 'gemma-4-e4b', 'messages': [{'role': 'user', 'content': 'PUBLIC fixture'}],
           'stream': False, 'max_tokens': 32}


def response():
    return {'model': 'gemma-4-e4b', 'usage': {'prompt_tokens': 10, 'completion_tokens': 2},
            'choices': [{'finish_reason': 'stop', 'message': {'content': 'ok'}}]}


class ContractTests(unittest.TestCase):
    def test_candidate_allowlist_rejects_traversal_and_active_markdown(self):
        self.assertEqual(set(candidate_files(FILES)), set(FILES))
        for files in ({**FILES, '../escape': 'x'}, {**FILES, 'SKILL.md': MARKDOWN + '!`id`'},
                      {**FILES, 'SKILL.md': MARKDOWN.replace('description:', 'deps:')},
                      {**FILES, 'scripts/review.py': 'not python code !'},
                      {**FILES, 'scripts/review.py': 'x' * 65537}):
            with self.assertRaises(EvaluationError):
                candidate_files(files)

    def test_request_cannot_choose_destination_model_multimodal_or_unbounded_output(self):
        self.assertEqual(request_body(REQUEST)['max_tokens'], 32)
        for patch in ({'model': 'other'}, {'base_url': 'https://example.invalid'},
                      {'stream': True}, {'max_tokens': True}, {'max_tokens': 4097},
                      {'messages': [{'role': 'user', 'content': [{'type': 'image_url'}]}]},
                      {'tools': [{'type': 'function', 'function': {'name': 'terminal'}}]}):
            with self.assertRaises(EvaluationError):
                request_body({**REQUEST, **patch})

    def test_model_sees_only_the_guarded_standard_tool_subset(self):
        tools = [{'type': 'function', 'function': {'name': name, 'parameters': {'type': 'object',
                  'properties': {'category': {'type': 'string'}}}}} for name in ('skill_manage', 'delegate_task')]
        original = copy.deepcopy(tools)
        normalized = request_body({**REQUEST, 'tools': tools})['tools']
        self.assertEqual(tools, original)
        create = normalized[0]['function']['parameters']['properties']['operations']['items']['anyOf'][0]
        self.assertNotIn('category', create['properties'])
        self.assertNotIn('file_path', create['properties'])
        self.assertFalse(create['additionalProperties'])
        markdown = create['properties']['content']['enum'][0]
        self.assertTrue(markdown.startswith('---\nname: delegated-patch-review\n'))
        self.assertNotIn('\\n', markdown)
        task = normalized[1]['function']['parameters']['properties']['tasks']
        self.assertEqual(task['maxItems'], 1)
        self.assertEqual(set(task['items']['properties']), {'goal', 'context'})

    def test_real_hermes_reasoning_default_is_explicitly_bounded(self):
        captured_shape = {k: v for k, v in REQUEST.items() if k != 'stream'}
        captured_shape['reasoning_effort'] = 'medium'
        self.assertEqual(request_body(captured_shape)['reasoning_effort'], 'medium')
        for value in ('high', 'unknown', None, {'budget': 100000}):
            with self.assertRaisesRegex(EvaluationError, 'REASONING_SCHEMA'):
                request_body({**captured_shape, 'reasoning_effort': value})
        with self.assertRaises(EvaluationError):
            request_body({**captured_shape, 'base_url': 'https://example.invalid'})

    def test_incomplete_delegate_task_is_rejected_before_dispatch(self):
        for args in ({'tasks': [{'context': 'public'}]}, {'tasks': 1},
                     {'tasks': [{'goal': '', 'context': 'public'}]}, {'tasks': []}):
            value = response()
            value['choices'][0]['message']['tool_calls'] = [
                {'function': {'name': 'delegate_task', 'arguments': canonical(args).decode()}}]
            with self.assertRaisesRegex(EvaluationError, 'DELEGATE_TASK_SCHEMA'):
                safe_tool_calls(value)

    def test_writes_are_inspected_before_real_tool_execution(self):
        def tool(args):
            value = response()
            value['choices'][0]['message']['tool_calls'] = [
                {'function': {'name': 'skill_manage', 'arguments': canonical(args).decode()}}]
            return value
        create = {'action': 'create', 'name': 'delegated-patch-review', 'content': MARKDOWN}
        self.assertEqual(safe_tool_calls(tool({'operations': [create]})), 0)
        for operation in ({**create, 'content': MARKDOWN + '!`cat /unmounted-canary`'},
                          {**create, 'name': 'different'}, {**create, 'action': 'delete'}):
            with self.assertRaises(EvaluationError):
                safe_tool_calls(tool({'operations': [operation]}))
        with self.assertRaisesRegex(EvaluationError, 'REUSE_WRITE'):
            safe_tool_calls(tool({'operations': [create]}), reuse=True)

    def test_handoff_keeps_uncommitted_candidate_unversioned(self):
        patch, result = handoff(FILES, 'print(0)\n', baseline_sha='a' * 40, spec_hash='b' * 64,
                                results=[True] * 6)
        self.assertIn('fixtures/skills/github-code-review/review.py', patch)
        self.assertIsNone(result['candidate_commit_sha'])
        self.assertEqual(result['evaluation'], 'NOT_RUN')
        for values in ([True] * 5, [True] * 5 + [False]):
            with self.assertRaises(EvaluationError):
                handoff(FILES, 'print(0)\n', baseline_sha='a' * 40, spec_hash='b' * 64, results=values)


class RelayTests(unittest.TestCase):
    def test_direct_source_proposal_has_no_tools_and_rejects_hallucinated_calls(self):
        captured = []
        def exchange(path, value):
            if path == '/v1/chat/completions':
                captured.append(value)
            return self.exchange(path, value)
        relay = LocalModel(exchange=exchange)
        relay.proposal_only = True
        relay.complete({**REQUEST, 'tools': [{'type': 'function', 'function': {'name': 'skill_view'}}],
                        'tool_choice': 'auto', 'parallel_tool_calls': False})
        self.assertFalse({'tools', 'tool_choice', 'parallel_tool_calls'} & set(captured[0]))
        relay = LocalModel(exchange=exchange)
        relay.proposal_only = True
        self.answer['choices'][0]['message']['tool_calls'] = [
            {'function': {'name': 'skill_view', 'arguments': '{"name":"delegated-patch-review"}'}}]
        with self.assertRaisesRegex(EvaluationError, 'PROPOSAL_TOOL_CALL'):
            relay.complete(REQUEST)
        self.assertTrue(relay.rejected_tool_calls)

    def test_read_only_model_surface_excludes_writes_and_delegation(self):
        captured = []
        def exchange(path, value):
            if path == '/v1/chat/completions':
                captured.append(value)
            return self.exchange(path, value)
        relay = LocalModel(exchange=exchange)
        relay.reuse = True
        tools = [{'type': 'function', 'function': {'name': name}} for name in
                 ('skills_list', 'skill_view', 'skill_manage', 'delegate_task')]
        relay.complete({**REQUEST, 'tools': tools})
        self.assertEqual([tool['function']['name'] for tool in captured[0]['tools']],
                         ['skills_list', 'skill_view'])

    def setUp(self):
        self.paths = []
        self.answer = response()
        self.tokens = 10

    def exchange(self, path, value):
        self.paths.append(path)
        if path == '/apply-template':
            return {'prompt': 'fixed public prompt'}
        if path == '/tokenize':
            return {'tokens': [1] * self.tokens}
        return copy.deepcopy(self.answer)

    def test_reserves_then_settles_and_never_contacts_extra_endpoint(self):
        relay = LocalModel(exchange=self.exchange)
        relay.complete(REQUEST)
        self.assertEqual((relay.calls, relay.input_tokens, relay.output_tokens), (1, 10, 2))
        self.assertEqual(self.paths, ['/apply-template', '/tokenize', '/v1/chat/completions'])

    def test_gemma_special_token_is_counted_before_budget_reservation(self):
        def exchange(path, value):
            if path == '/apply-template':
                return {'prompt': 'public rendered prompt'}
            if path == '/tokenize':
                return {'tokens': [1] * (12 if value['add_special'] else 11)}
            answer = response()
            answer['usage']['prompt_tokens'] = 12
            return answer
        relay = LocalModel(exchange=exchange)
        relay.complete(REQUEST)
        self.assertEqual(relay.input_tokens, 12)
        self.assertEqual(relay.usage_observations, [{'preflight_input_tokens': 12,
                         'reported_input_tokens': 12, 'reported_output_tokens': 2}])

    def test_invalid_generated_skill_is_quarantined_before_execution(self):
        arguments = {'operations': [{'action': 'create', 'name': 'delegated-patch-review',
                     'content': '---\nname: delegated-patch-review\ndescription: Test\n---\nx'}]}
        calls = [{'function': {'name': 'skill_manage', 'arguments': canonical(arguments).decode()}}]
        self.answer['choices'][0]['message']['tool_calls'] = calls
        relay = LocalModel(exchange=self.exchange)
        with self.assertRaisesRegex(EvaluationError, 'SKILL_METADATA'):
            relay.complete(REQUEST)
        self.assertEqual(relay.rejected_tool_calls, calls)
        self.assertTrue(relay.failed)

    def test_input_limit_stops_before_inference_and_poisoned_run_cannot_retry(self):
        relay = LocalModel(exchange=self.exchange)
        self.tokens = 16385
        with self.assertRaisesRegex(EvaluationError, 'TOKEN_BUDGET'):
            relay.complete(REQUEST)
        self.assertEqual(relay.calls, 0)
        self.assertNotIn('/v1/chat/completions', self.paths)
        with self.assertRaisesRegex(EvaluationError, 'RELAY_STOPPED'):
            relay.complete(REQUEST)

    def test_worst_case_output_and_call_count_are_checked_before_request(self):
        for field, value in [('output_tokens', 19999), ('calls', 20), ('input_tokens', 100000)]:
            with self.subTest(field=field):
                relay = LocalModel(exchange=self.exchange)
                setattr(relay, field, value)
                before = self.paths.count('/v1/chat/completions')
                with self.assertRaises(EvaluationError):
                    relay.complete(REQUEST)
                self.assertEqual(self.paths.count('/v1/chat/completions'), before)

    def test_missing_usage_and_template_mismatch_fail_without_unreserving(self):
        for usage in ({}, {'prompt_tokens': 11, 'completion_tokens': 2},
                      {'prompt_tokens': 10, 'completion_tokens': 33}):
            self.answer['usage'] = usage
            relay = LocalModel(exchange=self.exchange)
            with self.assertRaisesRegex(EvaluationError, 'USAGE_UNVERIFIED'):
                relay.complete(REQUEST)
            self.assertEqual(relay.calls, 1)
            self.assertEqual(relay.output_tokens, 32)

    def test_extended_budget_is_explicit_and_keeps_per_request_limits(self):
        relay = LocalModel(exchange=self.exchange, budget_profile='extended',
                           initial_usage={'calls': 39, 'input_tokens': 199990, 'output_tokens': 39968})
        relay.complete(REQUEST)
        self.assertEqual((relay.calls, relay.input_tokens, relay.output_tokens), (40, 200000, 39970))
        with self.assertRaises(EvaluationError):
            relay.complete(REQUEST)
        with self.assertRaisesRegex(EvaluationError, 'CARRIED_BUDGET'):
            LocalModel(initial_usage={'calls': 21, 'input_tokens': 0, 'output_tokens': 0})
        self.assertEqual(relay.budget['per_input'], 16384)
        self.assertEqual(relay.budget['per_output'], 4096)

    def test_carried_reservations_are_not_reset_on_next_trial(self):
        used = {'calls': 19, 'input_tokens': 99990, 'output_tokens': 19968}
        relay = LocalModel(exchange=self.exchange, initial_usage=used)
        relay.complete(REQUEST)
        self.assertEqual((relay.calls, relay.input_tokens, relay.output_tokens), (20, 100000, 19970))
        with self.assertRaises(EvaluationError):
            relay.complete(REQUEST)
        for value in ({**used, 'calls': -1}, {**used, 'calls': True}, {**used, 'output_tokens': 20001}):
            with self.assertRaisesRegex(EvaluationError, 'CARRIED_BUDGET'):
                LocalModel(initial_usage=value)

    def test_extended_budgets_carry_usage_and_stop_at_limit(self):
        for profile, calls, inputs, outputs in [('extended60', 60, 300000, 60000),
                                                 ('extended80', 80, 400000, 80000),
                                                 ('patch88', 88, 400000, 80000),
                                                 ('matrix94', 94, 400000, 80000)]:
            relay = LocalModel(exchange=self.exchange, budget_profile=profile,
                               initial_usage={'calls': calls - 1, 'input_tokens': inputs - 10,
                                              'output_tokens': outputs - 32})
            relay.complete(REQUEST)
            self.assertEqual((relay.calls, relay.input_tokens, relay.output_tokens), (calls, inputs, outputs - 30))
            with self.assertRaises(EvaluationError):
                relay.complete(REQUEST)
            self.assertEqual(relay.budget['per_input'], 16384)
            self.assertEqual(relay.budget['per_output'], 4096)

    def test_extended_timeouts_are_bounded_and_progress_contains_no_prompt(self):
        for seconds in (180, 300, 600):
            events = []
            relay = LocalModel(exchange=self.exchange, request_timeout=seconds, event_sink=events.append)
            relay.complete(REQUEST)
            self.assertEqual(relay.request_timeout, seconds)
            self.assertEqual(relay.child_seconds, seconds * 3)
            self.assertEqual([e['event'] for e in events], ['model_started', 'model_finished'])
            self.assertNotIn('messages', repr(events))
        for seconds in (0, 91, 601, True):
            with self.assertRaisesRegex(EvaluationError, 'REQUEST_TIMEOUT_BOUNDARY'):
                LocalModel(request_timeout=seconds)

    def test_socket_timeout_is_reported_as_timeout(self):
        with patch('delegation.relay.http.client.HTTPConnection') as connection:
            connection.return_value.request.side_effect = TimeoutError()
            with self.assertRaisesRegex(EvaluationError, 'MODEL_TIMEOUT'):
                local_http('/v1/models', deadline=time.monotonic() + 1)
        relay = LocalModel(exchange=lambda *_: (_ for _ in ()).throw(EvaluationError('MODEL_TIMEOUT')))
        with self.assertRaises(EvaluationError):
            relay.complete(REQUEST)
        self.assertEqual(relay.transport_failure['stage'], 'preflight')
        self.assertEqual(relay.transport_failure['reason'], 'MODEL_TIMEOUT')

    def test_error_and_deadline_never_retry_or_fallback(self):
        relay = LocalModel(exchange=lambda *_: (_ for _ in ()).throw(OSError('fixture')))
        with self.assertRaises(OSError):
            relay.complete(REQUEST)
        self.assertTrue(relay.failed)
        relay = LocalModel(deadline=time.monotonic() - 1, exchange=self.exchange)
        with self.assertRaises(EvaluationError):
            relay.complete(REQUEST)
        self.assertEqual(self.paths, [])

    def test_second_child_is_rejected_before_dispatch(self):
        self.answer['choices'][0]['message']['tool_calls'] = [
            {'function': {'name': 'delegate_task', 'arguments': '{"tasks":[{"goal":"public fixture","context":"public context"}]}'}}]
        relay = LocalModel(exchange=self.exchange)
        relay.complete(REQUEST)
        with self.assertRaisesRegex(EvaluationError, 'CHILD_LIMIT'):
            relay.complete(REQUEST)


class PipeTests(unittest.TestCase):
    def test_protocol_does_not_treat_prose_or_duplicate_result_as_success(self):
        for output in ('unstructured success', '{"kind":"result"}\n{"kind":"result"}'):
            argv = [sys.executable, '-I', '-c', 'import sys;sys.stdin.readline();print(' + repr(output) + ')']
            with self.assertRaises(EvaluationError):
                dialogue(argv, env={}, data=b'{}', timeout=2, relay=LocalModel(exchange=lambda *_: None))

    def test_child_deadline_also_bounds_blocking_model_exchange(self):
        observed = []
        fixture = RelayTests()
        fixture.setUp()
        relay = LocalModel(deadline=time.monotonic() + 1200)
        original_deadline = relay.deadline
        def exchange(path, value):
            observed.append(relay.deadline)
            return fixture.exchange(path, value)
        relay.exchange = exchange
        code = ('import sys,json;sys.stdin.readline();'
                'print(json.dumps({"kind":"event","event":"child_started","phase":"create"}),flush=True);'
                'print(json.dumps({"kind":"model_request","body":' + repr(REQUEST) + '}),flush=True);'
                'sys.stdin.readline();print(json.dumps({"kind":"result","status":"VERIFIED"}))')
        started = time.monotonic()
        dialogue([sys.executable, '-I', '-c', code], env={}, data=b'{}', timeout=2, relay=relay)
        self.assertTrue(observed and all(value < started + 301 for value in observed))
        self.assertEqual(relay.deadline, original_deadline)

    def test_relay_failure_preserves_prior_child_events(self):
        code = ('import sys,json;sys.stdin.readline();'
                'print(json.dumps({"kind":"event","event":"child_started","phase":"create"}),flush=True);'
                'print(json.dumps({"kind":"model_request","body":' + repr(REQUEST) + '}),flush=True);'
                'sys.stdin.readline()')
        relay = LocalModel(exchange=lambda *_: (_ for _ in ()).throw(EvaluationError('MODEL_TIMEOUT')))
        with self.assertRaises(EvaluationError) as caught:
            dialogue([sys.executable, '-I', '-c', code], env={}, data=b'{}', timeout=2, relay=relay)
        self.assertEqual(caught.exception.protocol_events[0]['event'], 'child_started')

    def test_bounded_pipe_delivers_model_response_and_keeps_events(self):
        code = ('import sys,json;sys.stdin.readline();'
                'print(json.dumps({"kind":"model_request","body":' + repr(REQUEST) + '}),flush=True);'
                'response=json.loads(sys.stdin.readline());'
                'print(json.dumps({"kind":"event","event":"tool_started","tool":"skills_list","phase":"capability"}));'
                'print(json.dumps({"kind":"result","status":"VERIFIED"}))')
        fixture = RelayTests()
        fixture.setUp()
        outcome = dialogue([sys.executable, '-I', '-c', code], env={}, data=b'{}', timeout=2,
                           relay=LocalModel(exchange=fixture.exchange))
        self.assertEqual(outcome['exit'], 0)
        self.assertEqual(len(outcome['events']), 1)

    def test_child_deadline_and_output_limit_do_not_return_success(self):
        code = 'import sys,time;sys.stdin.readline();print("x"*1048577,flush=True);time.sleep(2)'
        with self.assertRaisesRegex(EvaluationError, 'OUTPUT_LIMIT'):
            dialogue([sys.executable, '-I', '-c', code], env={}, data=b'{}', timeout=2,
                     relay=LocalModel())
        code = 'import sys,time;sys.stdin.readline();time.sleep(2)'
        result = dialogue([sys.executable, '-I', '-c', code], env={}, data=b'{}', timeout=0.05,
                          relay=LocalModel())
        self.assertEqual(result['error'], 'TIMEOUT')


class RuntimeBoundaryTests(unittest.TestCase):
    def test_matrix_records_format_and_scope_failures_without_skipping_other_conditions(self):
        from unittest.mock import Mock
        from delegation.experiment import CONDITIONS
        from test_delegation_patch import SOURCE, CONTEXT, COMMENT
        spec = importlib.util.spec_from_file_location('matrix_controller', ROOT / 'scripts/delegate_skill.py')
        controller = importlib.util.module_from_spec(spec); spec.loader.exec_module(controller)
        files = {**FILES, 'scripts/review.py': SOURCE}
        proposals = ['invalid JSON', canonical({'insertions': [{'after_line': 999, 'text': 'wrong'}]}).decode(),
                     canonical({'insertions': [{'after_line': 8, 'text': COMMENT}]}).decode(),
                     canonical({'insertions': [{'after_line': 5, 'text': CONTEXT},
                                                {'after_line': 8, 'text': COMMENT}]}).decode()]
        box = SimpleNamespace(relay=SimpleNamespace(reuse=False, proposal_only=False, condition=None,
                                                    calls=0, condition_observations=[]))
        observed = []
        def invoke(box, mode, **kwargs):
            self.assertTrue(box.relay.proposal_only)
            observed.append(box.relay.condition)
            self.assertEqual(kwargs['files'], files)
            self.assertEqual(kwargs['patch_attempt'], 1)
            box.relay.calls += 1
            thinking = box.relay.condition[0]
            box.relay.condition_observations.append({'thinking_prompt_observed': thinking,
                                                     'reasoning_characters': 7 if thinking else 0})
            return {'final': proposals[len(observed) - 1],
                    'source_sha256': controller.digest(SOURCE.encode())}
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); parent = root / 'runs/seed'; work = root / 'runs/matrix'; work.mkdir(parents=True)
            for name, content in files.items():
                path = parent / 'repair-candidate-1' / name
                path.parent.mkdir(parents=True, exist_ok=True); path.write_text(content)
            seed = parent / 'report.json'; seed.write_text('{}')
            (parent / 'repair-comparison-1.json').write_bytes(canonical({'hashes': candidate_files(files)}))
            with patch.object(controller, 'ROOT', root), patch.object(controller, 'Sandbox'), patch.object(
                    controller, 'invoke', side_effect=invoke), patch.object(controller, 'check_candidate',
                    side_effect=[[True] * 5 + [False] * 4, [True] * 9, [True] * 9]) as checks, patch(
                    'delegation.context.resources', return_value={'swap_mib': 0, 'memory_free_percent': 50}):
                experiment, qualified = controller.matrix_existing(box, work, seed, time.monotonic() + 30)
            self.assertEqual(observed, list(CONDITIONS))
            self.assertEqual(checks.call_count, 3)
            self.assertEqual(len(qualified), 2)
            rows = experiment['rows']
            self.assertFalse(rows[0]['json_valid'])
            self.assertTrue(rows[1]['json_valid']); self.assertFalse(rows[1]['scope_valid'])
            self.assertIsNone(rows[1]['tests'])
            self.assertEqual(rows[3]['tests'], [True] * 9)
            self.assertFalse(box.relay.proposal_only); self.assertIsNone(box.relay.condition)

    def test_repair_compares_all_cases_and_stops_on_regression(self):
        from unittest.mock import Mock
        spec = importlib.util.spec_from_file_location('repair_controller', ROOT / 'scripts/delegate_skill.py')
        controller = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(controller)
        baseline = [True, True, True, False, True, False]
        for after, error, invalid_output in [([False, True, True, True, True, False], 'REPAIR_REGRESSION', False),
                                             (baseline, 'REPAIR_NO_IMPROVEMENT', False),
                                             ([True] * 6, None, False),
                                             ([False, True, True, True, True, False], 'REPAIR_REGRESSION', True)]:
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                source = root / 'runs/seed/candidate'
                for name, content in FILES.items():
                    p = source / name; p.parent.mkdir(parents=True, exist_ok=True); p.write_text(content)
                seed = source.parent / 'report.json'
                seed.write_bytes(canonical({'candidate_hashes': candidate_files(FILES)}))
                work = root / 'runs/repair'; work.mkdir()
                repaired = {**FILES, 'scripts/review.py': 'print(2)\n'}
                runner = Mock()
                runner.run.return_value = {'error': None, 'exit': 0, 'stderr': b'',
                                           'container_exit': 0, 'stdout': b'{}'}
                if invalid_output:
                    runner.run.side_effect = ([dict(runner.run.return_value) for _ in range(6)] +
                                              [{**runner.run.return_value, 'stdout': b''}] +
                                              [dict(runner.run.return_value) for _ in range(5)])
                with patch.object(controller, 'ROOT', root), patch.object(controller, 'Sandbox', return_value=runner), patch.object(
                        controller, 'invoke', return_value={'files': repaired}) as invoked, patch.object(
                        controller, 'correct_output', side_effect=baseline + (after[1:] if invalid_output else after)):
                    if error:
                        with self.assertRaisesRegex(EvaluationError, error):
                            controller.repair_existing(object(), work, seed, time.monotonic() + 30)
                    else:
                        self.assertEqual(controller.repair_existing(object(), work, seed, time.monotonic() + 30),
                                         (repaired, after))
                    self.assertEqual(runner.run.call_count, 12)
                    self.assertEqual(invoked.call_count, 1)

    def test_background_child_wait_preserves_completion_and_both_deadlines(self):
        tree = ast.parse((ROOT / 'fixtures/delegation/worker.py').read_text())
        function = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'wait_for_child')
        from unittest.mock import Mock
        done = Mock()
        done.is_set.return_value = False
        done.wait.return_value = True
        scope = {'child_started_at': 10, 'phase_deadline': 50, 'child_seconds': 30,
                 'time': SimpleNamespace(monotonic=lambda: 20), 'child_done': done}
        exec(compile(ast.Module(body=[function], type_ignores=[]), '<worker-wait>', 'exec'), scope)
        scope['wait_for_child']()
        done.wait.assert_called_once_with(20)
        scope['phase_deadline'] = 25
        done.wait.reset_mock()
        scope['wait_for_child']()
        done.wait.assert_called_once_with(5)
        done.wait.return_value = False
        with self.assertRaisesRegex(RuntimeError, 'CHILD_TIMEOUT'):
            scope['wait_for_child']()
        scope['child_started_at'] = None
        with self.assertRaisesRegex(RuntimeError, 'REAL_DELEGATION_UNVERIFIED'):
            scope['wait_for_child']()

    def test_tree_commitment_rejects_directory_alias_even_if_it_adds_no_file(self):
        spec = importlib.util.spec_from_file_location('tree_controller', ROOT / 'scripts/delegate_skill.py')
        controller = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(controller)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / 'empty').mkdir()
            self.assertEqual(controller.hashes(root), {})
            (root / 'alias').symlink_to(root / 'empty', target_is_directory=True)
            with self.assertRaisesRegex(EvaluationError, 'TREE_SYMLINK'):
                controller.hashes(root)

    def test_live_identity_does_not_guess_or_accept_another_model(self):
        good = {'data': [{'id': 'gemma-4-e4b', 'meta': {'n_ctx': 32768}}]}
        with patch('delegation.relay.local_http', return_value=good):
            self.assertEqual(live_context(), 32768)
        for value in ({'data': []}, {'data': [{'id': 'other', 'meta': {'n_ctx': 32768}}]},
                      {'data': [{'id': 'gemma-4-e4b', 'meta': {'n_ctx': True}}]}):
            with patch('delegation.relay.local_http', return_value=value), self.assertRaises(EvaluationError):
                live_context()

    def test_no_other_destination_or_redirect_can_be_followed(self):
        for path in ('https://example.invalid', '//example.invalid', '/v1/completions', '/admin'):
            with self.assertRaisesRegex(EvaluationError, 'DESTINATION'):
                local_http(path, {})
        with patch('delegation.relay.http.client.HTTPConnection') as connection:
            connection.return_value.getresponse.return_value.status = 307
            with self.assertRaisesRegex(EvaluationError, 'LOCAL_MODEL_HTTP'):
                local_http('/v1/chat/completions', {})
            connection.assert_called_once()
            self.assertEqual(connection.call_args.args, ('127.0.0.1', 8081))

    def test_context_stop_is_preserved_by_controller(self):
        spec = importlib.util.spec_from_file_location('delegation_controller', ROOT / 'scripts/delegate_skill.py')
        controller = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(controller)
        with tempfile.TemporaryDirectory() as temporary:
            work = Path(temporary)
            value = {'kind': 'result', 'status': 'STOPPED', 'reason': 'RUNTIME_CONTEXT_UNSUPPORTED',
                     'runtime_context': 32768, 'required_context': 64000}
            box = SimpleNamespace(work=work, runtime_context=32768,
                    deadline=time.monotonic() + 1200, relay=LocalModel(),
                    run=lambda *a, **k: {'exit': 1, 'container_exit': 1, 'error': None,
                                        'stdout': canonical(value), 'stderr': b'', 'events': []})
            with self.assertRaisesRegex(EvaluationError, 'RUNTIME_CONTEXT_UNSUPPORTED'):
                controller.invoke(box, 'boot')
            self.assertEqual((work / 'boot.json').read_bytes().strip(), canonical(value))

    def test_runtime_has_no_host_write_mount_or_network_and_checks_configuration(self):
        (ROOT / 'runs').mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=ROOT / 'runs') as temporary:
            work = Path(temporary)
            prep = work / 'preparation'
            for name in ('source', 'packages/site'):
                (prep / name).mkdir(parents=True)
            (prep / 'requirements.lock').write_text('# test')
            box = DelegationSandbox(ROOT, work, 'sha256:' + 'a' * 64, preparation=prep)
            args = box.options('synthetic', ROOT / 'fixtures/delegation/worker.py')
            self.assertIn('--network=none', args)
            self.assertTrue(all(not writable for _, _, writable in box.mounts(ROOT / 'fixtures/delegation/worker.py')))
            with self.assertRaises(EvaluationError):
                box.verify_config({'HostConfig': {'NetworkMode': 'bridge'}, 'Config': {}},
                                  ROOT / 'fixtures/delegation/worker.py')


if __name__ == '__main__':
    unittest.main()
