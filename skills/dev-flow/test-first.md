# Test-first behavior development

Use for new APIs and substantive changes to observable behavior, in any language.
Plan and implement the initial relevant tests before production behavior. Keep
checks proportional: documentation-only edits and behavior-preserving mechanical
changes use the applicable existing checks rather than inventing API tests.

Begin with the applicable initial phase in [task-intake.md](task-intake.md):
Design supplies the intended contract and case map; Diagnose supplies the
supported failure mechanism and regression target. A written test plan alone
does not satisfy the executable tests-ready checkpoint below.

## Contract and initial case coverage

At Plan, define the public contract before writing its implementation: inputs,
outputs, status/error semantics, invariants, side effects and compatibility.
Resolve material ambiguity instead of encoding an assumed product decision in
a test. For APIs, include method/path, request/response schema, authorization
and resource/tenant ownership when applicable. Do not invent universal error
codes or require every service concern for a simple local function.

Map each requirement and known material risk to cases on the bead or in the
repo's existing test specification. Use this compact record per case/group:

```text
Requirement/risk: <contract clause and why it matters>
Cases: <normal, boundary, invalid input, failure or ordering>
Expected: <response and observable state/side effects; source of expectation>
Test: <file/test id and unit, contract or integration level>
Execution: <command, prerequisites, deterministic fixtures>
Evidence: <planned | red for intended reason | green; input/code identity>
Gap: <none, not applicable with reason, or unresolved risk/owner>
```

Use equivalence classes and boundaries to cover the agreed behavior broadly
before coding. Consider these API dimensions; mark genuinely inapplicable
ones rather than adding machinery just to test it:

| Dimension | Initial cases when relevant |
|---|---|
| Normal behavior | Minimal/full valid requests, exact response shape and required headers, persistence or other expected effects |
| Input and bounds | Missing versus null versus empty, wrong types, malformed body, invalid enums, min/max and immediately outside bounds, size limits, encoding/Unicode where accepted |
| Identity and access | Missing/invalid/expired credentials, forbidden role, wrong owner/tenant, identifier substitution, no unauthorized effects or sensitive-field leakage |
| Resource state | Missing resource, empty collection, duplicate/conflicting state, valid and invalid state transitions |
| Queries and collections | Filter/sort rules, default and maximum page sizes, invalid/expired cursor where defined, stable ordering and pagination boundaries |
| Failures and atomicity | Dependency failure/timeout, validation after partial work, transaction rollback, error mapping, no partial or repeated effects |
| Repetition and concurrency | Duplicate requests, idempotency-key reuse/conflicting payloads, retries and concurrent changes where the contract promises safety |
| Compatibility and lifecycle | Existing callers/older optional-field shapes, schema serialization, cancellation, cleanup or job progress if the operation supports them |

The initial matrix must cover every agreed requirement and known material edge
class, with executable tests for applicable cases. No percentage of line
coverage proves this. Record remaining uncertainty; critical contract or test
gaps block the affected implementation. "Most edge cases" is a risk-based
coverage target, not a claim that all possible inputs have been enumerated.

## Tests before production behavior

1. Establish the relevant existing baseline, test runner and isolated fixtures.
   Add only the minimal harness/interface scaffolding needed to run the tests;
   do not implement the intended behavior under the guise of test setup.
2. Write the initial contract/acceptance and applicable boundary/failure tests
   from the matrix before implementing production behavior. Use unit tests for
   pure decisions and request-level tests through actual routing, validation,
   authorization and serialization for an API. Exercise real persistence and
   transaction behavior in isolated integration tests when those are promised.
   Mock external providers at their boundary, not the endpoint under test or
   the authorization/persistence behavior a test claims to establish.
3. Check expected outcomes against the contract, including forbidden effects.
   The lead or an authorized reviewer checks the matrix, fixtures and assertions;
   normal independent review requirements still apply. Flash may suggest missing
   cases, but neither its expected answers nor the implementation are the oracle.
   For high-risk rules, use a representative wrong behavior/mutation where
   practical to demonstrate that the relevant test detects it.
4. Run the new tests before behavior implementation. Record actual failures
   caused by the specified missing/wrong behavior, with test and source identity.
   An import error, broken fixture, absent dependency or unreachable test runner
   does not establish red evidence. An unimplemented route's wrong response can
   be valid red evidence when the test reaches the real app and asserts the
   intended contract. Existing satisfied cases may already pass; require red
   evidence for each new behavior group that needs implementation.

**Tests-ready checkpoint:** the matrix and initial applicable tests exist,
expectations have been checked, and the suite executes with attributable red
evidence. Missing prerequisites leave this checkpoint pending for the affected
behavior. Continue independent preparation, not an invented passing result.

## Implement, keep green, then refactor

Implement the smallest coherent behavior that makes the tests pass, then run
the affected regression/integration suite. Refactor with tests green. Add a
test first when a new edge case or defect is discovered; an initial broad suite
does not freeze future coverage or require predicting private implementation.

Do not edit an expectation merely to match the implementation, replace a real
boundary with a mock, skip/quarantine a required case or narrow test selection
to obtain green. A legitimately changed requirement needs a documented contract
decision, independently checked expectations, and refreshed evidence. Review
test changes as carefully as production changes.

**Green checkpoint:** every required case passes on the resulting implementation,
with relevant regressions and repo gates passing. A required suite with no
collected tests, unexpected skips/expected failures, unavailable prerequisites
or missing integration coverage does not count as green. Configure deterministic
selection/collection checks using the repo's runner; fail meaningfully on gaps.

## Bind the hard gates

Record concrete commands, test selection, prerequisites and blocking triggers
in the repo contract/gate inventory; use [deterministic-gates.md](deterministic-gates.md)
to implement and prove the actual registration path. Run focused tests during
each behavior change; run the required affected/full suites before integration.
Fast offline tests can run at commit/push; service-dependent integration tests
belong in a configured local/CI tier. Never silently skip them or weaken an
existing hook because a suite is intentionally red during preparation.

The red checkpoint is recorded development evidence, not a hook success, a
failing-test commit requirement or permission to merge red code. Required gates
must be green at their declared delivery trigger. The skill alone installs no
hooks, CI jobs or branch protection; distinguish procedure from enforcement.

Retain baseline, test-case identities, expected-result rationale, observed red,
observed green, final input identity and any coverage gaps on the bead. Apply
[evidence-and-learning.md](evidence-and-learning.md) after fixes or rebases.
Passing tests support only what their assertions and exercised boundaries prove;
required independent review and supervised finding confirmation remain in force.
