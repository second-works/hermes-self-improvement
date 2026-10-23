"""PUBLIC synthetic API fixtures; no real network/model/service calls."""
import copy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from github_work_guide.collector import Collector, GhReadOnly, Limits, PREFIX, connection_query, rest_request
from github_work_guide.core import (Invalid, REPO, build_plan, diff, digest, gate, load_run,
    markdown, read_json, recheck, save_run, seal, source_url, strict_json, validate, validate_plan)

SHA = 'a' * 40


def detail(n, pr=False, state='open'):
    value = {'number': n, 'state': state, 'title': f'Synthetic {n}',
             'body': '# Goal\n合成課題\n# Dependencies\nnone', 'html_url': source_url('pr' if pr else 'issue', n),
             'comments': 0, 'updated_at': '2026-10-23T00:00:00Z'}
    if pr:
        value.update(merged=False, head={'sha': SHA})
    return value


def item(n, pr=False, state='open'):
    d = detail(n, pr, state)
    raw = {'detail': d, 'comments': []}
    if pr:
        raw.update(checks=[{'id': i, 'name': name, 'head_sha': SHA, 'status': 'completed', 'conclusion': 'success'}
                           for i, name in enumerate(('ci', 'Security Preflight', 'Analyze (python)'), 1)],
                   statuses=[], reviews=[{'id': 1, 'state': 'COMMENTED', 'commit_id': SHA,
                                          'user': {'login': 'chatgpt-codex-connector[bot]'}}],
                   threads=[], closing=[], review_comments=[])
    return {'kind': 'pr' if pr else 'issue', 'number': n, 'state': state.upper(),
            'title': d['title'], 'body': d['body'], 'url': d['html_url'], 'raw': raw, 'hash': digest(raw)}


def snapshot(*values):
    return seal({f'{x["kind"]}:{x["number"]}': x for x in values},
                {'status': 'COMPLETE', 'errors': [], 'calls': 1, 'limits': {'pages': 10, 'items': 5000, 'calls': 500, 'seconds': 180},
                 'connections': [{'route': PREFIX + '/issues', 'complete': True}]})


def change(snapshot_value, target, fn):
    value = copy.deepcopy(snapshot_value)
    it = value['items'][target]
    fn(it)
    it['hash'] = digest(it['raw'])
    return seal(value['items'], value['coverage'])


def body(it, text):
    it['body'] = text
    it['raw']['detail']['body'] = text
    it['hash'] = digest(it['raw'])


class Fake:
    def __init__(self):
        self.items = [detail(7), detail(25, True)]
        self.routes = []
        self.fail_at = None
        self.full = False
        self.partial_checks = False
        self.graph_error = False
        self.changed = False
        self.inventories = 0

    def get(self, path, page, timeout):
        rest_request(path, page)
        self.routes.append(('GET', path, page))
        if self.fail_at == len(self.routes):
            raise Invalid('synthetic permission/rate/network failure')
        if path == PREFIX:
            return {'full_name': REPO, 'private': False, 'visibility': 'public'}
        if path == PREFIX + '/issues':
            self.inventories += 1
            if self.full:
                return [detail(x) for x in range((page - 1) * 100 + 1, page * 100 + 1)]
            rows = copy.deepcopy(self.items)
            rows[1]['pull_request'] = {}
            if self.changed and self.inventories > 1:
                rows[0]['updated_at'] = '2026-10-23T01:00:00Z'
            return rows
        if path.endswith('/check-runs'):
            return {'total_count': 4 if self.partial_checks else 3, 'check_runs': item(25, True)['raw']['checks']}
        if path.endswith('/reviews'):
            return item(25, True)['raw']['reviews']
        if path.endswith(('/comments', '/statuses')):
            return []
        return copy.deepcopy(self.items[1 if '/pulls/' in path else 0])

    def connection(self, kind, n, cursor, timeout):
        self.routes.append(('QUERY', kind, n))
        if self.graph_error:
            return {'data': {}, 'errors': [{'message': 'synthetic'}]}
        name = 'reviewThreads' if kind == 'threads' else 'closingIssuesReferences'
        return {'data': {'repository': {'pullRequest': {name: {'nodes': [], 'pageInfo': {'hasNextPage': False, 'endCursor': None}}}}}}


class SnapshotTests(unittest.TestCase):
    def test_checked_in_synthetic_fixture(self):
        value = validate(read_json(ROOT / 'fixtures/github_work_guide/synthetic.json'))
        plan = build_plan(value, ['issue:9'])
        self.assertLess(plan['order'].index('issue:8'), plan['order'].index('issue:9'))
        self.assertTrue(plan['candidates']['issue:9']['hold_reasons'])

    def test_strict_json(self):
        for text in ('{"a":1,"a":2}', '[NaN]', '[Infinity]', '{', 'null'):
            if text == 'null':
                with self.assertRaises(Invalid):
                    validate(strict_json(text))
            else:
                with self.assertRaises(Invalid):
                    strict_json(text)

    def test_hash_identity_schema_and_repository(self):
        original = snapshot(item(7))
        for mutation in (lambda s: s.update(repo='other/repo'), lambda s: s.update(version=2),
                         lambda s: s['items']['issue:7'].update(body='forged'),
                         lambda s: s['items']['issue:7'].update(url='https://evil.invalid'),
                         lambda s: s['items']['issue:7'].update(number=True)):
            value = copy.deepcopy(original)
            mutation(value)
            with self.assertRaises(Invalid):
                validate(value)
        validate(original)

    def test_first_added_unchanged_and_unavailable(self):
        a = snapshot(item(7))
        self.assertEqual(diff(a)[0]['status'], 'FIRST')
        self.assertEqual(diff(a, a)[0]['status'], 'UNCHANGED')
        self.assertEqual(diff(snapshot(item(7), item(8)), a)[1]['status'], 'ADDED')
        self.assertEqual(diff(snapshot(), a)[0]['status'], 'UNAVAILABLE')

    def test_malformed_source_cannot_claim_merged_or_empty_body(self):
        original = snapshot(item(25, True))
        for field, value in (('merged', 'false'), ('body', False), ('number', True), ('comments', True)):
            malformed = change(original, 'pr:25', lambda i: i['raw']['detail'].update({field: value}))
            with self.assertRaises(Invalid):
                validate(malformed)

    def test_state_head_comments_checks_reviews_changes(self):
        base = snapshot(item(25, True))
        mutations = [lambda i: i['raw']['detail']['head'].update(sha='b' * 40),
                     lambda i: i['raw']['comments'].append({'body': 'new'}),
                     lambda i: i['raw']['checks'][0].update(conclusion='failure'),
                     lambda i: i['raw']['reviews'].clear()]
        for mutation in mutations:
            fresh = change(base, 'pr:25', mutation)
            self.assertEqual(diff(fresh, base)[0]['status'], 'CHANGED')
            self.assertEqual(recheck(base, build_plan(base), 'pr:25', fresh)['status'], 'STALE')
        for old, new in (('open', 'closed'), ('closed', 'open')):
            self.assertIn('state', diff(snapshot(item(7, state=new)), snapshot(item(7, state=old)))[0]['fields'])
        merged = change(base, 'pr:25', lambda i: (i.update(state='MERGED'), i['raw']['detail'].update(merged=True, state='closed')))
        self.assertIn('state', diff(merged, base)[0]['fields'])

    def test_incomplete_never_becomes_zero_success(self):
        value = snapshot()
        value['coverage'].update(status='INCOMPLETE', errors=['failure'])
        value = seal(value['items'], value['coverage'])
        with self.assertRaises(Invalid):
            build_plan(value)
        base = snapshot(item(7))
        self.assertEqual(recheck(base, build_plan(base), 'issue:7', value)['status'], 'BLOCKED')


class PlanTests(unittest.TestCase):
    def test_unsupported_completion_regression(self):
        snap = snapshot(item(7))
        plan = build_plan(snap)
        plan['candidates']['issue:7']['summary'] = '本番への自動適用と毎日の自動運転は完了している'
        with self.assertRaises(Invalid):
            validate_plan(snap, plan)

    def test_dependency_skipping_regression(self):
        dependency, dependent = item(8), item(9)
        body(dependent, '# Goal\n合成\n# Dependencies\n- depends-on: #8')
        snap = snapshot(dependency, dependent)
        plan = build_plan(snap, ['issue:9'])
        self.assertEqual(plan['order'], ['issue:8', 'issue:9'])
        self.assertTrue(plan['candidates']['issue:9']['hold_reasons'])
        altered = copy.deepcopy(plan)
        altered['order'] = ['issue:9', 'issue:8']
        with self.assertRaises(Invalid):
            validate_plan(snap, altered)
        self.assertEqual(recheck(snap, plan, 'issue:9', snap)['status'], 'BLOCKED')

    def test_merged_is_not_issue_completion_or_production(self):
        issue, pr = item(7), item(25, True)
        pr['state'] = 'MERGED'
        pr['raw']['detail'].update(merged=True, state='closed')
        pr['raw']['closing'] = [{'number': 7, 'repository': {'nameWithOwner': REPO}}]
        pr['hash'] = digest(pr['raw'])
        plan = build_plan(snapshot(issue, pr))
        self.assertEqual(plan['candidates']['issue:7']['kind'], 'completion')
        self.assertEqual(plan['candidates']['pr:25']['kind'], 'none')
        self.assertNotIn('完了している', json.dumps(plan, ensure_ascii=False))

    def test_closed_no_reimplementation(self):
        plan = build_plan(snapshot(item(7, state='closed')))
        self.assertEqual(plan['candidates']['issue:7']['kind'], 'none')

    def test_wrong_kind_unknown_evidence_forged_quote(self):
        snap = snapshot(item(7))
        for mutate in (lambda c: c.update(kind='none'), lambda c: c['evidence'][0].update(id='unknown'),
                       lambda c: c['evidence'][0].update(quote='forged'), lambda c: c.update(next_step='skip dependency')):
            plan = build_plan(snap)
            mutate(plan['candidates']['issue:7'])
            with self.assertRaises(Invalid):
                validate_plan(snap, plan)

    def test_unknown_cyclic_dependencies_and_goal_conflict(self):
        a, b = item(7), item(8)
        body(a, '# Goal\nx\n# Dependencies\n- depends-on: #8')
        body(b, '# Goal\nx\n# Dependencies\n- depends-on: #7')
        plan = build_plan(snapshot(a, b))
        self.assertTrue(all('依存循環' in c['hold_reasons'] for c in plan['candidates'].values()))
        for text in ('# Goal\nx\n# Dependencies\n先に#9を完了', '# Goal\nx\n# Goal\ny\n# Dependencies\nnone',
                     '# Goal\nx\n# Dependencies\n- depends-on: #99'):
            a = item(7)
            body(a, text)
            self.assertTrue(build_plan(snapshot(a))['candidates']['issue:7']['hold_reasons'])
        a = item(7)
        a['raw']['comments'] = [{'body': 'Goalを変更する'}]
        a['hash'] = digest(a['raw'])
        self.assertTrue(build_plan(snapshot(a))['candidates']['issue:7']['hold_reasons'])

    def test_long_dependency_chain_within_collection_limit(self):
        values = [item(n) for n in range(1, 1101)]
        for n, value in enumerate(values[:-1], 1):
            body(value, f'# Goal\nx\n# Dependencies\n- depends-on: #{n + 1}')
        plan = build_plan(snapshot(*values), ['issue:1'])
        self.assertEqual(plan['order'][0], 'issue:1100')
        self.assertEqual(plan['order'][-1], 'issue:1')

    def test_no_hidden_number_specific_rules(self):
        plan = build_plan(snapshot(item(567), item(777)))
        self.assertEqual(plan['candidates']['issue:567']['kind'], plan['candidates']['issue:777']['kind'])

    def test_checks_and_review_strict_head(self):
        pr = item(25, True)
        self.assertEqual(gate(pr), [])
        mutations = [lambda r: r['checks'].pop(), lambda r: r['checks'][0].update(head_sha='b' * 40),
                     lambda r: r['checks'][0].update(conclusion='skipped'), lambda r: r['reviews'][0].update(commit_id='b' * 40),
                     lambda r: r['threads'].append({'isResolved': False}),
                     lambda r: r['reviews'].append({'state': 'CHANGES_REQUESTED'})]
        for mutate in mutations:
            value = copy.deepcopy(pr)
            mutate(value['raw'])
            self.assertTrue(gate(value))

    def test_success_cannot_hide_failed_status_or_other_provider(self):
        pr = item(25, True)
        pr['raw']['statuses'] = [{'id': 100, 'context': 'ci', 'state': 'failure'}]
        self.assertTrue(gate(pr))
        pr['raw']['statuses'] = []
        pr['raw']['checks'][0].update(app={'id': 1}, conclusion='failure')
        pr['raw']['checks'].append({'id': 900, 'app': {'id': 2}, 'name': 'ci', 'head_sha': SHA,
                                   'status': 'completed', 'conclusion': 'success'})
        self.assertTrue(gate(pr))

    def test_latest_failure_not_old_success(self):
        pr = item(25, True)
        pr['raw']['checks'].append({'id': 900, 'name': 'ci', 'head_sha': SHA, 'status': 'completed', 'conclusion': 'failure'})
        self.assertTrue(gate(pr))

    def test_unchanged_confirmed_missing_blocked_and_dependency_stale(self):
        snap = snapshot(item(7), item(8))
        plan = build_plan(snap)
        self.assertEqual(recheck(snap, plan, 'issue:7', snap)['status'], 'CONFIRMED')
        self.assertEqual(recheck(snap, plan, 'issue:7', snapshot(item(8)))['status'], 'BLOCKED')
        fresh = snapshot(item(7), item(8, state='closed'))
        self.assertEqual(recheck(snap, plan, 'issue:7', fresh)['status'], 'STALE')

    def test_untrusted_commands_are_data(self):
        a = item(7)
        body(a, '# Goal\n<script>x</script> [click](https://evil.invalid) `rm -rf`\n# Dependencies\nnone')
        snap = snapshot(a)
        plan = build_plan(snap)
        report = markdown(snap, diff(snap), plan)
        self.assertNotIn('<script>', report)
        self.assertNotIn('[click]', report)
        self.assertEqual(plan['candidates']['issue:7']['next_step'], 'GoalとScopeを人が照合して計画を整理する。')


class CollectorTests(unittest.TestCase):
    def test_collect_all_connections_and_no_writes(self):
        fake = Fake()
        snap = Collector(fake).collect()
        self.assertEqual(snap['coverage']['status'], 'COMPLETE')
        self.assertEqual(len(snap['items']), 2)
        self.assertTrue(all(x['complete'] for x in snap['coverage']['connections']))
        self.assertTrue(all(x[0] in ('GET', 'QUERY') for x in fake.routes))

    def test_faults_never_complete(self):
        for field, value in (('fail_at', 4), ('partial_checks', True), ('graph_error', True), ('changed', True)):
            fake = Fake()
            setattr(fake, field, value)
            snap = Collector(fake).collect()
            self.assertEqual(snap['coverage']['status'], 'INCOMPLETE', field)

    def test_empty_list_is_valid(self):
        fake = Fake()
        original = fake.get
        fake.get = lambda path, page, timeout: [] if path == PREFIX + '/issues' else original(path, page, timeout)
        snap = Collector(fake).collect()
        self.assertEqual(snap['coverage']['status'], 'COMPLETE')
        self.assertEqual(snap['items'], {})

    def test_limits_and_pagination(self):
        fake = Fake()
        fake.full = True
        self.assertEqual(Collector(fake, Limits(pages=1)).collect()['coverage']['status'], 'INCOMPLETE')
        self.assertEqual(Collector(Fake(), Limits(items=1)).collect()['coverage']['status'], 'INCOMPLETE')
        self.assertEqual(Collector(Fake(), Limits(calls=2)).collect()['coverage']['status'], 'INCOMPLETE')
        for kwargs in ({'pages': 11}, {'seconds': 181}, {'calls': True}, {'items': 0}):
            with self.assertRaises(Invalid):
                Limits(**kwargs)

    def test_multiple_rest_pages_and_graphql_pages(self):
        collector = Collector(Fake())
        rows = [{'number': n} for n in range(100)]
        collector.transport.get = lambda p, page, t: rows if page == 1 else [{'number': 101}]
        self.assertEqual(len(collector.pages(PREFIX + '/issues')), 101)
        calls = []
        def pages(kind, n, cursor, timeout):
            calls.append(cursor)
            return {'data': {'repository': {'pullRequest': {'reviewThreads': {'nodes': [{'id': str(cursor), 'isResolved': True}],
                'pageInfo': {'hasNextPage': cursor is None, 'endCursor': 'next'}}}}}}
        collector.transport.connection = pages
        self.assertEqual(len(collector.connection('threads', 25)), 2)
        self.assertEqual(calls, [None, 'next'])

    def test_time_limit_and_repeated_cursor(self):
        collector = Collector(Fake())
        collector.started -= 181
        self.assertEqual(collector.collect()['coverage']['status'], 'INCOMPLETE')
        collector = Collector(Fake())
        collector.transport.connection = lambda *args: {'data': {'repository': {'pullRequest': {'reviewThreads': {
            'nodes': [], 'pageInfo': {'hasNextPage': True, 'endCursor': 'same'}}}}}}
        with self.assertRaises(Invalid):
            collector.connection('threads', 25)

    def test_transport_rejects_write_routes_other_repo_and_query(self):
        for path in ('https://evil.invalid', PREFIX + '/issues/1/lock', 'repos/other/repo/issues', PREFIX + '/issues?state=all', PREFIX + '/../../x'):
            with self.assertRaises(Invalid):
                rest_request(path, 1)
        for kind in ('mutation', 'execute', 'anything'):
            with self.assertRaises(Invalid):
                connection_query(kind)
        with patch('subprocess.run') as run:
            with self.assertRaises(Invalid):
                GhReadOnly().get(PREFIX + '/issues/1/lock', None, 1)
            run.assert_not_called()
        self.assertTrue(connection_query('threads').startswith('query('))
        self.assertNotIn('mutation', connection_query('closing'))

    def test_public_only_duplicate_and_malformed_results(self):
        for variant in ('private', 'duplicate', 'schema'):
            fake = Fake()
            original = fake.get
            def malformed(path, page, timeout):
                response = original(path, page, timeout)
                if variant == 'private' and path == PREFIX:
                    response['private'] = True
                if variant == 'duplicate' and path == PREFIX + '/issues':
                    response += [response[0]]
                if variant == 'schema' and path.endswith('/check-runs'):
                    response['check_runs'][0]['status'] = 'unknown'
                return response
            fake.get = malformed
            self.assertEqual(Collector(fake).collect()['coverage']['status'], 'INCOMPLETE')

    def test_transport_actual_arguments_only_get_or_fixed_query(self):
        with patch('subprocess.run', return_value=subprocess.CompletedProcess([], 0, b'{}', b'')) as run:
            transport = GhReadOnly()
            transport.get(PREFIX, None, 1)
            transport.connection('threads', 25, None, 1)
            transport.connection('closing', 25, 'cursor', 1)
            args = [call.args[0] for call in run.call_args_list]
            self.assertEqual(args[0], ['gh', 'api', '--hostname', 'github.com', '--method', 'GET', PREFIX])
            self.assertTrue(all('query=query(' in a[6] for a in args[1:]))
            self.assertTrue(all(call.kwargs.get('shell', False) is False for call in run.call_args_list))

    def test_transport_errors_omit_secret_diagnostics(self):
        with patch('subprocess.run', return_value=subprocess.CompletedProcess([], 1, b'', b'synthetic-secret')):
            with self.assertRaisesRegex(Invalid, 'details omitted'):
                GhReadOnly().get(PREFIX, None, 1)
        with patch('subprocess.run', side_effect=subprocess.TimeoutExpired('gh', 1)):
            self.assertEqual(Collector().collect()['coverage']['status'], 'INCOMPLETE')


class PersistenceTests(unittest.TestCase):
    def test_roundtrip_new_directory_and_manifest_tampering(self):
        snap = snapshot(item(7))
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp).resolve() / 'runs' / 'one'
            save_run(out, {'snapshot.json': snap})
            self.assertEqual(load_run(out), snap)
            with self.assertRaises(FileExistsError):
                save_run(out, {'snapshot.json': snap})
            (out / 'snapshot.json').write_text('{}')
            with self.assertRaises(Invalid):
                load_run(out)

    def test_partial_and_symlink(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            partial = root / 'runs' / 'partial'
            partial.mkdir(parents=True)
            with self.assertRaises(Invalid):
                load_run(partial)
            outside = root / 'outside'
            outside.mkdir()
            (root / 'runs-link').symlink_to(outside, target_is_directory=True)
            with self.assertRaises(Invalid):
                save_run(root / 'runs-link' / 'x', {})
            with self.assertRaises(Invalid):
                save_run(root / 'not-runs' / 'x', {})

    def test_write_interruption_and_retry_preserve_partial(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp).resolve() / 'runs' / 'broken'
            real_open = Path.open
            def broken(path, *args, **kwargs):
                if path.name == 'manifest.json':
                    raise OSError('synthetic interruption')
                return real_open(path, *args, **kwargs)
            with patch.object(Path, 'open', broken):
                with self.assertRaises(OSError):
                    save_run(out, {'snapshot.json': snapshot(item(7))})
            with self.assertRaises(Invalid):
                load_run(out)
            with self.assertRaises(FileExistsError):
                save_run(out, {'snapshot.json': snapshot(item(7))})

    def test_separate_process_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            first, second = Path(tmp).resolve() / 'runs' / 'first', Path(tmp).resolve() / 'runs' / 'second'
            snap = snapshot(item(7))
            save_run(first, {'snapshot.json': snap, 'plan.json': build_plan(snap)})
            proc = subprocess.run([sys.executable, '-I', '-B', str(ROOT / 'scripts/report_github_work_guide.py'),
                'report', '--run', str(first), '--out', str(second)], capture_output=True)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertEqual(load_run(second), snap)
            self.assertEqual(read_json(second / 'plan.json'), build_plan(snap))


if __name__ == '__main__':
    unittest.main()
