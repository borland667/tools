# Acceptance exercise

Use this reference at Verify when the change has a surface a user or calling
system can reach. Tests and a reviewed diff establish that the code does what
its author intended; this stage establishes that the delivered behavior is
actually reachable and usable through its real entry point. Neither replaces
the other, and neither waives [deterministic gates](deterministic-gates.md).

This is a verification procedure, not a separate role or agent. It adds no
authority: a helper performing it keeps project files and Git read-only under
invariant 2 and reports findings on the bead.

## When it applies

| Change | Exercise |
|---|---|
| User-reachable interface (UI, CLI, editor/tool integration) | Required at the lane's depth |
| Calling-system interface (HTTP route, RPC, queue consumer, scheduled job, hook, exported library entry point) | Required through that actual entry point, not a unit-level caller |
| Internal refactor, formatting, docs or a change with no reachable surface | Not applicable, with a reason on the bead |

Record the applicability decision at Frame or Plan, beside the
acceptance-to-verification mapping, so the exit condition is not discovered at
the end. A change can be partly applicable: exercise the reachable criteria and
mark the rest inapplicable individually.

A reachable surface behind an unreleased flag is still exercised, in the state
the change ships: with the flag in its delivered default, and again enabled when
the task's acceptance covers the enabled path.

## Procedure

1. **Derive the flows from the bead,** not from the implementation or from
   imagination. Each flow traces one acceptance criterion from its real entry
   point to its observable outcome. Do not invent flows the task never promised;
   an unmapped flow that looks broken is a finding about scope, recorded as such.
2. **Establish the instance and its identity.** Start the target at the revision
   under verification using the repo contract's binding. Record the revision,
   environment, configuration and data source. An instance built from different
   content verifies nothing about this change.
3. **Exercise each flow end to end** through the real entry point. Reach the
   outcome, not a page or a response that merely renders. Confirm the effect
   where it actually lands — persisted state, emitted message, written file,
   downstream call — and distinguish a live path from a stubbed or mocked one.
4. **Exercise the states the flow can enter,** proportional to the lane: empty
   and boundary input, rejected input, an unavailable dependency, and the
   recovery or retry path where the change owns one. Confirm the caller or user
   can tell what happened and what to do next.
5. **Record the result** in the Verify block from
   [evidence-and-learning.md](evidence-and-learning.md) — criterion, planned
   check, observed procedure and result, state, evidence, gap. Use
   `Observed: not run + reason` for anything not exercised. Bulky captures go to
   the bound scratch location under [tmp-docs.md](tmp-docs.md); the bead keeps
   the resumable state.

| Lane | Depth |
|---|---|
| Fast | The primary flow for the change's main acceptance criterion |
| Standard | Every applicable acceptance criterion's flow, plus rejected input on the paths the change owns |
| Deep | Those, plus boundary input, dependency failure, recovery paths and any flow a triggered review role reaches (data, contract, security, deploy) |

## Findings

A defect found here is a finding like any other. Apply the Stage 6 disposition:
fixed, filed as a child bead, or rejected with a reason recorded on the bead.
Advisory findings may be rejected without a fix, never without a reason.

- A reproducible defect in the change under verification is fixed with a
  regression test that fails on the defect first, under
  [test-first.md](test-first.md). An exercised defect with no test is a gap, not
  a pass, even after the behavior appears to work.
- A pre-existing defect outside this task becomes a linked bead
  (`--deps discovered-from:<id>`), not an incidental repair.
- The builder, or an authorized writer, applies fixes. A read-only helper
  reports; it does not edit. After any fix, re-exercise the affected flows and
  refresh the evidence under the revision rules in
  [evidence-and-learning.md](evidence-and-learning.md) — an earlier exercise does
  not carry forward across changed behavior.

## Limits

- **An unavailable instance is a recorded gap, not a pass.** If the target
  cannot be run — missing environment, credential, device, service or data — say
  which flows went unexercised and why. Required unexercised criteria keep the
  task open unless the repo or user explicitly accepts the limitation, which is
  recorded with its remaining risk.
- **A completed exercise is not acceptance by itself.** It supports the criteria
  it actually covered, at one revision, in one environment.
- **It is not a substitute for the test suite, the gates or independent review.**
  Observations here are the lead's or a helper's; they do not satisfy the
  different-model and adversarial coverage in
  [review-agents.md](review-agents.md).
- **It is not a coverage metric.** A percentage, a passing unrelated suite or a
  count of flows clicked does not establish that a criterion is demonstrated.

**Exit:** every acceptance criterion with a reachable surface has current
exercise evidence at the tested revision, or a recorded reason it does not
apply; defects are fixed with regressions, linked, or rejected with a reason.

Provenance: the case for exercising the running software as a distinct step came
from [gstack](https://github.com/garrytan/gstack)'s QA phase, by way of
[dev-workflow-skill](https://github.com/jahonn/dev-workflow-skill) (both MIT).
The procedure, records and limits above are this skill's own; the upstream
coverage target, reviewer auto-fix and root-level phase artifacts are
deliberately not adopted.
