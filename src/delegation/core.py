"""Controller-owned contracts. Candidate content is never executed here."""
import ast
import difflib
import re

from evaluation.core import canonical, digest, findings, require
from evaluation.core import load_json

UPSTREAM = '74e7a25c949625479487c009a2fd64d14d5b5c06'
MODEL = 'gemma-4-e4b'
IMAGE = 'sha256:eb7d16fec874f15b584063275012ac719885a2b87574d124c0da9c156d504629'
SKILL = 'delegated-patch-review'
FILES = ('SKILL.md', 'scripts/review.py')
TOOLS = frozenset({'skills_list', 'skill_view', 'skill_manage', 'delegate_task'})


def specification(budget_profile='standard'):
    require(budget_profile in ('standard', 'extended', 'extended60', 'extended80', 'patch88', 'matrix94', 'cycle100', 'controlled102'), 'BUDGET_PROFILE')
    multiplier = {'standard': 1, 'extended': 2, 'extended60': 3, 'extended80': 4, 'patch88': 4, 'matrix94': 4, 'cycle100': 4, 'controlled102': 4}[budget_profile]
    return {'schema_version': 1, 'classification': 'PUBLIC', 'skill': SKILL,
            'upstream_sha': UPSTREAM, 'model': MODEL, 'files': list(FILES),
            'contract': 'stdin JSON path/patch; stdout JSON findings/cpu_seconds; added lines only',
            'rules': ['dynamic-eval', 'shell-execution'],
            'budget': {'calls': {'patch88': 88, 'matrix94': 94, 'cycle100': 100, 'controlled102': 102}.get(budget_profile, 20 * multiplier),
                       'input_tokens': 100000 * multiplier, 'output_tokens': 20000 * multiplier,
                       'per_input': 16384, 'per_output': 4096, 'seconds': 1200,
                       'child_seconds': 300, 'candidate_count': 1, 'retry': 0, 'cost_usd': 0}}


def public_cases():
    """Small PUBLIC contract suite; never read or generate an evaluation hidden set."""
    samples = [('+eval(data)', [(7, 'dynamic-eval')]),
               ('+subprocess.run(cmd, shell=True)', [(7, 'shell-execution')]),
               ('+subprocess.run(cmd, shell=False)', []),
               ('+# eval(data)', []), ('-eval(data)\n+safe(data)', []),
               (' context\n+eval(data)', [(8, 'dynamic-eval')])]
    return [{'input': {'path': 'case_public00.py', 'patch': '@@ -7,1 +7,2 @@\n' + text},
             'expected': sorted([('case_public00.py', line, rule) for line, rule in expected])}
            for text, expected in samples]


def candidate_files(value):
    require(type(value) is dict and set(value) == set(FILES), 'CANDIDATE_PATHS')
    require(all(type(v) is str and 0 < len(v.encode()) <= 65536 for v in value.values()),
            'CANDIDATE_SIZE')
    markdown = value['SKILL.md']
    require(markdown.startswith('---\n') and '\n---\n' in markdown[4:], 'SKILL_FRONTMATTER')
    front, body = markdown[4:].split('\n---\n', 1)
    fields = {}
    for row in front.splitlines():
        require(':' in row, 'SKILL_FRONTMATTER')
        key, val = row.split(':', 1)
        require(key in ('name', 'description') and key not in fields, 'SKILL_METADATA')
        fields[key] = val.strip().strip('\"\'')
    require(set(fields) == {'name', 'description'} and fields['name'] == SKILL and
            1 <= len(fields['description']) <= 512 and len(body.strip()) > 30, 'SKILL_METADATA')
    # Reuse must not turn Markdown expansion or package preparation into arbitrary execution.
    require(not re.search(r'!\s*`|\{\{|\{%|(?im:^\s*(?:deps|env|hooks|requires|allowed-tools)\s*:)',
                          markdown), 'SKILL_ACTIVE_CONTENT')
    try:
        ast.parse(value['scripts/review.py'])
    except (SyntaxError, ValueError):
        require(False, 'CANDIDATE_SYNTAX')
    return {name: {'sha256': digest(text.encode()), 'bytes': len(text.encode())}
            for name, text in value.items()}


def handoff(value, baseline, *, baseline_sha, spec_hash, results):
    hashes = candidate_files(value)
    require(re.fullmatch('[a-f0-9]{40}', baseline_sha or ''), 'BASELINE_SHA')
    require(len(results) == len(public_cases()) and all(v is True for v in results), 'UNIT_FAILED')
    target = 'fixtures/skills/github-code-review/review.py'
    patch = ''.join(difflib.unified_diff(baseline.splitlines(True),
                    value['scripts/review.py'].splitlines(True), fromfile='a/' + target, tofile='b/' + target))
    require(bool(patch), 'UNCHANGED_CANDIDATE')
    return patch, {'schema_version': 1, 'classification': 'PUBLIC',
                   'status': 'PENDING_COMMIT', 'candidate_commit_sha': None,
                   'baseline_sha': baseline_sha, 'spec_hash': spec_hash,
                   'artifact_path': target, 'artifacts': hashes,
                   'diff_hash': digest(patch.encode()), 'public_cases': len(results),
                   'evaluation': 'NOT_RUN', 'adoption': 'NOT_REQUESTED'}


def correct_output(data, case):
    rows, _ = findings(data)
    return rows == [tuple(v) for v in case['expected']]


def bounded_tool(tool):
    """Advertise only the already-permitted subset of the real Hermes tools."""
    function = dict(tool['function'])
    name = function['name']
    def obj(properties):
        return {'type': 'object', 'properties': properties, 'required': list(properties),
                'additionalProperties': False}
    text = {'type': 'string'}
    skill = {'type': 'string', 'enum': [SKILL]}
    if name == 'skill_manage':
        markdown = ('---\nname: delegated-patch-review\ndescription: Detect unsafe added Python lines.\n---\n'
                    'Send one JSON object containing path and patch to python scripts/review.py on stdin; '
                    'read the findings JSON from stdout.\n')
        create = obj({'action': {'type': 'string', 'enum': ['create']}, 'name': skill,
                      'content': {'type': 'string', 'enum': [markdown]}})
        write = obj({'action': {'type': 'string', 'enum': ['write_file']}, 'name': skill,
                     'file_path': {'type': 'string', 'enum': ['scripts/review.py']}, 'file_content': text})
        function['description'] = 'Create the designated skill and write its script using the two permitted operation shapes.'
        function['parameters'] = obj({'operations': {'type': 'array', 'minItems': 1, 'maxItems': 2,
                                                    'items': {'anyOf': [create, write]}}})
    elif name == 'delegate_task':
        function['description'] = 'Delegate exactly one task, supplying its full goal and context.'
        function['parameters'] = obj({'tasks': {'type': 'array', 'minItems': 1, 'maxItems': 1,
                                               'items': obj({'goal': text, 'context': text})}})
    return {**tool, 'function': function}


def request_body(value):
    require(type(value) is dict and len(canonical(value)) <= 262144, 'REQUEST_SIZE')
    allowed = {'model', 'messages', 'tools', 'tool_choice', 'stream', 'max_tokens',
               'max_completion_tokens', 'temperature', 'top_p', 'parallel_tool_calls', 'seed',
               'reasoning_effort'}
    require(set(value) <= allowed and value.get('model') == MODEL and
            value.get('stream', False) is False, 'REQUEST_SCHEMA')
    if 'reasoning_effort' in value:
        require(value['reasoning_effort'] == 'medium', 'REASONING_SCHEMA')
    require(type(value.get('messages')) is list and 0 < len(value['messages']) <= 64, 'MESSAGES')
    for row in value['messages']:
        require(type(row) is dict and row.get('role') in ('system', 'developer', 'user', 'assistant', 'tool'),
                'MESSAGE_ROLE')
        require(type(row.get('content')) is str or row.get('content') is None, 'TEXT_ONLY')
    for tool in value.get('tools', []):
        require(type(tool) is dict and tool.get('type') == 'function' and
                tool.get('function', {}).get('name') in TOOLS, 'TOOL_ALLOWLIST')
    output = value.get('max_tokens', value.get('max_completion_tokens', 4096))
    require(type(output) is int and 1 <= output <= 4096, 'OUTPUT_BUDGET')
    body = dict(value)
    if 'tools' in body:
        body['tools'] = [bounded_tool(tool) for tool in body['tools']]
    body.pop('max_completion_tokens', None)
    body.update(max_tokens=output, stream=False)
    return body


def safe_tool_calls(result, *, reuse=False):
    """Reject active Markdown BEFORE Hermes executes a model-selected skill write/view."""
    calls = result['choices'][0].get('message', {}).get('tool_calls', [])
    require(type(calls) is list and len(calls) <= 4, 'TOOL_CALL_SCHEMA')
    spawns = 0
    for call in calls:
        function = call.get('function', {})
        name = function.get('name')
        require(name in TOOLS, 'TOOL_ALLOWLIST')
        args = function.get('arguments')
        require(type(args) is str, 'TOOL_ARGUMENTS')
        args = load_json(args)
        require(type(args) is dict, 'TOOL_ARGUMENTS')
        if name == 'delegate_task':
            require(not reuse and args.get('action', 'spawn') == 'spawn', 'CHILD_LIMIT')
            tasks = args.get('tasks')
            require(type(tasks) is list and len(tasks) == 1 and type(tasks[0]) is dict and
                    set(tasks[0]) == {'goal', 'context'} and
                    all(type(tasks[0][key]) is str and tasks[0][key].strip() for key in ('goal', 'context')),
                    'DELEGATE_TASK_SCHEMA')
            spawns += 1
        elif name == 'skill_view':
            require(args.get('name') == SKILL and args.get('file_path') in (None, 'scripts/review.py'),
                    'SKILL_VIEW_BOUNDARY')
        elif name == 'skill_manage':
            require(not reuse, 'REUSE_WRITE')
            operations = args.get('operations', [args])
            require(type(operations) is list and 1 <= len(operations) <= 2, 'WRITE_OPERATIONS')
            for operation in operations:
                require(type(operation) is dict and operation.get('name') == SKILL, 'SKILL_WRITE_BOUNDARY')
                if operation.get('action') == 'create':
                    require(set(operation) == {'action', 'name', 'content'}, 'SKILL_WRITE_BOUNDARY')
                    candidate_files({'SKILL.md': operation['content'], 'scripts/review.py': 'pass\n'})
                else:
                    require(set(operation) == {'action', 'name', 'file_path', 'file_content'} and
                            operation['action'] == 'write_file' and operation['file_path'] == 'scripts/review.py',
                            'SKILL_WRITE_BOUNDARY')
                    candidate_files({'SKILL.md': '---\nname: ' + SKILL + '\ndescription: Test\n---\n' +
                                     'Use this procedure for the bounded public patch review task.',
                                     'scripts/review.py': operation['file_content']})
    return spawns
