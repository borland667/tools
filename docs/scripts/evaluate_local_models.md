# Local model pilot

`scripts/evaluate_local_models.py` runs a fixed, bounded local inference pilot.
The HTTP runner uses Python 3.9+ standard library only. It contacts configured
loopback endpoints, never installs dependencies or executes model-produced code,
and writes evidence to a new output directory. It does not change model settings,
unload shared models or automatically approve a model for dev-flow.

## Configure and run

Copy `local_model_eval/config.example.json` to a private task location and fill
the advertised model id, endpoint, engine version/settings and checkpoint files.
API credentials, if needed, are read only from the named `api_key_env`; do not
put secrets in configuration or prompts. Use one engine at a time to avoid
competing for memory and GPU time. Model loading can evict idle models according
to the server's own settings; inspect shared service activity before a run.

```bash
python3 scripts/evaluate_local_models.py --help
python3 -B scripts/evaluate_local_models.py \
  --config /path/to/private-pilot.json \
  --output /path/to/new-results-directory \
  --only local-candidate --trials 3 --max-tokens 768 \
  --timeout 180 --max-seconds 1800
```

The default stages are `compat tasks performance generation reasoning`. Select them with `--stages`.
Default context targets are 128, 8192 and 32768 tokens; these are approximate
construction targets, not exact lengths. Read actual prompt/decoded/cache token
counts from engine usage. Each performance input is followed by an identical
request to expose possible prefix reuse; fresh prefixes do not clear OS caches.
Do not call a first request cold unless loading/cache state establishes it.
The long-context payload is repeated low-entropy text followed by a short
instruction: it measures prefill/cache behavior, not long-context code quality.
The generation stage asks for a long numeric sequence and caps output at 256
tokens (or the lower CLI cap), so decode throughput is measured beyond the
two-token context-check answer. Compare actual output counts and finish reasons.
Numeric decode speed does not establish typical coding throughput.

Limits: 1–5 trials, at most 2048 requested output tokens, at most 600 seconds per
request and 3600 seconds per run. A wall-clock deadline beats continued token
progress. The output path must be new; use a path outside Git or a gitignored
directory. Scores failing are model results, not runner crashes; transport or
engine errors return a nonzero runner exit. Inspect completeness and errors in
the report rather than equating process completion with model success.

## Ten developer fixtures

`local_model_eval/fixtures.json` is the versioned corpus. Prompt text and scoring
data are separate; the oracle is never sent to the model.

- Five review cases: three planted defects and two correct-code controls.
  Closed-vocabulary line/kind matching records missed bugs and false positives.
- Two constrained repair cases: numeric expressions are interpreted through a
  bounded AST grammar and tested against fixed input/output examples. Imports,
  attribute access and arbitrary Python/shell execution are not allowed.
- One regression-input case: all expected results must match the stated input
  contract, and at least one must distinguish the known mutant from the oracle.
- Two architecture plans: only JSON structure is checked mechanically. Quality
  stays `manual_review_required` against the recorded rubric; a model does not
  grade itself.

Semantic correctness and strict JSON formatting are distinct: fenced JSON may
be recovered for task scoring, with the formatting violation still recorded.
These small synthetic tasks are not a general coding benchmark, full patch/test
generation trial or proof of production quality. Deterministic repetitions are
not independent statistical samples. Freeze the corpus when comparing engines;
do not tune a prompt on failures and report that as the original comparison.

## Compatibility, timing and resources

HTTP probes cover plain/streamed responses, requested JSON output, a mock
read-fixture tool roundtrip, and early client disconnect. The mock never reads a
real file or executes a model command. Client disconnect is not proof that a
server stopped GPU work; `server_abort_verified: false` remains explicit.
Offline tests exercise timeouts, streaming chunk assembly and request limits.
The separate reasoning stage requests low-effort thinking on one arithmetic
prompt and preserves reasoning/content channels. A model that ignores the
request, truncates before its answer or exposes no reasoning remains explicit;
an empty channel does not prove separation. It is not part of task scoring.
The optional `cancellation` stage isolates early cancellation without running
the other compatibility probes; the raw Strata adapter checks its `DONE cancel`
response to `STOP`. HTTP still records client disconnect separately from backend
abort verification.

Reports preserve raw responses, prompts, timing and errors; manifests include
runtime/configuration, corpus/source hashes, sampled checkpoint fingerprints
and best-effort model status. Checkpoint hashes cover only the first/last MiB,
not every weight byte. Model-load timings are separate when the engine reports
them. TTFT for reasoning/tool events and visible content are distinct.

Process-tree RSS is sampled during generation. For HTTP this is a shared service
tree, may include other work and may double-count mappings. It is not peak GPU
allocation and excludes earlier load peaks. Swap/VM snapshots provide context;
missing metrics remain unavailable, not zero. Record external load, hardware,
precision, draft, context and cache differences before comparing numbers.

## Optional strata-mlx transport

The external engine and its dependencies are installed separately. The bundled
`local_model_eval.strata_bridge` adapts its token line protocol, using that
environment's `transformers` tokenizer in local-files-only mode. The adapter is
not a production HTTP API and does not implement native tools. Run `tasks` and
`performance`; qualify HTTP/harness integration separately through a real server.

Configure a `strata_line` engine with a `command` array of literal arguments:
Use trusted engine arguments; the runner executes the array without a shell.

```json
{
  "name": "strata-candidate",
  "kind": "strata_line",
  "model": "checkpoint-label",
  "load_timeout": 300,
  "checkpoint_files": ["/path/to/shard-1.gguf", "/path/to/shard-2.gguf"],
  "command": [
    "/path/to/strata/.venv/bin/python", "-B", "-m", "local_model_eval.strata_bridge",
    "--tokenizer", "/path/to/local-tokenizer", "--",
    "/path/to/strata/strata-mlx", "--serve", "--native", "/path/to/shard-1.gguf",
    "--mtp", "/path/to/local-draft", "--expert-profile", "off"
  ]
}
```

Run from this tools checkout so the optional environment can import the adapter,
or provide this checkout in its task-owned `PYTHONPATH`. Only test-owned engine
process groups are stopped on timeout/exit. Adapter startup, actual engine INFO,
tokenizer behavior and limitations are recorded. The same GGUF with different
drafts, precision, prompt templates or memory budgets compares deployment
configurations, not isolated engine kernels. Consult the pinned engine's
[upstream documentation](https://github.com/yibie/strata-mlx) for setup/protocol.

## Validation

```bash
python3 -B -m unittest discover -s tests/local_model_eval -v
python3 -B -m unittest discover -s tests/dev_flow -v
```

Tests use temporary loopback servers and processes; network-restricted sandboxes
must permit those local fixtures. No model or running inference service is
required. For a real harness probe see
[evaluate_model_harness.md](evaluate_model_harness.md).
