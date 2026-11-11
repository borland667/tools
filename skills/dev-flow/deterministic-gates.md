# Deterministic hooks and gates

Use when adding, strengthening or installing checks that run on each applicable
change. Gates can run on edit/save, pre-commit, commit-msg, pre-push, CI or a
manual verification command. Choose triggers for the repo's workflow; a gate
need not run on every keystroke or apply to every file type.

## Choose and register a check

- Inspect existing hook runners, configuration, scripts, CI and local hook-path
  settings. Extend the current mechanism; preserve existing hooks and their
  checks. Avoid competing runners or silently replacing a hook path. Keep
  installation local to the intended repo; account for Git configuration shared
  between worktrees and leave global settings alone.
- Prefer a check for a current requirement or reproducible recurring defect:
  formatting, lint, types, schema/codegen consistency, dependency or architecture
  rules, secrets patterns, or focused tests. Keep contextual judgment in review.
  Do not create a new gate for every task or speculative future requirement.
- A deterministic gate returns a reproducible verdict for defined inputs,
  configuration and tool versions. Avoid live model calls, nondeterministic
  external services and implicit dependency downloads during the check.
  Install prerequisites separately using the repo's setup process.
- Record command/config, trigger, input scope, prerequisites, expected duration,
  diagnostic output and blocking/advisory policy in existing config or the repo
  contract. Give blocking checks meaningful nonzero exits on violations and
  unavailable prerequisites. An advisory check is not proof a required gate passed.
- Put check logic in repo-owned commands/config that local hooks, manual
  verification and CI can reuse. Trigger wrappers may select different scopes;
  document those differences. CI should enforce required checks independently
  of whether a developer has installed local hooks.

## Inputs, cost and preservation

For new APIs and substantive behavior, use [test-first.md](test-first.md) to
establish initial case coverage and observed red before production behavior.
Required test gates must pass at delivery: red preparation evidence never waives
a hook or CI check. Configure the runner to detect missing required test groups,
zero collection and unexpected skips; code coverage alone does not prove the
contract or its edge cases. Record required integration prerequisites explicitly.

Pre-commit checks must validate the staged snapshot, including staged additions,
renames and deletions, rather than assuming the working tree matches the index.
Partially staged files can hide violations or create false failures if a check
reads unstaged content. Use a runner that isolates staged inputs or an equivalent
tested approach; do not implement destructive stash/restore logic casually.
Commit-message checks consume the message supplied by their actual hook event.

Keep interactive and commit checks small and offline. Move slow checks to a
later appropriate tier while retaining required fast protection. Changed-file
selection must include affected dependents; changes to shared config, schemas,
lockfiles or gate code may require broader checks. Skipping an inapplicable file
type is different from silently skipping a required check.

Autofixes must preserve unrelated and unstaged edits. Inspect their diff and
re-stage only intended hunks; never use blanket staging to get a commit through.
Run checks on the final staged content. Shared commands and temp resources must
also work safely in parallel worktrees without fixed ports or shared mutable
test data. A local hook does not require a push to validate it.

## Prove the gate works

Use an isolated fixture or temporary repo for gate validation, not planted
violations in the user's checkout. Reuse existing gate tests when available.

1. Show representative valid input passes and an intentional violation fails,
   with a useful diagnostic and the expected exit status. Include relevant
   selection edges, such as partial staging or shared-config changes.
2. Exercise the real registration path: install the repo's hook entrypoint in
   the temporary repo and trigger the relevant Git event. A direct runner call
   can validate checks, but alone does not prove Git will invoke them. For CI,
   validate the job configuration and run it when available; a local script run
   does not establish a remote CI result. Cover each trigger changed by the task.
3. Verify unrelated working-tree and staged content survives both pass and fail
   paths, including autofix when supported. Check that existing hooks still run.
4. Record tested revision, commands, observed outcomes, setup/install state and
   timing on the bead. Distinguish checked-in configuration, local installation,
   trigger execution and remote enforcement. Report unavailable checks explicitly.

Wire and install repo-local hooks when that is part of the authorized task;
document a reproducible setup command for other checkouts. If an existing hook
conflicts or broader settings need changing, preserve them and resolve the scope
before replacing anything. Follow normal autonomy and integration rules. Do not
bypass a required gate to complete a task, and do not weaken a check merely to
make its current failure disappear; investigate the input, environment or rule.
