"""Strict selection responses and deterministic, source-derived reports."""
import html
import os
from pathlib import Path
import re
import unicodedata

from .core import (ContractError, STATES, baseline, canonical, decode,
                   digest, evidence, fields, require)

LABELS = dict(zip(STATES, ('要確認', '承認待ち', '継続調査', '対応済み（ログ上）', '判断保留')))
PAIRS = {'needs_check': {'explicit_open'}, 'awaiting_approval': {'explicit_approval'},
         'investigating': {'explicit_investigation'}, 'resolved_in_log': {'linked_success'},
         'hold': {'insufficient_context', 'conflicting_evidence', 'unsupported_format'}}


def packets(snapshot):
    """Every task is a separate packet; no tools, free text fields, or gold labels."""
    return {'schema_version': 1, 'packets': [
        {'candidate_id': c['candidate_id'], 'session_id': c['session_id'],
         'task_id': c['task_id'],
         'records': [{'record_id': r.record_id, 'text': r.text, 'kind': r.kind,
                      'sequence': r.sequence} for r in c['records']]} for c in snapshot['candidates']]}


def validate_response(snapshot, raw):
    value = decode(raw)
    fields(value, 'schema_version decisions')
    require(type(value['schema_version']) is int and value['schema_version'] == 1, 'RESPONSE_VERSION')
    rows = value['decisions']
    require(type(rows) is list and len(rows) <= 64, 'RESPONSE_COUNT')
    allowed = {c['candidate_id']: {r.record_id for r in c['records']}
               for c in snapshot['candidates']}
    decisions = {}
    for row in rows:
        fields(row, 'candidate_id state reason evidence_ids')
        cid, state, reason, ids = (row[k] for k in ('candidate_id', 'state', 'reason', 'evidence_ids'))
        require(type(cid) is str and cid in allowed and cid not in decisions, 'RESPONSE_CANDIDATE')
        require(type(state) is str and state in STATES and type(reason) is str and
                reason in PAIRS[state], 'RESPONSE_STATE')
        require(type(ids) is list and 1 <= len(ids) <= 128 and
                all(type(i) is str and i in allowed[cid] for i in ids) and
                len(set(ids)) == len(ids), 'RESPONSE_EVIDENCE')
        decisions[cid] = row
    return decisions


def make_report(snapshot, raw_response=None):
    mode = 'rules' if raw_response is None else 'mock-selection'
    diagnostics, decisions = [], {}
    if raw_response is not None:
        try:
            decisions = validate_response(snapshot, raw_response)
        except ContractError as exc:
            diagnostics.append(str(exc))
    rows = []
    for candidate in snapshot['candidates']:
        refs = evidence(candidate)
        if raw_response is None:
            state, reason = baseline(candidate)
            ids = [r['record_id'] for r in refs]
        elif diagnostics:
            state, reason, ids = 'hold', 'invalid_response', [r['record_id'] for r in refs]
        elif candidate['candidate_id'] not in decisions:
            state, reason, ids = 'hold', 'missing_response', [r['record_id'] for r in refs]
        else:
            row = decisions[candidate['candidate_id']]
            state, reason, ids = row['state'], row['reason'], row['evidence_ids']
        # A model cannot erase a parser's evidence of incomplete input.
        if candidate['unsupported']:
            state, reason = 'hold', 'unsupported_format'
        rows.append({'candidate_id': candidate['candidate_id'],
                     'session_id': candidate['session_id'], 'task_id': candidate['task_id'],
                     'scenario_id': candidate['scenario_id'], 'state': state, 'reason': reason,
                     'evidence_ids': ids, 'references': refs})
    incomplete = sum(r['reason'] in ('invalid_response', 'missing_response', 'unsupported_format')
                     for r in rows)
    return {'schema_version': 1, 'classification': 'PUBLIC', 'source_kind': 'synthetic-fixture',
            'scope': 'Provided synthetic logs only; current GitHub/runtime state is unverified.',
            'source_root': 'fixtures/worklog_candidates',
            'mode': mode, 'status': 'PARTIAL' if incomplete or diagnostics else 'COMPLETE',
            'manifest_sha256': snapshot['manifest_sha256'], 'input_files': snapshot['files'],
            'input_bytes': snapshot['input_bytes'], 'model_calls': 0,
            'response_sha256': None if raw_response is None else digest(raw_response),
            'diagnostics': diagnostics,
            'coverage': {'candidates': len(rows), 'incomplete': incomplete,
                         'hold': sum(r['state'] == 'hold' for r in rows)},
            'candidates': rows}


def safe_text(value):
    # Strip terminal controls, bidi controls and other invisible format characters.
    value = ''.join(c if c in '\n\t' or not unicodedata.category(c).startswith('C')
                    else '\ufffd' for c in value)
    return re.sub(r'([\\`*_{}\[\]()#+.!|>~-])', r'\\\1', html.escape(value))


def markdown(report):
    lines = ['# 対応が必要と考えられる候補', '',
             '提供された合成ログ上の状態です。現在のGitHub・実行環境は未確認です。', '',
             '原文の相対パス基準: fixtures/worklog_candidates/', '',
             f"実行状態: {report['status']} / モデル通信: 0 / 入力hash: {report['manifest_sha256']}", '',
             f"候補: {report['coverage']['candidates']} / 不完全: {report['coverage']['incomplete']} / 判断保留: {report['coverage']['hold']}", '']
    for state in STATES:
        lines.extend(['## ' + LABELS[state], ''])
        for row in report['candidates']:
            if row['state'] != state:
                continue
            lines.extend(['### ' + row['candidate_id'], '',
                          '理由: ' + row['reason'], ''])
            for ref in row['references']:
                selected = '選択根拠' if ref['record_id'] in row['evidence_ids'] else '前後文脈'
                lines.extend([f"{selected}: {safe_text(ref['path'])} 行{ref['line_start']}–{ref['line_end']}", '',
                              f"ID: {ref['record_id']} / SHA256: {ref['file_sha256']}", ''])
                lines.extend('> ' + safe_text(line) for line in ref['text'].split('\n'))
                lines.append('')
    if 'evaluation' in report:
        score = report['evaluation']['splits']['all']
        lines.extend(['## 有限の合成評価', '',
                      f"状態一致: {score['correct_states']}/{score['cases']} / 対応候補の見落とし: {score['active_false_negative']} / 対応済みの誤検出: {score['resolved_false_positive']}", '',
                      '実モデル精度は未測定。意味的な根拠は人の確認が必要です。', ''])
    if report['diagnostics']:
        lines.extend(['診断: ' + ', '.join(report['diagnostics']), ''])
    return '\n'.join(lines)


def write_output(destination, report):
    """Create-only output with a pinned parent directory descriptor."""
    destination = Path(destination).absolute()
    require('\x00' not in str(destination) and destination.name not in ('', '.', '..') and
            '..' not in destination.parts, 'OUTPUT_PATH')
    fd = os.open('/', os.O_RDONLY | os.O_DIRECTORY)
    try:
        for part in destination.parent.parts[1:]:
            new = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = new
        os.mkdir(destination.name, mode=0o700, dir_fd=fd)
        out = os.open(destination.name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
        try:
            for name, data in [('report.json', canonical(report) + b'\n'),
                               ('report.md', markdown(report).encode('utf-8'))]:
                target = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                                 0o600, dir_fd=out)
                with os.fdopen(target, 'wb') as stream:
                    stream.write(data)
                    stream.flush()
                    os.fsync(stream.fileno())
        finally:
            os.close(out)
    finally:
        os.close(fd)
