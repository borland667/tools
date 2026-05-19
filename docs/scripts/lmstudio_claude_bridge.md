# lmstudio_claude_bridge

## Purpose

Small local bridge for running Anthropic-style Claude clients against
`LM Studio` without changing the client source. It forwards
Anthropic-compatible `/v1/*` requests to LM Studio, rewrites
Anthropic-style default model names to local LM Studio model ids, and keeps
Claude-side model pickers populated where the client supports that.

Use this when:

- You want Claude Code to run locally against LM Studio instead of Anthropic.
- You want Claude Desktop / Claude Cowork 3P mode to use a local bridge-backed
  `gateway` provider instead of a hosted inference endpoint.
- You want to pick among locally loaded models in the app instead of hardcoding
  one model id.
- You want a lightweight bridge with no extra runtime dependencies beyond Node.

Do NOT use this for:

- OpenAI-only backends that do not expose Anthropic-compatible `/v1/messages`.
- Mixing hosted Claude models and local bridge models inside one single 3P
  gateway picker. That is not how the current Claude Desktop 3P model picker
  works.
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

### Claude Code

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

### Claude Desktop / Claude Cowork 3P mode

The Desktop/Cowork 3P path needs two pieces:

1. a long-running bridge on `http://127.0.0.1:1245`
2. a 3P provider config that points Claude Desktop at that bridge

Step by step:

1. Start LM Studio's local server.
2. Verify LM Studio responds:

```bash
curl http://127.0.0.1:1234/v1/models
```

3. Sync the bridge model cache:

```bash
cd /Users/borland/tools/lmstudio_claude_bridge
/usr/local/bin/node bridge.mjs sync-models
```

4. Keep the bridge running continuously.
   On this machine we use a user LaunchAgent:

```bash
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.borland.lmstudio-claude-bridge.plist
```

5. Verify bridge health:

```bash
curl http://127.0.0.1:1245/healthz
tail -f ~/Library/Logs/lmstudio-claude-bridge.log
```

6. Find Claude Desktop's active 3P provider config:

```bash
cat ~/Library/Application\ Support/Claude-3p/configLibrary/_meta.json
```

That file points at an active provider id. Edit the matching provider JSON in
`~/Library/Application Support/Claude-3p/configLibrary/`.

7. Use a fixed provider config like:

```json
{
  "disableDeploymentModeChooser": false,
  "inferenceGatewayApiKey": "lmstudio",
  "inferenceGatewayAuthScheme": "bearer",
  "inferenceGatewayBaseUrl": "http://127.0.0.1:1245",
  "inferenceProvider": "gateway",
  "modelDiscoveryEnabled": false,
  "inferenceModels": [
    {
      "name": "claude-haiku-4-5",
      "labelOverride": "Qwen Coder 30B (Haiku route)"
    },
    {
      "name": "claude-sonnet-4-6",
      "labelOverride": "Qwen 35B A3B Abliterated (Sonnet route)"
    }
  ]
}
```

8. Restart Claude Desktop.
9. Verify the app actually targets the bridge:

```bash
rg "inference apiHost=http://127.0.0.1:1245" ~/Library/Logs/Claude-3p/main.log
```

10. Verify real model rewrites:

```bash
tail -f ~/Library/Logs/lmstudio-claude-bridge.log
```

Expected examples:

- `claude-haiku-4-5` -> `qwen/qwen3-coder-30b`
- `claude-sonnet-4-6` -> `qwen3.6-35b-a3b-abliterated-heretic-mlx`

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

### Understand why the picker shows Qwen labels, not raw Claude names

In Claude Desktop 3P mode, the picker shows the configured provider-side
`inferenceModels`, not LM Studio's raw ids.

That is why we use provider-facing ids such as:

- `claude-haiku-4-5`
- `claude-sonnet-4-6`

but label them honestly for the user:

- `Qwen Coder 30B (Haiku route)`
- `Qwen 35B A3B Abliterated (Sonnet route)`

The bridge then rewrites those provider-facing ids to the real LM Studio model
ids at request time.

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
- `CLAUDE_LMSTUDIO_TOOL_MODEL`: override model used when `/v1/messages`
  includes tool definitions
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

Tool-aware routing behavior:

- When a `/v1/messages` request includes a non-empty `tools` array and the
  requested model looks like an Anthropic alias such as `claude-sonnet-*` or
  `claude-haiku-*`, the bridge can route that request to
  `CLAUDE_LMSTUDIO_TOOL_MODEL`.
- If `CLAUDE_LMSTUDIO_TOOL_MODEL` is unset, normal alias routing continues.
- This is useful for Cowork/Desktop sessions where a larger general model is
  acceptable for plain chat but a stricter tool-calling model is needed for
  `TaskCreate`, file-edit, and other agentic turns.

## Input and Output

Input:

- HTTP requests from Claude Code to the local bridge.
- HTTP requests from Claude Desktop / Claude Cowork 3P gateway mode to the
  local bridge.
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
- When used with Desktop/Cowork 3P mode, depends on a separate Claude Desktop
  provider config file that points to the bridge URL.

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
- It also does not change Claude Desktop provider state by itself; pointing
  Cowork/Desktop at the bridge is a separate configuration step.
- The launcher avoids Claude Code flags that are not present on older
  installations and relies on the local bridge environment variables instead.
- `ENABLE_TOOL_SEARCH=false` is a conservative default because many local
  proxies do not support Anthropic's tool-reference features cleanly.

## Known Limitations

- Expects LM Studio to provide Anthropic-compatible `/v1/messages`.
- Model selection is heuristic when LM Studio metadata is sparse.
- Thinking is disabled by default for compatibility across local models.
- This is a local bridge, not a general-purpose auth or multi-user gateway.
- In Claude Desktop `1.8089.0`, the 3P provider health indicator may show
  `unreachable` at startup even when real inference later succeeds through the
  bridge.
- The current Desktop/Cowork 3P gateway picker does not mix hosted Claude
  models and local bridge-backed models in one dropdown.
- Some local models can still produce malformed tool payloads in Cowork/Desktop
  even when LM Studio reports `trained_for_tool_use=true`. During validation on
  this machine, `qwen3.6-35b-a3b-abliterated-heretic-mlx` emitted a
  `TaskCreate` call without the required `description`, while
  `qwen/qwen3-coder-30b` returned a valid payload for the same schema. Use
  `CLAUDE_LMSTUDIO_TOOL_MODEL` to steer tool-heavy turns to the more reliable
  model.
- Plugin availability is separate from inference routing. A working local bridge
  does not automatically populate Claude Cowork's Plugins directory.

## Validation Checklist

- `node bridge.mjs --help` prints the expected commands.
- `node bridge.mjs sync-models` populates `additionalModelOptionsCache`.
- `./run_claude_with_lmstudio.sh` starts Claude Code with the bridge env.
- `LMSTUDIO_MODELS_FILE=./models.fixture.json node bridge.mjs sync-models`
  picks the expected default models.
- `curl http://127.0.0.1:1245/healthz` succeeds while the bridge is running.
- Claude Desktop logs `inference apiHost=http://127.0.0.1:1245` after the 3P
  provider is pointed at the bridge.
- `~/Library/Logs/lmstudio-claude-bridge.log` shows `rewrite model ...` lines
  during real Cowork/Desktop traffic.

## Plugins in Claude Cowork

The bridge does not provide plugins. It only provides inference routing.

On this machine, Claude Cowork's plugin screen reported that the organization
had not provided plugins, and no system plugin directory existed yet under
`/Library/Application Support/Claude/org-plugins`.

That implies plugin support is controlled separately from the bridge, through an
organization/marketplace/plugin-bundle mechanism. To make plugins available in
Cowork while still using the local bridge for inference, you will need to set
up one of those plugin distribution paths in addition to the bridge.

## Maintenance Notes

- Update this doc when bridge commands, env vars, default model heuristics, or
  launcher behavior change.
- Keep `/Users/borland/tools/README.md` in sync with the folder name and script
  description.
