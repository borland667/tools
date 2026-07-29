# claude_local_bridge

## Purpose

Generic local API bridge for Claude Code and Claude Desktop/Cowork 3P profiles.
It proxies Anthropic-compatible `/v1/*` requests to local backends such as OMLX
or LM Studio, exposes Claude-safe model discovery, and supports profile-aware
Desktop/Cowork provider configuration.

Use this when:

- You want Claude Desktop/Cowork 3P mode to use a local `gateway` provider.
- You want Claude Code to run against a local Anthropic-compatible endpoint.
- You want one bridge that can switch between `omlx` and `lmstudio`.
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

- `CLAUDE_LOCAL_INFERENCE_BACKEND`: `omlx` or `lmstudio`.
- `CLAUDE_LOCAL_INFERENCE_BASE_URL`: generic upstream URL override.
- `OMLX_BASE_URL`: OMLX upstream URL.
- `LMSTUDIO_BASE_URL`: LM Studio upstream URL.
- `CLAUDE_LOCAL_INFERENCE_AUTH_SCHEME`: `auto`, `none`, `bearer`,
  `x-api-key`, or `both`.
- `CLAUDE_LOCAL_BRIDGE_HOST`: bridge host, default `127.0.0.1`.
- `CLAUDE_LOCAL_BRIDGE_PORT`: bridge port, default `1245`.
- `CLAUDE_LOCAL_MAIN_MODEL`: default local model.
- `CLAUDE_LOCAL_SMALL_MODEL`: Haiku/helper model.
- `CLAUDE_LOCAL_TOOL_MODEL`: tool-heavy request model.
- `CLAUDE_LOCAL_MODEL_MAP`: JSON route-to-upstream model map.
- `CLAUDE_PROFILE_NAME`: profile under `~/.claude-instances`.
- `CLAUDE_PROFILE_DIR`: explicit profile user-data directory.

Backend-specific `LMSTUDIO_*` and `OMLX_*` names are accepted for upstream
selection; bridge-specific settings use `CLAUDE_LOCAL_*`.

## Safety Notes

- Use placeholder local tokens such as `local-bridge`; do not commit real
  credentials.
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
```

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
