"""Read commit dates from registered local checkouts as a proxy for work days (#108).

Only local `git rev-parse` and `git log` run, with fixed arguments and without user or system git
configuration. Nothing is fetched, no remote is contacted, and nothing in the checkout is written.
"""
from datetime import datetime, timedelta, timezone
import os
from pathlib import Path
import re
import subprocess

from skill_improvement.ledger import LedgerError, inside, require

GIT_TIMEOUT_SECONDS = 30
SHA = re.compile(r'[0-9a-f]{40}')
# Allowed git subcommands. Tests check that nothing else (fetch, pull, remote ...) is ever run.
ALLOWED_SUBCOMMANDS = ('rev-parse', 'log')


def git_environment():
    return {'PATH': os.environ.get('PATH', '/usr/bin:/bin'), 'LC_ALL': 'C', 'GIT_CONFIG_NOSYSTEM': '1',
            'GIT_CONFIG_GLOBAL': os.devnull, 'GIT_TERMINAL_PROMPT': '0', 'GIT_OPTIONAL_LOCKS': '0',
            'HOME': os.devnull}


def checkout_path(item):
    """The registered checkout must be a canonical, symlink-free git working tree outside ~/.hermes."""
    path = Path(item['local_checkout'])
    require(path.is_absolute() and not {'.', '..'} & set(str(path).split('/')), 'REPOSITORY_UNAVAILABLE',
            f"{item['repository_id']}: absolute path without . or .. required")
    # Compared before anything touches the file system, so ~/.hermes is never resolved or opened.
    require(not inside(path, Path.home() / '.hermes'), 'REPOSITORY_UNAVAILABLE',
            f"{item['repository_id']}: ~/.hermes is never read")
    require(not inside(path, '/System/Volumes/Data'), 'REPOSITORY_UNAVAILABLE',
            f"{item['repository_id']}: use the path without /System/Volumes/Data")
    require(os.path.realpath(path) == str(path), 'REPOSITORY_UNAVAILABLE',
            f"{item['repository_id']}: symlinks and non-canonical paths are not allowed")
    require(path.is_dir() and not path.is_symlink(), 'REPOSITORY_UNAVAILABLE',
            f"{item['repository_id']}: checkout directory is missing")
    require(os.path.lexists(path / '.git'), 'REPOSITORY_UNAVAILABLE', f"{item['repository_id']}: not a git checkout")
    return path


def run_git(path, subcommand, *args):
    require(subcommand in ALLOWED_SUBCOMMANDS, 'REPOSITORY_UNAVAILABLE', 'git subcommand not allowed')
    command = ['git', '-c', 'core.fsmonitor=false', '-C', str(path), subcommand, *args]
    try:
        done = subprocess.run(command, env=git_environment(), capture_output=True, text=True,
                              timeout=GIT_TIMEOUT_SECONDS, check=False)
    except (OSError, subprocess.TimeoutExpired):
        raise LedgerError('REPOSITORY_UNAVAILABLE', 'git could not run') from None
    return done


def branch_tips(item):
    """Current commit of each allowed branch, or None when the branch does not exist locally."""
    path = checkout_path(item)
    tips = {}
    for branch in item['allowed_branches']:
        done = run_git(path, 'rev-parse', '--verify', '--quiet', f'refs/heads/{branch}^{{commit}}')
        value = done.stdout.strip()
        tips[branch] = value if done.returncode == 0 and SHA.fullmatch(value) else None
    return tips


def is_bot(name, email):
    return '[bot]' in name.lower() or '[bot]' in email.lower()


def commit_dates(item, tips, zone, start, end):
    """Local dates (manifest timezone) of non-merge, non-bot commits reachable from the allowed branches.

    The committer date is used: a cherry-pick or rebase counts on the day it was applied. A commit on
    several branches counts once.
    """
    path = checkout_path(item)
    since = datetime.combine(start, datetime.min.time(), zone).astimezone(timezone.utc) - timedelta(days=1)
    seen, dates, bots = set(), set(), 0
    for sha in sorted({value for value in tips.values() if value}):
        done = run_git(path, 'log', '--no-merges', f'--since={int(since.timestamp())}',
                       '--format=%H%x09%ct%x09%an%x09%ae', sha)
        require(done.returncode == 0, 'REPOSITORY_UNAVAILABLE', f"{item['repository_id']}: git log failed")
        for line in done.stdout.splitlines():
            parts = line.split('\t')
            if len(parts) != 4 or not SHA.fullmatch(parts[0]) or not parts[1].isdigit() or parts[0] in seen:
                continue
            seen.add(parts[0])
            if is_bot(parts[2], parts[3]):
                bots += 1
                continue
            day = datetime.fromtimestamp(int(parts[1]), zone).date()
            if start <= day <= end:
                dates.add(day)
    return dates, {'commits_read': len(seen), 'bot_commits_excluded': bots}
