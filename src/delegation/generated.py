"""Task-specific generated repair intake; candidate bytes only execute in Docker."""
import importlib.util
import os
from pathlib import Path
import re
import secrets
import time

from delegation.core import IMAGE
from evaluation.sandbox import capture
from evaluation.core import (canonical, digest, findings, judge, load_json, policy,
                             regular, require, write_new, EvaluationError)

TASK = 'review-input-contract-v1'
ARTIFACT = 'scripts/review.py'
BASELINE_HASH = '7d342aa1fc92afaeea8b7aee834650965b885f167975fd2d4f18e5c31ee80b6e'
DEGRADED = b'import json\nprint(json.dumps({"findings":[],"cpu_seconds":0}))\n'
SOURCES = ['src/delegation/core.py', 'src/delegation/generated.py', 'src/evaluation/generated.py',
           'scripts/generated_repair.py', 'fixtures/generated_repair/baseline.py',
           'fixtures/generated_repair/contract.json']


def git(repo, *args):
    result = capture(['git', '-c', 'core.hooksPath=/dev/null', '-c', 'core.fsmonitor=false', '-C', str(repo), *args],
                            env={'PATH': '/opt/homebrew/bin:/usr/bin:/bin', 'HOME': '/nonexistent',
                                 'GIT_CONFIG_NOSYSTEM': '1', 'GIT_NO_REPLACE_OBJECTS': '1', 'GIT_CONFIG_GLOBAL': '/dev/null'},
                            timeout=10, limit=1048576)
    require(not result['error'] and result['exit'] == 0, 'GIT_FAILED')
    return result['stdout']


def artifact(repo, sha):
    require(type(sha) is str and re.fullmatch('[a-f0-9]{40}', sha), 'COMMIT_SHA')
    require(git(repo, 'cat-file', '-t', sha).strip() == b'commit', 'COMMIT_TYPE')
    tree = git(repo, 'ls-tree', sha, '--', ARTIFACT).split()
    require(len(tree) == 4 and tree[:2] == [b'100644', b'blob'], 'ARTIFACT_TYPE')
    size = git(repo, 'cat-file', '-s', sha + ':' + ARTIFACT).strip()
    require(size.isdigit() and 0 < int(size) <= 65536, 'ARTIFACT_SIZE')
    value = git(repo, 'show', sha + ':' + ARTIFACT)
    require(0 < len(value) <= 65536, 'ARTIFACT_SIZE')
    return value


def cases(hidden=False):
    """Generate evaluator-owned synthetic cases; return no individual hidden observations."""
    tag = secrets.token_hex(8) if hidden else 'public00'
    path = 'case_' + tag + '.py'
    line = secrets.randbelow(50) + 2 if hidden else 7
    def valid(patch, expected):
        return {'stdin': canonical({'path': path, 'patch': patch}).decode(),
                'expected': [[path, n, rule] for n, rule in expected], 'exit': 0}
    prefix = f'@@ -{line},1 +{line},2 @@\n'
    result = [valid(prefix + '+eval(data)', [(line, 'dynamic-eval')]),
              valid(prefix + '+subprocess.run(cmd, shell=True)', [(line, 'shell-execution')]),
              valid(prefix + '+safe(data)', []),
              valid(prefix + ' context\n+eval(data)', [(line+1, 'dynamic-eval')]),
              valid(prefix + '+# comment\n+eval(data)', [(line+1, 'dynamic-eval')])]
    invalid = ['', '{', canonical({'path': path, 'patch': 'x', 'extra': 1}).decode(),
               canonical({'path': '../bad.py', 'patch': 'x'}).decode(),
               canonical({'path': path, 'patch': 7}).decode()]
    if hidden:
        # Different rejection categories from the public examples; values stay internal.
        invalid = [canonical([tag]).decode(), canonical({'path': path}).decode(),
                   canonical({'path': path, 'patch': ''}).decode(),
                   canonical({'path': 'case_A'+tag+'.py', 'patch': 'x'}).decode(),
                   canonical({'path': path, 'patch': tag * 1030}).decode()]
    result.extend({'stdin': value, 'expected': None, 'exit': 2} for value in invalid)
    return result


class Controller:
    def __init__(self, root):
        self.root = Path(root).resolve()
        spec = importlib.util.spec_from_file_location('generated_legacy_gate', self.root/'scripts/evaluate_fixture.py')
        self.gate = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.gate)
        self.gate.SOURCES = [*self.gate.SOURCES, *SOURCES]
        self.runs = self.root/'runs'

    def work(self, name):
        require(type(name) is str and re.fullmatch('generated-[a-f0-9]{24}', name), 'RUN_ID')
        path = self.runs/name
        require(path.is_dir() and not path.is_symlink() and not self.runs.is_symlink(), 'RUN_BOUNDARY')
        return path

    def prepare(self):
        require(not self.runs.is_symlink(), 'RUN_BOUNDARY')
        self.runs.mkdir(exist_ok=True)
        work = self.runs/('generated-'+secrets.token_hex(12))
        work.mkdir(mode=0o700)
        write_new(self.runs/'generated-repair.lock', canonical({'run_id': work.name}))
        started = time.monotonic()
        box = self.gate.Sandbox(self.root, work, IMAGE)
        environment, image = box.environment(), box.image_info(IMAGE)
        require(image['id'] == IMAGE, 'IMAGE_CHANGED')
        self.gate.save(work, 'environment.json', {'environment': environment, 'image': image})
        self.gate.event(work, 'ENVIRONMENT_PINNED', digest(regular(work/'environment.json', self.runs)))
        self.gate.gate(work)
        self.gate.save(work, 'budget.json', {'machine_seconds': time.monotonic()-started})
        return work.name

    def freeze(self, name):
        work = self.work(name)
        self.gate.verify_gate(work)
        require(not (work/'manifest.json').exists() and not (work/'packet').exists(), 'ALREADY_FROZEN')
        require(load_json(regular(self.root/'fixtures/evaluation/policy.json', self.root)) == policy(), 'POLICY_MISMATCH')
        require(load_json(regular(self.runs/'generated-repair.lock', self.runs)) == {'run_id': name}, 'GLOBAL_LOCK')
        baseline = regular(self.root/'fixtures/generated_repair/baseline.py', self.root, 65536)
        require(digest(baseline) == BASELINE_HASH, 'BASELINE_CHANGED')
        contract = load_json(regular(self.root/'fixtures/generated_repair/contract.json', self.root))
        public = cases()
        # Every evaluator source must already be committed before the experiment starts.
        head = git(self.root, 'rev-parse', 'HEAD').decode().strip()
        sources = self.gate.source_hashes()
        for path, value in sources.items():
            require(digest(git(self.root, 'show', head+':'+path)) == value, 'EVALUATOR_NOT_COMMITTED')
        packet = work/'packet'
        (packet/'scripts').mkdir(parents=True)
        write_new(packet/ARTIFACT, baseline)
        write_new(packet/'contract.json', canonical(contract)+b'\n')
        write_new(packet/'public.json', canonical(public)+b'\n')
        git(packet, 'init', '--template=', '--initial-branch=generated')
        git(packet, 'add', '--', ARTIFACT, 'contract.json', 'public.json')
        git(packet, '-c', 'user.name=Fixture Controller', '-c', 'user.email=fixture@example.invalid',
            'commit', '-m', TASK+' frozen baseline '+secrets.token_hex(16))
        baseline_sha = git(packet, 'rev-parse', 'HEAD').decode().strip()
        self.gate.save(work, 'public.json', public)
        self.gate.save(work, 'hidden.json', cases(True))
        manifest = {'task': TASK, 'baseline_sha': baseline_sha, 'baseline_hash': BASELINE_HASH,
                    'evaluator_sha': head, 'sources': sources, 'policy': policy(),
                    'contract_hash': digest(canonical(contract)),
                    'git_config_hash': digest(regular(packet/'.git/config', packet)),
                    'packet_files': {p: digest(regular(packet/p, packet)) for p in (ARTIFACT, 'contract.json', 'public.json')},
                    'dataset_hashes': {p: digest(regular(work/(p+'.json'), self.runs)) for p in ('public', 'hidden')},
                    'environment_hash': digest(regular(work/'environment.json', self.runs)),
                    'gate_hash': digest(regular(work/'gate.json', self.runs)),
                    'budget_hash': digest(regular(work/'budget.json', self.runs))}
        self.gate.save(work, 'manifest.json', manifest)
        self.gate.event(work, 'EVALUATION_FROZEN', digest(regular(work/'manifest.json', self.runs)))
        return {'run_id': name, 'baseline_sha': baseline_sha,
                'manifest_hash': digest(regular(work/'manifest.json', self.runs)), 'status': 'FROZEN'}

    def frozen(self, work):
        self.gate.verify_gate(work)
        rows = self.gate.verify_events(work)
        m = self.gate.read(work, 'manifest.json')
        require(m['task'] == TASK and m['sources'] == self.gate.source_hashes() and
                m['policy'] == policy() and m['baseline_hash'] == BASELINE_HASH, 'MANIFEST_CHANGED')
        frozen = [r for r in rows if r['state'] == 'EVALUATION_FROZEN']
        require(len(frozen) == 1 and frozen[0]['payload_hash'] == digest(regular(work/'manifest.json', self.runs)), 'MANIFEST_ANCHOR')
        for label in ('public', 'hidden'):
            require(digest(regular(work/(label+'.json'), self.runs)) == m['dataset_hashes'][label], 'DATASET_CHANGED')
        for label in ('environment', 'gate', 'budget'):
            require(digest(regular(work/(label+'.json'), self.runs)) == m[label+'_hash'], 'MANIFEST_CHANGED')
        return m

    def intake(self, work, m, sha):
        repo = work/'packet'
        require(not any(p.is_symlink() for p in (repo/'.git').rglob('*')), 'GIT_SYMLINK')
        require(digest(regular(repo/'.git/config', repo)) == m['git_config_hash'], 'GIT_CONFIG_CHANGED')
        require(not (repo/'.git/commondir').exists() and not (repo/'.git/objects/info/alternates').exists(), 'GIT_BOUNDARY')
        baseline = artifact(repo, m['baseline_sha'])
        candidate = artifact(repo, sha)
        require(digest(baseline) == m['baseline_hash'], 'BASELINE_CHANGED')
        require(sha != m['baseline_sha'] and baseline != candidate, 'CANDIDATE_NOT_DISTINCT')
        git(repo, 'merge-base', '--is-ancestor', m['baseline_sha'], sha)
        require(git(repo, 'diff', '--no-ext-diff', '--no-textconv', '--name-only', m['baseline_sha'], sha).splitlines() == [ARTIFACT.encode()], 'DIFF_BOUNDARY')
        require(git(repo, 'rev-parse', 'HEAD').decode().strip() == sha, 'OLD_SHA')
        require(not git(repo, 'status', '--porcelain', '--untracked-files=all'), 'DIRTY_PACKET')
        require(regular(repo/ARTIFACT, repo, 65536) == candidate, 'ARTIFACT_CHANGED')
        for path, value in m['packet_files'].items():
            if path != ARTIFACT:
                require(digest(regular(repo/path, repo)) == value, 'PACKET_CHANGED')
        return baseline, candidate

    def evaluate(self, name, sha):
        from evaluation.generated import observe
        work = self.work(name)
        m = self.frozen(work)
        require(not (work/'evaluation-lock.json').exists(), 'RUN_ALREADY_USED')
        baseline, candidate = self.intake(work, m, sha)
        # This single global lock is never automatically removed, including after failure.
        require(load_json(regular(self.runs/'generated-repair.lock', self.runs)) == {'run_id': name}, 'GLOBAL_LOCK')
        self.gate.save(work, 'evaluation-lock.json', {'baseline_sha': m['baseline_sha'], 'candidate_sha': sha,
                        'manifest_hash': digest(regular(work/'manifest.json', self.runs))})
        self.gate.event(work, 'EVALUATING', digest(regular(work/'evaluation-lock.json', self.runs)))
        try:
            charged = self.gate.read(work, 'budget.json')['machine_seconds']
            require(type(charged) in (int, float) and 0 < charged < 1200, 'RUN_BUDGET')
            deadline = time.monotonic()+1200-charged
            box = self.gate.sandbox(work)
            box.deadline = deadline
            records = {}
            programs = {'baseline': baseline, 'candidate': candidate, 'degraded': DEGRADED}
            for label, content in programs.items():
                program = work/(label+'.py')
                write_new(program, content)
                program.chmod(0o444)
                observations = []
                for case in self.gate.read(work, 'public.json') + self.gate.read(work, 'hidden.json'):
                    repeats = []
                    for _ in range(3):
                        require(time.monotonic() < deadline, 'RUN_DEADLINE')
                        outcome = box.run(program, case['stdin'].encode(), timeout=min(30, deadline-time.monotonic()))
                        observation = observe(outcome, case)
                        require(not observation['safety_failure'] and observation['kind'] not in
                                ('EXECUTION_FAILURE', 'UNEXPECTED_EXIT'), 'EXECUTION_FAULT')
                        repeats.append(observation)
                    observations.append(repeats)
                records[label] = observations
            metrics, unstable = self.gate.compare_records(records)
            unstable |= any(len({x['execution_state_hash'] for x in row}) != 1
                            for rows in records.values() for row in rows)
            safety = all(not x['safety_failure'] for rows in records.values() for row in rows for x in row)
            decision = judge(metrics['baseline'], metrics['candidate'], safety=safety, contaminated=unstable)
            control = judge(metrics['baseline'], metrics['degraded'], safety=safety, contaminated=unstable)
            if control['status'] != 'FAIL' and decision['status'] != 'FAIL':
                decision = {'status': 'HOLD', 'reasons': ['DEGRADED_CONTROL_INVALID']}
            self.frozen(work)
            self.intake(work, m, sha)
            for label, content in programs.items():
                require(regular(work/(label+'.py'), self.runs, 65536) == content, 'ARTIFACT_CHANGED')
            self.gate.save(work, 'metrics.private.json', records)
            report = {'task': TASK, 'baseline_sha': m['baseline_sha'], 'candidate_sha': sha,
                      'artifact_hashes': {label: digest(value) for label, value in programs.items()},
                      'manifest_hash': digest(regular(work/'manifest.json', self.runs)),
                      'private_metrics_hash': digest(regular(work/'metrics.private.json', self.runs)),
                      'decision': decision, 'unstable': unstable, 'degraded_control': control, 'counts': {k: {'public_correct': sum(v['correct'][:10]),
                       'hidden_correct': sum(v['correct'][10:]), 'failures': v['failures'], 'median_seconds': v['latency'], 'cost_usd': 0} for k,v in metrics.items()},
                      'claim': 'fixture comparison only; no adoption or generation-quality claim'}
            self.gate.save(work, 'report.json', report)
            self.gate.event(work, 'EVALUATION_COMPLETED', digest(regular(work/'report.json', self.runs)))
            events = self.gate.verify_events(work)
            self.gate.save(work, 'checkpoint.json', {'report_hash': digest(regular(work/'report.json', self.runs)),
                            'manifest_hash': report['manifest_hash'], 'last_event_hash': events[-1]['hash']})
            return report
        except Exception as error:
            self.gate.save(work, 'stopped.json', {'status': 'STOPPED', 'reason': str(error) if isinstance(error, EvaluationError) else 'CONTROLLER_ERROR',
                            'pending_container': getattr(error, 'pending_container', None)})
            self.gate.event(work, 'EVALUATION_STOPPED', digest(regular(work/'stopped.json', self.runs)))
            raise

    def audit(self, name):
        work = self.work(name)
        m = self.frozen(work)
        rows = self.gate.verify_events(work)
        require([r['state'] for r in rows] == ['ENVIRONMENT_PINNED', 'ISOLATION_VERIFIED', 'EVALUATION_FROZEN', 'EVALUATING', 'EVALUATION_COMPLETED'], 'AUDIT_STATES')
        checkpoint = self.gate.read(work, 'checkpoint.json')
        require(checkpoint['report_hash'] == digest(regular(work/'report.json', self.runs)) and
                checkpoint['last_event_hash'] == rows[-1]['hash'], 'AUDIT_CHECKPOINT')
        report = self.gate.read(work, 'report.json')
        self.intake(work, m, report['candidate_sha'])
        lock = self.gate.read(work, 'evaluation-lock.json')
        require(report['baseline_sha'] == lock['baseline_sha'] == m['baseline_sha'] and
                report['candidate_sha'] == lock['candidate_sha'] and report['manifest_hash'] == lock['manifest_hash'] ==
                digest(regular(work/'manifest.json', self.runs)), 'AUDIT_IDENTITY')
        for label, sha in [('baseline', report['baseline_sha']), ('candidate', report['candidate_sha'])]:
            require(digest(artifact(work/'packet', sha)) == report['artifact_hashes'][label] ==
                    digest(regular(work/(label+'.py'), self.runs, 65536)), 'AUDIT_ARTIFACT')
        require(digest(regular(work/'degraded.py', self.runs)) == report['artifact_hashes']['degraded'] == digest(DEGRADED), 'AUDIT_CONTROL')
        require(digest(regular(work/'metrics.private.json', self.runs)) == report['private_metrics_hash'], 'AUDIT_METRICS')
        return {'run_id': name, 'audit': 'VERIFIED', 'report_hash': digest(regular(work/'report.json', self.runs)),
                'manifest_hash': report['manifest_hash'], 'last_event_hash': rows[-1]['hash']}
