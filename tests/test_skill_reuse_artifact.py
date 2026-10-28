"""Archived PUBLIC observation identities; never execute or import generated skill resources."""
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
ART = ROOT / 'artifacts/skill-reuse/issue-34'


def digest(data):
    return hashlib.sha256(data).hexdigest()


class PublicProofTests(unittest.TestCase):
    def test_candidate_bundle_and_audit_preserve_identity(self):
        provenance = json.loads((ART / 'provenance.json').read_text())
        report_bytes = (ART / 'report.json').read_bytes()
        report = json.loads(report_bytes)
        audit = json.loads((ART / 'audit.json').read_text())
        self.assertEqual(audit['audit'], 'VERIFIED')
        self.assertEqual(audit['report_hash'], digest(report_bytes))
        self.assertEqual(audit['manifest_hash'], report['manifest_hash'])
        self.assertEqual(report['candidate_sha'], provenance['candidate_sha'])
        self.assertEqual(report['candidate_hash'], digest((ART / 'candidate.SKILL.md').read_bytes()))
        self.assertEqual(digest((ART / 'candidate.bundle').read_bytes()), provenance['bundle_hash'])
        # This is the old observer's status, not final output-contract acceptance.
        self.assertEqual(report['status'], 'PASS')
        self.assertEqual(provenance['acceptance_status'], 'HOLD')
        self.assertEqual(report['counts'], {name: 3 for name in ['primary', 'sufficient', 'denied', 'missing', 'baseline']})
        self.assertEqual(len(set(report['session_ids'])), 3)
        with tempfile.TemporaryDirectory() as directory:
            def git(*args):
                return subprocess.check_output(['git', '-c', 'core.hooksPath=/dev/null', '-C', directory, *args],
                                               stderr=subprocess.PIPE)
            git('init', '--template=', '--initial-branch=inspection')
            candidate, baseline = report['candidate_sha'], report['baseline_sha']
            git('fetch', '--no-tags', str(ART / 'candidate.bundle'), candidate)
            git('merge-base', '--is-ancestor', baseline, candidate)
            self.assertEqual(git('diff', '--name-only', baseline, candidate).decode().splitlines(),
                             ['github-code-review/SKILL.md'])
            self.assertEqual(git('show', candidate + ':github-code-review/SKILL.md'),
                             (ART / 'candidate.SKILL.md').read_bytes())
            for sha in [baseline, candidate]:
                source = git('show', sha + ':github-code-review/scripts/review.py')
                self.assertEqual(digest(source), report['script_hash'])
                self.assertEqual(source, (ROOT / 'fixtures/generated_skills/github-code-review/scripts/review.py').read_bytes())
        previous = json.loads((ART / 'stopped-attempt2/stopped-summary.json').read_text())
        self.assertEqual(previous['status'], 'STOPPED')
        self.assertEqual(previous['candidate_hash'], report['candidate_hash'])


if __name__ == '__main__': unittest.main()
