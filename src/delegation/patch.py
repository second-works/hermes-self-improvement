"""Insertion-only counter repairs; proposed code is never executed on the host."""
import ast
from evaluation.core import require


def apply_counter_patch(source, proposal):
    require(type(proposal) is dict and set(proposal) == {'insertions'}, 'PATCH_SCHEMA')
    edits = proposal['insertions']
    require(type(edits) is list and 1 <= len(edits) <= 2, 'PATCH_SCHEMA')
    lines = source.splitlines(keepends=True)
    allowed = {}
    for number, line in enumerate(lines, 1):
        if line.strip() == "elif line.startswith('+'):":
            # Insert a sibling context branch immediately before the addition branch.
            allowed[number - 1] = "        elif line.startswith(' '):\n            current_line_num += 1\n"
        if line.strip() == "if content.startswith('#'):":
            allowed[number] = '                current_line_num += 1\n'
    require(len(allowed) == 2, 'PATCH_BASELINE_SCOPE')
    selected = {}
    for edit in edits:
        require(type(edit) is dict and set(edit) == {'after_line', 'text'}, 'PATCH_SCHEMA')
        line, text = edit['after_line'], edit['text']
        require(type(line) is int and line in allowed and line not in selected and
                type(text) is str and text == allowed[line], 'PATCH_OUTSIDE_SCOPE')
        selected[line] = text
    for number in sorted(selected, reverse=True):
        lines.insert(number, selected[number])
    result = ''.join(lines)
    ast.parse(result)
    return result


def counter_cases():
    samples = [(' context1\n context2\n+eval(data)', 9),
               ('-old(data)\n context\n+eval(data)', 8),
               ('+# comment\n+eval(data)', 8)]
    return [{'input': {'path': 'case_counter001.py', 'patch': '@@ -7,1 +7,3 @@\n' + text},
             'expected': [('case_counter001.py', line, 'dynamic-eval')]} for text, line in samples]


OPERATION_IDS = ('count_context_lines', 'count_added_comments')
CONTEXT_INSERTION = "        elif line.startswith(' '):\n            current_line_num += 1\n"
COMMENT_INSERTION = '                current_line_num += 1\n'


def apply_operations(source, value):
    require(type(value) is dict and set(value) == {'operations'} and type(value['operations']) is list and
            len(value['operations']) <= 2 and all(type(op) is str and op in OPERATION_IDS
                                                for op in value['operations']), 'OPERATION_SCHEMA')
    operations = value['operations']
    require(len(operations) == len(set(operations)), 'DUPLICATE_OPERATION')
    edits = []
    for operation in operations:
        if operation == 'count_context_lines':
            require(CONTEXT_INSERTION not in source, 'OPERATION_ALREADY_PRESENT')
            matches = [n - 1 for n, line in enumerate(source.splitlines(), 1)
                       if line.strip() == "elif line.startswith('+'):"]
            text = CONTEXT_INSERTION
        else:
            require("            if content.startswith('#'):\n" + COMMENT_INSERTION not in source,
                    'OPERATION_ALREADY_PRESENT')
            matches = [n for n, line in enumerate(source.splitlines(), 1)
                       if line.strip() == "if content.startswith('#'):"]
            text = COMMENT_INSERTION
        require(len(matches) == 1, 'OPERATION_ANCHOR')
        edits.append({'after_line': matches[0], 'text': text})
    return apply_counter_patch(source, {'insertions': edits}) if edits else source
