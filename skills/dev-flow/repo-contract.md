# Repo contract template

Use this section in a fresh repo guide and fill it in. Delete rows that
do not apply. Keep it to commands and facts; process lives in the `dev-flow`
skill.

For a new standalone agent guide, use
[bootstrap-agents.md](bootstrap-agents.md) and its asset around this contract.
This remains the single contract template; do not maintain a second copy.

```markdown
## Dev flow contract

| Binding | Value |
|---|---|
| Mode | `<worktree / direct>` — direct means commits go straight to `<main>` |
| Verify (fast) | `<command>` — must pass before any commit |
| Verify (full) | `<command>` — whole suite incl. integration; needs `<local services>`; or "CI only" |
| Task intake | `<target design/contract sources; reproduction/diagnostic commands, environment and access prerequisites>` or explicit gaps |
| Test-first | `<contract/case matrix location; initial tests/commands; tests-ready red evidence; final green and regression commands>` or not applicable with reason |
| Acceptance exercise | `<start command; entry point/URL; seed data; credential source>` — how to run the target at the tested revision; or not applicable with reason |
| Hooks | runner/config: `<path>`; pre-commit/commit-msg: `<commands>`; pre-push: `<command>`; local install: `<command>` |
| Deterministic gates | `<gate inventory below, or existing config path>` |
| Integration | branch `<main>`; `<squash / rebase-and-merge / fast-forward>`; branch names `<pattern>`; local landing `<authorized / handoff>` |
| Base sync | `<local-only: use local base / remote and base-update command>` |
| Autonomy | `<propose / commit-local / commit-push>` |
| Review catalogs | `<paths to anti-pattern lists / bot rule files / checklists>` or none |
| Coordinator | `<herdr / hermes / none>` default for multi-agent passes; interchangeable, per-task override on the bead |
| Local second opinion | `<host profile / disabled>`; `<read-only HTTP packet / isolated harness>`; `<request/token/wall limits>`; advisory only |
| Models by role | `<primary and approved alternate per role; harness/profile; identity evidence; effort/budgets; qualification limits>` using the skill's model-selection reference |
| Engineering | `<target language/runtime/tooling; section/path for applicable architecture rules, module budgets and exceptions>` |
| Design decisions | `<bead design field only / decision-record path in TMP plans/ / an ADR directory in the repo>` — where requirement answers, compared alternatives and reversibility are recorded |
| Scratch | `<path, gitignored>` or none |
| TMP docs | `<scratch root; per-task document owner; ignore/export rules; archive/retention policy>` or none with reason |
| Release gate | `<tag / deploy / apply>` — triggered by `<who>` |
| Tracker | Beads (primary), local `<stealth / committed>`; optional external `<provider + tenant/workspace + project/team>` or none |
| Ticket mapping | `<stable external id + URL/key; canonical Beads store/id and 1:1 lookup scope; field owners; status/transition/resolution map; connector and read/write authority; required reconciliation checkpoints>` or disabled/local-only |

Worktree notes: `<anything that breaks in a worktree, e.g. fixed ports, path-derived names>`

List gates here only if existing configuration does not already supply these
facts. Delete this example row when using an existing inventory.

| Gate | Trigger | Input scope | Shared command | Result policy |
|---|---|---|---|---|
| `<name>` | `<edit / pre-commit / commit-msg / pre-push / CI / manual>` | `<staged snapshot / changed packages / whole repo / message>` | `<command and config path>` | `<blocking / advisory; expected failures or unavailable prerequisites>` |
```

When adding a gate, record its registration, prerequisites and local install
command in the existing setup docs or this contract. Distinguish a versioned
hook configuration from a hook actually installed and exercised in a checkout.
Keep commands reusable by manual verification and CI where their input scopes
match. The gate-authoring procedure lives in `deterministic-gates.md` in the
skill; do not copy it into each repo.

## Autonomy profiles

These are defaults. Apply explicit user/repo grants and restrictions first;
do not ask again for an action already authorized in the current scope.
Record local integration authority separately from remote publication.

- **propose** — edit files in the workspace; never commit, push or post. The
  default when a repo declares nothing.
- **commit-local** — commit verified and reviewed work locally, one change
  per commit; never push or change remotes.
- **commit-push** — commit and push; never merge, tag or deploy. In worktree
  mode this pushes the task branch. In direct mode it pushes the main branch,
  so only declare it for a repo where that is how you already work.

Profiles alone do not grant branch merging. An explicit or standing local
integration grant allows landing a verified task branch on the local target by
the declared method, including under `commit-local`. Without that grant, hand
off the verified branch. No local integration grant implies pushing, merging a
hosted PR, tagging, deploying or applying infrastructure; those follow their
own authorization and release rules.

In a local-only repo the integration base is a local branch; no fetch, pull,
remote creation or push is required. In a remote-backed repo use its declared
base-sync command only within the granted scope. Report proposed, committed,
integrated and published states separately.

## Modes

- **worktree** — the default. One worktree and branch per task; implementation
  edits stay there. Use the primary checkout for authorized integration while
  preserving unrelated work.
- **direct** — the primary checkout on the main branch is the workspace. One
  task at a time, small commits, review before each commit. Agents never
  assume this mode; the repo has to declare it.
