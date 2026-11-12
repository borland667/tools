# Bounded CLI worker launcher

`scripts/run_worker.py` inside this skill runs one Claude Code or Codex CLI job.
It requires Python 3.9+ on a POSIX host (`fcntl` and process groups), plus the
selected CLI/profile executable. It installs nothing and never uses a shell to
interpolate a task packet. A different platform needs a qualified launcher.

From the tools checkout, examples are:

```bash
python3 -B skills/dev-flow/scripts/run_worker.py \
  --engine claude --launcher <approved-claude-profile> --role tests \
  --workdir <task-worktree> --prompt-file <task-packet.txt> \
  --output <new-private-artifact-directory> --timeout 180

python3 -B skills/dev-flow/scripts/run_worker.py \
  --engine codex --launcher codex --role review \
  --workdir <task-worktree> --prompt-file <review-packet.txt> \
  --output <another-new-artifact-directory> --timeout 180
```

`--allowed-tools` scopes Claude permission rules per packet so bounded writer
jobs are not auto-denied in headless mode. For example:
`--allowed-tools 'Edit(<worktree>/**),Bash(make verify-fast),Bash(python3 -m pytest:*)'`.
It is a scoped allow-list, not a permission bypass, and has no effect on read-only
roles or on Codex jobs.

The Hermes coordinator resolves this script through its linked skill, for
example `$HERMES_HOME/skills/dev-flow/scripts/run_worker.py`. The caller supplies
the approved launcher explicitly; personal, work, local or another authorized
profile executable are choices, not built-in defaults.
Optional `--model` overrides only the selected job. Record
their provider/account implications; the wrapper does not authenticate or infer
that a profile is hosted merely from its name. Codex jobs use
`--ignore-user-config` to avoid inheriting unrelated MCP/plugin configuration;
authentication still comes from the selected launcher's Codex home. Supply any
required model choice explicitly. System/project rules are not bypassed.
For an explicitly approved scratch fixture outside Git, `--allow-nonrepo`
passes Codex's `--skip-git-repo-check`; it never initializes a repository.

Roles are `plan`, `tests`, `build`, `review`. Read-only roles give Claude only
Read/Glob/Grep tools, disable MCP tools, and select Codex's read-only sandbox.
Writing roles permit Claude file/shell tools or Codex workspace-write. Claude
permissions, installed hooks and the selected profile still apply; tool lists
are application restrictions, not an OS sandbox. No bypass/trust flags are used.
Do not widen permissions when a job cannot run unattended; record the gap.

The packet must be nonempty and at most 128 KiB. The wall budget is positive
and at most 600 seconds (default 180); Claude also has 1–12 turns (default 8).
The coordinator splits larger tasks into recorded jobs. An input-size limit is
not proof that the selected model's context fits. No retries happen automatically.

Artifacts require a fresh directory in approved private scratch storage:
`prompt.txt`, `worker.json` after launch, `stdout.log`, `stderr.log`, `final.txt` when available, and
`result.json`. They can contain project source, so keep them outside distributed
files and audit before sharing. Environment credentials are not written to the
report. Prompt hashes, launcher/command, role, wall budget, elapsed time, CLI exit
and available model/session metadata identify what actually ran.

`completed` means a valid CLI completion with a nonempty result, never task
acceptance: `acceptance_verified` remains false. Zero-exit budget errors,
missing final output, malformed results, nonzero/auth errors, timeout and lock
contention remain explicit statuses. Nonempty Claude `permission_denials` yields
`permission_denied`, even when the CLI otherwise reports success. A caught
termination signal yields `interrupted`. The CLI exits 0 only for `completed`, 1 for
other reported statuses, and 2 for invalid input/setup. Required test outcomes,
review coverage and permission to integrate are checked separately.

The wrapper starts an owned process group and stops its descendants on timeout,
SIGTERM/SIGHUP/SIGINT and normal completion. A worker must not intentionally
daemonize outside that group. Shared services are not stopped. The lock covers
the nearest ancestor with a `.git` marker (including worktree marker files),
or the resolved workspace when no marker exists. It permits concurrent readers
and one exclusive writer, including jobs started from checkout subdirectories.
It only coordinates this wrapper, not other terminals/agents.
Nested repositories/submodules have separate locks. Never dispatch overlapping
jobs in a parent folder and its nested checkout, or in a non-repository parent
and a contained repository; these boundaries require coordinator supervision.

The worker inherits the lock descriptor so an uncatchable supervisor SIGKILL
does not immediately unlock a live writer. SIGKILL cannot trigger cleanup or
produce a result report; the worker may survive past its intended deadline.
Trusted profile wrappers must preserve the inherited descriptor. If a wrapper
closes it or a worker escapes its process group, host containment is required.
Treat supervisor death as unresolved: stop the task-owned worker, inspect the
workspace and reconcile evidence before another dispatch. Use the workflow's
one-writer rule for the whole task.
`worker.json` is written atomically immediately after launch and records the
worker PID/process group, supervisor PID, launch time, workspace and command.
Before stopping a survivor, compare this record with the live process identity
and start time; a stale PID may belong to another task. Never kill solely by a
recorded PID. Death during the launch-to-record window needs host process
inspection. Signals caught while a worker is active produce `interrupted`;
signals during setup/reporting may exit without a complete result. Repeated
caught signals cannot interrupt cleanup, but SIGKILL remains uncatchable.

Offline validation from the tools repo:

```bash
python3 -B -m unittest discover -s tests/dev_flow -v
```

The worker tests use temporary fake CLIs and process inspection; no provider
credentials, live model calls or Git commands are needed. Restricted sandboxes
must permit the process fixtures/inspection. They do not qualify installed
Claude/Codex permissions, authentication, actual model independence or a live
Hermes delegation. Record those probes separately under
[hermes-coordinator.md](hermes-coordinator.md).
