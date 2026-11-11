# TMP working documents

Use TMP documents for substantial plans, investigations, test-case matrices,
review reports, verification evidence and delivery drafts. They support the
development stages; a small task can use its bead alone. Read the target's
scratch binding before creating files. This convention installs no directories,
ignore rules or hooks by itself.

Beads owns scope, accepted decisions, task status, blockers, dependencies and
the next action. TMP documents hold the detailed technical material behind
those records. Link each document from its bead and identify the bead in the
document. Keep the bead's design and handoff sufficient to resume without a
local file: an ignored document will not exist in a fresh clone. Do not create
a parallel Markdown task ledger or put the only copy of a decision in scratch.

## Location, naming and ownership

- Repo-specific work goes under `<task-worktree>/TMP_FILES/`, or the target's
  established scratch root. Direct mode uses the primary checkout.
- Cross-repo analysis goes under the agreed workspace-root `TMP_FILES/`, with
  the participating repos and their revisions identified. Bind that location
  explicitly; a Git ignore rule in a child repo cannot protect its parent.
- Keep one authoritative working document per purpose and task. Reuse it when
  resuming. Name a single writer; reviewers return separate reports, not edits
  to a shared plan. Concurrent writing jobs still require separate workspaces.
- Use `TMP_<TASK-ID>_<short-slug>.<ext>`. Use the bead id when there is no team
  ticket; record both when present. Add `_YYYY-MM-DD` for incidents/snapshots,
  and a pass/run suffix for distinct evidence that must be preserved.
- Create category folders on demand. Keep drafts out of repo roots and `docs/`.
  An existing target convention can bind different names without copying files.

| Category | Contents |
|---|---|
| `plans/` | Designs, alternatives, implementation/migration approaches, contract and initial test-case matrices |
| `analysis/` | Investigations, measurements and hypothesis/disposition notes |
| `reviews/` | Review findings, accepted/rejected dispositions and verification summaries |
| `incidents/` | Incident investigations, RCAs and postmortem drafts |
| `pr-descriptions/` | Draft PR/MR bodies |
| `commit-messages/` | Draft commit messages |
| `tickets/` | External ticket drafts |
| `runbooks/` | Operational procedure drafts |
| `scripts/` | One-off helpers; inspect before execution, with normal action permissions |
| `data/` | Redacted logs, fixtures, snapshots and exports |
| `misc/` | Material that does not fit another category |
| `archive/<category>/` | Retained completed or superseded material |

Use [assets/TMP.md.template](assets/TMP.md.template) when useful; keep only the
sections the document needs. The template is maintained here, while actual
task documents belong to the target's scratch root. Do not put them inside
the shared skill or create a second maintained copy of the workflow.

## Update at the workflow checkpoints

| Checkpoint | TMP content and durable update |
|---|---|
| Frame/resume | Find existing documents from the bead. Confirm owner, purpose, paths and revision before reuse; mark stale claims. Bind scratch/retention rules once per target. |
| Understand/Plan | Capture measurements, alternatives, contract and applicable edge-case matrix. Put the executable accepted plan and material decisions on the bead; link supporting detail. |
| Tests/Build | Record test identities and observed red before behavior implementation, then green/regression results. Keep the actual tests in the repo's test suite. Explain contract changes and refresh affected evidence. |
| Verify/Review | Identify exact source/diff, environment, commands and results. Separate planned checks, actual observations and unverified claims; preserve earlier runs and finding dispositions. |
| Handoff | Refresh the bead's stage, tested identity, gaps, retained paths and next action. Summarize enough for a new session even if local files are unavailable. |
| Close | Promote needed permanent knowledge, then archive or explicitly retain task material; record its final location and retention reason on the bead. |

Follow [test-first.md](test-first.md) and
[evidence-and-learning.md](evidence-and-learning.md) for test checkpoints,
revision identity, acceptance and stale-review handling. A TMP report, a model
verdict or a checkbox never substitutes for actual blocking gate results.
Refresh summaries after material changes and before handoff; do not rewrite a
failed historical run into a passing one or duplicate raw logs in every doc.
Hermes or another coordinator owns the links and summary; each worker receives
only its authorized artifact path and writes only within its assigned scope.

## Ignore and publication rules

TMP content is local and uncommitted. For an approved repo-local root, a
target ignore rule such as `/TMP_FILES/` is sufficient; an existing
`**/TMP_*` convention may already cover it. Verify the actual binding before
writing drafts, for example from the target checkout:

```bash
git check-ignore -v -- TMP_FILES/plans/TMP_task_example.md
git ls-files -- TMP_FILES
```

The first command must demonstrate exclusion; the second reveals files already
tracked, which ignore rules do not untrack. Preserve existing tracked content
and resolve its policy within the task's authority. Do not force-add drafts or
silently remove tracked files. An external scratch root needs its own access,
retention and export rules. Ignore rules are not access control: keep credentials,
private keys, personal data and unredacted sensitive exports out of task docs.

Committed docs and commit messages must stand alone without links to local TMP
files. Refer to the durable issue/PR or promote the necessary content to a
target-owned permanent location with a normal name and scope-appropriate
review. Keep permanent setup, architecture and usage docs in their owning
locations; the TMP convention does not rename existing documentation.
Drafting a PR body, ticket or message does not authorize publishing it.

## Promotion, archive and cleanup

When a task reaches its requested endpoint, move retained documents to
`TMP_FILES/archive/<category>/` if that is the target's bound policy. Keep the
task id in filenames and repair the bead's references. Record what remains
active when the task is handed off unfinished. Preserve the original run
identity even when a summary is updated or a document is superseded.

Before worktree removal, inspect ignored TMP files as well as tracked and
untracked work. If evidence is still needed, move it to the agreed retained
location and update links, or retain the worktree with a reason. Never delete
the only copy merely to finish cleanup. Cross-repo work needs one retained
owner/location, not copies in every participating repo.

Bind retention and pruning to the target's policy. Archiving is not permission
to delete evidence; automatic age-based deletion is not part of this skill.
Promote lasting decisions, contracts and runbooks before discarding drafts;
write concise project lessons to Beads using its normal memory mechanism.
