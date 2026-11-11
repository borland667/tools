# One external ticket, one Beads task

Use when the target already uses Jira, Linear or another ticket system. Keep
that system and its established workflow. Bind the provider, tenant/workspace,
project/team, identity fields, field ownership, status mapping and available
connector in the repo contract. Local-only work can remain unmapped when the
repo allows it. This reference defines the mapping protocol; it installs no
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
- Split independently tracked work into external child issues and matching
  beads only within existing authority. Do not map several beads to the same
  issue just to represent phases or repository-specific slices.
- One ticket spanning several repos keeps one bead with per-repo workspaces,
  gates, changes and delivery state. Honor each repo's selected mode: one task
  worktree per bead per repo in worktree mode, or its primary checkout in direct
  mode. Multiple repo worktrees for this one bead are permitted; keep one writer
  per checkout and the target's direct-mode task limits. Alternatively, use separately ticketed child tasks
  when the team's existing process requires independent ownership/delivery.
- Discovered follow-ups follow the same rule. If an external ticket is
  mandatory, obtain/create it under the target's authority before claiming a
  mapped implementation task. An explicitly local draft can record preparation
  and the missing binding; it must not masquerade as an established mapping.

## Field ownership

| Information | Default authority and local representation |
|---|---|
| Public title, scope, acceptance, business priority, team assignee | External tracker; Beads holds a sourced working snapshot and records change proposals, not a competing definition |
| External status, resolution, hierarchy and dependencies | External tracker; record exact provider identities and observed state, not guesses from display names |
| Agent claim, phase, executable plan, test/review evidence, workspaces and next action | Beads; a local agent claim does not reassign the external human owner |
| Commits, PRs, CI and release observations | Their actual source systems; summarize/link evidence in Beads and publish only the authorized team-facing portion |
| Large analysis and draft material | Approved TMP storage linked from the bead; external tickets must not depend on private local TMP paths |

Apply target-specific ownership where explicitly bound. Refresh the working
acceptance snapshot before planning and after relevant remote edits. Reconcile
changes against current tests/implementation and refresh affected evidence;
never overwrite a teammate's edit with an older local description.

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
Reopened work reuses the existing pair and invalidates affected completion
claims; do not create a replacement bead to conceal the earlier result.

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

Keep pending updates and failures on the bead, not a separate Markdown sync
queue. Remote unavailability does not prove deletion or permit duplicate
creation. Record missing credentials/connectivity without copying credentials;
continue only work whose required scope/acceptance remains established.

Do not infer external Done from a local commit or closed bead, or verified
completion from an external Done state. Check the requested endpoint and team
definition of done against actual gates/reviews/integration/release evidence.
If remote reconciliation is a required delivery step, keep the task unfinished
until it is verified. Otherwise local completion may explicitly retain a
pending external handoff; report local and remote states separately.

Provider references: [Jira Cloud issue API](https://developer.atlassian.com/cloud/jira/platform/rest/v3/api-group-issues/)
and [Linear GraphQL API](https://linear.app/developers/graphql). Inspect the
target's actual schema, permissions and workflow before binding it; their APIs
and individual workspaces need different adapters. Qualify identity reuse,
duplicate detection, renamed/reopened issues, dependency direction, conflicts
and partial/offline updates before claiming live synchronization works.
