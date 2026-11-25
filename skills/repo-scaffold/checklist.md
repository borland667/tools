# Adoption checklist

Use for an audit (mark each item present, partial or missing, with the file
or command that shows it) or for a new repository (work down the list).
Partial means written down but not enforced, or enforced in only some places.

## Tier S — day one

- [ ] Agent guide with commands, hard invariants, code style and working norms;
      other tools' guide files point at it
- [ ] `README.md` first-day section a new person can follow top to bottom
- [ ] `ARCHITECTURE.md` that marks built, decided-not-built and pending
- [ ] Tool versions pinned in one file; CI fails if a repeated pin disagrees
- [ ] One local gate command for typecheck, lint and unit tests
- [ ] Re-runnable bootstrap script
- [ ] Encrypted secrets or an external secret store; `.env.example` complete
- [ ] `.gitignore` covers env files, keys and the scratch directory
- [ ] Generated files marked; CI fails when they are stale
- [ ] PR template with verification and "not done" sections
- [ ] CODEOWNERS or equivalent required review
- [ ] CI on every pull request: lint, typecheck, tests, secret scan; actions
      pinned to SHAs; read-only default permissions; job timeouts
- [ ] Dependency updates enabled, including CI actions
- [ ] Deploy workflow that migrates, asserts migrations current, then deploys
- [ ] Agent working norms: no commit, push, post or release unless told

## Tier M — parallel work

- [ ] Every hard invariant names its guard, or says it is unguarded
- [ ] Env contract, redaction canary and endpoint sweep guards
- [ ] Each guard has a self-test and a minimum-match assertion
- [ ] Per-worktree port slots and a command that prints them
- [ ] Local service stack per worktree, loopback only
- [ ] Integration tests on runner-started services; external calls replayed
- [ ] Preview per pull request with its own data; teardown on close; nightly sweep
- [ ] Separate secrets per environment
- [ ] A PR review service configured, with who may request a run recorded
- [ ] Branch protection blocks merging with unresolved review threads
- [ ] Release tags created by a workflow
- [ ] `CLEAN-BUILDS.md`, `docs/runbooks/`, `docs/decisions/`
- [ ] Guard workflow closing pull requests from long-lived branches

## Tier L — several projects, formal QA

- [ ] Promotion by fast-forward workflow; atomic tag and production push
- [ ] Base branch and draft pull request per project
- [ ] Hotfix path and same-day resync of the integration branch
- [ ] QA runbooks per project; results in an ignored folder
- [ ] Evidence posted on the team ticket before QA
- [ ] Opt-in labelled jobs for slow or billed builds
- [ ] Nightly live check against real providers, alerting only
- [ ] Architecture diagram with canonical pages kept in step with the code

## Audit output

```text
Tier: <S | M | L> — <evidence>
| Practice | State | Evidence | Risk if missing | Proposed change |
Decisions needed from the user: <one-way choices, with options>
Not checked: <items and reason>
```
