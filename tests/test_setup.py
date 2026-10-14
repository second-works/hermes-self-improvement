import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
BASH = shutil.which('bash')
if Path('/opt/homebrew/bin/bash').exists():
    BASH = '/opt/homebrew/bin/bash'


class SetupTests(unittest.TestCase):
    def fixture(self):
        context = tempfile.TemporaryDirectory()
        self.addCleanup(context.cleanup)
        root = Path(context.name)
        subprocess.run(['git', 'init', '-q', str(root)], check=True)
        return root

    def security(self, root):
        subprocess.run(['git', '-C', str(root), 'add', '.'], check=True)
        return subprocess.run([BASH, str(ROOT / 'scripts/security-preflight.sh'), str(root)],
                              capture_output=True, text=True)

    def test_security_rejects_secret_in_path_without_echoing_value(self):
        value = 'ghp_' + 'a' * 30
        for filename in (value, 'requirements-' + value + '.txt'):
            with self.subTest(filename='redacted'):
                root = self.fixture()
                (root / filename).write_text('')
                result = self.security(root)
                self.assertEqual(result.returncode, 1, result.stdout)
                self.assertIn('SECURITY_STATUS=SECURITY_FAILED', result.stdout)
                self.assertNotIn(value, result.stdout + result.stderr)

    def test_lint_rejects_invalid_staged_sources_even_if_worktree_is_clean(self):
        for filename, invalid, valid in [('bad.sh', 'if\n', ':\n'),
                                         ('tests/bad.py', 'if:\n', 'pass\n')]:
            with self.subTest(filename=filename):
                root = self.fixture()
                path = root / filename
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(invalid)
                subprocess.run(['git', '-C', str(root), 'add', '.'], check=True)
                path.write_text(valid)
                result = subprocess.run([BASH, str(ROOT / 'scripts/lint.sh')], cwd=root,
                                        capture_output=True, text=True)
                self.assertNotEqual(result.returncode, 0, result.stdout)

    def helper_result(self, include_preflight, include_codeql=True, include_ci=True):
        import json
        root = self.fixture()
        checks = [{'name': 'ci' if include_ci else 'other-check',
                   'status': 'completed', 'conclusion': 'success'}]
        if include_codeql:
            checks.append({'name': 'Analyze (python)', 'status': 'completed', 'conclusion': 'success'})
        statuses = [{'context': 'Security Preflight', 'state': 'success'}] if include_preflight else []
        (root / 'checks.json').write_text(json.dumps([{'check_runs': checks}]))
        (root / 'statuses.json').write_text(json.dumps([{'statuses': statuses}]))
        (root / 'fallback.txt').write_text('SECURITY_STATUS=SECURITY_UNAVAILABLE\n')
        helper = (ROOT / '.agents/skills/pr-review-fix/scripts/wait-checks.sh').read_text()
        source = helper.split("<<'PY'\n", 1)[1].split('\nPY', 1)[0]
        return subprocess.run(['python3', '-c', source, str(root / 'checks.json'),
                               str(root / 'statuses.json'), str(root / 'fallback.txt')],
                              check=True, capture_output=True, text=True).stdout

    def test_helper_does_not_replace_missing_preflight_with_codeql(self):
        self.assertIn('SECURITY_STATUS=SECURITY_UNAVAILABLE', self.helper_result(False))

    def test_helper_rejects_missing_required_codeql(self):
        self.assertIn('SECURITY_STATUS=SECURITY_UNAVAILABLE',
                      self.helper_result(True, include_codeql=False))

    def test_helper_rejects_other_ci_as_replacement(self):
        self.assertIn('CI_STATUS=CI_UNAVAILABLE', self.helper_result(True, include_ci=False))

    def test_helper_accepts_exact_preflight_and_codeql(self):
        self.assertIn('SECURITY_STATUS=SECURITY_PASSED', self.helper_result(True))

    def test_trusted_gate_rejects_modified_or_missing_ci_definitions(self):
        workflow = (ROOT / '.github/workflows/security.yml').read_text()
        guard = workflow.split('        id: scan\n        run: |\n', 1)[1].split(
            '          bash security-tool/scripts/security-preflight.sh candidate', 1)[0]
        guard = '\n'.join(line[10:] for line in guard.splitlines())
        for modified in (None, 'ci.yml', 'codeql.yml', 'missing', 'mode', 'extra', 'security'):
            with self.subTest(modified=modified):
                root = self.fixture()
                for dirname in ('security-tool', 'candidate'):
                    repo = root / dirname
                    subprocess.run(['git', 'init', '-q', str(repo)], check=True)
                    workflows = repo / '.github/workflows'
                    workflows.mkdir(parents=True)
                    for name in ('ci.yml', 'codeql.yml', 'security.yml'):
                        (workflows / name).write_text('name: Trusted fixture\n')
                    if dirname == 'candidate' and modified in ('ci.yml', 'codeql.yml'):
                        (workflows / modified).write_text('name: Trusted fixture\n# no-op replacement\n')
                    if dirname == 'candidate' and modified == 'missing':
                        (workflows / 'codeql.yml').unlink()
                    if dirname == 'candidate' and modified == 'extra':
                        (workflows / 'fake.yml').write_text('name: Duplicate no-op fixture\n')
                    if dirname == 'candidate' and modified == 'security':
                        (workflows / 'security.yml').write_text('name: No-op Security fixture\n')
                    if dirname == 'candidate' and modified == 'mode':
                        (workflows / 'codeql.yml').chmod(0o755)
                    subprocess.run(['git', '-C', str(repo), 'add', '.'], check=True)
                    subprocess.run(['git', '-C', str(repo), '-c', 'user.name=Fixture',
                        '-c', 'user.email=fixture@example.invalid', 'commit', '-qm', 'fixture'], check=True)
                base = subprocess.check_output(['git', '-C', str(root / 'security-tool'),
                                                 'rev-parse', 'HEAD'], text=True).strip()
                subprocess.run(['git', '-C', str(root / 'candidate'), 'fetch', '-q',
                                str(root / 'security-tool'), base], check=True)
                head = subprocess.check_output(['git', '-C', str(root / 'candidate'),
                                                 'rev-parse', 'HEAD'], text=True).strip()
                result = subprocess.run([BASH, '-e', '-c', guard], cwd=root,
                    env={**os.environ, 'PR_HEAD_SHA': head, 'BASE_WORKFLOW_SHA': base}, capture_output=True, text=True)
                self.assertEqual(result.returncode, 0 if modified is None else 1,
                                 result.stdout + result.stderr)
                if modified:
                    self.assertIn('SECURITY_STATUS=SECURITY_FAILED', result.stdout)

    def test_security_clean(self):
        root = self.fixture()
        (root / 'README.md').write_text('clean fixture\n')
        result = self.security(root)
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn('SECURITY_STATUS=SECURITY_PASSED', result.stdout)

    def test_security_rejects_secret_without_echoing_value(self):
        root = self.fixture()
        value = 'ghp_' + 'a' * 30
        (root / 'leak.txt').write_text(value)
        result = self.security(root)
        self.assertEqual(result.returncode, 1)
        self.assertIn('SECURITY_STATUS=SECURITY_FAILED', result.stdout)
        self.assertNotIn(value, result.stdout + result.stderr)

    def test_security_scans_staged_secret_even_if_worktree_is_clean(self):
        root = self.fixture()
        value = 'ghp_' + 'a' * 30
        (root / 'leak.txt').write_text(value)
        subprocess.run(['git', '-C', str(root), 'add', '.'], check=True)
        (root / 'leak.txt').write_text('clean\n')
        result = subprocess.run([BASH, str(ROOT / 'scripts/security-preflight.sh'), str(root)],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn('SECURITY_STATUS=SECURITY_FAILED', result.stdout)
        self.assertNotIn(value, result.stdout + result.stderr)

    def test_security_scans_staged_manifest_even_if_worktree_is_clean(self):
        root = self.fixture()
        (root / 'requirements.txt').write_text('example==1.0\n')
        subprocess.run(['git', '-C', str(root), 'add', '.'], check=True)
        (root / 'requirements.txt').unlink()
        result = subprocess.run([BASH, str(ROOT / 'scripts/security-preflight.sh'), str(root)],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 4, result.stdout)
        self.assertIn('SECURITY_STATUS=SECURITY_UNAVAILABLE', result.stdout)

    def test_security_unsupported_dependency_is_unavailable(self):
        root = self.fixture()
        (root / 'requirements.txt').write_text('example==1.0\n')
        result = self.security(root)
        self.assertEqual(result.returncode, 4)
        self.assertIn('SECURITY_STATUS=SECURITY_UNAVAILABLE', result.stdout)

    def test_security_does_not_follow_symlink(self):
        root = self.fixture()
        (root / 'outside').symlink_to('/nonexistent/private-data')
        result = self.security(root)
        self.assertEqual(result.returncode, 0)

    def test_security_dependency_symlink_is_unavailable(self):
        root = self.fixture()
        (root / 'package-lock.json').symlink_to('/nonexistent/private-data')
        result = self.security(root)
        self.assertEqual(result.returncode, 4, result.stdout)
        self.assertIn('SECURITY_STATUS=SECURITY_UNAVAILABLE', result.stdout)

    def test_security_does_not_apply_checkout_filters(self):
        root = self.fixture()
        value = 'ghp_' + 'a' * 30
        (root / '.gitattributes').write_text('leak.txt filter=redact\n')
        (root / 'leak.txt').write_text(value)
        subprocess.run(['git', '-C', str(root), 'config', 'filter.redact.clean', 'cat'], check=True)
        subprocess.run(['git', '-C', str(root), 'config', 'filter.redact.smudge',
                        "sed 's/ghp_[a-z]*/redacted/g'"], check=True)
        result = self.security(root)
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn('SECURITY_STATUS=SECURITY_FAILED', result.stdout)
        self.assertNotIn(value, result.stdout + result.stderr)

    def test_security_can_scan_index_without_candidate_checkout(self):
        root = self.fixture()
        (root / 'leak.txt').write_text('ghp_' + 'a' * 30)
        subprocess.run(['git', '-C', str(root), 'add', '.'], check=True)
        (root / 'leak.txt').unlink()
        result = subprocess.run([BASH, str(ROOT / 'scripts/security-preflight.sh'), str(root)],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn('SECURITY_STATUS=SECURITY_FAILED', result.stdout)

    def test_security_does_not_execute_candidate_scanner(self):
        root = self.fixture()
        (root / 'scripts').mkdir()
        (root / 'scripts/security-preflight.sh').write_text('#!/bin/sh\nexit 0\n')
        (root / 'leak.txt').write_text('ghp_' + 'a' * 30)
        result = self.security(root)
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn('SECURITY_STATUS=SECURITY_FAILED', result.stdout)

    def test_security_template_matches_runtime(self):
        self.assertEqual((ROOT / 'scripts/security-preflight.sh').read_bytes(),
                         (ROOT / 'templates/security/security-preflight.sh').read_bytes())

    def verify_fixture(self):
        root = self.fixture()
        (root / 'scripts').mkdir()
        shutil.copy(ROOT / 'scripts/verify.sh', root / 'scripts/verify.sh')
        return root

    def verify(self, root):
        return subprocess.run([BASH, str(root / 'scripts/verify.sh')],
                              env={**os.environ, 'VERIFY_STACK': 'generic'},
                              capture_output=True, text=True)

    def test_verify_accepts_documented_python_markers(self):
        for marker in ('requirements-dev.txt', 'uv.lock', 'poetry.lock'):
            for stack in ('auto', 'python'):
                with self.subTest(marker=marker, stack=stack):
                    root = self.verify_fixture()
                    (root / marker).write_text('')
                    (root / 'tests').mkdir()
                    (root / 'tests/test_example.py').write_text('def test_example(): pass\n')
                    (root / 'bin').mkdir()
                    pytest = root / 'bin/pytest'
                    pytest.write_text('#!/bin/sh\ntouch pytest-ran\n')
                    pytest.chmod(0o755)
                    result = subprocess.run([BASH, str(root / 'scripts/verify.sh')], cwd=root,
                        env={**os.environ, 'VERIFY_STACK': stack,
                             'PATH': str(root / 'bin') + os.pathsep + os.environ['PATH']},
                        capture_output=True, text=True)
                    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                    self.assertTrue((root / 'pytest-ran').exists())

    def test_verify_template_matches_runtime(self):
        self.assertEqual((ROOT / 'scripts/verify.sh').read_bytes(),
                         (ROOT / 'templates/verification/verify.sh').read_bytes())

    def test_verify_all_skipped_fails(self):
        result = self.verify(self.verify_fixture())
        self.assertEqual(result.returncode, 2)
        self.assertIn('no applicable verification stages', result.stderr)

    def test_verify_failure_stops_before_test(self):
        root = self.verify_fixture()
        (root / 'scripts/lint.sh').write_text('#!/bin/sh\nexit 17\n')
        (root / 'scripts/test.sh').write_text('#!/bin/sh\ntouch test-ran\n')
        for path in root.glob('scripts/*.sh'):
            path.chmod(0o755)
        result = self.verify(root)
        self.assertEqual(result.returncode, 17)
        self.assertFalse((root / 'test-ran').exists())

    def test_agent_references_are_present(self):
        import re
        text = (ROOT / 'AGENTS.md').read_text()
        for path in re.findall(r'(?<![A-Za-z0-9_/])(?:docs|\.agents|templates)/[A-Za-z0-9_./-]+\.(?:md|sh)', text):
            self.assertTrue((ROOT / path).is_file(), path)


if __name__ == '__main__':
    unittest.main()
