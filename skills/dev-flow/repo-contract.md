# Repo contract template

Paste this section into a repo's `AGENTS.md` and fill it in. Delete rows that
do not apply. Keep it to commands and facts; process lives in the `dev-flow`
skill.

For a new agent guide or an existing guide that needs consolidation, use
[bootstrap-agents.md](bootstrap-agents.md) and its asset around this contract.
This remains the single contract template; do not maintain a second copy.

```markdown
## Dev flow contract

| Binding | Value |
|---|---|
| Mode | `<worktree / direct>` — direct means commits go straight to `<main>` |
| Verify (fast) | `<command>` — must pass before any commit |
| Verify (full) | `<command>` — whole suite incl. integration; needs `<local services>`; or "CI only" |
| Hooks | runner/config: `<path>`; pre-commit/commit-msg: `<commands>`; pre-push: `<command>`; local install: `<command>` |
| Deterministic gates | `<gate inventory below, or existing config path>` |
| Integration | branch `<main>`; `<squash / rebase-and-merge / fast-forward>`; branch names `<pattern>`; local landing `<authorized / handoff>` |
| Base sync | `<local-only: use local base / remote and base-update command>` |
| Autonomy | `<propose / commit-local / commit-push>` |
| Review catalogs | `<paths to anti-pattern lists / bot rule files / checklists>` or none |
| Scratch | `<path, gitignored>` or none |
| Release gate | `<tag / deploy / apply>` — triggered by `<who>` |
| Tracker | `<Jira project / Linear team>` or none; beads is local `<stealth / committed>` |

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
