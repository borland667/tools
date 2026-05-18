# local_llm_mcp

## Purpose

MCP (Model Context Protocol) server that lets `Claude Desktop` optionally call
a local OpenAI-compatible LLM endpoint such as `LM Studio`, `Ollama`, or a
local `LiteLLM` proxy, while keeping Claude itself as the normal hosted model.
When local mode is enabled, the server pushes Claude Desktop to use the local
LLM as the primary response engine for most ordinary requests.

Use this when:

- You want to keep using Claude Desktop normally for everyday work.
- You occasionally want Claude to call a local model for summarization,
  rewriting, or code assistance.
- You want a simple on/off switch for exposing local tools.

Do NOT use this for:

- Replacing Claude Desktop's main model. This package does not do that.
- Non-OpenAI-compatible endpoints unless you place a compatibility proxy in
  front of them.

## Requirements

- Python 3.10+.
- A local endpoint that supports:
  - `GET /v1/models`
  - `POST /v1/chat/completions`
- Optional examples:
  - LM Studio on `http://localhost:1234/v1`
  - Ollama on `http://localhost:11434/v1`

The package is standard-library only.

## Quick Start

```bash
cd ~/tools/local_llm_mcp
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

If you want to run the package tests too:

```bash
pip install -e ".[dev]"
```

Add it to Claude Desktop:

```json
{
  "mcpServers": {
    "local-llm": {
      "command": "/Users/borland/tools/local_llm_mcp/.venv/bin/python",
      "args": ["-m", "local_llm_mcp"],
      "env": {
        "LOCAL_LLM_BASE_URL": "http://localhost:1234/v1",
        "LOCAL_LLM_MODEL": "qwen3.6-35b-a3b-abliterated-heretic-mlx",
        "LOCAL_LLM_API_KEY": "lmstudio",
        "LOCAL_LLM_MODE_DEFAULT": "false",
        "LOCAL_LLM_DEBUG_LOG_FILE": "/Users/borland/.local-llm-mcp-debug.jsonl",
        "LOCAL_LLM_DISABLE_THINKING": "true"
      }
    }
  }
}
```

Enable local API mode:

```bash
/Users/borland/tools/local_llm_mcp/.venv/bin/claude-local-api-mode enable
```

Restart Claude Desktop.

## Common Usage Patterns

### Keep normal Claude and hide local tools

```bash
/Users/borland/tools/local_llm_mcp/.venv/bin/claude-local-api-mode disable
```

Restart Claude Desktop and use it as usual.

### Let Claude call a local LM Studio model

Set:

- `LOCAL_LLM_BASE_URL=http://localhost:1234/v1`
- `LOCAL_LLM_MODEL=qwen3.6-35b-a3b-abliterated-heretic-mlx`
- `LOCAL_LLM_DISABLE_THINKING=true`

Then ask Claude:

```text
Use the ask_local_llm tool to rewrite this in a more concise tone.
```

With local mode enabled, you can also try a normal prompt such as:

```text
Rewrite this in a more concise tone.
```

The server now instructs Claude Desktop to delegate most standard requests to
the local model first. This is still a best-effort preference layer, not a
true model-backend swap.

### See when Claude delegated to local

Set:

- `LOCAL_LLM_DEBUG_LOG_FILE=/Users/borland/.local-llm-mcp-debug.jsonl`

Optional:

- `LOCAL_LLM_LOG_PROMPT_PREVIEW=true`
- `LOCAL_LLM_PROMPT_PREVIEW_CHARS=160`

Then restart Claude Desktop and inspect the log:

```bash
tail -f /Users/borland/.local-llm-mcp-debug.jsonl
```

Useful events:

- `server.start`
- `mcp.initialize`
- `mcp.tools_list`
- `mcp.tools_call`
- `ask_local_llm.start`
- `ask_local_llm.success`
- `ask_local_llm.error`

If a prompt does not generate `mcp.tools_call` or `ask_local_llm.*`, Claude
did not delegate that request to the local backend.

### Let Claude call a local Ollama model

Set:

- `LOCAL_LLM_BASE_URL=http://localhost:11434/v1`
- `LOCAL_LLM_MODEL=qwen2.5-coder:14b`
- `LOCAL_LLM_API_KEY=ollama`

Then ask Claude:

```text
Use list_local_llm_models and tell me which Ollama models are currently available.
```

## Arguments and Options

There are no command-line flags for the server itself. Configuration comes from
environment variables:

- `LOCAL_LLM_BASE_URL`: API base URL, default `http://localhost:1234/v1`
- `LOCAL_LLM_MODEL`: default model id
- `LOCAL_LLM_API_KEY`: bearer token; any placeholder is fine for some local endpoints
- `LOCAL_LLM_TIMEOUT_SECONDS`: HTTP timeout, default `180`
- `LOCAL_LLM_MAX_TOKENS`: default generation limit, default `2048`
- `LOCAL_LLM_DISABLE_THINKING`: prepend `/no_think`, default `false`
- `LOCAL_LLM_MODE_FILE`: JSON toggle-state file, default `~/.claude-local-api-mode.json`
- `LOCAL_LLM_MODE_DEFAULT`: whether tools are visible when the mode file is missing, default `false`
- `LOCAL_LLM_DEBUG_LOG_FILE`: optional JSONL debug log path
- `LOCAL_LLM_LOG_PROMPT_PREVIEW`: include prompt previews in the debug log, default `false`
- `LOCAL_LLM_PROMPT_PREVIEW_CHARS`: prompt preview length, default `120`

Compatibility aliases are also supported:

- `LMSTUDIO_BASE_URL`
- `LMSTUDIO_MODEL`
- `LMSTUDIO_API_KEY`
- `LMSTUDIO_TIMEOUT_SECONDS`
- `LMSTUDIO_MAX_TOKENS`
- `LMSTUDIO_DISABLE_THINKING`
- `LMSTUDIO_MODE_FILE`
- `LMSTUDIO_MODE_DEFAULT`
- `LMSTUDIO_DEBUG_LOG_FILE`
- `LMSTUDIO_LOG_PROMPT_PREVIEW`
- `LMSTUDIO_PROMPT_PREVIEW_CHARS`

## Input and Output

Input:

- stdio JSON-RPC from an MCP client.
- Local mode state from `LOCAL_LLM_MODE_FILE`.
- Optional prompt/model overrides in tool arguments.

Output:

- MCP tool results over stdio.
- Local mode state persisted as JSON:
  - `{"enabled": true}`
  - `{"enabled": false}`

## Internal Behavior Summary

1. Claude Desktop starts the server with `python -m local_llm_mcp`.
2. On initialization, the server advertises itself but only exposes tools when
   local API mode is enabled.
3. When local mode is enabled, the server instructs Claude Desktop to treat
   `ask_local_llm` as the primary response path for most ordinary requests.
4. `ask_local_llm` sends prompts to `/v1/chat/completions`.
5. `list_local_llm_models` reads `/v1/models`.
6. When `LOCAL_LLM_DEBUG_LOG_FILE` is set, the server appends JSONL events for
   startup, MCP tool discovery, and local tool calls.
7. `claude-local-api-mode enable|disable|status` updates or reads the mode file.

## Safety Notes

- Local API mode is off by default. That keeps Claude Desktop in normal hosted
  mode until you explicitly opt in.
- Even when enabled, hosted Claude is still present as the host model. The
  delegation behavior is a strong preference layer, not a guaranteed full
  backend replacement.
- The package does not mutate source repositories or system configuration on
  its own, aside from the chosen mode-file path.
- The package does not manage authentication for your local backend; if you
  expose one beyond localhost, secure it separately.

## Known Limitations

- Expects OpenAI-compatible request/response shapes for `/v1/models` and
  `/v1/chat/completions`.
- `disable_thinking` is implemented as `/no_think` in the system message.
  That is useful for Qwen-style models but not universal.
- The server exposes no tools when disabled, so mode status must be checked
  with the CLI in that state.

## Validation Checklist

- `python -m local_llm_mcp` starts the server.
- `claude-local-api-mode status` prints the current mode and file path.
- `python -m pytest tests/local_llm_mcp/` is green after `pip install -e ".[dev]"`.
- With LM Studio or Ollama running:
  - `list_local_llm_models` returns model ids.
  - `ask_local_llm` returns a text answer.

## Maintenance Notes

When changing behavior or env vars, update:

- This doc.
- `local_llm_mcp/README.md`
- `local_llm_mcp/claude_desktop_config.example.json`
- `tests/local_llm_mcp/`
- Root `README.md` script index and layout.
