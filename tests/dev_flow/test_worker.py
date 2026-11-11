"""Exercise worker dispatch with temporary CLIs, never hosted model calls."""

import importlib.util
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import threading
import time
import unittest


SCRIPT = Path(__file__).resolve().parents[2] / "skills/dev-flow/scripts/run_worker.py"
SPEC = importlib.util.spec_from_file_location("dev_flow_worker", SCRIPT)
WORKER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(WORKER)


class WorkerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="dev-flow-worker-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.workspace = self.root / "workspace"
        self.workspace.mkdir()
        self.prompt = self.root / "prompt.txt"
        self.prompt.write_text("Review contract. Literal input: $(touch unwanted); `uname`.\n")

    def executable(self, name, body):
        path = self.root / name
        path.write_text("#!" + sys.executable + "\n" + body)
        path.chmod(0o700)
        return str(path)

    def run_worker(self, executable, engine="claude", role="review", **kwargs):
        return WORKER.run_worker(engine=engine, launcher=executable, role=role,
                                 workdir=kwargs.pop('workdir', self.workspace), prompt_file=self.prompt,
                                 output=self.root / kwargs.pop("output", "result"),
                                 timeout=kwargs.pop("timeout", 10), **kwargs)

    def test_arbitrary_claude_profile_is_selected_literally_and_review_has_no_write_tools(self):
        body = "import sys,json\nprint(json.dumps({'type':'result','subtype':'success','is_error':False,'result':'No findings','args':sys.argv,'input':sys.stdin.read()}))\n"
        for index, name in enumerate(["claude-personal", "other Claude profile"]):
            with self.subTest(profile=name):
                launcher = self.executable(name, body)
                result = self.run_worker(launcher, output="result" + str(index))
                self.assertEqual(result['status'], 'completed')
                self.assertFalse(result['acceptance_verified'])
                raw = json.loads((self.root / ("result" + str(index)) / "stdout.log").read_text())
                self.assertEqual(raw['args'][0], launcher)
                self.assertEqual(raw['args'][raw['args'].index('--tools') + 1], 'Read,Glob,Grep')
                self.assertIn('$(touch unwanted)', raw['input'])
                self.assertFalse((self.workspace / 'unwanted').exists())

    def test_codex_uses_read_only_and_requires_final_output(self):
        launcher = self.executable('fake-codex', "import sys,json,pathlib\np=pathlib.Path(sys.argv[sys.argv.index('-o')+1]);p.write_text('No findings')\nprint(json.dumps({'type':'turn.completed'}))\n")
        result = self.run_worker(launcher, engine='codex', allow_nonrepo=True)
        self.assertEqual(result['status'], 'completed')
        command = result['command']
        self.assertEqual(command[command.index('--sandbox') + 1], 'read-only')
        self.assertNotIn('--dangerously-bypass-approvals-and-sandbox', command)
        self.assertIn('--skip-git-repo-check', command)
        self.assertIn('--ignore-user-config', command)

    def test_zero_exit_with_claude_budget_error_is_not_completion(self):
        launcher = self.executable('limited', "print('{\"type\":\"result\",\"subtype\":\"error_max_turns\",\"is_error\":true}')\n")
        result = self.run_worker(launcher)
        self.assertEqual(result['status'], 'worker_error')

    def test_permission_denials_never_count_as_completion(self):
        launcher = self.executable('denied', "import json\nprint(json.dumps({'type':'result','subtype':'success','result':'Could not write','permission_denials':[{'tool_name':'Write'}]}))\n")
        result = self.run_worker(launcher, role='tests')
        self.assertEqual(result['status'], 'permission_denied')
        self.assertEqual(result['permission_denials'], [{'tool_name': 'Write'}])

    def test_missing_final_output_is_incomplete_and_auth_failure_preserves_exit(self):
        launcher = self.executable('empty', 'pass\n')
        self.assertEqual(self.run_worker(launcher)['status'], 'incomplete')
        failed = self.executable('auth-failed', 'import sys\nsys.exit(2)\n')
        result = self.run_worker(failed, output='failed')
        self.assertEqual(result['status'], 'worker_error')
        self.assertEqual(result['exit_code'], 2)

    def test_timeout_stops_the_owned_worker_and_child(self):
        launcher = self.executable('slow', "import subprocess,sys,time\np=subprocess.Popen([sys.executable,'-c','import time;time.sleep(60)'])\nprint(p.pid,flush=True)\ntime.sleep(60)\n")
        started = time.monotonic()
        result = self.run_worker(launcher, timeout=2)
        self.assertEqual(result['status'], 'timed_out')
        self.assertLess(time.monotonic() - started, 6)
        child = int((self.root / 'result/stdout.log').read_text().strip())
        process = subprocess.run(['ps', '-o', 'stat=', '-p', str(child)], capture_output=True, text=True)
        self.assertNotIn('not permitted', process.stderr.lower())
        self.assertTrue(process.returncode != 0 or process.stdout.strip().startswith('Z'))

    def test_success_also_stops_owned_background_children(self):
        pidfile = self.root / 'child.pid'
        body = ("import subprocess,sys,pathlib,json\n"
                "p=subprocess.Popen([sys.executable,'-c','import time;time.sleep(60)'])\n"
                "pathlib.Path(" + repr(str(pidfile)) + ").write_text(str(p.pid))\n"
                "print(json.dumps({'type':'result','subtype':'success','result':'done'}))\n")
        launcher = self.executable('background-child', body)
        result = self.run_worker(launcher)
        child = int(pidfile.read_text())
        def cleanup():
            try:
                os.kill(child, signal.SIGTERM)
            except ProcessLookupError:
                pass
        self.addCleanup(cleanup)
        self.assertEqual(result['status'], 'completed')
        process = subprocess.run(['ps', '-o', 'stat=', '-p', str(child)], capture_output=True, text=True)
        self.assertNotIn('not permitted', process.stderr.lower())
        self.assertTrue(process.returncode != 0 or process.stdout.strip().startswith('Z'))

    def test_overlapping_writers_are_rejected_without_a_second_launch(self):
        launcher = self.executable('busy', "import time\ntime.sleep(1)\nprint('{\"type\":\"result\",\"subtype\":\"success\",\"result\":\"done\"}')\n")
        running = threading.Thread(target=lambda: self.run_worker(launcher, role='build', output='first'))
        running.start()
        self.addCleanup(running.join)
        deadline = time.monotonic() + 2
        while not (self.root / 'first/stdout.log').exists() and time.monotonic() < deadline:
            time.sleep(0.01)
        result = self.run_worker(launcher, role='build', output='second')
        self.assertEqual(result['status'], 'busy')
        running.join()

    def test_writer_lock_covers_subdirectories_of_the_same_checkout(self):
        (self.workspace / '.git').write_text('gitdir: fixture-only-marker\n')
        sub = self.workspace / 'package'
        sub.mkdir()
        launcher = self.executable('nested-busy', "import time\ntime.sleep(2)\nprint('{\"type\":\"result\",\"subtype\":\"success\",\"result\":\"done\"}')\n")
        running = threading.Thread(target=lambda: self.run_worker(launcher, role='build', output='first'))
        running.start()
        self.addCleanup(running.join)
        deadline = time.monotonic() + 3
        while not (self.root / 'first/stdout.log').exists() and time.monotonic() < deadline:
            time.sleep(0.01)
        result = self.run_worker(launcher, role='tests', workdir=sub, output='nested')
        self.assertEqual(result['status'], 'busy')
        running.join()

    def start_outer_worker(self):
        pidfile = self.root / 'worker.pid'
        launcher = self.executable('supervised-child', "import pathlib,os,time\npathlib.Path(" + repr(str(pidfile)) + ").write_text(str(os.getpid()))\ntime.sleep(60)\n")
        process = subprocess.Popen([sys.executable, '-B', str(SCRIPT), '--engine', 'claude',
                                    '--launcher', launcher, '--role', 'build', '--workdir', str(self.workspace),
                                    '--prompt-file', str(self.prompt), '--output', str(self.root / 'outer'), '--timeout', '30'],
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
        def cleanup_outer():
            if process.poll() is None:
                process.kill()
            process.wait(timeout=3)
        self.addCleanup(cleanup_outer)
        deadline = time.monotonic() + 5
        while not pidfile.exists() and time.monotonic() < deadline:
            time.sleep(0.01)
        self.assertTrue(pidfile.exists(), 'worker did not start')
        child = int(pidfile.read_text())
        def cleanup_child():
            try:
                os.killpg(child, signal.SIGKILL)
            except ProcessLookupError:
                pass
        self.addCleanup(cleanup_child)
        return process, child

    def test_sigterm_of_supervisor_stops_worker_and_records_interruption(self):
        process, child = self.start_outer_worker()
        process.terminate()
        process.wait(timeout=5)
        status = subprocess.run(['ps', '-o', 'stat=', '-p', str(child)], capture_output=True, text=True)
        self.assertNotIn('not permitted', status.stderr.lower())
        self.assertTrue(status.returncode != 0 or status.stdout.strip().startswith('Z'))
        result = json.loads((self.root / 'outer/result.json').read_text())
        self.assertEqual(result['status'], 'interrupted')

    def test_sigkill_of_supervisor_does_not_unlock_a_live_writer(self):
        process, _ = self.start_outer_worker()
        record = self.root / 'outer/worker.json'
        deadline = time.monotonic() + 2
        while not record.exists() and time.monotonic() < deadline:
            time.sleep(0.01)
        metadata = json.loads(record.read_text())
        self.assertEqual(metadata['worker_pid'], metadata['process_group'])
        self.assertEqual(metadata['supervisor_pid'], process.pid)
        self.assertEqual(metadata['lock_scope'], str(self.workspace))
        process.kill()
        process.wait(timeout=3)
        launcher = self.executable('should-not-launch', "raise RuntimeError('must remain locked')\n")
        result = self.run_worker(launcher, role='build', output='after-kill')
        self.assertEqual(result['status'], 'busy')

    def test_repeated_termination_does_not_interrupt_cleanup(self):
        pidfile = self.root / 'resistant.pid'
        launcher = self.executable('resistant-child', "import pathlib,os,signal,time\nsignal.signal(signal.SIGTERM,signal.SIG_IGN)\npathlib.Path(" + repr(str(pidfile)) + ").write_text(str(os.getpid()))\ntime.sleep(60)\n")
        process = subprocess.Popen([sys.executable, '-B', str(SCRIPT), '--engine', 'claude',
            '--launcher', launcher, '--role', 'build', '--workdir', str(self.workspace),
            '--prompt-file', str(self.prompt), '--output', str(self.root / 'repeated'), '--timeout', '10'],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
        def cleanup():
            if process.poll() is None:
                process.kill()
            process.wait(timeout=3)
            if pidfile.exists():
                try:
                    os.killpg(int(pidfile.read_text()), signal.SIGKILL)
                except ProcessLookupError:
                    pass
        self.addCleanup(cleanup)
        deadline = time.monotonic() + 5
        while not pidfile.exists() and time.monotonic() < deadline:
            time.sleep(0.01)
        self.assertTrue(pidfile.exists())
        process.terminate()
        time.sleep(0.1)
        process.send_signal(signal.SIGHUP)
        process.wait(timeout=5)
        child = int(pidfile.read_text())
        status = subprocess.run(['ps', '-o', 'stat=', '-p', str(child)], capture_output=True, text=True)
        self.assertNotIn('not permitted', status.stderr.lower())
        self.assertTrue(status.returncode != 0 or status.stdout.strip().startswith('Z'))
        self.assertEqual(json.loads((self.root / 'repeated/result.json').read_text())['status'], 'interrupted')

    def test_output_reuse_and_invalid_roles_do_not_launch(self):
        launcher = self.executable('unused', "raise RuntimeError('must not run')\n")
        (self.root / 'result').mkdir()
        with self.assertRaises(FileExistsError):
            self.run_worker(launcher)
        with self.assertRaises(ValueError):
            self.run_worker(launcher, role='admin', output='invalid')
        self.assertFalse((self.root / 'invalid').exists())


if __name__ == '__main__':
    unittest.main()
