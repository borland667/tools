---
name: repo-scaffold
description: >-
  Set a repository up, or audit one, for safe parallel work by people and
  agents: document split, hard invariants enforced by tests, pinned toolchain,
  re-runnable bootstrap, per-worktree isolation, encrypted secrets, CI tiers,
  preview environments, release flow and PR/QA evidence. Sized by tier
  (small, medium, large) so a small repo is not given a large repo's process.
  Use when asked to scaffold a new repo, add project structure or process to an
  existing one, audit a repo against these practices, or decide which of them
  a repo needs. Pairs with dev-flow, which runs individual tasks inside the
  repo. Do not use for a single task's workflow or for one-off questions.
---

# Repo scaffold

What a repository should contain so that several people and agents can work in
it at once without colliding, and so that its rules are checked by machines
rather than remembered. dev-flow covers how one task moves through a repo; this
skill covers the repo that task runs in. When dev-flow is installed, its repo
contract is where this skill's decisions are recorded.

Repo and user instructions always win over this skill. Follow the target's
existing practices by default; a claim that one is wrong needs local evidence
and an applicable reference, as dev-flow's `engineering-practices.md` describes.

## Tiers

Pick the smallest tier that fits the evidence, and record why. Adopt a
practice when the repo has the problem it solves, not before.

| Tier | Signals | Adds |
|---|---|---|
| **S** | One person or a small team, one deployable, one environment besides local | Agent guide, document split, one local gate, pinned tools, bootstrap, encrypted secrets, PR template, CI on every PR, secret scan |
| **M** | Several people or agents working in parallel, a staging host, previews wanted, review is a bottleneck | S plus invariant guards, per-worktree isolation, local service stack, integration tests on runner-started services, a preview per PR, local review before a review-service run, release tags |
| **L** | Several projects in flight, mobile or other slow builds, paid review, formal QA | M plus a promotion workflow, a base branch per project, QA runbooks, evidence on the team ticket, a nightly live check against real providers |

A larger tier carries real cost: more branches, more CI, more process. Moving
up needs a concrete problem the next tier solves.

## Procedure

1. **Inspect the target.** Read its agent guides, README, build and package
   scripts, CI, hooks, ignore files and secret handling. For an empty repo,
   record what is undecided instead of borrowing another project's answers.
2. **Choose the tier** from the signals above and record the evidence.
3. **Audit.** For every practice in that tier, mark it present, partial or
   missing, with the file or command that shows it. A practice written down
   but not enforced is partial. Use [practices.md](practices.md) for what each
   practice is and the problem it solves.
4. **Propose** the smallest set of additions, ordered by the risk each removes.
   Choices that are expensive to undo — release flow, secret store, branch
   model, tracker, hosting — are the user's decision; present compared options.
   Write the audit and proposal to the repo's scratch area, never a committed
   doc, unless asked.
5. **Build** only what is authorized, one concern per change. Use the layout in
   [layout.md](layout.md) and the templates in `assets/`. Every new gate is
   proven to fail on a planted violation before it is relied on (dev-flow's
   `deterministic-gates.md`).
6. **Record** the resulting commands and decisions in the repo's agent guide.
   With dev-flow, fill its repo contract rows, including Hard invariants,
   Workspace isolation, Secrets, Preview environments, Review service and
   Release flow.

The output of an audit is a gap list and a proposal, not a rewrite. Creating
files, installing hooks, changing CI or branch protection, and adding secrets
each need their own authorization; choosing this skill grants none of them.

## Principles

- **One fact, one place.** The agent guide holds rules and commands; the
  architecture document holds design and reasons; runbooks hold procedures.
  Nothing is said twice, because copies drift.
- **A rule without a guard is a wish.** Every hard invariant names the test or
  lint rule that fails when it is broken, or says plainly that it is unguarded.
  Guard patterns: dev-flow's `invariant-guards.md`.
- **One command is the definition of done.** Typecheck, lint and unit tests run
  through one local command that CI also runs.
- **Parallel by default.** No fixed ports, no shared mutable local data, no
  global state that two checkouts would fight over.
- **Secrets are encrypted in the repo or held outside it, never in clear.** CI
  holds only what decrypts the secrets it needs.
- **Evidence, not intent.** PRs and tickets say what was run and what it
  printed, and what was not verified.
- **Cheap review before expensive review.** A local review must be clean before
  a paid or human review is requested.

## References

| File | Use for |
|---|---|
| [practices.md](practices.md) | Each practice: the problem it solves, how to implement it, tier, and what not to copy |
| [layout.md](layout.md) | Directory layout by tier and what each document owns |
| [delivery.md](delivery.md) | CI shape, preview environments, branch and release flow by tier, versioning |
| [checklist.md](checklist.md) | Adoption checklist per tier, for audits and new repos |
| `assets/ARCHITECTURE.md.template` | Architecture document skeleton |
| `assets/decision.md.template` | Decision record with compared options |
| `assets/runbook.md.template` | Operational runbook |
| `assets/CLEAN-BUILDS.md.template` | Reset ladder, cheapest first |
| `assets/bootstrap.sh.template` | Re-runnable check-then-act machine setup |
| `assets/worktree-ports.sh` | Per-worktree port slots, claimed atomically |

The agent guide and PR templates live in dev-flow (`assets/AGENTS.md.template`,
`assets/PR.md.template`) so there is one copy of each. Several references here
point into dev-flow (`invariant-guards.md`, `repo-contract.md`,
`review-agents.md`, `deterministic-gates.md`). Used alone, without dev-flow
installed, treat those as names for the practice and record the decisions in the
repo's own agent guide instead.
