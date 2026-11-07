#!/usr/bin/env python3
"""PUBLIC synthetic campaign: nine cold Hermes profiles, network hard-disabled."""
import base64
from copy import deepcopy
import json
from pathlib import Path
import sys
import time
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'));sys.path.insert(0,str(ROOT/'scripts'));sys.path.insert(0,str(ROOT/'tests'))
import evaluate_skill_candidate as controller
import evaluate_skill_semantics as semantic
import run_public_hermes as generation
import run_skill_profiles_docker as public_repairs
from delegation import hermes_cloud
from delegation.generated import git
from evaluation.core import canonical,digest,require
from intake_public_failure import failure_event_id


class OfflineSandbox(hermes_cloud.CloudSandbox):
    ids=[]

    def options(self,name,program):
        options=super().options(name,program)
        options[options.index('--network=bridge')]='--network=none'
        return options

    def verify_config(self,info,program):
        require(info['HostConfig']['NetworkMode']=='none','OFFLINE_NETWORK_REQUIRED')
        checked=deepcopy(info)
        # Production allows the fixed HTTPS transport. This test strengthens it to network-none.
        checked['HostConfig']['NetworkMode']='bridge'
        super().verify_config(checked,program)
        self.ids.append(info['Id'])


def synthetic_auth():
    encode=lambda v:base64.urlsafe_b64encode(canonical(v)).decode().rstrip('=')
    access=encode({'alg':'none'})+'.'+encode({'exp':int(time.time())+3600})+'.synthetic'
    return {'version':1,'active_provider':'openai-codex','providers':{'openai-codex':{
        'auth_mode':'chatgpt','tokens':{'access_token':access,'refresh_token':'synthetic-only'}}}}


def main():
    head=git(ROOT,'rev-parse','HEAD').decode().strip();check=time.time_ns()
    event={'schema_version':1,'status':'AWAITING_HUMAN_REVIEW','classification':'PUBLIC',
           'source_kind':'public-github-check','repo':'second-works/hermes-self-improvement',
           'pr_number':2000000,'pr_url':'https://github.com/second-works/hermes-self-improvement/pull/2000000',
           'head_sha':head,'check_id':check,'conclusion':'failure','snapshot_hash':digest(canonical(['PUBLIC_SYNTHETIC',check])),
           'event_id':failure_event_id(2000000,head,check),'reproduction_sha256':digest(b'PUBLIC_SYNTHETIC_REPRODUCTION')}
    print('PREPARE_PUBLIC_SYNTHETIC_PROFILE model_calls=0',flush=True)
    context=controller.prepare(event,'event-status-counts-v1',controller.mapping_plan(event,'event-status-counts-v1'))
    work=controller.gate.run_path(context['run_id'])
    edits=public_repairs.edits(context)
    skill=next(path for path in context['artifacts'] if path.endswith('/SKILL.md'))
    edits.append({'path':skill,'before':context['artifacts'][skill],
                  'after':context['artifacts'][skill]+'\nWhen tools are unavailable, count every event directly and return only strict JSON.\n'})
    proposal={'schema_version':1,'decision':'PROPOSE','reason':'PUBLIC synthetic code and procedure comparison.',
              'evidence_refs':['/reproduction_sha256'],'edits':edits}
    prompt=generation.request_prompt(event,context)
    approval=work/'synthetic-generation-approval.json'
    approval.write_bytes(canonical({**generation.plan(event,prompt),'expires_at':int(time.time())+600}));approval.chmod(0o600)
    simulated=canonical({'status':'COMPLETED','requests':1,'tools':0,'text':json.dumps(proposal)})
    with patch.object(generation,'read_auth',return_value=synthetic_auth()), \
         patch('delegation.hermes_cloud.response',return_value=simulated):
        generated=generation.execute(event,prompt,approval,ROOT/'runs/public-hermes',context_run=work.name)
    report=controller.evaluate(work.name,generated)
    require(report['state']=='HOLD' and report['decision']['reasons']==[
        'STRUCTURE_ONLY_SEMANTIC_EVALUATION_REQUIRED'],'STRUCTURE_ONLY_MUST_HOLD')
    plan=semantic.prepare(work.name,generated)['plan']
    target=semantic.area(event['event_id'])
    approval=target/'synthetic-evaluation-approval.json'
    approval.write_bytes(canonical({**plan,'expires_at':int(time.time())+900}));approval.chmod(0o600)
    original=hermes_cloud.response
    def offline(root,data,area,deadline,name):
        value=json.loads(data)
        require(value['offline_test'] is False,'PRODUCTION_MODE_ASSERTION')
        value['offline_test']=True
        print('COLD_OFFLINE_PROFILE '+name,flush=True)
        return original(root,canonical(value),area,deadline,name)
    print('NINE_COLD_OFFLINE_PROFILES model_calls=0 auth_reads=0',flush=True)
    with patch.object(generation,'read_auth',return_value=synthetic_auth()), \
         patch.object(hermes_cloud,'CloudSandbox',OfflineSandbox):
        result=semantic.run(event['event_id'],approval,transport=offline)
    require(result['state']!='AWAITING_HUMAN_APPROVAL','OFFLINE_MARKER_IS_NOT_SEMANTIC_SUCCESS')
    require(result['evaluation_attempts']==9 and len(OfflineSandbox.ids)==len(set(OfflineSandbox.ids))==9,
            'NINE_DISTINCT_PROFILES_REQUIRED')
    audit=semantic.audit(event['event_id'])
    require(audit['requests_reserved']==10,'BUDGET_MISMATCH')
    require(not (semantic.STATE/'pending.json').exists(),'PENDING_NOT_CLEARED')
    print(json.dumps({'status':'VERIFIED','mode':'PUBLIC_SYNTHETIC_OFFLINE','model_calls':0,'auth_reads':0,
        'network':'none','distinct_profiles':9,'requests_reserved':10,'semantic_state':result['state'],
        'event_id':event['event_id'],'source_run':work.name,'report_hash':audit['report_hash'],
        'adoption':'NOT_REQUESTED'}),flush=True)


if __name__=='__main__':main()
