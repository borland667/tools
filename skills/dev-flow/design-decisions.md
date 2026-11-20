# Design decisions before implementation

Use during Stage 2 **Design** in [task-intake.md](task-intake.md) for any new
capability or intentional behavior change. The goal is not a design document;
it is to expose the decisions before the agent's first edit locks them in.
Each answer becomes a requirement, an explicit assumption, or a question for
the user. Nothing here grants authority to change architecture, a repo
convention, or the approved scope.

The three-question framing (what problem, what alternatives, what
consequences) comes from ArjanCodes, ["We Are All Managers Now"](https://www.youtube.com/watch?v=xoBm-KUZwHs)
(2026-11-20). Adopt the procedure, not the authority: any claim that a target
practice is unsuitable still needs local evidence and a reference under
[engineering-practices.md](engineering-practices.md).

## 1. What problem are we actually solving?

A feature name is a label. The requirement is the behavior model behind it.
"Track clicks" is not a requirement; it is seven unanswered questions whose
answers produce different systems.

Interrogate anything that records, transforms, aggregates or exposes data:

| Axis | Question the label hides | What the answer changes |
|---|---|---|
| Granularity | Per event, per day, per campaign, per user? | Storage shape, query cost, retention |
| Volume | Typical **and peak** rate of the operation? | Store choice, batching, atomicity, cost |
| Time | Do consumers need *when* it happened, or only *how many*? | Analytical capability, retention |
| Identity | What counts as one occurrence? | Dedup rules, idempotency, retry semantics |
| Consumers | Who reads it, and what decision do they make from it? | Reporting shape, latency, accuracy |
| Failure | What is correct on a duplicate, a retry, an outage, a partial write? | Consistency model, error handling |
| Change | What will this requirement look like in six months? | Whether today's shape is a dead end |

- Before building, ask the agent explicitly: *which requirements here are
  undefined, and which plausible answers would change the implementation?*
  Answer each or record it as a gap.
- A resolved answer becomes a requirement on the bead. An unresolved one stays
  an explicit assumption. Never let an unstated default become code.
- A requirement is settled only when it is observable. Map it to the
  acceptance/case matrix in [test-first.md](test-first.md). "Accurate click
  data" is not a requirement; "a click counts once per campaign per visitor
  per day" is.
- Verify the requested feature is the real problem:
  [task-intake.md](task-intake.md) already requires naming the divergence
  between the request and the need before choosing an approach.

## 2. What are the design alternatives?

Do not accept the first design. Enumerate at least two genuinely different
designs — different representation, write path or ownership, not different
naming — before implementing. Every problem has more than one solution;
picking one without comparing is an unrecorded decision.

```text
Decision:        <what is being chosen>
Requirement drivers: <answers from 1 that constrain it>
Option A:      <representation + write path + read path>
  Gains:       <…>
  Hidden cost: <…>
  Fails when:  <…>
Option B:      …
Choice:        <chosen design, often a hybrid not on the list>
Rejected:      <one line per option, tied to a requirement driver>
Reversibility: <two-way / one-way, and what undoing it costs>
```

- Each option states the cost it hides, not only its benefit.
- The right answer is frequently a hybrid nobody offered. Daily counter
  documents per campaign is a counter design plus a time dimension: neither
  raw events nor a bare total fit the requirement, the combination does.
- Rejection reasons are tied to a requirement driver from step 1, not taste.
- Keep the decision and one-line rationale on the bead; put the full
  comparison in `TMP_FILES/plans/` under [tmp-docs.md](tmp-docs.md).

Worked example — recording clicks on a shortened tracking link:

| Option | Gains | Hidden cost | Fails when |
|---|---|---|---|
| One record per click | Detailed analytics, filtering, per-event search | Storage and query growth at millions of rows; some stores cannot absorb the write rate | Per-event detail is genuinely needed |
| Single counter | Trivial, no storage growth | Needs atomic increments for concurrent clicks; loses all history | Any time-based or per-segment reporting |
| List of timestamps | Total plus per-period analytics, no extra records | Field grows unbounded; document/row-size limits; slow appends | Volume is large |
| Daily counter document (chosen) | Total and per-day analytics, bounded record count | No sub-day detail; requires a per-day key and atomic increment | Minute-level attribution is required |

None of these is "the" design. Each optimizes a different requirement driver,
and the choice is only defensible once those drivers are written down.

## 3. What are the consequences?

Zoom out from the data model. Before committing, check:

- Write volume at **peak**, not average (a campaign running during a major
  event is a different workload than a normal week).
- Analytical query cost, and whether caching is required to make it affordable.
- Concurrency and atomicity of the write path.
- Behavior when the store, network or a dependency is temporarily unavailable.
- Cost at the assumed scale versus the real scale — capacity you pay for
  permanently to handle a spike you see twice a year.
- Security exposure of whatever is now being recorded.
- How the outcome is observable after release: the success signal in
  [task-intake.md](task-intake.md).
- The migration path if the assumption turns out wrong.

Architecture follows from the data model: the representation choice decides
whether a SQL or document store fits, whether writes need batching, and what
hosting is viable. Say so explicitly rather than leaving it implied.

## 4. Reversibility decides where the attention goes

Not every decision deserves review. Spend human attention where undoing is
expensive; let the agent decide the rest.

| Two-way — agent decides | One-way — decide before Build |
|---|---|
| Internal helper names, function decomposition, an added index, an advisory log, logging verbosity | Storage engine, data representation and retention model, hosting platform, a public contract another system reads, an ownership boundary, anything already written to durable data |

- **One-way decisions**: alternatives enumerated before Build, then surfaced
  to the user with `bd human <id>` before implementation. A standing autonomy
  grant does not settle them. Promote the lane to deep when a decision is
  hard to reverse, even if the diff is small.
- **Two-way decisions**: the agent chooses, records the choice and its reason
  on the bead, and continues. Do not escalate.
- Reversibility includes data. A schema change is reversible; six months of
  rows written under it usually is not. State which you are making.
- Choosing a hosted platform is a bundle of implicit one-way decisions: it
  picks the database, hosting, and often the front/back-end stack for you.
  Record each as a repo-contract row with its reversal cost instead of
  treating the platform choice as a neutral convenience.

## Phase exit

Design exits only when the bead shows: requirement answers or explicit gaps,
at least two compared alternatives for any non-trivial representation or
ownership choice, a reversibility classification for each decision, and
escalation or explicit approval for the one-way ones. Until then the phase
stays open — speculative implementation is not permitted.
