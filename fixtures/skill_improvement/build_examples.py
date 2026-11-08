"""Build the PUBLIC synthetic examples of the Skill improvement MVP contract (#106).

All ids, hashes, repositories and people are synthetic. `python3 -I -B
fixtures/skill_improvement/build_examples.py` rewrites the examples; the contract
test checks that the committed files equal `build()`.
"""
import copy
import hashlib
import json
from pathlib import Path

OUT = Path(__file__).resolve().parent
TZ = 'Asia/Tokyo'


def h(label):
    return hashlib.sha256(('synthetic:' + label).encode()).hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()


def sha(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def ev(event_id, at, date, repo, unit, record):
    return {'schema_version': 1, 'event_id': event_id, 'recorded_at': at, 'work_date': date,
            'timezone': TZ, 'repository_id': repo, 'work_unit_id': unit,
            'classification': 'PUBLIC', 'record': record}


def manifest(stage, manifest_id):
    return {
        'schema_version': 1, 'manifest_id': manifest_id, 'classification': 'PUBLIC', 'stage': stage,
        'timezone': TZ, 'period': {'start_date': '2026-11-02', 'end_date': '2026-11-15'},
        'ledger_location': {'kind': 'PUBLIC_FIXTURE', 'label': 'skill-improvement-example'},
        'approval': {'approved_by': 'example-owner', 'approved_at': '2026-11-01T00:00:00Z',
                     'ref': 'synthetic approval record (not a real approval)'},
        'repositories': [
            {'repository_id': 'demo-app', 'allowed_roots': ['docs', '.claude/skills'],
             'read_items': ['EXPLICIT_INPUT', 'END_RECORD'], 'classification': 'PUBLIC',
             'owner': 'example-owner'},
            {'repository_id': 'demo-cli', 'allowed_roots': ['skills'],
             'read_items': ['EXPLICIT_INPUT', 'END_RECORD', 'PR_REVIEW_COMMENT'],
             'classification': 'PUBLIC', 'owner': 'example-owner'},
        ],
    }


EVAL = {'kind': 'evaluation', 'evaluation_id': 'ev-review-steps', 'candidate_id': 'c-review-steps',
        'baseline_sha256': h('baseline'), 'candidate_sha256': h('candidate'),
        'evaluation_sha256': h('evaluation'),
        'required_contract': {'cases': 5, 'candidate_passed': 5},
        'regression': {'baseline_passing_cases': 4, 'candidate_failed_among_them': 0},
        'improvement': {'method': 'DETERMINISTIC', 'target_cases': 3, 'baseline_passed': 1,
                        'candidate_passed': 3, 'trials': 3, 'stable': True, 'control_valid': True},
        'verdict': 'IMPROVED'}
SIZE = {'kind': 'size_review', 'review_id': 'sr-review-steps', 'candidate_id': 'c-review-steps',
        'target_ref': 'demo-app:.claude/skills/pr-review/SKILL.md', 'guide_lines': 120,
        'lines_before': 96, 'lines_after': 104, 'net_added_lines': 8, 'moved_to': [],
        'responsibilities_before': ['r-scope', 'r-order', 'r-stop'],
        'responsibilities': [{'id': 'r-scope', 'status': 'KEPT', 'location': 'SKILL.md#scope'},
                             {'id': 'r-order', 'status': 'KEPT', 'location': 'SKILL.md#order'},
                             {'id': 'r-stop', 'status': 'KEPT', 'location': 'SKILL.md#stop'}],
        'exception_reason': None, 'verdict': 'WITHIN_GUIDE'}
PLAN = {'kind': 'deployment_plan', 'deployment_id': 'd-review-steps', 'candidate_id': 'c-review-steps',
        'evaluation_id': 'ev-review-steps', 'size_review_id': 'sr-review-steps',
        'target': {'skill_id': 'pr-review', 'canonical_ref': 'demo-app:.claude/skills/pr-review/SKILL.md',
                   'deploy_ref': 'demo-app:.claude/skills/pr-review/SKILL.md'},
        'route': {'type': 'LOCAL_MANUAL'},
        'hashes': {'baseline': h('baseline'), 'candidate': h('candidate'), 'evaluation': h('evaluation'),
                   'expected_before': h('deployed-before'), 'expected_after': h('deployed-after')},
        'backup': {'ref': 'approved-local-backup:pr-review-before', 'sha256': h('deployed-before')},
        'owner': 'example-owner', 'deadline': '2026-11-06T00:00:00Z',
        'applicability': {'conditions': ['PRレビュー依頼を受けた作業', 'pr-review Skillを読み込んだ作業'],
                          'skill_version': 'pr-review candidate ' + h('candidate')[:12]},
        'rollback_preapproval': {'approved_by': 'example-owner', 'executor': 'example-owner',
                                 'conditions': ['SAFETY_VIOLATION', 'MISAPPLICATION', 'CLEAR_WORSENING',
                                                'USER_WITHDRAWAL'],
                                 'expires_at': '2026-11-20T00:00:00Z'}}


def approved(plan, expires='2026-11-05T00:00:00Z', plan_event='e16'):
    return {'kind': 'deployment_event', 'deployment_id': 'd-review-steps',
            'state': {'status': 'APPROVED', 'approved_by': 'example-owner',
                      'approved_at': '2026-11-04T01:00:00Z', 'expires_at': expires,
                      'plan_event_id': plan_event, 'plan_sha256': sha(plan)}}


def deployed(at='2026-11-04T02:00:00Z', before=None):
    return {'kind': 'deployment_event', 'deployment_id': 'd-review-steps',
            'state': {'status': 'DEPLOYED_EFFECT_UNCONFIRMED', 'deployed_by': 'example-owner',
                      'deployed_at': at, 'approval_event_id': 'e17',
                      'observed_before_sha256': before or h('deployed-before'),
                      'observed_after_sha256': h('deployed-after')}}


def obs(n, task='COMPLETED', recurred=False, adverse=None, applied=True):
    return {'kind': 'effect_observation', 'observation_id': f'o-{n}', 'deployment_id': 'd-review-steps',
            'sequence': n, 'applicable': True, 'skill_applied': applied, 'task_result': task,
            'issue_recurred': recurred, 'adverse': adverse}


A = 'demo-app'


def base_deploy(plan=PLAN):
    return [ev('e14', '2026-11-03T09:00:00Z', '2026-11-03', A, 'wu-app-eval', EVAL),
            ev('e15', '2026-11-03T09:10:00Z', '2026-11-03', A, 'wu-app-eval', SIZE),
            ev('e16', '2026-11-04T00:30:00Z', '2026-11-04', A, 'wu-app-deploy', plan)]


def deployed_prefix():
    return base_deploy() + [
        ev('e17', '2026-11-04T01:00:00Z', '2026-11-04', A, 'wu-app-deploy', approved(PLAN)),
        ev('e18', '2026-11-04T02:00:00Z', '2026-11-04', A, 'wu-app-deploy', deployed())]


def ledger():
    rows = [
        ev('e01', '2026-11-02T03:00:00Z', '2026-11-02', 'demo-app', 'wu-app-1',
           {'kind': 'session_end', 'status': 'CANDIDATE_FOUND', 'experience_ids': ['x-app-1']}),
        ev('e02', '2026-11-02T03:01:00Z', '2026-11-02', 'demo-app', 'wu-app-1',
           {'kind': 'experience', 'experience_id': 'x-app-1', 'end_event_id': 'e01',
            'experience_type': 'CORRECTION', 'summary': 'レビュー前に変更範囲の確認を飛ばし、利用者に訂正された',
            'evidence_refs': ['synthetic:demo-app/pr-12/review-1'], 'cause': 'MISSING_PROCEDURE'}),
        ev('e03', '2026-11-02T06:00:00Z', '2026-11-02', 'demo-app', 'wu-app-2',
           {'kind': 'session_end', 'status': 'NO_CANDIDATE'}),
        ev('e04', '2026-11-03T08:00:00Z', '2026-11-03', 'demo-app', 'wu-app-3',
           {'kind': 'session_end', 'status': 'UNDETERMINED',
            'reason': '作業が途中で終わり、訂正や手戻りの有無を判断できない'}),
        ev('e05', '2026-11-02T04:00:00Z', '2026-11-02', 'demo-cli', 'wu-cli-1',
           {'kind': 'session_end', 'status': 'CANDIDATE_FOUND', 'experience_ids': ['x-cli-1', 'x-cli-2']}),
        ev('e06', '2026-11-02T04:01:00Z', '2026-11-02', 'demo-cli', 'wu-cli-1',
           {'kind': 'experience', 'experience_id': 'x-cli-1', 'end_event_id': 'e05',
            'experience_type': 'REPEATED_FEEDBACK', 'summary': '変更範囲の確認漏れを別repoでも指摘された',
            'evidence_refs': ['synthetic:demo-cli/pr-7/review-2'], 'cause': 'MISSING_PROCEDURE'}),
        ev('e07', '2026-11-02T04:02:00Z', '2026-11-02', 'demo-cli', 'wu-cli-1',
           {'kind': 'experience', 'experience_id': 'x-cli-2', 'end_event_id': 'e05',
            'experience_type': 'BETTER_METHOD', 'summary': '一時的なCI障害のため手元で再実行した',
            'evidence_refs': ['synthetic:demo-cli/ci-run-3'], 'cause': 'TEMPORARY'}),
        ev('e08', '2026-11-03T05:00:00Z', '2026-11-03', 'demo-cli', 'wu-cli-2',
           {'kind': 'session_end', 'status': 'CANDIDATE_FOUND', 'experience_ids': ['x-cli-3']}),
        ev('e09', '2026-11-03T05:01:00Z', '2026-11-03', 'demo-cli', 'wu-cli-2',
           {'kind': 'experience', 'experience_id': 'x-cli-3', 'end_event_id': 'e08',
            'experience_type': 'REWORK', 'summary': '既存Skillの手順があったのに読み込まず作業をやり直した',
            'evidence_refs': ['synthetic:demo-cli/pr-8/commit-2'], 'cause': 'NOT_LOADED'}),
        ev('e10', '2026-11-03T06:00:00Z', '2026-11-03', 'demo-app', 'wu-app-triage',
           {'kind': 'candidate', 'candidate_id': 'c-review-steps', 'experience_ids': ['x-app-1', 'x-cli-1'],
            'target_skill_id': 'pr-review', 'cause': 'MISSING_PROCEDURE',
            'scope': {'type': 'SHARED', 'basis': 'REPEATED_IN_REPOSITORIES',
                      'repository_ids': ['demo-app', 'demo-cli'], 'decided_by': 'example-owner'},
            'state': {'status': 'OPEN'}}),
        ev('e11', '2026-11-03T06:05:00Z', '2026-11-03', 'demo-cli', 'wu-cli-triage',
           {'kind': 'candidate', 'candidate_id': 'c-cli-scope-check', 'experience_ids': ['x-cli-1'],
            'target_skill_id': 'pr-review', 'cause': 'MISSING_PROCEDURE', 'scope': {'type': 'REPOSITORY_LOCAL'},
            'state': {'status': 'DUPLICATE', 'duplicate_of': 'c-review-steps',
                      'reason': '同じ経験x-cli-1を根拠とする共通候補が既にある'}}),
        ev('e12', '2026-11-03T06:10:00Z', '2026-11-03', 'demo-cli', 'wu-cli-triage',
           {'kind': 'candidate', 'candidate_id': 'c-ci-rerun', 'experience_ids': ['x-cli-2'],
            'target_skill_id': 'ci-triage', 'cause': 'TEMPORARY', 'scope': {'type': 'REPOSITORY_LOCAL'},
            'state': {'status': 'DECLINED', 'reason': '一時事情でありSkillを変更しない'}}),
        ev('e13', '2026-11-03T06:15:00Z', '2026-11-03', 'demo-cli', 'wu-cli-triage',
           {'kind': 'candidate', 'candidate_id': 'c-entry-loading', 'experience_ids': ['x-cli-3'],
            'target_skill_id': 'release-steps', 'cause': 'NOT_LOADED', 'scope': {'type': 'REPOSITORY_LOCAL'},
            'state': {'status': 'HOLD', 'reason': '読込不足のため本文追記ではなく入口と起動条件を確認する'}}),
    ]
    rows += deployed_prefix()
    rows += [
        ev('e19', '2026-11-04T02:05:00Z', '2026-11-04', A, 'wu-app-deploy',
           {'kind': 'candidate', 'candidate_id': 'c-review-steps', 'experience_ids': ['x-app-1', 'x-cli-1'],
            'target_skill_id': 'pr-review', 'cause': 'MISSING_PROCEDURE',
            'scope': {'type': 'SHARED', 'basis': 'REPEATED_IN_REPOSITORIES',
                      'repository_ids': ['demo-app', 'demo-cli'], 'decided_by': 'example-owner'},
            'state': {'status': 'DEPLOYED', 'deployment_id': 'd-review-steps',
                      'reason': '個別承認e17に基づき手動反映した'}}),
        ev('e20', '2026-11-04T05:00:00Z', '2026-11-04', A, 'wu-app-4', obs(1)),
        ev('e21', '2026-11-05T05:00:00Z', '2026-11-05', A, 'wu-app-5', obs(2, task='FAILED')),
        ev('e22', '2026-11-06T05:00:00Z', '2026-11-06', A, 'wu-app-6', obs(3)),
        ev('e23', '2026-11-06T05:10:00Z', '2026-11-06', A, 'wu-app-6',
           {'kind': 'deployment_event', 'deployment_id': 'd-review-steps',
            'state': {'status': 'EFFECT_CONFIRMED', 'observation_ids': ['o-1', 'o-2', 'o-3']}}),
    ]
    return rows


def eval_variant(**improvement):
    value = copy.deepcopy(EVAL)
    value['improvement'].update(improvement)
    return value


def scenarios():
    out = []

    def add(sid, check, description, records, expected, manifest_file='manifest.example.json', at=None):
        item = {'scenario_id': sid, 'check': check, 'description': description,
                'manifest': manifest_file, 'records': records, 'expected': expected}
        if at:
            item['at'] = at
        out.append(item)

    full = base_deploy() + [ev('e17', '2026-11-04T01:00:00Z', '2026-11-04', A, 'wu-app-deploy', approved(PLAN))]
    add('deploy-allowed', 'deploy_gate', '全条件がそろった陽性対照。', full,
        {'decision': 'ALLOWED', 'reason': None}, at='2026-11-04T02:00:00Z')
    add('deploy-approval-missing', 'deploy_gate', '計画は固定したが個別承認がない。', base_deploy(),
        {'decision': 'HOLD', 'reason': 'APPROVAL_MISSING'}, at='2026-11-04T02:00:00Z')
    add('deploy-approval-expired', 'deploy_gate', '承認期限後に反映しようとした。', full,
        {'decision': 'HOLD', 'reason': 'APPROVAL_EXPIRED'}, at='2026-11-05T00:00:01Z')
    changed = copy.deepcopy(PLAN)
    changed['target']['deploy_ref'] = 'demo-app:.claude/skills/pr-review-copy/SKILL.md'
    add('deploy-plan-changed-after-approval', 'deploy_gate', '承認後に配備先を差し替えた計画を追記した。',
        base_deploy() + [ev('e17', '2026-11-04T01:00:00Z', '2026-11-04', A, 'wu-app-deploy', approved(PLAN)),
                         ev('e17b', '2026-11-04T01:30:00Z', '2026-11-04', A, 'wu-app-deploy', changed)],
        {'decision': 'HOLD', 'reason': 'APPROVAL_MISMATCH'}, at='2026-11-04T02:00:00Z')
    add('deploy-record-only-stage', 'deploy_gate', 'manifestが記録のみの段階なので承認があっても反映しない。', full,
        {'decision': 'HOLD', 'reason': 'STAGE_RECORD_ONLY'}, manifest_file='manifest.record-only.example.json',
        at='2026-11-04T02:00:00Z')

    for sid, desc, imp, verdict in [
            ('evaluation-tie', 'baselineと候補が同点。', {'baseline_passed': 2, 'candidate_passed': 2}, 'IMPROVEMENT_UNCONFIRMED'),
            ('evaluation-unstable', '3試行の結果が揺らいだ。', {'stable': False}, 'IMPROVEMENT_UNCONFIRMED'),
            ('evaluation-control-invalid', '劣化対照が不合格にならず比較不能。', {'control_valid': False}, 'IMPROVEMENT_UNCONFIRMED')]:
        value = eval_variant(**imp)
        value['verdict'] = verdict
        add(sid, 'evaluation', desc, [ev('e14', '2026-11-03T09:00:00Z', '2026-11-03', A, 'wu-app-eval', value)],
            {'decision': verdict, 'reason': None})
    reg = copy.deepcopy(EVAL)
    reg['regression']['candidate_failed_among_them'] = 1
    reg['verdict'] = 'REGRESSED'
    add('evaluation-regressed', 'evaluation', '改善対象は良くなったが既存の合格ケースを1件落とした。',
        [ev('e14', '2026-11-03T09:00:00Z', '2026-11-03', A, 'wu-app-eval', reg)],
        {'decision': 'REGRESSED', 'reason': None})
    human = copy.deepcopy(EVAL)
    human['improvement'] = {'method': 'HUMAN_COMPARISON', 'reviewer': 'example-owner',
                            'not_deterministic_reason': '説明文の分かりやすさは決定的に判定できない',
                            'preferred': 'TIE'}
    human['verdict'] = 'IMPROVEMENT_UNCONFIRMED'
    add('evaluation-human-tie', 'evaluation', '人間比較で差がない。',
        [ev('e14', '2026-11-03T09:00:00Z', '2026-11-03', A, 'wu-app-eval', human)],
        {'decision': 'IMPROVEMENT_UNCONFIRMED', 'reason': None})

    dropped = copy.deepcopy(SIZE)
    dropped.update(lines_after=78, net_added_lines=-18, responsibilities=SIZE['responsibilities'][:2],
                   verdict='HOLD')
    add('size-responsibility-dropped', 'size_review', '行数は減ったが停止条件の責務r-stopの行き先がない。',
        [ev('e15', '2026-11-03T09:10:00Z', '2026-11-03', A, 'wu-app-eval', dropped)],
        {'decision': 'HOLD', 'reason': 'RESPONSIBILITY_UNACCOUNTED'})
    over = copy.deepcopy(SIZE)
    over.update(lines_after=131, net_added_lines=35, moved_to=['demo-app:.claude/skills/pr-review/reference.md'],
                exception_reason='手順の順序を1か所で読めることを優先し、詳細例だけ参照へ分離した',
                verdict='EXCEPTION_RECORDED')
    over['responsibilities'] = SIZE['responsibilities'][:2] + [
        {'id': 'r-stop', 'status': 'MOVED', 'location': 'reference.md#stop'}]
    add('size-over-guide-with-reason', 'size_review', '目安超過だが理由付き例外と責務の移動先がある。',
        [ev('e15', '2026-11-03T09:10:00Z', '2026-11-03', A, 'wu-app-eval', over)],
        {'decision': 'EXCEPTION_RECORDED', 'reason': None})
    over_no = copy.deepcopy(over)
    over_no.update(exception_reason=None, verdict='HOLD')
    add('size-over-guide-without-reason', 'size_review', '目安超過で理由がない。',
        [ev('e15', '2026-11-03T09:10:00Z', '2026-11-03', A, 'wu-app-eval', over_no)],
        {'decision': 'HOLD', 'reason': 'OVER_GUIDE_WITHOUT_REASON'})

    def obs_rows(items):
        return [ev(f'eo{i}', f'2026-11-0{4 + i}T05:00:00Z', f'2026-11-0{4 + i}', A, f'wu-app-o{i}', item)
                for i, item in enumerate(items)]
    add('effect-window-short', 'effect_window', '反映後の該当作業が2件しかない。', deployed_prefix() + obs_rows([obs(1), obs(2)]),
        {'decision': 'EFFECT_UNCONFIRMED', 'reason': 'WINDOW_INCOMPLETE'})
    add('effect-not-loaded-first', 'effect_window', '最初の該当作業ではSkillが読まれず、窓は読込確認から始まる。',
        deployed_prefix() + obs_rows([obs(1, applied=False), obs(2), obs(3)]),
        {'decision': 'EFFECT_UNCONFIRMED', 'reason': 'WINDOW_INCOMPLETE'})
    add('effect-recurrence', 'effect_window', '同じ問題が2件目で再発した。',
        deployed_prefix() + obs_rows([obs(1), obs(2, recurred=True), obs(3)]),
        {'decision': 'IMPROVEMENT_UNCONFIRMED', 'reason': 'ISSUE_RECURRED'})
    add('effect-unfinished-kept', 'effect_window', '未完了の作業を除外して次の作業で埋めない。',
        deployed_prefix() + obs_rows([obs(1), obs(2, task='UNFINISHED'), obs(3), obs(4)]),
        {'decision': 'IMPROVEMENT_UNCONFIRMED', 'reason': 'OUTCOME_UNKNOWN_IN_WINDOW'})
    add('effect-worsening', 'effect_window', '明確な悪化が起きたので再発とは分けて停止する。',
        deployed_prefix() + obs_rows([obs(1), obs(2, adverse='CLEAR_WORSENING')]),
        {'decision': 'HALTED', 'reason': 'CLEAR_WORSENING'})
    gap = obs_rows([obs(1), obs(3), obs(4)])
    add('effect-sequence-gap', 'effect_window', '2件目の記録が欠けている。', deployed_prefix() + gap,
        {'decision': 'EFFECT_UNCONFIRMED', 'reason': 'SEQUENCE_GAP'})

    halted = deployed_prefix() + obs_rows([obs(1, adverse='MISAPPLICATION')]) + [
        ev('eh', '2026-11-05T06:00:00Z', '2026-11-05', A, 'wu-app-o0',
           {'kind': 'deployment_event', 'deployment_id': 'd-review-steps',
            'state': {'status': 'HALTED', 'trigger': 'MISAPPLICATION', 'observation_id': 'o-1'}})]

    def intent(at='2026-11-05T06:05:00Z', authority=None, executor='example-owner'):
        return ev('er1', at, at[:10], A, 'wu-app-rollback',
                  {'kind': 'deployment_event', 'deployment_id': 'd-review-steps',
                   'state': {'status': 'ROLLING_BACK', 'intent_id': 'ri-1', 'lock_ref': 'approved-local-lock:pr-review',
                             'executor': executor, 'trigger': 'MISAPPLICATION',
                             'authority': authority or {'type': 'PREAPPROVED'},
                             'expected_current_sha256': h('deployed-after'),
                             'backup_sha256': h('deployed-before')}})

    def final(state):
        return ev('er2', '2026-11-05T06:06:00Z', '2026-11-05', A, 'wu-app-rollback',
                  {'kind': 'deployment_event', 'deployment_id': 'd-review-steps', 'state': state})
    add('rollback-success', 'rollback', '事前承認内で現在hashを照合して復元した。',
        halted + [intent(), final({'status': 'ROLLED_BACK', 'intent_id': 'ri-1',
                                    'observed_current_sha256': h('deployed-after'),
                                    'restored_sha256': h('deployed-before')})],
        {'decision': 'ROLLED_BACK', 'reason': None})
    add('rollback-hash-conflict', 'rollback', '現在hashが想定した候補と違うので上書きしない。',
        halted + [intent(), final({'status': 'RECOVERY_REQUIRED', 'intent_id': 'ri-1',
                                    'reason': 'CURRENT_HASH_MISMATCH',
                                    'observed_current_sha256': h('edited-by-someone-else')})],
        {'decision': 'RECOVERY_REQUIRED', 'reason': 'CURRENT_HASH_MISMATCH'})
    add('rollback-partial-write', 'rollback', 'intentを残したまま終了記録がない（途中書込）。',
        halted + [intent()], {'decision': 'RECOVERY_REQUIRED', 'reason': 'PARTIAL_WRITE'})
    add('rollback-preapproval-expired', 'rollback', '事前承認の期限後に即時rollbackしようとした。',
        halted + [intent(at='2026-11-20T00:00:01Z')], {'decision': 'HOLD', 'reason': 'ROLLBACK_NOT_AUTHORIZED'})
    add('rollback-other-executor', 'rollback', '事前承認にない実行者が即時rollbackしようとした。',
        halted + [intent(executor='someone-else')], {'decision': 'HOLD', 'reason': 'ROLLBACK_NOT_AUTHORIZED'})

    skip = base_deploy() + [ev('e18', '2026-11-04T02:00:00Z', '2026-11-04', A, 'wu-app-deploy', deployed())]
    add('transition-deploy-without-approval', 'transition', 'APPROVEDを経ずに反映済みを記録した。', skip,
        {'decision': 'REJECTED', 'reason': 'ILLEGAL_TRANSITION'})
    return out


def dump(value):
    return json.dumps(value, ensure_ascii=False, indent=2) + '\n'


def build():
    """Return {path relative to this directory: file text}."""
    files = {
        'manifest.example.json': dump(manifest('RECORD_AND_MANUAL_IMPROVEMENT', 'example-manual-improvement')),
        'manifest.record-only.example.json': dump(manifest('RECORD_ONLY', 'example-record-only')),
        'ledger.example.jsonl': ''.join(json.dumps(row, ensure_ascii=False) + '\n' for row in ledger()),
    }
    for item in scenarios():
        files[f"scenarios/{item['scenario_id']}.json"] = dump(item)
    return files


def main():
    for name, text in build().items():
        path = OUT / name
        path.parent.mkdir(exist_ok=True)
        path.write_text(text, encoding='utf-8')


if __name__ == '__main__':
    main()
