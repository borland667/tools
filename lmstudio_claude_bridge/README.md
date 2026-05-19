# LM Studio Claude Bridge

This bridge is for running Claude Code against LM Studio locally while still getting selectable model entries inside the app's model picker.

LM Studio already exposes an Anthropic-compatible `POST /v1/messages` endpoint with streaming and tool use, so this bridge does not try to reimplement inference. Instead it adds the two things Claude Code is missing in a local setup:

- it proxies `/v1/*` requests to LM Studio
- it syncs LM Studio's available models into Claude Code's cached `additionalModelOptionsCache`, which is what the picker reads

It also rewrites Anthropic-family defaults like `claude-sonnet-*` and `claude-haiku-*` to LM Studio models, so the app can boot and side-queries still work.

## Files

- [bridge.mjs](/Users/borland/tools/lmstudio_claude_bridge/bridge.mjs)
- [run_claude_with_lmstudio.sh](/Users/borland/tools/lmstudio_claude_bridge/run_claude_with_lmstudio.sh)

## Requirements

- Node 18+ (tested with Node 24)
- LM Studio local server running

LM Studio docs used for this bridge:

- [Anthropic Compatibility Endpoints](https://lmstudio.ai/docs/developer/anthropic-compat)
- [Messages](https://lmstudio.ai/docs/developer/anthropic-compat/messages)
- [List Models](https://lmstudio.ai/docs/developer/openai-compat/models)

## Quick Start

1. Start LM Studio's local server.
2. Run:

```bash
cd /Users/borland/tools/lmstudio_claude_bridge
./run_claude_with_lmstudio.sh
```

That launcher will:

- sync LM Studio models into Claude Code's global config
- start the bridge on `http://127.0.0.1:1245`
- set the recommended env vars
- default Claude Code's primary model mapping to `qwen3.6-35b-a3b-abliterated-heretic-mlx` unless you override it
- keep the helper/default side path on `qwen/qwen3-coder-30b` unless you override it
- launch `claude`

## Manual Usage

Sync model options only:

```bash
node bridge.mjs sync-models
```

Start the bridge:

```bash
node bridge.mjs serve
```

Print the env block to use manually:

```bash
node bridge.mjs print-env
```

Recommended env when using the bridge:

```bash
export ANTHROPIC_BASE_URL=http://127.0.0.1:1245
export ANTHROPIC_API_KEY=lmstudio
export ANTHROPIC_AUTH_TOKEN=lmstudio
export CLAUDE_CODE_DISABLE_EXPERIMENTAL_BETAS=1
export ENABLE_TOOL_SEARCH=false
export CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1
export CLAUDE_CODE_DISABLE_THINKING=1
```

The launcher avoids Claude Code flags that are unavailable in older installations and relies on environment variables only. On this machine, that keeps the bridge compatible with Claude Code `2.1.74`.

## Model Selection

By default the bridge chooses:

- `mainModel`: the best general LLM candidate it can infer from LM Studio's model list
- `smallModel`: the best smaller candidate for Haiku-like helper calls

When LM Studio exposes `abliterated` or `uncensored` variants, the bridge now prefers those as the default base models before falling back to the regular variants.

For Claude Code specifically, the included launcher pins the primary/default mapping to `qwen3.6-35b-a3b-abliterated-heretic-mlx` and the helper mapping to `qwen/qwen3-coder-30b` unless you override them. That keeps the picker dynamic while routing the main conversation to the largest abliterated model we verified on LM Studio's Anthropic-compatible `/v1/messages` path, while leaving helper/side work on a faster model that also behaves reliably there.

You can override both:

```bash
export CLAUDE_LMSTUDIO_MAIN_MODEL=qwen3-coder-30b
export CLAUDE_LMSTUDIO_SMALL_MODEL=qwen2.5-7b-instruct
```

You can also provide explicit rewrites:

```bash
export CLAUDE_LMSTUDIO_MODEL_MAP='{"claude-sonnet-4-6":"qwen3-coder-30b","claude-haiku-4-5":"qwen2.5-7b-instruct"}'
```

## Testing With a Fixture

If LM Studio is not running, you can test the model sync path with a JSON file:

```bash
export LMSTUDIO_MODELS_FILE=/path/to/models.json
node bridge.mjs sync-models
```

The fixture can look like either LM Studio's richer `/api/v1/models` output or the OpenAI-compatible `/v1/models` output.
