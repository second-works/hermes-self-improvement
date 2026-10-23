"""Host-only bounded local inference. No URL, headers or credential from the worker."""
import threading
import time
import http.client
import socket

from evaluation.core import EvaluationError, canonical, load_json, require
from .core import MODEL, request_body, safe_tool_calls, specification


def local_http(path, value=None, *, deadline=None, max_seconds=90):
    """One fixed loopback destination; total wall timeout includes headers and body."""
    require(path in ('/apply-template', '/tokenize', '/v1/chat/completions', '/v1/models'), 'DESTINATION')
    require((value is None) == (path == '/v1/models'), 'HTTP_METHOD')
    require(type(max_seconds) is int and 1 <= max_seconds <= 600, 'REQUEST_TIMEOUT_BOUNDARY')
    remaining = min(max_seconds, (deadline or time.monotonic() + max_seconds) - time.monotonic())
    require(remaining > 0, 'RUN_DEADLINE')
    connection = http.client.HTTPConnection('127.0.0.1', 8081, timeout=remaining)
    timed_out = threading.Event()
    def abort():
        timed_out.set()
        try:
            if connection.sock is not None:
                connection.sock.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        connection.close()
    timer = threading.Timer(remaining, abort)
    timer.daemon = True
    timer.start()
    try:
        connection.request('GET' if value is None else 'POST', path,
                           body=None if value is None else canonical(value),
                           headers={} if value is None else {'Content-Type': 'application/json'})
        response = connection.getresponse()
        require(response.status == 200, 'LOCAL_MODEL_HTTP')
        data = bytearray()
        while True:
            require(not timed_out.is_set(), 'MODEL_TIMEOUT')
            chunk = response.read1(min(65536, 1048577 - len(data)))
            if not chunk:
                break
            data.extend(chunk)
            require(len(data) <= 1048576, 'MODEL_OUTPUT_LIMIT')
        require(not timed_out.is_set(), 'MODEL_TIMEOUT')
        return load_json(bytes(data))
    except (OSError, http.client.HTTPException) as error:
        raise EvaluationError('MODEL_TIMEOUT' if timed_out.is_set() or isinstance(error, TimeoutError)
                              else 'LOCAL_MODEL_UNAVAILABLE') from None
    finally:
        timer.cancel()
        connection.close()


def live_context(deadline=None):
    value = local_http('/v1/models', deadline=deadline)
    require(type(value) is dict and type(value.get('data')) is list and len(value['data']) == 1,
            'MODEL_IDENTITY')
    model = value['data'][0]
    require(type(model) is dict and model.get('id') == MODEL, 'MODEL_IDENTITY')
    context = model.get('meta', {}).get('n_ctx')
    require(type(context) is int and 1 <= context <= 131072, 'CONTEXT_UNVERIFIED')
    return context


class LocalModel:
    def __init__(self, deadline=None, exchange=None, initial_usage=None, request_timeout=90, event_sink=None,
                 budget_profile='standard', tool_sink=None):
        self.budget = specification(budget_profile)['budget']
        require(type(request_timeout) is int and request_timeout in (90, 180, 300, 600), 'REQUEST_TIMEOUT_BOUNDARY')
        self.request_timeout = request_timeout
        self.child_seconds = max(300, request_timeout * 3)
        self.event_sink = event_sink or (lambda value: None)
        self.tool_sink = tool_sink or (lambda value: None)
        self.deadline = deadline or time.monotonic() + 1200
        self.exchange = exchange or self.http
        self.calls = self.input_tokens = self.output_tokens = 0
        if initial_usage is not None:
            limits = self.budget
            require(type(initial_usage) is dict and
                    set(initial_usage) == {'calls', 'input_tokens', 'output_tokens'} and
                    all(type(value) is int and 0 <= value <= limits[key]
                        for key, value in initial_usage.items()), 'CARRIED_BUDGET')
            self.calls = initial_usage['calls']
            self.input_tokens = initial_usage['input_tokens']
            self.output_tokens = initial_usage['output_tokens']
        self.failed = False
        self.spawns = 0
        self.reuse = False
        self.proposal_only = False
        self.condition = None
        self.output_kind = 'patch'
        self.condition_observations = []
        self.records = []
        self.usage_observations = []
        self.transport_failure = None
        self.rejected_tool_calls = []
        self.lock = threading.Lock()

    def http(self, path, value):
        require(path in ('/apply-template', '/tokenize', '/v1/chat/completions'), 'DESTINATION')
        return local_http(path, value, deadline=min(self.deadline, self.call_deadline),
                          max_seconds=self.request_timeout)

    def complete(self, value):
        with self.lock:
            started = time.monotonic()
            stage = 'preflight'
            try:
                require(not self.failed and time.monotonic() < self.deadline, 'RELAY_STOPPED')
                self.call_deadline = min(self.deadline, time.monotonic() + self.request_timeout)
                body = request_body(value)
                if self.condition is not None:
                    from .experiment import condition_body
                    body = condition_body(body, self.condition, self.output_kind)
                if self.proposal_only:
                    for field in ('tools', 'tool_choice', 'parallel_tool_calls'):
                        body.pop(field, None)
                if self.reuse and 'tools' in body:
                    body['tools'] = [tool for tool in body['tools']
                                     if tool['function']['name'] in ('skills_list', 'skill_view')]
                budget = self.budget
                require(self.calls < budget['calls'], 'CALL_BUDGET')
                rendered = self.exchange('/apply-template', body)
                require(type(rendered) is dict and type(rendered.get('prompt')) is str, 'TEMPLATE_SCHEMA')
                if self.condition is not None:
                    thinking = '<|think|>' in rendered['prompt']
                    self.condition_observations.append({'condition': list(self.condition),
                                                        'thinking_prompt_observed': thinking})
                    require(thinking == self.condition[0], 'THINKING_TEMPLATE_UNVERIFIED')
                tokenized = self.exchange('/tokenize', {'content': rendered['prompt'],
                                           'add_special': True, 'parse_special': True})
                tokens = tokenized.get('tokens') if type(tokenized) is dict else None
                require(type(tokens) is list and all(type(v) is int for v in tokens), 'TOKEN_SCHEMA')
                count, output = len(tokens), body['max_tokens']
                require(0 < count <= budget['per_input'] and
                        self.input_tokens + count <= budget['input_tokens'] and
                        self.output_tokens + output <= budget['output_tokens'], 'TOKEN_BUDGET')
                # Reserve worst-case output BEFORE every network attempt. Failures are never retried.
                self.calls += 1
                self.input_tokens += count
                self.output_tokens += output
                stage = 'completion'
                self.event_sink({'event': 'model_started', 'call': self.calls, 'input_tokens': count,
                                 'max_output_tokens': output, 'timeout_seconds': self.request_timeout})
                result = self.exchange('/v1/chat/completions', body)
                usage = result.get('usage', {}) if type(result) is dict else {}
                if type(usage) is not dict:
                    usage = {}
                actual_in, actual_out = usage.get('prompt_tokens'), usage.get('completion_tokens')
                self.usage_observations.append({
                    'preflight_input_tokens': count,
                    'reported_input_tokens': actual_in if type(actual_in) is int else None,
                    'reported_output_tokens': actual_out if type(actual_out) is int else None})
                require(type(actual_in) is int and actual_in == count and
                        type(actual_out) is int and 0 <= actual_out <= output, 'USAGE_UNVERIFIED')
                require(result.get('model') == MODEL and type(result.get('choices')) is list and
                        len(result['choices']) == 1 and result['choices'][0].get('finish_reason') != 'length',
                        'MODEL_RESULT')
                tool_calls = result['choices'][0].get('message', {}).get('tool_calls', [])
                if self.condition is not None:
                    thought = result['choices'][0].get('message', {}).get('reasoning_content')
                    self.condition_observations[-1]['reasoning_characters'] = len(thought) if type(thought) is str else 0
                if tool_calls:
                    self.tool_sink({'call': self.calls, 'tool_calls': tool_calls})
                try:
                    require(not self.proposal_only or not tool_calls, 'PROPOSAL_TOOL_CALL')
                    self.spawns += safe_tool_calls(result, reuse=self.reuse)
                except EvaluationError:
                    self.rejected_tool_calls = result['choices'][0].get('message', {}).get('tool_calls', [])
                    raise
                if self.spawns > 1:
                    self.rejected_tool_calls = tool_calls
                    raise EvaluationError('CHILD_LIMIT')
                self.output_tokens -= output - actual_out
                self.records.append({'call': self.calls, 'input_tokens': count, 'output_tokens': actual_out})
                self.event_sink({'event': 'model_finished', **self.records[-1]})
                return result
            except Exception as error:
                self.transport_failure = {'stage': stage, 'elapsed_seconds': round(time.monotonic() - started, 3),
                                          'reason': str(error) if isinstance(error, EvaluationError)
                                          else type(error).__name__}
                self.failed = True
                self.event_sink({'event': 'model_failed', **self.transport_failure})
                raise
