"""Approved, one-shot temporary Gemma context; installed LaunchAgent remains untouched."""
import copy
import json
import os
from pathlib import Path
import plistlib
import re
import signal
import subprocess
import time

from evaluation.core import EvaluationError, canonical, digest, require, write_new
from .relay import live_context

PLIST = Path('/Users/work/Library/LaunchAgents/local.llama-server.plist')
ORIGINAL_HASH = 'eb17a4eb952d83f13e3f5fda1f5ed2f8f7441c85126bd4237cecc0dd5346da04'
MEMORY_PLAN_HASH = '41f8f669acedbf0a90d861765ed0e178d7a6cf0a79653ccb15ea9171eeb6342e'
COMPACT_PLAN_HASH = '1bfc9f6689c763f74655926100cf05ad49e8c7c03c2c8e61d05f75d10ad84687'
MATRIX_PLAN_HASH = '36cdadd0f09996a7e6c0e52daf88b7597033881f57a6db1fd9497668ac2bfe87'
MEMORY_OPTIONS = ['--no-mmproj', '--cache-type-k', 'q8_0', '--cache-type-v', 'q8_0',
                  '--flash-attn', 'on', '--batch-size', '512', '--ubatch-size', '128']


def temporary_plist(data, *, memory_saving=False, compact_memory=False, matrix_profile=False):
    require(not compact_memory or memory_saving, 'MEMORY_PROFILE_SCOPE')
    require(not matrix_profile or memory_saving and not compact_memory, 'MATRIX_PROFILE_SCOPE')
    require(digest(data) == ORIGINAL_HASH, 'ORIGINAL_SERVICE_CHANGED')
    value = plistlib.loads(data)
    require(value.get('Label') == 'local.llama-server' and
            set(value.get('EnvironmentVariables', {})) == {'HOME'}, 'SERVICE_SCOPE')
    args = value.get('ProgramArguments', [])
    for flag, expected in (('--ctx-size', '32768'), ('--host', '127.0.0.1'),
                           ('--port', '8081'), ('--alias', 'gemma-4-e4b')):
        require(args.count(flag) == 1 and args[args.index(flag) + 1] == expected, 'SERVICE_SCOPE')
    updated = copy.deepcopy(value)
    updated['ProgramArguments'][args.index('--ctx-size') + 1] = '65536'
    check = copy.deepcopy(updated)
    check['ProgramArguments'][args.index('--ctx-size') + 1] = '32768'
    require(check == value, 'SERVICE_DIFF')
    if memory_saving:
        changed = updated['ProgramArguments']
        require(changed.count('--mmproj') == 1 and
                all(flag not in changed for flag in MEMORY_OPTIONS if flag.startswith('--')),
                'MEMORY_PROFILE_SCOPE')
        index = changed.index('--mmproj')
        del changed[index:index + 2]
        changed.extend(MEMORY_OPTIONS)
        check = copy.deepcopy(updated)
        restored = check['ProgramArguments']
        del restored[-len(MEMORY_OPTIONS):]
        restored[index:index] = args[index:index + 2]
        restored[args.index('--ctx-size') + 1] = '32768'
        require(check == value, 'SERVICE_DIFF')
    result = plistlib.dumps(updated, sort_keys=False)
    if memory_saving:
        require(digest(result) == MEMORY_PLAN_HASH, 'MEMORY_PLAN_CHANGED')
    if compact_memory:
        compact = copy.deepcopy(updated)
        arguments = compact['ProgramArguments']
        changes = (('--cache-ram', '1024', '0'), ('--batch-size', '512', '128'), ('--ubatch-size', '128', '32'))
        for flag, before, after in changes:
            require(arguments.count(flag) == 1 and arguments[arguments.index(flag) + 1] == before,
                    'MEMORY_PROFILE_SCOPE')
            arguments[arguments.index(flag) + 1] = after
        check = copy.deepcopy(compact)
        for flag, before, after in changes:
            check['ProgramArguments'][arguments.index(flag) + 1] = before
        require(check == updated, 'SERVICE_DIFF')
        result = plistlib.dumps(compact, sort_keys=False)
        require(digest(result) == COMPACT_PLAN_HASH, 'MEMORY_PLAN_CHANGED')
    if matrix_profile:
        matrix = copy.deepcopy(updated)
        arguments = matrix['ProgramArguments']
        require(arguments.count('--reasoning') == 1 and arguments[arguments.index('--reasoning') + 1] == 'off' and
                '--reasoning-format' not in arguments and '--reasoning-budget' not in arguments, 'MATRIX_PROFILE_SCOPE')
        arguments[arguments.index('--reasoning') + 1] = 'on'
        arguments.extend(['--reasoning-format', 'deepseek', '--reasoning-budget', '1024'])
        result = plistlib.dumps(matrix, sort_keys=False)
        require(digest(result) == MATRIX_PLAN_HASH, 'MATRIX_PLAN_CHANGED')
    return result


def resource_values(swap_output, pressure_output):
    swap = re.search(r'used\s*=\s*([0-9]+(?:\.[0-9]+)?)([MG])', swap_output)
    free = re.search(r'System-wide memory free percentage:\s*(\d+)%', pressure_output)
    require(swap is not None and free is not None, 'RESOURCE_UNVERIFIED')
    used = float(swap[1]) * (1024 if swap[2] == 'G' else 1)
    percent = int(free[1])
    require(0 <= used <= 262144 and 0 <= percent <= 100, 'RESOURCE_UNVERIFIED')
    return {'swap_mib': used, 'memory_free_percent': percent}


def resources():
    def read(argv):
        result = subprocess.run(argv, capture_output=True, text=True, timeout=5)
        require(result.returncode == 0 and len(result.stdout) <= 8192, 'RESOURCE_UNVERIFIED')
        return result.stdout
    return resource_values(read(['/usr/sbin/sysctl', 'vm.swapusage']),
                           read(['/usr/bin/memory_pressure', '-Q']))


def resource_gate(baseline, current):
    require(current['swap_mib'] - baseline['swap_mib'] < 32, 'SWAP_GROWTH')
    require(current['memory_free_percent'] >= 10, 'MEMORY_PRESSURE')


class TemporaryContext:
    def __init__(self, work, *, command=None, context=None, sleeper=None, guard=None, memory_saving=False,
                 compact_memory=False, matrix_profile=False):
        self.work = Path(work)
        self.command = command or self.launchctl
        self.context = context or (lambda: live_context(deadline=time.monotonic() + 3))
        self.sleep = sleeper or time.sleep
        self.guard = guard or (lambda: None)
        self.memory_saving = memory_saving
        self.compact_memory = compact_memory
        self.matrix_profile = matrix_profile
        self.changed = False
        self.restore_attempted = False
        self.events = []
        self.report = {'status': 'NOT_STARTED', 'restoration': 'NOT_REQUIRED'}

    @staticmethod
    def launchctl(action, path):
        require(action in ('load', 'unload'), 'SERVICE_ACTION')
        env = {'PATH': '/usr/bin:/bin:/usr/sbin:/sbin', 'HOME': '/Users/work', 'LANG': 'C'}
        result = subprocess.run(['/bin/launchctl', action, str(path)], env=env,
                                capture_output=True, timeout=10)
        require(result.returncode == 0, 'SERVICE_' + action.upper() + '_FAILED')

    def record(self, phase):
        self.events.append({'phase': phase, 'utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())})
        with (self.work / 'service-events.jsonl').open('ab') as stream:
            stream.write(canonical(self.events[-1]) + b'\n')
            stream.flush()
            os.fsync(stream.fileno())

    def wait(self, expected, *, monitor=False):
        until = time.monotonic() + 60
        while time.monotonic() < until:
            if monitor:
                self.guard()
            try:
                if self.context() == expected:
                    return
            except (EvaluationError, OSError):
                pass
            self.sleep(1)
        raise EvaluationError('SERVICE_CONTEXT_TIMEOUT')

    def start(self, data):
        require(not self.changed and self.context() == 32768, 'SERVICE_INITIAL_CONTEXT')
        temporary = temporary_plist(data, memory_saving=self.memory_saving, compact_memory=self.compact_memory,
                                    matrix_profile=self.matrix_profile)
        write_new(self.work / 'original.plist', data)
        write_new(self.work / 'temporary-64k.plist', temporary)
        self.report.update(original_hash=digest(data), temporary_hash=digest(temporary),
                           original_context=32768, temporary_context=65536,
                           memory_saving=self.memory_saving, compact_memory=self.compact_memory,
                           matrix_profile=self.matrix_profile)
        self.record('CHANGE_INTENT')
        self.changed = True  # Even an ambiguous unload must enter the restoration boundary.
        self.command('unload', PLIST)
        self.record('ORIGINAL_UNLOADED')
        self.command('load', self.work / 'temporary-64k.plist')
        self.record('TEMPORARY_LOADED')
        self.wait(65536, monitor=True)
        self.guard()
        self.record('CONTEXT_65536_CONFIRMED')
        self.report['status'] = 'ACTIVE'

    def restore(self):
        if not self.changed:
            return
        require(not self.restore_attempted, 'RESTORATION_ALREADY_ATTEMPTED')
        self.restore_attempted = True
        self.report['restoration'] = 'RECOVERY_REQUIRED'
        self.record('RESTORE_INTENT')
        require(digest(PLIST.read_bytes()) == self.report['original_hash'], 'INSTALLED_SERVICE_CHANGED')
        # A failed temporary load can leave no job. Always attempt the original load;
        # launchctl refuses to replace an already loaded job. Verify the live result.
        try:
            self.command('unload', self.work / 'temporary-64k.plist')
        except (EvaluationError, OSError, subprocess.TimeoutExpired):
            self.record('UNLOAD_RESULT_UNCERTAIN')
        try:
            self.command('load', PLIST)
        except (EvaluationError, OSError, subprocess.TimeoutExpired):
            self.record('LOAD_RESULT_UNCERTAIN')
        self.wait(32768)
        require(digest(PLIST.read_bytes()) == self.report['original_hash'], 'RESTORE_HASH')
        self.report['restoration'] = 'VERIFIED'
        self.record('CONTEXT_32768_RESTORED')


def run_temporary(root, preparation, *, memory_saving=False, carry_report=None, deadline_epoch=None, request_timeout=90,
                  budget_profile='standard', compact_memory=False, repair_report=None, patch_only=False, patch_attempt=1,
                  matrix=False, operations=False, cycle=False, reuse_cycle=False, controlled_execution=False):
    work = Path(root) / 'runs' / ('context64-' + time.strftime('%Y%m%dT%H%M%SZ', time.gmtime()))
    work.mkdir(mode=0o700, exist_ok=False)
    manager = TemporaryContext(work, memory_saving=memory_saving, compact_memory=compact_memory, matrix_profile=matrix or operations or cycle or reuse_cycle or controlled_execution)
    process = None
    report = manager.report
    report['reason'] = 'INCOMPLETE'
    try:
        baseline = resources()
        if deadline_epoch is not None:
            require(deadline_epoch - time.time() > 120, 'RUN_DEADLINE')
        report['baseline_resources'] = baseline
        def guard():
            current = resources()
            report['last_resources'] = current
            resource_gate(baseline, current)
        manager.guard = guard
        resource_gate(baseline, baseline)
        manager.start(PLIST.read_bytes())
        until = time.monotonic() + (min(3540, deadline_epoch - time.time() - 60) if deadline_epoch else 1200)
        env = {'PATH': '/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin',
               'HOME': '/Users/work', 'LANG': 'C.UTF-8'}
        output_path = work / 'controller-output.txt'
        command = [os.sys.executable, '-I', '-B', str(Path(root) / 'scripts/delegate_skill.py'),
                   'run', '--preparation', str(preparation), '--request-timeout', str(request_timeout),
                   '--budget-profile', budget_profile]
        if carry_report is not None:
            command.extend(['--carry-report', str(carry_report)])
        if repair_report is not None:
            command.extend(['--repair-report', str(repair_report)])
        if patch_only:
            command.extend(['--patch-only', '--patch-attempt', str(patch_attempt)])
        if matrix:
            command.append('--matrix')
        if operations:
            command.append('--operations')
        if cycle:
            command.append('--cycle')
        if reuse_cycle:
            command.append('--reuse-cycle')
        if controlled_execution:
            command.append('--controlled-execution')
        if deadline_epoch is not None:
            command.extend(['--deadline-epoch', str(deadline_epoch - 60)])
        with output_path.open('xb') as stream:
            process = subprocess.Popen(command, cwd=root, env=env,
                        stdout=stream, stderr=subprocess.STDOUT, start_new_session=True)
            while process.poll() is None:
                require(time.monotonic() < until, 'RUN_DEADLINE')
                current = resources()
                report['last_resources'] = current
                resource_gate(baseline, current)
                time.sleep(1)
        report['controller_exit'] = process.returncode
        require(process.returncode == 0, 'DELEGATION_STOPPED')
        report['status'] = 'VERIFIED'
        report['reason'] = None
    except BaseException as error:
        report['status'] = 'STOPPED'
        report['reason'] = str(error) if isinstance(error, EvaluationError) else 'SERVICE_EXPERIMENT_ERROR'
        raise
    finally:
        try:
            if process is not None and process.poll() is None:
                process.send_signal(signal.SIGTERM)
                try:
                    process.wait(timeout=35)
                except subprocess.TimeoutExpired:
                    report['controller_cleanup'] = 'UNVERIFIED'
                    # Kill only this controller; never assume its Docker containers were collected.
                    process.kill()
                    process.wait(timeout=5)
        except (OSError, subprocess.TimeoutExpired):
            report['controller_cleanup'] = 'UNVERIFIED'
        if report.get('controller_cleanup') == 'UNVERIFIED':
            report.update(status='STOPPED', reason='CONTROLLER_CLEANUP_UNVERIFIED')
        try:
            manager.restore()
        except BaseException:
            report['status'] = 'STOPPED'
            report['reason'] = 'RESTORATION_UNVERIFIED'
            raise
        finally:
            write_new(work / 'service-report.json', canonical(report) + b'\n')
            print(json.dumps({'service_run': work.name, 'status': report['status'],
                              'reason': report['reason'], 'restoration': report['restoration']}))
