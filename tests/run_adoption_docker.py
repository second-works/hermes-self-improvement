"""Explicit opt-in PUBLIC integration run using synthetic approvals, not acceptance."""
from datetime import datetime, timedelta, timezone
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from adoption.core import Controller, EvaluationError, canonical, digest, save, ARTIFACT
from adoption.regression import DockerRegression


def main():
    require_area = Path(sys.argv[1]).absolute()
    c = Controller(ROOT, require_area)
    packet = c.initialize()
    check = DockerRegression(c)
    results = []
    for target in ('normal', 'degradation', 'crash'):
        root = c.area / 'fixtures' / target
        (root / 'scripts').mkdir(parents=True)
        program = root / ARTIFACT
        program.write_bytes((c.area / 'baseline.py').read_bytes())
        c.register('public-synthetic-test',target,root)
        def approve(operation):
            request = c.request(target,operation,
                (datetime.now(timezone.utc)+timedelta(hours=2)).isoformat(), 'SYNTHETIC-TEST-NOT-HUMAN')
            return c.approve(request,confirmation=digest(canonical(request)))
        key = approve('ADOPT')
        if target == 'crash':
            # Real process death after durable intent and a partial fixture write.
            code = '''import os,sys
from pathlib import Path
sys.path.insert(0,sys.argv[1]+'/src')
from adoption.core import Controller
c=Controller(Path(sys.argv[1]),Path(sys.argv[2]))
def crash(*_):
    Path(sys.argv[3]).write_bytes(b'# partial fixture write\\n')
    os._exit(71)
c.replace=crash
c.execute(sys.argv[4],lambda *_:True)
'''
            run = subprocess.run([sys.executable,'-I','-B','-c',code,str(ROOT),str(c.area),str(program),key])
            assert run.returncode == 71
            c = Controller(ROOT,c.area); check = DockerRegression(c)
            assert c.state(target) == 'RECOVERY_REQUIRED'
        else:
            assert c.execute(key,check)['state'] == 'ADOPTED'
        if target == 'degradation':
            program.write_bytes(b'# injected degradation, PUBLIC fixture only\n')
            try:
                c.observe(target,check)
            except EvaluationError:
                pass
            assert c.state(target) == 'RECOVERY_REQUIRED'
        if target != 'normal':
            assert c.execute(approve('ROLLBACK'),check)['state'] == 'ROLLED_BACK'
            assert digest(program.read_bytes()) == packet['before_hash']
        results.append({'target':target,'state':c.state(target), 'actual_hash':digest(program.read_bytes()),
                        'journal_hash':c.events(target)[-1]['hash']})
    save(c.area / 'summary.json', {'classification':'PUBLIC','approval_kind':'SYNTHETIC_TEST',
        'human_acceptance':'NOT_RUN','candidate_sha':packet['candidate_sha'],
        'evaluation_hash':packet['evaluation_hash'],'scenarios':results,
        'candidate_execution':'fixed Docker only','gemma_calls':0,'paid_api_calls':0,'key_reads':0})
    print(canonical(results).decode())


if __name__ == '__main__': main()
