# Hermes coordinator with Claude Code and Codex

Use when the user selects Hermes to coordinate the dev-flow. Hermes owns task
framing, dispatch, evidence collection and the next-stage decision; it does not
become the production-code writer or override test/review gates. Claude Code
and Codex remain separate CLI workers using their own selected authentication.
Hermes' `delegate_task` creates Hermes children, not Claude Code/Codex workers.

## Task binding

Record these on the bead before dispatch: workspace, acceptance criteria,
test-first stage, allowed writes, verification commands, worker roles/models,
Claude launcher/profile, optional Codex profile, limits and artifact location.
Choose the Claude launcher for each task from the user's approved profiles.
There is no hardcoded personal/work/default profile. Accept another executable
profile wrapper when authorized; shell aliases must be made available as an
executable wrapper. Never substitute a profile after login or quota failure.

A profile label is not proof of account, endpoint or model independence.
Resolve those from approved host bindings and the actual worker report. A
local Claude-compatible profile remains local. Unknown model/provider identity
does not satisfy required independent hosted review. Running the same model
through Hermes and another harness does not create independence.

## Dispatch and checkpoints

1. Hermes frames/claims the bead and provides the worker a complete packet:
   contract, initial edge-case matrix, exact file/diff identity, scoped writes,
   expected results, repo rules and available check commands. Preserve the
   [test-first checkpoints](test-first.md).
2. Delegate `tests` before production behavior. Confirm executable red evidence
   for the intended missing behavior, then dispatch a bounded `build` job.
3. Run the repo's agreed deterministic checks and retain actual exit/output
   evidence. A worker's statement that tests passed is insufficient. Do not
   execute commands merely because a worker suggested them.
4. Once the writer finishes, give Codex or another authorized independent
   reviewer the actual resulting change and evidence. `review` and `plan` jobs
   are read-only; `tests` and `build` are writers. Normal hosted/deep/security
   review requirements still apply, including a different model where required.
5. Hermes checks findings against source/contract, requests a bounded fix when
   justified, reruns affected gates, and records coverage and remaining gaps.
   Integration/release still requires its own authority.

Use [tmp-docs.md](tmp-docs.md) for substantial plans, analysis and review
evidence. The coordinator maintains the bead links and summaries; each worker
gets a separate authorized artifact location. TMP reports do not create a
second task ledger or replace observed gate results.

Use [scripts/run_worker.py](scripts/run_worker.py), documented in
[worker-launcher.md](worker-launcher.md), for one-shot CLI jobs. It selects the
literal launcher, imposes a wall deadline, records artifacts and excludes
overlapping writers/readers during a writing job. All writers in a checkout
must use that protocol; other processes do not honor its advisory lock.

Each job has a finite budget; the coordinator's initial dispatch budget is at
most three worker jobs per task segment, then reassess or hand off. No automatic
retry, profile switch, permission bypass, recursion or untracked background
work. Rechecks are separately recorded jobs. Hermes' turn cap is a separate
runtime limit; the job-count policy is procedural, not an OS enforcement rule.

## Dedicated Hermes profile

Use a dedicated Hermes profile, with its `skills/dev-flow` symlink pointing at
this canonical folder and its `SOUL.md` linked to
[assets/hermes-coordinator.md](assets/hermes-coordinator.md). Keep actual model,
endpoint and profile paths in ignored `local.md`, not these portable files.
The profile is a host binding, not a second copy of the workflow.
Its `config.yaml` links to ignored `local.hermes.yaml` in this folder; keep
private runtime settings there and exclude them from exports. A minimal local
profile uses this shape, filled from approved host bindings:

```yaml
model:
  default: <approved-local-model-id>
  provider: custom
  base_url: <approved-loopback-endpoint>
  api_key: sk-local  # placeholder for an unauthenticated local service only
agent:
  max_turns: 12
  run_budget_seconds: 600
platform_toolsets:
  cli: [terminal, clarify]
auth:
  adopt_external_logins: false
memory:
  memory_enabled: false
  user_profile_enabled: false
auxiliary:
  background_review:
    enabled: false
curator:
  enabled: false
mcp_servers: {}
```

This config does not enforce the full workflow itself. The task packet, worker
permissions, actual gate runs and supervisor review provide the other checks.

Enable only `terminal` and `clarify` for this coordinator. Disable automatic
memory/skill reviews, curator and both built-in memory stores; Beads owns task
state. Do not clone another profile, import credentials, enable `codex-runtime`
configuration migration, or auto-approve trust/permission prompts. The terminal
can execute commands and is not an OS sandbox: use the worker permission modes
and the host's containment rules rather than claiming prompt-only isolation.

Launch from the authorized task workspace using the chosen profile. The native
run budget and turn cap bound a run separately from each worker's wall deadline:

```bash
hermes -p <coordinator-profile> --in <task-workspace> chat --skills dev-flow
```

Set the run budget in profile config: gateway-backed CLI routes may reject the
otherwise documented `--run-budget` flag. Confirm installed CLI syntax and profile loading before a live task. Preserve
provider/account settings outside the dedicated profile. If a prerequisite,
login or sandbox is unavailable, report the job as not run/incomplete; do not
fall back to `--yolo`, full-access sandboxes or a different account.

Sources: [Hermes profiles](https://github.com/NousResearch/hermes-agent/blob/main/website/docs/user-guide/profiles.md),
[Hermes delegation](https://github.com/NousResearch/hermes-agent/blob/main/website/docs/guides/delegation-patterns.md),
[Codex non-interactive mode](https://learn.chatgpt.com/docs/non-interactive-mode),
[Claude Code CLI](https://code.claude.com/docs/en/cli-reference).
