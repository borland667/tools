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
| Coordinator / task framing | Sol; Opus is an alternative | Flash/Splash or Qwen3.8 27B for supervised supplied-state decisions; neither is qualified for the full writer lifecycle; avoid 9B for gate/practice decisions |
| Architect / Design / planner | Opus; escalate to Astra or Fable for material ambiguity or cross-repo tradeoffs | Flash may challenge a supplied design; no qualified local primary architect or plan approver |
| Troubleshooter / debugger | Sol or Opus; Astra for difficult causal analysis | Flash can inspect a bounded trace or reproduction packet; its hypothesis needs confirmation |
| Test designer / test author | Sol or Opus, with expectations checked against the contract | 27B can draft an API case matrix at a separately sized output budget; Flash may suggest missing cases. No local test oracle or primary test author qualified |
| Coder / implementation | Opus preferred; Sol alternative; Sonnet candidate for well-scoped throughput work | Flash and Qwen3.8 9B can draft tiny isolated repairs for checked inputs; 27B and Sushi remain alternatives; no local primary writer or autonomous edits qualified |
| Correctness / contract reviewer | Sol when Opus built; Opus when Sol built; otherwise select a different qualified hosted model | Flash/Splash preferred for bounded advisory packets; Qwen3.8 27B is an alternative after path checks; neither replaces required hosted coverage |
| Security / data / concurrency reviewer | Astra or Opus when different from builder; specialist coverage still follows repo requirements | Local findings are suggestions, never sole required security review |
| Deep adversarial reviewer | Astra or Fable if distinct from builder and every other review model; Carbon is a further candidate | Flash may challenge a small packet but cannot satisfy required hosted/deep independence under current policy |
| Documentation / indexing / extraction | Luna or Haiku for bounded source-based work; Terra for visual checks; Sol/Opus for substantive technical decisions | Qwen3.8 9B for short supplied-fact summaries; Flash or 27B alternatives. Indexing/retrieval and Sushi extraction remain unqualified; check every summary against its source |

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
- **Qwen3.8 27B OrcaRouter 4-bit:** alternative supervised reviewer for small
  supplied code packets and source-summary drafts. Workflow-decision probes
  support supervised supplied-state assistance, not tool-using coordination.
  Architecture and diagnostic gaps prevent primary planner/debugger selection.
- **Qwen3.8 9B 8-bit:** first local option for short source-fact summaries
  and tiny isolated repair drafts with checked expectations. Correct-code
  false positives and missed workflow blockers prevent default reviewer or
  coordinator selection. Fast replies do not compensate for those errors.
- **Qwen3.5-9b-Sushi-Coder-RL-MLX:** candidate for small isolated repair
  drafts and inexpensive source processing. Existing repair fixtures do not
  qualify an autonomous writer; false-positive review and weak regression
  generation evidence prevent selecting it as the default reviewer/test author.
- **Other local checkpoints and raw strata transports:** evaluation candidates
  only until the actual transport, tools, task quality and containment are
  checked. Parameter count, quantization label or a coding-oriented name does
  not establish role suitability.

### Qwen3.8 role-probe findings

The 2026-11-11 host evaluation compared the three variants above on frozen
tool-free packets covering coordination, architecture, diagnosis, repair,
review, test inputs, API test design, repository fit, gates and documentation.
Deterministic oracles and blinded rubric assessment were separate from JSON
format, schema validity and completion checks. These are provisional helper
recommendations for the tested paths, not family-wide rankings.

- Flash and 27B handled the small code-review controls without the correct-code
  false positives seen in 9B. Flash was faster on this host and remains the
  preferred supervised local reviewer; 27B is a useful alternative.
- All three faithfully summarized the supplied documentation facts. Prefer
  9B when a small model is useful; Flash was faster in this particular run.
  This does not qualify repository search, retrieval or long-document synthesis.
- All three passed the supplied-state resume decision. Only Flash and 27B
  passed both the repository-practice and stale-test/failing-gate decisions.
  None was tested operating the coordinator, tools, accounts or writer lifecycle.
- Baseline architecture and diagnostic answers had material gaps. A separate
  low-thinking/larger-token arm improved a schema-rollout plan for Flash and
  27B, but did not establish reliable durable-job planning or debugging tests.
  Keep frontier leads for design, diagnosis and test expectations.
- All baseline API test designs exceeded the output cap. A separate larger
  disabled-thinking capacity check completed all three answers: 27B met the
  packet rubric/structure threshold, Flash exceeded the list limit, and 9B
  omitted concurrency coverage and exceeded the list limit. All three missed
  explicit tests-ready/red-before-implementation/green steps. Use 27B only for
  a case-matrix draft checked by the lead; no executable API tests were built
  or run, and no primary test-author qualification follows.

The common baseline used a small disabled-thinking output budget; a separate
low-thinking arm also changed the token budget. Do not pool them or attribute
differences to reasoning alone. Keep the API-capacity follow-up separate too;
truncation is not a categorical claim that a model cannot design tests.
Prompt-only JSON compliance does not measure grammar-constrained output.
Two repeats of tiny synthetic fixtures are not independent samples or an
end-to-end build, tool-use, security or primary test-author qualification.
Keep exact scores, budgets, corpus identity, raw answers, independent grades,
timing/resources and follow-up results in private `local.md` and retained
ignored evidence. Required deterministic gates and hosted review still apply.

## Additional installed-model evaluation candidates

A read-only oMLX API inventory on 2026-11-11 identified the shortlist below.
The Qwen3.8 text paths now have the limited role-probe evidence above; other
groups and untested modalities remain proposed evaluation roles. No entry is
an approved local primary agent. Metadata identifies an exposed path/type,
not correctness, tool reliability or runtime memory capacity.
Keep exact served ids, variants, configured aliases and inventory snapshots in
the host's private `local.md`; these family-level options are portable.

| Model / group | Role to evaluate first | Evidence boundary |
|---|---|---|
| Qwen3.8 9B 8-bit | Short source summaries and tiny checked repair drafts | Text probes measured; false-positive review and workflow-decision misses limit the role |
| Qwen3.8 27B OrcaRouter 4-bit | Alternative supervised code review and source summaries; planning critique only | Text probes measured; VLM metadata does not qualify vision or primary architect/test-author roles |
| Qwen3.8 Flash Next Q2_0 | Preferred supervised defect/edge-case opinion and source summaries | Current tested alias confirmed through runtime status as Splash; new aliases/checkpoints still need path checks |
| Qwen3.6 35B-A3B 4-bit | Compare code/debugging/review drafts against the Qwen3.8 candidates | Native VLM candidate; missing Splash draft affects that optional engine, not proof that native serving is unavailable |
| Qwen3.6 27B Heretic bf16 | Heavy comparison candidate for difficult supplied analysis | API reports VLM; record actual resource needs before considering a regular role |
| Qwen3-Next 80B-A3B Instruct / Thinking | Alternative code-analysis and planning-critique packets | API reports LLM; compare both variants empirically, without assuming Thinking is better |
| Gemma 4 12B coder fine-tune | Isolated patch drafts and review comparison | API reports VLM; name/distillation labels do not prove coding competence or frontier-model identity |
| Sushi 9B / Qwimi 9B distill | Small repair/source-processing drafts | Preserve Sushi's prior limitations; Qwimi is unqualified and is not hosted Opus because its name contains Opus |
| Gemma 4 E4B | Bounded extraction, document and visual-context drafts | API reports VLM; validate exact input modality, correctness and tool behavior |
| Qwen3-VL 4B / Huihui variant | Screenshot/OCR/UI-description candidates | VLM metadata only; check actual image inputs and prefer a controlled comparison, not a naming-based ranking |
| VisualQuality R1 7B | Advisory visual-quality critique | VLM metadata does not qualify code review or prove a design-quality judgment correct |
| Qwen3 Embedding / Reranker 0.6B | Repository-context retrieval and candidate-passage ordering | Use embedding/rerank endpoints, not chat/subagent roles; no retrieval index or pipeline is installed by this guide |
| HiDream O1 Image Dev entry | Inspect model integrity and actual task support before assigning a role | API currently reports a VLM; image generation is unverified despite the name |

Exclude hidden DFlash draft/helper entries from standalone subagent selection.
Do not infer exact architecture, safety properties or quality from community
names such as Uncensored, Heretic, Opus or Fable. Confirm the actual checkpoint,
configuration and intended task before testing or using it.

For API discovery, inspect the running server's OpenAPI first, then authorized
GET inventory/status/model-metadata endpoints. Cross-check public served ids
against raw models, hidden helpers, aliases and selected/compatible engines.
An advertised VLM type, reasoning option or context value is not an exercised
capability; null metadata is unknown, not proof of lack of support. Estimated
weight size is neither peak runtime memory nor context/KV-cache capacity.

Use the gap-specific priorities below to compare the remaining candidates
against the tested Qwen3.8 paths on frozen representative packets. These are
test priorities, not a quality ordering. Separately test vision and
retrieval specialists on their actual modalities/endpoints. Run only authorized
bounded inference, serially on the shared server; inventory inspection alone
does not load models or establish task competence. Existing writer/hosted-review
restrictions remain unchanged until qualification and an explicit policy change.

Keep measured scores, corpus identity, artifacts, current server inventory and
exact host settings in private `local.md`, not portable defaults. Existing
pilots are small synthetic checks; incomplete architecture plans, unreliable
regression inputs and strict-format failures remain qualification limits.
Larger summaries, tool-using local coordination and real-repo build roles need
their own evidence. See [local-second-opinions.md](local-second-opinions.md)
for bounded calls and supervised finding confirmation.

## Candidates for the remaining gaps

Research snapshot: 2026-11-11. The priorities here are inferences from the
measured failures, current publisher documentation and available conversions;
they are not additional benchmark results or new role approvals. Publisher
scores use different harnesses, budgets and sometimes modified task sets.
Do not combine them into a cross-model ranking or transfer full-precision
scores to a community fine-tune or quantization.

| Observed gap | Candidate responsibility | Evidence needed before promotion |
|---|---|---|
| Architecture misses ordering, owning-operation authorization or crash windows | Systems planner and adversarial design reviewer | Producer/consumer release and rollback checks; provider-side duplicate policy, durable progress, cancellation/cleanup and operation-bound authorization |
| Debugger asserts unseen implementation and supplies risks instead of tests | Causal investigator and regression designer | Distinguish fact/hypothesis, test alternatives, controlled reproduction, both tenant orders and cache states, correct content and authorization assertions |
| API drafts miss concurrency or test-first execution | Test designer plus an execution-capable builder | Executable assertions for every contract case, controlled overlap, intended red before behavior, final green and tests that reject relevant mutants |
| JSON fences, invalid output or list-limit violations | Structured-output adapter and deterministic validator | Probe actual schema/grammar enforcement for the exact engine; validate types, fields and list bounds separately from semantic correctness |
| Stale evidence or failing gates omitted from decisions | Coordinator assisted by durable state and tools | Bind evidence to the final diff, reject failed/missing checks, test resume and denied actions; a model's decision never replaces the gate |
| Tool use and full builds untested | Harness and model together | Tool-call/result correlation, reasoning history, cancellation, read/write containment, command exits and actual file/test effects |

### Installed candidates to evaluate first

1. **Qwen3.6 35B-A3B:** first general coding/debugging/test-draft challenger.
   Its [publisher card](https://huggingface.co/Qwen/Qwen3.6-35B-A3B)
   describes repository coding and preserved thinking, with agent evaluations.
   That makes it relevant to iterative investigation, not a proven replacement
   for a systems architect. Test the actual MLX 4-bit path; its optional missing
   Splash draft does not disqualify native serving.
2. **Qwen3-Next 80B-A3B Thinking:** first installed reasoning-focused
   architecture/diagnosis challenger. The [card](https://huggingface.co/Qwen/Qwen3-Next-80B-A3B-Thinking)
   specifies thinking-only behavior and potentially longer reasoning. A
   disabled-thinking comparison is inapplicable; predeclare a separate finite
   profile with enough budget for reasoning and the final answer.
3. **Qwen3-Next 80B-A3B Instruct:** compare workflow decisions, supplied
   architecture constraints and tool-oriented packets with the Thinking
   checkpoint. Its [card](https://huggingface.co/Qwen/Qwen3-Next-80B-A3B-Instruct)
   specifies non-thinking-only behavior. It is a separate checkpoint, not a
   toggle on the Thinking model, and neither is **Qwen3-Coder-Next**.
4. **Gemma 4 12B coder fine-tune:** a narrower repair/function-level challenger.
   The [fine-tuner's card](https://huggingface.co/yuxinlu1/gemma-4-12B-coder-fable5-composer2.5-v1)
   describes Python algorithmic tasks and solutions filtered through existing
   tests. That does not establish generation of new test oracles, distributed
   systems design or performance of the installed MLX conversion. Verify its
   native thought channel and chat template rather than reusing Qwen parsing.

Keep **27B Heretic bf16** as a lower-priority, resource-heavy comparison:
the [conversion](https://huggingface.co/TheCluster/Qwen3.6-27B-Heretic-MLX-bf16)
comes from a modified source, so higher precision does not isolate quantization
or prove better reasoning. **Qwimi 9B** is a lower-priority reasoning experiment:
its [card](https://huggingface.co/trjxter/Qwimi3.5-9B-Kimik2.6-Opus-Distill-MLX-8Bit)
reports training metrics and explicitly lacks a separate full evaluation of
that MLX quant. Retain Sushi's observed limitations. Teacher names, refusal
modifications and training loss do not establish hosted identity or capability.
The visual specialists and embedding/reranker entries address other tasks;
retrieval may improve repository context but cannot explain away failures in
the already supplied, self-contained packets.

### Additional open-weight candidates

These require checking installation, provenance and runtime support on the
target host. A published MLX conversion is not a qualified oMLX backend or
agent harness. Keep exact conversions, revisions and measured resource needs
in private host records; download or installation follows task authority.

| Candidate | Gap it could address; research basis | Main qualification limit |
|---|---|---|
| [Qwen3-Coder-Next](https://huggingface.co/Qwen/Qwen3-Coder-Next) | First additional coding-agent candidate: trained for tool use, long tasks and recovery from execution failures | 80B total/3B active, non-thinking-only; distinct from general Next; verify parser, containment and real edits/tests |
| [GLM-4.7-Flash](https://huggingface.co/zai-org/GLM-4.7-Flash) | Smaller alternative family for iterative debugging, tools and regression drafts; publisher reports agent/code results and preserved-thinking settings | 30B-A3B; exact conversion and multi-turn reasoning/tool history unqualified; not the latest GLM family |
| [Qwen3-Coder-30B-A3B-Instruct](https://huggingface.co/Qwen/Qwen3-Coder-30B-A3B-Instruct) | Smaller dedicated coding-agent comparison when the 80B checkpoint is impractical | Tool protocol and agent scaffold still require validation; no architecture/test-first guarantee |
| [Devstral Small 2 24B](https://huggingface.co/mistralai/Devstral-Small-2-24B-Instruct-2512) | Alternative family explicitly aimed at codebase exploration and multi-file edits | Local weights remain a candidate; the hosted model is marked deprecated in current Mistral docs; check current lifecycle before choosing an API |
| [Gemma 4 31B IT](https://huggingface.co/google/gemma-4-31B-it) | Official general reasoning/vision checkpoint as a different-family control, rather than assuming the 12B coding fine-tune generalizes | New weight/runtime qualification; native thought-channel handling and task quality remain untested |
| [gpt-oss-120b](https://developers.openai.com/api/docs/models/gpt-oss-120b) | Heavy open-weight reasoning/tool-use comparison for architecture and causal analysis | Significant residency plus context overhead; Harmony formatting, channels and tool continuations must be verified |
| [Mistral Small 4 119B](https://huggingface.co/mistralai/Mistral-Small-4-119B-2603) | Heavy alternative combining instruction, reasoning and coding capabilities | 119B total/6.5B active; memory and parser support must be checked before inference |

Mistral's [offline guide](https://docs.mistral.ai/vibe/code/cli/offline-models)
still recommends Devstral Small 2 for local use, while its
[hosted model page](https://docs.mistral.ai/models/devstral-small-2-25-12)
marks it deprecated. Keep local checkpoint suitability separate from API
lifecycle. For gpt-oss, the official
[implementation guide](https://developers.openai.com/cookbook/articles/gpt-oss/verifying-implementations)
explains Harmony and reasoning/tool-history requirements; an OpenAI-compatible
HTTP URL alone does not establish correct serving.

Active parameters describe per-token computation, not the full weights that
must reside in or be accessed from memory. Compare actual conversion sizes
with the current server budget, context/runtime overhead and other work.
Keep heavy models serial; physical RAM and a model-card context limit do not
guarantee usable capacity. Do not change shared memory limits to fit a candidate.

### Hosted candidates and evaluation controls

Use the existing **Opus 5.5 / Sol** pairing as practical controls, **Astra**
for demanding causal/systems analysis, and **Fable 5.2** when Opus at higher
effort still falls short. These role hypotheses follow the current
[OpenAI guidance](https://learn.chatgpt.com/docs/models?surface=cli) and
[Claude selection guidance](https://platform.claude.com/docs/en/models/overview),
not our local packet scores. A frontier control on the same tasks helps reveal
fixture or harness problems before attributing every miss to model capacity.

[Gemini 4 Carbon](https://aistudio.google.com/docs/models/gemini-4-carbon)
is a further complex-engineering/reasoning control requiring its own approved
account/harness. [Qwen3.8-Max](https://qwen.ai/blog?id=qwen3.8),
[GLM-5.3-Flash](https://huggingface.co/zai-org/GLM-5.3-Flash) and
[DeepSeek-V4.1-Flash](https://huggingface.co/deepseek-ai/DeepSeek-V4.1-Flash)
are additional provider comparisons, not routine fully resident local choices
based on their large published architectures. The Flash suffix is not a
small-memory guarantee. Extreme quantization or special offload would be a
separate unqualified experiment. Existing worker-launcher/provider boundaries
and account bindings remain unchanged; new providers need separate integration.

### What the next comparison must establish

- Preserve the original corpus/results as a regression set. Add held-out
  variations across languages and realistic repository changes, including
  clean controls; do not tune on the only known failure examples.
- Separate a common deployment-budget comparison from model-native profiles.
  Unsupported modes are inapplicable, not quality failures. Record actual
  reasoning/final channels, stop reasons, output budgets and parser behavior.
  Publisher multi-hour/token-heavy results are not a 90-second local promise.
- For diagnosis, separately test explicit `regression_tests` wording against
  the original `regressions` field. Ambiguous terminology is a possible
  confound, not an established explanation or permission to overwrite scores.
- For API work, require executable tests and observed intended assertion
  failures before implementation, then green and relevant mutation checks.
  Missing required auth, tenant isolation, concurrency or test-first evidence
  blocks that role even when a partial-credit rubric total is high.
- Probe structured decoding separately from prompt-only JSON compliance.
  The exact engine must enforce the requested schema, including supported
  bounds; always validate independently. As the
  [Structured Outputs guide](https://developers.openai.com/api/docs/guides/structured-outputs)
  explains, well-structured output can still contain semantic mistakes.
- Run tool-using qualification only in an authorized isolated fixture with
  observable reads/writes, denied-action controls, cancellation and finite
  turn/wall/token budgets. Reuse the outstanding real-repository/harness work
  instead of counting another tool-free answer as successful agent operation.
- Make tests-ready, final-diff gate checks and ownership/permission checks
  workflow conditions under [test-first.md](test-first.md) and
  [deterministic-gates.md](deterministic-gates.md). A stronger model may follow
  them better, but it cannot replace their enforcement. Compare confirmed
  quality and human repair effort before promoting one role/path at a time.

## Effort, budgets and escalation

Start with each model/client's documented default effort. As a workflow
heuristic, use lower/default effort for extraction and mechanical work, and
medium/high effort for design, diagnosis, test expectations and difficult review
where supported. Increase effort or use the named escalation model when actual
gaps justify it; stronger effort is not a correctness guarantee. Provider effort
labels are not interchangeable. Existing local Flash calls keep their host's
disabled-thinking and request/token/wall limits; do not copy frontier settings.
Do not reuse a short-review output cap for a complete API case matrix. A
separately recorded, bounded budget or smaller contract packets need their own
qualification; increasing tokens or enabling thinking alone did not establish
complete test-first behavior in these probes. Check structure as well as content.

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
