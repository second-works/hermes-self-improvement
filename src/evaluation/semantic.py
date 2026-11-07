"""Finite semantic trials and a monotone per-observation inference budget."""
from pathlib import Path
import re
from adoption.core import save
from .core import canonical, digest, judge, load_json, regular, require

ROLES = ('baseline', 'candidate', 'degraded')
TRIALS = tuple({'ordinal': i*3+j, 'role': ROLES[(i+j)%3], 'trial': i}
               for i in range(3) for j in range(3))


class Budget:
    """The controller holds its shared lock; exclusive durable intents also prevent replay."""
    def __init__(self, area, manifest):
        self.area, self.manifest = Path(area), manifest
        self.hash = digest(canonical(manifest))
        self.approval_hash = None

    def begin(self, approval_hash):
        require(type(approval_hash) is str and re.fullmatch('[a-f0-9]{64}',approval_hash),'SEMANTIC_APPROVAL')
        path = self.area / 'started.json'
        require(not path.exists(), 'SEMANTIC_ALREADY_STARTED')
        save(path, {'manifest_hash': self.hash, 'event_id': self.manifest['event_id'],
                    'generation_attempts': 1, 'approval_hash': approval_hash})
        self.approval_hash = approval_hash

    def intents(self):
        result = []
        for path in sorted(self.area.glob('intent-*.json')):
            index = len(result)
            require(index < 9 and path.name == f'intent-{index:02d}.json', 'SEMANTIC_BUDGET_GAP')
            value = load_json(regular(path, self.area, 4096))
            require(type(value) is dict and set(value)=={'manifest_hash','event_id','ordinal','role','trial',
                                                       'prompt_hash','container'},'SEMANTIC_INTENT_SCHEMA')
            trial = TRIALS[index]
            require(value['manifest_hash'] == self.hash and value['event_id'] == self.manifest['event_id']
                    and all(type(value.get(k)) is type(v) and value[k] == v for k,v in trial.items())
                    and value['prompt_hash'] == self.manifest['trials'][index]['prompt_hash']
                    and type(value['container']) is str and re.fullmatch(r'hermes-eval-[a-f0-9]{32}',value['container'])
                    and value['container'] not in [x['container'] for x in result], 'SEMANTIC_INTENT_CHANGED')
            result.append(value)
        require(1 + len(result) <= 10, 'SEMANTIC_BUDGET_LIMIT')
        return result

    def reserve(self, ordinal, container):
        require(type(ordinal) is int and 0 <= ordinal < 9, 'SEMANTIC_TRIAL')
        require(type(container) is str and re.fullmatch(r'hermes-eval-[a-f0-9]{32}',container),'SEMANTIC_CONTAINER')
        require(self.approval_hash is not None and load_json(regular(self.area/'started.json', self.area)) == {
            'manifest_hash':self.hash,'event_id':self.manifest['event_id'],'generation_attempts':1,
            'approval_hash':self.approval_hash},
                'SEMANTIC_START_CHANGED')
        intents=self.intents()
        require(len(intents) == ordinal, 'SEMANTIC_REPLAY_OR_ORDER')
        require(container not in [x['container'] for x in intents],'SEMANTIC_CONTAINER_REUSE')
        trial = self.manifest['trials'][ordinal]
        require(all(type(trial.get(k)) is type(v) and trial[k] == v for k,v in TRIALS[ordinal].items()), 'SEMANTIC_TRIAL')
        value = {**TRIALS[ordinal], 'manifest_hash':self.hash, 'event_id':self.manifest['event_id'],
                 'prompt_hash':trial['prompt_hash'], 'container':container}
        save(self.area/f'intent-{ordinal:02d}.json', value)
        return value


def prompt(skill, stdin):
    text = ('Perform this registered PUBLIC Skill for the supplied input. Available tools: none. '
            'Do not call tools or request external resources. Output only the Skill output as strict JSON; '
            'do not include markdown or explanations. If it cannot be performed, output '
            '{"error":"UNSUPPORTED"}.\n<skill>\n' + skill + '\n</skill>\n<input>\n' + stdin + '\n</input>')
    require(len(text.encode()) <= 8192, 'SEMANTIC_PROMPT_LIMIT')
    return text


def observation(text, expected, seconds):
    try:
        value = load_json(text.encode())
        valid = type(value) is dict and set(value) == {'counts'} and type(value['counts']) is dict
        if valid:
            for category, counts in value['counts'].items():
                valid = valid and type(counts) is dict and set(counts) == {'ok','failed'}
                if valid:
                    valid = all(type(n) is int and n >= 0 for n in counts.values())
                if not valid: break
        answer = canonical(value)
    except Exception:
        valid, answer = False, text.encode()
    return {'correct':valid and answer == canonical(expected), 'failed':not valid,
            'answer_hash':digest(answer), 'seconds':seconds}


def verdict(records):
    import statistics
    require(set(records) == set(ROLES) and all(len(records[r]) == 3 for r in ROLES), 'SEMANTIC_INCOMPLETE')
    metrics = {role:{'correct':[x['correct'] for x in records[role]],
                     'failures':sum(x['failed'] for x in records[role]),
                     'latency':statistics.median(x['seconds'] for x in records[role]), 'cost_usd':0}
               for role in ROLES}
    unstable = any(len({(x['correct'],x['failed'],x['answer_hash']) for x in records[r]}) != 1 for r in ROLES)
    decision = judge(metrics['baseline'],metrics['candidate'],safety=True,contaminated=unstable,
                     public_count=0,hidden_count=3)
    control_valid = not any(metrics['degraded']['correct'])
    state = 'REJECTED' if decision['status']=='FAIL' else 'HOLD'
    if decision['status']=='PASS' and all(metrics['candidate']['correct']) and control_valid:
        state = 'AWAITING_HUMAN_APPROVAL'
    elif decision['status']=='PASS':
        decision={'status':'HOLD','reasons':['SEMANTIC_CONTROL_OR_REQUIRED_TRIAL_INVALID']}
    return {'state':state,'decision':decision,'control_valid':control_valid,
            'counts':{r:sum(metrics[r]['correct']) for r in ROLES}}
