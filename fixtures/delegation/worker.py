"""Real upstream AIAgent inside network=none; pipe carries only bounded model messages."""
import contextlib
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import re
import stat
import sys
import threading
import time

wire_out, wire_in = sys.stdout, sys.stdin
payload = json.loads(wire_in.readline())
sys.stdout = sys.stderr
lock = threading.Lock()
seen = []
inventories = []
phase = payload['mode']
runtime_context = payload['runtime_context']
phase_seconds = payload.get('phase_seconds', 1100)
child_seconds = payload.get('child_seconds', 300)
phase_deadline = time.monotonic() + phase_seconds
child_started_at = None
child_done = threading.Event()
if type(phase_seconds) is not int or not 1 <= phase_seconds <= 3540 or type(child_seconds) is not int or not 300 <= child_seconds <= 1800:
    raise SystemExit(2)
if type(runtime_context) is not int or not 1 <= runtime_context <= 131072:
    raise SystemExit(2)


def emit(value):
    wire_out.write(json.dumps(value, separators=(',', ':')) + '\n')
    wire_out.flush()


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_GET(self):
        # Metadata only, fixed from controller's live identity check; never a model answer.
        if self.path != '/v1/models':
            self.send_error(404)
            return
        self.reply({'data': [{'id': 'gemma-4-e4b', 'meta': {'n_ctx': runtime_context}}]})

    def reply(self, value):
        data = json.dumps(value).encode()
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self):
        try:
            length = int(self.headers.get('Content-Length', '0'))
            if self.path != '/v1/chat/completions' or not 0 < length <= 262144:
                self.send_error(403)
                return
            body = json.loads(self.rfile.read(length))
            with lock:
                emit({'kind': 'model_request', 'body': body})
                response = json.loads(wire_in.readline(1048577))
            self.reply(response)
        except Exception:
            self.send_error(502)


def event(name, tool=''):
    if tool and not re.fullmatch(r'[a-z_]{1,60}', tool):
        raise RuntimeError('TOOL_NAME')
    seen.append((name, tool))
    emit({'kind': 'event', 'event': name, 'tool': tool, 'phase': phase})


def started(call_id, name, args):
    event('tool_started', name)


def completed(call_id, name, args, result):
    if payload.get('strict_reuse') and name == 'skill_view' and isinstance(args, dict) and args.get('file_path') == 'scripts/review.py':
        try:
            value = json.loads(result) if isinstance(result, str) else result
            if value.get('success') is True and value.get('content') == payload['files']['scripts/review.py']:
                event('script_viewed', 'skill_view')
        except (ValueError, TypeError, AttributeError):
            pass
    if name == 'skills_list':
        try:
            value = json.loads(result) if isinstance(result, str) else result
            if value.get('success') is True and type(value.get('skills')) is list:
                names = [row['name'] for row in value['skills']]
                if all(type(name) is str for name in names):
                    inventories.append(names)
        except (ValueError, TypeError, KeyError, AttributeError):
            pass


def progress(event_type, tool_name=None, preview=None, args=None, **kwargs):
    global child_started_at
    if event_type == 'subagent.start':
        child_started_at = time.monotonic()
        event('child_started')
    elif event_type == 'subagent.complete':
        event('child_finished')
        child_done.set()
    elif event_type == 'subagent.tool':
        event('child_tool', tool_name or '')


def wait_for_child():
    if child_started_at is None:
        raise RuntimeError('REAL_DELEGATION_UNVERIFIED')
    remaining = min(phase_deadline, child_started_at + child_seconds) - time.monotonic()
    if not child_done.is_set() and (remaining <= 0 or not child_done.wait(remaining)):
        raise RuntimeError('CHILD_TIMEOUT')


def read_artifacts(home):
    root = home / 'skills/delegated-patch-review'
    result = {}
    for rel in ('SKILL.md', 'scripts/review.py'):
        path = root / rel
        if any(p.is_symlink() for p in [root, *path.parents, path]):
            raise RuntimeError('CANDIDATE_SYMLINK')
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(fd, 'rb') as stream:
            info = os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode) or not 0 < info.st_size <= 65536:
                raise RuntimeError('CANDIDATE_SIZE')
            result[rel] = stream.read(65537).decode()
    files = {str(p.relative_to(root)) for p in root.rglob('*') if p.is_file()}
    if files != set(result):
        raise RuntimeError('CANDIDATE_EXTRA_FILES')
    return result


def main():
    home = Path('/run/work/home')
    home.mkdir(mode=0o700)
    for name in ('HOME', 'HERMES_HOME', 'CODEX_HOME'):
        os.environ[name] = str(home if name == 'HOME' else home / name.lower())
    profile = Path(os.environ['HERMES_HOME'])
    profile.mkdir()
    Path(os.environ['CODEX_HOME']).mkdir()
    config = {'model': {'provider': 'custom', 'default': 'gemma-4-e4b',
              'base_url': 'http://127.0.0.1:8917/v1', 'api_key': 'inert-local',
              'context_length': runtime_context, 'streaming': False},
              'agent': {'api_max_retries': 1, 'auto_recovery_cycles': 0},
              'delegation': {'oneshot_max_children': 1, 'max_concurrent_children': 1,
                             'max_spawn_depth': 1, 'max_iterations': 8,
                             'child_timeout_seconds': child_seconds,
                             'fallback_providers': [], 'inherit_mcp_toolsets': False},
              'fallback_providers': [], 'compression': {'enabled': False},
              'skills': {'external_dirs': [], 'write_approval': False},
              'memory': {'memory_enabled': False, 'user_profile_enabled': False},
              'auth': {'adopt_external_logins': False}}
    (profile / 'config.yaml').write_text(json.dumps(config))
    if phase in ('reuse', 'repair', 'propose_patch', 'select_operations'):
        for rel, text in payload['files'].items():
            if rel not in ('SKILL.md', 'scripts/review.py'):
                raise RuntimeError('CANDIDATE_PATH')
            path = profile / 'skills/delegated-patch-review' / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text)
    sys.path[:0] = ['/deps', '/source']
    from run_agent import AIAgent
    from agent.model_metadata import MINIMUM_CONTEXT_LENGTH
    if runtime_context < MINIMUM_CONTEXT_LENGTH:
        emit({'kind': 'result', 'status': 'STOPPED', 'reason': 'RUNTIME_CONTEXT_UNSUPPORTED',
              'runtime_context': runtime_context, 'required_context': MINIMUM_CONTEXT_LENGTH})
        raise SystemExit(1)
    server = ThreadingHTTPServer(('127.0.0.1', 8917), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    kwargs = dict(provider='custom', model='gemma-4-e4b', base_url='http://127.0.0.1:8917/v1',
                  api_key='inert-local', api_mode='chat_completions', max_tokens=4096,
                  max_iterations=4 if phase == 'reuse' else 8,
                  enabled_toolsets=['skills'] if phase in ('reuse', 'repair', 'propose_patch', 'select_operations', 'capability') else ['skills', 'delegation'],
                  skip_context_files=True, skip_memory=True, skip_background_review=True,
                  quiet_mode=True, save_trajectories=False, verbose_logging=False,
                  tool_start_callback=started, tool_complete_callback=completed, tool_progress_callback=progress,
                  run_budget_seconds=phase_seconds, cwd='/run/work',
                  ephemeral_system_prompt='Use only the provided tools. Do not claim an action succeeded without its tool result. No network, shell, installs or extra files.')
    agent = AIAgent(**kwargs)
    expected = {'skills_list', 'skill_view', 'skill_manage'}
    actual = set(agent.valid_tool_names)
    if not expected <= actual or actual - (expected | {'delegate_task'}):
        raise RuntimeError('TOOL_SURFACE')
    if phase == 'boot':
        emit({'kind': 'result', 'status': 'VERIFIED', 'tools': sorted(actual)})
        return
    if phase == 'capability':
        prompt = 'Call skills_list to inspect the available skills. Then give a brief final answer. You MUST actually call the tool.'
    elif phase == 'create':
        child_task = {
            'goal': 'Create delegated-patch-review using two real skill_manage calls and implement working Python patch detection.',
            'context': (
                'STEP 1: call skill_manage create for delegated-patch-review. Use the exact content value '
                'provided by the skill_manage tool schema, with real newline characters. '
                'STEP 2: call skill_manage write_file for delegated-patch-review, file_path scripts/review.py, '
                'and file_content containing your complete real Python implementation. '
                '\nSCRIPT REQUIREMENTS: Python standard library only. Read JSON {path,patch} from stdin. '
                'Parse unified diff hunk new-line numbers. Examine only added Python lines. '
                'Detect eval(...) as dynamic-eval and subprocess.run/call/Popen/check_call/check_output '
                'with shell=True as shell-execution. Ignore comments, deleted lines, and shell=False. '
                'PUBLIC feedback from the previous generated candidate: 4/6 cases passed; it wrongly flagged '
                'a comment and failed to advance the new-file line number for a context line. '
                'Use a single-pass diff state machine: a hunk header sets the new-file line counter; '
                'a context line advances it; a deletion does not; an addition is checked at the current '
                'counter then advances it. Header counts can be omitted. Skip file headers. '
                'Parse each added Python line with ast.parse where possible and inspect ast.Call nodes; '
                'comments and string contents are not executable calls. A leading comment must never be flagged. '
                'Print ONLY JSON {findings:[{path,line,rule}],cpu_seconds:0}. No command-line arguments, '
                'file reads, simulations, status messages, or extra files. '
                'After both actual operations succeed, report completion briefly.')}
        prompt = ('First call skills_list. Then call delegate_task with exactly this one task; '
                  'copy goal/context verbatim, do not summarize or change them: ' +
                  json.dumps({'tasks': [child_task]}) +
                  ' Wait for child completion. Do not create or modify skill files yourself.')
    elif phase == 'select_operations':
        prompt = ('Inspect the complete Python source below without tools. Choose ONLY the missing counter repairs. '
                  'Return JSON {"operations":[...]} using zero, one or two distinct operation IDs. '
                  'count_context_lines: ensures a diff context line starting with a space advances current_line_num. '
                  'count_added_comments: ensures an added Python comment advances current_line_num before continue. '
                  'An operation already implemented must NOT be selected. Return an empty list if neither is missing. '
                  'Do not produce code, line numbers, Markdown, or explanations. Source:\n' +
                  payload['files']['scripts/review.py'])
    elif phase == 'propose_patch':
        prompt = ('The complete verified source is provided below; use it directly without tools. Propose only insertions '
                  'to fix new-file line counting for context lines and added comments. Do not call any tool. '
                  'Return ONLY JSON {"insertions":[{"after_line":INTEGER,"text":STRING}]}, at most two entries. '
                  'Line numbers are one-based in the original file; after_line inserts after that original line. '
                  'Only two insertion forms are permitted: immediately BEFORE the addition elif branch, insert '
                  'a sibling elif line.startswith(\' \'): branch with current_line_num += 1, using 8 then 12 spaces. '
                  'Immediately after if content.startswith(\'#\'): insert current_line_num += 1 with 16 spaces. '
                  'Use real newline characters in each text. No deletions, replacements, regex edits, rule-name '
                  'edits, Markdown fences or explanations. Original file with line numbers follows:\n' +
                  '\n'.join(str(i) + ': ' + line for i, line in enumerate(payload['files']['scripts/review.py'].splitlines(), 1)))
        if payload.get('patch_attempt') == 2:
            prompt += ('\nPUBLIC validation feedback: the first proposal only inserted comments and was rejected '
                       'without application. Do NOT add comments or visualization text. Each permitted insertion '
                       'must execute current_line_num += 1. The direct-input first proposal also omitted the '
                       'closing JSON object brace. Return a complete valid JSON object, including the final }. '
                       'Do not insert continue statements. Use the exact indentation and branch forms described above.')
    elif phase == 'repair':
        if payload.get('target') not in ('comment', 'context_line'):
            raise RuntimeError('REPAIR_TARGET')
        feedback = ('The PUBLIC case +# eval(data) must produce no findings. Ignore Python comments.'
                    if payload['target'] == 'comment' else
                    'The PUBLIC patch @@ -7,1 +7,2 @@ followed by a context line and +eval(data) '
                    'must report dynamic-eval at new-file line8. Context lines advance the new-file counter.')
        prompt = ('Repair the EXISTING skill, do not regenerate or replace its design. '
                  'Use skill_view to read scripts/review.py for delegated-patch-review, then skill_manage '
                  'write_file to save the minimally changed script. Keep SKILL.md unchanged. '
                  'Fix ONLY this PUBLIC failure: ' + feedback +
                  ' Preserve stdin JSON path/patch and stdout findings/cpu_seconds, rule names '
                  'dynamic-eval/shell-execution, and all previously passing behavior. '
                  'After the actual write succeeds, finish briefly.')
    elif phase == 'reuse':
        prompt = ('Call skills_list, then skill_view(name="delegated-patch-review") to load the saved procedure. '
                  'Apply it to this NEW case and return ONLY JSON {findings:[{path,line,rule}],cpu_seconds:0}. '
                  'Do not modify the skill: ' + json.dumps(payload['case']))
    else:
        raise RuntimeError('MODE')
    if phase == 'reuse' and payload.get('strict_reuse'):
        prompt = ('First issue three tool calls together: skills_list, '
                  'skill_view(name="delegated-patch-review"), and '
                  'skill_view(name="delegated-patch-review", file_path="scripts/review.py"). '
                  'Read the actual saved script. Then return only a JSON object with findings and cpu_seconds. '
                  'Each finding must have exactly path, line, rule. The only permitted rule values are '
                  '"dynamic-eval" and "shell-execution", using the exact identifiers in the script. '
                  'cpu_seconds must be 0. No Markdown fences or prose. Do not modify any file. '
                  'Apply the saved script logic to this input: ' + json.dumps(payload['case']))
    outcome = agent.run_conversation(prompt)
    if not isinstance(outcome, dict) or outcome.get('completed') is not True:
        raise RuntimeError('HERMES_NOT_COMPLETED')
    if phase == 'capability' and ('tool_started', 'skills_list') not in seen:
        raise RuntimeError('TOOL_NOT_CALLED')
    result = {'kind': 'result', 'status': 'VERIFIED', 'api_calls': outcome.get('api_calls'),
              'final': outcome.get('final_response', '')}
    if phase in ('capability', 'create'):
        if not inventories or any(name.split('/')[-1] == 'delegated-patch-review' for name in inventories[0]):
            raise RuntimeError('SKILL_GAP_UNVERIFIED')
        result['initial_skill_names'] = inventories[0]
    if phase == 'create':
        # Top-level delegate_task may return before its real background child.
        # Keep the isolated worker alive; a parent final answer is not child completion.
        wait_for_child()
        if (('tool_started', 'delegate_task') not in seen or
                ('child_started', '') not in seen or ('child_finished', '') not in seen or
                ('child_tool', 'skill_manage') not in seen):
            raise RuntimeError('REAL_DELEGATION_UNVERIFIED')
        result['files'] = read_artifacts(profile)
    if phase == 'reuse':
        if not {('tool_started', 'skills_list'), ('tool_started', 'skill_view')} <= set(seen):
            raise RuntimeError('REUSE_TOOL_NOT_CALLED')
        if payload.get('strict_reuse') and ('script_viewed', 'skill_view') not in seen:
            raise RuntimeError('REUSE_SCRIPT_NOT_READ')
        if read_artifacts(profile) != payload['files']:
            raise RuntimeError('REUSE_MODIFIED')
    if phase == 'repair':
        if not {('tool_started', 'skill_view'), ('tool_started', 'skill_manage')} <= set(seen):
            raise RuntimeError('REPAIR_TOOLS_UNVERIFIED')
        result['files'] = read_artifacts(profile)
        if result['files']['SKILL.md'] != payload['files']['SKILL.md']:
            raise RuntimeError('REPAIR_METADATA_CHANGED')
    if phase in ('propose_patch', 'select_operations'):
        if any(name == 'tool_started' for name, _ in seen) or read_artifacts(profile) != payload['files']:
            raise RuntimeError('PATCH_READ_ONLY_UNVERIFIED')
        result['source_sha256'] = hashlib.sha256(payload['files']['scripts/review.py'].encode()).hexdigest()
    emit(result)


try:
    with contextlib.redirect_stdout(sys.stderr):
        main()
except Exception as error:
    import traceback
    traceback.print_exc(file=sys.stderr)  # Only PUBLIC synthetic input and an inert local key exist here.
    reason = str(error) if isinstance(error, RuntimeError) and re.fullmatch('[A-Z_]+', str(error)) else 'UPSTREAM_ERROR'
    extra = {}
    if isinstance(error, ModuleNotFoundError) and re.fullmatch('[a-zA-Z0-9_.]+', error.name or ''):
        extra['module'] = error.name
    emit({'kind': 'result', 'status': 'STOPPED', 'reason': reason,
          'error_type': type(error).__name__, **extra})
    raise SystemExit(1)
