# Models by task and subagent role

Recommendation snapshot: 2026-11-11. These are starting choices, not a benchmark
ranking or a change to installed defaults. Honor the repo's established model,
profile and data-handling bindings first. Confirm account/client availability
and actual identity before dispatch. Recommendations do not grant quota,
credentials, model calls or new permissions.

## Frontier options

The following names/IDs were checked against current primary documentation.
Availability in an API does not establish availability in a CLI or subscription.
The role assignments below are workflow recommendations inferred from those
documented strengths; qualify them on representative target tasks.

| Model | ID | Suggested place in the workflow |
|---|---|---|
| GPT-6.1 Sol | `gpt-6.1-sol` | General technical work and coordination |
| GPT-6 Astra | `gpt-6-astra` | Difficult reasoning/escalation |
| GPT-6.1 Terra | `gpt-6.1-terra` | Visual inspection, scoped edits and concise writing |
| GPT-6 Luna | `gpt-6-luna` | Focused repeatable tasks |
| Claude Opus 5.5 | `claude-opus-5-5` | Agentic implementation and complex work |
| Claude Sonnet 5.5 | `claude-sonnet-5-5` | Speed-oriented coding alternative |
| Claude Fable 5.2 | `claude-fable-5-2` | Demanding reasoning/long-horizon escalation |
| Claude Haiku 5.5 | `claude-haiku-5-5` | Extraction, classification and routing |
| Gemini 4 Carbon | `gemini-4-carbon` | Optional reasoning/coding comparison candidate |

Sources: [OpenAI models](https://learn.chatgpt.com/docs/models?surface=cli),
[OpenAI selection guidance](https://developers.openai.com/api/docs/guides/model-selection),
[Claude models](https://platform.claude.com/docs/en/models/overview),
[Gemini models](https://aistudio.google.com/docs/models).
Gemini needs a separately approved, qualified harness/account; the current
worker launcher accepts Claude/Codex only. Do not substitute it into that CLI.

## Role recommendations

Choose roles for their responsibility, not one agent per row. Combine roles
where appropriate under [review-agents.md](review-agents.md); retain required
independence and one writer per checkout.

| Task / role | Frontier recommendation | Local use and limits |
|---|---|---|
| Coordinator / task framing | Sol; Opus is an alternative | Flash/Splash only for bounded dispatch/status under an approved packet and supervision; full writer lifecycle still needs qualification |
| Architect / Design / planner | Opus; escalate to Astra or Fable for material ambiguity or cross-repo tradeoffs | Flash may challenge a supplied design; no qualified local primary architect or plan approver |
| Troubleshooter / debugger | Sol or Opus; Astra for difficult causal analysis | Flash can inspect a bounded trace or reproduction packet; its hypothesis needs confirmation |
| Test designer / test author | Sol or Opus, with expectations checked against the contract | Flash may suggest missing cases; no local test oracle or primary test author currently qualified |
| Coder / implementation | Opus preferred; Sol alternative; Sonnet candidate for well-scoped throughput work | No local primary writer recommended under current policy; Sushi is a candidate for isolated repair drafts, not autonomous edits |
| Correctness / contract reviewer | Sol when Opus built; Opus when Sol built; otherwise select a different qualified hosted model | Flash/Splash is an advisory second opinion; cannot replace required hosted coverage |
| Security / data / concurrency reviewer | Astra or Opus when different from builder; specialist coverage still follows repo requirements | Local findings are suggestions, never sole required security review |
| Deep adversarial reviewer | Astra or Fable if distinct from builder and every other review model; Carbon is a further candidate | Flash may challenge a small packet but cannot satisfy required hosted/deep independence under current policy |
| Documentation / indexing / extraction | Luna or Haiku for bounded source-based work; Terra for visual checks; Sol/Opus for substantive technical decisions | Flash can draft source summaries; Sushi extraction/indexing is an unqualified candidate, and all summaries need source checks |

A conservative initial pairing preserves the workflow's preferred shape:
Opus implements, Sol supplies hosted review, and qualified Flash/Splash adds
optional advisory coverage. Add a distinct Astra/Fable adversarial pass for
deep work when available and authorized. These are role recommendations, not
proof that every pairing outperforms alternatives or is available on this host.

## Local models and qualification

The current evidence supports a narrow local recommendation rather than a
local replacement for every frontier role:

- **Qwen3.8 Flash Next through oMLX/Splash:** preferred supervised local
  defect/edge-case second opinion when the exact host profile is qualified.
  The evaluated artifact was `Qwen3.8-Flash-Next-GSQ-RCO-Q2_0`; resolve the
  exact served id, checkpoint/quantization and backend from host setup. An id
  with a new suffix is not automatically the same qualified execution path.
- **Qwen3.5-9b-Sushi-Coder-RL-MLX:** candidate for small isolated repair
  drafts and inexpensive source processing. Existing repair fixtures do not
  qualify an autonomous writer; false-positive review and weak regression
  generation evidence prevent selecting it as the default reviewer/test author.
- **Other local checkpoints and raw strata transports:** evaluation candidates
  only until the actual transport, tools, task quality and containment are
  checked. Parameter count, quantization label or a coding-oriented name does
  not establish role suitability.

Keep measured scores, corpus identity, artifacts, current server inventory and
exact host settings in private `local.md`, not portable defaults. Existing
pilots are small synthetic checks; incomplete architecture plans, unreliable
regression inputs and strict-format failures remain qualification limits.
Draft summaries, new local coordinator behavior and real-repo build roles need
their own evidence. See [local-second-opinions.md](local-second-opinions.md)
for bounded calls and supervised finding confirmation.

## Effort, budgets and escalation

Start with each model/client's documented default effort. As a workflow
heuristic, use lower/default effort for extraction and mechanical work, and
medium/high effort for design, diagnosis, test expectations and difficult review
where supported. Increase effort or use the named escalation model when actual
gaps justify it; stronger effort is not a correctness guarantee. Provider effort
labels are not interchangeable. Existing local Flash calls keep their host's
disabled-thinking and request/token/wall limits; do not copy frontier settings.

Bound the job by relevant context, allowed tools, wall/turn/output budgets and
an observable result. Split work at coherent boundaries instead of assuming
a large advertised context fits the whole repo. Model passes stay out of
deterministic hooks and CI gates. Check source truth and actual gate results.

If authentication, quota, model identity or capability is unavailable, report
the gap. Use only an already authorized alternative bound for the task, or ask
for the missing choice; never silently change account, endpoint or model.
A proposed escalation is a new recorded job, not an automatic retry loop.
No recommendation here changes global harness/server configuration.

## Bind and keep the recommendation current

Record on the bead per job: role; primary/approved alternate; harness/profile;
requested and reported model/provider (unknown stays unknown); checkpoint and
transport for local work; effort and finite budgets; permissions; evidence and
qualification scope. A profile or coordinator name alone proves neither hosted
execution nor model independence. Hermes and Herdr use the same policy.

For standard/deep review, verify a different hosted model from the builder;
deep adversarial coverage must also differ from every other review model.
If identity cannot be established, required coverage remains pending or needs
an explicit approved alternative under [review-agents.md](review-agents.md).
Fresh context and a different harness alone do not meet that requirement.

Recheck current primary docs and host availability before changing a binding,
especially after model retirement, alias/transport changes or provider updates.
Use representative frozen tasks and deterministic acceptance checks to compare
choices; retain failures and measure review/repair effort as well as generation
time. Qualify one role/path at a time. Recommendations remain advisory;
Beads is primary and required deterministic gates cannot be waived by a model.
