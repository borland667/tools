# claude_local_bridge

## Purpose

Generic local API bridge for Claude Code and Claude Desktop/Cowork 3P profiles.
It proxies Anthropic-compatible `/v1/*` requests to local Claude-compatible
backends, adapts OpenAI-compatible `/v1/chat/completions` providers when
needed, exposes Claude-safe aggregate model discovery, and supports
profile-aware Desktop/Cowork provider configuration.

Use this when:

- You want Claude Desktop/Cowork 3P mode to use a local `gateway` provider.
- You want Claude Code to run against a local Anthropic-compatible endpoint.
- You want one bridge that can switch between `omlx` and `lmstudio`.
- You want one bridge to aggregate multiple OMLX, LM Studio, OpenAI-compatible,
  and Claude-compatible providers at the same time.
- You use multiple Claude Desktop profiles launched with `--user-data-dir`.

Do not use this when:

- The upstream only exposes OpenAI chat completions and not Anthropic
  `/v1/messages`.
- You want hosted Claude and local models in the same 3P model picker.
- You need plugin marketplace access beyond what the signed-in Claude account
  and organization provide.

## Requirements

- Node 18+.
- A local Anthropic-compatible backend:
  - OMLX on `http://127.0.0.1:8005` for the current recommended setup.
  - LM Studio on `http://127.0.0.1:1234` for legacy/local experiments.
- Claude Desktop/Cowork profile config access for 3P gateway setup.
- Python 3 for `refresh_omlx_cowork_models.py`.

## Main Files

- `/Users/borland/tools/claude_local_bridge/bridge.mjs`
- `/Users/borland/tools/claude_local_bridge/toggle_claude_local_bridge.sh`
- `/Users/borland/tools/claude_local_bridge/refresh_omlx_cowork_models.py`
- `/Users/borland/tools/claude_local_bridge/generate_claude_3p_config.py`
- `/Users/borland/tools/claude_local_bridge/bridge.config.example.json`
- `/Users/borland/tools/claude_local_bridge/claude-3p-provider.example.json`
- `/Users/borland/tools/claude_local_bridge/claude-3p-generator.example.json`
- `/Users/borland/tools/claude_local_bridge/launchd/com.borland.claude-local-bridge.plist.template`

## LaunchAgent Setup

The LaunchAgent template runs the generic bridge API in reloadable
multi-provider mode:

- Program: `/Users/borland/tools/claude_local_bridge/bridge.mjs serve`
- Working directory: `/Users/borland/tools/claude_local_bridge`
- Runtime config: `bridge.local.json` in the working directory
- Provider config: `providers.local.json` from `bridge.local.json`
- Logs: `$HOME/Library/Logs/claude-local-bridge.log`

Prepare the ignored local config files before loading launchd:

```bash
cd /Users/borland/tools/claude_local_bridge
cp bridge.config.example.json bridge.local.json
cp providers.example.json providers.local.json
```

Then copy the plist template into `$HOME/Library/LaunchAgents`, replace
`__NODE_BIN__`, `__BRIDGE_DIR__`, and `__HOME__`, validate with `plutil -lint`,
and load with `launchctl bootstrap gui/$(id -u) ...`.

The plist intentionally keeps `EnvironmentVariables` empty. Edit
`bridge.local.json` for bridge host/port, model defaults, sync interval,
non-streaming request timeout, streaming request timeout, provider file path,
Claude profile selection, and placeholder local API-key values. The bridge
re-reads `bridge.local.json` on `/sync-models` and periodic syncs; host/port
changes still require a LaunchAgent restart because the socket is already
bound. Use `claude.profileName: "local-3p"` for the local third-party inference
profile under `/Users/borland/.claude-instances/local-3p`.

## Claude Profile Model

The bridge assumes Claude Desktop profiles are isolated by Electron
`--user-data-dir`. The local reference for creating and managing those
profiles is `/Users/borland/tools/claude_multi_launcher/README.md`; see
`/Users/borland/tools/docs/scripts/claude_multi_launcher.md` for the
repository script index entry.

Default profile config:

```text
$HOME/Library/Application Support/Claude-3p/configLibrary
```

Named profile config:

```text
$HOME/.claude-instances/<profile>/configLibrary
```

Use a named profile with:

```bash
export CLAUDE_PROFILE_NAME=cowork-local
```

or pass it per command:

```bash
/Users/borland/tools/claude_local_bridge/toggle_claude_local_bridge.sh \
  --profile cowork-local \
  --status
```

Use separate profiles for hosted Claude and local bridge-backed Cowork. The 3P
gateway picker does not merge hosted Claude model entries with local gateway
entries.

## Usage Examples

Start the bridge manually:

```bash
cd /Users/borland/tools/claude_local_bridge
CLAUDE_LOCAL_INFERENCE_BACKEND=omlx \
OMLX_BASE_URL=http://127.0.0.1:8005 \
node bridge.mjs serve
```

Use a Claude profile through the bridge:

```bash
cd /Users/borland/tools/claude_local_bridge
node bridge.mjs sync-models
```

Then launch the configured local third-party inference profile from
`/Users/borland/.claude-instances/local-3p`. Profiles own the Claude app
runtime settings; the bridge owns inference routing.

Refresh a Cowork profile from live OMLX models:

```bash
cd /Users/borland/tools/claude_local_bridge
./refresh_omlx_cowork_models.py \
  --omlx-base-url http://127.0.0.1:8005 \
  --profile cowork-local \
  --apply \
  --restart-agent
```

Generate or repair the Claude 3P profile config from the working local-3p
base:

```bash
cd /Users/borland/tools/claude_local_bridge
./generate_claude_3p_config.py \
  --profile local-3p \
  --spec claude-3p-generator.example.json \
  --print-json

./generate_claude_3p_config.py \
  --profile local-3p \
  --spec claude-3p-generator.example.json \
  --apply
```

The generator emits local `configLibrary` JSON, not MDM plist/registry policy.
It understands gateway fields such as `inferenceCustomHeaders`,
`inferenceGatewayOidc`, static credentials, fixed `inferenceModels`, and
Claude model metadata such as `supports1m`, `prefer1m`,
`anthropicFamilyTier`, and `isFamilyDefault`.

The tracked example spec is intentionally permissive for a single-user local
profile: `coworkEgressAllowedHosts: ["*"]`, root workspace access, no disabled
built-in tools, bundled skills enabled, wildcard tool allow policy, local dev
MCP enabled, persistent MCP approvals enabled, desktop extensions enabled
without signature enforcement, and the Anthropic `knowledge-work-plugins` plus
`claude-plugins-official` marketplaces exposed. Tighten these keys before using
the generator for a managed or shared machine.

Toggle bridge config for one profile:

```bash
./toggle_claude_local_bridge.sh --profile cowork-local --status
./toggle_claude_local_bridge.sh --profile cowork-local --disable
./toggle_claude_local_bridge.sh --profile cowork-local --enable
```

## Key Environment Variables

- `CLAUDE_LOCAL_PROVIDERS_FILE`: JSON file for auto-reloaded provider
  definitions.
- `CLAUDE_LOCAL_PROVIDERS`: static JSON array of provider definitions for
  simultaneous multi-provider mode.
- `CLAUDE_LOCAL_INFERENCE_BACKEND`: single-provider fallback, such as `omlx`,
  `lmstudio`, `openai`, or `anthropic`.
- `CLAUDE_LOCAL_INFERENCE_BASE_URL`: generic upstream URL override.
- `OMLX_BASE_URL`: OMLX upstream URL.
- `LMSTUDIO_BASE_URL`: LM Studio upstream URL.
- `CLAUDE_LOCAL_INFERENCE_AUTH_SCHEME`: `auto`, `none`, `bearer`,
  `x-api-key`, or `both`.
- `CLAUDE_LOCAL_BRIDGE_HOST`: loopback-only bridge host. Allowed values are
  `127.0.0.1`, `localhost`, and `::1`; unsafe values such as `0.0.0.0` are
  ignored and coerced to `127.0.0.1`.
- `CLAUDE_LOCAL_BRIDGE_PORT`: bridge port, default `1245`.
- `CLAUDE_LOCAL_MAIN_MODEL`: default local model.
- `CLAUDE_LOCAL_SMALL_MODEL`: Haiku/helper model.
- `CLAUDE_LOCAL_TOOL_MODEL`: tool-heavy request model.
- `CLAUDE_LOCAL_MODEL_MAP`: JSON alias-to-route model map.
- `CLAUDE_PROFILE_NAME`: profile under `~/.claude-instances`.
- `CLAUDE_PROFILE_DIR`: explicit profile user-data directory.

Backend-specific `LMSTUDIO_*` and `OMLX_*` names are accepted for upstream
selection; bridge-specific settings use `CLAUDE_LOCAL_*`.

## Multi-Provider Mode

Use `providersFile` in `bridge.local.json` when more than one upstream should be
visible through the same local bridge and you want runtime reloads:

```bash
cp /Users/borland/tools/claude_local_bridge/providers.example.json \
  /Users/borland/tools/claude_local_bridge/providers.local.json
```

```json
{
  "providersFile": "providers.local.json"
}
```

The bridge re-reads that file on each model sync interval and whenever
`/sync-models` is called.

`providers.local.json` is ignored by git. Keep `providers.example.json` as the
tracked template, then customize the local copy with enabled providers and
`apiKeyEnv` names for each machine.

Static providers can also be embedded directly in `bridge.local.json`:

```json
{
  "providers": [
    {"id":"omlx","type":"anthropic","baseUrl":"http://127.0.0.1:8005","authScheme":"x-api-key","apiKeyEnv":"OMLX_API_KEY","label":"OMLX"},
    {"id":"lmstudio","type":"openai","baseUrl":"http://127.0.0.1:1234","authScheme":"x-api-key","apiKeyEnv":"LMSTUDIO_API_KEY","label":"LM Studio"}
  ],
  "env": {
    "OMLX_API_KEY": "local-bridge",
    "LMSTUDIO_API_KEY": "local-bridge"
  }
}
```

Legacy env-only provider config is still parsed as a fallback for tests and
one-off runs, but the LaunchAgent setup should keep settings in JSON.

By default, bridge route IDs are provider-qualified:

```text
omlx/Qwen3.5-9b-Sushi-Coder-RL-MLX
lmstudio/qwen/qwen3-coder-30b
openai/gpt-4.1-mini
anthropic/claude-sonnet-4-5
```

Direct bridge callers can use those IDs. The bridge exposes every discovered
provider model independent of inferred capabilities; embedding, reranking,
vision, image-quality, and other specialized models are visible by their
provider-qualified IDs.

Claude Desktop/Cowork 3P gateway discovery is stricter and filters model IDs
through Anthropic's model catalog. For Claude Desktop, configure
`claudeDesktopModels[]` in `bridge.local.json` so the bridge also exposes
Claude-compatible aliases such as `claude-sonnet-4-5` and routes each alias to
the real provider-qualified local target. These aliases are additive; they do
not hide the raw provider model IDs from the bridge API.

Give every usable local conversation model one unique Claude-facing alias. If
multiple local models share the same `anthropicFamilyTier`, use different
version aliases inside that tier, such as `claude-opus-4-5` and
`claude-opus-4-1`. The OMLX refresh helper validates this before writing
config.

Example:

```json
{
  "claudeDesktopModels": [
    {
      "name": "claude-sonnet-4-5",
      "target": "omlx/Qwen3.5-9b-Sushi-Coder-RL-MLX",
      "labelOverride": "Qwen3.5 Sushi Coder 9B via Local Bridge",
      "anthropicFamilyTier": "sonnet",
      "isFamilyDefault": true
    }
  ]
}
```

Current local OMLX desktop aliases:

```text
claude-sonnet-4-5          -> omlx/Qwen3.5-9b-Sushi-Coder-RL-MLX
claude-opus-4-5            -> omlx/Qwen3-Next-80B-A3B-Instruct-4bit
claude-mythos-5            -> omlx/Qwen3-Next-80B-A3B-Thinking-4bit
claude-sonnet-4-6          -> omlx/Qwen3.6-27B-Heretic-MLX-bf16
claude-opus-4-1            -> omlx/Qwen3.6-35B-A3B-MLX-4bit
claude-fable-5             -> omlx/gemma-4-12b-coder-fable5-composer2.5-8bit
claude-haiku-4-5           -> omlx/gemma-4-e4b-it-4bit
claude-haiku-4-5-20251001  -> omlx/Qwen3-VL-4B-Instruct-4bit
```

Legacy single-provider mode without `CLAUDE_LOCAL_PROVIDERS_FILE` or
`CLAUDE_LOCAL_PROVIDERS` still exposes raw upstream model IDs for compatibility
with the existing local Cowork setup. Explicit multi-provider mode always uses
provider-qualified IDs.

## Auto-Reload

Auto-reload is file-based. Edit the file referenced by
`CLAUDE_LOCAL_PROVIDERS_FILE`, then either wait for
`CLAUDE_LOCAL_MODEL_SYNC_INTERVAL_MS` or call:

```bash
curl http://127.0.0.1:1245/sync-models
```

Use `/healthz` to confirm the active source:

```bash
curl http://127.0.0.1:1245/healthz
```

### Claude Profile Model Discovery Troubleshooting

If Claude's 3P settings screen says model discovery found 0 models, first check
the bridge directly:

```bash
curl http://127.0.0.1:1245/v1/models
```

If that returns raw provider-qualified IDs such as
`omlx/Qwen3.5-9b-Sushi-Coder-RL-MLX`, the bridge is reachable but Claude will
filter those IDs out. Add Claude-facing aliases in `bridge.local.json`, then set
the active Claude profile to a fixed list using those aliases:

```json
{
  "modelDiscoveryEnabled": false,
  "inferenceModels": [
    {
      "name": "claude-sonnet-4-5",
      "labelOverride": "Qwen3.5 Sushi Coder 9B via Local Bridge",
      "anthropicFamilyTier": "sonnet",
      "isFamilyDefault": true
    }
  ]
}
```

`inferenceModels[].name` must match the exact Claude-facing ID returned from
`/v1/models`; `labelOverride` only changes what Claude displays. Fully quit and
reopen the affected Claude profile after editing because Claude reads 3P config
once at launch. If the settings dialog was open before the manual edit, discard
the stale dialog changes before relaunching so it does not remove the fixed
model list.

The bridge forwards upstream context-window metadata as `max_model_len` in
`/v1/models` for raw provider models and Claude aliases. Verify with:

```bash
curl -s http://127.0.0.1:1245/v1/models | jq '.data[] | {id, max_model_len}'
```

For OMLX, also check `~/.omlx/settings.json`: `sampling.max_context_window` is
the runtime cap. If it is lower than the model's discovered `max_model_len`, the
OMLX setting wins in practice.

For `type: "openai"` providers, the bridge adapts Anthropic `/v1/messages`
requests to OpenAI `/v1/chat/completions`. Streaming requests are returned as
Anthropic-shaped SSE after the upstream non-streaming response completes, so
they are client-compatible but not token-by-token.

For Anthropic-compatible streaming providers such as OMLX, the bridge starts
the SSE lifecycle immediately and supports a visible timeout guard for slow
local inference. The local config enables:

```json
{
  "requestTimeoutMs": 600000,
  "streamRequestTimeoutMs": 3600000,
  "streamingProgress": {
    "enabled": true,
    "delayMs": 8000,
    "intervalMs": 15000,
    "idleHeartbeatMs": 15000,
    "providerStatusEnabled": true,
    "providerStatusTimeoutMs": 1200
  }
}
```

Use `requestTimeoutMs` for short non-streaming calls such as token counting, and
`streamRequestTimeoutMs` for long-running streaming generations. Keep streaming
much higher than the normal timeout for slow local providers; large OMLX prompts
can spend more than 10 minutes in prefill before emitting visible answer text.
Set `streamRequestTimeoutMs` to `0` only when you want no bridge-side absolute
timeout for streaming requests.

Use a 15-second `idleHeartbeatMs` for slow OMLX models. Claude Desktop can run
long local generations as long as the stream receives occasional visible chunks;
the bridge starts guarding after `delayMs` and then sends a compact heartbeat at
least every `idleHeartbeatMs`, even when OMLX status remains in the same
deduplicated progress bucket.

Thinking passthrough is controlled separately:

```json
{
  "thinking": {
    "mode": "passthrough-with-progress"
  }
}
```

`passthrough-with-progress` is the default and forwards upstream Anthropic
`thinking` blocks / `thinking_delta` events so Claude can render a Thought
process when the provider emits one. `passthrough` forwards thinking without the
status fallback. `suppress` and `status-only` hide upstream thinking and keep the
older local status-block behavior. The bridge does not invent thinking for
models that do not stream it.

The guard applies to every Anthropic-compatible streaming model. If upstream
sends only hidden thinking or takes longer than `delayMs` to produce visible
text/tool output, the bridge emits a tiny one-line italic heartbeat and
occasional compact updates until real output arrives. For OMLX, the bridge also
samples `/admin/api/activity`, but only queue, prefill, generation, and ETA
essentials are shown; full diagnostics stay in bridge logs. Updates are
deduplicated by provider phase and coarse progress bucket so the UI does not
fill with repeated near-identical lines unless the idle heartbeat limit has
elapsed. This keeps Claude Desktop's stream watchdog from treating long local
prefill as an idle connection, without adding progress text to normal fast
responses. Disable by setting `streamingProgress.enabled` to `false`; disable
provider status only with
`streamingProgress.providerStatusEnabled=false`.

Bridge logs include a short request id such as `[bridge:000a]` for each proxied
request. On stream failures, the log records elapsed time, selected model,
upstream model, SSE event/byte counts, visible-output count, progress-update
count, and the last sampled OMLX provider status. Use that id with
`tail -f "$HOME/Library/Logs/claude-local-bridge.log"` and the OMLX
`server.log` timestamp to distinguish Claude UI timeouts from upstream model
unloads or request aborts.

## Safety Notes

- Use placeholder local tokens such as `local-bridge`; do not commit real
  credentials.
- The bridge API is intentionally localhost-only. Do not expose it on
  `0.0.0.0` or an external interface; the runtime refuses those bind hosts.
- Back up provider JSON before manual edits.
- Restart the exact Claude profile whose config changed.
- Keep `coworkEgressAllowedHosts` profile-specific; `["*"]` is convenient but
  intentionally permissive.
- MCP/plugin state belongs to the Claude profile. The bridge controls
  inference, not Anthropic organization plugin availability.

## Validation Checklist

```bash
cd /Users/borland/tools/claude_local_bridge
node --check bridge.mjs
bash -n toggle_claude_local_bridge.sh
python3 -m py_compile refresh_omlx_cowork_models.py
python3 -m py_compile generate_claude_3p_config.py
jq . bridge.config.example.json providers.example.json claude-3p-provider.example.json claude-3p-generator.example.json >/dev/null
node --test ../tests/claude_local_bridge/bridge.test.mjs
pytest ../tests/claude_local_bridge/generate_claude_3p_config.test.py
```

The Node test suite starts loopback-only stub providers and a loopback bridge
process. In sandboxed runners, allow local `127.0.0.1` listener binds for this
command.

Fixture sync:

```bash
CLAUDE_LOCAL_INFERENCE_MODELS_FILE=omlx-models.current.example.json \
CLAUDE_GLOBAL_CONFIG_FILE=/tmp/claude-local-bridge-test.json \
node bridge.mjs sync-models
```

Live checks:

```bash
curl http://127.0.0.1:1245/healthz
curl http://127.0.0.1:1245/v1/models
```
