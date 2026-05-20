# LM Studio Claude Bridge

This bridge lets Anthropic-style Claude clients talk to a local LM Studio
server while keeping the client's model picker usable.

It currently supports two practical workflows:

- `Claude Code`: launched with environment variables that point directly at the
  local bridge.
- `Claude Desktop` / `Claude Cowork` 3P mode: configured as a custom
  `gateway` provider that points at the local bridge.

## Current reproducible setup on this machine

The repository supports more than one routing pattern, but the setup we
validated in this session and documented below is:

- LM Studio local server on `http://127.0.0.1:1234`
- bridge LaunchAgent at
  `$HOME/Library/LaunchAgents/com.borland.lmstudio-claude-bridge.plist`
- bridge listener on `http://127.0.0.1:1245`
- Claude Desktop / Cowork 3P provider config under
  `$HOME/Library/Application Support/Claude-3p/configLibrary/`
- provider-facing model ids:
  - `claude-haiku-4-5`
  - `claude-sonnet-4-6`
- actual LM Studio route for both main and tool traffic:
  - `qwen/qwen3-coder-30b`

If you follow the Desktop/Cowork steps in this README exactly, that is the
behavior you should reproduce.

LM Studio already exposes an Anthropic-compatible `POST /v1/messages`
endpoint, so this bridge does not try to reimplement inference. Instead it
adds the missing glue:

- it proxies `/v1/*` requests to LM Studio,
- it rewrites Anthropic-style model names like `claude-sonnet-*` and
  `claude-haiku-*` to local LM Studio model ids,
- it syncs LM Studio's model list into Claude's local cache where applicable.

## Which local tool to use

- Use [`local_llm_mcp`](../local_llm_mcp/README.md) if you
  want normal hosted Claude plus optional local tool delegation inside Claude
  Desktop.
- Use this bridge if you want the client's primary inference path to go to LM
  Studio through an Anthropic-compatible local endpoint.

## Files

- [bridge.mjs](./bridge.mjs)
- [run_claude_with_lmstudio.sh](./run_claude_with_lmstudio.sh)
- [claude-3p-provider.example.json](./claude-3p-provider.example.json)

## Requirements

- Node 18+ (tested with Node 24)
- LM Studio local server running

LM Studio docs used for this bridge:

- [Anthropic Compatibility Endpoints](https://lmstudio.ai/docs/developer/anthropic-compat)
- [Messages](https://lmstudio.ai/docs/developer/anthropic-compat/messages)
- [List Models](https://lmstudio.ai/docs/developer/openai-compat/models)

## Prepare LM Studio Models

The bridge only discovers models that LM Studio already knows about. Before
setting up Claude Desktop or Claude Code against the bridge, make sure the
models you want are downloaded and visible to LM Studio.

Typical options:

- Download them in the LM Studio app UI.
- Or use the `lms` CLI to download and load them.

Example CLI flow:

```bash
"$HOME/.lmstudio/bin/lms" get qwen/qwen3-coder-30b --gguf -y
"$HOME/.lmstudio/bin/lms" get qwen/qwen3.5-32b --gguf -y
"$HOME/.lmstudio/bin/lms" load qwen/qwen3-coder-30b -y
"$HOME/.lmstudio/bin/lms" load qwen/qwen3.5-32b -y
```

If you prefer MLX variants on Apple Silicon, switch `--gguf` to `--mlx`.

After downloading and loading, start the LM Studio API server if it is not
already running:

```bash
"$HOME/.lmstudio/bin/lms" server start --port 1234
```

Then verify model discovery through the API:

```bash
curl http://127.0.0.1:1234/v1/models
```

The bridge and its `sync-models` command rely on that endpoint. If the model
you want does not appear there, Claude will not be able to route to it through
the bridge.

## Quick Start

### Claude Code

1. Make sure your target models are already downloaded and loaded in LM Studio.
2. Start LM Studio's local server.
3. Run:

```bash
cd <repo-root>/lmstudio_claude_bridge
./run_claude_with_lmstudio.sh
```

That launcher will:

- sync LM Studio models into Claude Code's global config,
- start the bridge on `http://127.0.0.1:1245`,
- set the recommended env vars,
- default Claude Code's main route to
  `qwen3.6-35b-a3b-abliterated-heretic-mlx` unless you override it,
- keep the helper/default side path on `qwen/qwen3-coder-30b` unless you
  override it,
- launch `claude`.

### Claude Desktop / Claude Cowork 3P mode

This is a typical local setup.

1. Make sure your target models are already downloaded and loaded in LM Studio.
2. Start LM Studio's local server on `http://127.0.0.1:1234`.
3. Verify LM Studio responds:

```bash
curl http://127.0.0.1:1234/v1/models
```

4. Sync the bridge's model cache:

```bash
cd <repo-root>/lmstudio_claude_bridge
node bridge.mjs sync-models
```

5. Keep the bridge running on `http://127.0.0.1:1245`.
   On this machine, the bridge is kept alive with this user LaunchAgent:

`$HOME/Library/LaunchAgents/com.borland.lmstudio-claude-bridge.plist`

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

What each key is doing:

- `Label`: the launchd job name we later query with `launchctl print`.
- `ProgramArguments`: runs `node bridge.mjs serve`.
- `EnvironmentVariables`: pins all bridge routes to `qwen/qwen3-coder-30b`.
- `WorkingDirectory`: makes relative bridge paths resolve consistently.
- `StandardOutPath` / `StandardErrorPath`: sends bridge logs to one stable file.
- `RunAtLoad` and `KeepAlive`: start the bridge at login and restart it if it exits.

6. Validate the plist:

```bash
plutil -lint "$HOME/Library/LaunchAgents/com.borland.lmstudio-claude-bridge.plist"
```

7. Load that LaunchAgent the first time:

```bash
launchctl bootstrap gui/$(id -u) \
  "$HOME/Library/LaunchAgents/com.borland.lmstudio-claude-bridge.plist"
```

8. If you edit the plist later, do not rely on `launchctl kickstart` alone.
   `kickstart` restarts the process, but launchd may keep the old cached
   environment variables. Fully reload the job instead:

```bash
launchctl bootout gui/$(id -u) \
  "$HOME/Library/LaunchAgents/com.borland.lmstudio-claude-bridge.plist"

launchctl bootstrap gui/$(id -u) \
  "$HOME/Library/LaunchAgents/com.borland.lmstudio-claude-bridge.plist"
```

9. Confirm the bridge is healthy and running with the expected env:

```bash
curl http://127.0.0.1:1245/healthz
launchctl print gui/$(id -u)/com.borland.lmstudio-claude-bridge
```

10. Point Claude Desktop's active 3P provider config at the bridge.
   The active provider id typically lives in:

```bash
$HOME/Library/Application Support/Claude-3p/configLibrary/_meta.json
```

and the provider JSON itself lives in:

```bash
$HOME/Library/Application Support/Claude-3p/configLibrary/<provider-id>.json
```

Before editing, make a backup copy of that provider JSON.

This repo also includes a ready-to-edit provider example at:

```text
lmstudio_claude_bridge/claude-3p-provider.example.json
```

In the active provider JSON, keep unrelated UI fields as they are and update
the inference-related fields so they match the bridge. At minimum, make sure
these keys have these values:

- `"deploymentOrganizationUuid": "<your-uuid>"`
- `"inferenceProvider": "gateway"`
- `"inferenceGatewayBaseUrl": "http://127.0.0.1:1245"`
- `"inferenceGatewayAuthScheme": "bearer"`
- `"inferenceGatewayApiKey": "lmstudio"`
- `"coworkEgressAllowedHosts": [...]`
- `"modelDiscoveryEnabled": false`

Then replace the provider-facing model list with Anthropic-style ids that the
bridge knows how to rewrite. Because the current LaunchAgent routes both
Haiku-like and Sonnet-like requests to the coder model, the labels should be
honest about that too. A known-good example is:

```json
{
  "deploymentOrganizationUuid": "11111111-2222-4333-8444-555555555555",
  "disableDeploymentModeChooser": false,
  "coworkEgressAllowedHosts": [
    "127.0.0.1",
    "localhost",
    "pypi.org",
    "files.pythonhosted.org",
    "registry.npmjs.org",
    "github.com",
    "api.github.com",
    "raw.githubusercontent.com"
  ],
  "inferenceGatewayApiKey": "lmstudio",
  "inferenceGatewayAuthScheme": "bearer",
  "inferenceGatewayBaseUrl": "http://127.0.0.1:1245",
  "inferenceProvider": "gateway",
  "isDesktopExtensionEnabled": true,
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

- `deploymentOrganizationUuid`: gives the deployment a stable identity in
  Anthropic's telemetry/support model instead of the shared placeholder UUID.
- `inferenceProvider`: switches the provider into 3P gateway mode.
- `inferenceGatewayBaseUrl`: points Claude Desktop at the local bridge, not at
  LM Studio directly.
- `inferenceGatewayAuthScheme`: keeps the provider on bearer-style auth.
- `inferenceGatewayApiKey`: placeholder token the local bridge accepts.
- `coworkEgressAllowedHosts`: host allowlist for Cowork's web fetch, shell,
  package installs, and many plugin or connector side effects. Keep this tight
  and extend it only for the tools you actually use.
- `isDesktopExtensionEnabled`: keeps local desktop extensions and plugin
  installs available in the app.
- `modelDiscoveryEnabled`: disables provider-side discovery so the app keeps
  using the explicit model list below.
- `inferenceModels`: the list shown in the Claude Desktop picker.
- `inferenceModels[].name`: provider-facing ids Claude Desktop expects.
- `inferenceModels[].labelOverride`: the human-readable labels you want shown
  in the picker.

Two important details:

- Do not put raw LM Studio model ids such as `qwen/...` into
  `inferenceModels[].name`. Keep Anthropic-style names there and let the bridge
  rewrite them.
- Do not point `inferenceGatewayBaseUrl` at `http://127.0.0.1:1234`. That
  would bypass the bridge and lose the model-rewrite behavior.

Official-docs caveat:

- Anthropic's 3P configuration docs are stricter than this local setup.
- The local bridge flow we validated uses `http://127.0.0.1:1245` and
  Anthropic-style alias names in `inferenceModels[].name`.
- Anthropic's published configuration reference prefers `https://` gateway URLs
  and gateway model names that match the upstream `/v1/models` ids.
- This repo documents the local setup that worked in practice on this machine,
  but you should treat it as a localhost-oriented workaround rather than a
  fully spec-aligned production deployment.
- Anthropic's docs also recommend setting `deploymentOrganizationUuid` for 3P
  deployments. Use it in practice.
- Anthropic's docs also make `coworkEgressAllowedHosts` central to whether
  Cowork can actually fetch the web, install packages, or use plugins and
  connectors that reach external services. If your tools mysteriously fail even
  though inference works, inspect this allowlist before blaming the bridge.

After saving the provider JSON, validate that it is still well-formed:

```bash
python -m json.tool "$HOME/Library/Application Support/Claude-3p/configLibrary/<provider-id>.json" >/dev/null
```

9. Restart Claude Desktop.
10. Verify Claude is now targeting the bridge:

```bash
rg "inference apiHost=http://127.0.0.1:1245" "$HOME/Library/Logs/Claude-3p/main.log"
tail -f "$HOME/Library/Logs/lmstudio-claude-bridge.log"
```

You should see bridge rewrite lines such as:

- `claude-haiku-4-5` -> `qwen/qwen3-coder-30b`
- `claude-sonnet-4-6` -> `qwen/qwen3-coder-30b`

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

The launcher avoids Claude Code flags that are unavailable in older installations and relies on environment variables only.

## Model Selection

By default the bridge chooses:

- `mainModel`: the best general LLM candidate it can infer from LM Studio's model list
- `smallModel`: the best smaller candidate for Haiku-like helper calls

When LM Studio exposes `abliterated` or `uncensored` variants, the bridge now prefers those as the default base models before falling back to the regular variants.

For Claude Code specifically, the included launcher pins the primary/default
mapping to `qwen3.6-35b-a3b-abliterated-heretic-mlx`, the helper mapping to
`qwen/qwen3-coder-30b`, and now also pins `CLAUDE_LMSTUDIO_TOOL_MODEL` to
`qwen/qwen3-coder-30b` unless you override them. That keeps the picker dynamic
while routing the main conversation to the larger abliterated model we
validated on LM Studio's Anthropic-compatible `/v1/messages` path, while
making tool-heavy turns consistently use the stricter coder model.

That is different from the current Desktop/Cowork LaunchAgent documented
earlier in this README, which pins `MAIN_MODEL`, `SMALL_MODEL`, and
`TOOL_MODEL` all to `qwen/qwen3-coder-30b` to make the live route explicit and
reduce ambiguity.

You can override all three:

```bash
export CLAUDE_LMSTUDIO_MAIN_MODEL=qwen3-coder-30b
export CLAUDE_LMSTUDIO_SMALL_MODEL=qwen2.5-7b-instruct
export CLAUDE_LMSTUDIO_TOOL_MODEL=qwen3-coder-30b
```

You can also provide explicit rewrites:

```bash
export CLAUDE_LMSTUDIO_MODEL_MAP='{"claude-sonnet-4-6":"qwen3-coder-30b","claude-haiku-4-5":"qwen2.5-7b-instruct"}'
```

For Cowork/Desktop, you can also tell the bridge to prefer a more reliable
tool-calling model whenever the request includes tools:

```bash
export CLAUDE_LMSTUDIO_TOOL_MODEL=qwen/qwen3-coder-30b
```

That keeps plain chat on the larger main model while routing tool-heavy turns
such as `TaskCreate`, file edits, and other agentic calls to a model that is
less likely to omit required tool parameters.

## Recommended models for this hardware

On this machine, `llmfit` reports:

- `Apple M4 Max`
- `128 GB` unified memory
- about `116 GB` available during validation

The strongest local fits we saw were:

- `Qwen/Qwen3-Coder-Next`
  - best coding-quality recommendation
  - about `40.8 GB` estimated memory
  - about `75.8 tok/s`
- `Qwen/Qwen3-Next-80B-A3B-Instruct`
  - best general chat / instruction-following recommendation
  - about `41.7 GB` estimated memory
  - about `74.8 tok/s`
- `Qwen/Qwen3-Coder-30B-A3B-Instruct`
  - best practical bridge default
  - about `15.6 GB` estimated memory
  - about `81 tok/s`

Practical recommendation:

- keep `qwen/qwen3-coder-30b` as the current Cowork/Desktop bridge model for
  reliability and lower memory pressure
- test `Qwen3-Coder-Next` next when you want the highest coding quality
- use `Qwen3-Next-80B-A3B-Instruct` when you want a stronger general assistant
  route than the coder model

Avoid keeping several large models loaded at once unless you actually need
them. LM Studio model workers can hold very large unified-memory allocations
even while idle.

## What the picker is showing

In Claude Desktop 3P gateway mode, the model picker shows the configured
`inferenceModels`, not LM Studio's raw model ids.

That is why the UI may show labels like:

- `Qwen Coder 30B (Haiku route)`
- `Qwen Coder 30B (Sonnet route)`

while the bridge log shows those names being rewritten to the actual LM Studio
model ids.

This is intentional. The current Claude Desktop 3P gateway validation expects
Anthropic-style model names for the provider-facing ids, and raw Qwen ids were
rejected as not usable.

If you later switch the Sonnet route back to a different local model, update
`labelOverride` to match so the picker stays honest.

## Claude Desktop limitations we observed

- The 3P gateway picker does not merge hosted Claude models and local bridge
  models into one dropdown.
- Re-enabling the deployment mode chooser may expose the hosted Claude.ai path,
  but it does not turn the gateway picker into a mixed hosted+local model list.
- On Claude Desktop `1.8089.0`, the 3P provider health banner may still report
  `unreachable` during startup even when real runtime inference is flowing
  through the bridge. Check the bridge log before assuming inference is broken.
- Some local models still make malformed tool calls in Cowork/Desktop even when
  they advertise tool-use support. In one validation run,
  `qwen3.6-35b-a3b-abliterated-heretic-mlx` produced a `TaskCreate` call
  without the required `description`, while `qwen/qwen3-coder-30b` returned a
  valid tool payload immediately. `CLAUDE_LMSTUDIO_TOOL_MODEL` exists to
  mitigate that class of failure.
- Plugin availability is separate from inference. Pointing Claude Desktop at the
  local bridge does not populate the Plugins directory by itself.

## Troubleshooting common runtime failures

### "API Error: The socket connection was closed unexpectedly"

If Cowork/Desktop shows:

```text
API Error: The socket connection was closed unexpectedly
```

that usually means the local model stream died while Claude was still reading
it. In our validation, this was not a Cowork VM crash. The failing session
stayed alive, but LM Studio or the upstream model closed the in-flight stream
mid-turn.

What to check:

- `~/Library/Logs/Claude-3p/main.log`
  - look for the affected `local_<session-id>` and lines such as
    `Intermediate SDK error "unknown"` or `Turn failed`
- `~/Library/Logs/lmstudio-claude-bridge.log`
  - look for `[bridge] upstream request failed` or
    `[bridge] upstream stream failed`
- the session audit log under
  `~/Library/Application Support/Claude-3p/local-agent-mode-sessions/.../audit.jsonl`
  - this preserves the exact user-visible error message for the turn

Bridge behavior:

- The bridge now traps dropped upstream streams and emits an Anthropic-style
  streaming error event instead of letting the HTTP socket die silently.
- This makes the failure easier to diagnose and avoids the bridge looking like
  it crashed locally when the real problem was upstream stream termination.

Practical mitigations:

- Set `CLAUDE_LMSTUDIO_TOOL_MODEL=qwen/qwen3-coder-30b` if the failure happens
  during tool-heavy turns.
- Consider setting `CLAUDE_LMSTUDIO_MAIN_MODEL=qwen/qwen3-coder-30b` as well if
  the larger default chat model is unstable on your machine.
- If the model is slow rather than broken, increase
  `CLAUDE_LMSTUDIO_REQUEST_TIMEOUT_MS`.
- Re-run the same task while tailing the bridge log:

```bash
tail -f ~/Library/Logs/lmstudio-claude-bridge.log
```

If the bridge logs repeated upstream stream failures, treat the local model or
LM Studio runtime as the primary suspect before blaming Cowork itself.

### "Why are there huge node processes? Is the bridge leaking memory?"

Usually no. In our validation, the largest `node` processes were LM Studio
worker runtimes, not the bridge.

How to tell them apart:

- The bridge is the `launchd` job
  `com.borland.lmstudio-claude-bridge` and normally shows up as a single
  `node` listener on `127.0.0.1:1245`.
- LM Studio model workers are child processes of the main `LM Studio` app and
  run LM Studio's internal `llmworker.js`.

Useful checks:

```bash
launchctl print gui/$(id -u)/com.borland.lmstudio-claude-bridge
lsof -nP -iTCP:1245 -sTCP:LISTEN
"$HOME/.lmstudio/bin/lms" ps --json
```

If you need to inspect memory ownership more deeply, `vmmap -summary <pid>`
will usually show that the very large footprints belong to `IOAccelerator
(graphics)` regions, which means GPU/Metal-backed model state rather than Node
heap growth.

## Plugins in Cowork

The local bridge only changes where inference requests go. It does not provide
plugins or marketplaces.

Claude's official Cowork on 3P docs describe three separate extension layers:

- `managedMcpServers`: admin-provisioned remote MCP servers delivered through
  managed config
- organization plugins: filesystem-delivered plugin bundles under
  `/Library/Application Support/Claude/org-plugins/`
- user extensions: plugins installed from the in-app Plugins UI, connectors
  installed as `.mcpb`, and local MCP servers added from Settings -> Developer

That means the bridge is compatible with plugins, but it is not the thing that
installs or manages them.

Important boundary:

- We observed internal session data under
  `~/Library/Application Support/Claude-3p/local-agent-mode-sessions/.../cowork_plugins/`,
  but that appears to be an implementation detail of Cowork sessions, not the
  documented deployment path.
- For reproducible setup, do not rely on that internal session store. Prefer
  the documented plugin paths:
  - `/Library/Application Support/Claude/org-plugins/`
  - the in-app Plugins / Connectors UI
  - local MCP configuration in Settings -> Developer where applicable
- On macOS, writing to `/Library/Application Support/Claude/org-plugins/`
  usually requires administrator privileges.
- If Cowork says your organization has not provided plugins, that usually means
  nothing has been deployed into the supported org-plugin path yet; it is not a
  bridge routing failure.

### Official plugin repos to use

- `anthropics/knowledge-work-plugins`
  - Purpose: role-based plugins primarily intended for Claude Cowork.
  - Repo: [knowledge-work-plugins](https://github.com/anthropics/knowledge-work-plugins)
  - Good starting points: `productivity`, `sales`, `customer-support`,
    `product-management`, `marketing`, `legal`, `finance`, `data`,
    `enterprise-search`, `bio-research`, `cowork-plugin-management`.
  - Notes from the repo: these plugins are built for Claude Cowork and are also
    compatible with Claude Code.

- `anthropics/claude-plugins-official`
  - Purpose: curated Anthropic-managed plugin directory with internal plugins in
    `plugins/` and partner/community plugins in `external_plugins/`.
  - Repo: [claude-plugins-official](https://github.com/anthropics/claude-plugins-official)
  - Best fit: Claude Code and the shared plugin format reference. It can also be
    mined for plugins to deploy into Cowork's `org-plugins/` directory when the
    plugin structure matches Cowork's documented org-plugin format.

### How to set up `knowledge-work-plugins` for Cowork on 3P

Anthropic's Cowork on 3P docs say organization plugins are delivered by placing
plugin folders in:

```text
/Library/Application Support/Claude/org-plugins/
```

Each subdirectory is one plugin, and the directory must contain
`.claude-plugin/plugin.json`.

Step by step:

1. Clone the repo somewhere convenient:

```bash
git clone https://github.com/anthropics/knowledge-work-plugins.git
```

2. Pick the plugin you want, for example `productivity` or `finance`.
3. Copy that plugin directory intact into the org-plugins folder so the final
   shape is:

```text
/Library/Application Support/Claude/org-plugins/productivity/
/Library/Application Support/Claude/org-plugins/finance/
```

4. If needed, customize the plugin before copying:
   - edit `.mcp.json` to match your connector/tool stack
   - edit skill markdown to reflect your team's workflows
   - optionally set `"installationPreference"` in
     `.claude-plugin/plugin.json` to one of:
     - `"required"`: auto-installs and cannot be removed by users
     - `"auto_install"`: auto-installs, but users may uninstall it
     - `"available"`: appears in the plugin browser for opt-in install
5. Restart Claude Desktop / Cowork.
6. Verify the plugin appears in the Plugins UI or auto-installs, depending on
   `installationPreference`.

### How to set up `claude-plugins-official`

There are two practical ways to use this repo:

1. `Claude Code` / plugin marketplace workflow

The repo README documents installs like:

```text
/plugin install {plugin-name}@claude-plugins-official
```

or discovery from `/plugin > Discover`.

This is the most natural fit for Claude Code and for browsing Anthropic's
curated plugin catalog.

2. `Cowork on 3P` organization-plugin workflow

If you want to use one of those plugins in Cowork on 3P, treat the individual
plugin directory as a filesystem plugin bundle:

- for Anthropic-maintained plugins, copy from `plugins/<plugin-name>/`
- for partner/community plugins, copy from `external_plugins/<plugin-name>/`
- place the chosen plugin under
  `/Library/Application Support/Claude/org-plugins/<plugin-name>/`

Keep the plugin directory structure intact, including `.claude-plugin`,
`.mcp.json`, `commands/`, `agents/`, and `skills/` where present.

### Practical guidance for this machine

- Use `knowledge-work-plugins` first if your goal is Cowork-style business
  workflows.
- Use `claude-plugins-official` first if your goal is Claude Code plugins or a
  curated plugin catalog.
- The bridge can stay exactly as-is while you do either of those. Inference
  routing and plugin delivery are separate concerns.
- If a plugin depends on remote connectors, you may also need:
  - `managedMcpServers` in the Cowork 3P configuration
  - plugin-specific `.mcp.json` edits
  - the relevant network egress allowed for Cowork's sandbox

## Testing With a Fixture

If LM Studio is not running, you can test the model sync path with a JSON file:

```bash
export LMSTUDIO_MODELS_FILE=/path/to/models.json
node bridge.mjs sync-models
```

The fixture can look like either LM Studio's richer `/api/v1/models` output or the OpenAI-compatible `/v1/models` output.

## Next iteration: moving from LM Studio bridge to OMLX

If you want a more Anthropic-doc-aligned local gateway, OMLX is the most
promising next step.

Why it is attractive:

- it already exposes Anthropic-compatible `POST /v1/messages`
- it exposes `GET /v1/models`
- it supports API-visible model aliases, so `/v1/models` can return the exact
  provider-facing ids Claude Cowork expects
- it includes model TTL, LRU eviction, and explicit memory controls
- according to the OMLX docs, it can reuse your existing LM Studio model
  directory instead of forcing a second parallel model store

Useful references:

- [Anthropic Cowork 3P configuration](https://claude.com/docs/cowork/3p/configuration)
- [Anthropic Cowork 3P installation](https://claude.com/docs/cowork/3p/installation)
- [oMLX README](https://github.com/jundot/omlx)
- [oMLX site](https://omlx.ai/)

Recommended migration plan:

1. Keep the current LM Studio bridge as the known-good baseline.
2. Install OMLX and point it at the same local model directory.
3. In OMLX, create provider-facing aliases such as:
   - `claude-haiku-4-5`
   - `claude-sonnet-4-6`
4. Expose a single local OMLX endpoint and test:
   - `GET /v1/models`
   - `POST /v1/messages`
   - tool-heavy Cowork turns
   - long streaming responses
5. Once OMLX is stable, replace the Claude Desktop 3P provider's
   `inferenceGatewayBaseUrl` with the OMLX endpoint and remove the custom
   rewrite bridge from the hot path.

Expected benefits of that migration:

- less custom glue
- provider-facing model ids that match gateway discovery more naturally
- better memory lifecycle controls for multiple large local models
- a cleaner path to future plugin and connector experiments
