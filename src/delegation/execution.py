"""Controller-owned execution: strict script JSON, never model-generated results."""
import re
from evaluation.core import canonical, findings, load_json, require


def execution_cases():
    return [
        {'input': {'path': 'case_cyclereuse00.py',
                   'patch': '@@ -21,1 +21,3 @@\n context\n+# note\n+eval(value)'},
         'expected': [('case_cyclereuse00.py', 23, 'dynamic-eval')]},
        {'input': {'path': 'case_batchshell01.py',
                   'patch': '@@ -1,1 +60,3 @@\n context\n+# note\n+subprocess.run(cmd, shell=True)'},
         'expected': [('case_batchshell01.py', 62, 'shell-execution')]},
    ]


def execute_case(unit, program, value):
    require(type(value) is dict and set(value) == {'path', 'patch'} and
            type(value['path']) is str and re.fullmatch(r'case_[a-z0-9]{8,32}\.py', value['path']) and
            type(value['patch']) is str and 0 < len(value['patch'].encode()) <= 16384, 'EXECUTION_INPUT')
    outcome = unit.run(program, canonical(value))
    require(not outcome['error'] and outcome['exit'] == 0 and not outcome['stderr'] and
            outcome['container_exit'] == 0, 'EXECUTION_FAILED')
    data = load_json(outcome['stdout'])
    rows, cpu = findings(data)
    require(cpu == 0 and all(path == value['path'] for path, _, _ in rows), 'EXECUTION_OUTPUT')
    # Serialize validated actual output. No expected answers or model prose enter this result.
    return {'findings': [{'path': path, 'line': line, 'rule': rule} for path, line, rule in rows],
            'cpu_seconds': 0}


def execute_batch(unit, program, values):
    require(type(values) is list and 1 <= len(values) <= 16, 'EXECUTION_BATCH_SIZE')
    return [execute_case(unit, program, value) for value in values]
