"""Strict fixture contracts and evidence rules for Issue #4."""
import hashlib
import json
import re
from datetime import datetime


UPSTREAM = 'f97608f178d1ffeca59860195ab7da295f7c8e5f'
CATEGORIES = ('skill_gap', 'skill_not_selected', 'procedure', 'model_limit',
              'permission_api', 'external_dependency')
CODES = ('SEARCH_COMPLETE', 'SELECTION_SKIPPED', 'STEP_SKIPPED',
         'CONTEXT_LENGTH_EXCEEDED', 'HTTP_401', 'HTTP_403', 'HTTP_429',
         'DEPENDENCY_UNAVAILABLE', 'UNKNOWN', 'SUCCESS')
RESOURCES = ('tools', 'models', 'auth', 'delegation')
ACTIONS = {
    'skill_gap': ('propose_isolated_skill', 'hermes-agent-skill-authoring',
                  'Add an isolated fixture skill for the missing capability.',
                  'The new fixture passes the failing case and existing regression cases.'),
    'skill_not_selected': ('improve_selection', None,
                           'Select an existing eligible skill before creating another.',
                           'The same task selects the existing skill and passes without a new skill.'),
    'procedure': ('repair_procedure', None,
                  'Repair the skipped step in the selected fixture skill.',
                  'The missing step executes and the task and regression cases pass.'),
    'model_limit': ('review_model_limit', None,
                    'Reduce fixture context within the declared model limit.',
                    'The same task passes within the fixed context and zero API budget.'),
    'permission_api': ('review_access_error', None,
                       'Diagnose the API denial in an inert fixture; request human review.',
                       'Denied and allowed fixture responses are distinguished without retrying credentials.'),
    'external_dependency': ('isolate_dependency', None,
                            'Use a deterministic dependency fixture and explicit failure reporting.',
                            'Unavailable dependencies stop explicitly and recovery passes in the fixture.'),
}


class AuditError(Exception):
    """Only fixed codes are reported; never echo untrusted input."""


def require(ok, code='INPUT_SCHEMA'):
    if not ok:
        raise AuditError(code)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'),
                      ensure_ascii=True, allow_nan=False).encode('ascii')


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def decode(data):
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, 'JSON_DUPLICATE')
            result[key] = value
        return result
    try:
        return json.loads(data, object_pairs_hook=pairs,
                          parse_constant=lambda _: require(False, 'JSON_NUMBER'))
    except (ValueError, UnicodeError, RecursionError):
        raise AuditError('JSON_INVALID') from None


def fields(value, names):
    require(type(value) is dict and set(value) == set(names.split()))


def ident(value):
    require(type(value) is str and re.fullmatch(r'[a-z][a-z0-9-]{0,63}', value))


def array(value, maximum=1024):
    require(type(value) is list and len(value) <= maximum)


def identifiers(values):
    array(values, 32)
    for value in values:
        ident(value)
    require(len(set(values)) == len(values), 'DUPLICATE_ID')


def unique(rows):
    require(len({r['id'] for r in rows}) == len(rows), 'DUPLICATE_ID')


def validate(value):
    fields(value, 'schema_version classification source_kind upstream_sha baseline_sha '
           'fixture_id observed_at issue_url profile profiles inventory_complete '
           'skills tools models auth delegation observations')
    require(type(value['schema_version']) is int and value['schema_version'] == 1)
    require(value['classification'] == 'PUBLIC' and value['source_kind'] == 'synthetic-fixture',
            'SOURCE_BOUNDARY')
    require(value['upstream_sha'] == UPSTREAM, 'SOURCE_REVISION')
    ident(value['fixture_id'])
    require(value['issue_url'] == 'https://github.com/second-works/hermes-self-improvement/issues/4')
    require(type(value['observed_at']) is str and
            re.fullmatch(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z', value['observed_at']), 'OBSERVED_AT')
    try:
        datetime.strptime(value['observed_at'], '%Y-%m-%dT%H:%M:%SZ')
    except ValueError:
        raise AuditError('OBSERVED_AT') from None
    require(type(value['baseline_sha']) is str and
            re.fullmatch('[a-f0-9]{40}', value['baseline_sha']), 'BASELINE_SHA')
    identifiers(value['profiles'])
    require(value['profile'] in value['profiles'], 'PROFILE')
    require(type(value['inventory_complete']) is bool)
    array(value['skills'])
    for skill in value['skills']:
        fields(skill, 'id name origin profile enabled compatible priority capabilities')
        ident(skill['id'])
        ident(skill['name'])
        require(skill['origin'] in ('builtin', 'local', 'hub'))
        require(skill['profile'] in value['profiles'], 'PROFILE')
        require(type(skill['enabled']) is bool and type(skill['compatible']) is bool)
        require(type(skill['priority']) is int and 0 <= skill['priority'] <= 1024)
        identifiers(skill['capabilities'])
    unique(value['skills'])
    for kind in RESOURCES:
        array(value[kind], 128)
        for row in value[kind]:
            fields(row, 'id state capabilities')
            ident(row['id'])
            require(row['state'] in ('ready', 'blocked', 'unknown'))
            identifiers(row['capabilities'])
        unique(value[kind])
    array(value['observations'], 256)
    for row in value['observations']:
        fields(row, 'id capability outcome selected_skill model_id tool_id auth_id delegation_id logs')
        ident(row['id'])
        ident(row['capability'])
        require(row['outcome'] in ('failed', 'succeeded'))
        selected = row['selected_skill']
        require(selected is None or type(selected) is str)
        require(selected is None or selected in {s['id'] for s in value['skills']}, 'SKILL_REFERENCE')
        for kind, field in zip(RESOURCES, ('tool_id', 'model_id', 'auth_id', 'delegation_id')):
            resource = next((r for r in value[kind] if r['id'] == row[field]), None)
            require(resource is not None and row['capability'] in resource['capabilities'],
                    'RESOURCE_REFERENCE')
        array(row['logs'], 32)
        for event in row['logs']:
            fields(event, 'line code')
            require(type(event['line']) is int and 1 <= event['line'] <= 1000000)
            require(event['code'] in CODES)
        require(len({e['line'] for e in row['logs']}) == len(row['logs']), 'LOG_LINE_DUPLICATE')
    unique(value['observations'])
    return value


def inventory(value):
    """Origin is provenance, not precedence. Priority is explicit in the fixture."""
    skills = value['skills']
    filtered = [s for s in skills if s['profile'] == value['profile'] and
                s['enabled'] and s['compatible']]
    winners = {}
    for skill in sorted(filtered, key=lambda s: (s['priority'], s['id'])):
        winners.setdefault(skill['name'], skill)
    available = sorted(winners.values(), key=lambda s: s['id'])
    return {'registered_records': len(skills), 'profile_filtered_records': len(filtered),
            'available_unique_names': len(available),
            'by_origin': {origin: sum(s['origin'] == origin for s in skills)
                          for origin in ('builtin', 'local', 'hub')},
            'excluded': {'other_profile': sum(s['profile'] != value['profile'] for s in skills),
                         'disabled_in_profile': sum(s['profile'] == value['profile'] and not s['enabled']
                                                    for s in skills),
                         'incompatible_enabled_in_profile': sum(s['profile'] == value['profile'] and
                                                               s['enabled'] and not s['compatible']
                                                               for s in skills),
                         'duplicate_eligible_names': len(filtered) - len(available)},
            'available_skill_ids': [s['id'] for s in available],
            'skill_records': sorted(skills, key=lambda s: s['id']),
            'profiles': sorted(value['profiles']),
            'resources': {kind: sorted(value[kind], key=lambda r: r['id']) for kind in RESOURCES}}


def diagnose(value, row, available):
    codes = {event['code'] for event in row['logs']}
    matching = [s for s in value['skills'] if s['id'] in available and
                row['capability'] in s['capabilities']]
    known = [s for s in value['skills'] if row['capability'] in s['capabilities']]
    selected = row['selected_skill']
    if selected is not None and selected not in {s['id'] for s in matching}:
        return None, 'INELIGIBLE_SELECTION'
    states = {kind: next(r['state'] for r in value[kind] if r['id'] == row[field])
              for kind, field in zip(RESOURCES, ('tool_id', 'model_id', 'auth_id', 'delegation_id'))}
    if row['outcome'] == 'succeeded':
        if 'blocked' in states.values():
            return None, 'CONFLICTING_EVIDENCE'
        if 'unknown' in states.values():
            return None, 'INSUFFICIENT_EVIDENCE'
        return None, 'NO_FAILURE' if codes == {'SUCCESS'} else 'CONFLICTING_EVIDENCE'
    if not codes or codes & {'SUCCESS', 'UNKNOWN'}:
        return None, 'INSUFFICIENT_EVIDENCE'
    if 'SELECTION_SKIPPED' in codes and (selected is not None or not matching):
        return None, 'CONFLICTING_EVIDENCE'
    causes = set()
    if 'STEP_SKIPPED' in codes:
        if selected is None:
            return None, 'INSUFFICIENT_EVIDENCE'
        causes.add('procedure')
    if 'CONTEXT_LENGTH_EXCEEDED' in codes:
        causes.add('model_limit')
    if codes & {'HTTP_401', 'HTTP_403', 'HTTP_429'}:
        causes.add('permission_api')
    if 'DEPENDENCY_UNAVAILABLE' in codes:
        causes.add('external_dependency')
    # Unknown/blocked resources cannot establish absence or non-selection as the root cause.
    ready = all(state == 'ready' for state in states.values())
    if 'SEARCH_COMPLETE' in codes and value['inventory_complete'] and ready:
        if not known and selected is None:
            causes.add('skill_gap')
        if matching and selected is None and 'SELECTION_SKIPPED' in codes:
            causes.add('skill_not_selected')
    if len(causes) > 1:
        return None, 'CONFLICTING_EVIDENCE'
    if not causes:
        return None, 'INSUFFICIENT_EVIDENCE'
    cause = next(iter(causes))
    if 'unknown' in states.values():
        return None, 'INSUFFICIENT_EVIDENCE'
    # Unexplained blocked resources may represent another cause: preserve HOLD.
    explained = {'model_limit': {'models'}, 'permission_api': {'auth', 'tools'},
                 'external_dependency': {'tools', 'delegation'}}.get(cause, set())
    if any(state == 'blocked' and kind not in explained for kind, state in states.items()):
        return None, 'CONFLICTING_EVIDENCE'
    return cause, 'RULE_SUPPORTED'


def audit(raw):
    value = validate(raw)
    counts = inventory(value)
    input_hash = digest(value)
    diagnoses, groups = [], {}
    for index, row in sorted(enumerate(value['observations']), key=lambda pair: pair[1]['id']):
        cause, reason = diagnose(value, row, set(counts['available_skill_ids']))
        refs = [{'input_hash': input_hash, 'pointer': f'/observations/{index}/logs/{i}',
                 'line': event['line'], 'code': event['code']}
                for i, event in enumerate(row['logs'])]
        diagnoses.append({'observation_id': row['id'], 'cause': cause,
                          'status': 'DIAGNOSED' if cause else ('NO_FAILURE' if reason == 'NO_FAILURE' else 'HOLD'),
                          'reason': reason, 'confidence': 'MEDIUM' if cause else 'LOW',
                          'evidence': refs})
        if cause:
            groups.setdefault((cause, row['capability']), []).append(row['id'])
    proposals = []
    for (cause, capability), ids in sorted(groups.items()):
        action, authoring, effect, acceptance = ACTIONS[cause]
        body = {'cause': cause, 'capability': capability, 'profile': value['profile'],
                'observation_ids': ids, 'baseline_sha': value['baseline_sha'],
                'change_allowlist': ['fixtures/skills/'] if cause in ('skill_gap', 'procedure')
                else ['fixtures/audit/'], 'public_evaluation_id': 'audit-v1-' + capability,
                'budget': {'api_calls': 0, 'api_cost_usd': 0, 'max_candidates': 1},
                'dependencies': {'design': 'merged-pr-11', 'memory': 'merged-pr-12'},
                'approval': 'NOT_REQUESTED', 'state': 'PROPOSED', 'action': action,
                'authoring_suggestion': authoring, 'confidence': 'MEDIUM',
                'expected_effect': effect, 'acceptance': acceptance,
                'input_hash': input_hash}
        proposals.append({'proposal_hash': digest(body), **body})
    return {'schema_version': 1, 'classification': 'PUBLIC', 'source_kind': value['source_kind'],
            'run_id': 'audit-' + input_hash[:12], 'fixture_id': value['fixture_id'],
            'observed_at': value['observed_at'], 'issue_url': value['issue_url'],
            'upstream_sha': value['upstream_sha'], 'baseline_sha': value['baseline_sha'],
            'input_hash': input_hash, 'profile': value['profile'], 'inventory_complete': value['inventory_complete'],
            'inventory': counts, 'diagnoses': diagnoses, 'proposals': proposals,
            'limitations': ['synthetic fixture only', 'rule confidence is not calibrated causal probability',
                            'historical 123/124 cause and production inventory not verified',
                            'proposals do not authorize execution or installation']}
