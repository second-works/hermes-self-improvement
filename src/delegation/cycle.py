"""Controller-owned improvement acceptance and separate public transfer fixtures."""
from evaluation.core import require


def transfer_cases():
    # These fixtures are never included in the model's source-selection prompt.
    samples = [(41, ' first\n second\n+eval(value)', [(43, 'dynamic-eval')]),
               (13, '+# first\n+# second\n+eval(value)', [(15, 'dynamic-eval')]),
               (27, '-old(value)\n context\n+# note\n+subprocess.run(cmd, shell=True)',
                [(29, 'shell-execution')]),
               (52, '+# eval(value)\n+subprocess.run(cmd, shell=False)', []),
               (63, '+eval(a)\n context\n+eval(b)', [(63, 'dynamic-eval'), (65, 'dynamic-eval')]),
               (81, ' context\n+# note\n+subprocess.check_output(cmd, shell=True)',
                [(83, 'shell-execution')])]
    return [{'input': {'path': 'case_transfer' + str(n).zfill(4) + '.py',
                       'patch': '@@ -1,' + str(sum(line.startswith((' ', '-')) for line in patch.splitlines())) +
                                ' +' + str(start) + ',' + str(sum(line.startswith((' ', '+')) for line in patch.splitlines())) + ' @@\n' + patch},
             'expected': [('case_transfer' + str(n).zfill(4) + '.py', line, rule) for line, rule in findings]}
            for n, (start, patch, findings) in enumerate(samples)]


def acceptance(before, after, unchanged=False):
    require(type(before) is list and type(after) is list and len(before) == len(after) and
            len(before) > 0 and all(type(v) is bool for v in before + after), 'CYCLE_RESULTS')
    if unchanged:
        require(before == after, 'UNCHANGED_RESULTS_MISMATCH')
        return 'UNCHANGED'
    if any(old and not new for old, new in zip(before, after)):
        return 'REJECTED_REGRESSION'
    if not all(after):
        return 'REJECTED_INCOMPLETE'
    return 'ACCEPTED' if sum(after) > sum(before) else 'REJECTED_NO_IMPROVEMENT'
