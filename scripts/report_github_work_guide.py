#!/usr/bin/env python3
"""Manual collect/report/recheck/excerpt; deliberately no write or execution subcommand."""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from github_work_guide.collector import Collector
from github_work_guide.core import (OLD_PLAN, Invalid, REPO, build_plan, diff, excerpt, load_run, markdown,
                                   read_json, recheck, require, save_run, validate_plan)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=('collect', 'report', 'recheck', 'excerpt'))
    parser.add_argument('--repo', default=REPO)
    parser.add_argument('--run', type=Path, help='explicit saved planning run')
    parser.add_argument('--previous', type=Path, help='explicit previous run')
    parser.add_argument('--target', help='candidate ID, e.g. issue:26')
    parser.add_argument('--priority', nargs='*', default=[], help='human supplied IDs; dependencies take precedence')
    parser.add_argument('--out', type=Path, required=True, help='new runs/<name> directory')
    args = parser.parse_args(argv)
    try:
        require(args.repo == REPO, 'repository not allowlisted')
        require(args.mode == 'collect' or args.run is not None, '--run required')
        require(args.mode not in ('recheck', 'excerpt') or args.target is not None, '--target required')
        if args.mode == 'excerpt':
            # Saved-run read only: verified manifest/hash, complete acquisition and a matching saved plan.
            snapshot = load_run(args.run)
            require('plan.json' in read_json(args.run / 'manifest.json')['files'], 'saved plan required')
            text = excerpt(snapshot, read_json(args.run / 'plan.json'), args.target, args.run.name)
            save_run(args.out, {'excerpt.md': text})
            print(f'excerpt={len(text)} chars target={args.target} out={args.out}')
            return 0
        previous = load_run(args.previous) if args.previous else None
        result = None
        if args.mode == 'collect':
            snapshot = Collector().collect()
            plan = build_plan(snapshot, args.priority) if snapshot['coverage']['status'] == 'COMPLETE' else None
        else:
            snapshot = load_run(args.run)
            if args.mode == 'recheck':
                require('plan.json' in read_json(args.run / 'manifest.json')['files'], 'saved plan required')
                plan = read_json(args.run / 'plan.json')
                validate_plan(snapshot, plan)
                require(args.target in plan['candidates'], 'unknown candidate')
                fresh = Collector().collect()
                result = recheck(snapshot, plan, args.target, fresh)
                snapshot = fresh
                plan = build_plan(fresh, plan['priority']) if fresh['coverage']['status'] == 'COMPLETE' else None
            else:
                plan = build_plan(snapshot, args.priority) if snapshot['coverage']['status'] == 'COMPLETE' else None
        changes = diff(snapshot, previous)
        documents = {'snapshot.json': snapshot, 'diff.json': changes,
                     'report.md': markdown(snapshot, changes, plan, result)}
        if plan is not None:
            documents['plan.json'] = plan
        if result is not None:
            documents['recheck.json'] = result
        save_run(args.out, documents)
        print(f'coverage={snapshot["coverage"]["status"]} items={len(snapshot["items"])} out={args.out}')
        if result:
            print(f'dry_run={result["status"]}')
        return 0 if snapshot['coverage']['status'] == 'COMPLETE' and (not result or result['status'] == 'CONFIRMED') else 2
    except (Invalid, OSError, KeyError, TypeError, AttributeError, ValueError) as error:
        # Only fixed messages are printed; raw errors may carry remote text or auth diagnostics.
        if isinstance(error, Invalid) and str(error) == OLD_PLAN:
            print(f'BLOCKED: {OLD_PLAN}', file=sys.stderr)
            return 2
        print('BLOCKED: 入力/取得/保存を検証できません。原本と新規出力先を確認してください。', file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
