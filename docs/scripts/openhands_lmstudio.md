# run_openhands_with_lmstudio.sh

## Purpose

Launch `OpenHands` against a local `LM Studio` server without retyping the
required `LLM_MODEL`, `LLM_BASE_URL`, and `LLM_API_KEY` environment variables
each time.

Use this when:

- `LM Studio` is exposing its local OpenAI-compatible API,
- you want `OpenHands` to use a local model instead of a hosted provider,
- you want a repeatable launcher from this repository.

## Requirements

- `OpenHands` CLI installed and available on `PATH`
- `curl`
- `LM Studio` local API server reachable at `http://127.0.0.1:1234/v1` by
  default, or a custom `--base-url`
- An LM Studio model that can handle agent-style coding loops

Optional:

- `$HOME/.lmstudio/bin/lms` if you want the helper to try starting LM Studio with
  `--start-lmstudio`

## Quick Start

```bash
cd <repo-root>
scripts/run_openhands_with_lmstudio.sh
```

## Common Usage Patterns

### Open the normal OpenHands CLI

```bash
scripts/run_openhands_with_lmstudio.sh
```

### Start with a task

```bash
scripts/run_openhands_with_lmstudio.sh -- --task "Summarize this repository"
```

### Use headless mode

```bash
scripts/run_openhands_with_lmstudio.sh -- --headless --task "Reply with hello"
```

### Target a different local model

```bash
scripts/run_openhands_with_lmstudio.sh \
  --model openai/google/gemma-4-31b
```

### Start LM Studio if the API is down

```bash
scripts/run_openhands_with_lmstudio.sh --start-lmstudio
```

## Arguments and Options

### Required

- No positional arguments are required.

### Optional

- `--model <id>`: override the OpenHands model id. The default is
  `openai/qwen/qwen3-coder-30b`.
- `--base-url <url>`: override the LM Studio base URL. The default is
  `http://127.0.0.1:1234/v1`.
- `--api-key <key>`: override the API key sent to LM Studio. The default is
  `lmstudio`.
- `--start-lmstudio`: if the API is unreachable, try starting it with
  `$HOME/.lmstudio/bin/lms server start`.
- `--`: stop parsing launcher flags and pass the remaining arguments straight
  to `openhands`.
- `-h`, `--help`: show help text.

All additional arguments after `--` are passed through to `openhands`
unchanged.

## Input and Output

Inputs:

- an already running LM Studio API server, or a locally installed `lms` CLI
- the chosen model id
- any extra `OpenHands` CLI flags

Outputs:

- an `OpenHands` CLI session configured to call the LM Studio base URL
- error messages when `OpenHands` or LM Studio are unavailable

Side effects:

- may start LM Studio's server if `--start-lmstudio` is used
- does not modify OpenHands settings files directly

## Internal Behavior Summary

1. Validate that `openhands` and `curl` are available.
2. Probe the LM Studio `/v1/models` endpoint.
3. Optionally run `lms server start` if the endpoint is down and
   `--start-lmstudio` is set.
4. Export `LLM_MODEL`, `LLM_BASE_URL`, and `LLM_API_KEY`.
5. Execute `openhands --override-with-envs` with any extra arguments.

## Safety Notes

- The script only targets a local OpenAI-compatible endpoint by default.
- It does not download models or install OpenHands.
- It does not alter OpenHands' persistent config files on its own.

## Known Limitations

- The default model id is intentionally opinionated for this machine and may
  need `--model` on other systems.
- This helper only wires up the LLM connection; OpenHands still manages its own
  sandboxing and conversation storage.
- If your OpenHands installation ignores env overrides or changes config file
  formats in a future release, this helper may need an update.

## Validation Checklist

- `scripts/run_openhands_with_lmstudio.sh --help` shows the expected options.
- `curl http://127.0.0.1:1234/v1/models` succeeds before launch, or
  `--start-lmstudio` starts the local server.
- `scripts/run_openhands_with_lmstudio.sh -- --task "Reply with hello"` starts
  OpenHands with LM Studio-backed env vars.

## Maintenance Notes

- Update this doc if the default model, launcher flags, or LM Studio startup
  behavior changes.
- Keep the repository `README.md` and `scripts/README.md` in sync with the
  helper name and usage.
