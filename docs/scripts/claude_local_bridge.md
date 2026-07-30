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
- `/Users/borland/tools/claude_local_bridge/run_claude_with_local_bridge.sh`
- `/Users/borland/tools/claude_local_bridge/toggle_claude_local_bridge.sh`
- `/Users/borland/tools/claude_local_bridge/refresh_omlx_cowork_models.py`
- `/Users/borland/tools/claude_local_bridge/claude-3p-provider.example.json`
- `/Users/borland/tools/claude_local_bridge/launchd/com.borland.claude-local-bridge.plist.template`

## LaunchAgent Setup

The LaunchAgent template runs the generic bridge API in reloadable
multi-provider mode:

- Program: `/Users/borland/tools/claude_local_bridge/bridge.mjs serve`
- Bind host: `127.0.0.1` only
- Port: `1245`
- Provider config: `/Users/borland/tools/claude_local_bridge/providers.local.json`
- Logs: `$HOME/Library/Logs/claude-local-bridge.log`

Prepare the ignored local provider file before loading launchd:

```bash
cd /Users/borland/tools/claude_local_bridge
cp providers.example.json providers.local.json
```

Then copy the plist template into `$HOME/Library/LaunchAgents`, replace
`__NODE_BIN__`, `__BRIDGE_DIR__`, and `__HOME__`, validate with `plutil -lint`,
and load with `launchctl bootstrap gui/$(id -u) ...`.

The template includes placeholder `OMLX_API_KEY` and `LMSTUDIO_API_KEY` values
of `local-bridge` for local providers that only require a non-empty API key.
Do not put real cloud provider secrets in the plist; keep cloud providers
disabled or reference secrets through a machine-local mechanism.

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

Run Claude Code through the bridge:

```bash
cd /Users/borland/tools/claude_local_bridge
./run_claude_with_local_bridge.sh
```

Refresh a Cowork profile from live OMLX models:

```bash
cd /Users/borland/tools/claude_local_bridge
./refresh_omlx_cowork_models.py \
  --omlx-base-url http://127.0.0.1:8005 \
  --profile cowork-local \
  --apply \
  --restart-agent
```

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

Use `CLAUDE_LOCAL_PROVIDERS_FILE` when more than one upstream should be visible
through the same local bridge and you want runtime reloads:

```bash
cp /Users/borland/tools/claude_local_bridge/providers.example.json \
  /Users/borland/tools/claude_local_bridge/providers.local.json
export CLAUDE_LOCAL_PROVIDERS_FILE=/Users/borland/tools/claude_local_bridge/providers.local.json
```

The bridge re-reads that file on each model sync interval and whenever
`/sync-models` is called.

`providers.local.json` is ignored by git. Keep `providers.example.json` as the
tracked template, then customize the local copy with enabled providers and
`apiKeyEnv` names for each machine.

`CLAUDE_LOCAL_PROVIDERS` is also supported for static env-only configuration:

```bash
export CLAUDE_LOCAL_PROVIDERS='[
  {"id":"omlx","type":"anthropic","baseUrl":"http://127.0.0.1:8005","authScheme":"x-api-key","apiKeyEnv":"OMLX_API_KEY","label":"OMLX"},
  {"id":"lmstudio","type":"openai","baseUrl":"http://127.0.0.1:1234","authScheme":"x-api-key","apiKeyEnv":"LMSTUDIO_API_KEY","label":"LM Studio"},
  {"id":"openai","type":"openai","baseUrl":"https://api.openai.com","authScheme":"bearer","apiKeyEnv":"OPENAI_API_KEY","label":"OpenAI"},
  {"id":"anthropic","type":"anthropic","baseUrl":"https://api.anthropic.com","authScheme":"x-api-key","apiKeyEnv":"ANTHROPIC_API_KEY","anthropicVersion":"2023-06-01","label":"Anthropic"}
]'
```

Every exposed model ID is provider-qualified:

```text
omlx/Qwen3.5-9b-Sushi-Coder-RL-MLX
lmstudio/qwen/qwen3-coder-30b
openai/gpt-4.1-mini
anthropic/claude-sonnet-4-5
```

Claude Desktop/Cowork `inferenceModels[].name` must use those exact route IDs.
The bridge uses the route prefix to select the right provider, then sends the
raw upstream model ID to that provider.

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

For `type: "openai"` providers, the bridge adapts Anthropic `/v1/messages`
requests to OpenAI `/v1/chat/completions`. Streaming requests are returned as
Anthropic-shaped SSE after the upstream non-streaming response completes, so
they are client-compatible but not token-by-token.

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
bash -n run_claude_with_local_bridge.sh
bash -n toggle_claude_local_bridge.sh
python3 -m py_compile refresh_omlx_cowork_models.py
jq . claude-3p-provider.example.json >/dev/null
node --test ../tests/claude_local_bridge/bridge.test.mjs
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
