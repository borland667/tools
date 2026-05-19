# lmstudio_claude_bridge

## Purpose

Small local bridge for running `Claude Code` against `LM Studio` without
changing Claude Code's source. It forwards Anthropic-compatible `/v1/*`
requests to LM Studio, rewrites Anthropic-style default model names to local
LM Studio model ids, and keeps Claude Code's model picker populated from
LM Studio's live model list.

Use this when:

- You want Claude Code to run locally against LM Studio instead of Anthropic.
- You want to pick among locally loaded models in the app instead of hardcoding
  one model id.
- You want a lightweight bridge with no extra runtime dependencies beyond Node.

Do NOT use this for:

- OpenAI-only backends that do not expose Anthropic-compatible `/v1/messages`.
- Hosted/remote deployments that need real auth, tenancy, or hardened network
  security.

## Requirements

- Node 18+.
- LM Studio local server running.
- A Claude Code build that accepts `ANTHROPIC_BASE_URL`,
  `ANTHROPIC_API_KEY`, and `ANTHROPIC_AUTH_TOKEN`.
- Local filesystem access to Claude Code's global config file so the bridge can
  update `additionalModelOptionsCache`.

Optional:

- `LMSTUDIO_API_KEY` if your LM Studio server expects one.
- `LMSTUDIO_MODELS_FILE` for fixture-based testing without a live LM Studio
  server.

The bridge is standard-library Node only.

## Quick Start

```bash
cd /Users/borland/tools/lmstudio_claude_bridge
./run_claude_with_lmstudio.sh
```

That launcher:

- syncs LM Studio models into Claude Code's global config,
- starts the bridge on `http://127.0.0.1:1245`,
- exports the local Claude Code env vars,
- defaults the primary model mapping to
  `qwen3.6-35b-a3b-abliterated-heretic-mlx` unless you override it,
- keeps the helper/default side path on `qwen/qwen3-coder-30b` unless you
  override it,
- runs `claude`.

## Common Usage Patterns

### Run Claude Code against LM Studio

```bash
cd /Users/borland/tools/lmstudio_claude_bridge
./run_claude_with_lmstudio.sh
```

### Target a different LM Studio host or port

```bash
LMSTUDIO_BASE_URL=http://127.0.0.1:1234 \
CLAUDE_LMSTUDIO_BRIDGE_PORT=1246 \
./run_claude_with_lmstudio.sh
```

### Force preferred main and helper models

```bash
CLAUDE_LMSTUDIO_MAIN_MODEL=qwen3-coder-30b-abliterated \
CLAUDE_LMSTUDIO_SMALL_MODEL=qwen2.5-coder-7b-instruct-abliterated \
./run_claude_with_lmstudio.sh
```

### Use the Claude Code-safe default model mapping

```bash
./run_claude_with_lmstudio.sh
```

By default, the launcher pins both `CLAUDE_LMSTUDIO_MAIN_MODEL` and
`CLAUDE_LMSTUDIO_SMALL_MODEL` to values that favor Claude Code compatibility:

- `CLAUDE_LMSTUDIO_MAIN_MODEL=qwen3.6-35b-a3b-abliterated-heretic-mlx`
- `CLAUDE_LMSTUDIO_SMALL_MODEL=qwen/qwen3-coder-30b`

That keeps the model picker populated with all LM Studio models, routes the
main/default Anthropic-style alias path to the largest abliterated model, and
keeps helper-side calls on a model that behaved more predictably on LM Studio's
Anthropic-compatible `/v1/messages` path.

### Sync model options without starting the bridge

```bash
node bridge.mjs sync-models
```

### Test with a fixture instead of LM Studio

```bash
LMSTUDIO_MODELS_FILE=./models.fixture.json \
CLAUDE_GLOBAL_CONFIG_FILE=/tmp/claude-lmstudio-test.json \
node bridge.mjs sync-models
```

## Arguments and Options

There are no required positional arguments.

`bridge.mjs` commands:

- `serve`: sync models, then start the local proxy server.
- `sync-models`: fetch LM Studio models and write them into Claude Code's
  global config cache.
- `print-env`: print the recommended Claude Code environment variables.
- `--help`: show usage.

Environment variables:

- `LMSTUDIO_BASE_URL`: LM Studio base URL, default `http://127.0.0.1:1234`
- `LMSTUDIO_API_KEY`: optional API key/header value for LM Studio
- `CLAUDE_LMSTUDIO_BRIDGE_HOST`: bind host, default `127.0.0.1`
- `CLAUDE_LMSTUDIO_BRIDGE_PORT`: bind port, default `1245`
- `CLAUDE_LMSTUDIO_MODEL_SYNC_INTERVAL_MS`: periodic sync interval, default `30000`
- `CLAUDE_LMSTUDIO_REQUEST_TIMEOUT_MS`: upstream timeout, default `600000`
- `CLAUDE_LMSTUDIO_MAIN_MODEL`: override chosen main model id
- `CLAUDE_LMSTUDIO_SMALL_MODEL`: override chosen helper/small model id
- `CLAUDE_LMSTUDIO_MODEL_MAP`: JSON map of explicit model rewrites
- `CLAUDE_GLOBAL_CONFIG_FILE`: override Claude Code global config path
- `CLAUDE_CONFIG_DIR`: alternate Claude config root
- `LMSTUDIO_MODELS_FILE`: fixture JSON path for testing

Launcher-exported Claude Code env:

- `ANTHROPIC_BASE_URL`
- `ANTHROPIC_API_KEY`
- `ANTHROPIC_AUTH_TOKEN`
- `CLAUDE_CODE_DISABLE_EXPERIMENTAL_BETAS=1`
- `ENABLE_TOOL_SEARCH=false`
- `CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1`
- `CLAUDE_CODE_DISABLE_THINKING=1`

## Input and Output

Input:

- HTTP requests from Claude Code to the local bridge.
- LM Studio model-list responses from `/api/v1/models` or `/v1/models`.
- Claude Code global config JSON from `~/.claude/.config.json` or
  `~/.claude.json` unless overridden.

Output:

- proxied HTTP responses from LM Studio,
- updated `additionalModelOptionsCache` in Claude Code's global config,
- console logs describing sync results and model rewrites.

Side effects:

- Writes Claude Code's global config file when LM Studio model options change.
- Starts a local HTTP listener while `serve` is running.

## Internal Behavior Summary

1. `sync-models` or `serve` fetches the LM Studio model list.
2. The bridge normalizes those models into Claude Code picker options.
3. It chooses `mainModel` and `smallModel`, preferring `abliterated` or
   `uncensored` variants when present.
4. It writes the normalized options into Claude Code's
   `additionalModelOptionsCache`.
5. On `serve`, it listens locally and forwards `/v1/*` traffic to LM Studio.
6. For `/v1/messages`, it rewrites Anthropic-style default model ids to the
   chosen LM Studio ids when needed.
7. It also exposes `/healthz`, `/sync-models`, and
   `/api/claude_cli/bootstrap` helper endpoints.

## Safety Notes

- The bridge only targets localhost-style usage by default.
- It does not change Claude Code source files.
- The launcher avoids Claude Code flags that are not present on older
  installations and relies on the local bridge environment variables instead.
- `ENABLE_TOOL_SEARCH=false` is a conservative default because many local
  proxies do not support Anthropic's tool-reference features cleanly.

## Known Limitations

- Expects LM Studio to provide Anthropic-compatible `/v1/messages`.
- Model selection is heuristic when LM Studio metadata is sparse.
- Thinking is disabled by default for compatibility across local models.
- This is a local bridge, not a general-purpose auth or multi-user gateway.

## Validation Checklist

- `node bridge.mjs --help` prints the expected commands.
- `node bridge.mjs sync-models` populates `additionalModelOptionsCache`.
- `./run_claude_with_lmstudio.sh` starts Claude Code with the bridge env.
- `LMSTUDIO_MODELS_FILE=./models.fixture.json node bridge.mjs sync-models`
  picks the expected default models.

## Maintenance Notes

- Update this doc when bridge commands, env vars, default model heuristics, or
  launcher behavior change.
- Keep `/Users/borland/tools/README.md` in sync with the folder name and script
  description.
