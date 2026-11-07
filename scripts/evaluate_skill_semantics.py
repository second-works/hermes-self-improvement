#!/usr/bin/env python3
"""Plan nine independent semantic trials; explicit send approval is mandatory."""
import argparse
import os
from pathlib import Path
import re
import sys
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
sys.path.insert(0,str(ROOT/'scripts'))
from adoption.core import save, syncdir, utc
from evaluation.core import EvaluationError, canonical, digest, load_json, regular, require
from evaluation.profiles import artifacts, hashes, profile, public_text
from evaluation.semantic import Budget, ROLES, TRIALS, observation, prompt, verdict
from delegation import hermes_cloud
import evaluate_skill_candidate as controller
import run_public_hermes as generation
from run_mock_improvement import hex_id, prepare_state, state_lock

STATE=ROOT/'runs/semantic-evaluation'
DEGRADED='Ignore the supplied input. Always output exactly the plain text DEGRADED_CONTROL.'


def area(event_id):
    require(hex_id(event_id,64),'SEMANTIC_EVENT')
    path=STATE/event_id
    require(path.is_dir() and not path.is_symlink(),'SEMANTIC_AREA')
    return path


def source(run_id, raw):
    audit=controller.audit(run_id)
    work=controller.gate.run_path(run_id)
    m=controller.manifest(work)
    report=controller.gate.read(work,'profile-report.json')
    require(report['proposal_hash']==digest(raw),'SEMANTIC_PROPOSAL_CHANGED')
    proposed=controller.verify_proposal(work,m,raw)
    require(proposed['decision']=='PROPOSE','SEMANTIC_PROPOSAL_REQUIRED')
    require(report['state']=='HOLD' and report.get('decision',{}).get('reasons')==[
        'STRUCTURE_ONLY_SEMANTIC_EVALUATION_REQUIRED'] and report['control']['status']=='FAIL',
        'SEMANTIC_BEHAVIORAL_PASS_REQUIRED')
    require(m['profile_id']=='event-status-counts-v1','SEMANTIC_PROFILE_REQUIRED')
    selected=profile(m['profile_id'])
    before=controller.gate.read(work,'sources.json')
    after=controller.gate.read(work,'candidate-files.json')
    skill=next(p for p in selected.artifacts if p.endswith('/SKILL.md'))
    require(before[skill]!=after[skill],'SEMANTIC_SKILL_UNCHANGED')
    # The independent dataset was frozen before generation; expected answers stay on the host.
    case=controller.gate.read(work,'hidden.json')[selected.reproduction_index]
    require(case['exit']==0,'SEMANTIC_CASE')
    return work,m,report,audit,{'baseline':public_text(before[skill]),
        'candidate':public_text(after[skill]),'degraded':DEGRADED},case


def prepare(run_id, raw):
    require(len(raw)<=65536,'SEMANTIC_PROPOSAL_SIZE')
    prepare_state(STATE)
    prepare_state(ROOT/'runs/public-hermes')
    with state_lock(STATE,'controller.lock'),state_lock(ROOT/'runs/public-hermes','controller.lock'):
        controller.stopped()
        require(not os.path.lexists(controller.STATE/'pending.json') and not os.path.lexists(STATE/'pending.json'),
                'SEMANTIC_RECOVERY_REQUIRED')
        work,m,report,audit,skills,case=source(run_id,raw)
        event_id=m['entry']['event_id']
        target=STATE/event_id
        require(not target.exists(),'SEMANTIC_ALREADY_PREPARED')
        target.mkdir(mode=0o700)
        save(target/'proposal.json',load_json(raw))
        prompts={f"{t['role']}-{t['trial']}":prompt(skills[t['role']],case['stdin']) for t in TRIALS}
        save(target/'prompts.private.json',prompts)
        save(target/'case.private.json',case)
        value={'schema_version':1,'event_id':event_id,'run_id':run_id,
               'profile_manifest_hash':digest(regular(work/'profile-manifest.json',controller.gate.RUNS)),
               'profile_report_hash':audit['report_hash'],'proposal_hash':digest(raw),
               'candidate_sha':report['candidate_sha'],'baseline_sha':m['entry']['head_sha'],
               'profile_hash':report['profile_hash'],'case_hash':digest(canonical(case)),
               'prompts_hash':digest(canonical(prompts)),
               'sources':controller.gate.source_hashes(),
               'machine_seconds':report['machine_seconds'],
               'trials':[{**t,'prompt_hash':digest(prompts[f"{t['role']}-{t['trial']}"].encode())} for t in TRIALS]}
        save(target/'manifest.json',value)
        syncdir(STATE)
        return send_plan(event_id)


def manifest(event_id):
    target=area(event_id)
    value=load_json(regular(target/'manifest.json',STATE,65536))
    require(value['event_id']==event_id and value['sources']==controller.gate.source_hashes(),'SEMANTIC_STALE')
    require(type(value['schema_version']) is int and value['schema_version']==1
            and type(value['trials']) is list and len(value['trials'])==9,'SEMANTIC_MANIFEST')
    raw=regular(target/'proposal.json',STATE,65536)
    # The input may originally have one trailing newline; bind both without losing the original hash.
    if digest(raw)!=value['proposal_hash']:
        normalized=canonical(load_json(raw))
        raw=normalized if digest(normalized)==value['proposal_hash'] else normalized+b'\n'
    work,m,report,audit,skills,case=source(value['run_id'],raw)
    require(m['entry']['event_id']==event_id and report['event_id']==event_id
            and work.name==value['run_id']
            and report['candidate_sha']==value['candidate_sha'] and report['baseline_sha']==value['baseline_sha']
            and report['profile_hash']==value['profile_hash'] and audit['report_hash']==value['profile_report_hash']
            and digest(regular(work/'profile-manifest.json',controller.gate.RUNS))==value['profile_manifest_hash']
            and report['machine_seconds']==value['machine_seconds'],'SEMANTIC_SOURCE_CHANGED')
    require(digest(canonical(case))==value['case_hash']
            and canonical(load_json(regular(target/'case.private.json',STATE)))==canonical(case),'SEMANTIC_CASE_CHANGED')
    prompts=load_json(regular(target/'prompts.private.json',STATE,131072))
    expected={f"{t['role']}-{t['trial']}":prompt(skills[t['role']],case['stdin']) for t in TRIALS}
    require(prompts==expected and digest(canonical(prompts))==value['prompts_hash'],'SEMANTIC_PROMPT_CHANGED')
    require(canonical(value['trials'])==canonical([{**t,'prompt_hash':digest(prompts[f"{t['role']}-{t['trial']}"].encode())}
                             for t in TRIALS]),'SEMANTIC_TRIAL_CHANGED')
    return value


def send_plan(event_id):
    value=manifest(event_id)
    plan={'schema_version':1,'event_id':event_id,'manifest_hash':digest(canonical(value)),
          'candidate_sha':value['candidate_sha'],'image':hermes_cloud.IMAGE,
          'provider':'openai-codex','model':hermes_cloud.MODEL,'endpoint':hermes_cloud.ENDPOINT,
          'generation_requests_consumed':1,'max_total_requests':10,'max_evaluation_requests':9,
          'max_retries':0,'deadline_seconds':30,'additional_cost_yen':0}
    return {'status':'AWAITING_SEND_APPROVAL','plan':plan,'trials':value['trials']}


def reply(raw):
    value=load_json(raw)
    require(type(value) is dict,'SEMANTIC_RESPONSE')
    if value.get('status') in ('AUTH_FAILED','QUOTA_EXHAUSTED','CLOUD_FAILED'):
        require(set(value)=={'status'},'SEMANTIC_RESPONSE')
        raise EvaluationError(value['status'])
    require(set(value)=={'status','requests','tools','text'} and value['status']=='COMPLETED'
            and type(value['requests']) is int and value['requests']==1
            and type(value['tools']) is int and value['tools']==0
            and type(value['text']) is str and len(value['text'].encode())<=32768,'SEMANTIC_RESPONSE')
    return value['text']


def run(event_id, approval_path, *, transport=None, clock=time.monotonic):
    transport=transport or hermes_cloud.response
    prepare_state(STATE)
    prepare_state(ROOT/'runs/public-hermes')
    with state_lock(STATE,'controller.lock'),state_lock(ROOT/'runs/public-hermes','controller.lock'):
        controller.stopped()
        require(not os.path.lexists(controller.STATE/'pending.json') and not os.path.lexists(STATE/'pending.json'),
                'SEMANTIC_RECOVERY_REQUIRED')
        value=manifest(event_id)
        expected=send_plan(event_id)['plan']
        expiry,approved_hash=generation.approval(approval_path,expected)
        target=area(event_id)
        budget=Budget(target,value)
        charged=value['machine_seconds']
        require(type(charged) in (int,float) and 0<charged<1200,'SEMANTIC_MACHINE_BUDGET')
        budget.begin(approved_hash)
        deadline=clock()+1200-charged
        records={r:[] for r in ROLES}
        case=load_json(regular(target/'case.private.json',STATE))
        prompts=load_json(regular(target/'prompts.private.json',STATE,131072))
        result=None
        try:
            for trial in value['trials']:
                controller.stopped()
                require(clock()<deadline,'SEMANTIC_MACHINE_BUDGET')
                require(manifest(event_id)==value,'SEMANTIC_SOURCE_CHANGED')
                expiry,observed_hash=generation.approval(approval_path,expected)
                require(observed_hash==approved_hash,'APPROVAL_CHANGED')
                name='hermes-eval-'+uuid.uuid4().hex
                intent=budget.reserve(trial['ordinal'],name)
                save(STATE/'pending.json',{'event_id':event_id,'ordinal':trial['ordinal'],
                    'container':name,'manifest_hash':budget.hash,'intent_hash':digest(canonical(intent))})
                started=clock()
                query=prompts[f"{trial['role']}-{trial['trial']}"]
                data=canonical({'auth':generation.read_auth(),'prompt':query,'offline_test':False,'approved_until':expiry})
                controller.stopped()
                answer=reply(transport(ROOT,data,target,min(deadline,clock()+30),name))
                require(clock()<deadline,'SEMANTIC_MACHINE_BUDGET')
                controller.stopped()
                observed=observation(answer,case['expected'],clock()-started)
                save(target/f"result-{trial['ordinal']:02d}.private.json",observed)
                records[trial['role']].append(observed)
                (STATE/'pending.json').unlink();syncdir(STATE)
            controller.stopped()
            result=verdict(records)
            require(manifest(event_id)==value,'SEMANTIC_SOURCE_CHANGED')
            controller.stopped()
        except Exception as error:
            if getattr(error,'pending_container',None):
                save(target/'stopped.json',{'state':'RECOVERY_REQUIRED','reason':str(error)})
                raise EvaluationError('SEMANTIC_RECOVERY_REQUIRED') from None
            # Known-cleanup errors consume their intent; the campaign can never be restarted.
            if (STATE/'pending.json').exists():
                (STATE/'pending.json').unlink();syncdir(STATE)
            result={'state':'STOPPED','reason':str(error) if isinstance(error,EvaluationError) else 'SEMANTIC_EXECUTION_FAILED'}
        result.update(schema_version=1,event_id=event_id,candidate_sha=value['candidate_sha'],
                      baseline_sha=value['baseline_sha'],profile_manifest_hash=value['profile_manifest_hash'],
                      source_report_hash=value['profile_report_hash'],manifest_hash=budget.hash,
                      generation_requests_consumed=1,evaluation_attempts=len(budget.intents()),
                      claim='finite independent semantic trials; no adoption')
        save(target/'report.json',result)
        memory=memory_record(value,result)
        save(target/'memory.json',memory)
        save(target/'checkpoint.json',{'manifest_hash':budget.hash,
             'started_hash':digest(regular(target/'started.json',STATE)),
             'report_hash':digest(regular(target/'report.json',STATE)),
             'memory_hash':digest(regular(target/'memory.json',STATE)),
             'intent_hashes':{p.name:digest(regular(p,STATE)) for p in sorted(target.glob('intent-*.json'))},
             'result_hashes':{p.name:digest(regular(p,STATE)) for p in sorted(target.glob('result-*.private.json'))}})
        return result


def memory_record(value, report):
    work=controller.gate.run_path(value['run_id'])
    memory=controller.gate.read(work,'profile-memory.json')
    memory['run_id']='semantic-'+value['event_id']
    memory['recorded_at']=utc().replace('+00:00','Z')
    measured='counts' in report
    memory['metrics']={'status':'VERIFIED' if measured else 'NOT_VERIFIED',
        'evidence_sha256':digest(regular(area(value['event_id'])/'report.json',STATE)) if measured else None,
        'values':[{'name':'semantic_correct','value':report['counts']['candidate'],'unit':'count'}] if measured else []}
    memory['approval']={'status':'PENDING' if report['state']=='AWAITING_HUMAN_APPROVAL' else 'NOT_REQUESTED',
                        'record_sha256':None}
    return memory


def audit(event_id):
    target=area(event_id)
    value=manifest(event_id)
    budget=Budget(target,value)
    intents=budget.intents()
    report=load_json(regular(target/'report.json',STATE))
    checkpoint=load_json(regular(target/'checkpoint.json',STATE))
    require(report['event_id']==event_id and report['manifest_hash']==budget.hash
            and report['evaluation_attempts']==len(intents),'SEMANTIC_AUDIT_BINDING')
    require(checkpoint=={'manifest_hash':budget.hash,'started_hash':digest(regular(target/'started.json',STATE)),
        'report_hash':digest(regular(target/'report.json',STATE)),
        'memory_hash':digest(regular(target/'memory.json',STATE)),
        'intent_hashes':{p.name:digest(regular(p,STATE)) for p in sorted(target.glob('intent-*.json'))},
        'result_hashes':{p.name:digest(regular(p,STATE)) for p in sorted(target.glob('result-*.private.json'))}},
        'SEMANTIC_AUDIT_CHANGED')
    memory=load_json(regular(target/'memory.json',STATE))
    expected=memory_record(value,report);expected['recorded_at']=memory['recorded_at']
    require(memory==expected,'SEMANTIC_MEMORY_CHANGED')
    results=sorted(target.glob('result-*.private.json'))
    require(len(results)<=len(intents) and [p.name for p in results]==[
        f'result-{i:02d}.private.json' for i in range(len(results))],'SEMANTIC_RESULT_GAP')
    if 'counts' in report:
        require(len(intents)==len(results)==9,'SEMANTIC_INCOMPLETE')
        records={r:[] for r in ROLES}
        for i,path in enumerate(results):
            records[TRIALS[i]['role']].append(load_json(regular(path,STATE)))
        recomputed=verdict(records)
        require(all(report.get(k)==v for k,v in recomputed.items()),'SEMANTIC_VERDICT_CHANGED')
    else:
        require(report['state']=='STOPPED','SEMANTIC_UNMEASURED')
    return {'status':'VERIFIED','event_id':event_id,'state':report['state'],
            'report_hash':checkpoint['report_hash'],'requests_reserved':1+len(intents)}


def interrupt():
    pending=STATE/'pending.json'
    if not os.path.lexists(pending):return
    record=load_json(regular(pending,STATE,4096))
    require(set(record)=={'event_id','ordinal','container','manifest_hash','intent_hash'},'SEMANTIC_PENDING')
    target=area(record['event_id'])
    value=manifest(record['event_id'])
    budget=Budget(target,value)
    require(type(record['ordinal']) is int and 0<=record['ordinal']<9,'SEMANTIC_PENDING')
    intent=load_json(regular(target/f"intent-{record['ordinal']:02d}.json",STATE,4096))
    require(record['manifest_hash']==budget.hash and record['intent_hash']==digest(canonical(intent))
            and record['container']==intent['container']
            and re.fullmatch(r'hermes-eval-[0-9a-f]{32}',record['container']),'SEMANTIC_PENDING_BINDING')
    box=hermes_cloud.CloudSandbox(ROOT,target,hermes_cloud.IMAGE)
    if not box.container_exists(record['container']):return
    info=box.inspect(record['container'],timeout=5)
    if not info['State']['Running']:return
    box.verify_config(info,ROOT/hermes_cloud.WORKER_PATH)
    require(hex_id(info['Id'],64),'CONTAINER_IDENTITY_UNKNOWN')
    box.checked('kill',info['Id'],timeout=5)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    sub=p.add_subparsers(dest='command',required=True)
    create=sub.add_parser('prepare');create.add_argument('--run',required=True);create.add_argument('--proposal',required=True,type=Path)
    for command in ('plan','execute','audit'):
        c=sub.add_parser(command);c.add_argument('--event',required=True)
        if command=='execute':c.add_argument('--approval',required=True,type=Path)
    args=p.parse_args()
    try:
        if args.command=='prepare':result=prepare(args.run,regular(args.proposal,args.proposal.absolute().parent,65536))
        elif args.command=='plan':result=send_plan(args.event)
        elif args.command=='execute':result=run(args.event,args.approval)
        else:result=audit(args.event)
        print(canonical(result).decode());return 0
    except (EvaluationError,OSError,ValueError,KeyError,TypeError,AttributeError) as error:
        reason=str(error) if isinstance(error,EvaluationError) else 'SEMANTIC_OPERATION_FAILED'
        print(canonical({'status':'STOPPED','reason':reason}).decode(),file=sys.stderr);return 2


if __name__=='__main__':sys.exit(main())
