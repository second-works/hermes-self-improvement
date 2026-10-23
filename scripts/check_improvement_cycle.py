#!/usr/bin/env python3
"""Offline controller rehearsal. No model call, scheduling, or service change."""
import importlib.util
import json
from pathlib import Path
import sys
import time
import secrets

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from delegation.cycle import transfer_cases, acceptance
from delegation.execution import execute_batch, execution_cases
from delegation.patch import apply_operations, counter_cases, OPERATION_IDS
from evaluation.core import canonical, digest, load_json, regular, require, EvaluationError
from evaluation.sandbox import Sandbox
from delegation.core import candidate_files, public_cases, IMAGE
from delegation.sandbox import DelegationSandbox

spec = importlib.util.spec_from_file_location('trusted_delegate', ROOT / 'scripts/delegate_skill.py')
controller = importlib.util.module_from_spec(spec)
spec.loader.exec_module(controller)
controller.PREPARATION = ROOT / 'runs/delegation-prepare-74e7a25c9496-3'
controller.verify_preparation()
work = ROOT / 'runs' / ('cycle-offline-' + time.strftime('%Y%m%dT%H%M%SZ', time.gmtime()) + '-' + secrets.token_hex(4))
work.mkdir(mode=0o700)
report = {'classification': 'PUBLIC', 'model_calls': 0, 'mode': 'CONTROLLER_REHEARSAL',
          'risk_tier': 'HIGH', 'status': 'STOPPED', 'adoption': 'NOT_REQUESTED'}
try:
    deadline = time.monotonic() + 600
    box = DelegationSandbox(ROOT, work, IMAGE, preparation=controller.PREPARATION, deadline=deadline)
    report['environment'] = box.environment()
    report['image'] = box.image_info(IMAGE)
    report['gates'] = controller.gate(box)
    source = ROOT / 'runs/delegation-20261017T112524Z-cdfed6305bab/repair-candidate-1'
    expected = load_json(regular(source.parent / 'repair-comparison-1.json', ROOT / 'runs'))['hashes']
    files = {name: regular(source / name, ROOT / 'runs').decode() for name in ('SKILL.md', 'scripts/review.py')}
    require(candidate_files(files) == expected, 'REPAIR_SEED_CHANGED')
    cases = public_cases() + counter_cases() + transfer_cases()
    unit = Sandbox(ROOT, work, IMAGE, deadline=deadline)
    before = controller.check_candidate(unit, work, files, 'baseline', cases)
    repaired = {**files, 'scripts/review.py': apply_operations(files['scripts/review.py'], {'operations': list(OPERATION_IDS)})}
    after = controller.check_candidate(unit, work, repaired, 'repaired', cases)
    decision = acceptance(before, after)
    report.update(baseline=before, improved=after, decision=decision)
    require(decision == 'ACCEPTED', 'REHEARSAL_IMPROVEMENT_FAILED')
    jobs = execution_cases()
    results = execute_batch(unit, work / 'repaired/scripts/review.py', [job['input'] for job in jobs])
    checks = [controller.correct_output(result, job) for result, job in zip(results, jobs)]
    controller.save(work, 'execution-results.json', results)
    report.update(execution_checks=checks, execution_result_owner='controller_from_actual_script_stdout')
    require(all(checks), 'CONTROLLED_EXECUTION_FAILED')
    # Deliberately offer the old buggy bytes again, then retain the successful bytes.
    regression = controller.check_candidate(unit, work, files, 'regression-proposal', cases)
    rejected = acceptance(after, regression)
    report.update(regression=regression, regression_decision=rejected)
    require(rejected == 'REJECTED_REGRESSION', 'REHEARSAL_REGRESSION_NOT_REJECTED')
    unchanged = apply_operations(repaired['scripts/review.py'], {'operations': []})
    require(unchanged == repaired['scripts/review.py'], 'NOOP_MODIFIED')
    require(candidate_files({name: regular(source / name, ROOT / 'runs').decode() for name in files}) == expected,
            'SOURCE_CHANGED')
    report.update(status='VERIFIED', baseline=before, improved=after, decision=decision,
                  regression=regression, regression_decision=rejected,
                  retained_hashes=candidate_files(repaired), source_hashes=expected,
                  public_cases=9, transfer_cases=6,
                  limitation='Trusted operation replay, not a new Gemma judgment or sealed independent evaluation.')
except Exception as error:
    report['reason'] = str(error) if isinstance(error, EvaluationError) else type(error).__name__
    raise
finally:
    controller.save(work, 'report.json', report)
    print(json.dumps({'run': str(work), 'status': report['status'], 'model_calls': 0}))
