"""Fixed PUBLIC smoke/regression checks through the existing isolated Docker."""
import uuid
from evaluation.core import canonical, digest, load_json, regular, require, write_new
from evaluation.sandbox import Sandbox
from .core import IMAGE, LIMIT, save


class DockerRegression:
    def __init__(self, controller):
        self.controller = controller
        self.deadline = None
        self.sandbox_factory = Sandbox

    def __call__(self, program, operation):
        c = self.controller
        packet, _, _ = c.source()
        expected_hash = packet['after_hash' if operation == 'ADOPT' else 'before_hash']
        data = regular(program, c.area, LIMIT)
        require(digest(data) == expected_hash, 'REGRESSION_ARTIFACT')
        work = c.area / ('check-' + uuid.uuid4().hex)
        work.mkdir(mode=0o700)
        snapshot = work / 'program.py'
        write_new(snapshot, data)
        snapshot.chmod(0o444)
        box = self.sandbox_factory(c.repo, work, IMAGE, deadline=self.deadline)
        environment = box.environment()
        image = box.image_info(IMAGE)
        require(image['id'] == IMAGE, 'IMAGE_ID')
        cases = c.public_cases()
        # Baseline guarantees five valid-input cases; its known rejection defects
        # are not reclassified as successful validation during rollback.
        selected = cases if operation == 'ADOPT' else [r for r in cases if r['exit'] == 0]
        outcomes = []
        for case in selected:
            result = box.run(snapshot, case['stdin'].encode(), timeout=15)
            good = result['exit'] == result['container_exit'] == case['exit'] and not any(
                result[k] for k in ('stderr', 'error', 'oom'))
            try:
                value = load_json(result['stdout'])
                if case['exit'] == 2:
                    good &= value == {'error': 'INVALID_INPUT'}
                else:
                    good &= set(value) == {'findings','cpu_seconds'} and value['cpu_seconds'] == 0 and [
                        [f['path'],f['line'],f['rule']] for f in value['findings']] == case['expected']
            except (KeyError, TypeError, ValueError):
                good = False
            outcomes.append({'passed': bool(good), 'stdout_hash': digest(result['stdout']),
                             'exit': result['exit'], 'container_exit': result['container_exit']})
        save(work / 'result.json', {'classification':'PUBLIC', 'operation':operation,
             'artifact_hash':digest(data), 'image':image, 'environment':environment,
             'cases':outcomes, 'passed':all(r['passed'] for r in outcomes)})
        return all(r['passed'] for r in outcomes)
