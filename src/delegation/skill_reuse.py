"""Frozen skill handoff: typed requests, real sandbox stdout, separate fresh users."""
import importlib.util
from pathlib import Path
import re
import secrets
import time

from delegation.core import IMAGE
from delegation.generated import git
from evaluation.core import (EvaluationError, canonical, digest, findings, load_json,
                             regular, require, write_new)
from evaluation.sandbox import Sandbox

FIXTURE = 'fixtures/generated_skills'
SKILL = 'github-code-review/SKILL.md'
PROGRAM = 'github-code-review/scripts/review.py'
SCRIPT_HASH = '7d342aa1fc92afaeea8b7aee834650965b885f167975fd2d4f18e5c31ee80b6e'
SOURCES = ['src/delegation/__init__.py', 'src/evaluation/__init__.py', 'src/delegation/skill_reuse.py', 'scripts/skill_reuse.py',
           'src/delegation/generated.py', 'src/delegation/core.py',
           'src/evaluation/core.py', 'src/evaluation/sandbox.py',
           'scripts/evaluate_fixture.py', 'fixtures/evaluation/isolation_probe.py']
SCENARIOS = ('primary', 'sufficient', 'denied', 'missing', 'baseline')


def request(value):
    require(type(value) is dict and set(value) == {'operation'}, 'REQUEST_SCHEMA')
    require(value['operation'] in ('run_review', 'stop_permission', 'stop_evidence',
                                   'stop_no_procedure'), 'REQUEST_OPERATION')
    return value['operation']


def observe(outcome):
    require(outcome['exit'] == 0 and outcome['container_exit'] == 0 and
            not outcome['error'] and not outcome['oom'] and not outcome['stderr'], 'EXECUTION_FAILED')
    return findings(load_json(outcome['stdout']))[0]


class Controller:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.runs = self.root / 'runs'

    def work(self, name):
        require(type(name) is str and re.fullmatch('skill-[a-f0-9]{24}', name), 'RUN_ID')
        work = self.runs / name
        require(work.is_dir() and not work.is_symlink() and not self.runs.is_symlink(), 'RUN_BOUNDARY')
        return work

    def read_json(self, work, name):
        return load_json(regular(work / name, self.runs))

    def save(self, work, name, value):
        write_new(work / name, canonical(value) + b'\n')

    def legacy(self):
        spec = importlib.util.spec_from_file_location('skill_legacy_gate', self.root / 'scripts/evaluate_fixture.py')
        gate = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(gate)
        gate.SOURCES = list(dict.fromkeys([*gate.SOURCES, *SOURCES,
            *[FIXTURE + '/' + p for p in (SKILL, PROGRAM, 'catalog.json', 'public.json')]]))
        return gate

    def sources(self):
        return self.legacy().source_hashes()

    def prepare(self):
        require(not self.runs.is_symlink(), 'RUN_BOUNDARY')
        self.runs.mkdir(exist_ok=True)
        work = self.runs / ('skill-' + secrets.token_hex(12))
        work.mkdir(mode=0o700)
        self.save(self.runs, 'skill-reuse.lock', {'run_id': work.name})
        start = time.monotonic(); started_at = time.time()
        gate = self.legacy()
        box = Sandbox(self.root, work, IMAGE)
        image, environment = box.image_info(IMAGE), box.environment()
        require(image['id'] == IMAGE, 'IMAGE_CHANGED')
        self.save(work, 'environment.json', {'image': image, 'environment': environment})
        gate.event(work, 'ENVIRONMENT_PINNED', digest(regular(work / 'environment.json', self.runs)))
        gate.gate(work)
        gate.verify_gate(work)
        self.save(work, 'budget.json', {'seconds': time.monotonic() - start, 'started_at': started_at})
        return {'run_id': work.name, 'status': 'ISOLATION_VERIFIED'}

    def freeze(self, name):
        work = self.work(name)
        require(self.read_json(self.runs, 'skill-reuse.lock') == {'run_id': name}, 'GLOBAL_LOCK')
        self.legacy().verify_gate(work)
        head = git(self.root, 'rev-parse', 'HEAD').decode().strip()
        sources = self.sources()
        require(all(digest(git(self.root, 'show', head + ':' + p)) == h
                    for p, h in sources.items()), 'EVALUATOR_NOT_COMMITTED')
        require(sources[FIXTURE + '/' + PROGRAM] == SCRIPT_HASH, 'SCRIPT_CHANGED')
        packet = work / 'packet'
        (packet / 'github-code-review/scripts').mkdir(parents=True)
        for p in (SKILL, PROGRAM, 'catalog.json', 'public.json'):
            write_new(packet / p, regular(self.root / FIXTURE / p, self.root))
        git(packet, 'init', '--template=', '--initial-branch=skill')
        git(packet, 'add', '.')
        git(packet, '-c', 'user.name=Fixture Controller', '-c', 'user.email=fixture@example.invalid',
            'commit', '-m', 'frozen skill baseline ' + secrets.token_hex(12))
        trials = []
        for index in range(3):
            values = {}
            for scenario in SCENARIOS:
                tag, line = secrets.token_hex(8), secrets.randbelow(50) + 2
                path = 'case_' + tag + '.py'
                body = ' context\n+# comment\n+eval(data)' if index != 1 else '+subprocess.run(cmd, shell=True)'
                offset, rule = (2, 'dynamic-eval') if index != 1 else (0, 'shell-execution')
                task = {'path': path, 'patch': f'@@ -{line},1 +{line},3 @@\n' + body}
                operation = 'run_review'
                if scenario == 'denied': operation = 'stop_permission'
                elif scenario == 'missing':
                    task.pop('patch'); operation = 'stop_evidence'
                elif scenario == 'baseline': operation = 'stop_no_procedure'
                values[scenario] = {'task': task, 'expected_operation': operation,
                                    'expected': [[path, line + offset, rule]]}
            trials.append(values)
        self.save(work, 'trials.private.json', trials)
        manifest = {'controller_sha': head, 'sources': sources,
                    'baseline_sha': git(packet, 'rev-parse', 'HEAD').decode().strip(),
                    'packet_git_hash': digest(regular(packet / '.git/config', self.runs)),
                    'script_hash': SCRIPT_HASH, 'trials_hash': digest(regular(work / 'trials.private.json', self.runs)),
                    'environment_hash': digest(regular(work / 'environment.json', self.runs)),
                    'gate_hash': digest(regular(work / 'gate.json', self.runs)),
                    'budget_hash': digest(regular(work / 'budget.json', self.runs)),
                    'budget_seconds': 1200, 'trials': 3, 'candidate_count': 1,
                    'api_calls': 0, 'simultaneous_runs': 1}
        self.save(work, 'manifest.json', manifest)
        self.save(work, 'freeze.checkpoint.json', {'manifest_hash': digest(regular(work / 'manifest.json', self.runs))})
        self.legacy().event(work, 'EVALUATION_FROZEN', digest(regular(work / 'manifest.json', self.runs)))
        return {'run_id': name, 'manifest_hash': digest(regular(work / 'manifest.json', self.runs)),
                'baseline_sha': manifest['baseline_sha'], 'status': 'FROZEN'}

    def frozen(self, work):
        m = self.read_json(work, 'manifest.json')
        require(self.read_json(self.runs, 'skill-reuse.lock') == {'run_id': work.name}, 'GLOBAL_LOCK')
        gate = self.legacy()
        gate.verify_gate(work)
        anchors = [r for r in gate.verify_events(work) if r['state'] == 'EVALUATION_FROZEN']
        require(len(anchors) == 1 and anchors[0]['payload_hash'] == digest(regular(work / 'manifest.json', self.runs)), 'FREEZE_EVENT')
        require(self.read_json(work, 'freeze.checkpoint.json')['manifest_hash'] == digest(regular(work / 'manifest.json', self.runs)), 'FREEZE_ANCHOR')
        require(m['sources'] == self.sources(), 'SOURCE_CHANGED')
        for path, key in [('trials.private.json', 'trials_hash'), ('environment.json', 'environment_hash'),
                          ('gate.json', 'gate_hash'), ('budget.json', 'budget_hash')]:
            require(digest(regular(work / path, self.runs)) == m[key], 'FREEZE_CHANGED')
        return m

    def intake(self, work, sha):
        m = self.frozen(work); packet = work / 'packet'
        require(not packet.is_symlink() and not (packet / '.git').is_symlink() and
                not (packet / '.git/objects/info/alternates').exists(), 'PACKET_BOUNDARY')
        require(digest(regular(packet / '.git/config', self.runs)) == m['packet_git_hash'], 'PACKET_CONFIG')
        require(type(sha) is str and re.fullmatch('[a-f0-9]{40}', sha), 'CANDIDATE_SHA')
        require(sha != m['baseline_sha'], 'NO_CHANGE')
        require(git(packet, 'rev-parse', 'HEAD').decode().strip() == sha and
                not git(packet, 'status', '--porcelain', '--untracked-files=all'), 'PACKET_IDENTITY')
        git(packet, 'merge-base', '--is-ancestor', m['baseline_sha'], sha)
        require(git(packet, 'diff', '--name-only', m['baseline_sha'], sha).decode().splitlines() == [SKILL], 'EDIT_SCOPE')
        tree = git(packet, 'ls-tree', sha, '--', SKILL).split()
        require(tree[:2] == [b'100644', b'blob'] and len(tree) == 4, 'SKILL_TYPE')
        candidate = git(packet, 'show', sha + ':' + SKILL)
        require(0 < len(candidate) <= 16384, 'SKILL_SIZE')
        require(digest(git(packet, 'show', sha + ':' + PROGRAM)) == SCRIPT_HASH, 'SCRIPT_CHANGED')
        return m, candidate

    def accept(self, name, sha):
        work = self.work(name); m, candidate = self.intake(work, sha)
        require(not (work / 'accepted.json').exists(), 'CANDIDATE_USED')
        write_new(work / 'candidate.md', candidate)
        (work / 'candidate.md').chmod(0o444)
        accepted = {'candidate_sha': sha, 'candidate_hash': digest(candidate),
                    'baseline_sha': m['baseline_sha'], 'script_hash': SCRIPT_HASH,
                    'manifest_hash': digest(regular(work / 'manifest.json', self.runs)),
                    'accepted_at': time.time()}
        self.save(work, 'accepted.json', accepted)
        self.save(work, 'evaluation-lock.json', accepted)
        self.legacy().event(work, 'EVALUATING', digest(regular(work / 'accepted.json', self.runs)))
        return accepted

    def accepted(self, work):
        a = self.read_json(work, 'accepted.json')
        m, candidate = self.intake(work, a['candidate_sha'])
        require(regular(work / 'accepted.json', self.runs) == regular(work / 'evaluation-lock.json', self.runs), 'ACCEPTED_LOCK')
        require(a['baseline_sha'] == m['baseline_sha'] and a['script_hash'] == SCRIPT_HASH and
                a['manifest_hash'] == digest(regular(work / 'manifest.json', self.runs)), 'ACCEPTED_IDENTITY')
        anchors = [r for r in self.legacy().verify_events(work) if r['state'] == 'EVALUATING']
        require(len(anchors) == 1 and anchors[0]['payload_hash'] == digest(regular(work / 'accepted.json', self.runs)), 'ACCEPTED_EVENT')
        require(digest(candidate) == a['candidate_hash'] == digest(regular(work / 'candidate.md', self.runs)), 'CANDIDATE_CHANGED')
        return a

    def location(self, name, trial, scenario):
        work = self.work(name)
        require(type(trial) is int and 0 <= trial < 3 and scenario in SCENARIOS, 'TRIAL_ID')
        return work, f'{trial}-{scenario}'

    def handoff(self, name, trial, scenario):
        work, label = self.location(name, trial, scenario)
        a = self.accepted(work)
        require(not (work / 'assessment.lock').exists(), 'ASSESSMENT_STARTED')
        case = self.read_json(work, 'trials.private.json')[trial][scenario]
        skill = (git(work / 'packet', 'show', a['baseline_sha'] + ':' + SKILL)
                 if scenario == 'baseline' else regular(work / 'candidate.md', self.runs))
        self.save(work, label + '.read.json', {'skill_hash': digest(skill), 'task_hash': digest(canonical(case['task']))})
        return {'skill': skill.decode(), 'task': case['task'],
                'allowed_tools': ['run_review'] if scenario != 'denied' else [],
                'transport': 'Use this adapter use with an operation-only JSON request. Stop reports: stop_permission, stop_evidence, stop_no_procedure. After successful run_review, deliver the final task result through respond --response with the exact stdout string including its final newline. Do not summarize or reconstruct it. The session closing message is an administrative receipt only.',
                'instruction': 'Follow this skill for this task only. If sufficient, reuse unchanged. If permission or evidence is missing, stop. Never invent findings, edit files, request external retrieval or arbitrary commands.'}

    def use(self, name, trial, scenario, value):
        work, label = self.location(name, trial, scenario)
        a = self.accepted(work)
        require(not (work / 'assessment.lock').exists(), 'ASSESSMENT_STARTED')
        require((work / (label + '.read.json')).is_file(), 'SKILL_NOT_READ')
        require(not (work / (label + '.trace.json')).exists(), 'TRIAL_ALREADY_USED')
        case = self.read_json(work, 'trials.private.json')[trial][scenario]
        started = time.monotonic()
        # Serial and fail-closed even if a model attempts overlapping tool calls.
        write_new(work / 'active.lock', canonical({'label': label}))
        try:
            op = request(value)
            budget = self.read_json(work, 'budget.json')
            require(time.time() - budget['started_at'] < 1200, 'RUN_DEADLINE')
            spent = budget['seconds']
            spent += sum(self.read_json(work, p.name)['seconds'] for p in work.glob('*.trace.json'))
            require(spent < 1200, 'BUDGET_EXHAUSTED')
            trace = {'operation': op, 'request_hash': digest(canonical(value)), 'task_hash': digest(canonical(case['task'])),
                     'candidate_hash': a['candidate_hash'], 'script_hash': SCRIPT_HASH}
            if op == 'run_review':
                require(scenario != 'denied', 'PERMISSION_DENIED')
                require(set(case['task']) == {'path', 'patch'}, 'EVIDENCE_MISSING')
                require(scenario != 'baseline', 'NO_EXECUTION_PROCEDURE')
                program = work / (label + '.py')
                write_new(program, regular(self.root / FIXTURE / PROGRAM, self.root))
                program.chmod(0o444)
                box = Sandbox(self.root, work, IMAGE, deadline=time.monotonic() + 1200 - spent)
                outcome = box.run(program, canonical(case['task']), timeout=min(30, 1200 - spent))
                observe(outcome)
                stdout = outcome.pop('stdout'); stderr = outcome.pop('stderr')
                trace.update(outcome=outcome, stdout=stdout.decode(), stderr=stderr.decode(),
                             stdout_hash=digest(stdout), program_hash=digest(regular(program, self.runs)))
                response = {'exit': outcome['exit'], 'stdout': stdout.decode(), 'stderr': stderr.decode()}
            else:
                response = {'status': 'STOPPED', 'operation': op}
            trace['seconds'] = time.monotonic() - started
            self.save(work, label + '.trace.json', trace)
            self.accepted(work)
            (work / 'active.lock').unlink()
            return response
        except Exception as error:
            # A failed run retains its lock and recovery identity; no automatic retry.
            self.save(work, 'stopped.json', {'label': label,
                'reason': str(error) if isinstance(error, EvaluationError) else 'CONTROLLER_ERROR',
                'pending_container': getattr(error, 'pending_container', None)})
            raise

    def respond(self, name, trial, scenario, response):
        """Receive the session's final task result; no correctness feedback before batch."""
        work, label = self.location(name, trial, scenario)
        a = self.accepted(work)
        require(not (work / 'active.lock').exists(), 'ACTIVE_OR_FAILED')
        require(not (work / 'assessment.lock').exists(), 'ASSESSMENT_STARTED')
        require(time.time() - self.read_json(work, 'budget.json')['started_at'] < 1200, 'RUN_DEADLINE')
        require(type(response) is str and len(response.encode('utf-8')) <= 65536, 'RESPONSE_BOUNDARY')
        trace = self.read_json(work, label + '.trace.json')
        require(trace['operation'] == 'run_review', 'RESPONSE_NOT_APPLICABLE')
        self.save(work, label + '.response.json', {'response': response,
            'response_hash': digest(response.encode('utf-8')), 'task_hash': trace['task_hash'],
            'candidate_hash': a['candidate_hash']})
        return {'status': 'RECEIVED'}

    def evaluate(self, name):
        work = self.work(name); a = self.accepted(work)
        require(not (work / 'active.lock').exists(), 'ACTIVE_OR_FAILED')
        require(not (work / 'report.json').exists(), 'EVALUATION_USED')
        write_new(work / 'assessment.lock', canonical({'candidate_sha': a['candidate_sha']}))
        cases = self.read_json(work, 'trials.private.json')
        budget = self.read_json(work, 'budget.json')
        require(time.time() - budget['started_at'] < 1200, 'RUN_DEADLINE')
        sessions = self.read_json(work, 'sessions.json')
        require(type(sessions) is list and len(sessions) == 3 and
                all(type(v) is str and re.fullmatch(r'[/A-Za-z0-9_-]{1,200}', v) for v in sessions) and
                len(set(sessions)) == 3, 'FRESH_SESSIONS_MISSING')
        correct = {scenario: 0 for scenario in SCENARIOS}; hashes = {}
        seconds = self.read_json(work, 'budget.json')['seconds']
        for i in range(3):
            for scenario in SCENARIOS:
                label = f'{i}-{scenario}'
                read = self.read_json(work, label + '.read.json')
                trace = self.read_json(work, label + '.trace.json')
                case = cases[i][scenario]
                require(trace['candidate_hash'] == a['candidate_hash'] and trace['script_hash'] == SCRIPT_HASH, 'TRACE_IDENTITY')
                require(trace['task_hash'] == read['task_hash'] == digest(canonical(case['task'])), 'TASK_IDENTITY')
                expected_skill = (git(work / 'packet', 'show', a['baseline_sha'] + ':' + SKILL)
                                 if scenario == 'baseline' else regular(work / 'candidate.md', self.runs))
                require(read['skill_hash'] == digest(expected_skill), 'READ_IDENTITY')
                good = trace['operation'] == case['expected_operation']
                if trace['operation'] == 'run_review':
                    require((work / (label + '.response.json')).is_file(), 'FINAL_RESPONSE_MISSING')
                    response = self.read_json(work, label + '.response.json')
                    require(response['candidate_hash'] == a['candidate_hash'] and
                            response['task_hash'] == trace['task_hash'], 'RESPONSE_IDENTITY')
                    require(digest(response['response'].encode('utf-8')) == response['response_hash'], 'RESPONSE_HASH')
                    good &= response['response'].encode('utf-8') == trace['stdout'].encode('utf-8')
                    hashes[label + '.response.json'] = digest(regular(work / (label + '.response.json'), self.runs))
                    parsed = observe(dict(trace['outcome'], stdout=trace['stdout'].encode(), stderr=trace['stderr'].encode()))
                    good &= [list(row) for row in parsed] == case['expected']
                    require(digest(trace['stdout'].encode()) == trace['stdout_hash'] and
                            trace['program_hash'] == SCRIPT_HASH, 'OUTPUT_IDENTITY')
                correct[scenario] += int(good)
                seconds += trace['seconds']
                for suffix in ('read', 'trace'):
                    p = label + '.' + suffix + '.json'
                    hashes[p] = digest(regular(work / p, self.runs))
        require(seconds <= 1200, 'BUDGET_EXHAUSTED')
        report = {'status': 'PASS' if all(n == 3 for n in correct.values()) else 'FAIL',
                  'counts': correct, 'candidate_sha': a['candidate_sha'], 'baseline_sha': a['baseline_sha'],
                  'candidate_hash': a['candidate_hash'], 'script_hash': SCRIPT_HASH,
                  'manifest_hash': a['manifest_hash'], 'machine_seconds': seconds,
                  'trace_hashes': hashes, 'sessions_hash': digest(regular(work / 'sessions.json', self.runs)),
                  'session_ids': sessions, 'api_calls': 0,
                  'claim': 'Three fresh Codex sessions and finite synthetic tasks only; no adoption.'}
        self.save(work, 'report.json', report)
        self.legacy().event(work, 'EVALUATION_COMPLETED', digest(regular(work / 'report.json', self.runs)))
        self.save(work, 'checkpoint.json', {'assessment_hash': digest(regular(work / 'assessment.lock', self.runs)), 'last_event_hash': self.legacy().verify_events(work)[-1]['hash'], ** {'report_hash': digest(regular(work / 'report.json', self.runs)),
                                           'accepted_hash': digest(regular(work / 'accepted.json', self.runs))}})
        return report

    def audit(self, name):
        work = self.work(name); a = self.accepted(work)
        events = self.legacy().verify_events(work)
        require([r['state'] for r in events] == ['ENVIRONMENT_PINNED', 'ISOLATION_VERIFIED', 'EVALUATION_FROZEN', 'EVALUATING', 'EVALUATION_COMPLETED'], 'AUDIT_STATES')
        report = self.read_json(work, 'report.json'); checkpoint = self.read_json(work, 'checkpoint.json')
        require(not (work / 'active.lock').exists(), 'ACTIVE_OR_FAILED')
        require(checkpoint['assessment_hash'] == digest(regular(work / 'assessment.lock', self.runs)), 'AUDIT_ASSESSMENT')
        require(checkpoint['last_event_hash'] == events[-1]['hash'] and events[-1]['payload_hash'] == checkpoint['report_hash'], 'AUDIT_EVENTS')
        require(checkpoint['report_hash'] == digest(regular(work / 'report.json', self.runs)) and
                checkpoint['accepted_hash'] == digest(regular(work / 'accepted.json', self.runs)), 'AUDIT_CHECKPOINT')
        require(digest(regular(work / 'sessions.json', self.runs)) == report['sessions_hash'], 'AUDIT_SESSIONS')
        require(report['candidate_sha'] == a['candidate_sha'] and report['manifest_hash'] == a['manifest_hash'], 'AUDIT_IDENTITY')
        for p, h in report['trace_hashes'].items():
            require(digest(regular(work / p, self.runs)) == h, 'AUDIT_TRACE')
        return {'audit': 'VERIFIED', 'report_hash': checkpoint['report_hash'],
                'manifest_hash': a['manifest_hash'], 'candidate_sha': a['candidate_sha']}
