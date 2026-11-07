#!/usr/bin/env python3
"""Explicit network-none Docker acceptance with PUBLIC synthetic proposals, no model/auth."""
import json
from pathlib import Path
import sys
import time
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
sys.path.insert(0, str(ROOT / 'scripts'))
import evaluate_skill_candidate as controller
import run_public_hermes as runner
from evaluation.core import canonical, digest, require
from evaluation.profiles import COUNTS, REVIEW, profile
from delegation.generated import git
from intake_public_failure import failure_event_id


# Fixed PUBLIC comparison repairs based on the published contracts, not hidden answers.
REVIEW_REPAIR = '''import ast, json, re, sys, time
started = time.process_time()
case = json.load(sys.stdin)
chunks, current, line = [], [], 0
for text in case['patch'].splitlines():
    match = re.match(r'@@ -\\d+(?:,\\d+)? \\+(\\d+)(?:,\\d+)? @@', text)
    if match:
        if current: chunks.append(current)
        current, line = [], int(match[1])
    elif text.startswith('+++') or text.startswith('---'): continue
    elif text.startswith(('+', ' ')):
        current.append((line, text[1:], text.startswith('+'))); line += 1
if current: chunks.append(current)
rows = []
for chunk in chunks:
    try: tree = ast.parse('\\n'.join(row[1] for row in chunk))
    except SyntaxError: continue
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not chunk[node.lineno-1][2]: continue
        rule = None
        if isinstance(node.func, ast.Name) and node.func.id == 'eval': rule = 'dynamic-eval'
        if (isinstance(node.func, ast.Attribute) and isinstance(node.func.value, ast.Name)
                and node.func.value.id == 'subprocess' and node.func.attr in ('run','call','Popen','check_call','check_output')
                and any(k.arg == 'shell' and isinstance(k.value, ast.Constant) and k.value.value is True for k in node.keywords)):
            rule = 'shell-execution'
        if rule: rows.append({'path':case['path'], 'line':chunk[node.lineno-1][0], 'rule':rule})
print(json.dumps({'findings':rows, 'cpu_seconds':time.process_time()-started}))
'''


def edits(context):
    files = context['artifacts']
    if context['profile_id'] == 'review-multiline-shell-v1':
        return [{'path': REVIEW, 'before': files[REVIEW], 'after': REVIEW_REPAIR}]
    helper = COUNTS + 'scripts/helpers.py'
    main = COUNTS + 'scripts/aggregate.py'
    repaired_helper = files[helper].replace('        if identity in seen:\n            continue\n', '')
    pairs = '''def pairs(items):
    result = {}
    for key, value in items:
        if key in result: raise ValueError()
        result[key] = value
    return result

'''
    repaired_main = files[main].replace('try:\n', pairs + 'try:\n', 1).replace(
        'json.load(sys.stdin)', 'json.load(sys.stdin, object_pairs_hook=pairs)')
    return [{'path': p, 'before': files[p], 'after': text} for p, text in ((helper, repaired_helper), (main, repaired_main))]


def main():
    head = git(ROOT, 'rev-parse', 'HEAD').decode().strip()
    reports = []
    for index, name in enumerate(controller.PROFILES):
        check = time.time_ns() + index
        event = {'schema_version':1, 'status':'AWAITING_HUMAN_REVIEW', 'classification':'PUBLIC',
                 'source_kind':'public-github-check', 'repo':'second-works/hermes-self-improvement',
                 'event_id':failure_event_id(1000000+index,head,check), 'pr_number':1000000+index,
                 'pr_url':f'https://github.com/second-works/hermes-self-improvement/pull/{1000000+index}',
                 'head_sha':head, 'check_id':check, 'conclusion':'failure',
                 'snapshot_hash':digest(canonical(['PUBLIC_SYNTHETIC',check])),
                 'reproduction_sha256':digest(b'PUBLIC_SYNTHETIC_REPRODUCTION')}
        print(json.dumps({'phase':'PREPARE','profile':name,'model_calls':0}),flush=True)
        context = controller.prepare(event, name, controller.mapping_plan(event,name))
        prompt = runner.request_prompt(event,context)
        work = controller.gate.run_path(context['run_id'])
        approval = work/'synthetic-send-approval.json'
        approval.write_bytes(canonical({**runner.plan(event,prompt),'expires_at':int(time.time())+300}))
        approval.chmod(0o600)
        proposal = {'schema_version':1,'decision':'PROPOSE','reason':'PUBLIC synthetic contract comparison.',
                    'evidence_refs':['/reproduction_sha256'],'edits':edits(context)}
        fake = canonical({'status':'COMPLETED','requests':1,'tools':0,'text':json.dumps(proposal)})
        with patch.object(runner,'read_auth',return_value={'synthetic_only':True}), \
             patch('delegation.hermes_cloud.response',return_value=fake) as send:
            output = runner.execute(event,prompt,approval,ROOT/'runs/public-hermes',context_run=work.name)
            require(send.call_count==1,'SYNTHETIC_TRANSPORT_COUNT')
        print(json.dumps({'phase':'EVALUATE','profile':name,'model_calls':0}),flush=True)
        report = controller.evaluate(work.name,output)
        require(report['state']=='AWAITING_HUMAN_APPROVAL','PROFILE_ACCEPTANCE_'+report['state'])
        audit = controller.audit(work.name)
        memory = controller.gate.read(work,'profile-memory.json')
        require(audit['status']=='VERIFIED' and memory['approval']['status']=='PENDING'
                and memory['rollback']['status']=='NOT_REQUESTED','PROFILE_HANDOFF')
        reports.append({'profile':name,'run_id':work.name,'state':report['state'],
                        'report_hash':audit['report_hash'],'adoption':'NOT_REQUESTED'})
        print(json.dumps(reports[-1]),flush=True)
    print(json.dumps({'status':'VERIFIED','classification':'PUBLIC','mode':'OFFLINE_SYNTHETIC',
                      'model_calls':0,'auth_reads':0,'reports':reports}),flush=True)


if __name__=='__main__':
    main()
