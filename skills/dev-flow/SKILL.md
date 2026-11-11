---
name: dev-flow
description: >-
  End-to-end development workflow for any repo: Beads task record,
  one worktree per task, staged plan/build/verify/review/integrate with exit
  conditions, optional multi-agent planning and review through Herdr, and
  optional local models served by oMLX as second opinions. Use when asked to
  "use the dev flow", start or resume a task with the workflow, set a repo up
  for it (including an AGENTS.md bootstrap), or run a multi-agent plan or
  review. Do not use for one-off questions or quick reads.
---

# Dev flow

A fixed loop of stages with exit conditions, plus a small per-repo contract
that supplies the commands. The loop never names a repo-specific tool; the
contract does. Repo and user instructions always win over this skill.

For guide-only/bootstrap authoring, follow
[bootstrap-agents.md](bootstrap-agents.md) with the repo's existing tracker and
authority. That request alone does not adopt the full workflow, initialize
Beads or grant Git actions. The workflow invariants and stages below apply
when adopting or executing dev-flow.

## Canonical source and local setup

Maintain this skill and its workflow references in the tools repo's
`skills/dev-flow/` directory. Other local installations link to that retained
directory; edit the source, not separate copies. Installation and maintenance
instructions live in [installation.md](installation.md) and
[validation.md](validation.md).

When present, read `local.md` beside this file for the host's account profiles,
harnesses, selected model and qualification record. It is private and ignored;
never copy its contents into portable instructions or an exported package.
Use [local.example.md](local.example.md) when a needed host binding is missing.
The optional Hermes coordinator's private runtime settings live in
`local.hermes.yaml`; the dedicated Hermes profile links to that file.
Preserve an existing account choice; ask only for a binding the task actually
needs. Installing or moving this skill does not grant workflow actions.

Resolve scoped standing authorization before applying the defaults below.
Record routine lane, plan and implementation decisions and continue within
already approved scope. Ask only for a missing decision, material scope change
or action outside that authority. Permission to edit, commit, integrate locally,
publish remotely and release are separate; one does not imply the others.

## Requirements and optional integrations

Running the full workflow requires Git, the Beads `bd` CLI and an available
task workspace, plus the target repo's own tools. Guide-only authoring uses
the existing tracker and does not require Beads. Dependency installation and
tracker initialization follow the repo/user's authority; this package installs
neither. If a required dependency is missing, record the gap and continue only
independent authorized preparation.

Herdr, oMLX and the named agent harnesses below are optional integrations.
Check availability, authentication, configured model identity and permissions
on the target host; installing this folder establishes none of them. Without
Herdr, use native Git worktrees and an authorized fresh reviewer session or
host subagent. Unavailable model passes follow the review fallback rules;
required independence/coverage remains pending until satisfied or explicitly
changed. Local model ids and memory limits are host/repo bindings, not bundled
defaults.

## Invariants

These hold in every repo, whatever its contract says.

1. **State lives in the bead, never in the conversation.** Every stage ends
   with a next step on the bead that another agent could execute from a fresh
   clone. TMP documents may hold supporting detail; accepted decisions and
   resumable state remain on the bead.
2. **One writing agent per checkout.** Any other agent in the same checkout
   keeps project files and Git read-only. Parallel writing means separate
   beads and worktrees, which only worktree mode allows.
3. **The mode decides where edits happen.** In worktree mode implementation
   edits stay in the task worktree; the primary checkout is used for authorized
   integration, preserving unrelated work. In direct mode the primary checkout
   is the workspace (see Modes).
4. **No destructive git on a dirty tree.** No `git restore .`, `git checkout .`
   or `reset --hard` with uncommitted work. Before any risky history
   operation: backup branch plus `git stash --include-untracked`.
5. **Conservative by default.** Without applicable explicit or standing
   authorization, use `propose`: edit and verify, but do not commit, push, post,
   merge, deploy or apply.
6. **Release actions are human-triggered.** Tags, deploys, infra applies and
   production changes are prepared by the agent and run by the user.
7. **Never bypass hooks.** No `--no-verify`. A broken hook gets fixed.
8. **Say exactly what was skipped.** A check that did not run is reported as
   not run, with the reason.

## Repo contract

Use a target-specific contract for these bindings, established from explicit
requirements and verified implementation/configuration facts. Active repo/user
instructions govern execution. To create a fresh guide, read
[bootstrap-agents.md](bootstrap-agents.md) and its bundled template; do not
derive the output from another project's instructions. For an unknown binding,
inspect build/package scripts, hook config or CI and distinguish facts from
inference. Use [repo-contract.md](repo-contract.md) when setup is authorized;
otherwise propose the addition.

| Binding | Meaning |
|---|---|
| Mode | `worktree` (default) or `direct` (commit straight to the main branch) |
| Verify (fast) | The command that must pass before any commit |
| Verify (full) | Optional local full suite including integration tests |
| Test-first | Applicable behavior/contract cases, test commands and tests-ready/red-to-green evidence |
| Hooks | What runs on commit and on push, runner/config and local install command |
| Deterministic gates | Repeatable commands, triggers, input scope and blocking/advisory status |
| Integration | Target branch, merge style and local integration authority |
| Base sync | Local-only base or configured remote/base-update command |
| Autonomy | `propose` / `commit-local` / `commit-push` |
| Review catalogs | Anti-pattern lists, review-bot rule files or checklists the reviewers must apply |
| Local second opinion | Optional host profile, read-only transport and limits; advisory only |
| Engineering | Target language/tooling, architecture ownership, applicable rules and declared module budgets |
| Scratch | Where bulky notes and analysis go, if anywhere |
| TMP docs | Scratch root, document owner, ignore/export policy and retention; see [tmp-docs.md](tmp-docs.md) |
| Release gate | What ships to production and who triggers it |
| Tracker | External tracker (Jira, Linear) if the team requires one |

For architecture decisions, implementation and review, use the applicable
sections of [engineering-practices.md](engineering-practices.md). It owns the
language-independent baseline and conditional stack rules. Bind specifics to
the target's actual code/tools; it grants no authority or cross-project policy.

## Modes

The mode is a property of the repo, not of the task. Never infer `direct`:
use it only when the contract says so or the user says so for this repo.

| | Worktree mode | Direct mode |
|---|---|---|
| For | Shared repos, PR-based repos, anything with parallel work | Small personal repos where the user commits to main |
| Workspace | One worktree and branch per bead | The primary checkout, on the main branch |
| Parallel tasks | Yes, one worktree each | No. One bead in progress at a time |
| Unit of change | One squashed commit or PR per bead | One small verified commit per bead, or per step of it |
| Review happens on | The branch diff, before integration | The uncommitted diff, before the commit |
| Undo | Preserve unintegrated work; revert integrated changes under repo rules | `git revert`; never rewrite main once pushed |

Direct mode rules:

- Start from a clean tree on an up-to-date main branch. If the tree is dirty
  with work that is not yours, stop and ask.
- Verify and review come before the commit, because the commit is the
  integration. There is no later gate.
- Commit only as far as the autonomy profile allows. With `propose`, leave
  the verified change uncommitted and say so.
- Keep each commit small enough to revert on its own. A change that needs
  several days or several agents is a reason to use a worktree for that
  bead; say so and ask.
- Deep-lane work still gets a worktree unless the user says otherwise.
- Helpers keep project files and Git read-only. Report findings under the
  permissions in [review-agents.md](review-agents.md).

## Lanes

Pick a lane when framing and record the reason on the bead. Existing approval
covers routine classification; ask only when the choice needs a new scope or
authority decision.

| Lane | When | Stages |
|---|---|---|
| Fast | One obvious change; no schema, auth, payment, infra or contract | Frame, Build, Verify, local review pass, Integrate, Close |
| Standard | A normal task | All except Understand |
| Deep | Cross-repo, migration, production data, security, or unclear cause | All |

Release applies only when the requested endpoint includes shipping; an
implementation-only task records release as not applicable. Promotion to a
deeper lane changes investigation/verification needs, not the approved scope.

## Stages

### 1. Frame

- Make sure beads exists: `bd where`. If not, ask before initialising. In a
  repo shared with others use `bd init --stealth --prefix <short>` so nothing
  is committable.
- At session start or after compaction, reload repo guidance, `bd prime` and
  dynamic saved preferences using the repo's documented bootstrap. Confirm
  the actual tracker, checkout root, branch, status and existing worktrees.
- `bd ready --json` first, then inspect the requested/related bead and relevant
  in-progress work; ready work alone does not show everything resumable.
  Confirm ownership before claiming. Do not take over another active writer.
- On resume, reuse the existing bead/worktree and reconcile its recorded stage
  and evidence with current files and Git state. Continue at the first unmet
  exit condition, not automatically at Build. Use the resume/handoff record in
  [evidence-and-learning.md](evidence-and-learning.md).
- Create or claim:
  `bd create "<title>" -t <bug|feature|task|chore> -p <0-4> --description "..." --acceptance "..." --design "Lane: <lane>. ..." --json`
  then `bd update <id> --claim --json`.
- Where a team tracker is required, the ticket must exist first; link it with
  `--external-ref`. The ticket is the public record; the bead is the working
  state.
- Record the outcome, requested completion endpoint, non-goals and constraints.
  Map each acceptance criterion to an observable check on the bead; even a
  fast-lane task needs this mapping.
  Read [evidence-and-learning.md](evidence-and-learning.md) for the compact
  record format and revision rules. Unknown checks stay unresolved.
- Inspect the existing hooks and deterministic gates. A missing check that
  directly enforces this task's requirements can be part of the implementation;
  unrelated improvements become linked beads.
- Identify the smallest relevant baseline and its environment for the intended
  task workspace. Establish it before edits in Build, using the guidance in
  [evidence-and-learning.md](evidence-and-learning.md).

**Exit:** a claimed bead with a lane and acceptance-to-verification mapping.

### 2. Understand (deep lane)

- Read code and read-only data. Measure; do not assume.
- Findings go on the bead; bulky output goes to the repo's scratch location.
  Use [tmp-docs.md](tmp-docs.md) for categorized investigations and evidence.

**Exit:** every claim the plan will rest on is measured or cited.

### 3. Plan

- Write the executable plan into the bead's design field (`--design` or
  `--design-file`). It must stand alone without chat or local files. Substantial
  technical detail may live in linked TMP documents under
  [tmp-docs.md](tmp-docs.md); do not create a second task ledger.
- Refine the acceptance checks against the actual code and commands. Keep
  planned verification separate from observed results. If discoveries change
  the design, update the bead and assess whether they exceed approved scope.
- For new APIs and substantive behavior changes, follow
  [test-first.md](test-first.md): define the contract and initial case matrix,
  including known material edge cases, before production behavior. Bind the
  test commands and blocking triggers; do not promise exhaustive input coverage.
- When a requirement can be checked mechanically, consider making it a
  repeatable gate instead of relying on repeated model review. For gate changes,
  define the command, trigger, input scope and failure behaviour using
  [deterministic-gates.md](deterministic-gates.md).
- Deep lane with authorized multi-agent planning: use two planners when
  available (see Multi-agent) and merge their drafts. Otherwise the lead writes
  the plan; do not treat an unavailable planning pass as one that ran.
- Use `bd human <id>` for a decision only the user can make.

**Exit:** an executable plan within existing approval, or new approval obtained
where scope, risk or the repo's rules require it.

### 4. Build

- Worktree mode: one worktree per bead, branched from the current integration
  branch. When the repo uses a remote, synchronize its configured base as the
  repo requires and authority permits. In a local-only repo use the local base;
  no fetch, pull or remote setup is needed. Name the branch after the bead or
  ticket using repo conventions. Keep dots out of the worktree directory name.
- Direct mode: work in the primary checkout on the main branch, from a clean
  and up-to-date tree.
- Before edits, run the relevant baseline in that actual task workspace or
  reuse evidence for matching inputs/environment. Record existing failures or
  unavailable checks and their limits. They do not waive required final gates
  or authorize unrelated repairs.
- Smallest diff. Change a contract or schema before the code that uses it.
  For new APIs/substantive behavior, complete the tests-ready checkpoint in
  [test-first.md](test-first.md) before production behavior: executable initial
  tests, checked expectations and failures for the intended missing behavior.
  Then implement to green and refactor. Add newly discovered cases before their
  fixes; expected red does not authorize bypassing existing hooks or delivery gates.
- For bugs or unexpected failures: reproduce the symptom, gather baseline
  evidence, state one root-cause hypothesis and test the smallest change that
  distinguishes it. Verify the original symptom after the fix; use a regression
  test when warranted. Do not stack speculative fixes. Repeated attempts that
  add no evidence trigger a different investigation or revised plan; involve
  the user when a decision or scope change needs them.
- Scope creep becomes a new bead:
  `bd create "..." --deps discovered-from:<id> --json`.
- Add or strengthen repo-owned pre-commit hooks and other deterministic gates
  when they belong to the authorized task. Reuse the repo's runner and shared
  commands, wire the actual trigger, and document setup in the repo contract.
  A general workflow invocation does not authorize changes to other repos or
  global Git configuration.

**Exit:** the change is complete in the worktree and its tests pass locally.

### 5. Verify

- Run the fast verify command. Run the full local suite when the lane is
  deep, or standard and the change touches a boundary (schema, API contract,
  auth, background jobs). Run long suites in the background.
- Exercise the real behaviour where practical, not only the tests.
- For test-first work, retain observed red and final green evidence. All required
  cases and relevant regressions must pass without weakened assertions or hidden
  skips; package validation or a coverage percentage cannot substitute for them.
- Work backwards from each acceptance criterion: confirm implementation,
  reachable wiring and real data where relevant. File presence, a stub or a
  passing unrelated suite does not establish the outcome.
- Record on the bead: criterion, tested revision/diff, environment, actual
  command or procedure, observed result, evidence and gaps. Keep failed,
  skipped and unavailable checks visible. Use the record in
  [evidence-and-learning.md](evidence-and-learning.md).
- For a new or changed gate, demonstrate that a known-good case passes and a
  representative violation fails through its actual trigger. Check the
  declared input scope and preservation of unrelated edits. A passing manual
  command alone does not prove a hook or CI job is registered or active.

**Exit:** required checks pass and every acceptance criterion has current
supporting evidence; unmet criteria remain open, with gaps recorded.

### 6. Review

- A fresh context reviews the diff against the bead's acceptance criteria.
  The builder never reviews its own work in the same context. Give the reviewer
  the acceptance/evidence map and the exact revision under review. Check
  acceptance coverage before applying the correctness and triggered-role lenses.
- Required coverage is acceptance, `correctness`, `tests`, `fit`, all triggered
  roles, and `adversarial` on deep tasks. Use the fixed prompts and authorization/
  availability rules in [review-agents.md](review-agents.md). Preferred passes:

  | Lane | Preferred review passes |
  |---|---|
  | Fast | One local pass: `correctness`, `tests`, `fit`; advisory |
  | Standard | A hosted pass on a different model from the builder (`correctness` plus roles the diff triggers) and a local pass (`tests`, `fit`, mechanical scans) |
  | Deep | Both of those, plus an `adversarial` pass on a third engine |

- Pass counts describe the preferred topology, not launch authority. An
  authorized reviewer may combine roles when a preferred pass is unavailable;
  preserve the standard/deep different-model hosted review and deep adversarial
  independence requirements unless the repo/user explicitly approves an
  alternative. Without launch authority, hand off to an authorized fresh
  reviewer session or human under those same rules. Missing required coverage
  stays pending; builder self-review does not substitute for independent review.
- Triggered roles are `concurrency`, `data`, `contract`, `security` and
  `deploy`; the file lists what triggers each.

- Each finding is fixed, or filed as a child bead, or rejected with a reason
  recorded on the bead. Advisory findings may be rejected without a fix, but
  not without a reason.
- After fixes, the same agent re-checks its findings. Refresh affected checks
  and acceptance evidence; new changes outside that review's coverage need
  review too. Filing a follow-up does not satisfy an unmet acceptance criterion.

**Exit:** no unresolved blocking findings or unmet acceptance criteria;
non-blocking deferrals have a reason and a linked bead.

### 7. Integrate

- Refresh the configured integration base as the repo requires. Fetch/pull only
  for a repo that uses a remote, within authorized scope; local-only repos use
  their local base.
- Worktree mode: rebase onto that base, preserving uncommitted work before the
  history operation. Refresh affected verification and review before committing
  or landing. If the integration base moves again, repeat that reassessment.
- After a rebase, fix, hook autofix or other relevant edit, reassess evidence
  against the resulting diff. Rerun affected checks and the repo's required
  final gates, refresh review coverage, and record the final tested revision.
  Earlier results remain historical evidence; they do not automatically
  establish the new state. Explain any carry-forward across identical content.
- Direct mode: synchronize the base as above while preserving uncommitted work.
  Do not amend or rebase commits that are already pushed.
- Follow the repo's commit and PR conventions.
- Audit the staged diff for secrets. Update docs in the same change.
- With commit authority, create one clean commit per change unless the repo
  says otherwise. In direct mode that commit is local integration. In worktree
  mode, land the verified branch only when local integration is authorized, by
  the declared method (for example, fast-forward `main` to the rebased branch).
  Preserve unrelated primary-checkout edits. Otherwise leave the verified
  commit/branch ready for the authorized integrator; do not call it integrated.
  With `propose` and no overriding grant, leave the change uncommitted.
- Honor explicit and standing grants plus the autonomy profile's defaults.
  Local integration does not authorize a push, hosted PR merge or release.

**Exit:** the change is proposed, committed awaiting integration, or integrated
as authorized; the bead and handoff state which actually occurred.

### 8. Release

- Apply this stage only when shipping is part of the requested endpoint. A
  release handoff satisfies the task only if that is its agreed endpoint;
  required but unexecuted release or verification stays pending.
- Prepare the release steps and state the risk. The user triggers them.
- After release, check the behaviour against a baseline where the repo has
  production telemetry; file a bead per regression.

**Exit:** released and checked, or explicitly handed to the user.

### 9. Close

- Confirm acceptance evidence and review coverage for the requested endpoint.
  Implementation, integration and release are separate states; a handoff does
  not satisfy an outstanding required outcome. Keep such work open.
- Record material workflow friction or a safeguard that helped, with evidence,
  impact, one primary owner and proposed validation. Repo-specific conventions
  belong in its guide/contract; reusable procedure in this skill or a reference;
  mechanical checks in a validator; reproducible defects in regression tests.
  Propose changes and link follow-up beads within the authorized scope. Do not
  accumulate generic rules from harmless incidents.
- When a recurring finding has a reliable mechanical check, prefer a repo-owned
  gate with a tested trigger over another prose reminder. Implement it within
  approved scope, or file the gate improvement as linked work.
- When considering a different review topology, use the optional comparison
  protocol in [evidence-and-learning.md](evidence-and-learning.md). Record
  observations on the bead; measurement does not require extra agents.
- Before cleanup, inspect tracked, untracked and ignored files and task-owned
  processes. Remove only integrated worktrees with no retained data or active
  processes needing them; never force removal to finish a task. Preserve dirty
  or unintegrated work and report its location/retention reason. Stop only
  task-owned processes whose shutdown is authorized; leave shared services alone.
- Apply the bound TMP lifecycle: promote lasting knowledge, archive or retain
  local evidence, and refresh bead links before removing its worktree. Follow
  [tmp-docs.md](tmp-docs.md); ignored documents can still be the only copy.
- Record the final tested revision/environment, actual delivery state, gaps,
  follow-up beads, retained work and concrete next action before closing.
  Close with `bd close <id> --reason "..." --json` only when acceptance is
  satisfied.
  If handing off unfinished work, leave it open and record the next action and
  the condition needed to proceed. See the compact record in the linked reference.

**Exit:** fulfilled task closed with cleanup or explicit retention recorded;
unfinished work remains open with an executable handoff.

## Hooks and test tiers

The flow supports creating and evolving these gates, not only running existing
ones. Read [deterministic-gates.md](deterministic-gates.md) when adding, changing
or installing a gate. Use the repo's declared budgets; these are defaults.

| Tier | Trigger | Budget | Contents |
|---|---|---|---|
| Edit | Optional watcher/editor task | Interactive | Targeted feedback on configured changes |
| Commit | Pre-commit / commit-msg hook | Under 5 s | Staged-content format/lint and secrets checks; message validation at commit-msg |
| Push | Hook | Under 60 s | Type check and unit tests for changed packages |
| Full local | Manual | None | Whole suite with integration tests against local, isolated services |
| CI | Automatic | None | The same suite, plus build and anything needing shared infrastructure |

- Hooks use no network, Docker or database. A hook over budget moves down a
  tier; it is not skipped.
- An autofix may require another attempt. Inspect and re-stage only intended
  changes, preserving partial staging and unrelated edits; never blanket-stage
  the working tree. Verify the final staged content.
- Blocking gates must pass at their declared trigger. Hook success does not
  replace Stage 5 acceptance verification or independent review.
- The full local run and CI should call one script, and must be safe to run
  from several worktrees at once (no fixed ports, no shared database).

## Multi-agent (Herdr)

When Hermes is selected as coordinator, use
[hermes-coordinator.md](hermes-coordinator.md) for bounded delegation to actual
Claude Code/Codex CLI workers and per-task Claude profile selection. Herdr
remains an optional pane/worktree interface, not a required second coordinator.

Launch agents only under applicable explicit or standing authorization and the
host's active limits. A lane or preferred-pass table alone grants no launch
authority. Without it, use the review handoff path above. Keep the preferred
topology until an authorized comparison supports changing its defaults;
role-combining fallbacks retain required coverage and record omitted passes.
Requires running inside a Herdr pane: `test "${HERDR_ENV:-}" = 1`. If that
fails, say so and use a fresh session or the host's own subagents instead.
Load Herdr's own skill (`herdr --skill`) for command syntax.

- **Topology:** one Herdr workspace per worktree, one pane per agent.
  Create the worktree with
  `herdr worktree create --cwd <repo> --branch <name> --base <ref> --path <dir> --label "<bead> <title>" --no-focus`.
- **Fan-out limits:** at most two planners per bead. Review agents follow
  the passes in `review-agents.md`: one on the fast lane, two on standard,
  and at most four on deep.
- **Start and prompt:** `herdr pane split`, then
  `herdr agent start <name> --kind <agent> --pane <id>`, then
  `herdr agent prompt <name> "<text>" --wait`.
- **Check before trusting status.** Read the pane after starting an agent; a
  login or first-run screen can be reported as idle.
- **Coordinate through the bead.** Give each helper the bead id and its role.
  Helpers report findings on that bead when authorized; otherwise the lead
  records their returned findings. Helpers do not edit project files or change
  issue status/ownership.
- **Default pairing:** use the host binding in `local.md` when supplied.
  Otherwise the preferred pairing is Claude Code building and Codex reviewing
  and planning second, subject to actual availability and task authority.
- **Accounts:** preserve the task's account/profile binding. When multiple
  profiles are available and none is bound, ask which one applies; do not pick
  credentials. Start the intended profile launcher rather than a default binary.

## Local models

Use [local-second-opinions.md](local-second-opinions.md) for the supervised
Flash-through-oMLX/Splash integration: a bounded, read-only local review pass
whose findings the lead confirms. Resolve the exact model, endpoint, transport
and resource limits from the host binding; this portable package sets no
machine defaults. Run local passes serially within that budget.

Local models never lead builds or decide gate outcomes. Required deterministic
checks remain blocking according to the repo contract; a model's opinion cannot
waive them. Required hosted/deep/security review independence still follows
[review-agents.md](review-agents.md). Local advice does not replace that coverage.

## Status of this skill

Package validation checks structure, bundled references and portability; it
does not qualify a host, validate project code or establish workflow quality.
Host-specific results and outstanding qualification gaps stay in `local.md`.
Record actual runs and limitations on the task's bead. A full end-to-end task,
the preferred multi-model topology, direct mode and hook tiers still require
qualification in real tasks; no measured productivity benefit is claimed.
