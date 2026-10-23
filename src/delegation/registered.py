"""File-based selection adapter and deterministic, fail-closed execution controller."""
from pathlib import Path
import time

from delegation.catalog import (CATALOG_VERSION, available_operations,
                                registered_source_hashes, validate_selection)
from delegation.core import IMAGE, correct_output, public_cases
from delegation.cycle import acceptance, transfer_cases
from delegation.execution import execute_batch, execution_cases
from delegation.patch import apply_operations, counter_cases
from evaluation.core import (EvaluationError, canonical, digest, load_json, regular,
                             require, write_new)


def verify_candidate(unit, program, cases):
    results = []
    for case in cases:
        # An execution failure is never a successful 'no findings' result.
        output = execute_batch(unit, program, [case['input']])[0]
        results.append(correct_output(output, case))
    return results


def run(root, source_path, selection_path, output_path, *, execute=False, sandbox_factory=None):
    """Apply one bounded selection. Execute candidate bytes only via Docker Sandbox."""
    root = Path(root).resolve()
    source = regular(source_path, root, 65536)
    baseline = regular(root / 'fixtures/delegation/registered-operations/review.py', root, 65536)
    require(digest(source) in registered_source_hashes(baseline), 'UNREGISTERED_SOURCE')
    selection_bytes = regular(selection_path, root, 4096)
    selection = load_json(selection_bytes)
    operations = validate_selection(selection)
    try:
        text = source.decode('utf-8')
    except UnicodeError:
        raise EvaluationError('SOURCE_ENCODING') from None
    available = available_operations(text)
    require(all(op in available for op in operations), 'OPERATION_NOT_AVAILABLE')
    candidate = apply_operations(text, selection)
    output = Path(output_path).absolute()
    require(output.is_relative_to(root / 'runs') and '..' not in output.parts,
            'RUN_BOUNDARY')
    # Only an existing, non-aliased parent under runs may receive a fresh run.
    for parent in (root / 'runs', *output.parents):
        if parent.is_relative_to(root / 'runs'):
            require(parent.is_dir() and not parent.is_symlink(), 'RUN_PARENT')
    output.mkdir(mode=0o700, exist_ok=False)
    report = {'schema_version': 1, 'catalog_version': CATALOG_VERSION,
              'classification': 'PUBLIC', 'model_calls': 0,
              'selection_origin': 'supplied_file_not_a_new_model_judgment',
              'selection_sha256': digest(selection_bytes), 'operations': list(operations),
              'source_sha256': digest(source), 'candidate_sha256': digest(candidate.encode()),
              'available_before': available, 'status': 'PREPARED_NOT_EXECUTED',
              'adoption': 'NOT_REQUESTED', 'independent_evaluation': 'NOT_RUN'}
    try:
        # Separate copies keep the caller's input out of container mounts.
        baseline_path = output / 'baseline.py'
        candidate_path = output / 'candidate.py'
        write_new(baseline_path, source)
        write_new(candidate_path, candidate.encode())
        baseline_path.chmod(0o444)
        candidate_path.chmod(0o444)
        if execute:
            from evaluation.sandbox import Sandbox
            factory = sandbox_factory or Sandbox
            unit = factory(root, output, IMAGE, deadline=time.monotonic() + 600)
            report['status'] = 'RUNNING'
            report['environment'] = unit.environment()
            report['image'] = unit.image_info(IMAGE)
            require(report['image']['id'] == IMAGE, 'IMAGE_MISMATCH')
            cases = public_cases() + counter_cases() + transfer_cases()
            before = verify_candidate(unit, baseline_path, cases)
            after = verify_candidate(unit, candidate_path, cases)
            decision = acceptance(before, after, candidate == text)
            report.update(before=before, after=after, decision=decision)
            require(all(after) and decision in ('ACCEPTED', 'UNCHANGED'), 'CANDIDATE_REJECTED')
            jobs = execution_cases()
            results = execute_batch(unit, candidate_path, [job['input'] for job in jobs])
            write_new(output / 'execution-results.json', canonical(results) + b'\n')
            require(all(correct_output(result, job) for result, job in zip(results, jobs)),
                    'EXECUTION_MISMATCH')
            report['results_sha256'] = digest(canonical(results))
            report['status'] = 'VERIFIED'
        require(regular(source_path, root, 65536) == source, 'SOURCE_CHANGED')
        require(regular(candidate_path, root, 65536) == candidate.encode(), 'CANDIDATE_CHANGED')
        return report
    except Exception as error:
        report.update(status='FAILED', reason=str(error) if isinstance(error, EvaluationError)
                      else type(error).__name__)
        raise
    finally:
        write_new(output / 'report.json', canonical(report) + b'\n')
