"""Reuse verified Docker create/inspect/cleanup; add a bounded pipe for local inference."""
import os
from pathlib import Path
import selectors
import subprocess
import time

from evaluation.core import EvaluationError, canonical, load_json, require
from self_evolution.sandbox import SpikeSandbox


def dialogue(argv, *, env, data, timeout, relay):
    process = subprocess.Popen(argv, env=env, stdin=subprocess.PIPE,
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               start_new_session=True)
    deadline = min(time.monotonic() + timeout, relay.deadline)
    selector = selectors.DefaultSelector()
    streams = {1: bytearray(), 2: bytearray()}
    pending = bytearray(data + b'\n')
    events, total, result, error = [], 0, None, None
    child_started = None
    try:
        for stream, key in ((process.stdout, 1), (process.stderr, 2), (process.stdin, 0)):
            os.set_blocking(stream.fileno(), False)
            selector.register(stream, selectors.EVENT_WRITE if key == 0 else selectors.EVENT_READ, key)
        while selector.get_map():
            now = time.monotonic()
            if now >= deadline or child_started is not None and now - child_started >= relay.child_seconds:
                error = 'TIMEOUT'
                break
            for key, _ in selector.select(min(0.1, max(0, deadline - now))):
                if key.data == 0:
                    try:
                        count = os.write(key.fileobj.fileno(), pending[:65536])
                        del pending[:count]
                    except BrokenPipeError:
                        require(False, 'WORKER_PIPE_CLOSED')
                    if not pending:
                        selector.unregister(key.fileobj)
                    continue
                chunk = os.read(key.fileobj.fileno(), 65536)
                if not chunk:
                    selector.unregister(key.fileobj)
                    if key.data == 1 and process.stdin in [k.fileobj for k in selector.get_map().values()]:
                        selector.unregister(process.stdin)
                    continue
                total += len(chunk)
                require(total <= 1048576, 'OUTPUT_LIMIT')
                streams[key.data].extend(chunk)
                if key.data == 2:
                    continue
                while b'\n' in streams[1]:
                    line, _, rest = streams[1].partition(b'\n')
                    streams[1] = bytearray(rest)
                    record = load_json(line)
                    require(type(record) is dict and type(record.get('kind')) is str, 'PIPE_SCHEMA')
                    if record['kind'] == 'model_request':
                        require(set(record) == {'kind', 'body'}, 'PIPE_SCHEMA')
                        global_deadline = relay.deadline
                        if child_started is not None:
                            relay.deadline = min(global_deadline, child_started + relay.child_seconds)
                        try:
                            response = relay.complete(record['body'])
                        finally:
                            relay.deadline = global_deadline
                        pending.extend(canonical(response) + b'\n')
                        require(len(pending) <= 1048576, 'INPUT_LIMIT')
                        if process.stdin not in [k.fileobj for k in selector.get_map().values()]:
                            selector.register(process.stdin, selectors.EVENT_WRITE, 0)
                    elif record['kind'] == 'event':
                        require(set(record) <= {'kind', 'event', 'tool', 'phase'} and
                                all(type(v) is str and len(v) <= 80 for v in record.values()), 'EVENT_SCHEMA')
                        events.append(record)
                        relay.event_sink(record)
                        require(len(events) <= 200, 'EVENT_LIMIT')
                        if record.get('event') == 'child_started':
                            require(child_started is None, 'CHILD_LIMIT')
                            child_started = time.monotonic()
                        if record.get('event') == 'child_finished':
                            require(child_started is not None, 'CHILD_NOT_STARTED')
                            child_started = None
                    elif record['kind'] == 'result':
                        require(result is None, 'DUPLICATE_RESULT')
                        result = record
                    else:
                        require(False, 'PIPE_SCHEMA')
            if process.poll() is not None and not selector.get_map():
                break
        require(not streams[1], 'PIPE_INCOMPLETE')
        process.wait(timeout=max(0.1, min(5, deadline - time.monotonic())))
        return {'exit': process.returncode, 'error': error, 'stdout': canonical(result),
                'stderr': bytes(streams[2]), 'events': events}
    except EvaluationError as failure:
        # Preserve bounded tool/child events even when the relay rejects a request.
        failure.protocol_events = list(events)
        raise
    except subprocess.TimeoutExpired:
        return {'exit': -1, 'error': 'TIMEOUT', 'stdout': b'null', 'stderr': b'', 'events': events}
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=5)
        for stream in (process.stdin, process.stdout, process.stderr):
            stream.close()
        selector.close()


class DelegationSandbox(SpikeSandbox):
    def __init__(self, *args, preparation=None, relay=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.preparation = Path(preparation).absolute()
        self.relay = relay
        self.phase = 'probe'

    def mounts(self, program):
        paths = [(program, '/input/program.py', False),
                 (self.preparation / 'requirements.lock', '/input/requirements.lock', False)]
        if self.phase in ('download', 'install'):
            paths.append((self.preparation / 'packages', '/prepare', True))
        else:
            paths.extend([(self.preparation / 'source', '/source', False),
                          (self.preparation / 'packages/site', '/deps', False),
                          (self.root / 'fixtures/self-evolution/hermes-agent', '/fixture/hermes-agent', False)])
        return paths

    def command(self, *args, **kwargs):
        if args and args[0] == 'start' and self.phase == 'probe' and self.relay is not None:
            return dialogue([self.binary, '--config', str(self.config), '--host', self.endpoint, *args],
                            env=self.env, data=kwargs.get('data', b'{}'),
                            timeout=kwargs.get('timeout', 30), relay=self.relay)
        return super().command(*args, **kwargs)
