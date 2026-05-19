# Scripts Helpers

Helper scripts for repository maintenance and automation.

## `install-to-bin.sh`

Install one or more repository scripts into `$HOME/bin` so they are runnable from
`$PATH`.

By default, installation uses symlinks (recommended), so updates in this repo
are reflected immediately.

### Usage

```bash
scripts/install-to-bin.sh [options] <script-path> [<script-path> ...]
scripts/install-to-bin.sh [options] --all
```

### Options

- `--all`: install all top-level executable scripts from repo root
- `--copy`: copy files to `$HOME/bin` instead of symlinking
- `--force`: replace existing file/link in `$HOME/bin`
- `--dry-run`: print actions without changing files
- `-h`, `--help`: show help

### Examples

Install one script:

```bash
scripts/install-to-bin.sh media_carver.py
```

Same pattern for [`media_classifier.py`](../media_classifier.py) (companion to `media_carver.py`).

Install all top-level executable scripts:

```bash
scripts/install-to-bin.sh --all
```

Preview only:

```bash
scripts/install-to-bin.sh --all --dry-run
```

### PATH setup

If `$HOME/bin` is not already in your Bash PATH, add this to `$HOME/.bashrc`:

```bash
export PATH="$HOME/bin:$PATH"
```

Then reload your shell and verify:

```bash
source "$HOME/.bashrc"
which media_carver.py
```

## `run_openhands_with_lmstudio.sh`

Launch `OpenHands` against LM Studio's local OpenAI-compatible server with
the required `LLM_*` environment variables already set.

The helper:

- checks that `openhands` is installed,
- verifies that the LM Studio `/v1/models` endpoint is reachable,
- defaults to `openai/qwen/qwen3-coder-30b`,
- passes through the rest of your `openhands` arguments unchanged.

### Usage

```bash
scripts/run_openhands_with_lmstudio.sh [options] [-- <openhands-args...>]
```

### Options

- `--model <id>`: override the OpenHands model id
- `--base-url <url>`: override the LM Studio base URL
- `--api-key <key>`: override the API key sent to LM Studio
- `--start-lmstudio`: try `lms server start` if the API is not already up
- `-h`, `--help`: show help

### Examples

Open the normal OpenHands CLI:

```bash
scripts/run_openhands_with_lmstudio.sh
```

Start with an initial task:

```bash
scripts/run_openhands_with_lmstudio.sh -- --task "Summarize this repo"
```

Headless mode:

```bash
scripts/run_openhands_with_lmstudio.sh -- --headless --task "Reply with hello"
```

## `run_openclaw_local_gateway.sh`

Start the `OpenClaw` gateway in localhost-only mode.

The helper:

- sets `gateway.mode` to `local`,
- sets `gateway.bind` to `loopback`,
- sets the configured gateway port,
- runs `openclaw gateway run --bind loopback ...`,
- refuses passthrough `--bind` and `--port` overrides that would weaken the
  local-only posture.

### Usage

```bash
scripts/run_openclaw_local_gateway.sh [options] [-- <openclaw-gateway-args...>]
```

### Options

- `--port <port>`: override the gateway port
- `--dry-run`: print the commands without executing them
- `-h`, `--help`: show help

### Examples

Start the normal localhost-only gateway:

```bash
scripts/run_openclaw_local_gateway.sh
```

Use a different loopback port:

```bash
scripts/run_openclaw_local_gateway.sh --port 19001
```

Preview the exact `openclaw` commands:

```bash
scripts/run_openclaw_local_gateway.sh --dry-run
```
