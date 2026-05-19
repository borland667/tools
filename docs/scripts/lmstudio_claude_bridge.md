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

## Current validated setup

The bridge can support other model-routing patterns, but the setup validated in
this session and documented below is:

- LM Studio local server on `http://127.0.0.1:1234`
- bridge LaunchAgent at
  `$HOME/Library/LaunchAgents/com.borland.lmstudio-claude-bridge.plist`
- bridge listener on `http://127.0.0.1:1245`
- Claude Desktop / Cowork 3P provider config under
  `$HOME/Library/Application Support/Claude-3p/configLibrary/`
- provider-facing ids:
  - `claude-haiku-4-5`
  - `claude-sonnet-4-6`
- actual LM Studio route for both main and tool traffic:
  - `qwen/qwen3-coder-30b`

If you follow the Desktop/Cowork section exactly, that is the behavior you
should reproduce.

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

## Prepare LM Studio Models

The bridge only discovers models that LM Studio already knows about. Before
using the bridge, make sure the models you want are downloaded and visible to
LM Studio.

You can do that either in the LM Studio app UI or through the `lms` CLI.

Example CLI flow:

```bash
"$HOME/.lmstudio/bin/lms" get qwen/qwen3-coder-30b --gguf -y
"$HOME/.lmstudio/bin/lms" get qwen/qwen3.5-32b --gguf -y
"$HOME/.lmstudio/bin/lms" load qwen/qwen3-coder-30b -y
"$HOME/.lmstudio/bin/lms" load qwen/qwen3.5-32b -y
```

If you prefer MLX variants on Apple Silicon, switch `--gguf` to `--mlx`.

Start the LM Studio API server if needed:

```bash
"$HOME/.lmstudio/bin/lms" server start --port 1234
```

Then verify that the models are discoverable:

```bash
curl http://127.0.0.1:1234/v1/models
```

If the model you expect is missing from `/v1/models`, `sync-models` will not
add it to Claude-facing model options and the bridge will not route to it.

## Quick Start

### Claude Code

```bash
cd <repo-root>/lmstudio_claude_bridge
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

1. Make sure your target models are already downloaded and loaded in LM Studio.
2. Start LM Studio's local server.
3. Verify LM Studio responds:

```bash
curl http://127.0.0.1:1234/v1/models
```

4. Sync the bridge model cache:

```bash
cd <repo-root>/lmstudio_claude_bridge
node bridge.mjs sync-models
```

5. Keep the bridge running continuously.
   On this machine, the bridge is kept alive by this user LaunchAgent:

```text
$HOME/Library/LaunchAgents/com.borland.lmstudio-claude-bridge.plist
```

The current file contents are:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>com.borland.lmstudio-claude-bridge</string>
  <key>ProgramArguments</key>
  <array>
    <string>/usr/local/bin/node</string>
    <string>/Users/borland/tools/lmstudio_claude_bridge/bridge.mjs</string>
    <string>serve</string>
  </array>
  <key>EnvironmentVariables</key>
  <dict>
    <key>LMSTUDIO_BASE_URL</key>
    <string>http://127.0.0.1:1234</string>
    <key>CLAUDE_LMSTUDIO_MAIN_MODEL</key>
    <string>qwen/qwen3-coder-30b</string>
    <key>CLAUDE_LMSTUDIO_SMALL_MODEL</key>
    <string>qwen/qwen3-coder-30b</string>
    <key>CLAUDE_LMSTUDIO_TOOL_MODEL</key>
    <string>qwen/qwen3-coder-30b</string>
  </dict>
  <key>RunAtLoad</key>
  <true/>
  <key>KeepAlive</key>
  <true/>
  <key>WorkingDirectory</key>
  <string>/Users/borland/tools/lmstudio_claude_bridge</string>
  <key>StandardOutPath</key>
  <string>/Users/borland/Library/Logs/lmstudio-claude-bridge.log</string>
  <key>StandardErrorPath</key>
  <string>/Users/borland/Library/Logs/lmstudio-claude-bridge.log</string>
</dict>
</plist>
```

Validate it:

```bash
plutil -lint "$HOME/Library/LaunchAgents/com.borland.lmstudio-claude-bridge.plist"
```

```bash
launchctl bootstrap gui/$(id -u) \
  "$HOME/Library/LaunchAgents/com.borland.lmstudio-claude-bridge.plist"
```

Important launchd caveat:

- If you edit the plist later, `launchctl kickstart` may restart the process
  without re-reading changed environment variables.
- To make changed model env vars take effect, fully unload and reload it:

```bash
launchctl bootout gui/$(id -u) \
  "$HOME/Library/LaunchAgents/com.borland.lmstudio-claude-bridge.plist"

launchctl bootstrap gui/$(id -u) \
  "$HOME/Library/LaunchAgents/com.borland.lmstudio-claude-bridge.plist"
```

6. Verify bridge health:

```bash
curl http://127.0.0.1:1245/healthz
tail -f "$HOME/Library/Logs/lmstudio-claude-bridge.log"
launchctl print gui/$(id -u)/com.borland.lmstudio-claude-bridge
```

7. Find Claude Desktop's active 3P provider config:

```bash
cat "$HOME/Library/Application Support/Claude-3p/configLibrary/_meta.json"
```

That file points at an active provider id. Edit the matching provider JSON in
`$HOME/Library/Application Support/Claude-3p/configLibrary/`.

8. Before editing, make a backup copy of the active provider JSON.

9. In that active provider JSON, leave unrelated UI fields alone and update
   the inference-related fields so they match the bridge. At minimum, ensure:

   - `"inferenceProvider": "gateway"`
   - `"inferenceGatewayBaseUrl": "http://127.0.0.1:1245"`
   - `"inferenceGatewayAuthScheme": "bearer"`
   - `"inferenceGatewayApiKey": "lmstudio"`
   - `"modelDiscoveryEnabled": false`

10. Replace the provider-facing model list with Anthropic-style ids that the
   bridge rewrites. Because the current LaunchAgent routes both paths to the
   coder model, the labels should say that too. A known-good example is:

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
      "labelOverride": "Qwen Coder 30B (Sonnet route)"
    }
  ]
}
```

What each JSON field is doing:

- `inferenceProvider`: enables 3P gateway mode.
- `inferenceGatewayBaseUrl`: points the app at the local bridge.
- `inferenceGatewayAuthScheme`: keeps the gateway auth mode on bearer.
- `inferenceGatewayApiKey`: placeholder token accepted by the bridge.
- `modelDiscoveryEnabled`: forces Claude Desktop to use the explicit model
  list instead of provider-side discovery.
- `inferenceModels`: the list shown in the picker.
- `inferenceModels[].name`: provider-facing Anthropic-style ids.
- `inferenceModels[].labelOverride`: honest labels for the local models those
  ids map to.

Two important details:

- Do not put raw LM Studio ids such as `qwen/...` into
  `inferenceModels[].name`; the bridge expects Anthropic-style aliases there.
- Do not point `inferenceGatewayBaseUrl` at `http://127.0.0.1:1234`, because
  that bypasses the bridge and loses alias rewriting.

Official-docs caveat:

- Anthropic's 3P configuration docs are stricter than this local setup.
- The working local bridge flow uses `http://127.0.0.1:1245` and
  Anthropic-style alias names in `inferenceModels[].name`.
- Anthropic's published configuration reference prefers `https://` gateway URLs
  and gateway model names that match the upstream `/v1/models` ids.
- This file documents the localhost-oriented setup that worked in practice on
  this machine, not a fully spec-aligned production deployment.
- Anthropic's docs also recommend setting `deploymentOrganizationUuid` for 3P
  deployments. Our local experiment ran without it, but add it if you want the
  config to align more closely with the documented rollout model.

11. Validate the JSON file after saving:

```bash
python -m json.tool "$HOME/Library/Application Support/Claude-3p/configLibrary/<provider-id>.json" >/dev/null
```

12. Restart Claude Desktop.
13. Verify the app actually targets the bridge:

```bash
rg "inference apiHost=http://127.0.0.1:1245" "$HOME/Library/Logs/Claude-3p/main.log"
```

14. Verify real model rewrites:

```bash
tail -f "$HOME/Library/Logs/lmstudio-claude-bridge.log"
```

Expected examples for the current Cowork/Desktop setup:

- `claude-haiku-4-5` -> `qwen/qwen3-coder-30b`
- `claude-sonnet-4-6` -> `qwen/qwen3-coder-30b`

## Common Usage Patterns

### Run Claude Code against LM Studio

```bash
cd <repo-root>/lmstudio_claude_bridge
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

That is different from the current Desktop/Cowork LaunchAgent documented
earlier in this file, which pins `MAIN_MODEL`, `SMALL_MODEL`, and
`TOOL_MODEL` all to `qwen/qwen3-coder-30b`.

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
- `Qwen Coder 30B (Sonnet route)`

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
- Claude Code global config JSON from `$HOME/.claude/.config.json` or
  `$HOME/.claude.json` unless overridden.

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

## Troubleshooting the socket-closed Cowork error

Observed symptom:

```text
API Error: The socket connection was closed unexpectedly.
For more information, pass `verbose: true` in the second argument to fetch()
```

What this usually means in this setup:

- Claude Cowork kept running.
- The local bridge stayed up.
- The upstream LM Studio request or SSE response died mid-turn.

In one traced failure on this machine, the Cowork session audit log captured the
exact message while `Claude-3p/main.log` recorded an intermediate SDK stream
error for the same `local_<session-id>`. The VM log did not show a Cowork VM
crash, which points to inference-stream termination rather than a sandbox
failure.

Where to inspect:

- `~/Library/Logs/Claude-3p/main.log`
- `~/Library/Logs/lmstudio-claude-bridge.log`
- the session-specific
  `~/Library/Application Support/Claude-3p/local-agent-mode-sessions/.../audit.jsonl`

Bridge-side behavior:

- The bridge now catches dropped upstream streams during `/v1/messages`
  streaming and converts them into Anthropic-style error events.
- Before this change, a dead upstream stream could surface as a plain socket
  close with little bridge-side context.

Mitigations:

- Prefer a stricter tool model with
  `CLAUDE_LMSTUDIO_TOOL_MODEL=qwen/qwen3-coder-30b`
- If the large main chat model is unstable, also set
  `CLAUDE_LMSTUDIO_MAIN_MODEL=qwen/qwen3-coder-30b`
- If the stream is just slow, increase
  `CLAUDE_LMSTUDIO_REQUEST_TIMEOUT_MS`
- Tail the bridge log during reproduction:

```bash
tail -f ~/Library/Logs/lmstudio-claude-bridge.log
```

## Troubleshooting high-memory node processes

If Activity Monitor shows huge `node` processes, they are usually LM Studio
model workers, not the bridge.

How to tell them apart:

- The bridge is the `launchd` job
  `com.borland.lmstudio-claude-bridge` and normally appears as one listener on
  `127.0.0.1:1245`.
- LM Studio workers are child processes of the main `LM Studio` app and run
  LM Studio's internal `llmworker.js`.

Useful checks:

```bash
launchctl print gui/$(id -u)/com.borland.lmstudio-claude-bridge
lsof -nP -iTCP:1245 -sTCP:LISTEN
"$HOME/.lmstudio/bin/lms" ps --json
```

If you need to inspect memory ownership more deeply:

```bash
vmmap -summary <pid>
```

On this machine, the very large footprints were dominated by
`IOAccelerator (graphics)`, which indicates GPU/Metal-backed model state rather
than Node heap growth.

## Validation Checklist

- `node bridge.mjs --help` prints the expected commands.
- `node bridge.mjs sync-models` populates `additionalModelOptionsCache`.
- `./run_claude_with_lmstudio.sh` starts Claude Code with the bridge env.
- `LMSTUDIO_MODELS_FILE=./models.fixture.json node bridge.mjs sync-models`
  picks the expected default models.
- `curl http://127.0.0.1:1245/healthz` succeeds while the bridge is running.
- `launchctl print gui/$(id -u)/com.borland.lmstudio-claude-bridge` shows the
  expected env vars and plist path.
- Claude Desktop logs `inference apiHost=http://127.0.0.1:1245` after the 3P
  provider is pointed at the bridge.
- `$HOME/Library/Logs/lmstudio-claude-bridge.log` shows `rewrite model ...` lines
  during real Cowork/Desktop traffic.

## Plugins in Claude Cowork

The bridge does not provide plugins. It only provides inference routing.

Official Cowork on 3P docs describe three extension layers:

- `managedMcpServers`: admin-provisioned remote MCP servers
- organization plugins: filesystem-delivered plugin bundles under
  `/Library/Application Support/Claude/org-plugins/`
- user extensions: plugins from the in-app Plugins UI, `.mcpb` connectors, and
  local MCP servers from Settings -> Developer

So the correct mental model is:

- the bridge changes inference routing
- Cowork's plugin system is a separate extension surface
- both can be used together

Important boundary:

- We observed internal session data under
  `~/Library/Application Support/Claude-3p/local-agent-mode-sessions/.../cowork_plugins/`,
  but that appears to be an implementation detail of Cowork sessions rather
  than a documented deployment path.
- For reproducible setup, prefer the documented plugin paths instead:
  - `/Library/Application Support/Claude/org-plugins/`
  - the in-app Plugins / Connectors UI
  - local MCP configuration from Settings -> Developer where applicable
- On macOS, writing to `/Library/Application Support/Claude/org-plugins/`
  usually requires administrator privileges.
- If Cowork says your organization has not provided plugins, that usually means
  nothing has been deployed into the supported org-plugin path yet; it is not a
  bridge routing failure.

### Recommended official plugin repos

1. `anthropics/knowledge-work-plugins`

- Repo: [knowledge-work-plugins](https://github.com/anthropics/knowledge-work-plugins)
- Intended audience: primarily Claude Cowork knowledge-work roles
- Repo guidance: built for Claude Cowork, also compatible with Claude Code
- Notable plugin directories:
  - `productivity`
  - `sales`
  - `customer-support`
  - `product-management`
  - `marketing`
  - `legal`
  - `finance`
  - `data`
  - `enterprise-search`
  - `bio-research`
  - `cowork-plugin-management`

2. `anthropics/claude-plugins-official`

- Repo: [claude-plugins-official](https://github.com/anthropics/claude-plugins-official)
- Intended audience: curated Anthropic-managed Claude plugin directory
- Structure:
  - `plugins/`: Anthropic-maintained plugins
  - `external_plugins/`: partner/community plugins
- Best fit: Claude Code installs, plugin-format reference, and curated plugin
  sourcing for Cowork org-plugin deployment

### Setup path: `knowledge-work-plugins` as Cowork org plugins

Cowork on 3P organization plugins are installed by placing plugin directories
under:

```text
/Library/Application Support/Claude/org-plugins/
```

Each subdirectory is a plugin, and the plugin is ignored if it does not contain
`.claude-plugin/plugin.json`.

Step by step:

1. Clone the repo:

```bash
git clone https://github.com/anthropics/knowledge-work-plugins.git
```

2. Choose one plugin directory, for example `productivity`.
3. Copy it into the org-plugin path as:

```text
/Library/Application Support/Claude/org-plugins/productivity/
```

4. Optionally customize before deployment:
   - update `.mcp.json` for your actual tool stack
   - edit skill files for your team's workflows and terminology
   - set `"installationPreference"` in `.claude-plugin/plugin.json`
     - `"required"`
     - `"auto_install"`
     - `"available"`
5. Restart Claude Desktop / Cowork.
6. Confirm the plugin appears in the plugin browser or auto-installs according
   to `installationPreference`.

### Setup path: `claude-plugins-official`

There are two useful ways to consume this repo.

For `Claude Code`:

- install through the plugin system using the repo's documented flow:
  - `/plugin install {plugin-name}@claude-plugins-official`
  - or browse from `/plugin > Discover`

For `Cowork on 3P`:

- pick a plugin from `plugins/` or `external_plugins/`
- copy the individual plugin directory into:

```text
/Library/Application Support/Claude/org-plugins/<plugin-name>/
```

- keep the plugin structure intact:
  - `.claude-plugin/plugin.json`
  - `.mcp.json` when present
  - `commands/`
  - `agents/`
  - `skills/`

### Operational caveats

- User-added plugins are separate from org plugins. A Cowork screen that says
  the organization has not provided plugins only describes the org-plugin
  layer.
- End users still may be able to add their own plugins unless admin policy
  disables that extension surface.
- End users cannot add remote MCP servers directly. Remote MCP should come from
  `managedMcpServers` or an org plugin.
- If a plugin depends on remote connectors, make sure Cowork's sandbox egress
  and MCP configuration are compatible with those connectors.

## Maintenance Notes

- Update this doc when bridge commands, env vars, default model heuristics, or
  launcher behavior change.
- Keep the repository `README.md` in sync with the folder name and script
  description.
