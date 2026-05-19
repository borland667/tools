# run_openclaw_local_gateway.sh

## Purpose

Start `OpenClaw` with a localhost-only gateway.

Use this when:

- you want the `OpenClaw` gateway reachable only from the same machine,
- you plan to use Docker for agent sandboxing but do not want the gateway
  exposed on LAN interfaces,
- you want a repeatable launcher that reinforces the safe default in both
  config and the current process.

## Requirements

- `openclaw` installed and available on `PATH`
- a local `OpenClaw` config directory writable by the current user

Optional:

- local `LM Studio` or `Ollama` if you plan to attach a local model provider
- Docker if you plan to enable `OpenClaw`'s agent sandbox

## Quick Start

```bash
cd <repo-root>
scripts/run_openclaw_local_gateway.sh
```

This helper writes:

- `gateway.mode=local`
- `gateway.bind=loopback`
- `gateway.port=<chosen-port>`

Then it starts:

```bash
openclaw gateway run --bind loopback --port <chosen-port>
```

## Common Usage Patterns

### Start on the default local port

```bash
scripts/run_openclaw_local_gateway.sh
```

### Use a different localhost port

```bash
scripts/run_openclaw_local_gateway.sh --port 19001
```

### Inspect what the helper would do

```bash
scripts/run_openclaw_local_gateway.sh --dry-run
```

### Pass through extra gateway flags

```bash
scripts/run_openclaw_local_gateway.sh -- --startup-trace
```

## Arguments and Options

### Required

- No positional arguments are required.

### Optional

- `--port <port>`: override the gateway port. Default: `18789`.
- `--dry-run`: print the `openclaw config set` and `openclaw gateway run`
  commands without executing them.
- `--`: stop parsing helper flags and pass the remaining arguments straight
  to `openclaw gateway run`.
- `-h`, `--help`: show help text.

## Input and Output

Inputs:

- the installed `openclaw` CLI
- an optional override port
- optional extra gateway flags

Outputs:

- an `OpenClaw` gateway process bound to loopback
- updated local `OpenClaw` config values for `gateway.mode`, `gateway.bind`,
  and `gateway.port`

Side effects:

- writes the selected gateway settings into the local `OpenClaw` config
- starts the foreground gateway process

## Internal Behavior Summary

1. Validate that `openclaw` is installed.
2. Persist `gateway.mode=local`.
3. Persist `gateway.bind=loopback`.
4. Persist the chosen `gateway.port`.
5. Start `openclaw gateway run --bind loopback --port ...`.

The helper refuses passthrough `--bind` or `--port` overrides so the current
run cannot accidentally drift away from the localhost-only posture.

## Local Model Notes

The helper does not choose a model provider on its own. Pair it with one of
these local-only patterns:

### `LM Studio`

Start the local server:

```bash
"$HOME/.lmstudio/bin/lms" server start --port 1234
```

Use `OpenClaw`'s `lmstudio` provider against:

```text
http://127.0.0.1:1234/v1
```

Confirm the LM Studio server is still local-only:

```bash
curl -fsS http://127.0.0.1:1234/v1/models
```

### `Ollama`

Start the local daemon:

```bash
ollama serve
```

Use `OpenClaw`'s native `ollama` provider against:

```text
http://127.0.0.1:11434
```

Do not switch Ollama to `/v1` for `OpenClaw`; the native provider expects the
native Ollama API.

Confirm the Ollama daemon is still local-only:

```bash
curl -fsS http://127.0.0.1:11434/api/tags
```

## Docker Sandbox Notes

To keep the gateway local while still sandboxing agents in Docker, run the
gateway on the host and enable `OpenClaw`'s Docker sandbox separately.

Safer default example:

```json5
{
  agents: {
    defaults: {
      sandbox: {
        mode: "all",
        scope: "agent",
        backend: "docker",
        workspaceAccess: "ro"
      }
    }
  }
}
```

Use `workspaceAccess: "rw"` only when you intentionally want the sandboxed
agent to modify files in the host workspace. Bind-mounted workspaces reduce the
strength of the isolation boundary.

If you later containerize the gateway itself, bind the published host port to
loopback too, for example:

```yaml
ports:
  - "127.0.0.1:18789:18789"
```

## Safety Notes

- The helper is intentionally opinionated: it always binds the gateway to
  localhost.
- It does not expose the gateway on LAN or tailnet interfaces.
- Localhost-only binding does not replace Gateway authentication; keep the
  generated Gateway auth token enabled and use authenticated local clients.
- Keep local model backends loopback-only too; do not expose Ollama or LM
  Studio beyond `127.0.0.1` unless you secure them separately.
- It does not weaken auth requirements or bypass `OpenClaw` safety checks.

## Known Limitations

- It does not install `OpenClaw`.
- It does not configure a model provider for you.
- It does not manage Docker sandbox images or service files.

## Validation Checklist

- `scripts/run_openclaw_local_gateway.sh --help` shows the expected options.
- `scripts/run_openclaw_local_gateway.sh --dry-run` prints `gateway.bind loopback`
  and `openclaw gateway run --bind loopback`.
- Verify Gateway auth is still enabled in your local `OpenClaw` setup and that
  connecting clients use the generated auth token.
- `curl -fsS http://127.0.0.1:1234/v1/models` succeeds only when LM Studio is
  intentionally running on loopback.
- `curl -fsS http://127.0.0.1:11434/api/tags` succeeds only when Ollama is
  intentionally running on loopback.
- After launch, the gateway is reachable through `ws://127.0.0.1:<port>`.

## Maintenance Notes

- Update this doc if the helper flags or default port change.
- Keep the repository `README.md` and `scripts/README.md` in sync with the
  helper name and usage.
