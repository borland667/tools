# One external ticket, one Beads task

Beads is the main tracker and canonical task record for dev-flow. Jira, Linear
and other external systems are optional linked representations; using dev-flow
does not require one. When linking a system, preserve its established workflow
and bind the provider, tenant/workspace,
project/team, identity fields, field ownership, status mapping and available
connector in the repo contract. A bead may remain unlinked throughout its
lifecycle. This reference defines the optional mapping protocol; it installs no
connector, background sync or provider-side configuration.

## Identity and task boundaries

A mapped Beads task has exactly one primary external issue, and that external
issue has exactly one canonical Beads task in the participating workspace.
Use `(provider, tenant/workspace, stable issue id)` as the identity. Store the
human-readable key and URL separately so a rename/move does not create another
task. Other tickets may be related links; they are not additional primary
mappings. Resolve identity from the selected provider, never a title match.
Identify the local side by its owning Beads workspace/store and bead id; a
bare bead id is not a cross-store identity. Include that canonical location in
repo bindings and worker packets so other repositories route task operations
there instead of creating a duplicate in their own store.

Use Beads' native `--external-ref` for the canonical external URL/reference and
its metadata for the provider-qualified identity, current key, last observed
remote revision/time, field mapping and reconciliation state. Merge metadata
without replacing unrelated fields. These are task records, not credentials;
keep tokens and private exports out of metadata and committed files.

Before creating or linking, search existing open and closed records by exact
external reference and stable identity, including the relevant Beads stores
when several repos participate. Include pagination/complete exports rather
than only ready work or the first results page. Reuse an existing pair. Multiple
matches or conflicting bindings require reconciliation, not another task.
Serialize bind/create operations under one coordinator and recheck before
creation. Do not claim cross-store atomic uniqueness: this protocol has no
global mapping service or database uniqueness constraint.

- An epic/parent is a different issue from each of its children. Map each
  participating issue once; preserve hierarchy and dependency direction.
- Split independently tracked work into child beads as needed. Optionally link
  each to its own external child issue within existing authority. Do not map several beads to the same
  issue just to represent phases or repository-specific slices.
- One ticket spanning several repos keeps one bead with per-repo workspaces,
  gates, changes and delivery state. Honor each repo's selected mode: one task
  worktree per bead per repo in worktree mode, or its primary checkout in direct
  mode. Multiple repo worktrees for this one bead are permitted; keep one writer
  per checkout and the target's direct-mode task limits. Alternatively, use separately ticketed child tasks
  when the team's existing process requires independent ownership/delivery.
- Discovered follow-ups can begin as ordinary unlinked beads. Creating or
  claiming a bead does not depend on an external ticket. If external tracking
  is later enabled for that task, resolve/create the external issue under the
  existing authority and attach it to the same bead. Until identity is verified,
  record the proposed link as pending, not an established mapping.

## Field ownership

| Information | Default authority and local representation |
|---|---|
| Canonical title, scope, acceptance, priority, task ownership, status, hierarchy and dependencies | Beads; optional external fields are mapped/public representations, not a second source of task truth |
| Agent claim, phase, executable plan, test/review evidence, workspaces and next action | Beads; an agent claim does not automatically reassign an external human owner |
| Actual external fields, assignee, status and resolution | Observe the provider's real state separately; record identity, revision and pending differences without treating them as canonical Beads decisions |
| Commits, PRs, CI and release observations | Their actual source systems; summarize/link evidence in Beads and publish only the authorized team-facing portion |
| Large analysis and draft material | Approved TMP storage linked from the bead; external tickets must not depend on private local TMP paths |

Bind which Beads fields may be published and how external inputs are reviewed;
the binding does not displace Beads as primary. External edits are proposed
changes to reconcile against the canonical bead, current requirements and
implementation evidence. Record accepted changes in Beads before dependent
work and refresh affected tests/review. Do not blindly import remote edits or
overwrite a teammate's remote change with an older local description.

## State mapping and reconciliation

1:1 describes task identity, not identical status vocabularies. Bind actual
provider status ids/transitions and resolution meanings to the available local
states. Local Design/Diagnose/Build/Review phases are execution detail; do not
invent a remote status for every phase. For example, several active phases may
correspond to one external In Progress state. This is an illustration, not a
default transition map for Jira or Linear.

Keep blocked conditions, assignees and dependency links explicit even if a
provider represents them as flags/relations instead of statuses. Preserve
external blockers even when their tickets have no local bead; `bd ready` alone
does not establish external readiness, and no full backlog import is required.
Preserve unmapped statuses as reconciliation gaps. Distinguish completed, canceled and
duplicate resolutions; cancellation/duplication is not successful acceptance.
Reopened work reuses the existing pair; an external reopen triggers review,
not an automatic local status change. Confirm any regression or accepted scope
change in Beads before revising affected completion claims. Do not create a
replacement bead to conceal the earlier result.

At start/resume, material remote edits, handoff and Close:

1. Read both records and the relevant source/delivery evidence. Compare with
   the last observed revision; identify proposed changes by field ownership.
2. Prepare the smallest update, including intended transition, exact fields
   and public evidence. Resolve conflicting acceptance, owner or resolution
   before dependent work; continue independent preparation where possible.
3. Apply external writes only through an available authorized connector/API
   and within explicit or standing task authority. Binding a ticket or adopting
   this skill does not authorize creating issues, posting comments, changing
   assignees or transitioning a team workflow. Without authority, retain the
   concrete proposed update and pending action on the bead.
4. Re-read/verify the resulting remote fields and record actual success or
   failure. Respect provider concurrency/version checks where supported;
   detect intervening edits instead of using last-write-wins synchronization.
   A repeated reconciliation must not create another ticket, bead or duplicate
   comment. After a timeout, inspect current remote state before any authorized
   retry; partial API success is not a complete update.

## QA-facing evidence

Testers and reviewers outside the agent workflow read the external ticket, not
the bead or the PR. Posting there needs the same write authority as any other
external change; a ticket binding does not grant it. Where that authority
exists and the task reaches a review, QA handoff or Close, publish the
authorized public portion of the evidence on the ticket:

- a recording for a flow or motion, screenshots for static screens, or a
  redacted terminal transcript for backend-only work; the before state for a fix;
- every environment touched, with the build or preview it was checked on;
- two to five numbered how-to-test steps, each with its expected result;
- what the task leaves out or could not verify.

Keep it short and plain; attach logs rather than pasting them into the
comment. Without that authority, record the prepared text as a pending update
on the bead. Moving the ticket to a QA state follows the bound status map and
its own authority.

## Reconciliation and pending updates

Keep pending updates and failures on the bead, not a separate Markdown sync
queue. Remote unavailability does not prove deletion or permit duplicate
creation. Record missing credentials/connectivity without copying credentials;
continue work whose scope/acceptance remains established in Beads; unavailable
optional synchronization alone does not block local progress.

Do not infer external Done from a local commit or closed bead, or verified
completion from an external Done state. Check the requested endpoint and team
definition of done against actual gates/reviews/integration/release evidence.
Only when an explicit task/repo requirement makes remote reconciliation a
delivery step, keep that requested endpoint unfinished
until it is verified. Otherwise local completion may explicitly retain a
pending external handoff; report local and remote states separately.

Provider references: [Jira Cloud issue API](https://developer.atlassian.com/cloud/jira/platform/rest/v3/api-group-issues/)
and [Linear GraphQL API](https://linear.app/developers/graphql). Inspect the
target's actual schema, permissions and workflow before binding it; their APIs
and individual workspaces need different adapters. Qualify identity reuse,
duplicate detection, renamed/reopened issues, dependency direction, conflicts
and partial/offline updates before claiming live synchronization works.
