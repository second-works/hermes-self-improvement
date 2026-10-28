"""Recheck PUBLIC candidate/history/proof identities without executing generated Python."""
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
ART=ROOT/'artifacts/skill-creation/issue-35'
FIX=ROOT/'fixtures/generated_skills/event-counts-task'


def digest(data): return hashlib.sha256(data).hexdigest()


class ArtifactTests(unittest.TestCase):
    def test_two_files_originals_and_final_response_proof(self):
        report_bytes=(ART/'report.json').read_bytes(); report=json.loads(report_bytes)
        audit=json.loads((ART/'audit.json').read_text()); provenance=json.loads((ART/'provenance.json').read_text())
        self.assertEqual(audit['audit'],'VERIFIED')
        self.assertEqual(audit['report_hash'],digest(report_bytes))
        self.assertEqual(audit['manifest_hash'],report['manifest_hash'])
        self.assertEqual(audit['candidate_sha'],report['candidate_sha'])
        self.assertEqual(provenance['candidate_sha'],report['candidate_sha'])
        self.assertEqual(report['status'],'PASS')
        self.assertTrue(all(n==3 for n in report['counts'].values()))
        self.assertEqual(len(report['counts']),13)
        self.assertEqual(sum(p.endswith('.response.json') for p in report['trace_hashes']),27)
        self.assertEqual(len(set(report['session_ids'])),3)
        self.assertEqual(digest((ART/'candidate.bundle').read_bytes()),provenance['bundle_hash'])
        self.assertEqual(provenance['public_revision_attempts'],1)
        with tempfile.TemporaryDirectory() as directory:
            def git(*args):
                return subprocess.check_output(['git','-c','core.hooksPath=/dev/null','-C',directory,*args],stderr=subprocess.PIPE)
            git('init','--template=','--initial-branch=inspection')
            git('fetch','--no-tags',str(ART/'candidate.bundle'),report['candidate_sha'])
            base,initial,final=report['baseline_sha'],provenance['initial_candidate_sha'],report['candidate_sha']
            git('merge-base','--is-ancestor',base,initial); git('merge-base','--is-ancestor',initial,final)
            files=['event-status-counts/SKILL.md','event-status-counts/scripts/aggregate.py']
            self.assertEqual(git('diff','--name-only',base,final).decode().splitlines(),files)
            self.assertEqual(git('diff','--name-only',initial,final).decode().splitlines(),[files[0]])
            for name in ['catalog.json','contract.json','public.json']:
                original=git('show',base+':'+name)
                self.assertEqual(original,git('show',final+':'+name))
                self.assertEqual(original,(FIX/name).read_bytes())
            for name in files:
                source=git('show',final+':'+name)
                self.assertEqual(source,(ART/'candidate'/name).read_bytes())
                self.assertEqual(digest(source),report['artifact_hashes'][name])
            self.assertEqual(git('show',initial+':'+files[1]),git('show',final+':'+files[1]))


if __name__=='__main__': unittest.main()
