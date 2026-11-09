"""Read commit dates from registered local checkouts as a proxy for work days (#108).

Only local `git rev-parse` and `git log` run, with fixed arguments and without user or system git
configuration. The checkout's own config is still read by git, so settings that could start a program or
read another file are forced off, and config includes are refused. Nothing is fetched, no remote is
contacted, and nothing in the checkout is written.
"""
from datetime import datetime
import hashlib
from itertools import dropwhile
import os
from pathlib import Path
import re
import subprocess

from skill_improvement.ledger import LedgerError, inside, require

GIT_TIMEOUT_SECONDS = 30
SHA = re.compile(r'[0-9a-f]{40}')
# Allowed git subcommands. Tests check that nothing else (fetch, pull, remote ...) is ever run.
ALLOWED_SUBCOMMANDS = ('rev-parse', 'log')
# The checkout's own config is still read by git. These settings could start a program or read a file
# elsewhere, so they are forced off for every call (signature checks, mailmap, pager, fsmonitor).
FORCED_CONFIG = ('core.fsmonitor=false', 'core.pager=cat', 'log.showSignature=false', 'log.mailmap=false',
                 'mailmap.file=', 'mailmap.blob=', 'gpg.program=false', 'gpg.openpgp.program=false',
                 'gpg.ssh.program=false', 'gpg.x509.program=false')
# Anywhere, not only at line start: git accepts several section headers on one line (`[core] [include]`).
INCLUDE = re.compile(r'\[\s*include', re.IGNORECASE)
# Not read by rev-parse or log; other tools often place symlinks here.
SKIPPED_IN_WALK = ('hooks',)
MAX_CONFIG_BYTES = 1024 * 1024


def git_environment():
    return {'PATH': os.environ.get('PATH', '/usr/bin:/bin'), 'LC_ALL': 'C', 'GIT_CONFIG_NOSYSTEM': '1',
            'GIT_CONFIG_GLOBAL': os.devnull, 'GIT_TERMINAL_PROMPT': '0', 'GIT_OPTIONAL_LOCKS': '0',
            'GIT_NO_REPLACE_OBJECTS': '1', 'GIT_NO_LAZY_FETCH': '1', 'HOME': os.devnull}


def safe_directory(path, repository, what):
    """A canonical, symlink-free directory outside ~/.hermes; checked before anything resolves it."""
    text = str(path)
    require(path.is_absolute() and not {'.', '..'} & set(text.split('/')), 'REPOSITORY_UNAVAILABLE',
            f'{repository}: {what} must be an absolute path without . or ..')
    # Compared before anything touches the file system, so ~/.hermes is never resolved or opened.
    require(not inside(path, Path.home() / '.hermes'), 'REPOSITORY_UNAVAILABLE', f'{repository}: ~/.hermes is never read')
    require(not inside(path, '/System/Volumes/Data'), 'REPOSITORY_UNAVAILABLE',
            f'{repository}: use the path without /System/Volumes/Data')
    require(os.path.realpath(path) == text, 'REPOSITORY_UNAVAILABLE',
            f'{repository}: symlinks and non-canonical paths are not allowed ({what})')
    require(path.is_dir() and not path.is_symlink(), 'REPOSITORY_UNAVAILABLE', f'{repository}: {what} is missing')
    return path


def pointer(base, name, repository):
    """Read a one-line path file such as `.git` (gitdir: X) or `commondir`, relative to base."""
    try:
        with open(base / name, 'rb') as handle:
            text = handle.read(4097).decode('utf-8').strip()
    except (OSError, UnicodeDecodeError):
        raise LedgerError('REPOSITORY_UNAVAILABLE', f'{repository}: {name} is unreadable') from None
    if name == '.git':
        require(text.startswith('gitdir:'), 'REPOSITORY_UNAVAILABLE', f'{repository}: .git file is invalid')
        text = text[len('gitdir:'):].strip()
    require(text and '\n' not in text and len(text) <= 4096, 'REPOSITORY_UNAVAILABLE', f'{repository}: {name} is invalid')
    # git resolves the value physically. Lexical normalisation gives the same place only when `..` comes
    # first (from an already canonical base); `x/../y` could cross a symlink at x, so it is refused.
    parts = [part for part in text.split('/') if part]
    leading = len(parts) - len(list(dropwhile(lambda part: part == '..', parts)))
    require(not {'.', '..'} & set(parts[leading:]), 'REPOSITORY_UNAVAILABLE',
            f'{repository}: {name} may use .. only at the start')
    return Path(os.path.normpath(base / text))


def no_symlinks_inside(directory, repository):
    """Refuse any symlink git might follow out of the checked directory (objects, refs, HEAD, packs ...)."""
    pending = [directory]
    while pending:
        current = pending.pop()
        try:
            entries = list(os.scandir(current))
        except OSError:
            raise LedgerError('REPOSITORY_UNAVAILABLE', f'{repository}: git directory is unreadable') from None
        for entry in entries:
            if current == directory and entry.name in SKIPPED_IN_WALK:
                continue
            require(not entry.is_symlink(), 'REPOSITORY_UNAVAILABLE',
                    f'{repository}: symlinks inside the git directory are not allowed')
            if entry.is_dir(follow_symlinks=False):
                pending.append(entry.path)


def git_directory(item):
    """Resolve and check every directory git will read for this checkout; return (git dir, common dir).

    `.git` may be a directory or a `gitdir:` file (worktree); a symlink is refused. The git directory,
    its `commondir`, and object alternates must all stay outside ~/.hermes, and config includes are
    refused because they would make git read files that were not checked here.
    """
    repository = item['repository_id']
    checkout = safe_directory(Path(item['local_checkout']), repository, 'checkout')
    dot = checkout / '.git'
    require(not dot.is_symlink() and dot.exists(), 'REPOSITORY_UNAVAILABLE', f'{repository}: not a git checkout')
    gitdir = dot if dot.is_dir() else pointer(checkout, '.git', repository)
    safe_directory(gitdir, repository, 'git directory')
    common = gitdir
    if os.path.lexists(gitdir / 'commondir'):
        common = safe_directory(pointer(gitdir, 'commondir', repository), repository, 'common git directory')
    for directory in {gitdir, common}:
        no_symlinks_inside(directory, repository)
    # grafts rewrite history without moving any branch tip, so a cached report could go stale.
    require(not os.path.lexists(common / 'info' / 'grafts'), 'REPOSITORY_UNAVAILABLE',
            f'{repository}: grafts are not supported')
    alternates = common / 'objects' / 'info' / 'alternates'
    require(not os.path.lexists(alternates) or os.path.getsize(alternates) == 0, 'REPOSITORY_UNAVAILABLE',
            f'{repository}: object alternates are not supported')
    for config in (common / 'config', gitdir / 'config.worktree'):
        if not os.path.lexists(config):
            continue
        require(config.is_file() and not config.is_symlink(), 'REPOSITORY_UNAVAILABLE',
                f'{repository}: git config must be a regular file')
        with open(config, 'rb') as handle:
            data = handle.read(MAX_CONFIG_BYTES + 1)
        require(len(data) <= MAX_CONFIG_BYTES and not INCLUDE.search(data.decode('utf-8', 'replace')),
                'REPOSITORY_UNAVAILABLE', f'{repository}: git config includes are not supported')
    return gitdir, common


def shallow_marker(common):
    """Digest of the shallow boundary: deepening history changes the result without moving any tip."""
    try:
        with open(common / 'shallow', 'rb') as handle:
            return hashlib.sha256(handle.read()).hexdigest()
    except FileNotFoundError:
        return None
    except OSError:
        raise LedgerError('REPOSITORY_UNAVAILABLE', 'shallow file is unreadable') from None


def run_git(gitdir, subcommand, *args):
    require(subcommand in ALLOWED_SUBCOMMANDS, 'REPOSITORY_UNAVAILABLE', 'git subcommand not allowed')
    forced = [part for setting in FORCED_CONFIG for part in ('-c', setting)]
    command = ['git', '--no-pager', *forced, f'--git-dir={gitdir}', subcommand, *args]
    try:
        done = subprocess.run(command, env=git_environment(), capture_output=True, text=True,
                              timeout=GIT_TIMEOUT_SECONDS, check=False, stdin=subprocess.DEVNULL)
    except (OSError, subprocess.TimeoutExpired):
        raise LedgerError('REPOSITORY_UNAVAILABLE', 'git could not run') from None
    return done


def branch_tips(item):
    """Current commit of each allowed branch, or None when the branch does not exist locally.

    Only exit code 1 of `rev-parse --verify --quiet` means "no such branch"; any other failure means
    the repository could not be read and stops the report instead of counting zero commits.
    """
    gitdir, common = git_directory(item)
    tips = {}
    for branch in item['allowed_branches']:
        done = run_git(gitdir, 'rev-parse', '--verify', '--quiet', f'refs/heads/{branch}^{{commit}}')
        value = done.stdout.strip()
        if done.returncode == 0 and SHA.fullmatch(value):
            tips[branch] = value
        else:
            require(done.returncode == 1 and not value, 'REPOSITORY_UNAVAILABLE',
                    f"{item['repository_id']}: git rev-parse failed")
            tips[branch] = None
    return tips, shallow_marker(common)


def is_bot(name, email):
    return '[bot]' in name.lower() or '[bot]' in email.lower()


def commit_dates(item, tips, zone, start, end):
    """Local dates (manifest timezone) of non-merge, non-bot commits reachable from the allowed branches.

    The committer date is used: a cherry-pick or rebase counts on the day it was applied. A commit on
    several branches counts once. All reachable commits are read and filtered by date: `--since` stops at
    the first older commit, so it drops in-period ancestors when committer dates go backwards. The
    report cache keeps this from running again while nothing changed.
    """
    gitdir = git_directory(item)[0]
    seen, dates, bots = set(), set(), 0
    for sha in sorted({value for value in tips.values() if value}):
        done = run_git(gitdir, 'log', '--no-merges', '--no-show-signature',
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
