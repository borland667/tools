# Claude Local Bridge

Provider-neutral local bridge for Claude clients.

The bridge exposes an Anthropic-compatible local API for Claude Code and Claude
Desktop/Cowork 3P `gateway` profiles, then proxies inference requests to a
local backend such as OMLX or LM Studio. It also keeps Claude-facing model
lists usable by aggregating local model discovery and, when configured,
rewriting model aliases to actual local model IDs.

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
  Backend["Local inference backends\nOMLX, LM Studio, OpenAI, Claude-compatible"]
  Config["Profile configLibrary\ninferenceModels + gateway URL"]

  Claude --> Bridge
  Bridge --> Backend
  Bridge --> Config
```

The bridge is intentionally small:

- `GET /healthz` reports provider health and selected models.
- `GET /v1/models` and `GET /api/v1/models` expose every discovered provider
  model plus any configured Claude-facing aliases.
- `POST /v1/messages` proxies Anthropic-compatible providers directly and
  adapts OpenAI-compatible providers through `/v1/chat/completions`.
- Image-bearing Claude alias requests can be routed to a dedicated vision
  model with `models.vision` / `CLAUDE_LOCAL_VISION_MODEL`.
- `GET /api/claude_cli/bootstrap` returns additional model picker options for
  Claude Code builds that read that bootstrap endpoint.
- `GET /sync-models` refreshes the local model cache.
- `generate_claude_3p_config.py` generates Claude Desktop/Cowork
  `configLibrary` entries for isolated 3P profiles.

The bridge does not implement inference itself. Anthropic-compatible providers
must serve `/v1/messages`; OpenAI-compatible providers must serve
`/v1/chat/completions`.

## Current Recommended Setup

Validated local setup:

- OMLX server: `http://127.0.0.1:8005`
- Bridge server: `http://127.0.0.1:1245`
- LaunchAgent label: `com.borland.claude-local-bridge`
- Default/tool route: `omlx/Qwen3.5-9b-Sushi-Coder-RL-MLX`
- Vision route: `omlx/Qwen3-VL-4B-Instruct-4bit`
- Claude profiles: isolated with Electron `--user-data-dir`, usually under
  `$HOME/.claude-instances/<profile>`

Keep Claude Desktop/Cowork pointed at the bridge, not directly at OMLX. The
bridge aggregates every discovered provider model. Capability hints still
inform request routing and default-model heuristics, but they do not remove
models from discovery.

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

Install the generic bridge API as a user LaunchAgent so Claude Desktop/Cowork
can reach it whenever a profile starts. The LaunchAgent plist stays minimal:
it only runs `bridge.mjs serve` from this directory. Runtime settings live in
`bridge.local.json`, so normal changes do not require editing XML.

Prepare the ignored local config files first:

```bash
cd /Users/borland/tools/claude_local_bridge
cp bridge.config.example.json bridge.local.json
cp providers.example.json providers.local.json
```

`bridge.local.json` is loaded from the LaunchAgent `WorkingDirectory`, which is
`/Users/borland/tools/claude_local_bridge`. It points at `providers.local.json`
by default. Keep local providers such as OMLX and LM Studio on loopback. If you
enable cloud providers, keep `apiKeyEnv` references and set those secrets
outside git; do not write real keys into the plist.

Copy and fill the template:

```bash
cp launchd/com.borland.claude-local-bridge.plist.template \
  "$HOME/Library/LaunchAgents/com.borland.claude-local-bridge.plist"
```

Replace placeholders:

- `__NODE_BIN__`: usually `/usr/local/bin/node` or `/opt/homebrew/bin/node`
- `__BRIDGE_DIR__`: `/Users/borland/tools/claude_local_bridge`
- `__HOME__`: `/Users/borland`

The template keeps an empty `EnvironmentVariables` dict on purpose. The bridge
defaults to `bridge.local.json` in the working directory. That JSON file sets
the bridge host/port, model defaults, provider file, sync interval, request
timeout, and placeholder local provider keys.

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

For launchd, prefer `bridge.local.json` in the bridge working directory:

```bash
cp bridge.config.example.json bridge.local.json
```

Environment variables are still supported as overrides for tests and one-off
runs, but the installed LaunchAgent intentionally avoids bridge settings in the
plist.

For one provider, generic names are enough:

```bash
export CLAUDE_LOCAL_INFERENCE_BACKEND=omlx
export CLAUDE_LOCAL_INFERENCE_BASE_URL=http://127.0.0.1:8005
export CLAUDE_LOCAL_INFERENCE_AUTH_SCHEME=x-api-key
export CLAUDE_LOCAL_INFERENCE_API_KEY=local-bridge
export CLAUDE_LOCAL_BRIDGE_HOST=127.0.0.1
export CLAUDE_LOCAL_BRIDGE_PORT=1245
export CLAUDE_LOCAL_MAIN_MODEL=omlx/Qwen3.5-9b-Sushi-Coder-RL-MLX
export CLAUDE_LOCAL_SMALL_MODEL=omlx/Qwen3.5-9b-Sushi-Coder-RL-MLX
export CLAUDE_LOCAL_TOOL_MODEL=omlx/Qwen3.5-9b-Sushi-Coder-RL-MLX
export CLAUDE_LOCAL_VISION_MODEL=omlx/Qwen3-VL-4B-Instruct-4bit
```

For multiple simultaneous providers, prefer a reloadable provider file:

```bash
cp providers.example.json providers.local.json
export CLAUDE_LOCAL_PROVIDERS_FILE=/Users/borland/tools/claude_local_bridge/providers.local.json
```

The bridge re-reads `CLAUDE_LOCAL_PROVIDERS_FILE` on every model sync. The
default sync interval is `30000` ms and can be changed with:

```bash
export CLAUDE_LOCAL_MODEL_SYNC_INTERVAL_MS=10000
```

You can also use static env-only JSON with `CLAUDE_LOCAL_PROVIDERS`:

```bash
export CLAUDE_LOCAL_PROVIDERS='[
  {
    "id": "omlx",
    "type": "anthropic",
    "baseUrl": "http://127.0.0.1:8005",
    "authScheme": "x-api-key",
    "apiKeyEnv": "OMLX_API_KEY",
    "label": "OMLX"
  },
  {
    "id": "lmstudio",
    "type": "openai",
    "baseUrl": "http://127.0.0.1:1234",
    "authScheme": "x-api-key",
    "apiKeyEnv": "LMSTUDIO_API_KEY",
    "label": "LM Studio"
  },
  {
    "id": "openai",
    "type": "openai",
    "baseUrl": "https://api.openai.com",
    "authScheme": "bearer",
    "apiKeyEnv": "OPENAI_API_KEY",
    "label": "OpenAI"
  },
  {
    "id": "anthropic",
    "type": "anthropic",
    "baseUrl": "https://api.anthropic.com",
    "authScheme": "x-api-key",
    "apiKeyEnv": "ANTHROPIC_API_KEY",
    "anthropicVersion": "2023-06-01",
    "label": "Anthropic"
  }
]'
```

Provider fields:

- `id`: stable route prefix. Exposed model IDs become `<id>/<model-id>`.
- `type`: `anthropic` for Claude-compatible `/v1/messages`, or `openai` for
  OpenAI-compatible `/v1/chat/completions`.
- `baseUrl`: provider API root, without the trailing `/v1` path when possible.
- `authScheme`: `auto`, `none`, `bearer`, `x-api-key`, or `both`.
- `apiKeyEnv`: environment variable that contains the secret key. Prefer this
  over inline `apiKey` so secrets are not written into plist files or docs.
- `label`: human-readable provider label for picker entries and diagnostics.
- `modelsFile`: optional fixture file for offline tests.

Internally, the aggregate catalog uses provider-qualified route IDs, for example:

```text
omlx/Qwen3.5-9b-Sushi-Coder-RL-MLX
lmstudio/qwen/qwen3-coder-30b
openai/gpt-4.1-mini
anthropic/claude-sonnet-4-5
```

Claude Code and direct bridge callers can use those route IDs. Claude
Desktop/Cowork 3P gateway discovery is stricter: expose Claude-compatible model
IDs with `claudeDesktopModels[]`, then map each alias to the real route ID.
This lets Claude see `claude-sonnet-4-5` while the bridge sends
`omlx/Qwen3.5-9b-Sushi-Coder-RL-MLX` upstream.

For backward compatibility, if neither `CLAUDE_LOCAL_PROVIDERS_FILE` nor
`CLAUDE_LOCAL_PROVIDERS` is set and the bridge is running in legacy
single-provider mode, the bridge keeps exposing raw upstream model IDs. As soon
as file/env multi-provider config is set, use provider-qualified IDs.

OpenAI-compatible providers are adapted from Anthropic `/v1/messages` to
OpenAI `/v1/chat/completions`. When Claude requests streaming for an OpenAI
provider, the bridge asks the upstream for a non-streaming chat completion and
then emits Anthropic-shaped SSE events. That preserves Claude client
compatibility, but it is buffered rather than token-by-token streaming.

## Tool And Vision Routing

Claude Desktop/Cowork can choose internal Claude-family aliases that differ
from the model label selected in the UI. For example, an image prompt may be
sent as an opus-family request even when the profile later shows a sonnet-family
model. The bridge therefore treats tools and images as request capabilities,
not just picker labels.

When a request includes tools and the requested model looks like an Anthropic
alias, the bridge first checks whether the selected route is tool-capable. If
it is, the tool-shaped request stays on that selected model. If it is not,
`models.tool` or `CLAUDE_LOCAL_TOOL_MODEL` can force a more reliable
tool-calling model. When a request includes Anthropic image content blocks and
the requested model looks like an Anthropic alias, the bridge applies the same
pattern for vision: selected vision-capable routes stay selected, and
non-vision routes fall back to `models.vision` or
`CLAUDE_LOCAL_VISION_MODEL`. Exact provider-qualified model IDs, such as
`omlx/Qwen3-VL-4B-Instruct-4bit`, are left alone because they are not
Anthropic aliases.

For the current OMLX setup, keep:

```json
{
  "models": {
    "main": "claude-sonnet-4-5",
    "small": "claude-haiku-4-5",
    "tool": "claude-sonnet-4-5",
    "vision": "claude-haiku-4-5-20251001"
  }
}
```

The `claude-haiku-4-5-20251001` alias maps to
`omlx/Qwen3-VL-4B-Instruct-4bit`. This avoids routing image prompts to
`Qwen3.6-35B-A3B-Claude-Opus-VL-grafted-MLX-8bit`, which has been observed to
fail in OMLX with `409 Conflict` and a VLM load error about missing parameters.
Models that are tested and known to handle images, such as
`Qwen3.6-27B-Heretic-MLX-bf16`, can set `visionCapable: true` on their
Claude-facing alias so image requests selected from that alias are not
redirected to the fallback vision route.
Models that should keep tool-shaped Claude requests, even when
`models.tool` points elsewhere, can set `toolCapable: true` on their
Claude-facing alias.

## Auto-Reload

Auto-reload applies to `bridge.local.json`, provider-file changes, model
discovery, route maps, health state, and Claude Code model option cache. It
does not reload process environment variables because launchd and shells do not
mutate a running process environment. It also does not reload changed
JavaScript source code; restart the LaunchAgent after changing `bridge.mjs`.

Use this for reloadable provider changes:

```bash
export CLAUDE_LOCAL_PROVIDERS_FILE=/Users/borland/tools/claude_local_bridge/providers.local.json
```

Then edit `providers.local.json`. Within the next sync interval, or
immediately after calling `/sync-models`, the bridge will re-read providers,
rebuild `/v1/models`, rebuild routes, and refresh `/healthz`.

Force a reload immediately:

```bash
curl http://127.0.0.1:1245/sync-models
```

Check the active source:

```bash
curl http://127.0.0.1:1245/healthz
```

Look for `providerConfigSource` and `providerConfigReloadable`.

The LaunchAgent template expects `providers.local.json`, which is ignored by
git. Create it from `providers.example.json`, then customize enabled providers
and `apiKeyEnv` values for the machine.

Supported single-provider backend shortcuts:

- `omlx`: defaults to `http://127.0.0.1:8000`, bearer auth when auth is `auto`
- `lmstudio`: defaults to `http://127.0.0.1:1234`, `x-api-key` when auth is
  `auto`

Generic variables:

- `CLAUDE_LOCAL_INFERENCE_BACKEND`: `omlx` or `lmstudio`
- `CLAUDE_LOCAL_PROVIDERS_FILE`: reloadable provider JSON file
- `CLAUDE_LOCAL_BRIDGE_HOST`: loopback-only bridge listen host. Allowed values
  are `127.0.0.1`, `localhost`, and `::1`; unsafe values such as `0.0.0.0`
  are ignored and coerced to `127.0.0.1`.
- `CLAUDE_LOCAL_INFERENCE_BASE_URL`: overrides backend-specific URLs
- `CLAUDE_LOCAL_INFERENCE_API_KEY`: optional upstream API key
- `CLAUDE_LOCAL_INFERENCE_AUTH_SCHEME`: `auto`, `none`, `bearer`, `x-api-key`,
  or `both`
- `CLAUDE_LOCAL_INFERENCE_MODELS_FILE`: fixture JSON for offline testing
- `CLAUDE_LOCAL_MODEL_MAP`: JSON object of alias to provider-qualified route ID
- `CLAUDE_PROFILE_NAME`: profile under `~/.claude-instances`
- `CLAUDE_PROFILE_DIR`: explicit profile user-data dir

`LMSTUDIO_*`, `OMLX_*`, `OPENAI_*`, and `ANTHROPIC_*` remain provider-specific
variables. The bridge's own configuration uses `CLAUDE_LOCAL_*`.

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
- keeps the bridge provider model list complete
- generates Claude-compatible aliases for local models suitable for primary
  chat inference
- chooses a default/tool model by local heuristics
- writes `inferenceModels` with Claude-compatible gateway alias IDs
- updates `bridge.local.json` and `providers.local.json`
- backs up changed provider/config files before writing
- optionally restarts the LaunchAgent

## Claude Desktop / Cowork 3P Provider

For Anthropic's `gateway` provider mode, Claude filters `/v1/models` through
its Anthropic model catalog. Do not expose raw local IDs such as
`omlx/Qwen3.5-9b-Sushi-Coder-RL-MLX` directly to Claude Desktop. Configure
`claudeDesktopModels[]` in `bridge.local.json` so `/v1/models` returns
Claude-compatible aliases, and set `inferenceModels[].name` to those aliases.
`labelOverride` is display-only and should carry the real local model label.

The generator follows Anthropic's Claude Desktop 3P configuration reference:
local user configs live under `configLibrary`, `_meta.json` selects the active
entry, gateway configs use `inferenceGatewayBaseUrl`,
`inferenceGatewayApiKey`, and `inferenceGatewayAuthScheme`, and
`inferenceModels[].name` must be the exact model ID returned by the gateway.
The official reference also notes that managed macOS/Windows policy stores
encode array/object keys as JSON strings, while local `configLibrary` files use
normal JSON values.

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
      "name": "claude-sonnet-4-5",
      "labelOverride": "Qwen3.5 Sushi Coder 9B via Local Bridge",
      "anthropicFamilyTier": "sonnet",
      "isFamilyDefault": true
    }
  ]
}
```

Important behavior:

- `modelDiscoveryEnabled: false` keeps the explicit list stable.
- `inferenceModels[0]` is the default picker entry.
- `inferenceModels[].name` must match the Claude-facing ID returned by the
  bridge `/v1/models`, not the hidden upstream local model ID.
- `coworkEgressAllowedHosts: ["*"]` allows Cowork/plugin/network side effects
  broadly; tighten this per profile if you want stricter egress.
- Hosted Claude models do not merge into the same 3P gateway picker. Use
  separate profiles if you want one profile on hosted Claude and another on
  local bridge-backed models.

### Generate A Profile Config

Use `generate_claude_3p_config.py` when you want to reproduce or repair the
Claude Desktop/Cowork 3P provider entry itself. It uses the working
`~/.claude-instances/local-3p/configLibrary` profile as the default base, keeps
the local bridge fields aligned with the official 3P `gateway` shape, and is
dry-run by default.

Dry run against the local-3p profile and print the generated config with
sensitive fields redacted:

```bash
cd /Users/borland/tools/claude_local_bridge
./generate_claude_3p_config.py \
  --profile local-3p \
  --spec claude-3p-generator.example.json \
  --print-json
```

Apply the generated config to the same profile:

```bash
./generate_claude_3p_config.py \
  --profile local-3p \
  --spec claude-3p-generator.example.json \
  --apply
```

Generate a separate profile from the local-3p base:

```bash
./generate_claude_3p_config.py \
  --base-profile local-3p \
  --profile cowork-omlx \
  --name "Local OMLX Bridge" \
  --config-id "$(uuidgen)" \
  --apply
```

Model sources:

- `bridge-config`: default; reads `claudeDesktopModels[]` from
  `bridge.local.json`.
- `bridge-live`: fetches `GET /v1/models` from the bridge.
- `base`: reuses `inferenceModels` from the base config.
- `file`: reads a JSON file containing `inferenceModels`, `data`, `models`, or
  `items`.

Permissive single-user defaults:

- `permissive: true` is the example-spec default. Pass `--strict-local` or set
  `permissive: false` when you want a smaller generated config.
- Public egress is open with `coworkEgressAllowedHosts: ["*"]`.
- Workspace access is open with `allowedWorkspaceFolders: [{"path": "/"}]`.
  Leaving this key unset is also unrestricted, but the generator writes it
  explicitly so the local profile is self-documenting.
- Built-in tools and bundled skills are enabled with
  `disabledBuiltinTools: []`, `disableBundledSkills: false`, and
  `builtinToolPolicy: {"*": "allow"}`.
- Chat, Code, Cowork, Auto mode, tool search, advanced file analysis, local dev
  MCP, persistent MCP approvals, and unsigned desktop extensions are enabled.
- `managedMcpServers` defaults to an empty list, ready for explicit local or
  remote MCP server entries in the spec.
- Plugin-delivered MCP tools are pre-approved through `orgPluginSettings`, and
  the Anthropic `knowledge-work-plugins` and `claude-plugins-official`
  repositories are exposed through `allowedPluginMarketplaces`.

Gateway extras supported by the spec:

- `gateway.customHeaders`: writes `inferenceCustomHeaders`.
- `gateway.oidc`: writes `inferenceGatewayOidc`.
- `gateway.sessionLifetimeSec`: writes `inferenceSessionLifetimeSec`.
- Model entries preserve `supports1m`, `prefer1m`,
  `anthropicFamilyTier`, and `isFamilyDefault` when present.
- `workspace`, `connectors`, `plugins`, `usageLimits`, `appearance`,
  `updates`, `telemetry`, `bootstrap`, `source`, and `extra` sections map to
  the same top-level keys used by Claude's 3P configuration reference.

Secret handling:

- By default, generated configs use placeholder localhost auth such as
  `local-bridge` instead of preserving copied secret fields.
- Pass `--preserve-secret-values` only for private local profile generation.
- Do not commit generated profile configs containing real keys, custom
  inference headers, or profile account state.

### If Claude Shows "Gateway Returned No Usable Models"

When `curl http://127.0.0.1:1245/v1/models` returns models but the Claude 3P
settings screen reports "found 0 models" or "Gateway returned no usable
models", check the IDs in the response. If they are raw local/provider IDs such
as `omlx/Qwen3.5-9b-Sushi-Coder-RL-MLX`, Claude reached the bridge but filtered
them out because they are not Anthropic catalog IDs.

Fix the active profile config by setting:

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

Use alias IDs copied exactly from the bridge `/v1/models` response. The bridge
routes those aliases to provider-qualified local targets configured in
`bridge.local.json`.

After editing the config file, fully quit and reopen the exact Claude profile.
Claude reads the 3P config once at launch. If the in-app settings dialog was
already open, choose `Discard Changes` before relaunching; applying a stale
dialog can overwrite the static `inferenceModels` list and put the profile back
into discovery-only mode.

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
export CLAUDE_LOCAL_MAIN_MODEL=omlx/Qwen3.5-9b-Sushi-Coder-RL-MLX
export CLAUDE_LOCAL_TOOL_MODEL=omlx/Qwen3.5-9b-Sushi-Coder-RL-MLX
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

`/v1/models` is built from every configured provider and includes every
discovered provider model, independent of inferred capabilities. Embedding,
reranking, vision, image-quality, and other specialized models remain visible
and routable by their provider-qualified IDs. Capability hints only affect
automatic fallback routing for tool/image requests and default-model selection.

`CLAUDE_LOCAL_MODEL_MAP` is now for aliases such as `default`, `coder`, or
Anthropic-style model names that should route to one of those provider-qualified
model IDs.

For Claude Desktop/Cowork 3P, prefer `claudeDesktopModels[]` in
`bridge.local.json`. These aliases are added alongside raw provider models,
not used as a replacement list:

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

- `name`: Claude-facing model ID returned by `/v1/models`.
- `target`: provider-qualified local route ID or raw upstream model ID.
- `labelOverride`: local model label shown in Claude's picker.
- `anthropicFamilyTier`: optional Claude tier mapping for alias resolution.
- `toolCapable`: optional boolean; when true, tool-shaped requests selected
  through this alias stay on this route instead of falling back to
  `models.tool`.
- `visionCapable`: optional boolean; when true, image requests selected through
  this alias stay on this route instead of falling back to `models.vision`.
- `maxContextLength` / `max_model_len`: optional override for the advertised
  alias context window; by default aliases inherit the target model's upstream
  context metadata.
- `isFamilyDefault`: optional winner when several entries share a tier.

Every usable local conversation model should have exactly one Claude-facing
alias. When several local models use the same `anthropicFamilyTier`, give each
one a different Claude model version alias, for example `claude-opus-4-5` and
`claude-opus-4-1`. The refresh helper validates this and refuses to write a
partial or duplicate alias table.

### Context Windows

The bridge preserves provider context-window metadata in `/v1/models`. OMLX
reports this as `max_model_len`; the bridge forwards it for raw provider routes
and for Claude-facing aliases. Check what Claude/config tooling can discover:

```bash
curl -s http://127.0.0.1:1245/v1/models | jq '.data[] | {id, max_model_len}'
```

This is the advertised model capacity. OMLX also has a runtime cap in
`~/.omlx/settings.json` at `sampling.max_context_window`; if that value is lower
than a model's `max_model_len`, the OMLX runtime cap is the practical limit.
For long Cowork/code tasks, keep the OMLX runtime context window at least as
large as the models exposed through the bridge.

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

Alias mapping can make Claude Code and experiments easier:

```bash
export CLAUDE_LOCAL_MODEL_MAP='{"coder":"omlx/Qwen3.5-9b-Sushi-Coder-RL-MLX"}'
```

Anthropic-style alias mapping is also supported:

```bash
export CLAUDE_LOCAL_MODEL_MAP='{"default":"omlx/Qwen3.5-9b-Sushi-Coder-RL-MLX","claude-sonnet-4-5":"omlx/Qwen3.5-9b-Sushi-Coder-RL-MLX"}'
```

When a request includes tools or image content and the requested model looks
like an Anthropic alias, `CLAUDE_LOCAL_TOOL_MODEL` and
`CLAUDE_LOCAL_VISION_MODEL` can force more reliable capability-specific models.
Tool fallback is skipped when the selected route is marked `toolCapable: true`.
Vision fallback is skipped when the selected route is already marked or
detected as vision-capable. This is bridge behavior, not an Anthropic provider
config key.

## Validation

Syntax checks:

```bash
node --check bridge.mjs
bash -n run_claude_with_local_bridge.sh
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
tail -f "$HOME/.omlx/logs/server.log"
```

The bridge log shows local routing decisions, such as
`claude-sonnet-4-6 -> omlx/Qwen3.6-27B-Heretic-MLX-bf16`. The OMLX server log is the
source of truth for upstream model load failures, token generation timings, and
image parser errors. The OMLX dashboard log viewer at
`http://127.0.0.1:8005/admin/dashboard?tab=logs` reads from the same log
directory and rotates daily files like `server.log.2026-07-29`.

Each proxied request also gets a short bridge request id in log lines, for
example `[bridge:000a]`. Grep that id to follow one request from route
selection through upstream response, progress updates, completion, or mid-stream
failure. Stream-failure logs include elapsed time, selected Claude-facing model,
upstream provider model, event/byte counts, visible-output count, progress
update count, and the last sampled provider status from OMLX when available.

### If Claude Shows "Stream Idle Timeout"

Claude Desktop may display `API Error: Stream idle timeout - no chunks
received` when the gateway does not send a usable streaming event quickly
enough. This can happen with local OMLX models during model load, prompt
prefill, long tool-context requests, or when a selected model stalls before
emitting text.

The bridge starts Anthropic SSE responses immediately for streaming
`/v1/messages` requests by sending an early `message_start` event, then sends
periodic `ping` events while waiting for the upstream provider. When OMLX later
emits its own `message_start`, the bridge filters that duplicate event and
continues proxying the real content blocks.

Slow local models can still spend a long time in hidden thinking or prefill
without emitting visible assistant text. Claude Desktop's local-agent watchdog
may ignore SSE `ping`, lifecycle events, and hidden thinking chunks. To keep
slow models usable, the local config enables a visible stream timeout guard:

```json
{
  "streamingProgress": {
    "enabled": true,
    "delayMs": 12000,
    "intervalMs": 30000,
    "providerStatusEnabled": true,
    "providerStatusTimeoutMs": 1200
  }
}
```

Thinking handling is configured separately:

```json
{
  "thinking": {
    "mode": "passthrough-with-progress"
  }
}
```

`passthrough-with-progress` is the default. It passes real upstream Anthropic
`thinking` content blocks and `thinking_delta` events through so Claude can
render the model's thought process when the provider emits it. If the provider
does not produce usable thinking or visible output before `streamingProgress`
fires, the bridge still falls back to the local status block.

Use `passthrough` to show upstream thinking without the extra status fallback,
or `suppress` / `status-only` to hide upstream thinking and keep the older
visible-progress behavior. The bridge does not synthesize private chain of
thought for models that do not emit Anthropic thinking events; it only forwards
what the upstream provider actually streams.

When enabled, the bridge applies this to every Anthropic-compatible streaming
model, not just the known slow aliases. It waits `delayMs` for upstream visible
text or tool output. If none arrives, the request is considered at risk of
Claude's stream idle timeout: the bridge emits the smallest visible heartbeat it
can, then appends occasional one-line italic updates until the real upstream
text/tool output begins.

Example:

```markdown
_Local model: queued, position 1 (12s)._

_Local model: prefill 24.1k / 29.8k tokens (80%), about 1m 58s left (42s)._
```

For OMLX providers, `providerStatusEnabled` lets the bridge fetch
`/admin/api/activity` while waiting. When available, the visible heartbeat stays
minimal and includes only the most useful phase, queue, prefill, or ETA detail;
full model, memory, event-count, and provider diagnostics stay in the bridge log
instead of the Claude transcript. The status fetch is
best-effort and bounded by `providerStatusTimeoutMs`, so it cannot block or fail
the model stream. Repeated updates are deduplicated by provider phase and coarse
progress bucket, so Claude does not render a long wall of near-identical status
lines. This intentionally trades a tiny visible heartbeat for reliable
long-running local inference. Set `CLAUDE_LOCAL_STREAM_PROGRESS=false` or
`"streamingProgress": {"enabled": false}` to disable the visible timeout guard;
set `"providerStatusEnabled": false` to keep the guard but use generic messages.
If the error still appears:

```bash
curl http://127.0.0.1:1245/healthz
tail -f "$HOME/Library/Logs/claude-local-bridge.log"
tail -f "$HOME/.omlx/logs/server.log"
```

Look for bridge entries like `upstream stream failed ... Premature close`,
which usually means the upstream stream closed before Anthropic SSE completed.
The request id suffix includes details such as `lastStatus=prefill:...` or
`lastStatus=activity:...`; pair that with OMLX entries showing model unloads,
request cancellations, or long hidden thinking phases without visible text
deltas. If OMLX reports a model as
unavailable after a cached load failure, remove that model from
`bridge.local.json` or remap its Claude alias to a known-working local model,
then restart the launchd service.

## Files

- `bridge.mjs`: provider-neutral Anthropic-compatible proxy
- `run_claude_with_local_bridge.sh`: Claude Code launcher
- `toggle_claude_local_bridge.sh`: Desktop/Cowork profile toggle
- `refresh_omlx_cowork_models.py`: live OMLX model refresh helper
- `bridge.config.example.json`: tracked bridge runtime config template
- `claude-3p-provider.example.json`: editable provider example
- `launchd/com.borland.claude-local-bridge.plist.template`: LaunchAgent template
## Safety Notes

- Do not commit real API keys, tokens, profile databases, or `.env` files.
- Use placeholder local tokens such as `local-bridge` for localhost auth.
- The bridge API intentionally binds to loopback only. Keep
  `CLAUDE_LOCAL_BRIDGE_HOST` as `127.0.0.1`, `localhost`, or `::1`; the bridge
  refuses wildcard/external bind hosts.
- Back up provider JSON before hand-editing it.
- Restart the exact Claude profile you changed; other profiles have separate
  config and may continue using their old provider state.
