"""Run one bounded Claude/Codex worker; completion never proves acceptance."""

import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import tempfile
import time


GUARD = """You are one delegated dev-flow worker. Stay within the supplied task.
Do not run Git commands, commit, push, post messages, change accounts/config,
launch subagents, or edit the shared dev-flow skill. Return evidence and gaps;
the coordinator owns task state and decides the next stage. Never weaken tests
or bypass permissions/gates. A review/plan is read-only. For tests work, write
tests before production behavior; report observed red separately from green.
"""


class WorkerInterrupted(Exception):
    def __init__(self, signum):
        self.signum = signum


def checkout_root(workdir):
    for directory in (workdir, *workdir.parents):
        if (directory / '.git').exists():
            return directory
    return workdir


def stop_group(process):
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    try:
        process.wait(timeout=1)
    except subprocess.TimeoutExpired:
        pass
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    process.wait(timeout=2)


def run_worker(*, engine, launcher, role, workdir, prompt_file, output,
               timeout=180, model=None, max_turns=8, allow_nonrepo=False):
    if engine not in {'claude', 'codex'} or role not in {'plan', 'tests', 'build', 'review'}:
        raise ValueError('unknown worker or role')
    if not 0 < timeout <= 600 or not 1 <= max_turns <= 12:
        raise ValueError('wall timeout must be 0..600s; Claude turns 1..12')
    workdir, prompt_file, output = Path(workdir).resolve(), Path(prompt_file).resolve(), Path(output).resolve()
    if not workdir.is_dir():
        raise ValueError('worker workspace must already exist')
    prompt = prompt_file.read_text()
    if not prompt.strip() or len(prompt.encode()) > 128 * 1024:
        raise ValueError('provide a nonempty task packet of at most 128KiB')
    executable = shutil.which(str(launcher))
    if not executable:
        raise ValueError('selected launcher is not executable; do not substitute another profile')
    # Preserve the selected launcher path; resolving a profile symlink may
    # bypass a wrapper or change basename-dependent profile selection.
    executable = os.path.abspath(executable)
    output.mkdir(parents=True, exist_ok=False)
    read_only = role in {'review', 'plan'}
    command = [executable]
    if engine == 'claude':
        command += ['-p', '--output-format', 'json', '--max-turns', str(max_turns),
                    '--no-session-persistence', '--tools', 'Read,Glob,Grep' if read_only else 'Read,Glob,Grep,Edit,Write,Bash',
                    '--disallowedTools', 'mcp__*,Agent,Task,Skill,NotebookEdit',
                    '--strict-mcp-config', '--mcp-config', '{"mcpServers":{}}']
    else:
        command += ['exec', '--ignore-user-config', '--sandbox', 'read-only' if read_only else 'workspace-write',
                    '--ephemeral', '--json', '--color', 'never', '-o', str(output / 'final.txt')]
        if allow_nonrepo:
            command.append('--skip-git-repo-check')
    if model:
        command += ['--model', model]
    if engine == 'codex':
        command.append('-')
    packet = GUARD + '\nRole: ' + role + '\nTask packet:\n' + prompt
    result = {'engine': engine, 'selected_launcher': str(launcher), 'command': command,
              'role': role, 'workdir': str(workdir), 'prompt_sha256': hashlib.sha256(packet.encode()).hexdigest(),
              'requested_model': model,
              'timeout_seconds': timeout, 'claude_max_turns': max_turns if engine == 'claude' else None,
              'acceptance_verified': False, 'status': 'incomplete', 'exit_code': None}
    scope = checkout_root(workdir)
    result['lock_scope'] = str(scope)
    (output / 'prompt.txt').write_text(packet)
    lock_root = Path(tempfile.gettempdir()) / ('dev-flow-worker-locks-' + str(os.getuid()))
    lock_root.mkdir(mode=0o700, exist_ok=True)
    lock_name = hashlib.sha256(str(scope).encode()).hexdigest() + '.lock'
    started = time.monotonic()
    with (lock_root / lock_name).open('a') as lock:
        try:
            fcntl.flock(lock, (fcntl.LOCK_SH if read_only else fcntl.LOCK_EX) | fcntl.LOCK_NB)
        except BlockingIOError:
            result['status'] = 'busy'
        else:
            with (output / 'stdout.log').open('w') as stdout, (output / 'stderr.log').open('w') as stderr:
                process = None
                try:
                    process = subprocess.Popen(command, cwd=workdir, stdin=subprocess.PIPE,
                                               stdout=stdout, stderr=stderr, text=True, start_new_session=True,
                                               pass_fds=(lock.fileno(),))
                    worker = {'supervisor_pid': os.getpid(), 'worker_pid': process.pid,
                              'process_group': process.pid, 'launched_at_unix': time.time(),
                              'lock_scope': str(scope), 'workdir': str(workdir), 'command': command}
                    pending = output / 'worker.json.tmp'
                    pending.write_text(json.dumps(worker, indent=2) + '\n')
                    pending.replace(output / 'worker.json')
                    process.communicate(packet, timeout=timeout)
                except subprocess.TimeoutExpired:
                    result['status'] = 'timed_out'
                    stop_group(process)
                except OSError as exc:
                    result['status'], result['error'] = 'launch_error', type(exc).__name__ + ': ' + str(exc)
                except WorkerInterrupted as exc:
                    result['status'], result['signal'] = 'interrupted', exc.signum
                except BaseException:
                    if process is not None:
                        stop_group(process)
                    raise
                finally:
                    if process is not None:
                        # One-shot jobs cannot leave test servers or other
                        # descendants running after the CLI itself exits.
                        stop_group(process)
                        result['exit_code'] = process.poll()
            if result['status'] not in {'timed_out', 'launch_error', 'interrupted'}:
                if result['exit_code'] != 0:
                    result['status'] = 'worker_error'
                else:
                    try:
                        raw = (output / 'stdout.log').read_text()
                        if engine == 'claude':
                            data = json.loads(raw)
                            result['worker_identity'] = {'modelUsage': data.get('modelUsage'), 'session_id': data.get('session_id')}
                            result['permission_denials'] = data.get('permission_denials', [])
                            result['status'] = ('permission_denied' if result['permission_denials']
                                                else 'worker_error' if data.get('is_error') or data.get('subtype') != 'success'
                                                else 'completed' if data.get('result', '').strip() else 'incomplete')
                            if result['status'] == 'completed':
                                (output / 'final.txt').write_text(data['result'])
                        else:
                            events = [json.loads(line) for line in raw.splitlines() if line.strip()]
                            result['worker_identity'] = {'reported_models': sorted({e['model'] for e in events if isinstance(e.get('model'), str)})}
                            failed = any(e.get('type') in {'error', 'turn.failed'} for e in events)
                            final = output / 'final.txt'
                            completed = any(e.get('type') == 'turn.completed' for e in events) and final.is_file() and bool(final.read_text().strip())
                            result['status'] = 'worker_error' if failed else 'completed' if completed else 'incomplete'
                    except (ValueError, TypeError, AttributeError):
                        result['status'] = 'incomplete'
    result['elapsed_seconds'] = time.monotonic() - started
    (output / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--engine', required=True, choices=['claude', 'codex'])
    parser.add_argument('--launcher', required=True, help='approved profile launcher or Codex executable, one literal path/name')
    parser.add_argument('--role', required=True, choices=['plan', 'tests', 'build', 'review'])
    parser.add_argument('--workdir', type=Path, required=True)
    parser.add_argument('--prompt-file', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True, help='fresh artifact directory in approved scratch storage')
    parser.add_argument('--timeout', type=float, default=180)
    parser.add_argument('--max-turns', type=int, default=8)
    parser.add_argument('--model')
    parser.add_argument('--allow-nonrepo', action='store_true', help='explicitly permit a scratch Codex workspace without Git initialization')
    args = parser.parse_args()
    interrupted = False
    def interrupt(signum, frame):
        nonlocal interrupted
        if not interrupted:
            interrupted = True
            raise WorkerInterrupted(signum)

    signals = (signal.SIGTERM, signal.SIGHUP, signal.SIGINT)
    previous = {sig: signal.signal(sig, interrupt) for sig in signals}
    try:
        result = run_worker(**vars(args))
    except WorkerInterrupted as exc:
        return 128 + exc.signum
    except (ValueError, OSError) as exc:
        parser.error(str(exc))
    finally:
        for sig, handler in previous.items():
            signal.signal(sig, handler)
    print(json.dumps(result, indent=2))
    return 0 if result['status'] == 'completed' else 1


if __name__ == '__main__':
    raise SystemExit(main())
