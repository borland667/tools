# Choose the initial phase

Use after Frame and before implementation planning. Task type chooses the
initial phase; risk lane chooses its depth and review coverage. Record both
on the bead. A fast task still needs the applicable phase, but a short bead
entry can cover its phase and plan. Do not require a design document, extra
agent or another approval for a routine decision already within scope.

| Task type | Initial phase | Example |
|---|---|---|
| New capability or intentional behavior change | Design | New API, feature, integration or changed public contract |
| Defect, regression or unexplained behavior | Diagnose (troubleshooting/debugging) | Wrong result, failing test, crash or unexpected latency |
| Mixed repair and new behavior | Diagnose, then Design for the intentional change | Find a failure's cause before deciding a replacement contract |
| Mechanical maintenance with no behavior decision or unexplained failure | Not applicable, with a reason | Formatting, known rename or a routine documentation correction |

A file or issue label alone does not determine the type. Documentation can
define new behavior; a feature request can hide a defect. If intent is unclear,
inspect the existing contract and observations first. Ask only when a material
product/scope decision remains. Reclassify when evidence changes the task;
keep the reasoning and any lane change on the bead.

## Design: establish what to build

- Establish the target's existing practices before choosing an approach. Reuse
  its architecture, tooling and conventions; justify any departure with the
  evidence/reference protocol in [engineering-practices.md](engineering-practices.md).
- State the problem, intended users/callers, outcome, non-goals and constraints.
  Inspect the existing implementation and contracts where they exist. Separate
  verified facts, explicit requirements and unresolved assumptions.
- Define observable behavior and acceptance: inputs/outputs, errors, state and
  side effects, boundaries and compatibility as relevant. For an API, specify
  method/path and request/response semantics before implementation.
- Choose the smallest coherent approach using
  [engineering-practices.md](engineering-practices.md). Compare alternatives
  when there is a real tradeoff; record state/dependency ownership and relevant
  migration, failure or recovery considerations. Do not invent architecture
  layers or infrastructure merely to fill a design.
- Map requirements and known material edge cases to planned tests and checks
  using [test-first.md](test-first.md). State expected results from the agreed
  contract, not from model guesses or the future implementation.
- Resolve decisions needed for the next implementation slice. Existing user
  intent or standing authority can settle a decision; this checkpoint is not
  a mandatory human sign-off. Keep material unresolved choices explicit and
  continue only independent work until they are resolved.

**Exit:** a coherent intended contract, scoped approach, acceptance/case map and
resolved decisions for the next slice, recorded on the bead. Link substantial
supporting design in `TMP_FILES/plans/` under [tmp-docs.md](tmp-docs.md). Plan
then turns that design into ordered tests, implementation and verification work.
Tests are implemented and observed red before production behavior, not replaced
by the design's test plan.

## Diagnose: establish why it fails

- Capture expected versus actual behavior and the source of that expectation.
  Record triggering inputs, affected revision/environment, reproduction steps
  and impact. Reproduce the symptom or collect discriminating evidence for an
  intermittent failure; unavailable reproduction is an explicit gap.
- Establish the relevant baseline and trace the failing boundary through actual
  callers, state and dependencies. Inspect logs/data only within authorized
  access. Distinguish an application defect from a broken fixture, dependency,
  configuration or test harness; do not change requirements to explain a failure.
- State one causal hypothesis at a time. Use the smallest scoped experiment
  that can support or reject it. Isolated fixtures or temporary instrumentation
  may help; speculative production fixes are not diagnostic evidence. Revisit
  assumptions when attempts stop adding information.
  If a worker must write a reproducer, fixture or temporary instrumentation,
  assign a bounded diagnostic job with explicit files, expected observations
  and cleanup/retention rules. Such experiments may precede the phase exit;
  they do not authorize a speculative repair or count as accepted delivery.
- Record the supported cause, its evidence, remaining uncertainty, affected
  boundary and proposed repair. Define how the original symptom and relevant
  regressions will be checked. For a code defect, plan a regression test that
  fails on the faulty behavior before applying its fix when practical.

**Exit:** evidence supports a causal explanation and a scoped repair with an
observable verification path. Without that evidence, remain in Diagnose and
record the next discriminating check; do not mark a speculative fix ready to
build. Link substantial analysis in `TMP_FILES/analysis/` or `incidents/`.
If the repair needs an intentional behavior/architecture choice, run Design
before Plan. A simple repair restoring an established contract can go to Plan
without a second design exercise.

An investigation-only request can end with the supported findings, limits and
next action; Build/Integrate/Release may be inapplicable. If urgent mitigation
is authorized, record it separately from confirmed diagnosis and preserve its
scope and verification needs. A successful mitigation is not root-cause proof.

## Carry the phase forward

Keep a compact record on the bead: task type and lane, selected phase, contract
or symptom, observations/decision and supporting identity, exit evidence or
remaining gap, and next action. This is task state, not a second TMP ledger.
An authorized architect/planner or debugger may contribute; the lead or chosen
coordinator owns the decision. No extra agent is required by the phase name.

Plan consumes the phase's result; Build starts after the applicable phase exit
and plan. Build may prepare its workspace and initial tests; production behavior
implementation waits for the tests-ready checkpoint. If verification contradicts
the diagnosis or reveals a material design gap, return to that phase, update
the plan/case map and refresh affected evidence. A phase label, model opinion
or passing unrelated suite never waives
[deterministic gates](deterministic-gates.md). Refresh evidence under
[evidence-and-learning.md](evidence-and-learning.md).
