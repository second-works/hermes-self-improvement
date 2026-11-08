"""Check the Skill improvement MVP contract (#106) against its PUBLIC examples.

The judges below restate the decision rules of docs/skill-improvement-mvp.md as code,
so each recorded verdict and each scenario expectation must follow from the data
instead of being copied from the document text. No CLI, model call, or file write.
"""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import unittest
from zoneinfo import ZoneInfo
from datetime import datetime

ROOT = Path(__file__).resolve().parents[1]
SCHEMAS = ROOT / 'schemas/skill-improvement'
FIXTURES = ROOT / 'fixtures/skill_improvement'
DOC = ROOT / 'docs/skill-improvement-mvp.md'

SUPPORTED = {'$schema', '$id', 'title', 'description', '$defs', '$ref', 'type', 'const', 'enum',
             'required', 'properties', 'additionalProperties', 'items', 'minItems', 'maxItems',
             'uniqueItems', 'pattern', 'minLength', 'maxLength', 'minimum', 'maximum', 'oneOf'}
DEPLOYED_STATES = {'DEPLOYED_EFFECT_UNCONFIRMED', 'EFFECT_CONFIRMED', 'IMPROVEMENT_UNCONFIRMED', 'HALTED',
                   'ROLLING_BACK', 'ROLLED_BACK', 'RECOVERY_REQUIRED'}
TYPES = {'object': dict, 'array': list, 'string': str, 'integer': int, 'boolean': bool,
         'null': type(None)}


def load(path):
    return json.loads(path.read_text(encoding='utf-8'))


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()


def sha(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def same(left, right):
    return type(left) is type(right) and left == right


def schema_errors(value, schema, root, path='$'):
    """Validate the small keyword set the published schemas are allowed to use."""
    unknown = set(schema) - SUPPORTED
    if unknown:
        raise AssertionError(f'unsupported schema keyword at {path}: {sorted(unknown)}')
    if '$ref' in schema:
        name = schema['$ref'].removeprefix('#/$defs/')
        return schema_errors(value, root['$defs'][name], root, path)
    if 'oneOf' in schema:
        matched = sum(not schema_errors(value, branch, root, path) for branch in schema['oneOf'])
        return [] if matched == 1 else [f'{path}: oneOf matched {matched}']
    errors = []
    kind = schema.get('type')
    if kind and type(value) is not TYPES[kind]:
        return [f'{path}: expected {kind}']
    if 'const' in schema and not same(value, schema['const']):
        errors.append(f'{path}: const')
    if 'enum' in schema and not any(same(value, item) for item in schema['enum']):
        errors.append(f'{path}: enum')
    if kind == 'object':
        if schema.get('additionalProperties') is not False:
            raise AssertionError(f'object schema must close additionalProperties at {path}')
        missing = set(schema.get('required', [])) - set(value)
        extra = set(value) - set(schema.get('properties', {}))
        errors += [f'{path}: missing {sorted(missing)}'] if missing else []
        errors += [f'{path}: unexpected {sorted(extra)}'] if extra else []
        for name, item in value.items():
            if name in schema.get('properties', {}):
                errors += schema_errors(item, schema['properties'][name], root, f'{path}.{name}')
    if kind == 'array':
        if not schema.get('minItems', 0) <= len(value) <= schema.get('maxItems', len(value)):
            errors.append(f'{path}: item count')
        if schema.get('uniqueItems') and len({canonical(item) for item in value}) != len(value):
            errors.append(f'{path}: duplicate items')
        for index, item in enumerate(value):
            errors += schema_errors(item, schema['items'], root, f'{path}[{index}]')
    if kind == 'string':
        if 'pattern' in schema and not re.search(schema['pattern'], value):
            errors.append(f'{path}: pattern')
        if not schema.get('minLength', 0) <= len(value) <= schema.get('maxLength', len(value)):
            errors.append(f'{path}: length')
    if kind == 'integer' and not schema.get('minimum', value) <= value <= schema.get('maximum', value):
        errors.append(f'{path}: range')
    return errors


def walk_subschemas(schema):
    yield schema
    children = list(schema.get('$defs', {}).values()) + list(schema.get('properties', {}).values())
    children += schema.get('oneOf', []) + ([schema['items']] if 'items' in schema else [])
    for child in children:
        yield from walk_subschemas(child)


def records(rows, kind, **match):
    return [row for row in rows if row['record']['kind'] == kind and
            all(row['record'].get(key) == value for key, value in match.items())]


def deployment_states(rows, deployment_id):
    return [row for row in rows if row['record'].get('deployment_id') == deployment_id and
            row['record']['kind'] == 'deployment_event']


# --- Judges: the decision tables of docs/skill-improvement-mvp.md as code ---

def judge_evaluation(value):
    contract = value['required_contract']
    if contract['candidate_passed'] > contract['cases']:
        raise AssertionError('more passes than required cases')
    if contract['candidate_passed'] < contract['cases']:
        return 'CONTRACT_FAILED'
    if value['regression']['candidate_failed_among_them'] > 0:
        return 'REGRESSED'
    improvement = value['improvement']
    if improvement['method'] == 'DETERMINISTIC':
        improved = (improvement['candidate_passed'] > improvement['baseline_passed'] and
                    improvement['stable'] and improvement['control_valid'])
    else:
        improved = improvement['preferred'] == 'CANDIDATE'
    return 'IMPROVED' if improved else 'IMPROVEMENT_UNCONFIRMED'


def judge_size(value):
    listed = [item['id'] for item in value['responsibilities']]
    if set(value['responsibilities_before']) - set(listed):
        return 'HOLD', 'RESPONSIBILITY_UNACCOUNTED'
    if len(listed) != len(set(listed)) or set(listed) - set(value['responsibilities_before']):
        return 'HOLD', 'RESPONSIBILITY_UNKNOWN'
    if value['net_added_lines'] != value['lines_after'] - value['lines_before']:
        return 'HOLD', 'LINE_COUNT_MISMATCH'
    if value['lines_after'] > value['guide_lines']:
        if value['exception_reason'] is None:
            return 'HOLD', 'OVER_GUIDE_WITHOUT_REASON'
        return 'EXCEPTION_RECORDED', None
    return 'WITHIN_GUIDE', None


def replay(rows, transitions):
    """Return (deployment final states, candidate final states, illegal transitions)."""
    deployment, candidate, illegal, planned_for = {}, {}, [], {}
    for row in rows:
        record = row['record']
        if record['kind'] == 'candidate' and 'deployment_id' in record['state']:
            linked = record['state']['deployment_id']
            needed = DEPLOYED_STATES if record['state']['status'] == 'DEPLOYED' else {'ROLLED_BACK'}
            if deployment.get(linked) not in needed or planned_for.get(linked) != record['candidate_id']:
                illegal.append((row['event_id'], 'deployment', deployment.get(linked)))
        if record['kind'] == 'deployment_plan':
            planned_for[record['deployment_id']] = record['candidate_id']
            key, new, table, store = record['deployment_id'], 'PLANNED', 'deployment', deployment
        elif record['kind'] == 'deployment_event':
            key, new, table, store = record['deployment_id'], record['state']['status'], 'deployment', deployment
        elif record['kind'] == 'candidate':
            key, new, table, store = record['candidate_id'], record['state']['status'], 'candidate', candidate
        else:
            continue
        current = store.get(key)
        allowed = (transitions[table]['initial'] if current is None
                   else transitions[table]['transitions'][current])
        if new not in allowed:
            illegal.append((row['event_id'], current, new))
        store[key] = new
    return deployment, candidate, illegal


def local_date(utc, timezone):
    moment = datetime.strptime(utc, '%Y-%m-%dT%H:%M:%SZ').replace(tzinfo=ZoneInfo('UTC'))
    return moment.astimezone(ZoneInfo(timezone)).date().isoformat()


def judge_deploy_gate(manifest, rows, at):
    plan_row = records(rows, 'deployment_plan')[-1]
    plan = plan_row['record']
    listed = [item['repository_id'] for item in manifest['repositories']]
    if len(listed) != len(set(listed)):
        return 'HOLD', 'MANIFEST_DUPLICATE_REPOSITORY'
    repositories = set(listed)
    if plan_row['repository_id'] not in repositories:
        return 'HOLD', 'REPOSITORY_NOT_IN_MANIFEST'
    if manifest['stage'] != 'RECORD_AND_MANUAL_IMPROVEMENT':
        return 'HOLD', 'STAGE_RECORD_ONLY'
    if not manifest['period']['start_date'] <= local_date(at, manifest['timezone']) <= manifest['period']['end_date']:
        return 'HOLD', 'OUTSIDE_PERIOD'
    evaluations = records(rows, 'evaluation', evaluation_id=plan['evaluation_id'])
    if not evaluations or judge_evaluation(evaluations[-1]['record']) != 'IMPROVED':
        return 'HOLD', 'EVALUATION_NOT_IMPROVED'
    evaluation = evaluations[-1]['record']
    if (evaluation['candidate_id'], evaluation['baseline_sha256'], evaluation['candidate_sha256'],
            evaluation['evaluation_sha256']) != (plan['candidate_id'], plan['hashes']['baseline'],
                                                 plan['hashes']['candidate'], plan['hashes']['evaluation']):
        return 'HOLD', 'EVALUATION_MISMATCH'
    reviews = records(rows, 'size_review', review_id=plan['size_review_id'])
    if not reviews or judge_size(reviews[-1]['record'])[0] == 'HOLD':
        return 'HOLD', 'SIZE_REVIEW_HOLD'
    approvals = [row for row in deployment_states(rows, plan['deployment_id'])
                 if row['record']['state']['status'] == 'APPROVED']
    if not approvals:
        return 'HOLD', 'APPROVAL_MISSING'
    approval = approvals[-1]['record']['state']
    if approval['plan_sha256'] != sha(plan) or approval['plan_event_id'] != plan_row['event_id'] or \
            rows.index(approvals[-1]) < rows.index(plan_row):
        return 'HOLD', 'APPROVAL_MISMATCH'
    if not approval['approved_at'] <= at < approval['expires_at']:
        return 'HOLD', 'APPROVAL_EXPIRED'
    if at >= plan['deadline']:
        return 'HOLD', 'DEADLINE_PASSED'
    if plan['route']['type'] == 'OWNER_REPOSITORY_PR' and not any(
            row['record']['state']['status'] == 'MERGED'
            for row in deployment_states(rows, plan['deployment_id'])
            if rows.index(row) > rows.index(approvals[-1])):
        return 'HOLD', 'MERGE_MISSING'
    return 'ALLOWED', None


def effect_window(rows, deployment_id):
    deployed = [row for row in deployment_states(rows, deployment_id)
                if row['record']['state']['status'] == 'DEPLOYED_EFFECT_UNCONFIRMED']
    if not deployed:
        return 'EFFECT_UNCONFIRMED', 'NOT_DEPLOYED', []
    deployed_at = deployed[-1]['record']['state']['deployed_at']
    observations = sorted((row['record'] for row in records(rows, 'effect_observation', deployment_id=deployment_id)
                           if row['recorded_at'] > deployed_at),
                          key=lambda item: item['sequence'])
    adverse = [item for item in observations if item['adverse'] is not None]
    if adverse:
        return 'HALTED', adverse[0]['adverse'], []
    if [item['sequence'] for item in observations] != list(range(1, len(observations) + 1)):
        return 'EFFECT_UNCONFIRMED', 'SEQUENCE_GAP', []
    start = next((index for index, item in enumerate(observations)
                  if item['applicable'] and item['skill_applied']), None)
    window = [] if start is None else [item for item in observations[start:] if item['applicable']][:3]
    ids = [item['observation_id'] for item in window]
    if any(item['issue_recurred'] for item in window):
        return 'IMPROVEMENT_UNCONFIRMED', 'ISSUE_RECURRED', ids
    if any(not item['skill_applied'] for item in window):
        return 'IMPROVEMENT_UNCONFIRMED', 'NOT_APPLIED_IN_WINDOW', ids
    if any(item['task_result'] == 'UNFINISHED' for item in window):
        return 'IMPROVEMENT_UNCONFIRMED', 'OUTCOME_UNKNOWN_IN_WINDOW', ids
    if len(window) < 3:
        return 'EFFECT_UNCONFIRMED', 'WINDOW_INCOMPLETE', ids
    return 'EFFECT_CONFIRMED', None, ids


def judge_rollback(rows, deployment_id):
    plan = records(rows, 'deployment_plan', deployment_id=deployment_id)[-1]['record']
    states = deployment_states(rows, deployment_id)
    intent_row = [row for row in states if row['record']['state']['status'] == 'ROLLING_BACK'][-1]
    intent = intent_row['record']['state']
    at = intent_row['recorded_at']
    halts = [row['record']['state'] for row in states[:states.index(intent_row)]
             if row['record']['state']['status'] == 'HALTED']
    if not halts or halts[-1]['trigger'] != intent['trigger']:
        return 'HOLD', 'TRIGGER_MISMATCH'
    authority = intent['authority']
    if authority['type'] == 'PREAPPROVED':
        allowed = plan['rollback_preapproval']
        authorized = bool(allowed) and intent['executor'] == allowed['executor'] and \
            intent['trigger'] in allowed['conditions'] and at < allowed['expires_at']
    else:
        authorized = authority['approved_at'] <= at < authority['expires_at']
    if not authorized:
        return 'HOLD', 'ROLLBACK_NOT_AUTHORIZED'
    if (intent['expected_current_sha256'], intent['backup_sha256']) != (
            plan['hashes']['expected_after'], plan['backup']['sha256']):
        return 'HOLD', 'INTENT_MISMATCH'
    finals = [row['record']['state'] for row in states[states.index(intent_row) + 1:]
              if row['record']['state'].get('intent_id') == intent['intent_id']]
    if not finals:
        return 'RECOVERY_REQUIRED', 'PARTIAL_WRITE'
    final = finals[-1]
    observed = final['observed_current_sha256']
    if observed is not None and observed != intent['expected_current_sha256']:
        return 'RECOVERY_REQUIRED', 'CURRENT_HASH_MISMATCH'
    if final['status'] == 'RECOVERY_REQUIRED':
        # Without a mismatching hash the recorded cause must be one the facts allow.
        allowed = {'PARTIAL_WRITE', 'UNKNOWN_RESULT'} if observed is None else \
            {'PARTIAL_WRITE', 'UNKNOWN_RESULT', 'RESTORED_HASH_MISMATCH'}
        return 'RECOVERY_REQUIRED', final['reason'] if final['reason'] in allowed else 'REASON_INCONSISTENT'
    if final['restored_sha256'] != plan['hashes']['expected_before']:
        return 'RECOVERY_REQUIRED', 'RESTORED_HASH_MISMATCH'
    return 'ROLLED_BACK', None


class SkillImprovementContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ledger_schema = load(SCHEMAS / 'ledger-record.schema.json')
        cls.manifest_schema = load(SCHEMAS / 'repository-manifest.schema.json')
        cls.transitions = load(SCHEMAS / 'state-transitions.json')
        cls.manifests = {path.name: load(path) for path in FIXTURES.glob('manifest*.json')}
        lines = (FIXTURES / 'ledger.example.jsonl').read_text(encoding='utf-8').splitlines()
        cls.ledger = [json.loads(line) for line in lines]
        cls.scenarios = {path.stem: load(path) for path in sorted((FIXTURES / 'scenarios').glob('*.json'))}

    def assert_valid(self, value, schema):
        self.assertEqual(schema_errors(value, schema, schema), [])

    def assert_record_valid(self, row):
        self.assert_valid(row, self.ledger_schema)
        self.assertEqual(row['classification'], 'PUBLIC')

    def test_schemas_use_only_checked_keywords_and_resolvable_refs(self):
        for schema in (self.ledger_schema, self.manifest_schema):
            for node in walk_subschemas(schema):
                self.assertEqual(set(node) - SUPPORTED, set())
                if '$ref' in node:
                    self.assertIn(node['$ref'].removeprefix('#/$defs/'), schema['$defs'])
        deployment = self.transitions['deployment']['transitions']
        statuses = {branch['properties']['status']['const']
                    for branch in self.ledger_schema['$defs']['deployment_event']['properties']['state']['oneOf']}
        self.assertEqual(set(deployment), statuses | {'PLANNED'})
        for table in self.transitions.values():
            if isinstance(table, dict):
                for targets in table['transitions'].values():
                    self.assertLessEqual(set(targets), set(table['transitions']))

    def test_manifests_need_two_public_repositories_and_separate_stages(self):
        for manifest in self.manifests.values():
            self.assert_valid(manifest, self.manifest_schema)
            self.assertEqual(manifest['classification'], 'PUBLIC')
        stages = {manifest['stage'] for manifest in self.manifests.values()}
        self.assertEqual(stages, {'RECORD_ONLY', 'RECORD_AND_MANUAL_IMPROVEMENT'})
        one_repo = copy.deepcopy(self.manifests['manifest.example.json'])
        one_repo['repositories'] = one_repo['repositories'][:1]
        self.assertTrue(schema_errors(one_repo, self.manifest_schema, self.manifest_schema))
        unknown_owner = copy.deepcopy(self.manifests['manifest.example.json'])
        del unknown_owner['repositories'][0]['owner']
        self.assertTrue(schema_errors(unknown_owner, self.manifest_schema, self.manifest_schema))

    def test_schema_rejects_states_that_hide_missing_reasons_or_links(self):
        rows = {row['event_id']: row for row in self.ledger}
        broken = []
        undetermined = copy.deepcopy(rows['e04'])
        del undetermined['record']['reason']
        broken.append(undetermined)
        no_candidate = copy.deepcopy(rows['e03'])
        no_candidate['record']['experience_ids'] = ['x-app-1']
        broken.append(no_candidate)
        duplicate = copy.deepcopy(rows['e11'])
        del duplicate['record']['state']['duplicate_of']
        broken.append(duplicate)
        declined = copy.deepcopy(rows['e12'])
        del declined['record']['state']['reason']
        broken.append(declined)
        shared = copy.deepcopy(rows['e10'])
        shared['record']['scope']['repository_ids'] = ['demo-app']
        broken.append(shared)
        deployed = copy.deepcopy(rows['e18'])
        del deployed['record']['state']['approval_event_id']
        broken.append(deployed)
        unknown = copy.deepcopy(rows['e23'])
        unknown['record']['state']['status'] = 'DONE'
        broken.append(unknown)
        for row in broken:
            with self.subTest(event=row['event_id']):
                self.assertTrue(schema_errors(row, self.ledger_schema, self.ledger_schema))

    def test_ledger_example_is_valid_linked_and_covers_mvp_records(self):
        manifest = self.manifests['manifest.example.json']
        repositories = {item['repository_id'] for item in manifest['repositories']}
        ids = [row['event_id'] for row in self.ledger]
        self.assertEqual(len(ids), len(set(ids)))
        for row in self.ledger:
            with self.subTest(event=row['event_id']):
                self.assert_record_valid(row)
                self.assertIn(row['repository_id'], repositories)
                self.assertEqual(row['timezone'], manifest['timezone'])

        ends = {row['event_id']: row for row in records(self.ledger, 'session_end')}
        experiences = {row['record']['experience_id']: row for row in records(self.ledger, 'experience')}
        self.assertEqual({row['record']['status'] for row in ends.values()},
                         {'CANDIDATE_FOUND', 'NO_CANDIDATE', 'UNDETERMINED'})
        self.assertEqual({row['record']['experience_type'] for row in experiences.values()},
                         {'CORRECTION', 'REWORK', 'REPEATED_FEEDBACK', 'BETTER_METHOD'})
        claimed = [item for row in ends.values() for item in row['record'].get('experience_ids', [])]
        self.assertEqual(sorted(claimed), sorted(experiences))
        for experience_id, row in experiences.items():
            end = ends[row['record']['end_event_id']]
            self.assertIn(experience_id, end['record']['experience_ids'])
            self.assertEqual((row['repository_id'], row['work_unit_id']),
                             (end['repository_id'], end['work_unit_id']))

        candidates = records(self.ledger, 'candidate')
        candidate_ids = {row['record']['candidate_id'] for row in candidates}
        self.assertTrue({'DUPLICATE', 'DECLINED', 'HOLD', 'DEPLOYED'} <=
                        {row['record']['state']['status'] for row in candidates})
        for row in candidates:
            record = row['record']
            self.assertLessEqual(set(record['experience_ids']), set(experiences))
            if record['state']['status'] == 'DUPLICATE':
                original = [item['record'] for item in candidates
                            if item['record']['candidate_id'] == record['state']['duplicate_of']]
                self.assertTrue(original)
                self.assertNotEqual(record['candidate_id'], record['state']['duplicate_of'])
                self.assertTrue(set(record['experience_ids']) & set(original[0]['experience_ids']))
            if record['scope']['type'] == 'SHARED' and record['scope']['basis'] == 'REPEATED_IN_REPOSITORIES':
                sources = {experiences[item]['repository_id'] for item in record['experience_ids']}
                self.assertLessEqual(set(record['scope']['repository_ids']), sources)
        self.assertIn('c-review-steps', candidate_ids)

    def test_ledger_verdicts_and_states_follow_from_recorded_data(self):
        deployment, candidate, illegal = replay(self.ledger, self.transitions)
        self.assertEqual(illegal, [])
        self.assertEqual(deployment, {'d-review-steps': 'EFFECT_CONFIRMED'})
        self.assertEqual(candidate['c-review-steps'], 'DEPLOYED')
        for row in records(self.ledger, 'evaluation'):
            self.assertEqual(row['record']['verdict'], judge_evaluation(row['record']))
        for row in records(self.ledger, 'size_review'):
            self.assertEqual(row['record']['verdict'], judge_size(row['record'])[0])

        plan = records(self.ledger, 'deployment_plan')[-1]['record']
        states = {row['record']['state']['status']: row for row in deployment_states(self.ledger, 'd-review-steps')}
        deployed = states['DEPLOYED_EFFECT_UNCONFIRMED']
        self.assertEqual(judge_deploy_gate(self.manifests['manifest.example.json'], self.ledger,
                                           deployed['record']['state']['deployed_at']), ('ALLOWED', None))
        self.assertEqual(deployed['record']['state']['approval_event_id'], states['APPROVED']['event_id'])
        self.assertEqual((deployed['record']['state']['observed_before_sha256'],
                          deployed['record']['state']['observed_after_sha256']),
                         (plan['hashes']['expected_before'], plan['hashes']['expected_after']))
        self.assertEqual(plan['backup']['sha256'], plan['hashes']['expected_before'])
        for row in records(self.ledger, 'effect_observation'):
            self.assertGreater(row['recorded_at'], deployed['recorded_at'])
        verdict, reason, window = effect_window(self.ledger, 'd-review-steps')
        self.assertEqual((verdict, reason), ('EFFECT_CONFIRMED', None))
        self.assertEqual(states['EFFECT_CONFIRMED']['record']['state']['observation_ids'], window)
        self.assertIn('FAILED', [row['record']['task_result'] for row in records(self.ledger, 'effect_observation')])

    def test_scenarios_reach_the_documented_hold_stop_or_recovery_outcome(self):
        checks = {
            'deploy_gate': lambda item: judge_deploy_gate(self.manifests[item['manifest']], item['records'], item['at']),
            'evaluation': lambda item: (judge_evaluation(item['records'][-1]['record']), None),
            'size_review': lambda item: judge_size(item['records'][-1]['record']),
            'effect_window': lambda item: effect_window(item['records'], 'd-review-steps')[:2],
            'rollback': lambda item: judge_rollback(item['records'], 'd-review-steps'),
            'transition': lambda item: ('REJECTED', 'ILLEGAL_TRANSITION')
            if replay(item['records'], self.transitions)[2] else ('ACCEPTED', None),
        }
        for name, item in self.scenarios.items():
            with self.subTest(scenario=name):
                self.assertEqual(item['scenario_id'], name)
                for row in item['records']:
                    self.assert_record_valid(row)
                if item['check'] != 'transition':
                    self.assertEqual(replay(item['records'], self.transitions)[2], [])
                outcome = checks[item['check']](item)
                self.assertEqual(outcome, (item['expected']['decision'], item['expected']['reason']))
                recorded = item['records'][-1]['record']
                if item['check'] in ('evaluation', 'size_review'):
                    self.assertEqual(recorded['verdict'], outcome[0])
                if item['check'] == 'rollback' and recorded['kind'] == 'deployment_event' and \
                        recorded['state']['status'] in ('ROLLED_BACK', 'RECOVERY_REQUIRED'):
                    self.assertEqual(recorded['state']['status'], outcome[0])
                    self.assertEqual(recorded['state'].get('reason'), outcome[1])
        required = {('deploy_gate', 'APPROVAL_MISSING'), ('deploy_gate', 'APPROVAL_EXPIRED'),
                    ('deploy_gate', 'STAGE_RECORD_ONLY'), ('evaluation', 'IMPROVEMENT_UNCONFIRMED'),
                    ('size_review', 'HOLD'), ('rollback', 'CURRENT_HASH_MISMATCH'),
                    ('rollback', 'PARTIAL_WRITE'), ('effect_window', 'HALTED'),
                    ('effect_window', 'IMPROVEMENT_UNCONFIRMED'), ('transition', 'REJECTED')}
        present = {(item['check'], item['expected']['reason'] or item['expected']['decision'])
                   for item in self.scenarios.values()}
        present |= {(item['check'], item['expected']['decision']) for item in self.scenarios.values()}
        self.assertLessEqual(required, present)

    def test_judges_react_to_changed_facts_not_to_recorded_labels(self):
        allowed = self.scenarios['deploy-allowed']
        manifest = self.manifests['manifest.example.json']
        tampered = copy.deepcopy(allowed['records'])
        tampered[2]['record']['backup']['ref'] = 'another-backup'
        self.assertEqual(judge_deploy_gate(manifest, tampered, allowed['at']), ('HOLD', 'APPROVAL_MISMATCH'))
        outside = copy.deepcopy(manifest)
        outside['repositories'] = [item for item in outside['repositories'] if item['repository_id'] != 'demo-app']
        outside['repositories'].append({**manifest['repositories'][1], 'repository_id': 'demo-other'})
        self.assertEqual(judge_deploy_gate(outside, allowed['records'], allowed['at']),
                         ('HOLD', 'REPOSITORY_NOT_IN_MANIFEST'))
        unimproved = copy.deepcopy(allowed['records'])
        unimproved[0]['record']['improvement']['candidate_passed'] = 1
        self.assertEqual(judge_deploy_gate(manifest, unimproved, allowed['at']), ('HOLD', 'EVALUATION_NOT_IMPROVED'))
        owner_route = copy.deepcopy(allowed['records'])
        owner_route[2]['record']['route'] = {'type': 'OWNER_REPOSITORY_PR', 'owner_repository_id': 'demo-cli',
                                             'issue_ref': 'synthetic:demo-cli/issue-9'}
        owner_route[3]['record']['state']['plan_sha256'] = sha(owner_route[2]['record'])
        self.assertEqual(judge_deploy_gate(manifest, owner_route, allowed['at']), ('HOLD', 'MERGE_MISSING'))

        success = copy.deepcopy(self.scenarios['rollback-success']['records'])
        success[-1]['record']['state']['observed_current_sha256'] = '0' * 64
        self.assertEqual(judge_rollback(success, 'd-review-steps'), ('RECOVERY_REQUIRED', 'CURRENT_HASH_MISMATCH'))
        unknown = copy.deepcopy(self.scenarios['rollback-hash-conflict']['records'])
        unknown[-1]['record']['state'].update(observed_current_sha256=None, reason='UNKNOWN_RESULT')
        self.assertEqual(judge_rollback(unknown, 'd-review-steps'), ('RECOVERY_REQUIRED', 'UNKNOWN_RESULT'))
        restored_wrong = copy.deepcopy(self.scenarios['rollback-success']['records'])
        restored_wrong[-1]['record']['state']['restored_sha256'] = '1' * 64
        self.assertEqual(judge_rollback(restored_wrong, 'd-review-steps'),
                         ('RECOVERY_REQUIRED', 'RESTORED_HASH_MISMATCH'))

        confirmed = copy.deepcopy(self.ledger)
        confirmed = [row for row in confirmed if row['event_id'] != 'e22']
        self.assertEqual(effect_window(confirmed, 'd-review-steps')[:2], ('EFFECT_UNCONFIRMED', 'WINDOW_INCOMPLETE'))

    def test_review_findings_are_rejected_by_the_judges(self):
        manifest = self.manifests['manifest.example.json']
        allowed = self.scenarios['deploy-allowed']
        # Preapproval may not be borrowed with a trigger other than the one that halted the deployment.
        borrowed = copy.deepcopy(self.scenarios['rollback-success']['records'])
        intent = next(row for row in borrowed if row['record'].get('state', {}).get('status') == 'ROLLING_BACK')
        intent['record']['state']['trigger'] = 'USER_WITHDRAWAL'
        self.assertEqual(judge_rollback(borrowed, 'd-review-steps'), ('HOLD', 'TRIGGER_MISMATCH'))
        # A candidate cannot claim DEPLOYED / ROLLED_BACK without the deployment reaching that state.
        early = [row for row in copy.deepcopy(self.ledger) if row['event_id'] != 'e18']
        self.assertIn(('e19', 'deployment', 'APPROVED'), replay(early, self.transitions)[2])
        rolled = copy.deepcopy(self.ledger) + [copy.deepcopy(self.ledger[-5])]
        rolled[-1]['event_id'] = 'e24'
        rolled[-1]['record']['state']['status'] = 'ROLLED_BACK'
        self.assertIn(('e24', 'deployment', 'EFFECT_CONFIRMED'), replay(rolled, self.transitions)[2])
        # Two entries for one repository do not make two repositories.
        duplicated = copy.deepcopy(manifest)
        duplicated['repositories'][1]['repository_id'] = 'demo-app'
        self.assertEqual(judge_deploy_gate(duplicated, allowed['records'], allowed['at']),
                         ('HOLD', 'MANIFEST_DUPLICATE_REPOSITORY'))
        # The period is read in the manifest timezone (2026-11-15T16:00Z is 11-16 in Asia/Tokyo).
        late = copy.deepcopy(manifest)
        late['period']['start_date'] = '2026-11-04'
        late['period']['end_date'] = '2026-11-04'
        self.assertEqual(judge_deploy_gate(late, allowed['records'], '2026-11-04T14:59:59Z'), ('ALLOWED', None))
        self.assertEqual(judge_deploy_gate(late, allowed['records'], '2026-11-04T15:00:00Z'),
                         ('HOLD', 'OUTSIDE_PERIOD'))
        # The approval must name the plan event it approved.
        renamed = copy.deepcopy(allowed['records'])
        renamed[3]['record']['state']['plan_event_id'] = 'e99'
        self.assertEqual(judge_deploy_gate(manifest, renamed, allowed['at']), ('HOLD', 'APPROVAL_MISMATCH'))
        # A recorded recovery cause has to fit the observed facts.
        mislabeled = copy.deepcopy(self.scenarios['rollback-hash-conflict']['records'])
        mislabeled[-1]['record']['state'].update(observed_current_sha256=None, reason='RESTORED_HASH_MISMATCH')
        self.assertEqual(judge_rollback(mislabeled, 'd-review-steps'), ('RECOVERY_REQUIRED', 'REASON_INCONSISTENT'))
        partial = copy.deepcopy(mislabeled)
        partial[-1]['record']['state']['reason'] = 'PARTIAL_WRITE'
        self.assertEqual(judge_rollback(partial, 'd-review-steps'), ('RECOVERY_REQUIRED', 'PARTIAL_WRITE'))
        # Work recorded before the deployment does not count toward the effect window.
        before = copy.deepcopy(self.ledger)
        for row in before:
            if row['record']['kind'] == 'effect_observation':
                row['recorded_at'] = '2026-11-04T01:30:00Z'
        self.assertEqual(effect_window(before, 'd-review-steps')[:2], ('EFFECT_UNCONFIRMED', 'WINDOW_INCOMPLETE'))
        # Valid IANA names with digits, signs and hyphens are accepted.
        for zone in ('America/Port-au-Prince', 'Etc/GMT+9', 'America/Argentina/Buenos_Aires'):
            changed = copy.deepcopy(manifest)
            changed['timezone'] = zone
            self.assertEqual(schema_errors(changed, self.manifest_schema, self.manifest_schema), [])
            ZoneInfo(zone)

    def test_committed_examples_equal_the_builder_output(self):
        spec = importlib.util.spec_from_file_location('build_examples', FIXTURES / 'build_examples.py')
        builder = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(builder)
        expected = builder.build()
        committed = {path.relative_to(FIXTURES).as_posix(): path.read_text(encoding='utf-8')
                     for path in FIXTURES.rglob('*') if path.is_file() and path.suffix in ('.json', '.jsonl')}
        self.assertEqual(sorted(committed), sorted(expected))
        for name, text in expected.items():
            self.assertEqual(committed[name], text, name)

    def test_document_links_resolve_and_name_the_contract_files(self):
        text = DOC.read_text(encoding='utf-8')
        targets = [target.split('#', 1)[0] for target in re.findall(r'\]\(([^)]+)\)', text)
                   if not target.startswith(('http://', 'https://', '#'))]
        self.assertTrue(targets)
        for target in targets:
            with self.subTest(target=target):
                self.assertTrue((DOC.parent / target).resolve().exists())
        linked = {(DOC.parent / target).resolve() for target in targets}
        for path in (SCHEMAS / 'ledger-record.schema.json', SCHEMAS / 'repository-manifest.schema.json',
                     SCHEMAS / 'state-transitions.json', FIXTURES / 'ledger.example.jsonl', FIXTURES / 'scenarios'):
            self.assertIn(path.resolve(), linked)


if __name__ == '__main__':
    unittest.main()
