"""Check PUBLIC artifact provenance without executing or importing candidate code."""
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
ART = ROOT / 'artifacts/generated-repair/issue-33'


def sha(data):
    return hashlib.sha256(data).hexdigest()


class ArtifactIdentityTests(unittest.TestCase):
    def test_bundle_preserves_both_commits_and_only_allowed_diff(self):
        provenance = json.loads((ART / 'provenance.json').read_text())
        report_bytes = (ART / 'report.json').read_bytes()
        report = json.loads(report_bytes)
        audit = json.loads((ART / 'audit.json').read_text())
        self.assertEqual(audit['audit'], 'VERIFIED')
        self.assertEqual(sha(report_bytes), audit['report_hash'])
        self.assertEqual(audit['manifest_hash'], provenance['manifest_hash'])
        self.assertEqual(report['manifest_hash'], provenance['manifest_hash'])
        self.assertEqual(sha((ART / 'candidate.bundle').read_bytes()), provenance['bundle_sha256'])
        with tempfile.TemporaryDirectory() as directory:
            def git(*args):
                return subprocess.check_output(
                    ['git', '-c', 'core.hooksPath=/dev/null', '-C', directory, *args],
                    stderr=subprocess.PIPE)
            git('init', '--template=', '--initial-branch=inspection')
            git('fetch', '--no-tags', str(ART / 'candidate.bundle'), provenance['candidate_sha'])
            base, candidate = provenance['baseline_sha'], provenance['candidate_sha']
            self.assertEqual(set(git('ls-tree', '-r', '--name-only', candidate).decode().splitlines()),
                             {'scripts/review.py', 'contract.json', 'public.json'})
            git('merge-base', '--is-ancestor', base, candidate)
            self.assertEqual(git('diff', '--name-only', base, candidate).decode().splitlines(),
                             ['scripts/review.py'])
            for label, commit in [('baseline', base), ('candidate', candidate)]:
                self.assertEqual(report[label + '_sha'], commit)
                source = git('show', commit + ':scripts/review.py')
                self.assertEqual(sha(source), report['artifact_hashes'][label])
                if label == 'candidate':
                    self.assertEqual(source, (ART / 'review.py').read_bytes())
                    self.assertLessEqual(len(source), 65536)
            self.assertEqual(git('show', base + ':public.json'), (ART / 'public.json').read_bytes())
        # Reports contain aggregate evidence; hidden inputs and traces stay local.
        self.assertEqual(set(report['counts']), {'baseline', 'candidate', 'degraded'})
        for counts in report['counts'].values():
            self.assertEqual(set(counts), {'public_correct', 'hidden_correct', 'failures',
                                          'median_seconds', 'cost_usd'})


if __name__ == '__main__':
    unittest.main()
