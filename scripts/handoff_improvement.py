#!/usr/bin/env python3
"""Connect a #64 mock proposal to an independently evaluated fixture.

Use baseline-check after freezing the multiline suite, then use candidate to write the proposed bytes to stdout for a local fixture
commit, then evaluate with that commit SHA. Use prepare to register the fixture
target after PASS. The existing adopt_fixture.py commands accept --evaluation-run
to request, approve, execute and observe operations on this target.
"""
import argparse
import difflib
from pathlib import Path
import sys
import uuid

import evaluate_fixture as evaluator
from adoption.core import Controller, save, read, utc
from evaluation.core import (EvaluationError, canonical, digest, findings, load_json,
                             regular, require, write_new)
from run_mock_improvement import MAX_PACKET_BYTES, MAX_RESPONSE_BYTES, packet_refs, response_result


def baseline_check(work):
    manifest = evaluator.verify_manifest(work)
    require(manifest.get('suite') == 'multiline-shell-v1', 'EVALUATION_SUITE')
    public = evaluator.read(work, 'public.json')
    require(len(public) == 12 and len(public[10]['expected']) == 1, 'BASELINE_CASE')
    data = evaluator.git_bytes(manifest['baseline_sha'])
    require(digest(data) == manifest['baseline_artifact_hash'], 'BASELINE_CHANGED')
    program = work / 'baseline-check.py'
    write_new(program, data)
    program.chmod(0o444)
    result = evaluator.sandbox(work).run(program, canonical(public[10]['input']))
    require(result['exit'] == result['container_exit'] == 0
            and not any(result[key] for key in ('stderr', 'error', 'oom')), 'BASELINE_EXECUTION')
    answer, _ = findings(load_json(result['stdout']))
    require(answer == [], 'BASELINE_MISS_NOT_REPRODUCED')
    save(work / 'baseline-check.json', {'manifest_hash': digest(regular(work / 'manifest.json', evaluator.RUNS)),
                                       'result': 'MISS_REPRODUCED'})


def candidate(work, packet_file, proposal_file):
    packet = load_json(regular(packet_file, packet_file.absolute().parent, MAX_PACKET_BYTES))
    refs = packet_refs(packet)
    manifest = evaluator.verify_manifest(work)
    baseline = manifest['baseline_sha']
    require(manifest.get('suite') == 'multiline-shell-v1' and packet['baseline_sha'] == baseline,
            'EVALUATION_BASELINE')
    baseline_receipt = evaluator.read(work, 'baseline-check.json')
    require(baseline_receipt == {'manifest_hash': digest(regular(work / 'manifest.json', evaluator.RUNS)),
                                 'result': 'MISS_REPRODUCED'}, 'BASELINE_CHECK_REQUIRED')
    raw = regular(proposal_file, proposal_file.absolute().parent, 2 * MAX_RESPONSE_BYTES)
    proposal = load_json(raw)
    require(type(proposal) is dict, 'PROPOSAL_SCHEMA')
    normalized = canonical(proposal)
    require(raw in (normalized, normalized + b'\n'), 'PROPOSAL_ENCODING')
    metadata = {'event_id': packet['event_id'], 'packet_hash': digest(canonical(packet)),
                'classification': 'PUBLIC', 'target_skill': packet['target_skill'],
                'baseline_sha': baseline}
    require(all(proposal.get(key) == value for key, value in metadata.items()), 'PROPOSAL_BINDING')
    event_dir = evaluator.RUNS / 'mock-improvement' / packet['event_id']
    receipt = load_json(regular(event_dir / 'finished.json', evaluator.RUNS))
    require(receipt == {'event_id': metadata['event_id'], 'packet_hash': metadata['packet_hash'],
                        'status': 'COMPLETED', 'decision': 'PROPOSE',
                        'result_hash': digest(normalized)}, 'PROPOSAL_RECEIPT')
    response = response_result({key: value for key, value in proposal.items() if key not in metadata}, refs)
    require(response['decision'] == 'PROPOSE', 'PROPOSAL_REQUIRED')
    edit = response['edit']
    original = evaluator.git_bytes(baseline)
    before, after = edit['before'].encode(), edit['after'].encode()
    require(edit['path'] == evaluator.ARTIFACT and original.count(before) == 1, 'EDIT_BINDING')
    content = original.replace(before, after, 1)
    require(0 < len(content) <= 65536 and original != content, 'CANDIDATE_SIZE')
    return baseline, content, receipt['result_hash']


def evaluate(work, packet_file, proposal_file, sha):
    baseline, expected, proposal_hash = candidate(work, packet_file, proposal_file)
    require(evaluator.git_bytes(sha) == expected, 'CANDIDATE_CHANGED')
    require(evaluator.git_command('diff', '--name-only', '--no-renames', baseline, sha).splitlines()
            == [evaluator.ARTIFACT.encode()], 'DIFF_SCOPE')
    evaluator.git_command('merge-base', '--is-ancestor', baseline, sha)
    save(work / 'handoff.json', {'baseline_sha': baseline, 'candidate_sha': sha,
                                'proposal_hash': proposal_hash})
    handoff_hash = digest(regular(work / 'handoff.json', evaluator.RUNS))
    evaluator.evaluate(work, baseline, sha, handoff_hash=handoff_hash)


class HandoffAdoption(Controller):
    def __init__(self, area, work):
        super().__init__(evaluator.ROOT, area)
        self.work = work

    def source(self):
        checkpoint = evaluator.audit(self.work, emit=False)
        report = evaluator.read(self.work, 'report.json')
        handoff = regular(self.work / 'handoff.json', evaluator.RUNS)
        lock = evaluator.read(self.work, 'evaluation-lock.json')
        require(lock.get('handoff_hash') == digest(handoff), 'HANDOFF_CHANGED')
        binding = load_json(handoff)
        require(report['status'] == 'PASS' and report['control_verified'] is True
                and report['metrics']['baseline']['public_correct'] == 11
                and report['metrics']['candidate']['public_correct'] == 12
                and report['metrics']['candidate']['hidden_correct'] == 12
                and binding['baseline_sha'] == report['baseline_sha']
                and binding['candidate_sha'] == report['candidate_sha'], 'EVALUATION_NOT_PASS')
        versions = {label: evaluator.git_bytes(report[label + '_sha'])
                    for label in ('baseline', 'candidate')}
        path = evaluator.ARTIFACT
        patch = ''.join(difflib.unified_diff(versions['baseline'].decode().splitlines(True),
            versions['candidate'].decode().splitlines(True), fromfile='a/' + path, tofile='b/' + path))
        return {
            'classification': 'PUBLIC', 'issue': 65, 'run_id': self.work.name,
            'baseline_sha': report['baseline_sha'], 'candidate_sha': report['candidate_sha'],
            'evaluation_hash': checkpoint['report_hash'], 'proposal_hash': binding['proposal_hash'],
            'manifest_hash': report['manifest_hash'], 'artifact_path': path, 'allowlist': [path],
            'before_hash': digest(versions['baseline']), 'after_hash': digest(versions['candidate']),
            'diff_hash': digest(patch.encode()), 'merge_is_adoption': False,
        }, versions, patch

    def regression(self, program, operation):
        packet, _, _ = self.source()
        expected = packet['after_hash' if operation == 'ADOPT' else 'before_hash']
        require(digest(regular(program, self.area)) == expected, 'REGRESSION_ARTIFACT')
        work = self.area / ('check-' + uuid.uuid4().hex)
        work.mkdir(mode=0o700)
        pinned = evaluator.read(self.work, 'environment.json')
        box = evaluator.Sandbox(self.repo, work, pinned['image']['id'])
        require(box.environment() == pinned['environment']
                and box.image_info(box.image) == pinned['image'], 'ENVIRONMENT_CHANGED')
        selected = evaluator.read(self.work, 'public.json')
        if operation == 'ROLLBACK':
            selected = selected[:10]
        for case in selected:
            result = box.run(program, canonical(case['input']))
            require(result['exit'] == result['container_exit'] == 0 and
                    not any(result[key] for key in ('stderr', 'error', 'oom')), 'REGRESSION_EXECUTION')
            actual, _ = findings(load_json(result['stdout']))
            require(actual == sorted(map(tuple, case['expected'])), 'REGRESSION_OUTPUT')
        return True

    def memory_record(self, target):
        packet = self.packet()
        events = self.events(target)
        adopted = next((event for event in reversed(events) if event['state'] == 'ADOPTED'), None)
        restored = next((event for event in reversed(events) if event['state'] == 'ROLLED_BACK'), None)
        def artifact(label, field):
            return {'commit_sha': packet[label + '_sha'], 'artifact_sha256': packet[field]}
        report = evaluator.read(self.work, 'report.json')
        return {
            'schema_version': 1, 'run_id': self.work.name, 'recorded_at': utc().replace('+00:00', 'Z'),
            'classification': 'PUBLIC', 'iteration': 1,
            'baseline': artifact('baseline', 'before_hash'), 'candidate': artifact('candidate', 'after_hash'),
            'metrics': {'status': 'VERIFIED', 'evidence_sha256': packet['evaluation_hash'],
                        'values': [{'name': 'public_correct', 'value': report['metrics']['candidate']['public_correct'],
                                    'unit': 'count'}]},
            'approval': {'status': 'RECORDED' if adopted else 'PENDING',
                         'record_sha256': adopted['details']['approval_hash'] if adopted else None},
            'rollback': {'status': 'RECORDED' if restored else 'NOT_REQUESTED',
                         'record_sha256': restored['hash'] if restored else None},
        }


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--run', required=True)
    sub = parser.add_subparsers(dest='operation', required=True)
    for name in ('candidate', 'evaluate'):
        command = sub.add_parser(name)
        command.add_argument('--packet', type=Path, required=True)
        command.add_argument('--proposal', type=Path, required=True)
        if name == 'evaluate':
            command.add_argument('--candidate-sha', required=True)
    sub.add_parser('baseline-check')
    memory = sub.add_parser('memory-record')
    memory.add_argument('--area', type=Path, required=True)
    prepare = sub.add_parser('prepare')
    prepare.add_argument('--area', type=Path, required=True)
    args = parser.parse_args()
    work = evaluator.run_path(args.run)
    if args.operation == 'baseline-check':
        baseline_check(work)
        print('{"status":"MISS_REPRODUCED"}')
    elif args.operation == 'memory-record':
        controller = HandoffAdoption(args.area, work)
        with controller.guard():
            print(canonical(controller.memory_record('target')).decode())
    elif args.operation == 'candidate':
        sys.stdout.buffer.write(candidate(work, args.packet, args.proposal)[1])
    elif args.operation == 'evaluate':
        evaluate(work, args.packet, args.proposal, args.candidate_sha)
    else:
        controller = HandoffAdoption(args.area, work)
        packet = controller.initialize()
        target = controller.area / 'fixtures' / 'target'
        artifact = target / packet['artifact_path']
        artifact.parent.mkdir(parents=True)
        write_new(artifact, evaluator.git_bytes(packet['baseline_sha']))
        controller.register('public-mock-improvement', 'target', target)
        save(controller.area / 'improvement-log.json', controller.memory_record('target'))
        print(canonical({'state': controller.state('target'), 'candidate_sha': packet['candidate_sha']}).decode())


if __name__ == '__main__':
    try:
        main()
    except (EvaluationError, OSError, KeyError, ValueError, TypeError):
        print('{"status":"STOPPED","reason":"HANDOFF_REJECTED"}', file=sys.stderr)
        sys.exit(2)
