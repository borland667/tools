# LM Studio Claude Bridge

This bridge lets Anthropic-style Claude clients talk to a local LM Studio
server while keeping the client's model picker usable.

It currently supports two practical workflows on this machine:

- `Claude Code`: launched with environment variables that point directly at the
  local bridge.
- `Claude Desktop` / `Claude Cowork` 3P mode: configured as a custom
  `gateway` provider that points at the local bridge.

LM Studio already exposes an Anthropic-compatible `POST /v1/messages`
endpoint, so this bridge does not try to reimplement inference. Instead it
adds the missing glue:

- it proxies `/v1/*` requests to LM Studio,
- it rewrites Anthropic-style model names like `claude-sonnet-*` and
  `claude-haiku-*` to local LM Studio model ids,
- it syncs LM Studio's model list into Claude's local cache where applicable.

## Which local tool to use

- Use [`local_llm_mcp`](/Users/borland/tools/local_llm_mcp/README.md) if you
  want normal hosted Claude plus optional local tool delegation inside Claude
  Desktop.
- Use this bridge if you want the client's primary inference path to go to LM
  Studio through an Anthropic-compatible local endpoint.

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

### Claude Code

1. Start LM Studio's local server.
2. Run:

```bash
cd /Users/borland/tools/lmstudio_claude_bridge
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

This is the setup we validated locally.

1. Start LM Studio's local server on `http://127.0.0.1:1234`.
2. Verify LM Studio responds:

```bash
curl http://127.0.0.1:1234/v1/models
```

3. Sync the bridge's model cache:

```bash
cd /Users/borland/tools/lmstudio_claude_bridge
/usr/local/bin/node bridge.mjs sync-models
```

4. Keep the bridge running on `http://127.0.0.1:1245`.
   On this machine we use a LaunchAgent:

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
    <string>qwen3.6-35b-a3b-abliterated-heretic-mlx</string>
    <key>CLAUDE_LMSTUDIO_SMALL_MODEL</key>
    <string>qwen/qwen3-coder-30b</string>
    <key>CLAUDE_LMSTUDIO_TOOL_MODEL</key>
    <string>qwen/qwen3-coder-30b</string>
  </dict>
  <key>RunAtLoad</key>
  <true/>
  <key>KeepAlive</key>
  <true/>
</dict>
</plist>
```

5. Load that LaunchAgent:

```bash
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.borland.lmstudio-claude-bridge.plist
```

6. Confirm the bridge is healthy:

```bash
curl http://127.0.0.1:1245/healthz
```

7. Point Claude Desktop's active 3P provider config at the bridge.
   On this machine, the active provider id lives in:

```bash
~/Library/Application Support/Claude-3p/configLibrary/_meta.json
```

and the provider JSON itself lives in:

```bash
~/Library/Application Support/Claude-3p/configLibrary/<provider-id>.json
```

Set it to a fixed `gateway` config like:

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
9. Verify Claude is now targeting the bridge:

```bash
rg "inference apiHost=http://127.0.0.1:1245" ~/Library/Logs/Claude-3p/main.log
tail -f ~/Library/Logs/lmstudio-claude-bridge.log
```

You should see bridge rewrite lines such as:

- `claude-haiku-4-5` -> `qwen/qwen3-coder-30b`
- `claude-sonnet-4-6` -> `qwen3.6-35b-a3b-abliterated-heretic-mlx`

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

For Cowork/Desktop, you can also tell the bridge to prefer a more reliable
tool-calling model whenever the request includes tools:

```bash
export CLAUDE_LMSTUDIO_TOOL_MODEL=qwen/qwen3-coder-30b
```

That keeps plain chat on the larger main model while routing tool-heavy turns
such as `TaskCreate`, file edits, and other agentic calls to a model that is
less likely to omit required tool parameters.

## What the picker is showing

In Claude Desktop 3P gateway mode, the model picker shows the configured
`inferenceModels`, not LM Studio's raw model ids.

That is why the UI may show labels like:

- `Qwen Coder 30B (Haiku route)`
- `Qwen 35B A3B Abliterated (Sonnet route)`

while the bridge log shows those names being rewritten to the actual LM Studio
model ids.

This is intentional. The current Claude Desktop 3P gateway validation expects
Anthropic-style model names for the provider-facing ids, and raw Qwen ids were
rejected as not usable.

## Claude Desktop limitations we observed

- The 3P gateway picker does not merge hosted Claude models and local bridge
  models into one dropdown.
- Re-enabling the deployment mode chooser may expose the hosted Claude.ai path,
  but it does not turn the gateway picker into a mixed hosted+local model list.
- On Claude Desktop `1.8089.0`, the 3P provider health banner may still report
  `unreachable` during startup even when real runtime inference is flowing
  through the bridge. Check the bridge log before assuming inference is broken.
- Some local models still make malformed tool calls in Cowork/Desktop even when
  they advertise tool-use support. During validation on this machine,
  `qwen3.6-35b-a3b-abliterated-heretic-mlx` produced a `TaskCreate` call
  without the required `description`, while `qwen/qwen3-coder-30b` returned a
  valid tool payload immediately. `CLAUDE_LMSTUDIO_TOOL_MODEL` exists to
  mitigate that class of failure.
- Plugin availability is separate from inference. Pointing Claude Desktop at the
  local bridge does not populate the Plugins directory by itself.

## Plugins in Cowork

The local bridge only changes where inference requests go. It does not provide
plugins or marketplaces.

The current Cowork/Desktop 3P plugin UI is organization/marketplace driven.
On this machine we observed:

- the Plugins directory says the organization has not provided plugins,
- no organization plugin directory exists yet under
  `/Library/Application Support/Claude/org-plugins`,
- no local plugin marketplace has been configured for the current 3P org.

So if you want plugins in Claude Cowork with the local bridge, you need a
separate plugin distribution path:

- an organization-provided plugin bundle,
- a configured plugin marketplace repo,
- or a local marketplace flow supported by the current Claude Desktop build.

The bridge itself is not the missing piece for plugins.

## Testing With a Fixture

If LM Studio is not running, you can test the model sync path with a JSON file:

```bash
export LMSTUDIO_MODELS_FILE=/path/to/models.json
node bridge.mjs sync-models
```

The fixture can look like either LM Studio's richer `/api/v1/models` output or the OpenAI-compatible `/v1/models` output.
