"""Synthetic unified-patch reviewer; finite fixture only, not a production reviewer."""
import json
import re
import sys
import time

started = time.process_time()
case = json.load(sys.stdin)
rows = []
line = 0
for text in case['patch'].splitlines():
    match = re.match(r'@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@', text)
    if match:
        line = int(match[1])
    elif text.startswith('+++') or text.startswith('---'):
        continue
    elif text.startswith('+'):
        if re.search(r'\beval\s*\(', text[1:]) and not text[1:].lstrip().startswith('#'):
            rows.append({'path': case['path'], 'line': line, 'rule': 'dynamic-eval'})
        if (re.search(r'\bsubprocess\.(?:run|call|Popen|check_call|check_output)\s*\(.*\bshell\s*=\s*True\b', text[1:])
                and not text[1:].lstrip().startswith('#')):
            rows.append({'path': case['path'], 'line': line, 'rule': 'shell-execution'})
        line += 1
    elif text.startswith(' '):
        line += 1
print(json.dumps({'findings': rows, 'cpu_seconds': time.process_time() - started}))
