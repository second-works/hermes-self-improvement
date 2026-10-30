"""#55: scripts/check-pr-head.sh review gate with a fake gh/git. No network; needs bash and jq."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'scripts/check-pr-head.sh'
HEAD = 'a' * 40
OLD = 'b' * 40
REPO = 'second-works/hermes-self-improvement'

FAKE_GH = r'''#!/usr/bin/env python3
import json, os, sys
s = json.load(open(os.environ['FAKE_SCENARIO']))
a = sys.argv[1:]
def out(v):
    print(v if isinstance(v, str) else json.dumps(v)); sys.exit(0)
if a[:2] == ['pr', 'view']:
    fields = a[a.index('--json') + 1]
    if fields == 'comments':
        out({'comments': s['comments']})
    out({'headRefOid': s['head'], 'baseRefName': 'main', 'url': f"https://github.com/{s['repo']}/pull/7",
         'state': 'OPEN', 'mergeable': 'MERGEABLE', 'reviewDecision': '', 'reviews': []})
if a[:1] == ['api']:
    path = a[-1]
    if '/contents/' in path:
        name = path.split('/contents/', 1)[1]
        if name in s['files']:
            if s['files'][name] is None:
                sys.stderr.write('gh: Not Found (HTTP 404)\n'); sys.exit(1)
            out(s['files'][name])
        sys.stderr.write('gh: Not Found (HTTP 404)\n'); sys.exit(1)
    if '/check-runs' in path:
        out({'total_count': 1, 'check_runs': [{'name': 'ci', 'status': 'completed', 'conclusion': 'success'}]})
    if '/status' in path:
        out({'total_count': 0, 'statuses': []})
    if path.startswith('query=') or 'graphql' in a:
        out({'data': {'repository': {'pullRequest': {'reviewThreads': {'pageInfo': {'hasNextPage': False}, 'nodes': []}}}}})
sys.stderr.write('unexpected gh call: %r\n' % (a,)); sys.exit(3)
'''
FAKE_GIT = '#!/usr/bin/env python3\nimport json, os\nprint(json.load(open(os.environ["FAKE_SCENARIO"]))["head"])\n'


def claude(sha=HEAD, status='completed', unresolved=False, association='OWNER', raw=None):
    state = raw if raw is not None else json.dumps(
        {'commit_sha': sha, 'status': status, 'has_unresolved_findings': unresolved})
    return {'author': {'login': 'second-works'}, 'authorAssociation': association,
            'body': f'## Claude Code review\n<!-- claude-code-review:v1 {state} -->\n本文'}


def codex(sha=HEAD, status='completed', unresolved=False):
    state = json.dumps({'code_review': {'commit_sha': sha, 'status': status, 'has_any_findings': unresolved,
                                        'has_unresolved_findings': unresolved}})
    return {'author': {'login': 'chatgpt-codex-connector'}, 'authorAssociation': 'NONE',
            'body': f'<!-- codex-pull-request-review-summary -->\n<!-- codex-review-state:v1 {state} -->'}


@unittest.skipUnless(shutil.which('jq') and shutil.which('bash'), 'needs bash and jq')
class ReviewGateTests(unittest.TestCase):
    def run_gate(self, comments, review_file='claude-code\n', env=None):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            bindir = tmp / 'bin'
            bindir.mkdir()
            for name, text in (('gh', FAKE_GH), ('git', FAKE_GIT)):
                (bindir / name).write_text(text)
                (bindir / name).chmod(0o755)
            scenario = {'head': HEAD, 'repo': REPO, 'comments': comments,
                        'files': {'.github/pr-gate-checks': 'ci\n', '.github/pr-gate-review': review_file}}
            (tmp / 'scenario.json').write_text(json.dumps(scenario))
            environ = {**os.environ, 'PATH': f'{bindir}{os.pathsep}{os.environ["PATH"]}',
                       'FAKE_SCENARIO': str(tmp / 'scenario.json')}
            environ.pop('PR_GATE_REVIEW', None)
            environ.pop('PR_GATE_CHECKS', None)
            environ.update(env or {})
            proc = subprocess.run(['bash', str(SCRIPT), '7'], capture_output=True, text=True, env=environ, timeout=60)
        status = next((l.split('=', 1)[1] for l in proc.stdout.splitlines() if l.startswith('PR_GATE_STATUS=')), None)
        return proc.returncode, status, proc.stdout + proc.stderr

    def assert_status(self, expected, comments, **kwargs):
        code, status, text = self.run_gate(comments, **kwargs)
        self.assertEqual(status, expected, text)
        self.assertEqual(code == 0, expected == 'READY', text)

    def test_claude_review_on_head_is_ready(self):
        self.assert_status('READY', [claude()])

    def test_claude_review_for_old_head_is_pending(self):
        self.assert_status('REVIEW_PENDING', [claude(sha=OLD)])

    def test_claude_review_not_completed_is_pending(self):
        self.assert_status('REVIEW_PENDING', [claude(status='running')])

    def test_claude_review_with_findings_stops(self):
        self.assert_status('REVIEW_FINDINGS', [claude(unresolved=True)])

    def test_untrusted_author_is_ignored(self):
        for association in ('NONE', 'CONTRIBUTOR', 'FIRST_TIME_CONTRIBUTOR'):
            with self.subTest(association=association):
                self.assert_status('REVIEW_UNAVAILABLE', [claude(association=association)])

    def test_broken_marker_is_not_success(self):
        for raw in ('{"commit_sha": "%s"' % HEAD, '{}', '{"commit_sha": "%s", "status": "completed"}' % HEAD):
            with self.subTest(raw=raw):
                code, status, text = self.run_gate([claude(raw=raw)])
                self.assertNotEqual(status, 'READY', text)
                self.assertNotEqual(code, 0)

    def test_latest_claude_record_wins(self):
        self.assert_status('REVIEW_FINDINGS', [claude(), claude(unresolved=True)])
        self.assert_status('READY', [claude(unresolved=True), claude()])

    def test_without_setting_file_only_codex_counts(self):
        self.assert_status('REVIEW_UNAVAILABLE', [claude()], review_file=None)
        self.assert_status('READY', [codex()], review_file=None)

    def test_codex_only_setting_ignores_claude(self):
        self.assert_status('REVIEW_UNAVAILABLE', [claude()], review_file='codex\n')

    def test_both_kinds_any_pass_but_findings_block(self):
        both = '# 正式レビュー\ncodex\nclaude-code\n'
        self.assert_status('READY', [codex(sha=OLD), claude()], review_file=both)
        self.assert_status('READY', [codex()], review_file=both)
        self.assert_status('REVIEW_FINDINGS', [codex(unresolved=True), claude()], review_file=both)

    def test_unknown_kind_is_rejected(self):
        self.assert_status('REVIEW_UNAVAILABLE', [claude()], review_file='claude\n')

    def test_environment_overrides_setting(self):
        self.assert_status('READY', [codex()], env={'PR_GATE_REVIEW': 'codex'})
        self.assert_status('REVIEW_UNAVAILABLE', [codex()], env={'PR_GATE_REVIEW': 'claude-code'})


if __name__ == '__main__':
    unittest.main()
