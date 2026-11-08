"""Allowlisted GitHub read transport and bounded acquisition (existing gh auth)."""
import re
import subprocess
import time
from dataclasses import asdict, dataclass

from .core import (CLOSED_PR_OMITTED, Invalid, REPO, digest, number, now, require, seal, source_url,
                   strict_json, validate)

PREFIX = f'repos/{REPO}'
REST = re.compile(re.escape(PREFIX) + r'(?:|/issues|/issues/[1-9][0-9]*(?:/comments)?|/pulls/[1-9][0-9]*(?:/reviews|/comments)?|/commits/[0-9a-f]{40}/(?:check-runs|statuses))\Z')
CONNECTIONS = {
    'threads': ('reviewThreads', 'id isResolved isOutdated'),
    'closing': ('closingIssuesReferences', 'number repository { nameWithOwner }'),
}
BATCH_SIZE = 10


@dataclass(frozen=True)
class Limits:
    pages: int = 10  # Per connection, not per repository.
    items: int = 5000  # All returned list nodes, including checks/comments.
    calls: int = 500
    seconds: int = 180

    def __post_init__(self):
        for field, maximum in (('pages', 10), ('items', 5000), ('calls', 500), ('seconds', 180)):
            require(type(getattr(self, field)) is int and 0 < getattr(self, field) <= maximum, 'invalid limit')


def rest_request(path, page=None):
    require(isinstance(path, str) and REST.fullmatch(path) is not None, 'read route not allowlisted')
    query = ''
    if path == PREFIX + '/issues':
        require(page is not None, 'issue list requires page')
        query = 'state=all&sort=created&direction=asc&'
    if page is not None:
        require(type(page) is int and 1 <= page <= 10, 'invalid page')
        query += f'per_page=100&page={page}'
    return path + ('?' + query if query else '')


def connection_query(kind):
    require(kind in CONNECTIONS, 'unknown connection')
    name, fields = CONNECTIONS[kind]
    return ('query($number:Int!,$cursor:String){repository(owner:"second-works",name:"hermes-self-improvement")'
            '{pullRequest(number:$number){' + name + '(first:100,after:$cursor){nodes{' + fields + '}'
            'pageInfo{hasNextPage endCursor}}}}}')


def closing_batch_query(requests):
    """Only bounded closing-reference reads, with all untrusted values in variables."""
    require(isinstance(requests, list) and 0 < len(requests) <= BATCH_SIZE, 'invalid batch size')
    variables, fields, seen = [], [], set()
    for i, (n, cursor) in enumerate(requests):
        number(n)
        require(n not in seen, 'duplicate batch PR')
        seen.add(n)
        require(cursor is None or isinstance(cursor, str) and 0 < len(cursor) <= 1024, 'invalid cursor')
        variables += [f'$n{i}:Int!', f'$c{i}:String']
        fields.append(f'p{i}:pullRequest(number:$n{i})' + '{number closingIssuesReferences(first:100,after:$c'
                      + str(i) + '){nodes{number repository{nameWithOwner}}pageInfo{hasNextPage endCursor}}}')
    return ('query(' + ','.join(variables) + '){repository(owner:"second-works",name:"hermes-self-improvement")'
            '{nameWithOwner ' + ' '.join(fields) + '}}')


class GhReadOnly:
    """No public arbitrary command/query/method facility; never reads token values."""
    @staticmethod
    def _run(args, timeout):
        try:
            proc = subprocess.run(['gh', 'api', '--hostname', 'github.com', *args],
                                  capture_output=True, timeout=timeout, check=False)
        except (OSError, subprocess.TimeoutExpired):
            raise Invalid('GitHub transport unavailable/timeout') from None
        require(proc.returncode == 0, 'GitHub read failed (auth/permission/rate/network); details omitted')
        require(len(proc.stdout) <= 10_000_000, 'API response too large')
        try:
            return strict_json(proc.stdout.decode('utf-8'))
        except UnicodeError:
            raise Invalid('invalid API encoding') from None

    def get(self, path, page, timeout):
        return self._run(['--method', 'GET', rest_request(path, page)], timeout)

    def connection(self, kind, n, cursor, timeout):
        number(n)
        require(cursor is None or isinstance(cursor, str) and 0 < len(cursor) <= 1024, 'invalid cursor')
        args = ['graphql', '-f', 'query=' + connection_query(kind), '-F', f'number={n}']
        if cursor is not None:
            args += ['-f', 'cursor=' + cursor]
        return self._run(args, timeout)

    def closing_batch(self, requests, timeout):
        args = ['graphql', '-f', 'query=' + closing_batch_query(requests)]
        for i, (n, cursor) in enumerate(requests):
            args += ['-F', f'n{i}={n}']
            if cursor is not None:
                args += ['-f', f'c{i}={cursor}']
        return self._run(args, timeout)


class Collector:
    def __init__(self, transport=None, limits=None):
        self.transport = transport or GhReadOnly()
        self.limits = limits or Limits()
        self.started = time.monotonic()
        self.calls = 0
        self.http_requests = 0
        self.nodes = 0
        self.connections = []

    def call(self, function, *args, cost=1):
        remaining = self.limits.seconds - (time.monotonic() - self.started)
        # A batch reserves one logical read per alias, retaining the original 500-read budget.
        require(type(cost) is int and 0 < cost <= BATCH_SIZE, 'invalid read cost')
        require(self.calls + cost <= self.limits.calls and remaining > 0, 'API/time limit reached')
        self.calls += cost
        self.http_requests += 1
        result = function(*args, min(30, remaining))
        require(time.monotonic() - self.started <= self.limits.seconds, 'time limit reached')
        return result

    def count(self, rows):
        require(isinstance(rows, list), 'API list missing')
        self.nodes += len(rows)
        require(self.nodes <= self.limits.items, 'item limit reached')

    def pages(self, path, field=None):
        marker = {'route': path, 'pages': 0, 'count': 0, 'complete': False}
        self.connections.append(marker)
        result = []
        expected = None
        for page in range(1, self.limits.pages + 1):
            response = self.call(self.transport.get, path, page)
            marker['pages'] = page
            if field:
                require(isinstance(response, dict) and type(response.get('total_count')) is int, 'check count missing')
                if expected is None:
                    expected = response['total_count']
                require(expected == response['total_count'], 'check count changed during pagination')
                rows = response.get(field)
            else:
                rows = response
            self.count(rows)
            require(len(rows) <= 100, 'invalid page size')
            result += rows
            marker['count'] = len(result)
            if len(rows) < 100:
                require(expected is None or len(result) == expected, 'partial check results')
                marker['complete'] = True
                return result
        raise Invalid('page limit reached')

    def connection(self, kind, n):
        marker = {'route': f'pr:{n}:{kind}', 'pages': 0, 'count': 0, 'complete': False}
        self.connections.append(marker)
        result, cursor, seen = [], None, set()
        for page in range(1, self.limits.pages + 1):
            response = self.call(self.transport.connection, kind, n, cursor)
            require(isinstance(response, dict) and not response.get('errors'), 'GraphQL read error')
            name = CONNECTIONS[kind][0]
            connection = response['data']['repository']['pullRequest'][name]
            rows, info = connection['nodes'], connection['pageInfo']
            self.count(rows)
            require(len(rows) <= 100 and type(info['hasNextPage']) is bool, 'invalid GraphQL pagination')
            result += rows
            marker.update(pages=page, count=len(result))
            if not info['hasNextPage']:
                marker['complete'] = True
                return result
            cursor = info['endCursor']
            require(isinstance(cursor, str) and cursor and cursor not in seen, 'missing/repeated cursor')
            seen.add(cursor)
        raise Invalid('GraphQL page limit reached')

    def closings(self, numbers):
        result = {n: [] for n in numbers}
        for offset in range(0, len(numbers), BATCH_SIZE):
            active = [(n, None) for n in numbers[offset:offset + BATCH_SIZE]]
            markers, cursors = {}, {n: set() for n, _ in active}
            for n, _ in active:
                markers[n] = {'route': f'pr:{n}:closing', 'pages': 0, 'count': 0, 'complete': False}
                self.connections.append(markers[n])
            while active:
                require(all(markers[n]['pages'] < self.limits.pages for n, _ in active), 'GraphQL page limit reached')
                response = self.call(self.transport.closing_batch, active, cost=len(active))
                require(isinstance(response, dict) and not response.get('errors'), 'GraphQL read error')
                repo = response['data']['repository']
                require(repo['nameWithOwner'] == REPO, 'GraphQL repository mismatch')
                require(set(repo) == {'nameWithOwner'} | {f'p{i}' for i in range(len(active))}, 'GraphQL aliases missing')
                pending = []
                for i, (n, _) in enumerate(active):
                    pr = repo[f'p{i}']
                    require(type(pr['number']) is int and pr['number'] == n, 'GraphQL PR mismatch')
                    connection = pr['closingIssuesReferences']
                    rows, info = connection['nodes'], connection['pageInfo']
                    self.count(rows)
                    require(len(rows) <= 100 and type(info['hasNextPage']) is bool, 'invalid GraphQL pagination')
                    result[n] += rows
                    marker = markers[n]
                    marker.update(pages=marker['pages'] + 1, count=len(result[n]))
                    if not info['hasNextPage']:
                        marker['complete'] = True
                        continue
                    cursor = info['endCursor']
                    require(isinstance(cursor, str) and 0 < len(cursor) <= 1024
                            and cursor not in cursors[n], 'missing/repeated cursor')
                    cursors[n].add(cursor)
                    pending.append((n, cursor))
                active = pending
        return result

    def collect(self):
        items, errors = {}, []
        try:
            meta = self.call(self.transport.get, PREFIX, None)
            require(meta['full_name'] == REPO and meta['private'] is False and meta['visibility'] == 'public', 'PUBLIC repo required')
            listing = self.pages(PREFIX + '/issues')
            seen = set()
            for row in listing:
                n = number(row['number'])
                require(n not in seen, 'duplicate issue/PR in pagination')
                seen.add(n)
            # Capability check is only for existing injected transports. A failed batch never retries.
            batched = callable(getattr(self.transport, 'closing_batch', None))
            closings = self.closings([row['number'] for row in listing if 'pull_request' in row]) if batched else {}
            for row in listing:
                n = row['number']
                kind = 'pr' if 'pull_request' in row else 'issue'
                route = f'{PREFIX}/{"pulls" if kind == "pr" else "issues"}/{n}'
                detail = self.call(self.transport.get, route, None)
                require(detail['number'] == n and detail['html_url'] == source_url(kind, n), 'API target mismatch')
                raw = {'detail': detail, 'comments': self.pages(f'{PREFIX}/issues/{n}/comments')}
                require(detail['comments'] == len(raw['comments']), 'comment count changed/partial')
                if kind == 'pr':
                    sha = detail['head']['sha']
                    require(isinstance(sha, str) and re.fullmatch(r'[0-9a-f]{40}', sha), 'invalid head')
                    require(detail['state'] in ('open', 'closed'), 'invalid PR state')
                    # Closed/merged PRs are only shown as "no action"; their review gate is not read (#49).
                    if detail['state'] == 'open':
                        raw.update(checks=self.pages(f'{PREFIX}/commits/{sha}/check-runs', 'check_runs'),
                                   statuses=self.pages(f'{PREFIX}/commits/{sha}/statuses'),
                                   reviews=self.pages(f'{PREFIX}/pulls/{n}/reviews'),
                                   review_comments=self.pages(f'{PREFIX}/pulls/{n}/comments'),
                                   threads=self.connection('threads', n))
                    raw['closing'] = closings[n] if batched else self.connection('closing', n)
                item = {'kind': kind, 'number': n, 'state': 'MERGED' if kind == 'pr' and detail['merged'] else detail['state'].upper(),
                        'title': detail['title'], 'body': detail['body'] or '', 'url': source_url(kind, n),
                        'raw': raw, 'hash': digest(raw)}
                items[f'{kind}:{n}'] = item
            # A second inventory catches additions/state changes during the multi-request sweep.
            final = self.pages(PREFIX + '/issues')
            def inventory(rows):
                return sorted((x['number'], x['updated_at'], x['state']) for x in rows)
            require(inventory(listing) == inventory(final), 'inventory changed during collection')
        except (Invalid, KeyError, TypeError, ValueError, AttributeError):
            # Raw error messages may contain remote text or auth diagnostics: never persist them.
            errors.append('取得不完全: schema/権限/rate limit/network/上限/収集中の変化を確認してください。')
        coverage = {'status': 'INCOMPLETE' if errors else 'COMPLETE', 'errors': errors,
                    'calls': self.calls, 'http_requests': self.http_requests,
                    'limits': asdict(self.limits), 'connections': self.connections,
                    'returned_nodes': self.nodes, 'finished_at': now(),
                    'scope': 'all issue/PR states; bodies, comments, heads, closing links; '
                             'checks, statuses, reviews, review comments, threads for OPEN PRs only',
                    'omitted': CLOSED_PR_OMITTED}
        snapshot = seal(items, coverage)
        # Invalid partial items are not silently emitted as complete.
        try:
            validate(snapshot)
        except (Invalid, KeyError, TypeError, AttributeError):
            coverage['status'] = 'INCOMPLETE'
            coverage['errors'].append('取得した原文のschemaを検証できません。')
            snapshot = seal({}, coverage)
        return snapshot
