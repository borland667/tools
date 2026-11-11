# Architecture and engineering practices

Use for design, implementation, review and fresh guide authoring. Apply these
rules by responsibility and risk, across languages. Select relevant sections
and bind them to the target's code and tools. No framework, directory layout,
object model or service topology is prescribed. A small CLI or library can
satisfy this baseline without an API, container, database or queue.

## Follow established repository practices by default

Use the target repository's existing architecture, ownership boundaries,
language idioms, dependencies, naming/style, test runner, hooks and delivery
conventions. Inspect applicable instructions, project documentation,
configuration and representative code before choosing an approach. Distinguish
an established convention from an isolated legacy example or a documented
exception. Resolve disagreement between docs and code with evidence; neither
automatically establishes that the other is wrong.

Apply the baseline below through those existing mechanisms. Do not replace
tools, impose a preferred architecture, or demand consistency with another
project simply because it is familiar or newer. Across repositories, establish
each repository's practices independently and change only the shared contracts
needed by the task; do not standardize their internals as a side effect.

Challenge a practice when evidence shows a defect, incompatibility, security
problem, requirement conflict or meaningful suitability tradeoff. Before
calling it wrong or recommending a departure, record a proportional rationale
on the bead, with supporting TMP detail only when useful:

```text
Existing practice: <affected convention, owning instruction/config/code>
Problem: <specific failure, constraint or cost in this task's actual context>
Evidence: <reproduction, measurements or traced mechanism; uncertainty>
Reference: <project contract/decision or authoritative documentation, section
            and link/path; relevant version and applicability>
Alternative: <smallest scoped change; compatibility and maintenance tradeoffs>
Verification/disposition: <checks, decision and remaining gaps>
```

For technical best-practice claims, consult the actual primary reference:
language/framework/tool documentation for the target version, an applicable
standard or security advisory, or an established engineering source with
stated applicability. A reproduced defect may be grounded in the project's
own documented contract; it need not acquire an unrelated external citation.
Explain how the source supports the local claim. Separate mandatory constraints
from recommendations, and measured facts from inference. A generic article,
an uninspected link, model opinion, or the phrase "best practice" alone does
not establish that a working repository convention is unsuitable.

If support is missing, label the concern unconfirmed and gather evidence or
retain the established practice; do not turn preference into a blocking finding
or silently replace the convention. Evidence supports a proposal or scoped fix,
not authority to override active instructions, weaken tests/gates, expand the
task or change other repos. Continue within existing authority; obtain a new
decision only where scope or an applicable instruction requires one.

Supporting rationale: Google's engineering review guidance prioritizes
technical evidence over preference and existing consistency where no stronger
rule applies, while allowing demonstrated improvements to code health. Its
[review standard](https://google.github.io/eng-practices/review/reviewer/standard.html)
and [style/consistency guidance](https://google.github.io/eng-practices/review/reviewer/looking-for.html)
support this policy; they do not import Google's tooling, style guides or
approval structure into the target repository.

## Language-independent baseline

- **Implement the current requirement.** Prefer the smallest coherent change
  and the stack's ordinary idioms. Add an abstraction for a current boundary or
  repeated behavior, not hypothetical reuse. A new public module, provider or
  workflow needs a current consumer, owner, reachable integration (including
  registration where required) and proportionate verification in the same
  change. Record future intent as work;
  do not ship speculative scaffolding.
- **Keep responsibilities cohesive.** Separate domain decisions from transport,
  UI and infrastructure where that serves the actual code. Give state mutation
  an explicit owner and route callers through it. Avoid parallel write paths,
  cyclic dependencies and framework details leaking into unrelated code. Reuse
  an implementation; do not duplicate business rules across clients or add a
  wrapper that only renames a function.
- **Make contracts explicit.** Define inputs, outputs, invariants, errors and
  compatibility at shared/public boundaries before changing callers. When
  schemas generate bindings, change the schema first, regenerate in the required
  order and update consumers together. Generated output belongs to its
  generator. A local function does not need a schema or generator merely
  because public protocols do.
- **Keep failure visible.** Use clear names and explicit outcomes. Validate
  untrusted input at its boundary using appropriate types or runtime checks,
  rather than trusting a cast. Preserve error context; do not turn failure into
  empty success. Clean up owned resources on success, failure and cancellation.
  Comments explain constraints and reasons that code cannot express clearly.
- **Bound change cost.** Respect declared module/file budgets and make dependency
  and lifecycle ownership visible. Split by responsibility; avoid a utility
  dumping ground. If the target prohibits growth of an oversized file, extract
  cohesive behavior instead. Do not invent a universal line limit or restructure
  unrelated code to satisfy a preferred pattern.
- **Verify observable behavior.** For new APIs and substantive behavior changes,
  follow [test-first.md](test-first.md): contract/case matrix, initial executable
  tests before production behavior, attributable red, then green and refactor.
  Check outputs, boundary conditions and relevant failures. Mock external
  boundaries; exercise real behavior where practical.
  Use a reproducer that catches a regression rather than tests mirroring private
  implementation. Formatting, lint, types, contracts and builds belong in
  repeatable commands with meaningful failure exits. Use
  [deterministic-gates.md](deterministic-gates.md); prose is not enforcement.
- **Protect data and access.** Keep credentials out of source, logs and fixtures.
  Check authorization where the protected operation is owned. Preserve source
  data in read-only/recovery tasks. Use parameterized queries and safe argument
  passing when input reaches SQL, processes or paths. Distinguish example
  placeholders from real secrets.
- **Keep evidence and docs current.** Update affected contracts, setup and behavior
  docs with code. Resolve code/doc disagreement by checking the implementation
  and intended requirement. Measure before claiming performance gains; name the
  workload, environment and limitations. This baseline grants no publication
  or cross-repo modification authority.

## Apply specifics when the architecture needs them

| Situation | Design consideration |
|---|---|
| UI/client plus an owning service | Route protected state and external operations through the declared service boundary; do not bypass it with direct DB, engine or provider calls. A local single-process tool may own those operations directly. |
| External engines/providers | Keep protocol/SDK details in thin adapters. Centralize configured provider/model routing when supported; do not hardcode model ids or accounts in business logic. Do not create a registry without a current consumer. |
| Authentication and authorization | Use the chosen identity/session owner and check application/resource access at the owning operation. UI visibility is insufficient. This rule does not require a new auth service or identity model. |
| Web/mobile interfaces | Keep client state ownership clear and honor shared contracts. Cover loading, empty and error states, usable labels/focus/keyboard behavior and target accessibility/localization requirements. Do not duplicate domain rules in presentation code. |
| Durable or long-running work | When work must outlive a request/process, use the target's job/lifecycle boundary with durable state, progress and cancellation as required. Persist reusable outputs/provenance through its artifact/storage boundary. Short synchronous operations need no queue or artifact subsystem. |
| Concurrent or remote operations | Define ownership, timeouts, cancellation and cleanup. Retry suitable failures within a finite budget; use idempotency or an explicit duplicate policy for side effects. Check shutdown, partial completion and races. |
| Data and migrations | Make transaction/invariant ownership explicit. Version migrations for the actual store and preserve migration history. Bound queries/results, batch per-record database/remote calls when appropriate, and choose indexes from query evidence. Plan compatibility and recovery for risky changes. |

## Language and tooling specifics

These are starting points, not compulsory tools or a closed list of languages.
Add another profile from that ecosystem's actual runtime, package manager,
compiler/formatter and error/resource model. Do not turn a Python/Web convention
into a requirement for every stack.

| Profile | Applicable specifics |
|---|---|
| Python | State supported interpreter/dependencies. Use appropriate type annotations and boundary validation; keep orchestration thin where services own behavior. Avoid blocking work in async paths. Respect lifecycle/cleanup and package/import rules. Bind actual formatter, lint, type and test commands without assuming tools are installed. |
| TypeScript / JavaScript | Record runtime, package manager and module mode. For TypeScript, follow project strictness and narrow unknown input; do not hide mismatches with unsafe casts or `any`. JavaScript still needs runtime boundary checks. Keep shared DTO/codegen contracts aligned and async errors visible. UI/service ownership applies to web apps, not automatically to Node scripts. |
| Shell / launchers | State dialect and required utilities. Quote path/argument expansions, preserve argument boundaries and handle exit statuses explicitly. Use safe temporary resources and task-specific variables. Destructive tools need explicit input/output boundaries and opt-in; a dry run must not perform the previewed mutation. Do not silently change global configuration. |
| Other languages | Bind language/runtime version, build/package tools, module visibility, null/error handling, ownership/concurrency model and idiomatic verification. Apply shared principles without introducing unrelated Python/Node tools or a framework. |

## Carry applicable rules into a fresh repo

State a concise applicable baseline in the generated guide. Fill these facts
from explicit requirements and implementation evidence:

- Language/runtime versions, package manager and supported environment.
- Module/dependency direction, state owner and actual contract/adapter boundaries.
- Selected profile rules, generated-file ownership and declared size budgets.
- Verification commands, working directories, prerequisites and ordered steps;
  use the contract's gate inventory instead of duplicating it.
- Exceptions with scope, reason, owner and verification. Select relevant rules;
  naming a language does not adopt every optional profile concern.

Unknown choices stay explicit. Do not import another project's guide, paths,
credentials, service names or command inventory. Mechanical safeguards belong
in target-owned gates with tested triggers; contextual tradeoffs remain review
decisions. Findings still follow the evidence and introduced-defect discipline
in [review-agents.md](review-agents.md). This reference does not require legacy
rewrites or turn every suggestion into a blocker.
