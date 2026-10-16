"""Runs only inside the Issue #6 container; preparation never imports wheel code."""
import email.parser
import hashlib
import importlib.metadata
import inspect
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import zipfile

request = json.load(sys.stdin)
mode = request['mode']


def output(value):
    print(json.dumps(value, sort_keys=True))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def normalized(name):
    return re.sub(r'[-_.]+', '-', name).lower()


if mode == 'download':
    Path('/prepare/wheels').mkdir()
    # Wheel-only resolution: do not execute package build hooks or source distributions.
    subprocess.run([sys.executable, '-I', '-m', 'pip', '--isolated', '--disable-pip-version-check',
                    'download', '--no-cache-dir', '--only-binary=:all:',
                    '--index-url=https://pypi.org/simple', '--dest=/prepare/wheels',
                    '--require-hashes', '-r', '/input/requirements.lock'],
                   check=True, timeout=55)
elif mode == 'install':
    wheels = []
    identities = set()
    for path in sorted(Path('/prepare/wheels').iterdir()):
        assert path.is_file() and not path.is_symlink() and path.suffix == '.whl'
        with zipfile.ZipFile(path) as archive:
            metadata_paths = [n for n in archive.namelist() if n.endswith('.dist-info/METADATA')]
            assert len(metadata_paths) == 1
            meta = email.parser.Parser().parsestr(archive.read(metadata_paths[0]).decode())
            name, version = normalized(meta['Name']), meta['Version']
            assert re.fullmatch(r'[a-z0-9][a-z0-9-]*', name)
            assert re.fullmatch(r'[a-zA-Z0-9.!+_-]+', version)
            assert name not in identities
            identities.add(name)
            # Reject external direct references before any dependency is installed/imported.
            assert all('@' not in requirement for requirement in meta.get_all('Requires-Dist', []))
        wheels.append({'file': path.name, 'name': name, 'version': version,
                       'sha256': sha(path), 'bytes': path.stat().st_size})
    assert wheels
    lock = ''.join(f"{w['name']}=={w['version']} --hash=sha256:{w['sha256']}\n" for w in wheels)
    assert lock == Path('/input/requirements.lock').read_text()
    Path('/prepare/requirements.lock').write_text(lock)
    Path('/prepare/wheels.json').write_text(json.dumps(wheels, sort_keys=True))
    Path('/prepare/tmp').mkdir()
    subprocess.run([sys.executable, '-I', '-m', 'pip', '--isolated', '--disable-pip-version-check',
                    'install', '--ignore-installed', '--no-cache-dir', '--no-compile', '--no-deps',
                    '--no-index', '--find-links=/prepare/wheels', '--require-hashes',
                    '--target=/prepare/site', '-r', '/prepare/requirements.lock'], check=True, timeout=55,
                   env={**os.environ, 'TMPDIR': '/prepare/tmp'})
    installed = {normalized(d.metadata['Name']): d.version
                 for d in importlib.metadata.distributions(path=['/prepare/site'])}
    assert installed == {w['name']: w['version'] for w in wheels}
    output({'offline_lock_install': 'VERIFIED', 'packages': len(wheels)})
else:
    # Isolated Python intentionally ignores PYTHONPATH and user site packages.
    sys.path[:0] = ['/deps', '/source']
    import dspy
    from evolution.core.config import EvolutionConfig
    from evolution.core.constraints import ConstraintValidator
    from evolution.skills.skill_module import SkillModule, load_skill, reassemble_skill
    skill_path = Path('/fixture/hermes-agent/skills/github-code-review/SKILL.md')
    skill = load_skill(skill_path)

    if mode in ('help', 'dry-run'):
        prefix = "import sys; sys.path[:0]=['/deps','/source']; from evolution.skills.evolve_skill import main; main()"
        args = ['--help'] if mode == 'help' else [
            '--skill', 'github-code-review', '--hermes-repo', '/fixture/hermes-agent', '--dry-run']
        result = subprocess.run([sys.executable, '-I', '-B', '-c', prefix, *args], timeout=50)
        raise SystemExit(result.returncode)
    elif mode == 'contracts':
        config = EvolutionConfig(hermes_agent_path=Path('/fixture/hermes-agent'))
        validator = ConstraintValidator(config)
        def constraints(text):
            return {c.constraint_name: c.passed for c in validator.validate_all(text, 'skill')}
        module = SkillModule(skill['body'])
        changed = module.deepcopy()
        before_instructions = changed.predictor.predict.signature.instructions
        changed.predictor.predict.signature = changed.predictor.predict.signature.with_instructions(
            'Fixture mutation of DSPy predictor instructions. ' + before_instructions)
        try:
            dspy.GEPA(metric=lambda *args: 0.0, max_steps=1)
            gepa = {'status': 'CONSTRUCTED'}
        except Exception as error:
            # This captures real dependency API behavior, with no provider or LM invocation.
            gepa = {'status': 'ERROR', 'type': type(error).__name__, 'message': str(error)[:500]}
        output({'python': sys.version.split()[0],
                'versions': {n: importlib.metadata.version(n) for n in ('dspy', 'openai', 'pyyaml', 'click', 'rich')},
                'raw_constraints': constraints(skill['raw']),
                'body_constraints': constraints(skill['body']),
                'gepa_signature': str(inspect.signature(dspy.GEPA)), 'gepa_cli_constructor': gepa,
                'extraction_fixture': {'kind': 'manual-predictor-mutation-not-optimizer',
                    'predictor_changed': changed.predictor.predict.signature.instructions != before_instructions,
                    'saved_skill_unchanged': reassemble_skill(skill['frontmatter'], changed.skill_text) ==
                                            reassemble_skill(skill['frontmatter'], module.skill_text)},
                'fixture_sha256': sha(skill_path), 'model_api_calls': 0})
    elif mode == 'failure-path':
        from click.testing import CliRunner
        from unittest.mock import patch
        from evolution.skills.evolve_skill import main
        from evolution.core.dataset_builder import EvalDataset, EvalExample
        example = EvalExample(task_input='Review a safe synthetic diff.', expected_behavior='Return [].')
        dataset = EvalDataset(train=[example], val=[example], holdout=[example])
        calls = {'tests': 0, 'compile': 0}
        class FixtureOptimizer:
            def __init__(self, **kwargs):
                pass
            def compile(self, module, **kwargs):
                calls['compile'] += 1
                return module
        def sentinel(*args, **kwargs):
            calls['tests'] += 1
            raise AssertionError('test-suite sentinel reached')
        # Explicit fault-injection: real CLI/validator, fixture dataset and optimizer.
        with patch('evolution.skills.evolve_skill.GoldenDatasetLoader.load', return_value=dataset), \
             patch.object(dspy, 'GEPA', FixtureOptimizer), \
             patch.object(ConstraintValidator, 'run_test_suite', sentinel):
            result = CliRunner().invoke(main, ['--skill', 'github-code-review', '--iterations', '1',
                '--eval-source', 'golden', '--dataset-path', '/fixture/golden', '--run-tests',
                '--hermes-repo', '/fixture/hermes-agent'])
        artifact = Path('output/github-code-review/evolved_FAILED.md')
        output({'kind': 'injected-dataset-and-optimizer-not-improvement', 'exit': result.exit_code,
                'constraint_failure_reported': 'FAILED constraints' in result.output,
                'failed_artifact_written': artifact.exists(),
                'failed_artifact_sha256': sha(artifact) if artifact.exists() else None,
                'failed_artifact_text': artifact.read_text() if artifact.exists() else None,
                'candidate_body_unchanged': load_skill(artifact)['body'] == skill['body'] if artifact.exists() else None,
                'calls': calls, 'model_api_calls': 0})
    else:
        raise SystemExit('unsupported mode')
