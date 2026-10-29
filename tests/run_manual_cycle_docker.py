"""Opt-in integration over the newly evaluated candidate; synthetic tickets only.

Keep the human cycle's registered target unchanged. Every integration scenario
has a separate controller/root/backup/intent, tied to the same audited packet.
"""
from pathlib import Path
from datetime import datetime, timedelta, timezone
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from manual_cycle.core import Cycle, EvaluatedAdoption
from adoption.core import ARTIFACT, save
from evaluation.core import EvaluationError, canonical, digest, regular, require, write_new


def main():
    c = Cycle(ROOT, sys.argv[1])
    with c.operation('synthetic-docker-verification', {'AWAITING_PR'}):
        started = time.monotonic()
        normal = c.adoption()
        before = normal.actual(normal.binding('target'),ARTIFACT)
        rows = []
        for kind in ('normal','degradation','crash'):
            trial = 'synthetic-' + kind
            a = EvaluatedAdoption(c, trial)
            packet = a.initialize()
            root = a.area / 'fixtures/target'
            (root / 'scripts').mkdir(parents=True)
            write_new(root / ARTIFACT, regular(a.area / 'baseline.py', ROOT))
            binding = a.register('synthetic-docker-test', 'target',root)
            def approve(operation):
                ticket = a.request('target',operation,
                    (datetime.now(timezone.utc)+timedelta(hours=2)).isoformat(), 'SYNTHETIC-NOT-HUMAN')
                return a.approve(ticket,confirmation=digest(canonical(ticket)))
            key=approve('ADOPT')
            if kind == 'crash':
                code = '''import os,sys
from pathlib import Path
sys.path.insert(0,sys.argv[1]+'/src')
from manual_cycle.core import Cycle,EvaluatedAdoption
c=Cycle(Path(sys.argv[1]),sys.argv[2]); a=EvaluatedAdoption(c,'synthetic-crash')
replace=a.replace
def crash(binding,path,data,expected):
    replace(binding,path,data[:128],expected)
    os._exit(71)
a.replace=crash
a.execute(sys.argv[3],lambda *_:True)
'''
                process=subprocess.run([sys.executable,'-I','-B','-c',code,str(ROOT),c.name,key],timeout=30)
                require(process.returncode == 71, 'CRASH_EXIT')
                a=EvaluatedAdoption(Cycle(ROOT,c.name),trial)
                require(a.state('target') == 'RECOVERY_REQUIRED','CRASH_STATE')
            else:
                require(a.execute(key,c.regression(a))['state'] == 'ADOPTED','ADOPTION')
                if kind == 'normal':
                    a.observe('target',c.regression(a))
                else:
                    a.replace(binding,ARTIFACT,b'# PUBLIC synthetic fault\n',packet['after_hash'])
                    try:
                        a.observe('target',c.regression(a))
                    except EvaluationError:
                        pass
                    require(a.state('target') == 'RECOVERY_REQUIRED','DEGRADATION_STATE')
            if kind != 'normal':
                require(a.execute(approve('ROLLBACK'),c.regression(a))['state'] == 'ROLLED_BACK','RECOVERY')
            require(a.actual(a.binding('target'),ARTIFACT)[0] == packet['after_hash' if kind == 'normal' else 'before_hash'], 'ACTUAL_HASH')
            rows.append({'scenario':kind,'state':a.state('target'),
                         'actual_hash':a.actual(a.binding('target'),ARTIFACT)[0],
                         'last_event_hash':a.events('target')[-1]['hash']})
        require(normal.actual(normal.binding('target'),ARTIFACT) == before and
                normal.state('target') == 'AWAITING_APPROVAL','HUMAN_TARGET_CHANGED')
        result={'classification':'PUBLIC','approval_kind':'SYNTHETIC_TEST','human_acceptance':'NOT_RUN',
                'candidate_sha':packet['candidate_sha'],'evaluation_hash':packet['evaluation_hash'],
                'scenarios':rows,'docker_cases':40,'machine_seconds':time.monotonic()-started,
                'human_target':'UNCHANGED_AWAITING_APPROVAL','paid_api_calls':0,'key_reads':0,'gemma_calls':0}
        save(c.area / 'synthetic-docker-results.json',result)
        c.event('AWAITING_PR',{'synthetic_verification_hash':digest(canonical(result))})
        print(canonical(result).decode())


if __name__ == '__main__': main()
