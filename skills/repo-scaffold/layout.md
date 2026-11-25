# Layout

The tier column says when each path comes in. Names in brackets are common
alternatives; use whatever the target's ecosystem already uses.

```text
<repo>/
  AGENTS.md                      S  rules and commands; CLAUDE.md etc. point here
  README.md                      S  stack, first day, troubleshooting, secrets, releases
  ARCHITECTURE.md                S  built / decided-not-built / pending
  CLEAN-BUILDS.md                M  reset ladder
  <version pins>                 S  [mise.toml, .tool-versions]
  <task runner>                  S  check = typecheck + lint + unit tests  [Makefile, justfile, turbo.json]
  .env.example                   S  every variable, one comment each
  .env.worktree.example          M  per-worktree overrides, every port listed
  <encrypted secrets>            S  [fnox.toml, secrets.sops.yaml]
  .gitignore / .gitattributes    S  secret patterns, scratch dir, generated files marked
  <agent tool config>            M  variable references only  [.mcp.json]
  scripts/
    bootstrap.sh                 S  check-then-act, re-runnable
    env-setup.sh                 S  decrypt into the shell; warn without a key
    worktree-ports.sh            M  slot claim, port stride, info
  infra/dev/compose.yaml         M  local services, loopback only, ports from env
  docs/
    runbooks/                    M  production.md, branching.md
    decisions/                   M  one decision per file
    diagrams/                    M  canonical pages only
    plans/<project>/             L  spec.md, plan.md, tasks.md
    qa/<project>.md              L  scenario tables
  .github/                           [or the CI system's equivalent]
    pull_request_template.md     S
    CODEOWNERS                   S
    dependabot.yml               S  including the CI actions directory
    actions/setup/               S  pinned toolchain, pin-agreement check, cache
    workflows/
      ci.yml                     S  lint | typecheck | test | secret scan (| integration M)
      deploy.yml                 S  migrate, assert current, deploy, publish release
      preview.yml                M  per-PR environment, smoke test, teardown on close
      preview-sweep.yml          M  nightly, deletes only what CI marked, dry-run flag
      mainline-pr-guard.yml      M  closes PRs whose head is a long-lived branch
      promote.yml                L  fast-forward promotion, atomic tag
      live-check.yml             L  nightly against real providers, alerts only
  <guard tests>                  M  next to the code they guard, or tests/arch/
  TMP_FILES/                     S  ignored scratch
```

## What a reader should find where

| Question | Place |
|---|---|
| How do I run it, and what must I never do? | Agent guide |
| How does it work, and why this way? | `ARCHITECTURE.md` |
| How do I set up my machine? | `README.md` first-day section, `scripts/bootstrap.sh` |
| Something is broken locally | `README.md` troubleshooting, then `CLEAN-BUILDS.md` |
| How do I deploy, promote or recover production? | `docs/runbooks/` |
| Why was X chosen over Y? | `docs/decisions/` or the matching `ARCHITECTURE.md` section |
| What is this project building right now? | `docs/plans/<project>/` and the tracker |
| How do I test this feature by hand? | `docs/qa/<project>.md` |

## Templates

- Agent guide and repo contract: dev-flow's `assets/AGENTS.md.template` and
  `repo-contract.md`.
- PR body: dev-flow's `assets/PR.md.template`.
- Everything else: this skill's `assets/`.

Fill every placeholder from the target's verified facts. A command that has
not been run in the target is marked unverified until it has.
