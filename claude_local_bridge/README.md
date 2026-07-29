# Claude Local Bridge

Provider-neutral local bridge for Claude clients.

The bridge exposes an Anthropic-compatible local API for Claude Code and Claude
Desktop/Cowork 3P `gateway` profiles, then proxies inference requests to a
local backend such as OMLX or LM Studio. It also keeps Claude-facing model
lists usable by filtering local model discovery and, when configured, rewriting
model aliases to actual local model IDs.

## Project Path

Use the renamed generic bridge project:

```bash
cd /Users/borland/tools/claude_local_bridge
```

## Architecture

```mermaid
flowchart LR
  Claude["Claude Code or Claude Desktop profile"]
  Bridge["Claude Local Bridge :1245"]
  Backend["Local inference backend\nOMLX :8005 or LM Studio :1234"]
  Config["Profile configLibrary\ninferenceModels + gateway URL"]

  Claude --> Bridge
  Bridge --> Backend
  Bridge --> Config
```

The bridge is intentionally small:

- `GET /healthz` reports backend and selected models.
- `GET /v1/models` and `GET /api/v1/models` expose Claude-safe conversation
  model IDs.
- `POST /v1/messages` proxies Anthropic-compatible message requests upstream.
- `GET /api/claude_cli/bootstrap` returns additional model picker options for
  Claude Code builds that read that bootstrap endpoint.
- `GET /sync-models` refreshes the local model cache.

The bridge does not implement inference itself. OMLX or LM Studio must already
serve Anthropic-compatible `/v1/messages`.

## Current Recommended Setup

Validated local setup:

- OMLX server: `http://127.0.0.1:8005`
- Bridge server: `http://127.0.0.1:1245`
- LaunchAgent label: `com.borland.claude-local-bridge`
- Default/tool model: `Qwen3.5-9b-Sushi-Coder-RL-MLX`
- Claude profiles: isolated with Electron `--user-data-dir`, usually under
  `$HOME/.claude-instances/<profile>`

Keep Claude Desktop/Cowork pointed at the bridge, not directly at OMLX. The
bridge filters embedding, reranking, image-generation, and image-quality models
out of the conversation model list.

## Claude Profiles

Claude Desktop is an Electron app. Launching it with `--user-data-dir` gives
each account/profile an isolated data directory containing login state,
settings, MCP servers, desktop extensions, and Cowork 3P config.

Recommended profile pattern:

```bash
open -n -a "/Applications/Claude.app" --args \
  --user-data-dir="$HOME/.claude-instances/work"
```

Use one dedicated profile directory per account or workflow:

- `~/.claude-instances/personal`
- `~/.claude-instances/work`
- `~/.claude-instances/cowork-local`
- `~/.claude-instances/cowork-omlx`

Do not share one profile between multiple running Claude processes. The first
process owns the login/session database; extra processes against the same
profile can appear logged out or behave inconsistently.

The profile launcher workflow is documented locally in
[`../claude_multi_launcher/README.md`](../claude_multi_launcher/README.md).
That folder is our repo-local copy/reference for the multi-instance Claude
profile gist workflow. The external provenance is
[aoxborrow's Claude profile gist](https://gist.github.com/aoxborrow/5a3a0ac0aa37819cc19439b70a552221).

## Profile Config Paths

The bridge tooling understands three ways to find a Claude Desktop/Cowork 3P
provider config.

Default stock Claude profile:

```text
$HOME/Library/Application Support/Claude-3p/configLibrary
```

Named isolated profile:

```text
$HOME/.claude-instances/<profile>/configLibrary
```

Explicit profile directory:

```text
<profile-dir>/configLibrary
```

Use a named profile with helper scripts:

```bash
export CLAUDE_PROFILE_NAME=cowork-local
```

or pass it explicitly:

```bash
./toggle_claude_local_bridge.sh --profile cowork-local --status
./refresh_omlx_cowork_models.py --profile cowork-local --apply
```

Use an explicit directory when your launcher stores profiles somewhere else:

```bash
./toggle_claude_local_bridge.sh \
  --profile-dir "$HOME/.claude-instances/work" \
  --status
```

## LaunchAgent

Install the generic bridge as a user LaunchAgent so Claude Desktop/Cowork can
reach it whenever a profile starts.

Copy and fill the template:

```bash
cd /Users/borland/tools/claude_local_bridge
cp launchd/com.borland.claude-local-bridge.plist.template \
  "$HOME/Library/LaunchAgents/com.borland.claude-local-bridge.plist"
```

Replace placeholders:

- `__NODE_BIN__`: usually `/usr/local/bin/node` or `/opt/homebrew/bin/node`
- `__BRIDGE_DIR__`: `/Users/borland/tools/claude_local_bridge`
- `__HOME__`: `/Users/borland`

Validate and load:

```bash
plutil -lint "$HOME/Library/LaunchAgents/com.borland.claude-local-bridge.plist"
launchctl bootstrap gui/$(id -u) \
  "$HOME/Library/LaunchAgents/com.borland.claude-local-bridge.plist"
```

After editing LaunchAgent environment variables, fully reload it. `kickstart`
alone may keep launchd's cached environment:

```bash
launchctl bootout gui/$(id -u) \
  "$HOME/Library/LaunchAgents/com.borland.claude-local-bridge.plist"
launchctl bootstrap gui/$(id -u) \
  "$HOME/Library/LaunchAgents/com.borland.claude-local-bridge.plist"
```

Check status:

```bash
launchctl print gui/$(id -u)/com.borland.claude-local-bridge
curl http://127.0.0.1:1245/healthz
```

## Environment

Prefer generic names:

```bash
export CLAUDE_LOCAL_INFERENCE_BACKEND=omlx
export CLAUDE_LOCAL_INFERENCE_BASE_URL=http://127.0.0.1:8005
export CLAUDE_LOCAL_INFERENCE_AUTH_SCHEME=x-api-key
export CLAUDE_LOCAL_INFERENCE_API_KEY=local-bridge
export CLAUDE_LOCAL_BRIDGE_HOST=127.0.0.1
export CLAUDE_LOCAL_BRIDGE_PORT=1245
export CLAUDE_LOCAL_MAIN_MODEL=Qwen3.5-9b-Sushi-Coder-RL-MLX
export CLAUDE_LOCAL_SMALL_MODEL=Qwen3.5-9b-Sushi-Coder-RL-MLX
export CLAUDE_LOCAL_TOOL_MODEL=Qwen3.5-9b-Sushi-Coder-RL-MLX
```

Supported upstream backends:

- `omlx`: defaults to `http://127.0.0.1:8000`, bearer auth when auth is `auto`
- `lmstudio`: defaults to `http://127.0.0.1:1234`, `x-api-key` when auth is
  `auto`

Generic variables:

- `CLAUDE_LOCAL_INFERENCE_BACKEND`: `omlx` or `lmstudio`
- `CLAUDE_LOCAL_INFERENCE_BASE_URL`: overrides backend-specific URLs
- `CLAUDE_LOCAL_INFERENCE_API_KEY`: optional upstream API key
- `CLAUDE_LOCAL_INFERENCE_AUTH_SCHEME`: `auto`, `none`, `bearer`, `x-api-key`,
  or `both`
- `CLAUDE_LOCAL_INFERENCE_MODELS_FILE`: fixture JSON for offline testing
- `CLAUDE_LOCAL_MODEL_MAP`: JSON object of route ID to upstream model ID
- `CLAUDE_PROFILE_NAME`: profile under `~/.claude-instances`
- `CLAUDE_PROFILE_DIR`: explicit profile user-data dir

`LMSTUDIO_*` and `OMLX_*` remain backend-specific variables. The bridge's own
configuration uses `CLAUDE_LOCAL_*`.

## OMLX Setup

Start OMLX and verify model discovery:

```bash
curl http://127.0.0.1:8005/v1/models
```

Refresh the bridge/provider config from live OMLX models:

```bash
cd /Users/borland/tools/claude_local_bridge
./refresh_omlx_cowork_models.py \
  --omlx-base-url http://127.0.0.1:8005 \
  --profile cowork-local \
  --apply \
  --restart-agent
```

Dry run first if you want to inspect the planned route map:

```bash
./refresh_omlx_cowork_models.py \
  --omlx-base-url http://127.0.0.1:8005 \
  --profile cowork-local \
  --print-json
```

The refresh helper:

- fetches live OMLX `/v1/models`
- drops non-conversation models
- chooses a default/tool model by local heuristics
- writes `inferenceModels` with exact gateway model IDs
- updates `CLAUDE_LOCAL_MODEL_MAP` in the bridge LaunchAgent
- backs up changed provider/plist files before writing
- optionally restarts the LaunchAgent

## Claude Desktop / Cowork 3P Provider

For Anthropic's `gateway` provider mode, `inferenceModels[].name` must match an
exact model ID returned by the gateway `/v1/models` endpoint. `labelOverride`
is display-only.

Minimum provider fields:

```json
{
  "deploymentOrganizationUuid": "11111111-2222-4333-8444-555555555555",
  "coworkEgressAllowedHosts": ["*"],
  "inferenceGatewayApiKey": "local-bridge",
  "inferenceGatewayAuthScheme": "x-api-key",
  "inferenceGatewayBaseUrl": "http://127.0.0.1:1245",
  "inferenceProvider": "gateway",
  "isDesktopExtensionEnabled": true,
  "modelDiscoveryEnabled": false,
  "inferenceModels": [
    {
      "name": "Qwen3.5-9b-Sushi-Coder-RL-MLX",
      "labelOverride": "Qwen3.5 Sushi Coder 9B via Local Bridge"
    }
  ]
}
```

Important behavior:

- `modelDiscoveryEnabled: false` keeps the explicit list stable.
- `inferenceModels[0]` is the default picker entry.
- `coworkEgressAllowedHosts: ["*"]` allows Cowork/plugin/network side effects
  broadly; tighten this per profile if you want stricter egress.
- Hosted Claude models do not merge into the same 3P gateway picker. Use
  separate profiles if you want one profile on hosted Claude and another on
  local bridge-backed models.

## Toggle Per Profile

The toggle script switches one profile's active provider config between two
snapshots:

- `<provider-id>.json.bridge-on.bak`
- `<provider-id>.json.bridge-off.bak`

Check status:

```bash
./toggle_claude_local_bridge.sh --profile cowork-local --status
```

Disable bridge for that profile:

```bash
./toggle_claude_local_bridge.sh --profile cowork-local --disable
```

Enable bridge again:

```bash
./toggle_claude_local_bridge.sh --profile cowork-local --enable
```

If the first disable cannot auto-detect a pre-bridge backup, seed it:

```bash
./toggle_claude_local_bridge.sh \
  --profile cowork-local \
  --disable \
  --baseline /path/to/pre-bridge-provider.json
```

## Claude Code

Run Claude Code against the bridge:

```bash
cd /Users/borland/tools/claude_local_bridge
./run_claude_with_local_bridge.sh
```

That script:

- starts a foreground bridge for the session
- exports `ANTHROPIC_BASE_URL=http://127.0.0.1:1245`
- sets local placeholder auth values
- syncs the local model picker cache
- runs `claude`

Override backend/model choices before launching:

```bash
export CLAUDE_LOCAL_INFERENCE_BACKEND=omlx
export OMLX_BASE_URL=http://127.0.0.1:8005
export CLAUDE_LOCAL_MAIN_MODEL=Qwen3.5-9b-Sushi-Coder-RL-MLX
export CLAUDE_LOCAL_TOOL_MODEL=Qwen3.5-9b-Sushi-Coder-RL-MLX
./run_claude_with_local_bridge.sh
```

## MCP And Plugins

MCP and inference are separate layers:

- This bridge controls the primary inference API path.
- Claude Desktop profile config controls which MCP servers/extensions/plugins
  are available to that profile.
- A profile launched with `--user-data-dir` has its own MCP settings and
  desktop extension state.
- Plugin availability in Claude Desktop can still depend on Anthropic account
  or organization policy. The local bridge cannot make the official plugin
  directory show organization-managed plugins.

Recommended pattern:

- Put local inference experiments in a dedicated profile, for example
  `cowork-local`.
- Configure MCP servers inside that profile, not the stock profile.
- Use `coworkEgressAllowedHosts` per profile to decide how permissive tools and
  plugin side effects should be.
- Use [`local_llm_mcp`](../local_llm_mcp/README.md) when you want hosted Claude
  inference plus local model delegation as tools.
- Use this bridge when you want Claude's primary inference to be local.

## Model Mapping

If `CLAUDE_LOCAL_MODEL_MAP` is set, `/v1/models` returns the configured route
IDs whose targets exist upstream.

Identity mapping is recommended for Cowork gateway mode:

```bash
export CLAUDE_LOCAL_MODEL_MAP='{"Qwen3.5-9b-Sushi-Coder-RL-MLX":"Qwen3.5-9b-Sushi-Coder-RL-MLX"}'
```

Alias mapping is still useful for Claude Code and experiments:

```bash
export CLAUDE_LOCAL_MODEL_MAP='{"default":"Qwen3.5-9b-Sushi-Coder-RL-MLX","claude-sonnet-4-5":"Qwen3.5-9b-Sushi-Coder-RL-MLX"}'
```

When a request includes tools and the requested model looks like an Anthropic
alias, `CLAUDE_LOCAL_TOOL_MODEL` can force a more reliable tool-calling model.
This is a bridge behavior, not an Anthropic provider config key.

## Validation

Syntax checks:

```bash
node --check bridge.mjs
bash -n run_claude_with_local_bridge.sh
bash -n toggle_claude_local_bridge.sh
python3 -m py_compile refresh_omlx_cowork_models.py
```

Offline model sync with fixture:

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

Logs:

```bash
tail -f "$HOME/Library/Logs/claude-local-bridge.log"
```

## Files

- `bridge.mjs`: provider-neutral Anthropic-compatible proxy
- `run_claude_with_local_bridge.sh`: Claude Code launcher
- `toggle_claude_local_bridge.sh`: Desktop/Cowork profile toggle
- `refresh_omlx_cowork_models.py`: live OMLX model refresh helper
- `claude-3p-provider.example.json`: editable provider example
- `launchd/com.borland.claude-local-bridge.plist.template`: LaunchAgent template
## Safety Notes

- Do not commit real API keys, tokens, profile databases, or `.env` files.
- Use placeholder local tokens such as `local-bridge` for localhost auth.
- Back up provider JSON before hand-editing it.
- Restart the exact Claude profile you changed; other profiles have separate
  config and may continue using their old provider state.
