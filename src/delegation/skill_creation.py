"""Generated two-file skill intake using the existing frozen skill audit and Sandbox."""
import ast
import re
import secrets
import sys
import time

from delegation.core import IMAGE
from delegation.generated import git
from delegation.skill_reuse import Controller as SkillController
from evaluation.core import EvaluationError, canonical, digest, load_json, regular, require, write_new
from evaluation.sandbox import Sandbox

FIXTURE = 'fixtures/generated_skills/event-counts-task'
SKILL = 'event-status-counts/SKILL.md'
PROGRAM = 'event-status-counts/scripts/aggregate.py'
FILES = (SKILL, PROGRAM)
PACKET = ('catalog.json', 'contract.json', 'public.json')
ROUTING = ('needed', 'equivalent', 'incomplete', 'denied')
EXECUTION = ('mixed', 'empty', 'duplicates', 'boundary', 'bad_type', 'bad_status',
             'bad_category', 'extra_key', 'oversized')
CASES = ROUTING + EXECUTION
OPERATIONS = ('select_create', 'select_reuse', 'hold_evidence', 'hold_permission', 'run_aggregate')


def request(value):
    require(type(value) is dict and set(value) == {'operation'} and
            value['operation'] in OPERATIONS, 'REQUEST_SCHEMA')
    return value['operation']


def observe(outcome):
    require(outcome['exit'] in (0, 2) and outcome['container_exit'] == outcome['exit'] and
            not outcome['error'] and not outcome['oom'] and not outcome['stderr'], 'EXECUTION_FAILED')
    value = load_json(outcome['stdout'])
    if outcome['exit'] == 2:
        require(value == {'error': 'INVALID_INPUT'}, 'ERROR_SCHEMA')
    else:
        require(type(value) is dict and set(value) == {'counts'} and type(value['counts']) is dict, 'OUTPUT_SCHEMA')
        for category, counts in value['counts'].items():
            require(type(category) is str and re.fullmatch('[a-z0-9]{1,16}', category), 'OUTPUT_CATEGORY')
            require(type(counts) is dict and set(counts) == {'ok', 'failed'} and
                    all(type(n) is int and 0 <= n <= 16384 for n in counts.values()), 'OUTPUT_COUNTS')
    return value


def make_trials(catalog):
    """Supervisor-owned expectations; never supply this function or its answers to generator."""
    trials = []
    for _ in range(3):
        first, second = secrets.token_hex(4), secrets.token_hex(8)
        while second == first: second = secrets.token_hex(8)
        event = {'category': first, 'status': 'ok'}
        inputs = {
            'mixed': {'events': [event, {'category': second, 'status': 'failed'}, event,
                                  {'category': first, 'status': 'failed'}]},
            'empty': {'events': []}, 'duplicates': {'events': [event]*4},
            'boundary': {'events': []}, 'bad_type': {'events': first},
            'bad_status': {'events': [{'category': first, 'status': 'other'}]},
            'bad_category': {'events': [{'category': 'A'+first, 'status': 'ok'}]},
            'extra_key': {'events': [dict(event, extra=1)]}, 'oversized': {'events': []}}
        row = {}
        for name in ROUTING:
            listing = load_json(canonical(catalog))
            if name == 'equivalent': listing['skills'].append({'name': 'existing-counter', 'capability': 'event-status-counts'})
            if name == 'incomplete': listing['complete'] = False
            row[name] = {'kind': 'routing', 'task': {'required_capability': 'event-status-counts',
                'catalog': listing, 'creation_allowed': name != 'denied',
                'instruction': 'Choose routing for the original request from this catalog snapshot only; never write a skill in a routing task.'},
                'operation': {'needed': 'select_create', 'equivalent': 'select_reuse',
                              'incomplete': 'hold_evidence', 'denied': 'hold_permission'}[name]}
        for name, value in inputs.items():
            raw = canonical(value)
            if name in ('boundary', 'oversized'):
                raw += b' ' * ((16384 if name == 'boundary' else 16385)-len(raw))
            valid = name in ('mixed', 'empty', 'duplicates', 'boundary')
            counts = {}
            if valid:
                for item in value['events']:
                    counts.setdefault(item['category'], {'ok': 0, 'failed': 0})[item['status']] += 1
            row[name] = {'kind': 'execution', 'task': {'input': value, 'stdin_bytes': len(raw),
                         'stdin_sha256': digest(raw), 'padding': 'trailing JSON whitespace' if name in ('boundary','oversized') else None},
                         'stdin': raw.decode(), 'operation': 'run_aggregate', 'exit': 0 if valid else 2,
                         'expected': {'counts': counts} if valid else {'error': 'INVALID_INPUT'}}
        trials.append(row)
    return trials


class Controller(SkillController):
    def legacy(self):
        gate = super().legacy()
        gate.SOURCES = list(dict.fromkeys([*gate.SOURCES, 'src/delegation/skill_creation.py',
            'scripts/skill_create.py', *[FIXTURE+'/'+p for p in PACKET]]))
        return gate

    def freeze(self, name):
        work = self.work(name); self.legacy().verify_gate(work)
        require(self.read_json(self.runs, 'skill-reuse.lock') == {'run_id': name}, 'GLOBAL_LOCK')
        head = git(self.root, 'rev-parse', 'HEAD').decode().strip(); sources = self.sources()
        require(all(digest(git(self.root, 'show', head+':'+p)) == h for p,h in sources.items()), 'EVALUATOR_NOT_COMMITTED')
        packet = work/'packet'; packet.mkdir()
        for p in PACKET: write_new(packet/p, regular(self.root/FIXTURE/p, self.root))
        git(packet, 'init', '--template=', '--initial-branch=generated')
        git(packet, 'add', '.')
        git(packet, '-c', 'user.name=Fixture Controller', '-c', 'user.email=fixture@example.invalid',
            'commit', '-m', 'event skill frozen baseline '+secrets.token_hex(12))
        self.save(work, 'trials.private.json', make_trials(self.read_json(packet, 'catalog.json')))
        m = {'controller_sha': head, 'sources': sources,
             'baseline_sha': git(packet, 'rev-parse', 'HEAD').decode().strip(),
             'packet_git_hash': digest(regular(packet/'.git/config', self.runs)),
             'trials_hash': digest(regular(work/'trials.private.json', self.runs)),
             'environment_hash': digest(regular(work/'environment.json', self.runs)),
             'gate_hash': digest(regular(work/'gate.json', self.runs)),
             'budget_hash': digest(regular(work/'budget.json', self.runs)),
             'candidate_count': 1, 'trials': 3, 'budget_seconds': 1200, 'api_calls': 0}
        self.save(work, 'manifest.json', m)
        self.save(work, 'freeze.checkpoint.json', {'manifest_hash': digest(regular(work/'manifest.json', self.runs))})
        self.legacy().event(work, 'EVALUATION_FROZEN', digest(regular(work/'manifest.json', self.runs)))
        return {'status': 'FROZEN', 'run_id': name, 'baseline_sha': m['baseline_sha'],
                'manifest_hash': digest(regular(work/'manifest.json', self.runs))}

    def intake(self, work, sha):
        m = self.frozen(work); packet = work/'packet'
        require(not packet.is_symlink() and not (packet/'.git').is_symlink() and
                not (packet/'.git/objects/info/alternates').exists(), 'PACKET_BOUNDARY')
        require(digest(regular(packet/'.git/config', self.runs)) == m['packet_git_hash'], 'PACKET_CONFIG')
        require(type(sha) is str and re.fullmatch('[a-f0-9]{40}', sha), 'CANDIDATE_SHA')
        require(sha != m['baseline_sha'] and git(packet,'rev-parse','HEAD').decode().strip() == sha and
                not git(packet,'status','--porcelain','--untracked-files=all'), 'PACKET_IDENTITY')
        git(packet,'merge-base','--is-ancestor',m['baseline_sha'],sha)
        require(git(packet,'diff','--name-only',m['baseline_sha'],sha).decode().splitlines() == sorted(FILES), 'EDIT_SCOPE')
        data = {}
        for path in FILES:
            tree = git(packet,'ls-tree',sha,'--',path).split()
            require(len(tree)==4 and tree[:2]==[b'100644',b'blob'], 'ARTIFACT_TYPE')
            size = git(packet,'cat-file','-s',sha+':'+path).strip()
            require(size.isdigit() and 0<int(size)<=65536, 'ARTIFACT_SIZE')
            data[path] = git(packet,'show',sha+':'+path)
        require(sum(map(len,data.values())) <= 65536, 'ARTIFACT_SIZE')
        try: tree = ast.parse(data[PROGRAM])
        except (SyntaxError, ValueError): require(False, 'PYTHON_SYNTAX')
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                require(all(n.name.split('.')[0] in sys.stdlib_module_names for n in node.names), 'DEPENDENCY_FORBIDDEN')
            elif isinstance(node, ast.ImportFrom):
                require(node.level==0 and (node.module or '').split('.')[0] in sys.stdlib_module_names, 'DEPENDENCY_FORBIDDEN')
        return m,data

    def public(self, name, sha):
        work=self.work(name); _,data=self.intake(work,sha)
        require(not (work/'accepted.json').exists(), 'CANDIDATE_FIXED')
        index=len(list(work.glob('public-*.json')))
        require(index<2, 'PUBLIC_LIMIT')
        start=time.monotonic(); budget=self.read_json(work,'budget.json')
        require(time.time()-budget['started_at']<1200, 'RUN_DEADLINE')
        program=work/f'public-{index}.py'; write_new(program,data[PROGRAM]); program.chmod(0o444)
        remaining=1200-(time.time()-budget['started_at'])-10
        require(remaining>0, 'RUN_DEADLINE')
        box=Sandbox(self.root,work,IMAGE,deadline=time.monotonic()+remaining)
        rows=[]
        for case in self.read_json(work/'packet','public.json'):
            result=box.run(program,canonical(case['input']),timeout=min(15,box.deadline-time.monotonic()))
            reason=None
            try:
                actual=observe(result)
                correct=result['exit']==case['exit'] and actual==case['expected']
            except EvaluationError as error:
                correct=False; reason=str(error)
            rows.append({'correct':correct,'reason':reason,'exit':result['exit'],
                         'stdout':result['stdout'].decode('utf-8',errors='replace'),
                         'stdout_hash':digest(result['stdout']),
                         'stderr':result['stderr'].decode('utf-8',errors='replace')})
        report={'candidate_sha':sha,'artifact_hashes':{p:digest(v) for p,v in data.items()},
                'passed':sum(r['correct'] for r in rows),'total':len(rows),'seconds':time.monotonic()-start,'cases':rows}
        self.save(work,f'public-{index}.json',report)
        return report

    def accept(self, name, sha):
        work=self.work(name); m,data=self.intake(work,sha)
        require(not (work/'accepted.json').exists(), 'CANDIDATE_USED')
        public_reports=sorted(work.glob('public-*.json'))
        require(bool(public_reports), 'PUBLIC_NOT_VERIFIED')
        public_name=public_reports[-1].name; public=self.read_json(work,public_name)
        public_total=len(self.read_json(work/'packet','public.json'))
        require(public['candidate_sha']==sha and public['artifact_hashes']=={p:digest(v) for p,v in data.items()} and
                public['passed']==public['total']==public_total and len(public['cases'])==public_total and
                all(row['correct'] is True for row in public['cases']), 'PUBLIC_NOT_VERIFIED')
        candidate=work/'candidate'; candidate.mkdir()
        for path,value in data.items():
            target=candidate/path; target.parent.mkdir(parents=True,exist_ok=True)
            write_new(target,value); target.chmod(0o444)
        a={'candidate_sha':sha,'baseline_sha':m['baseline_sha'],
           'artifact_hashes':{p:digest(v) for p,v in data.items()},
           'public_report':public_name,'public_report_hash':digest(regular(work/public_name,self.runs)),
           'manifest_hash':digest(regular(work/'manifest.json',self.runs))}
        self.save(work,'accepted.json',a); self.save(work,'evaluation-lock.json',a)
        self.legacy().event(work,'EVALUATING',digest(regular(work/'accepted.json',self.runs)))
        return a

    def accepted(self, work):
        a=self.read_json(work,'accepted.json'); m,data=self.intake(work,a['candidate_sha'])
        require(regular(work/'accepted.json',self.runs)==regular(work/'evaluation-lock.json',self.runs), 'ACCEPTED_LOCK')
        require(a['public_report'] in ('public-0.json','public-1.json') and
                digest(regular(work/a['public_report'],self.runs))==a['public_report_hash'], 'PUBLIC_CHANGED')
        require(a['baseline_sha']==m['baseline_sha'] and a['manifest_hash']==digest(regular(work/'manifest.json',self.runs)), 'ACCEPTED_IDENTITY')
        anchors=[r for r in self.legacy().verify_events(work) if r['state']=='EVALUATING']
        require(len(anchors)==1 and anchors[0]['payload_hash']==digest(regular(work/'accepted.json',self.runs)), 'ACCEPTED_EVENT')
        require(a['artifact_hashes']=={p:digest(v) for p,v in data.items()} and
                all(regular(work/'candidate'/p,self.runs)==v for p,v in data.items()), 'ARTIFACT_CHANGED')
        return a

    def location(self, name, trial, case):
        work=self.work(name)
        require(type(trial) is int and 0<=trial<3 and case in CASES, 'CASE_ID')
        return work,f'{trial}-{case}'

    def handoff(self, name, trial):
        work=self.work(name); a=self.accepted(work)
        require(type(trial) is int and 0<=trial<3, 'TRIAL_ID')
        require(not (work/'assessment.lock').exists(), 'ASSESSMENT_STARTED')
        cases=self.read_json(work,'trials.private.json')[trial]
        tasks=[{'id':key,'kind':value['kind'],'task':value['task']} for key,value in cases.items()]
        self.save(work,f'{trial}.read.json',{'candidate_sha':a['candidate_sha'],'tasks_hash':digest(canonical(tasks))})
        return {'skill':regular(work/'candidate'/SKILL,self.runs).decode(),'tasks':tasks,
                'allowed_operations':list(OPERATIONS),
                'transport':'For each task call use with operation-only JSON. Execution returns exit 0 counts or expected exit 2 INVALID_INPUT. Deliver its exact stdout through respond --response including final newline. Routing selections need no respond. No retries. Closing chat is administrative only.'}

    def use(self, name, trial, case, value):
        work,label=self.location(name,trial,case); a=self.accepted(work)
        require((work/f'{trial}.read.json').is_file(), 'SKILL_NOT_READ')
        require(not (work/'assessment.lock').exists(), 'ASSESSMENT_STARTED')
        require(not (work/(label+'.trace.json')).exists(), 'CASE_USED')
        write_new(work/'active.lock',canonical({'label':label})); start=time.monotonic()
        try:
            op=request(value); row=self.read_json(work,'trials.private.json')[trial][case]
            budget=self.read_json(work,'budget.json')
            require(time.time()-budget['started_at']<1200, 'RUN_DEADLINE')
            trace={'operation':op,'task_hash':digest(canonical(row['task'])),'candidate_sha':a['candidate_sha']}
            if op=='run_aggregate':
                require(row['kind']=='execution', 'EXECUTION_NOT_ALLOWED')
                remaining=1200-(time.time()-budget['started_at'])-10
                require(remaining>0, 'RUN_DEADLINE')
                result=Sandbox(self.root,work,IMAGE,deadline=time.monotonic()+remaining).run(
                    work/'candidate'/PROGRAM,row['stdin'].encode(),timeout=min(15,remaining))
                observe(result)
                stdout=result.pop('stdout'); stderr=result.pop('stderr')
                trace.update(outcome=result,stdout=stdout.decode(),stderr=stderr.decode(),stdout_hash=digest(stdout))
                response={'exit':result['exit'],'stdout':stdout.decode(),'stderr':stderr.decode()}
            else:
                require(row['kind']=='routing', 'ROUTING_NOT_ALLOWED')
                response={'status':'RECORDED','operation':op}
            trace['seconds']=time.monotonic()-start
            self.save(work,label+'.trace.json',trace); self.accepted(work)
            (work/'active.lock').unlink()
            return response
        except Exception as error:
            from evaluation.core import EvaluationError
            self.save(work,'stopped.json',{'label':label,'reason':str(error) if isinstance(error,EvaluationError) else 'CONTROLLER_ERROR',
                                         'pending_container':getattr(error,'pending_container',None)})
            raise

    def respond(self, name, trial, case, response):
        work,label=self.location(name,trial,case); a=self.accepted(work)
        require(not (work/'active.lock').exists() and not (work/'assessment.lock').exists(), 'ASSESSMENT_OR_FAILURE')
        require(time.time()-self.read_json(work,'budget.json')['started_at']<1200, 'RUN_DEADLINE')
        require(type(response) is str and len(response.encode())<=65536, 'RESPONSE_BOUNDARY')
        trace=self.read_json(work,label+'.trace.json')
        require(trace['operation']=='run_aggregate', 'RESPONSE_NOT_APPLICABLE')
        self.save(work,label+'.response.json',{'response':response,'response_hash':digest(response.encode()),
                                            'task_hash':trace['task_hash'],'candidate_sha':a['candidate_sha']})
        return {'status':'RECEIVED'}

    def evaluate(self, name):
        work=self.work(name); a=self.accepted(work)
        require(not (work/'active.lock').exists() and not (work/'report.json').exists(), 'ACTIVE_OR_USED')
        write_new(work/'assessment.lock',canonical({'candidate_sha':a['candidate_sha']}))
        budget=self.read_json(work,'budget.json'); require(time.time()-budget['started_at']<1200, 'RUN_DEADLINE')
        sessions=self.read_json(work,'sessions.json')
        require(type(sessions) is list and len(sessions)==3 and len(set(sessions))==3 and
                all(type(s) is str and re.fullmatch(r'[/A-Za-z0-9_-]{1,200}',s) for s in sessions), 'FRESH_SESSIONS')
        correct=dict.fromkeys(CASES,0); hashes={}; seconds=budget['seconds']
        for p in work.glob('public-*.json'): seconds+=self.read_json(work,p.name)['seconds']
        for i,cases in enumerate(self.read_json(work,'trials.private.json')):
            read=self.read_json(work,f'{i}.read.json')
            tasks=[{'id':k,'kind':v['kind'],'task':v['task']} for k,v in cases.items()]
            require(read=={'candidate_sha':a['candidate_sha'],'tasks_hash':digest(canonical(tasks))}, 'READ_IDENTITY')
            hashes[f'{i}.read.json']=digest(regular(work/f'{i}.read.json',self.runs))
            for key,row in cases.items():
                label=f'{i}-{key}'; trace=self.read_json(work,label+'.trace.json')
                require(trace['candidate_sha']==a['candidate_sha'] and trace['task_hash']==digest(canonical(row['task'])), 'TRACE_IDENTITY')
                good=trace['operation']==row['operation']
                if trace['operation']=='run_aggregate':
                    result=dict(trace['outcome'],stdout=trace['stdout'].encode(),stderr=trace['stderr'].encode())
                    good &= result['exit']==row['exit'] and observe(result)==row['expected']
                    require(digest(result['stdout'])==trace['stdout_hash'], 'STDOUT_HASH')
                    require((work/(label+'.response.json')).is_file(), 'FINAL_RESPONSE_MISSING')
                    response=self.read_json(work,label+'.response.json')
                    require(response['candidate_sha']==a['candidate_sha'] and response['task_hash']==trace['task_hash'] and
                            digest(response['response'].encode())==response['response_hash'], 'RESPONSE_IDENTITY')
                    good &= response['response'].encode()==result['stdout']
                    hashes[label+'.response.json']=digest(regular(work/(label+'.response.json'),self.runs))
                correct[key]+=int(good); seconds+=trace['seconds']
                hashes[label+'.trace.json']=digest(regular(work/(label+'.trace.json'),self.runs))
        require(seconds<=1200, 'RUN_BUDGET')
        report={'status':'PASS' if all(n==3 for n in correct.values()) else 'FAIL','counts':correct,
                'candidate_sha':a['candidate_sha'],'baseline_sha':a['baseline_sha'],'artifact_hashes':a['artifact_hashes'],
                'manifest_hash':a['manifest_hash'],'machine_seconds':seconds,'trace_hashes':hashes,
                'sessions_hash':digest(regular(work/'sessions.json',self.runs)),'session_ids':sessions,'api_calls':0,
                'claim':'Finite synthetic task and three fresh Codex sessions; no adoption.'}
        self.save(work,'report.json',report)
        self.legacy().event(work,'EVALUATION_COMPLETED',digest(regular(work/'report.json',self.runs)))
        self.save(work,'checkpoint.json',{'assessment_hash':digest(regular(work/'assessment.lock',self.runs)),
            'last_event_hash':self.legacy().verify_events(work)[-1]['hash'],
            'report_hash':digest(regular(work/'report.json',self.runs)),'accepted_hash':digest(regular(work/'accepted.json',self.runs))})
        return report
