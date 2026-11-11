# Evidence and workflow learning

Use this reference when framing acceptance checks, recording verification,
refreshing a review, closing a task or considering a review-topology change.
Keep durable records on the bead; large logs belong in the repo's approved
scratch location. Use [tmp-docs.md](tmp-docs.md) for categorized local working
documents and their lifecycle. These formats are examples, not additional
tracking files; TMP documents supplement the bead's resumable state.

## Start, resume and handoff

Reload current repo instructions, contract and Beads bootstrap/preferences at
session start or after compaction. Confirm the Beads workspace with `bd where`
and inspect the actual checkout using `git rev-parse --show-toplevel`,
`git status --short --branch` and `git worktree list`. Read the requested bead
even if it is not in `bd ready --json`; inspect relevant in-progress work before
creating a duplicate. Confirm the current claim and writer before editing.
Unclear or conflicting ownership needs a handoff decision, not a forced claim.
For a mapped ticket, also apply [ticket-mapping.md](ticket-mapping.md): refresh
the authoritative external scope, acceptance and observed revision, reuse the
canonical pair and record pending reconciliation or conflicts before dependent
work. Include both identities and local/remote delivery states in handoffs.

Reuse an existing task worktree/branch when appropriate. Compare the bead's
stage, HEAD/diff and evidence to current files, base and environment; files may
have changed since the last session. Resume at the first exit condition that
still lacks evidence. Revalidate affected claims under the revision rules
below; do not rerun unrelated suites or recreate/reset work just because the
chat context changed. Missing worktrees or mismatched records require inspection
of surviving branches/files before any recreation. Preserve all unrelated work.

Before ending a session or handing off, put a concise record on the bead:

```text
Task/stage and requested endpoint: <current state; first unmet exit condition>
Location: <repo/tracker, worktree, branch, HEAD/diff identity>
Evidence: <checks/review actually complete; failed, stale or missing evidence>
Authority/decision needed: <only unresolved scope, ownership or permission>
Retained resources: <files, worktree, checkpoints, task-owned processes or none>
Next action: <concrete command or decision, with prerequisites/unblock condition>
```

Keep the record proportional to the task; link existing evidence rather than
copying it. Chat compaction alone does not complete, pause or reassign a task.
Do not close unfinished work merely to produce a tidy handoff.

## Baseline and existing failures

Before edits in the actual task workspace, establish the smallest relevant
baseline or reuse observed evidence for matching inputs, tools and environment.
A targeted check may be enough; there is no requirement to run the whole suite
at every start/resume.
Record the tested state, command and result, including unavailable prerequisites.

When a final check fails, compare its actual failure with the baseline. Label
new regressions, demonstrated pre-existing failures and uncertain attribution
separately. Do not call a failure pre-existing without evidence, silently skip
it, weaken the gate or fix unrelated behavior under the current task.
Required failing/unrun gates still prevent verified completion unless an
explicit repo/user decision changes the requirement; record that decision and
remaining limitation. Continue useful authorized investigation and link any
out-of-scope repair.

## Acceptance and observed evidence

At Frame/Plan, record the outcome, non-goals and constraints, then map each
acceptance criterion to a check. A fast task can use one concise entry. Name
unknown commands or missing environments; do not invent them or infer success.

At Verify, fill in observed results separately from the planned check:

```text
Criterion: <observable required behaviour>
Planned check: <command or interaction, expected result>
Observed: <actual command/procedure and result, or not run + reason>
State: demonstrated | failed | unverified
Evidence: <tested revision/diff identity, environment, log/artifact reference>
Gap/next action: <remaining uncertainty, or none>
```

Verify from the user-visible outcome backwards through its implementation,
callers and data source when applicable. Static wiring checks can support the
claim, but an import or query's presence does not prove runtime behaviour.
Exercise the real path where practical; distinguish mocked checks, live checks
and any human judgment still needed. Use tests proportional to the change.

Failed or unverified mandatory criteria keep the task open. A follow-up bead
records work; it does not turn missing evidence into acceptance. If the user
explicitly changes scope or accepts a limitation, record the decision and
updated criterion without rewriting historical failures as successes.

## Revision and review coverage

Record the worktree, branch, `git rev-parse HEAD`, integration base, relevant
environment versions/configuration, and the commands/procedures actually run.
For an uncommitted tree, HEAD alone is insufficient: retain a reproducible
patch or content fingerprint covering staged, unstaged and relevant untracked
files. Use approved scratch storage for bulky evidence and exclude credentials
or sensitive configuration values. Record test-data and tool/model identity
when they affect the claim.

Give each reviewer that identity, the complete task diff including relevant
new files, and the acceptance/evidence map. The reviewer marks each criterion
supported, contradicted or unconfirmed before applying its assigned roles.
An unconfirmed criterion needs an appropriate check, not an invented defect.

After a fix, rebase, hook autofix, dependency/config change or integration:

- Compare the reviewed/tested state with the resulting state. Relevant changes
  make affected evidence stale; a changed commit hash alone does not prove a
  behavioural change. Explain evidence carried forward across identical content.
- Rerun affected checks and all repo-required final gates on the final content.
  Recheck findings and review newly changed behaviour outside prior coverage.
- Append the new identity and results to the bead. Preserve earlier attempts
  as history. For a content-identical commit, link the tested diff to its commit.

Report exactly what was tested, reviewed, skipped and integrated. Do not
describe an untested integration result as verified.

## Debugging without speculative fixes

For defects and unexplained failures, start in Diagnose under
[task-intake.md](task-intake.md) before planning a repair. These records also
apply when a new failure sends an in-progress task back to that phase.

Record the reproduction and baseline, the current hypothesis and why the
evidence supports it, the smallest discriminating probe/change, and its result.
If the original symptom cannot be reproduced, gather evidence and state that
limit. A passing suite alone does not establish that the reported bug is fixed.

When attempts stop producing new evidence, revisit assumptions, trace another
boundary or revise the plan instead of layering guesses. There is no universal
attempt count. Continue useful authorized investigation; ask for a human
decision only when new scope, access or a tradeoff requires it.

## Material lessons at Close

Record only events that affected correctness, scope, verification confidence,
repeated effort or human intervention. Include evidence of what happened,
impact, the safeguard that worked or failed, one primary improvement owner,
and a way to validate the proposed improvement. A short entry is enough;
record no material lesson when there was none.

Choose the smallest owner: repo guide/contract for local commands or rules,
this skill for reusable procedure, a reference for conditional detail, a
validator for mechanical conditions, or a regression test for a reproducible
defect. Link future work with `discovered-from:<bead-id>`. Recording a lesson
does not authorize edits to other repos, skills or external systems.

Record lessons, follow-ups and handoff evidence before closing. Check the
requested endpoint: a verified implementation may be ready for an authorized
integration/release handoff, but if integration or release is itself required,
it remains unfinished until that outcome is demonstrated. Mark inapplicable
stages explicitly rather than inventing release work for a local task.

Before removing a worktree, verify integration and inspect tracked/untracked
changes, ignored data and task-owned processes that use the directory. A clean
short status alone does not establish there is no ignored data. Retain the
worktree if cleanup could destroy work or resources still needed; record its
path and reason. Do not force-remove directories, discard checkpoints, delete
branches that are the only copy of pending work, or stop shared services for
cleanup. Explicit retention can accompany a completed task unless cleanup is
an acceptance requirement; unmet required cleanup keeps the task open.

## Optional review-topology comparison

Use this protocol when evaluating whether another planner, reviewer, model or
pass earns its overhead. Capture available observations from normal authorized
tasks; launching experiments or additional agents needs the relevant authority.
This protocol changes no required review coverage or model preferences.

- Compare tasks with similar lane, risk, scope and verification needs. Record
  builder/reviewer models, harness versions, assigned roles and actual passes.
  Change one topology choice at a time where feasible; note confounding changes.
- Record elapsed delivery time separately from human effort/interventions,
  review time and repair rounds. Do not add parallel agent durations and call
  the sum elapsed time. Include setup, verification and integration overhead.
- Track findings confirmed, rejected or deferred, regressions/reopened work
  and missed acceptance criteria. Finding count alone is not a quality score.
  Missing follow-up observation is unknown, not zero regressions.
- Record actual tokens and cost only when available; local inference cost is
  not assumed to be zero. Mark missing measurements rather than estimating
  them as observations. Keep results on the relevant beads.
- State sample size and limitations. A planted-bug test, one successful run
  or faster generation does not establish delivery-quality or throughput gains.
  Propose retaining, simplifying or expanding the topology from the evidence;
  preserve required coverage until a change is authorized.

Research provenance: transferable ideas came from
[Superpowers debugging](https://github.com/obra/superpowers/blob/main/skills/systematic-debugging/SKILL.md),
[GSD outcome verification](https://github.com/gsd-build/get-shit-done/blob/main/agents/gsd-verifier.md),
[Anthropic's harness experiments](https://www.anthropic.com/research/harness-design-long-running-apps)
and [OpenAI's workflow iteration recipe](https://developers.openai.com/cookbook/examples/codex/iterating-development-workflows-with-codex).
These motivate the procedure; they do not validate this skill's results.
