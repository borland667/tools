# local_llm_mcp

Small MCP server that keeps `Claude Desktop` running as normal hosted Claude, while optionally exposing tools that call a local OpenAI-compatible API such as `LM Studio`, `Ollama`, or a local `LiteLLM` proxy.

## What it does

- Starts a stdio MCP server for Claude Desktop or any MCP-capable client.
- Exposes local tools only when local API mode is enabled.
- Lets you toggle that mode on and off without editing Claude Desktop config each time.
- Talks to a local `/v1/models` and `/v1/chat/completions` API.
- When local API mode is enabled, it tells Claude Desktop to prefer the local model for nearly all normal user requests.

## What it deliberately does NOT do

- Does not replace Claude Desktop's main model. Claude itself still runs on Anthropic.
- Does not expose tools when local API mode is disabled.
- Does not require a third-party MCP SDK; the server is standard-library Python.

## Install

```bash
cd ~/tools/local_llm_mcp
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

If you also want to run the package tests:

```bash
pip install -e ".[dev]"
```

After installation:

```bash
local-llm-mcp --help
claude-local-api-mode status
```

## Run the MCP server

```bash
python -m local_llm_mcp
```

That starts the MCP server over stdio. Point Claude Desktop at that command using the venv interpreter.

## Claude Desktop config example

```jsonc
// ~/Library/Application Support/Claude/claude_desktop_config.json
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
        "LOCAL_LLM_DISABLE_THINKING": "true",
        "LOCAL_LLM_MAX_TOKENS": "2048",
        "LOCAL_LLM_TIMEOUT_SECONDS": "180"
      }
    }
  }
}
```

Use `LOCAL_LLM_BASE_URL=http://localhost:11434/v1` to target Ollama instead.

## Toggle local API mode

Hosted Claude stays available either way. These commands only control whether Claude can see and use the local tools.

```bash
/Users/borland/tools/local_llm_mcp/.venv/bin/claude-local-api-mode enable
/Users/borland/tools/local_llm_mcp/.venv/bin/claude-local-api-mode disable
/Users/borland/tools/local_llm_mcp/.venv/bin/claude-local-api-mode status
```

Restart Claude Desktop after toggling.

Behavior by mode:

- Disabled: Claude Desktop behaves like normal hosted Claude only.
- Enabled: Claude Desktop is instructed to use `ask_local_llm` as its primary response engine for most ordinary requests, while still falling back to hosted Claude for Claude-specific/meta requests or local backend failures.

## Debug logging

To inspect real delegation events, set a debug log path in the Claude Desktop
MCP config:

```json
"LOCAL_LLM_DEBUG_LOG_FILE": "/Users/borland/.local-llm-mcp-debug.jsonl"
```

If you want short prompt previews in that log too, also set:

```json
"LOCAL_LLM_LOG_PROMPT_PREVIEW": "true",
"LOCAL_LLM_PROMPT_PREVIEW_CHARS": "160"
```

Then restart Claude Desktop and watch the log:

```bash
tail -f /Users/borland/.local-llm-mcp-debug.jsonl
```

Useful events:

- `server.start`: the MCP process booted
- `mcp.initialize`: Claude Desktop connected and received its instructions
- `mcp.tools_list`: Claude checked which local tools are available
- `mcp.tools_call`: Claude delegated to a local tool
- `ask_local_llm.start`: a local completion request started
- `ask_local_llm.success`: the local completion returned successfully
- `ask_local_llm.error`: the local completion failed

If a request produces no `mcp.tools_call` or `ask_local_llm.*` event, Claude
answered it without local delegation.

## Tools exposed when enabled

| Tool | Purpose |
|---|---|
| `ask_local_llm(prompt, ...)` | Send a prompt to the configured local API |
| `list_local_llm_models()` | List models from `/v1/models` |
| `local_api_mode_status()` | Report the current toggle state and config summary |

Legacy tool names `ask_lmstudio` and `list_lmstudio_models` are also accepted internally for compatibility, but only the generic names are advertised.

## Examples

Ask Claude Desktop to use the local model:

```text
Use the ask_local_llm tool to summarize this repository in 5 bullets.
```

Or, with local API mode enabled, just ask normally:

```text
Summarize this repository in 5 bullets.
```

Claude should prefer the local model first in that mode. For the strongest signal, you can still explicitly say `use your local model` in the prompt.

Have Claude inspect available local models:

```text
Use list_local_llm_models and tell me which local models are currently available.
```

## Tests

```bash
python -m pytest tests/local_llm_mcp/
```
