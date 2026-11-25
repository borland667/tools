# Practices

Each practice names the problem it solves and the lowest tier that should
adopt it. If the target does not have the problem, skip the practice. Bind
every command and path to the target's actual tools; the examples are shapes,
not requirements.

## Documents

**Problem:** rules, design and procedures spread across files drift apart, and
agents act on whichever copy they read first.

| Document | Tier | Owns | Does not hold |
|---|---|---|---|
| Agent guide (`AGENTS.md`, with tool-specific files as one-line pointers) | S | Commands, hard invariants with their guards, code style, working norms, the dev-flow contract | Design or rationale; it links to them |
| `README.md` | S | What the project is, a first day top to bottom, troubleshooting, secrets setup, branches and releases for people | Rules for code |
| `ARCHITECTURE.md` | S | What is built and what is decided, and why. Sections that are decided but not built, or still pending, say so | Commands |
| `CLEAN-BUILDS.md` | M | Resets ordered cheapest to most drastic, each with its symptom and what it deletes | — |
| `docs/runbooks/` | M | Operational procedures: production, branching, incidents | Design |
| `docs/decisions/` | M | One decision per file, options compared, the chosen one marked | Ongoing work |
| Architecture diagram | M | The same design as a picture; status shown by style (for example solid = shipped, dashed = planned); saved uncompressed so diffs read | Undecided ideas on canonical pages |
| `docs/plans/<project>/` | L | Spec, plan and tasks for a project in flight | Anything after it ships; fold that into `ARCHITECTURE.md` |
| `docs/qa/<project>.md` | L | Scenario table an agent or tester can rerun | Results; those go to an ignored folder |

Rules that keep them honest:

- A change that alters an invariant or the architecture updates the owning
  document in the same change, in one place only.
- The agent guide stays short. A guide that grows past a few screens is
  carrying design; move it.
- Never keep a second copy of the rules for another tool. Point at the one copy.
- Code comments explain why, and never reference a ticket, plan or spec.

## Hard invariants as tests

**Problem:** rules that only live in prose are broken by the first agent or
person who did not read them, and review catches them late or never.

Tier M. List the rules where a violation is a bug even if the code works —
data boundaries, what may reach a client, identifiers that must not be
enumerable, what must never be logged. For each one, add a guard that fails
CI, and name the guard next to the rule in the agent guide. A rule with no
guard yet says "unguarded" so the gap is visible.

Start with the three cheapest, high-value guards:

1. **Env contract diff** — every variable the code reads is declared wherever
   the build, the example env file and the secret store need it.
2. **Seeded-canary redaction** — known fake secrets and personal data pushed
   through the real logging or error-reporting path never appear in its output.
3. **Endpoint sweep** — every public route or procedure has input validation
   and the intended authorization.

Then add guards as rules appear. The guard patterns, their self-tests and
per-language tooling are in dev-flow's `invariant-guards.md`.

## Toolchain

**Problem:** "works on my machine" — different tool versions, a setup only
one person knows, and a definition of done that varies by person.

- **Pinned versions, checked everywhere (S).** Pin tool versions in one file
  (`mise.toml`, `.tool-versions` or the ecosystem's equivalent). Where another
  file must repeat a pin (a package manager field, a build service config),
  CI fails when they disagree and says which to update.
- **One local gate command (S).** Typecheck, lint and unit tests in one run
  (`make check`, `just check`, a task-runner task). It is the first line of
  every PR's evidence and what CI runs. If workspaces have their own test
  configuration, tell people never to call the bare test runner.
- **Re-runnable bootstrap (S).** One script prints a pass or fail line per
  requirement, installs what it can, exits non-zero until nothing is missing,
  and never prints a secret. It takes a `--check` flag that reports without
  installing, so a person can see what is wrong without changing anything.
  Template: `assets/bootstrap.sh.template`.
- **Environment composed in a fixed order (S).** Secrets are decrypted into
  the shell first, then local overrides applied last. A missing key prints a
  warning and leaves the shell usable.
- **Strict environment in the build (M).** Undeclared variables never reach a
  build or test task, so results are reproducible. Values that change per
  commit or per machine are declared on the task that needs them, so they do
  not change every task's cache key.
- **Dependency patches (S).** Committed patch files pinned to an exact version,
  never edits inside the dependency directory.
- **Generated files (S).** Marked as generated for review tools; CI regenerates
  them and fails on any difference.
- **Reset ladder (M).** `CLEAN-BUILDS.md` from `assets/CLEAN-BUILDS.md.template`.

## Parallel work

**Problem:** two checkouts, agents or people start the app at once and fight
over ports, local databases and caches.

- **Per-worktree port slots (M).** Each worktree claims a numbered slot
  atomically under the shared git directory; every port is a base plus a
  stride times the slot; a gitignored local file can override any port; one
  command prints what the checkout resolved. Template:
  `assets/worktree-ports.sh`.
- **Local service stack per worktree (M).** A compose file (or equivalent)
  bound to loopback, with throwaway credentials, ports from the slot and a
  project name per slot, so each worktree has its own data.
- **Agent sandboxes (L).** For work that does not need the host OS, a
  sandboxed clone per agent task. It cannot reach the host's loopback
  services, so give it its own remote database branch or none.

## Secrets

**Problem:** secrets in chat, in plain files, or in a CI store nobody can
audit; and teammates who leave still holding everything.

- **Encrypted in the repo (S).** A tool such as fnox with age, or sops, keeps
  ciphertext committed. Each person holds their own private key outside the
  repo, from the team's password manager.
- **Personal tokens in the OS keychain (S)**, named in the secret file but not
  stored in it.
- **CI holds only the decryption key (S)** and reads secrets one by name,
  never the whole set into the environment.
- **Agent tool config committed with variable references only (S)**, never an
  inline token.
- **One recipient set or key per environment (M).** Production secrets must not
  be readable by jobs that only deploy previews.
- **Removing a teammate** means removing their recipient, re-encrypting, and
  rotating everything they held; old ciphertext stays in history.
- **Secret scanner in CI (S)**, such as gitleaks, over the whole diff.

## Review

**Problem:** review is slow and expensive, and paid bots re-review on every push.

The ordering and the prompt are dev-flow's — see its `review-agents.md`,
"Pull-request review services". Do not restate them here. What the repo must
supply so the rule can be followed:

- **A review service named in the repo contract (M)** — which one, who may
  request a run, and where its verdict is read.
- **Branch protection that treats review threads as blocking (M)**, so an
  unresolved thread cannot merge.
- **A way to read the service's threads from the command line (M)**, so a local
  reviewer can see them without a browser.

## Evidence and QA

**Problem:** reviewers and QA cannot tell what was actually checked.

- **PR template (S).** dev-flow's `assets/PR.md.template`: what changed (and
  the cause, for a fix), how it was verified, risk, rollback, not done.
- **Evidence on the team ticket (L).** QA reads the ticket, not the PR. What to
  publish and who is allowed to publish it is dev-flow's
  `ticket-mapping.md`, "QA-facing evidence".
- **QA runbooks (L).** A scenario table per project, rerunnable by an agent,
  with results written to an ignored dated folder. Rules for every run:
  fictional data only, devices and services the run created itself, no
  outbound messages to real people, never print secrets, clean up only what
  the run started, stop and ask after a step fails twice.

## Agent working norms

**Problem:** agents commit, push, post or rewrite things nobody asked for.

Put these in the agent guide (S):

- Never commit, push, merge, post to the tracker or release unless told.
- Look for an existing helper before writing one; justify any new file or
  dependency; smallest diff; no dead code; no speculative abstractions; no new
  docs unless asked.
- Type safety is structural: the language's escape hatches are not used to
  silence the checker.
- Tests maximise coverage per line; one boundary test beats five that restate
  the implementation.
- Scratch goes in an ignored scratch directory.
- Kill only processes the agent started; use only devices and services it
  created.

## What not to copy

Patterns seen in large repos that cost more than they return elsewhere.

| Pattern | Problem | Instead |
|---|---|---|
| One CI workflow file so long nobody can change it safely, with label-driven state | Hard to edit without fear | Composite actions per step; keep each workflow readable in one sitting |
| Several long-lived promotion branches plus a base branch per project, below tier L | Rebase and promotion overhead with no QA stage to justify it | `main` plus tags, or `main` plus one staging branch |
| A hand-maintained list of every environment variable with no check | Drifts silently | The env contract diff guard |
| Infrastructure identifiers hard-coded in workflow files | Config buried in code | Environment-scoped CI variables |
| One decryption key for every environment | No production boundary | A key or recipient set per environment |
| A second rules document restating the agent guide | The two drift | One copy; others point at it |
| Paragraph-long comments in configuration files | Unreadable | One line, link to the architecture document |
| Guards that parse imports or source with regular expressions | A rename silently narrows the check | The real resolver or AST, plus a self-test and minimum-match assertion |
| Dependency update automation switched off | Security updates stop | Grouped weekly updates |
