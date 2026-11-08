"""Batch transport contract and frozen-input equivalence; no network or model."""
import copy
import subprocess
import unittest
from unittest.mock import patch

from test_github_work_guide import Fake, detail, item
from github_work_guide.collector import Collector, GhReadOnly, Limits, PREFIX, closing_batch_query
from github_work_guide.core import Invalid, REPO, build_plan, work_view


def page(rows=(), next_page=False, cursor=None):
    return {'nodes': list(rows), 'pageInfo': {'hasNextPage': next_page, 'endCursor': cursor}}


def response(requests, pages=None):
    repo = {'nameWithOwner': REPO}
    for i, (n, cursor) in enumerate(requests):
        repo[f'p{i}'] = {'number': n, 'closingIssuesReferences':
                        pages(n, cursor) if pages else page([{'number': 7, 'repository': {'nameWithOwner': REPO}}])}
    return {'data': {'repository': repo}}


class Legacy(Fake):
    def __init__(self):
        super().__init__()
        self.items = [detail(7)] + [detail(n, True, 'open' if n == 10 else 'closed') for n in range(10, 21)]
        self.reads = []

    def get(self, path, p, timeout):
        self.reads.append((path, p))
        if path == PREFIX + '/issues':
            rows = copy.deepcopy(self.items)
            for row in rows[1:]:
                row['pull_request'] = {}
            return rows
        if path.rsplit('/', 1)[-1].isdigit():
            n = int(path.rsplit('/', 1)[-1])
            return copy.deepcopy(next(x for x in self.items if x['number'] == n))
        return super().get(path, p, timeout)

    def connection(self, kind, n, cursor, timeout):
        if kind == 'closing':
            return {'data': {'repository': {'pullRequest': {'closingIssuesReferences':
                    response([(n, cursor)])['data']['repository']['p0']['closingIssuesReferences']}}}}
        return super().connection(kind, n, cursor, timeout)


class Batched(Legacy):
    def __init__(self):
        super().__init__()
        self.batches = []
        self.modify = lambda r: r
        self.pages_fn = None

    def closing_batch(self, requests, timeout):
        closing_batch_query(requests)
        self.batches.append(copy.deepcopy(requests))
        return self.modify(response(requests, self.pages_fn))


class BatchTests(unittest.TestCase):
    def test_same_raw_hashes_decisions_and_logical_budget_fewer_http_requests(self):
        old, new = Collector(Legacy()).collect(), Collector(Batched()).collect()
        self.assertEqual(old['coverage']['status'], 'COMPLETE')
        self.assertEqual(new['coverage']['status'], 'COMPLETE')
        self.assertEqual(old['items'], new['items'])
        self.assertEqual(old['coverage']['calls'], new['coverage']['calls'])
        self.assertEqual(old['coverage']['returned_nodes'], new['coverage']['returned_nodes'])
        self.assertEqual(old['coverage']['http_requests'] - new['coverage']['http_requests'], 9)
        for key in old['items']:
            self.assertEqual(work_view(old['items'][key]['raw']), work_view(new['items'][key]['raw']))
        plans = [build_plan(s) for s in (old, new)]
        for p in plans:
            p.pop('snapshot_hash')
        self.assertEqual(*plans)

    def test_transport_fixed_query_variables_no_interpolation_or_shell(self):
        with patch('subprocess.run', return_value=subprocess.CompletedProcess([], 0, b'{}', b'')) as run:
            cursor = 'opaque-"cursor\\value'
            GhReadOnly().closing_batch([(10, None), (11, cursor)], 3)
            args = run.call_args.args[0]
            self.assertEqual(args[:5], ['gh', 'api', '--hostname', 'github.com', 'graphql'])
            query = args[6]
            self.assertTrue(query.startswith('query=query('))
            self.assertNotIn(cursor, query)
            self.assertNotIn('mutation', query)
            self.assertIn('p1:pullRequest(number:$n1)', query)
            self.assertIn('c1=' + cursor, args)
            self.assertEqual(run.call_args.kwargs['timeout'], 3)
            self.assertFalse(run.call_args.kwargs.get('shell', False))

    def test_transport_rejects_unbounded_or_invalid_requests_before_wire(self):
        invalid = [[], [(1, None)] * 2, [(n, None) for n in range(1, 12)],
                   [(True, None)], [(0, None)], [('1', None)], [(1, '')], [(1, 'x' * 1025)], [(1, 7)]]
        with patch('subprocess.run') as run:
            for requests in invalid:
                with self.subTest(requests=str(requests)[:60]), self.assertRaises(Invalid):
                    GhReadOnly().closing_batch(requests, 1)
            run.assert_not_called()

    def test_per_pr_cursors_and_completed_alias_removed(self):
        fake = Batched()
        fake.pages_fn = lambda n, c: page([{'number': n, 'repository': {'nameWithOwner': REPO}}],
                                          n == 10 and c is None, 'next-10')
        c = Collector(fake)
        rows = c.closings([10, 11])
        self.assertEqual(fake.batches, [[(10, None), (11, None)], [(10, 'next-10')]])
        self.assertEqual(len(rows[10]), 2)
        self.assertEqual(c.calls, 3)
        self.assertEqual(c.http_requests, 2)
        self.assertEqual([x['pages'] for x in c.connections], [2, 1])
        self.assertTrue(all(x['complete'] for x in c.connections))

    def test_batch_boundaries_and_empty_listing(self):
        for size, expected in ((0, []), (1, [1]), (10, [10]), (11, [10, 1])):
            f = Batched()
            c = Collector(f)
            c.closings(list(range(1, size + 1)))
            self.assertEqual([len(x) for x in f.batches], expected)
            self.assertEqual(c.calls, size)
        f = Batched()
        f.items = []
        self.assertEqual(Collector(f).collect()['coverage']['status'], 'COMPLETE')
        self.assertEqual(f.batches, [])

    def test_logical_budget_reserved_before_whole_batch_no_request_on_overflow(self):
        f = Batched()
        c = Collector(f, Limits(calls=9))
        with self.assertRaises(Invalid):
            c.closings(list(range(1, 11)))
        self.assertEqual(f.batches, [])
        self.assertEqual(c.calls, 0)
        c = Collector(f, Limits(calls=10))
        c.closings(list(range(1, 11)))
        self.assertEqual(c.calls, 10)
        with self.assertRaises(Invalid):
            c.closings([11])
        self.assertEqual(len(f.batches), 1)

    def test_time_budget_before_and_after_wire(self):
        f = Batched()
        c = Collector(f)
        c.started -= 181
        with self.assertRaises(Invalid):
            c.closings([10])
        self.assertEqual(f.batches, [])
        c = Collector(f)
        def expire(r):
            c.started -= 181
            return r
        f.modify = expire
        with self.assertRaises(Invalid):
            c.closings([10])
        self.assertFalse(c.connections[0]['complete'])

    def test_node_limit_and_oversized_page(self):
        f = Batched()
        f.pages_fn = lambda n, c: page([{'number': 7}] * 101)
        with self.assertRaises(Invalid):
            Collector(f).closings([10])
        f.pages_fn = lambda n, c: page([{'number': 7}] * 2)
        with self.assertRaises(Invalid):
            Collector(f, Limits(items=1)).closings([10])

    def test_page_limit_and_repeated_or_invalid_cursor(self):
        for cursor in (None, '', 'x' * 1025, 7, 'same'):
            f = Batched()
            f.pages_fn = lambda n, c: page([], True, cursor)
            with self.subTest(cursor=str(cursor)[:10]), self.assertRaises(Invalid):
                Collector(f).closings([10])
            self.assertLessEqual(len(f.batches), 2)
        f = Batched()
        f.pages_fn = lambda n, c: page([], True, 'next')
        with self.assertRaises(Invalid):
            Collector(f, Limits(pages=1)).closings([10])
        self.assertEqual(len(f.batches), 1)

    def test_partial_errors_nulls_missing_wrong_alias_or_identity_never_complete(self):
        def repo(r):
            return r['data']['repository']
        changes = [lambda r: r.update(errors=[{'message': 'synthetic-secret'}]),
                   lambda r: r.update(data=None),
                   lambda r: repo(r).update(nameWithOwner='other/repo'),
                   lambda r: repo(r).pop('p0'),
                   lambda r: repo(r).update(p0=None),
                   lambda r: repo(r)['p0'].update(number=11),
                   lambda r: repo(r)['p0'].update(number=True),
                   lambda r: repo(r)['p0'].update(closingIssuesReferences=None),
                   lambda r: repo(r)['p0']['closingIssuesReferences'].update(nodes=None),
                   lambda r: repo(r)['p0']['closingIssuesReferences']['pageInfo'].update(hasNextPage=1)]
        for change in changes:
            f = Batched()
            def modify(r):
                change(r)
                return r
            f.modify = modify
            s = Collector(f).collect()
            self.assertEqual(s['coverage']['status'], 'INCOMPLETE')
            self.assertNotIn('synthetic-secret', str(s))
            self.assertEqual(len(f.batches), 1)  # No retry or fallback.

    def test_failed_batch_charged_and_no_fallback(self):
        f = Batched()
        def fail(*args):
            raise Invalid('synthetic transport error')
        f.closing_batch = fail
        f.connection = lambda *args: self.fail('fallback must not run')
        s = Collector(f).collect()
        self.assertEqual(s['coverage']['status'], 'INCOMPLETE')
        self.assertEqual(s['coverage']['calls'], 12)  # Metadata + inventory + 10 reserved aliases.
        self.assertEqual(s['coverage']['http_requests'], 3)

    def test_inventory_comment_and_source_schema_checks_retained(self):
        for kind in ('inventory', 'comments', 'source'):
            f = Batched()
            original = f.get
            inventories = []
            def read(path, p, t):
                r = original(path, p, t)
                if path == PREFIX + '/issues':
                    inventories.append(1)
                    if kind == 'inventory' and len(inventories) == 2:
                        r[0]['updated_at'] = 'changed'
                elif path == PREFIX + '/issues/7':
                    if kind == 'comments':
                        r['comments'] = 1
                    if kind == 'source':
                        r['number'] = 8
                return r
            f.get = read
            self.assertEqual(Collector(f).collect()['coverage']['status'], 'INCOMPLETE')


if __name__ == '__main__':
    unittest.main()
