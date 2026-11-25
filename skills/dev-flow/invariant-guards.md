# Invariant guards

A hard invariant is a rule whose violation is a bug even when the code works:
a data boundary, what may reach a client, an identifier that must never be
exposed, what must never be logged. Prose does not enforce it. Use this
reference when a task adds or changes such a rule, or when review keeps
finding the same violation.

A guard is an ordinary test or lint rule in the repo's normal suite, so the
fast verify command and CI both run it. The repo's agent guide lists each
invariant with its guard, or marks it unguarded so the gap is visible (repo
contract row *Hard invariants*). Registration, triggers and proving the
trigger fires follow [deterministic-gates.md](deterministic-gates.md).

## Every guard needs three things

1. **A self-test.** Plant a violation in an isolated fixture (a temporary
   directory, a synthetic source file, a migration that undoes an earlier
   one) and show the guard fails with a useful message. A guard never seen to
   fail is not evidence.
2. **A minimum-match assertion.** A sweep asserts it inspected at least the
   number of items it expects. Otherwise a broken pattern, a moved directory
   or a renamed function makes it pass by checking nothing.
3. **Declared inputs.** When a build cache keys tasks by their own inputs, a
   guard that reads files outside its package declares those files. Otherwise
   the cache replays an old pass after the violating change.

Prefer the language's real resolver, parser or AST over regular expressions.
A text match narrows silently when code is renamed or reformatted.

## Patterns

| Pattern | Guards rules like | How |
|---|---|---|
| Reachability walk | Server-only code never ships to a client; no vendor dependency in a shared package | Start at each client entry point, follow imports with the real resolver, skip type-only edges, fail on reaching a forbidden module and print the import chain. Catches transitive paths a per-file lint rule misses |
| Sweep with a shrinking allowlist | One data store per module; no raw query naming another domain's table | Scan all sources for the forbidden co-occurrence. Existing violations go in a keyed allowlist that may only shrink; the test fails when an entry is no longer needed |
| Compile-fail fixtures | A cross-boundary call does not typecheck | Lines that must stay type errors, marked so an unused marker fails the build |
| Migration replay | Primary key type; replication or row-security settings; columns a table must have | Read migrations in order, fold them into the final schema state, compare with what the code declares. Catches a later migration undoing an earlier one |
| Two-source contract diff | Every env var declared everywhere it is needed; a registry and a skip list agree | Load both sets from their real files and fail on any difference, naming the side each item is missing from |
| CI config as test input | Only the deploy job holds the production key; integration tests block real providers | Parse the workflow files and assert which jobs hold which secrets or settings |
| Seeded-canary redaction | No secrets or personal data in logs or error reports | Push unique fake secrets and personal data through the real logging or error SDK into a capture transport; fail if any canary appears in the bytes that would leave the process |
| Fresh-process import probe | No work at import time | Import modules in a child process with network stubbed and env removed; assert no calls were made |
| Build-artifact check | A native binary or data file is present in the deploy bundle; a heavy dependency is absent from a client bundle | Run after the real build; inspect its output or metafile |
| Generated-file drift | Generated types and clients match their source | Regenerate in CI, then fail on any difference |
| Endpoint sweep | Every route validates its input and checks authorization | Enumerate the router or route table; assert each entry has an input schema and the intended auth wrapper, with an explicit list of deliberate public routes |

## Tools by language

Starting points, not requirements. Bind to what the target already uses, and
verify a tool works in the target before naming it in the contract.

| Pattern | TypeScript / JavaScript | Python | Go | JVM / Kotlin |
|---|---|---|---|---|
| Reachability walk | dependency-cruiser, or a resolver walk in a test | import-linter | `go list -deps` in a test | ArchUnit layered rules |
| Sweep with allowlist | TypeScript compiler API | `ast` module | `go/packages` | Konsist, ArchUnit |
| Compile-fail fixtures | `@ts-expect-error` | mypy or pyright with unused-ignore warnings | a build-tagged fixture package | compile-testing |
| Seeded-canary redaction | the error SDK's test transport | logging handler capture | `slog` test handler | Logback list appender |

## Where to start

For a repo with none, the three cheapest guards with the widest reach are the
env contract diff, seeded-canary redaction and the endpoint sweep. Add a
guard to a task only when the task's own requirement or a recurring review
finding calls for it; file the rest as linked work.
