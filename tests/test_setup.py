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
