"""Opt-in, bounded Chat Completions selection for the fixed PUBLIC catalog."""
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
import http.client
import os
import queue
import re
import socket
import ssl
import threading
import time

from delegation.catalog import catalog, validate_selection
from evaluation.core import EvaluationError, canonical, digest, load_json, require


ENDPOINT = 'https://api.openai.com/v1/chat/completions'


def connect_fixed(address, timeout, source_address=None):
    """Bound DNS separately; a late resolver can never send a paid request."""
    require(address == ('api.openai.com', 443) and source_address is None, 'API_FAILED')
    deadline = time.monotonic() + timeout
    answers = queue.Queue(maxsize=1)
    def resolve():
        try:
            answers.put(socket.getaddrinfo('api.openai.com', 443, type=socket.SOCK_STREAM)[0])
        except Exception:
            answers.put(None)
    resolver = threading.Thread(target=resolve, daemon=True)
    resolver.start()
    try:
        answer = answers.get(timeout=timeout)
    except queue.Empty:
        raise EvaluationError('API_TIMEOUT') from None
    require(answer is not None, 'API_FAILED')
    remaining = deadline - time.monotonic()
    require(remaining > 0, 'API_TIMEOUT')
    family, kind, protocol, _, target = answer
    sock = socket.socket(family, kind, protocol)
    try:
        sock.settimeout(remaining)
        sock.connect(target)
        return sock
    except Exception:
        sock.close()
        raise


@dataclass(frozen=True)
class Config:
    model: str
    input_usd_per_million: Decimal
    output_usd_per_million: Decimal
    max_cost_usd: Decimal
    max_calls: int
    model_context_tokens: int
    max_input_tokens: int
    max_output_tokens: int
    max_total_input_tokens: int
    max_total_output_tokens: int
    deadline_seconds: int
    timeout_seconds: int
    max_response_bytes: int

    @classmethod
    def parse(cls, value):
        fields = set(cls.__dataclass_fields__)
        require(type(value) is dict and set(value) == fields, 'API_CONFIG')
        require(type(value['model']) is str and
                re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]{0,127}', value['model']), 'API_MODEL')
        parsed = dict(value)
        for name in ('input_usd_per_million', 'output_usd_per_million', 'max_cost_usd'):
            raw = value[name]
            require(type(raw) is str and len(raw) <= 24 and
                    re.fullmatch(r'[0-9]+(?:\.[0-9]{1,12})?', raw), 'API_PRICE')
            try:
                number = Decimal(raw)
            except InvalidOperation:
                raise EvaluationError('API_PRICE') from None
            require(number.is_finite() and 0 < number <= 1000000, 'API_PRICE')
            parsed[name] = number
        bounds = {'max_calls': 100, 'model_context_tokens': 2000000, 'max_input_tokens': 2000000,
                  'max_output_tokens': 100000, 'max_total_input_tokens': 200000000,
                  'max_total_output_tokens': 10000000, 'deadline_seconds': 600,
                  'timeout_seconds': 120, 'max_response_bytes': 1048576}
        for name, upper in bounds.items():
            require(type(value[name]) is int and 1 <= value[name] <= upper, 'API_LIMIT')
        require(value['model_context_tokens'] <= value['max_input_tokens'] <= value['max_total_input_tokens'] and
                value['max_output_tokens'] < value['model_context_tokens'] and
                value['max_output_tokens'] <= value['max_total_output_tokens'] and
                value['timeout_seconds'] <= value['deadline_seconds'], 'API_LIMIT')
        return cls(**parsed)


def post(body, key, timeout, limit):
    """One direct TLS POST. No env proxy, redirects, retries, or error-body logging."""
    connection = http.client.HTTPSConnection('api.openai.com', 443, timeout=timeout,
                                              context=ssl.create_default_context())
    connection._create_connection = connect_fixed
    # A wall timer also bounds slow headers / slow-drip response bodies.
    def expire():
        sock = connection.sock
        if sock is not None:
            try:
                sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
        connection.close()
    timer = threading.Timer(timeout, expire)
    timer.daemon = True
    timer.start()
    started = time.monotonic()
    try:
        connection.connect()
        # Prevent http.client from reconnecting after the wall timer closes a
        # connection between this deadline check and request dispatch.
        connection.auto_open = 0
        require(time.monotonic() - started < timeout, 'API_TIMEOUT')
        connection.request('POST', '/v1/chat/completions', body=body,
                           headers={'Authorization': 'Bearer ' + key,
                                    'Content-Type': 'application/json',
                                    'Accept': 'application/json'})
        response = connection.getresponse()
        require(response.status == 200, 'API_HTTP_ERROR')
        require(response.getheader('Content-Type', '').split(';')[0].strip() ==
                'application/json', 'API_CONTENT_TYPE')
        length = response.getheader('Content-Length')
        require(length is None or (length.isascii() and length.isdigit() and
                                  int(length) <= limit), 'API_RESPONSE_SIZE')
        data = response.read(limit + 1)
        require(time.monotonic() - started < timeout, 'API_TIMEOUT')
        require(len(data) <= limit, 'API_RESPONSE_SIZE')
        return data
    finally:
        timer.cancel()
        connection.close()


class Provider:
    def __init__(self, config, *, allow_api=False, transport=post, clock=time.monotonic):
        self.config = config
        self.allow_api = allow_api
        self.transport = transport
        self.clock = clock
        self.deadline = clock() + config.deadline_seconds
        self.calls = 0
        self.input_tokens = 0
        self.output_tokens = 0
        self.cost = Decimal(0)
        self.reserved = Decimal(0)
        self.status = 'NOT_CALLED'
        self.response_hash = None
        self.halted = False
        self.lock = threading.Lock()

    def metadata(self):
        return {'provider': 'openai', 'endpoint': ENDPOINT, 'model': self.config.model,
                'status': self.status,
                'calls': self.calls, 'input_tokens': self.input_tokens,
                'output_tokens': self.output_tokens, 'cost_usd': str(self.cost),
                'unsettled_reserved_usd': str(self.reserved),
                'response_sha256': self.response_hash}

    def price(self, inputs, outputs):
        return (inputs * self.config.input_usd_per_million +
                outputs * self.config.output_usd_per_million) / Decimal(1000000)

    def select(self, public_state):
        # Only the caller's validated finite PUBLIC state is accepted, never free text.
        require(type(public_state) is dict and set(public_state) == {'available_operations'} and
                type(public_state['available_operations']) is list, 'API_PUBLIC_STATE')
        validate_selection({'operations': public_state['available_operations']})
        with self.lock:
            require(self.allow_api is True, 'API_OPT_IN_REQUIRED')
            require(not self.halted, 'API_RUN_HALTED')
            config = self.config
            payload = {'model': config.model, 'store': False, 'stream': False, 'n': 1,
                       'service_tier': 'default', 'max_completion_tokens': config.max_output_tokens,
                       'messages': [{'role': 'system', 'content':
                           'Select all available registered repairs for this fixed PUBLIC fixture. '
                           'Return only the JSON selection; choose [] when none are available. '
                           'Never invent operations, code, tools, or execution results.'},
                           {'role': 'user', 'content': canonical({
                               'catalog': catalog(), 'state': public_state}).decode()}],
                       'response_format': {'type': 'json_schema', 'json_schema': {
                           'name': 'registered_operations', 'strict': True,
                           # uniqueItems is checked locally; not in OpenAI's schema subset.
                           'schema': {key: val for key, val in catalog()['selection_schema'].items()}}}}
            del payload['response_format']['json_schema']['schema']['properties']['operations']['uniqueItems']
            body = canonical(payload)
            # Reserve the configured input ceiling, not a guessed average token count.
            # Reject oversized requests early. For cost safety reserve the entire
            # operator-declared model context, including server-side framing, rather
            # than relying on this conservative byte heuristic as a token estimate.
            require(len(body) + 8192 + config.max_output_tokens <= config.model_context_tokens,
                    'API_INPUT_LIMIT')
            reservation = self.price(config.max_input_tokens, config.max_output_tokens)
            require(self.calls < config.max_calls and
                    self.input_tokens + config.max_input_tokens <= config.max_total_input_tokens and
                    self.output_tokens + config.max_output_tokens <= config.max_total_output_tokens and
                    self.cost + reservation < config.max_cost_usd, 'API_BUDGET')
            remaining = self.deadline - self.clock()
            require(remaining > 0, 'API_DEADLINE')
            # Read the key only after every opt-in / preflight gate has passed.
            key = os.environ.get('OPENAI_API_KEY')
            require(type(key) is str and re.fullmatch(r'[A-Za-z0-9_-]{1,512}', key), 'API_KEY_REQUIRED')
            self.calls += 1
            self.reserved = reservation
            self.status = 'REQUESTED'
            try:
                raw = self.transport(body, key, min(config.timeout_seconds, remaining),
                                     config.max_response_bytes)
                require(self.clock() < self.deadline, 'API_DEADLINE')
                require(type(raw) is bytes and len(raw) <= config.max_response_bytes,
                        'API_RESPONSE_SIZE')
                self.response_hash = digest(raw)
                value = load_json(raw)
                require(type(value) is dict and 'error' not in value and
                        value.get('model') == config.model and
                        value.get('object') == 'chat.completion', 'API_RESPONSE')
                usage = value.get('usage')
                require(type(usage) is dict and all(type(usage.get(k)) is int and usage[k] >= 0
                        for k in ('prompt_tokens', 'completion_tokens', 'total_tokens')), 'API_USAGE')
                inputs, outputs = usage['prompt_tokens'], usage['completion_tokens']
                require(inputs > 0 and inputs + outputs == usage['total_tokens'] and
                        inputs <= config.max_input_tokens and outputs <= config.max_output_tokens and
                        inputs + outputs <= config.model_context_tokens,
                        'API_USAGE')
                self.input_tokens += inputs
                self.output_tokens += outputs
                self.cost += self.price(inputs, outputs)
                self.reserved = Decimal(0)
                choices = value.get('choices')
                require(type(choices) is list and len(choices) == 1 and type(choices[0]) is dict,
                        'API_CHOICES')
                choice = choices[0]
                message = choice.get('message')
                require(type(choice.get('index')) is int and choice['index'] == 0 and
                        choice.get('finish_reason') == 'stop' and
                        type(message) is dict and message.get('role') == 'assistant' and
                        not message.get('refusal') and not message.get('tool_calls') and
                        not message.get('function_call') and type(message.get('content')) is str,
                        'API_SELECTION')
                selection = load_json(message['content'])
                operations = validate_selection(selection)
                require(all(op in public_state['available_operations'] for op in operations),
                        'OPERATION_NOT_AVAILABLE')
                self.status = 'SELECTED_NOT_EXECUTED'
                return {'operations': list(operations)}
            except Exception as error:
                self.status = 'FAILED'
                self.halted = True
                # Never propagate transport messages, JSON fragments, headers, or keys.
                codes = {'API_HTTP_ERROR', 'API_CONTENT_TYPE', 'API_RESPONSE_SIZE',
                         'API_TIMEOUT', 'API_DEADLINE', 'API_RESPONSE', 'API_USAGE',
                         'API_CHOICES', 'API_SELECTION', 'OPERATION_SCHEMA',
                         'DUPLICATE_OPERATION', 'OPERATION_NOT_AVAILABLE',
                         'JSON_INVALID', 'JSON_DUPLICATE', 'JSON_NUMBER'}
                code = str(error) if type(error) is EvaluationError and str(error) in codes else 'API_FAILED'
                raise EvaluationError(code) from None
