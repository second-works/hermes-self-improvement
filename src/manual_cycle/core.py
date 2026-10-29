"""Supervisor orchestration over frozen evaluation and explicit fixture approval.

Only PUBLIC packets cross to the generator. Journal/hidden/registry stay with
the supervisor. Hashes detect accidental drift, not a malicious same-OS user.
"""
from contextlib import contextmanager
from datetime import datetime, timezone
import difflib
import fcntl
import math
import os
from pathlib import Path
import re
import time

from adoption.core import Controller as Adoption, identifier, read, save, stamp, syncdir, utc
from adoption.regression import DockerRegression
from delegation.generated import Controller as Generated, ARTIFACT, IMAGE, artifact, git
from evaluation.core import EvaluationError, canonical, digest, load_json, regular, require, write_new
from evaluation.generated import observe
from evaluation.sandbox import Sandbox

STATES = {'INITIALIZED', 'BUSY', 'OBSERVED', 'PROPOSED', 'BUILDING', 'PUBLIC_FAILED',
          'CANDIDATE_READY', 'AWAITING_PR', 'AWAITING_APPROVAL', 'ADOPTED', 'REOBSERVED',
          'RECOVERY_REQUIRED', 'ROLLED_BACK', 'TRIAL_AWAITING_APPROVAL', 'NO_CHANGE', 'REUSED', 'HOLD', 'FAIL', 'STOPPED'}
DECISIONS = {'REPAIR': 'PROPOSED', 'NO_CHANGE': 'NO_CHANGE', 'REUSE': 'REUSED',
             'INSUFFICIENT_EVIDENCE': 'HOLD', 'INSUFFICIENT_AUTHORITY': 'HOLD', 'FORBIDDEN': 'FAIL'}
SOURCES = ['src/manual_cycle/core.py', 'scripts/manual_cycle.py', 'fixtures/manual_cycle/dependency.json',
           'src/adoption/core.py', 'src/adoption/regression.py']


class BudgetSandbox(Sandbox):
    def command(self, *args, timeout=30, **kwargs):
        remaining = self.deadline - time.monotonic()
        require(remaining > 0, 'CYCLE_BUDGET')
        return super().command(*args, timeout=min(timeout, remaining), **kwargs)


class EvaluatedAdoption(Adoption):
    def __init__(self, cycle, trial=None):
        self.cycle = cycle
        super().__init__(cycle.repo, cycle.area / ('adoption-' + trial if trial else 'adoption'))

    def source(self):
        c = self.cycle
        evaluated = c.receipt('evaluation')
        g, run, work = c.generated()
        audit = g.audit(run)
        require(audit['report_hash'] == evaluated['evaluation_hash'], 'EVALUATION_CHANGED')
        report = read(work / 'report.json')
        require(report['decision']['status'] == 'PASS' and report['candidate_sha'] ==
                evaluated['candidate_sha'], 'EVALUATION_NOT_PASS')
        versions = {label: artifact(work / 'packet', report[label + '_sha'])
                    for label in ('baseline', 'candidate')}
        require(all(digest(data) == report['artifact_hashes'][label]
                    for label, data in versions.items()), 'ARTIFACT_CHANGED')
        patch = ''.join(difflib.unified_diff(versions['baseline'].decode().splitlines(True),
            versions['candidate'].decode().splitlines(True), fromfile='a/' + ARTIFACT,
            tofile='b/' + ARTIFACT, n=0))
        packet = {'schema_version': 1, 'classification': 'PUBLIC', 'issue': 9,
            'repository': 'second-works/hermes-self-improvement', 'run_id': c.name,
            'baseline_sha': report['baseline_sha'], 'candidate_sha': report['candidate_sha'],
            'evaluation_hash': audit['report_hash'], 'manifest_hash': audit['manifest_hash'],
            'observation_hash': digest(canonical(c.receipt('observation'))),
            'proposal_hash': digest(canonical(c.receipt('proposal'))),
            'artifact_path': ARTIFACT, 'before_hash': digest(versions['baseline']),
            'after_hash': digest(versions['candidate']), 'diff_hash': digest(patch.encode()),
            'public_hash': digest(regular(work / 'public.json', c.repo)), 'allowlist': [ARTIFACT],
            'evaluation': report['decision'], 'counts': report['counts'],
            'merge_is_adoption': False, 'unverified': ['Human adoption/recovery acceptance',
                'General quality and production']}
        return packet, versions, patch

    def public_cases(self):
        _, _, work = self.cycle.generated()
        return read(work / 'public.json')


class Cycle:
    def __init__(self, repo, name):
        identifier(name)
        require(name.startswith('cycle-'), 'CYCLE_ID')
        self.repo, self.name = Path(repo).resolve(), name
        self.area = self.repo / 'runs' / name
        require(not (self.repo / 'runs').is_symlink() and not self.area.is_symlink(), 'CYCLE_BOUNDARY')
        self.deadline = None

    def initialize(self, expires_at):
        now = datetime.now(timezone.utc).timestamp()
        require(0 < stamp(expires_at) - now <= 86400, 'CYCLE_EXPIRY')
        # Merge and acceptance are independently checked by the trusted supervisor;
        # the public dependency receipt records both, without importing old approvals.
        dependency = read(self.repo / 'fixtures/manual_cycle/dependency.json')
        require(dependency['issue'] == 8 and dependency['product_acceptance'] == 'ACCEPTED', 'DEPENDENCY')
        git(self.repo, 'merge-base', '--is-ancestor', dependency['merge_sha'], 'HEAD')
        self.area.parent.mkdir(exist_ok=True)
        save(self.area.parent / 'manual-cycle.lock', {'run_id': self.name})
        self.area.mkdir(mode=0o700)
        config = {'run_id': self.name, 'classification': 'PUBLIC',
             'expires_at': expires_at, 'machine_limit_seconds': 1200, 'generation_limit': 2,
             'dependency_hash': digest(canonical(dependency)), 'gemma': 'OFF', 'api_calls': 0}
        save(self.area / 'config.json', config)
        self.event('INITIALIZED', {'config_hash': digest(canonical(config))})

    def rows(self):
        data = regular(self.area / 'events.jsonl', self.repo / 'runs', 2 * 1024 * 1024)
        rows = [load_json(line) for line in data.splitlines()]
        previous, charged = '0' * 64, 0
        for i, row in enumerate(rows):
            require(type(row) is dict and set(row) == {'run_id','sequence','previous','at','state',
                    'machine_seconds','details','hash'}, 'CYCLE_JOURNAL')
            body = {k:v for k,v in row.items() if k != 'hash'}
            seconds = row['machine_seconds']
            require(row['run_id'] == self.name and row['sequence'] == i and row['previous'] == previous
                    and row['state'] in STATES and digest(canonical(body)) == row['hash']
                    and type(seconds) in (int,float) and math.isfinite(seconds) and seconds >= charged,
                    'CYCLE_JOURNAL')
            previous, charged = row['hash'], seconds
        require(rows and rows[0]['state'] == 'INITIALIZED', 'CYCLE_JOURNAL')
        return rows

    def event(self, state, details, seconds=None):
        path = self.area / 'events.jsonl'
        rows = self.rows() if path.exists() else []
        require(state in STATES, 'CYCLE_STATE')
        row = {'run_id': self.name, 'sequence': len(rows),
               'previous': rows[-1]['hash'] if rows else '0' * 64, 'at': utc(), 'state': state,
               'machine_seconds': seconds if seconds is not None else (rows[-1]['machine_seconds'] if rows else 0),
               'details': details}
        row['hash'] = digest(canonical(row))
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND | os.O_NOFOLLOW, 0o600)
        try:
            require(os.write(fd, canonical(row) + b'\n') == len(canonical(row)) + 1, 'CYCLE_JOURNAL_WRITE')
            os.fsync(fd)
        finally:
            os.close(fd)
        syncdir(self.area)
        return row

    def receipt(self, label):
        matches = [r['details'][label] for r in self.rows() if label in r['details']]
        require(len(matches) == 1, 'CYCLE_RECEIPT')
        return matches[0]

    @contextmanager
    def guard(self):
        require(read(self.area.parent / 'manual-cycle.lock') == {'run_id': self.name}, 'GLOBAL_CYCLE_LOCK')
        fd = os.open(self.area.parent / 'manual-cycle.lock', os.O_RDWR | os.O_NOFOLLOW)
        try:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise EvaluationError('CONCURRENT_CYCLE') from None
            yield
        finally:
            os.close(fd)

    def interrupted(self):
        rows = self.rows()
        if rows[-1]['state'] != 'BUSY':
            return rows[-1]['state']
        a = self.active_adoption()
        state = a.state('target') if (a.area / 'targets/target.json').exists() else None
        result = 'RECOVERY_REQUIRED' if state in ('RECOVERY_REQUIRED','ADOPTED','ROLLED_BACK') else 'STOPPED'
        started = [r for r in rows if r['state'] == 'BUSY' and 'started_monotonic' in r['details']][-1]
        details = started['details']
        # Across a process restart on the same boot, elapsed wall time is a
        # conservative upper bound. Across an OS reboot, reserve the full budget.
        same_boot = abs((time.time() - time.monotonic()) - details['boot_epoch']) < 5
        charged = min(1200, started['machine_seconds'] + max(0, time.monotonic() - details['started_monotonic'])) if same_boot else 1200
        self.event(result, {'reason': 'INTERRUPTED', 'operation': details['operation']}, charged)
        return result

    def status(self):
        with self.guard():
            state = self.interrupted()
            rows = self.rows()
            return {'run_id': self.name, 'state': state, 'machine_seconds': rows[-1]['machine_seconds'],
                    'last_event_hash': rows[-1]['hash'], 'human_acceptance': 'NOT_RECORDED'}

    @contextmanager
    def operation(self, name, allowed):
        with self.guard():
            state = self.interrupted()
            require(state in allowed, 'CYCLE_STATE')
            config = read(self.area / 'config.json')
            rows = self.rows()
            started = time.monotonic()
            charged = rows[-1]['machine_seconds']
            try:
                require(config['run_id'] == self.name and config['machine_limit_seconds'] == 1200 and
                        config['generation_limit'] == 2 and config['gemma'] == 'OFF' and config['api_calls'] == 0,
                        'CYCLE_CONFIG')
                require(digest(canonical(config)) == rows[0]['details']['config_hash'], 'CYCLE_CONFIG')
                require(datetime.now(timezone.utc).timestamp() < stamp(config['expires_at']), 'CYCLE_EXPIRED')
                require(charged < 1200, 'CYCLE_BUDGET')
                self.deadline = started + 1200 - charged
                self.event('BUSY', {'operation': name, 'previous_state': state,
                    'started_monotonic': started, 'boot_epoch': time.time() - started})
                yield
                require(time.monotonic() < self.deadline, 'CYCLE_BUDGET')
                require(self.rows()[-1]['state'] != 'BUSY', 'INCOMPLETE_OPERATION')
                last = self.rows()[-1]
                self.event(last['state'], {'operation_completed': name}, charged + time.monotonic() - started)
            except Exception as error:
                a = self.active_adoption()
                deployed = a.state('target') if (a.area / 'targets/target.json').exists() else None
                result = 'RECOVERY_REQUIRED' if deployed in ('RECOVERY_REQUIRED','ADOPTED','ROLLED_BACK') else 'STOPPED'
                self.event(result, {'reason': str(error) if isinstance(error, EvaluationError) else 'CONTROLLER_ERROR',
                           'operation': name}, charged + time.monotonic() - started)
                raise

    def generated(self):
        g = Generated(self.repo)
        g.gate.SOURCES = [*g.gate.SOURCES, *SOURCES]
        if self.deadline is not None:
            g.gate.Sandbox = lambda *args, **kwargs: BudgetSandbox(*args, **dict(kwargs, deadline=self.deadline))
        run = self.receipt('frozen')['run_id']
        return g, run, g.work(run)

    def box(self, work):
        return BudgetSandbox(self.repo, work, IMAGE, deadline=self.deadline)

    def start(self):
        with self.operation('observe', {'INITIALIZED'}):
            g = Generated(self.repo)
            g.gate.SOURCES = [*g.gate.SOURCES, *SOURCES]
            g.gate.Sandbox = lambda *args, **kwargs: BudgetSandbox(*args, **dict(kwargs, deadline=self.deadline))
            run = g.prepare()
            frozen = g.freeze(run)
            self.event('BUSY', {'operation': 'observe', 'frozen': frozen})
            work = g.work(run)
            # A single PUBLIC failure is the observed problem, never hidden feedback.
            case = read(work / 'public.json')[5]
            box = self.box(work)
            result = observe(box.run(work / 'packet' / ARTIFACT, case['stdin'].encode(), timeout=15), case)
            require(not result['safety_failure'], 'OBSERVATION_INFRASTRUCTURE')
            observation = {'classification': 'PUBLIC', 'fixture_id': 'public-5',
                'source_sha': frozen['baseline_sha'], 'manifest_hash': frozen['manifest_hash'],
                'case_hash': digest(canonical(case)), 'kind': result['kind'], 'correct': result['correct'],
                'answer_hash': result['answer_hash'], 'execution_state_hash': result['execution_state_hash']}
            self.event('OBSERVED', {'observation': observation})

    def diagnose(self, proposal):
        with self.operation('diagnose', {'OBSERVED'}):
            require(type(proposal) is dict and set(proposal) == {'decision','reason','observation_hash',
                    'baseline_sha','allowlist','classification'}, 'PROPOSAL_SCHEMA')
            decision = proposal['decision']
            require(decision in DECISIONS and proposal['classification'] == 'PUBLIC' and
                    type(proposal['reason']) is str and 1 <= len(proposal['reason']) <= 2000, 'PROPOSAL_SCHEMA')
            observation = self.receipt('observation')
            require(proposal['observation_hash'] == digest(canonical(observation)) and
                    proposal['baseline_sha'] == observation['source_sha'] and
                    proposal['allowlist'] == ([ARTIFACT] if decision == 'REPAIR' else []), 'PROPOSAL_BINDING')
            require(decision != 'REPAIR' or not observation['correct'], 'NO_FAILURE')
            self.event(DECISIONS[decision], {'proposal': proposal})

    def handoff(self):
        with self.operation('handoff', {'PROPOSED','PUBLIC_FAILED'}):
            attempts = sum(r['details'].get('generation_started', 0) for r in self.rows())
            require(attempts < 2, 'GENERATION_LIMIT')
            g, _, work = self.generated()
            manifest = g.frozen(work)
            require(not (work / 'evaluation-lock.json').exists(), 'HIDDEN_ALREADY_USED')
            # Verify the immutable baseline and PUBLIC support files before disclosure.
            for path, value in manifest['packet_files'].items():
                if path != ARTIFACT or attempts == 0:
                    require(digest(regular(work / 'packet' / path, self.repo)) == value, 'PACKET_CHANGED')
            self.event('BUILDING', {'generation_started': 1, 'attempt': attempts + 1,
                       'packet': str(work / 'packet'), 'proposal_hash': digest(canonical(self.receipt('proposal')))})
            return {'packet': str(work / 'packet'), 'attempt': attempts + 1}

    def public_check(self, sha):
        with self.operation('public-check', {'BUILDING'}):
            g, _, work = self.generated()
            manifest = g.frozen(work)
            _, data = g.intake(work, manifest, sha)
            number = sum('public_check' in r['details'] for r in self.rows()) + 1
            program = self.area / ('public-candidate-' + str(number) + '.py')
            write_new(program, data)
            box = self.box(self.area)
            outcomes = [observe(box.run(program, case['stdin'].encode(), timeout=15), case)
                        for case in read(work / 'public.json')]
            require(not any(r['safety_failure'] or r['kind'] in ('EXECUTION_FAILURE','UNEXPECTED_EXIT')
                            for r in outcomes), 'PUBLIC_EXECUTION_FAULT')
            good = all(r['correct'] and not r['failed'] for r in outcomes)
            self.event('CANDIDATE_READY' if good else 'PUBLIC_FAILED', {'public_check': {
                'candidate_sha': sha, 'artifact_hash': digest(data), 'passed': good,
                'correct': sum(r['correct'] for r in outcomes), 'total': len(outcomes)}})

    def evaluate(self):
        with self.operation('evaluate', {'CANDIDATE_READY'}):
            check = [r['details']['public_check'] for r in self.rows() if 'public_check' in r['details']][-1]
            g, run, work = self.generated()
            report = g.evaluate(run, check['candidate_sha'], remaining_seconds=self.deadline - time.monotonic())
            audit = g.audit(run)
            evaluation = {'candidate_sha': report['candidate_sha'], 'baseline_sha': report['baseline_sha'],
                'evaluation_hash': audit['report_hash'], 'manifest_hash': audit['manifest_hash'],
                'status': report['decision']['status']}
            if evaluation['status'] != 'PASS':
                self.event(evaluation['status'], {'evaluation': evaluation})
                return evaluation
            self.event('BUSY', {'operation': 'evaluate', 'evaluation': evaluation})
            a = self.adoption()
            packet = a.initialize()
            root = a.area / 'fixtures/target'
            (root / 'scripts').mkdir(parents=True)
            write_new(root / ARTIFACT, regular(a.area / 'baseline.py', self.repo))
            bound = a.register('public-manual-cycle', 'target', root)
            self.event('AWAITING_PR', {'packet_hash': digest(canonical(packet)), 'target': bound})
            return evaluation

    def adoption(self):
        return EvaluatedAdoption(self)

    def active_trial(self):
        trials = [r['details']['active_trial'] for r in self.rows() if 'active_trial' in r['details']]
        return trials[-1] if trials else None

    def active_adoption(self):
        return EvaluatedAdoption(self, self.active_trial())

    def prepare_trial(self, kind):
        require(kind in ('degradation','crash'), 'FAULT_KIND')
        with self.operation('prepare-trial', {'REOBSERVED','ROLLED_BACK'}):
            require(self.receipt('reobservation')['state'] == 'ADOPTED', 'NORMAL_CYCLE_INCOMPLETE')
            require(not self.active_trial() or self.rows()[-2]['state'] == 'ROLLED_BACK', 'TRIAL_PENDING')
            require(not any(r['details'].get('active_trial') == kind for r in self.rows()), 'TRIAL_ALREADY_USED')
            # The successful main target stays untouched; each fault has its own
            # registered root, baseline backup, approvals and durable intent.
            a = EvaluatedAdoption(self, kind)
            a.initialize()
            root = a.area / 'fixtures/target'
            (root / 'scripts').mkdir(parents=True)
            write_new(root / ARTIFACT, regular(a.area / 'baseline.py', self.repo))
            bound = a.register('public-fault-trial', 'target', root)
            self.event('TRIAL_AWAITING_APPROVAL', {'active_trial': kind, 'trial_target': bound})

    def fault_plan(self, request):
        kind = self.active_trial()
        require(kind in ('degradation','crash') and request['operation'] == 'ADOPT', 'FAULT_KIND')
        a = self.active_adoption()
        data = regular(a.area / 'candidate.py', self.repo)
        partial = data[:128] if kind == 'crash' else b'# PUBLIC injected degradation\n'
        return {'classification': 'PUBLIC', 'trial': kind, 'request_hash': digest(canonical(request)),
                'root_binding_hash': request['root_binding_hash'], 'root': request['root'],
                'candidate_sha': request['candidate_sha'], 'evaluation_hash': request['evaluation_hash'],
                'backup_hash': request['backup_hash'], 'expires_at': request['expires_at'],
                'injected_hash': digest(partial), 'injected_bytes': len(partial),
                'expected_state': 'RECOVERY_REQUIRED', 'recovery': 'SEPARATE_HUMAN_APPROVAL'}

    def submit(self, url, head_sha, packet_hash):
        # The trusted supervisor checks GitHub and explicitly records its receipt.
        # This records submission, never CI/review/merge success or human acceptance.
        with self.operation('submit', {'AWAITING_PR'}):
            require(type(url) is str and re.fullmatch(r'https://github.com/second-works/hermes-self-improvement/pull/[1-9][0-9]*', url), 'PR_DESTINATION')
            require(type(head_sha) is str and re.fullmatch('[a-f0-9]{40}', head_sha), 'PR_SHA')
            require(packet_hash == digest(canonical(self.adoption().packet())), 'PR_PACKET')
            self.event('AWAITING_APPROVAL', {'pr': {'url': url, 'head_sha': head_sha, 'packet_hash': packet_hash}})

    def request(self, operation, expires_at, actor):
        with self.operation('request', {'AWAITING_APPROVAL','TRIAL_AWAITING_APPROVAL'} if operation == 'ADOPT' else {'RECOVERY_REQUIRED'}):
            request = self.active_adoption().request('target', operation, expires_at, actor)
            state = ('TRIAL_AWAITING_APPROVAL' if self.active_trial() else 'AWAITING_APPROVAL') if operation == 'ADOPT' else 'RECOVERY_REQUIRED'
            self.event(state,
                       {'request_hash': digest(canonical(request)), 'operation': operation})
            return request

    def execute(self, request, confirmation, fault_confirmation=None):
        operation = request.get('operation') if type(request) is dict else None
        require(operation in ('ADOPT','ROLLBACK'), 'OPERATION')
        with self.operation('execute', {'AWAITING_APPROVAL','TRIAL_AWAITING_APPROVAL'} if operation == 'ADOPT' else {'RECOVERY_REQUIRED'}):
            a = self.active_adoption()
            kind = self.active_trial()
            if kind and operation == 'ADOPT':
                require(fault_confirmation == digest(canonical(self.fault_plan(request))), 'FAULT_CONFIRMATION')
                if kind == 'crash':
                    replace = a.replace
                    def crash(binding, path, data, expected):
                        replace(binding, path, data[:128], expected)
                        os._exit(71)
                    a.replace = crash
            key = a.approve(request, confirmation=confirmation)
            event = a.execute(key, self.regression(a))
            self.event(event['state'], {'adoption' if operation == 'ADOPT' else 'rollback': {
                'approval_hash': key, 'event_hash': event['hash'], 'actual_hash': event['details']['actual_hash']}})
            if kind == 'degradation' and operation == 'ADOPT':
                bound = a.binding('target')
                a.replace(bound, ARTIFACT, b'# PUBLIC injected degradation\n', a.packet()['after_hash'])
                try:
                    a.observe('target', self.regression(a))
                except EvaluationError:
                    require(a.state('target') == 'RECOVERY_REQUIRED', 'FAULT_NOT_DETECTED')
                require(a.state('target') == 'RECOVERY_REQUIRED', 'FAULT_NOT_DETECTED')
                self.event('RECOVERY_REQUIRED', {'fault_confirmation': fault_confirmation,
                           'fault': 'degradation', 'event_hash': a.events('target')[-1]['hash']})

    def regression(self, adoption):
        check = DockerRegression(adoption)
        # Limit every child Docker call to the cycle's remaining machine budget.
        check.deadline = self.deadline
        check.sandbox_factory = BudgetSandbox
        return check

    def reobserve(self):
        with self.operation('reobserve', {'ADOPTED'}):
            a = self.adoption()
            a.observe('target', self.regression(a))
            self.event('REOBSERVED', {'reobservation': {'state': 'ADOPTED',
                'actual_hash': a.actual(a.binding('target'), ARTIFACT)[0],
                'evaluation_hash': a.packet()['evaluation_hash'], 'next_cycle': 'NOT_STARTED'}})
