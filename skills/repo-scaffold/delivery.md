# Delivery: CI, previews and releases

## CI by tier

**S — every pull request**

- Lint, typecheck, unit tests and a secret scan, as parallel jobs calling the
  same command as the local gate.
- A lint rule that fails stray debug output on production paths (raw console
  or print calls, unstructured logging at the wrong level), or the language's
  equivalent.
- Third-party actions pinned to a commit SHA; workflow permissions read-only by
  default, widened per job; a timeout on every job.
- A dependency update bot that also covers the CI actions.
- Jobs needing secrets skip, rather than fail, on pull requests from forks.

**M — add**

- Integration tests on services the runner starts itself (a compose stack), so
  no job shares a database. External model or API calls are replayed from
  recordings, and the real host is blocked so a missing recording fails loudly.
- A preview environment per pull request (below).
- One pull-request comment updated in place (where the host supports editing a
  comment) for preview URLs and test accounts, instead of a new comment per push.
- Generated-file drift check: regenerate, then fail on any difference.

**L — add**

- Integration tests sharded by committed timings, longest first.
- Opt-in jobs by label for slow or billed work (for example a mobile build or
  a payment sandbox).
- A nightly live check against the real providers. It alerts; it never blocks
  a pull request, so provider flakiness does not stop merges.

## Preview environments (M)

- CI is the only deployer; the hosting platform's own git integration is off.
- Each pull request gets its own isolated data (a database branch, a schema,
  or a throwaway instance), migrated and seeded with fixture accounts that exist
  only in disposable stores.
- Deploy only after the gates pass, then run a smoke test that signs in as a
  fixture account and checks the preview reached its own data.
- Tear the preview and its data down when the pull request closes. A nightly
  sweep deletes only resources CI marked as its own, with a dry-run option.
- Test code refuses to write to any store not marked disposable.

## Branches and releases

| Tier | Branches | Release |
|---|---|---|
| S | `main` only; short-lived task branches squash-merged | Merging deploys; a workflow tags `vX.Y.Z` |
| M | `main`; optional staging host deployed from `main` | A workflow tags a chosen commit and deploys production |
| L | an integration branch → a staging branch → the production branch (names vary) | Promotion is a fast-forward by a workflow; the release pushes the tag and the production branch atomically |

Rules at every tier:

- Squash merges and linear history; nobody pushes to a long-lived branch
  directly. Branch protection enforces it, and a guard workflow closes any pull
  request whose head is a long-lived branch.
- Task branches rebase onto their base; they never merge the base in.
- The deploy job runs migrations, asserts they are current, deploys, then moves
  how the platform switches traffic (an alias, a tag, a blue-green swap).
  Migrations never run inside the application build. Its concurrency group never
  cancels a deploy halfway.
- Release actions — tags, production deploys, infrastructure applies — are
  triggered by a person, never by an agent on its own authority.

Tier L additions:

- **Base branch per project.** One draft pull request per project into the
  integration branch, open until the whole project is accepted. Each ticket is
  a small pull request into that base. The base merges once every ticket is in,
  manual QA has passed on a build, and errors raised on its previews are
  resolved or accepted. Because that base pull request stays a draft, the review
  service runs on each ticket pull request, not on the base.
- **Hotfixes** branch from staging, ship as a patch release, and the
  integration branch is rebased onto staging the same day; the next promotion
  refuses until it has been.

## Versioning

- Semantic versions. Hotfix = patch, feature release = minor, a breaking change
  to an API that shipped clients call = major.
- Tags are the only source of the version, and only production is tagged.
  Release notes are generated from the tag at deploy.
- Never push a tag by hand; the release workflow does it.

## Merge gate

Mergeable means all of these hold on the exact head commit:

1. The local gate passed.
2. Required CI checks are green.
3. Review is clean with zero unresolved threads.
4. The pull request description is complete, including what was not verified.
5. Tier L: evidence is posted on the team ticket.

A red check: read the failing log first. One rerun only for a known flaky
test; red twice is a real failure to investigate.
