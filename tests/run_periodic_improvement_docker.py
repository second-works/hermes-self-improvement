#!/usr/bin/env python3
"""Explicit isolated integration: synthetic inspection to nine network-none Hermes profiles."""
from copy import deepcopy
from datetime import datetime
import json
from pathlib import Path
import sys
import time
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'));sys.path.insert(0,str(ROOT/'scripts'));sys.path.insert(0,str(ROOT/'tests'))
import periodic_improvement as runner
import run_skill_profiles_docker as repairs
from run_semantic_budget_docker import OfflineSandbox,synthetic_auth
from test_github_work_guide import change
from delegation import hermes_cloud
from delegation.generated import git
from evaluation.core import canonical,digest,require,load_json,regular
from evaluation.semantic import ROLES
from github_work_guide.core import save_run,REPO
from extract_public_failure import PREFIX
from intake_public_failure import intake
from bind_public_reproduction import BINDING


def private(path,value):
    path.write_bytes(canonical(value));path.chmod(0o600)


class SyntheticGitHub:
    def __init__(self,snapshot):
        self.item=snapshot['items']['pr:25']
    def get(self,path,page,timeout):
        if path==PREFIX:return {'full_name':REPO,'private':False,'visibility':'public'}
        if path==PREFIX+'/pulls/25':return self.item['raw']['detail']
        require(path==PREFIX+'/commits/'+self.item['raw']['detail']['head']['sha']+'/check-runs',
                'UNEXPECTED_SYNTHETIC_ROUTE')
        checks=self.item['raw']['checks']
        return {'total_count':len(checks),'check_runs':checks}


def verify_offline_verdict(final, report):
    """The fixed marker may be held or rejected for latency, never semantically accepted."""
    require(type(final) is dict and type(report) is dict, 'SYNTHETIC_RESULT_SCHEMA')
    state = final.get('status')
    require(state in ('HOLD', 'REJECTED') and report.get('state') == state,
            'SYNTHETIC_MARKER_MUST_NOT_PASS')
    require(type(report.get('evaluation_attempts')) is int and report['evaluation_attempts'] == 9
            and type(report.get('generation_requests_consumed')) is int
            and report['generation_requests_consumed'] == 1, 'NINE_COMPLETED_TRIALS_REQUIRED')
    counts = report.get('counts')
    require(type(counts) is dict and set(counts) == set(ROLES)
            and all(type(counts[r]) is int and counts[r] == 0 for r in ROLES)
            and report.get('control_valid') is True, 'SYNTHETIC_MARKER_COUNTS_OR_CONTROL')
    expected = ({'status': 'HOLD', 'reasons': ['INSUFFICIENT_GAIN']} if state == 'HOLD' else
                {'status': 'FAIL', 'reasons': ['LATENCY_LIMIT', 'INSUFFICIENT_GAIN']})
    require(report.get('decision') == expected, 'UNEXPECTED_SYNTHETIC_VERDICT')


def main():
    head=git(ROOT,'rev-parse','HEAD').decode().strip()
    snapshot=json.loads((ROOT/'fixtures/github_work_guide/synthetic.json').read_text())
    def failed(item):
        item['body']=item['raw']['detail']['body']='PUBLIC_SYNTHETIC_OFFLINE_ONLY'
        item['raw']['detail']['head']['sha']=head
        for check in item['raw']['checks']:check['head_sha']=head
        item['raw']['checks'][0].update(conclusion='failure',id=time.time_ns())
    snapshot=change(snapshot,'pr:25',failed)
    run=ROOT/'runs'/datetime.now().strftime('periodic-%Y%m%d-%H%M')
    run.parent.mkdir(exist_ok=True);save_run(run,{'snapshot.json':snapshot})
    transport=SyntheticGitHub(snapshot)
    runner.prepare_state(runner.STATE)
    private(runner.STATE/'config.json',{'schema_version':1,'enabled':True})
    evidence=runner.STATE/'reproductions';evidence.mkdir()
    entry=intake(run,25,transport)
    entry.update(status='AWAITING_HUMAN_REVIEW',reproduction_sha256=digest(b'PUBLIC_SYNTHETIC_REPRODUCTION'))
    private(evidence/(entry['event_id']+'.json'),{'schema_version':1,'observed':'FAIL','expected':'PASS',
            'reproduction_sha256':entry['reproduction_sha256'],**{k:entry[k] for k in BINDING}})
    def dispatch():return runner.dispatch(run,transport=transport)
    print('SYNTHETIC_PERIODIC_HANDOFF model_calls=0 auth_reads=0',flush=True)
    require(dispatch()['status']=='AWAITING_MAPPING','MAPPING_MUST_BE_APPROVED')
    job=runner.STATE/'events'/entry['event_id']
    private(job/'mapping.json',runner.profiles.mapping_plan(entry,'event-status-counts-v1'))
    require(dispatch()['status']=='AWAITING_GENERATION_APPROVAL','GENERATION_MUST_BE_APPROVED')
    context=json.loads((job/'prepare.json').read_text())
    edits=repairs.edits(context)
    skill=next(path for path in context['artifacts'] if path.endswith('/SKILL.md'))
    edits.append({'path':skill,'before':context['artifacts'][skill],
                  'after':context['artifacts'][skill]+'\nWithout tools, count every event directly. Return strict JSON only.\n'})
    proposal={'schema_version':1,'decision':'PROPOSE','reason':'PUBLIC synthetic integration.',
              'evidence_refs':['/reproduction_sha256'],'edits':edits}
    plan=json.loads((job/'generation-plan.json').read_text())
    private(job/'generation-approval.json',{**plan,'expires_at':int(time.time())+600})
    response=canonical({'status':'COMPLETED','requests':1,'tools':0,'text':json.dumps(proposal)})
    with patch.object(runner.generation,'read_auth',return_value=synthetic_auth()), \
         patch.object(hermes_cloud,'response',return_value=response) as generation:
        result=dispatch()
    require(result['status']=='AWAITING_SEMANTIC_APPROVAL' and generation.call_count==1,
            'SEPARATE_SEMANTIC_APPROVAL_REQUIRED')
    plan=runner.semantic.send_plan(entry['event_id'])['plan']
    private(job/'semantic-approval.json',{**plan,'expires_at':int(time.time())+900})
    original=hermes_cloud.response
    def offline(root,data,area,deadline,name):
        value=json.loads(data);require(value['offline_test'] is False,'PRODUCTION_MODE_REQUIRED')
        value['offline_test']=True
        print('COLD_OFFLINE_PROFILE '+name,flush=True)
        return original(root,canonical(value),area,deadline,name)
    with patch.object(runner.generation,'read_auth',return_value=synthetic_auth()), \
         patch.object(hermes_cloud,'CloudSandbox',OfflineSandbox),patch.object(hermes_cloud,'response',side_effect=offline):
        final=dispatch()
    report=load_json(regular(runner.semantic.area(entry['event_id'])/'report.json',runner.semantic.STATE))
    verify_offline_verdict(final,report)
    require(len(OfflineSandbox.ids)==len(set(OfflineSandbox.ids))==9,'NINE_INDEPENDENT_PROFILES')
    with patch.object(runner.generation,'read_auth',side_effect=AssertionError('must not resend')):
        require(dispatch()==final,'RESTART_MUST_NOT_RESEND')
        require(runner.control_intake(ROOT/'runs/public-hermes','stop')=='INTAKE_STOPPED','STOP_FAILED')
        require(dispatch()['reason']=='INTAKE_STOPPED','STOP_NOT_PERSISTENT')
        require(runner.control_intake(ROOT/'runs/public-hermes','resume')=='ACCEPTING','RESUME_FAILED')
        require(dispatch()==final,'RESUME_MUST_NOT_RESEND')
    require(runner.inspection(run)['hash']==snapshot['hash'],'INSPECTION_NOT_PRESERVED')
    audit=runner.semantic.audit(entry['event_id'])
    require(audit['requests_reserved']==10,'BUDGET_MISMATCH')
    print(json.dumps({'status':'VERIFIED','mode':'PUBLIC_SYNTHETIC_OFFLINE','model_calls':0,'auth_reads':0,
        'network':'none','distinct_profiles':9,'requests_reserved':10,'final':final,
        'inspection_preserved':True,'restart_stop_resume_no_resend':True,'head':head,
        'semantic_state':report['state'],'semantic_decision':report['decision'],
        'adoption':'NOT_REQUESTED'}),flush=True)


if __name__=='__main__':main()
