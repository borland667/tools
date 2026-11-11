# Review agents

Read-only agents that review a change before it is integrated. They run on
this machine, before any PR or push, and are separate from review bots that
run on a hosted PR.

## Rules for every review agent

- Read-only with respect to project files and Git: no edits, staging, commits
  or mutating commands. Read-only checks/probes must preserve project state.
- It reviews one bead's change against that bead's acceptance criteria.
- Reporting findings on the assigned bead is the sole permitted write when
  granted to the reviewer. Otherwise it returns findings to the lead, who
  records them on the bead. It never posts to a PR, external ticket or external
  chat, changes issue status/ownership, or performs other mutations.
- The lead agent confirms each finding by reading the code before acting on
  it. A finding the lead cannot reproduce is rejected with that reason.
- Findings from a local model are advisory until confirmed.

## Discipline

A finding is reported only when all three hold:

1. The symptom is real in the new code.
2. It will fail, or it breaks a rule that can be quoted from the repo.
3. This change introduced it.

Otherwise it is a question, or it is dropped.

- **Check the callers.** When severity depends on how code is called, list
  the callers and grade by what actually triggers: a reachable path with a
  user-visible symptom is a blocker; a rare path is should-fix; no caller is
  a note.
- **Do not flag:** pre-existing issues the change does not touch, anything a
  linter or formatter owns, renames by taste, suppressions that carry a
  reason, or a vague "needs more tests" with no named case.
- **One issue per finding.** Group repeated locations under it.
- **Mechanical before judgment.** Anything a script can decide (secret
  patterns, commit message rules, a repo's scan recipes) is run as a script
  and its hits triaged. A model does not eyeball what a scan can count.

## Roles

A role is a lens, not a separate agent. One agent pass can carry several.

### Always on

| Role | Looks for |
|---|---|
| `correctness` | Wrong results; no-ops and dead branches; missing returns; unhandled cases; broken callers; state not carried through a copy or transition; cleanup missing on the error or retry path; regression of behaviour fixed before; acceptance criteria not met |
| `tests` | Changed behaviour with no test that would fail if the bug came back; tests asserting the wrong scenario; deleted or skipped tests without a reason; tests that cannot run in parallel or depend on shared state |
| `fit` | Diff larger than the task; scope drift; dead code; a duplicated helper; repo conventions broken; docs, README or env docs not updated in the same change; commit and branch hygiene |

### Triggered by the diff

| Role | Trigger | Looks for |
|---|---|---|
| `concurrency` | Background jobs, queues, caches, locks, retries, timeouts, transactions, shutdown paths | Races and check-then-act gaps; non-idempotent retries; missing timeouts; multi-step writes without a transaction; stale or asymmetric cache behaviour; failures cached as values; work lost on shutdown |
| `data` | Queries, ORM code, migrations, schema, backfills, list endpoints | Per-row queries or cache reads where a batch exists; unbounded results; locking migrations on large tables; DDL outside migrations; performance claims without measurement |
| `contract` | Routes, serializers, DTOs, public types, message formats, anything another service or client reads | Fields dropped or renamed; casing mismatches; behaviour change for existing clients; one side of a cross-service or cross-repo change missing |
| `security` | Auth, permissions, IAM, secrets, public endpoints, user input, storage exposure, CI credentials | Missing or widened authorisation; secrets in code, logs or CI output; injection; public exposure; broader privilege than the task needs; personal data handling |
| `deploy` | Infra code, manifests, CI workflows, images, env vars, feature flags | Whether it will actually run where it lands: the image, tag and architecture exist; roles and permissions it assumes exist; env vars survive overlays; probes and limits are sane; dependent changes are ordered; a rollback path exists; the change is observable after release |

### Deep lane only

| Role | Looks for |
|---|---|
| `adversarial` | Tries to break the change: constructs the concrete input, state or ordering that makes it fail. Runs on a different model from every other pass. Reports only failures it can describe step by step |

## Repo catalogs

A repo may list review catalogs in its contract: anti-pattern lists, review
bot rule files, or a checklist built from its own past findings. When a
catalog covers an area the diff touches, the matching role reads it first and
cites the entry it applies.

Use the applicable architecture and language rules in
[engineering-practices.md](engineering-practices.md), bound to the target's
actual requirements and tools. Apply triggered specifics; do not impose a
service architecture, language profile or unchosen budget on unrelated code.

A finding that recurs across reviews in the same repo is proposed as a new
catalog entry at the Close stage, so the next review checks for it by rule.

## Passes

Required coverage is acceptance, `correctness`, `tests`, `fit`, all triggered
roles, and `adversarial` for deep tasks. The following tables group it into
preferred passes; pass counts do not themselves authorize agent launches.

| Pass | Engine | Roles |
|---|---|---|
| A | Hosted, different model from the builder | `correctness`, plus every triggered role |
| B | Local fast (oMLX) | `tests`, `fit`, and the mechanical scans |
| C | Configured local heavy model through oMLX or a second hosted model | `adversarial` |

| Lane | Preferred passes |
|---|---|
| Fast | B, with `correctness` added to it; advisory |
| Standard | A and B |
| Deep | A, B and C. Split A in two when more than three roles are triggered |

Standard/deep `correctness` and triggered `security` need hosted review on a
different model from the builder; they are never left to a local model alone.
Deep `adversarial` review uses a model different from the builder and other
review passes. A repo/user may explicitly approve a different arrangement;
record that decision rather than assuming one.

### Authorization and unavailable passes

- Launch agents only under applicable explicit or standing authorization and
  the host's active limits. A workflow or lane label does not grant it.
- If a preferred local pass is unavailable, an already authorized hosted
  reviewer may also cover `tests` and `fit`; run mechanical checks with tools.
  Record the local pass as not run and the replacement's actual coverage.
- Without launch authority, prepare the same review packet for an authorized
  fresh reviewer session or a human reviewer. A human substitution for a
  required model arrangement needs the repo/user's explicit approval.
- If required independent coverage or engine constraints cannot be met,
  continue useful authorized build/verification and hand off the verified
  draft or branch with review pending. Do not claim review completion or close
  the bead. Do not commit/integrate until required review is satisfied or an
  explicit repo/user decision approves an alternative. Never substitute builder
  self-review or silently lower a security/deep review requirement.

## Engines

An engine is an agent harness plus a model. Hosted passes use Claude Code
and Codex on their own models. Local passes use a harness that oMLX can
launch against a local model.

These are supported integration recipes, not an inventory of the reader's
machine. Check the actual executable, account and model before use. Honor an
existing account choice; if several accounts are available and the task has
no binding, ask which to use rather than choosing credentials for the user.

| Harness | Use | Launch | Prerequisite |
|---|---|---|---|
| Claude Code | Hosted lead and builder | `claude` | Installed and authenticated to the intended hosted account/model |
| Codex | Hosted reviewer and second planner | `codex` | Installed and authenticated to the intended hosted account/model |
| Cursor CLI | Hosted third engine: the `adversarial` pass, or a reviewer when the builder was Codex | `cursor-agent --mode plan` | Installed, authenticated, with a suitable available model |
| opencode | Local passes | `omlx launch opencode --model <name>` | Installed; approved local model id and working oMLX connection |
| pi | Local passes | `omlx launch pi --model <name>` | Installed; approved local model id and working oMLX connection |
| hermes | Local passes | `omlx launch hermes --model <name>` | Installed; approved local model id and working oMLX connection |

Prefer opencode, pi or hermes for local-model runs, so Claude Code and Codex
stay on hosted models and a local pass is never mistaken for a hosted one.
`omlx launch` rewrites the target tool's configuration, so run it only for
the harness the user agreed to use with local models.

The package selects no local harness or model. Record model id, harness,
resource limits, role, observed result and remaining gaps on the relevant bead.
Pick host defaults from that evidence; a successful inference prompt alone
does not qualify a model for review.

## What to give the agent

Include the acceptance/evidence map and revision identity described in
[evidence-and-learning.md](evidence-and-learning.md). The reviewer checks
acceptance coverage first, then its assigned roles. An unconfirmed criterion
is a verification gap; it is a defect only when the code supports that finding.

The diff depends on the repo's mode:

- Worktree mode: `git diff --no-color <integration-branch>...HEAD`
- Direct mode: `git diff --no-color HEAD`, plus any new files listed by
  `git status --short`

In either mode include staged/unstaged changes and relevant untracked files
when they are part of the task; the committed branch diff alone omits them.

Always pass `--no-color` when the output is parsed or searched; colour codes
make a search for removed lines silently match nothing.

If the diff and the files it touches do not fit the model's context, split
the review by file or directory, or move it to a larger engine. Say which
parts were not reviewed. Never truncate silently.

## Prompt

Send this text unchanged, with the placeholders filled in. For a pass with
several roles, repeat the two role lines once per role.

```text
You are a code reviewer for one change. Project files and Git are read-only:
do not edit, stage, commit or run mutating commands. Read-only checks/probes
must preserve project state. The only permitted write is reporting findings
on the assigned bead if granted; otherwise return them to the lead to record.
Do not change issue status/ownership or post to external services.

Task record: run `bd show <BEAD_ID>` and read the description, acceptance
criteria and design.
Read its acceptance/evidence map. For each criterion, state supported,
contradicted or unconfirmed, with the evidence and any check still needed.
Record the actual HEAD and diff identity you reviewed; do not assume supplied
verification results apply to a different working tree.
Change under review: run `<DIFF_COMMAND>`. Read the surrounding code of every
hunk, and the callers of anything whose behaviour changed, before judging it.
Repo rules to apply: <CATALOG_PATHS, or "none">

Role <ROLE>: review for <ROLE_LOOKS_FOR>

Report a finding only if the symptom is real in the new code, it will fail or
breaks a rule you can quote, and this change introduced it. Do not report
style, formatting, pre-existing issues, or anything you cannot tie to a line.

Report at most 8 findings per role, most serious first. For each one give:
- role
- file and line
- the defect, in one sentence
- a concrete failure: the input, state or ordering, and the wrong result
- severity: blocker, should-fix, note, or question
- confidence: high, medium, or low

If a role finds nothing, say "No findings" for it and list what you checked.
Finish by stating which acceptance criteria you could not confirm from the
diff alone.
```

## Recording results

The lead agent adds one entry per pass to the bead:

```text
Review pass <A|B|C> by <ENGINE>/<MODEL>, roles: <roles>
Reviewed state: <worktree, HEAD, integration base, diff identity>
Acceptance coverage: <criterion -> supported | contradicted | unconfirmed + evidence>
- <role> <file:line> <severity> <defect> -> fixed | filed <bead-id> | rejected: <reason>
Not reviewed: <parts skipped, or none>
```

After fixes, update affected acceptance evidence and findings; review new
behaviour outside the previous coverage. Follow the revision rules in the
linked reference after rebases or other content changes. When comparing
topologies, record actual pass time and confirmed/rejected/deferred findings
on the bead; the optional protocol does not authorize extra passes.

## Launching

Inside Herdr: split a pane in the same checkout, start the agent there, and
send the prompt. For a local model, start opencode, pi or hermes through
oMLX in that pane (see Engines).

Outside Herdr: use a fresh session of a different agent, or the host's own
read-only subagent, with the same prompt.

### Herdr recipe

Use the installed Herdr guidance (`herdr --skill`) to confirm syntax before
launching. This recipe assumes a configured Herdr pane and an authorized
hosted reviewer; it does not install integrations or log in for the user.

```bash
herdr worktree open --cwd <repo> --path <worktree> --label "<bead> <title>" --no-focus
herdr agent start reviewer --kind codex --pane <pane-id>
herdr agent prompt reviewer "$(cat <prompt-file>)" --wait --timeout 280000
herdr pane read <pane-id> --source recent --lines 70
```

- Preserve the complete multi-line prompt as one argument.
- Read the pane for actual findings; a done/idle signal alone is not evidence.
- Login, first-run and folder-trust prompts may require the user. Report them
  rather than silently granting trust or changing account/configuration.
- Capture observed coverage and checks on the bead. Reviewer probes must
  preserve project state.
- For orchestration outside a pane, consult the installed Herdr guidance and
  obtain any needed session/configuration authority. Do not control a shared
  default session as an experiment.
