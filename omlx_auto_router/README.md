# oMLX Auto Router

An OpenAI-compatible proxy that adds intelligent local model routing in front of an [oMLX](https://github.com/jundot/omlx) server.

It exposes three model aliases:

- `auto` — equivalent to `auto-chat`
- `auto-chat` — classifies each normal chat request and selects a suitable local model
- `auto-agent` — pins Agent and tool-bearing requests to the most reliable coding model

It also proxies local embeddings and reranking.

## Project status

This is a small local-first development service. It is designed for one developer workstation and binds to `127.0.0.1` by default.

## Python version and pyenv behavior

Use **Python 3.13.14** for the recommended local environment. The package declares compatibility with Python `>=3.10,<3.15`, while the included `.python-version` pins the tested development version.

The project explicitly honors `.python-version` whenever `pyenv` is installed:

- `scripts/resolve_python.sh` runs Python through `pyenv exec python`.
- This works even when pyenv shell shims have not been initialized.
- `scripts/create_venv.sh` compares the selected Python version with the interpreter inside `.venv`.
- If `.venv` was created with a different Python version, it is automatically recreated.
- `PYTHON_BIN=/absolute/path/to/python` can be used as an explicit override.
- When pyenv is unavailable, the resolver falls back to `python3.13`, `python3`, and then `python`.

Check the interpreter selected for the project:

```bash
make python-version
```

Create or validate the environment:

```bash
make venv
```

## Architecture

```text
Continue / OpenAI-compatible client
                 |
                 v
      http://127.0.0.1:8010/v1
          oMLX Auto Router
                 |
          +------+------+
          | classifier  |
          | heuristics   |
          | agent rules  |
          +------+------+
                 |
                 v
      http://127.0.0.1:8005/v1
                 oMLX
```

The router does not load models directly. It selects a model and forwards the original request to oMLX.

## Features

- OpenAI-compatible `/v1/chat/completions`
- Streaming passthrough
- Fast local prompt classifier
- Confidence threshold and deterministic fallback
- Conservative `auto-agent` routing
- `/v1/embeddings` proxy
- `/v1/rerank` proxy
- `/v1/models` passthrough with aliases injected
- Routing metadata for non-streaming requests
- Routing headers for streaming requests
- Tool-call history validation
- In-memory classifier cache
- Environment-based model overrides
- Continue configuration example
- Docker and Docker Compose support
- macOS `launchd` service template
- Unit tests and lint/type-check configuration

## Default routing

| Route | Default model | Use |
|---|---|---|
| `coding` | `Qwen3.5-9b-Sushi-Coder-RL-MLX` | Implementation, refactoring, tests, APIs, SQL and infrastructure code |
| `debugging` | `Qwen3-Next-80B-A3B-Thinking-4bit` | Incidents, performance, timeouts, root-cause analysis |
| `architecture` | `Qwen3-Next-80B-A3B-Thinking-4bit` | System design, migrations and tradeoffs |
| `deep_review` | `Qwen3.6-35B-A3B-Claude-Opus-VL-grafted-MLX-8bit` | Design, code, security and operational review |
| `summary` | `gemma-4-e4b-it-4bit` | Short explanations and summaries |
| `general` | `Qwen3.5-9b-Sushi-Coder-RL-MLX` | Default fallback |
| `vision` | `Qwen3-VL-4B-Instruct-4bit` | Screenshots, diagrams, images and UI analysis |
| `visual_quality` | `VisualQuality-R1-7B-4bit` | Blur, sharpness, artifacts and image quality |

Agent requests and requests containing a `tools` array are pinned to `Qwen3.5-9b-Sushi-Coder-RL-MLX`.

Auto embedding requests use `Qwen3-Embedding-0.6B-4bit-DWQ`.

Auto reranking requests use `Qwen3-Reranker-0.6B-4bit`.

## Project structure

```text
.
├── .dockerignore
├── .env.example
├── .gitignore
├── .python-version
├── Dockerfile
├── Makefile
├── README.md
├── compose.yaml
├── continue.config.example.yaml
├── launchd/
│   └── com.omlx.auto-router.plist.template
├── omlx_auto_router.py
├── pyproject.toml
├── requirements-dev.txt
├── requirements.txt
├── scripts/
│   ├── create_venv.sh
│   ├── install_launchd.sh
│   ├── resolve_python.sh
│   ├── run.sh
│   ├── smoke_test.sh
│   └── uninstall_launchd.sh
└── tests/
    └── test_router.py
```

## Prerequisites

- macOS or Linux
- Python 3.13.14 recommended
- A running oMLX API at `http://127.0.0.1:8005/v1`
- `curl` and `jq` for smoke tests
- The configured models available in oMLX

Verify oMLX:

```bash
curl -qs http://127.0.0.1:8005/v1/models \
  | jq '.data[] | {id, max_model_len}'
```

## Quick start

### With `pyenv`

```bash
pyenv install 3.13.14

# The repository already contains .python-version.
# This command is optional unless you want to rewrite or confirm it.
pyenv local 3.13.14

make python-version
make install
cp .env.example .env
make run
```

`make install` uses `pyenv exec python` when both pyenv and `.python-version` are available. It also recreates `.venv` when its interpreter does not match the selected pyenv version.

### With `uv`

```bash
uv python install 3.13.14
uv venv --python 3.13.14
source .venv/bin/activate

uv pip install -r requirements.txt
cp .env.example .env
python omlx_auto_router.py
```

### Plain Python

```bash
python3.13 -m venv .venv
source .venv/bin/activate

python -m pip install --upgrade pip
pip install -r requirements.txt

cp .env.example .env
./scripts/run.sh
```

The router starts at:

```text
http://127.0.0.1:8010
```

## Health check

```bash
curl -qs http://127.0.0.1:8010/health | jq .
```

## API examples

### Models

```bash
curl -qs http://127.0.0.1:8010/v1/models | jq '.data[].id'
```

Expected aliases:

```text
auto
auto-chat
auto-agent
```

### Auto Chat

```bash
curl -qs http://127.0.0.1:8010/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer sk-local" \
  -d '{
    "model": "auto-chat",
    "messages": [
      {
        "role": "user",
        "content": "Investigate intermittent PostgreSQL query timeouts and build a hypothesis tree."
      }
    ],
    "max_tokens": 512,
    "temperature": 0.1
  }' | jq '{
    model,
    auto_router,
    content: .choices[0].message.content
  }'
```

### Auto Agent

```bash
curl -qs http://127.0.0.1:8010/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer sk-local" \
  -d '{
    "model": "auto-agent",
    "messages": [
      {
        "role": "user",
        "content": "Find where authentication is implemented. Do not edit files."
      }
    ],
    "max_tokens": 512
  }' | jq '.auto_router'
```

### Streaming

```bash
curl -N http://127.0.0.1:8010/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer sk-local" \
  -d '{
    "model": "auto-chat",
    "stream": true,
    "messages": [
      {
        "role": "user",
        "content": "Explain this Django query optimization briefly."
      }
    ]
  }'
```

Streaming responses include:

```text
X-Auto-Router-Model
X-Auto-Router-Route
X-Auto-Router-Source
```

### Embeddings

```bash
curl -qs http://127.0.0.1:8010/v1/embeddings \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer sk-local" \
  -d '{
    "model": "auto",
    "input": "authentication login token validation"
  }' | jq '{
    model,
    dimensions: (.data[0].embedding | length),
    usage
  }'
```

### Reranking

```bash
curl -qs http://127.0.0.1:8010/v1/rerank \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer sk-local" \
  -d '{
    "model": "auto",
    "query": "Where is authentication implemented?",
    "documents": [
      "auth/login.py handles user login and token validation",
      "billing/invoices.py creates monthly invoices",
      "README.md contains setup instructions"
    ]
  }' | jq .
```

## Continue setup

Copy the example or merge its model blocks into your existing Continue config:

```bash
cp continue.config.example.yaml ~/.continue/config.yaml
```

The example keeps these local and direct to oMLX:

- autocomplete
- embeddings
- reranking

Only `auto-chat` and `auto-agent` pass through the router.

## Configuration

Copy the template:

```bash
cp .env.example .env
```

The run script automatically loads `.env`.

### Core settings

| Variable | Default |
|---|---|
| `OMLX_BASE_URL` | `http://127.0.0.1:8005/v1` |
| `OMLX_API_KEY` | `sk-local` |
| `ROUTER_HOST` | `127.0.0.1` |
| `ROUTER_PORT` | `8010` |
| `LOG_LEVEL` | `INFO` |

### Classifier settings

| Variable | Default |
|---|---|
| `CLASSIFIER_MODEL` | `gemma-4-e4b-it-4bit` |
| `CLASSIFIER_TIMEOUT` | `10` |
| `CLASSIFIER_THRESHOLD` | `0.65` |
| `CLASSIFIER_MAX_CHARS` | `12000` |
| `CLASSIFIER_CACHE_TTL` | `300` |
| `ALLOW_HEAVY_MODELS` | `true` |

Set `ALLOW_HEAVY_MODELS=false` to route architecture requests to the smaller reasoner and deep-review requests to the coder.

All model assignments can be overridden through the `MODEL_*` variables in `.env.example`.

## Development

Install development dependencies:

```bash
make install-dev
```

Run tests:

```bash
make test
```

Run linting:

```bash
make lint
```

Format:

```bash
make format
```

Run mypy:

```bash
make typecheck
```

Run the full local check:

```bash
make check
```

Run API smoke tests while the service is running:

```bash
make smoke
```

## Docker

On macOS, Docker can reach the host oMLX process through `host.docker.internal`.

```bash
docker compose up --build
```

The router remains exposed only on:

```text
127.0.0.1:8010
```

Stop it with:

```bash
docker compose down
```

## Run automatically on macOS

Install dependencies first:

```bash
make install
```

Install the per-user launch agent:

```bash
./scripts/install_launchd.sh
```

Inspect logs:

```bash
tail -f ~/Library/Logs/omlx-auto-router.log
tail -f ~/Library/Logs/omlx-auto-router.error.log
```

Remove it:

```bash
./scripts/uninstall_launchd.sh
```

## Tool-call validation

The router validates existing OpenAI-style assistant tool calls before forwarding a conversation.

Malformed arguments such as:

```json
{"filepath":"/tmp/example.md","contents":}
```

are rejected with HTTP `422`.

Arguments must be a JSON-encoded object string:

```json
"{\"filepath\":\"/tmp/example.md\",\"contents\":\"# Example\\n\"}"
```

A thread that already contains malformed tool-call history should normally be replaced with a new chat.

## Routing metadata

Non-streaming responses contain:

```json
{
  "auto_router": {
    "requested_model": "auto-chat",
    "classifier_model": "gemma-4-e4b-it-4bit",
    "route": "debugging",
    "model": "Qwen3-Next-80B-A3B-Thinking-4bit",
    "confidence": 0.94,
    "reason": "The request asks for root-cause analysis.",
    "source": "classifier"
  }
}
```

Possible sources:

| Source | Meaning |
|---|---|
| `hard_rule` | Agent mode or tools pinned the request to the coder |
| `classifier` | The fast local classifier selected the route |
| `cache` | A cached classifier result was reused |
| `heuristic` | A deterministic image or keyword rule was used |
| `heuristic_fallback` | Classification failed or confidence was too low |

### `.python-version` is not being resolved

Check the selected interpreter:

```bash
./scripts/resolve_python.sh --version
```

When pyenv is installed but the requested version is missing:

```bash
pyenv install "$(head -n 1 .python-version)"
make venv
```

An existing virtual environment created with the wrong patch version is automatically recreated by:

```bash
make venv
```

To bypass pyenv intentionally:

```bash
PYTHON_BIN=/absolute/path/to/python3.13 make venv
```

## Security

- The service binds to `127.0.0.1` by default.
- Do not bind it to `0.0.0.0` without adding authentication and network controls.
- Do not commit `.env`.
- Treat model-generated commands and tool calls as untrusted.
- Keep IDE approval controls enabled for commands and workspace mutations.
- The router forwards its configured oMLX API key upstream; it does not currently authenticate incoming clients independently.

## Limitations

- Classification adds one extra local inference for uncached Auto Chat requests.
- Agent requests remain pinned to one coding model.
- The cache is process-local and resets on restart.
- Streaming bodies are passed through unchanged; routing metadata is in headers.
- There is no persistent routing history, metrics endpoint, rate limiting or client-auth middleware.
- Vision routing depends on the multimodal request format supported by the oMLX model.
