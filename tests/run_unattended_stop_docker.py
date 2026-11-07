#!/usr/bin/env python3
"""Stop a real fixed, network-none Hermes worker blocked before reading any auth/input."""
import json
from pathlib import Path
import subprocess
import sys
from threading import Event, Thread
import time
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'));sys.path.insert(0,str(ROOT/'scripts'));sys.path.insert(0,str(ROOT/'tests'))
import run_public_hermes as generation
from run_mock_improvement import control_intake
from delegation import hermes_cloud
from delegation.generated import git
from evaluation.core import EvaluationError,canonical,digest,require
from intake_public_failure import failure_event_id
from run_semantic_budget_docker import OfflineSandbox,synthetic_auth


def main():
    head=git(ROOT,'rev-parse','HEAD').decode().strip();check=time.time_ns()
    entry={'schema_version':1,'status':'AWAITING_HUMAN_REVIEW','classification':'PUBLIC',
           'source_kind':'public-github-check','repo':'second-works/hermes-self-improvement',
           'pr_number':3000000,'pr_url':'https://github.com/second-works/hermes-self-improvement/pull/3000000',
           'head_sha':head,'check_id':check,'conclusion':'failure','snapshot_hash':digest(canonical(['PUBLIC_STOP_TEST',check])),
           'event_id':failure_event_id(3000000,head,check),'reproduction_sha256':digest(b'PUBLIC_SYNTHETIC_STOP')}
    state=ROOT/'runs/public-hermes';state.mkdir(parents=True,exist_ok=True)
    prompt=generation.request_prompt(entry)
    approval=ROOT/'runs/synthetic-stop-approval.json'
    approval.write_bytes(canonical({**generation.plan(entry,prompt),'expires_at':int(time.time())+300}));approval.chmod(0o600)
    entered=Event();errors=[];identities=[]
    answer=canonical({'status':'COMPLETED','requests':1,'tools':0,'text':json.dumps({
        'schema_version':1,'decision':'HOLD','reason':'Synthetic stop test.',
        'evidence_refs':['/reproduction_sha256']})})

    def stalled(root,data,work,deadline,name):
        box=OfflineSandbox(root,work,hermes_cloud.IMAGE)
        program=root/hermes_cloud.WORKER_PATH
        box.checked(*box.options(name,program),timeout=5)
        process=None
        try:
            info=box.inspect(name,timeout=5);box.verify_config(info,program)
            identities.append(info['Id'])
            # Keep stdin open and empty. The pinned worker blocks before parsing an auth object.
            process=subprocess.Popen([box.binary,'--config',str(box.config),'--host',box.endpoint,
                                      'start','--attach','--interactive',name],env=box.env,
                                     stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
            until=time.monotonic()+5
            while not box.inspect(name,timeout=5)['State']['Running']:
                require(time.monotonic()<until,'STOP_TEST_START_TIMEOUT');time.sleep(0.05)
            entered.set()
            require(process.wait(timeout=15)!=0,'STOP_TEST_WORKER_NOT_KILLED')
            require(not box.inspect(name,timeout=5)['State']['Running'],'STOP_TEST_STILL_RUNNING')
        finally:
            if process is not None:
                for stream in (process.stdin,process.stdout,process.stderr):
                    if stream:stream.close()
            box.cleanup(name)
            if process is not None and process.poll() is None:process.wait(timeout=5)
        return answer

    def execute():
        try:generation.execute(entry,prompt,approval,state)
        except Exception as error:errors.append(str(error))

    print('REAL_OFFLINE_WORKER_STOP model_calls=0 real_auth_reads=0 auth_delivered=0',flush=True)
    with patch.object(generation,'read_auth',return_value=synthetic_auth()), \
         patch.object(hermes_cloud,'response',side_effect=stalled) as cloud, \
         patch.object(hermes_cloud,'CloudSandbox',OfflineSandbox):
        thread=Thread(target=execute);thread.start()
        try:
            require(entered.wait(10),'STOP_TEST_NOT_STARTED')
            require(control_intake(state,'stop')=='INTAKE_STOPPED','STOP_TEST_UNCONFIRMED')
        finally:thread.join(20)
        require(not thread.is_alive() and errors==['INTAKE_STOPPED'],'STOP_TEST_RESULT')
        require(cloud.call_count==1 and len(identities)==1,'STOP_TEST_ATTEMPT_COUNT')
        require(not (state/'isolation-pending.json').exists(),'STOP_TEST_PENDING')
        finished=json.loads((state/entry['event_id']/'finished.json').read_text())
        require(finished['status']=='STOPPED' and finished['reason']=='INTAKE_STOPPED','STOP_TEST_RECEIPT')
        require(control_intake(state,'resume')=='ACCEPTING','STOP_TEST_RESUME')
        try:generation.execute(entry,prompt,approval,state)
        except EvaluationError as error:require(str(error)=='EVENT_ALREADY_CLAIMED','STOP_TEST_REPLAY_REASON')
        else:raise EvaluationError('STOP_TEST_REPLAY_ALLOWED')
        require(cloud.call_count==1,'STOP_TEST_RESENT')
    print(json.dumps({'status':'VERIFIED','mode':'PUBLIC_SYNTHETIC_OFFLINE','head':head,
        'event_id':entry['event_id'],'network':'none','model_calls':0,'real_auth_reads':0,
        'auth_delivered':0,'inspected_container_id':identities[0],'worker_stopped':True,
        'container_removed':True,'pending_cleared':True,'resume_did_not_resend':True,
        'finished_receipt_sha256':digest((state/entry["event_id"]/"finished.json").read_bytes())}),flush=True)


if __name__=='__main__':main()
