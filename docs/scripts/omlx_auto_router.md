# oMLX Auto Router

## Purpose

`omlx_auto_router/` is a local OpenAI-compatible proxy in front of an OMLX
server. It exposes stable aliases such as `auto`, `auto-chat`, and
`auto-agent`, then routes each request to a suitable local OMLX model.

The project README is the primary operator guide:

```text
/Users/borland/tools/omlx_auto_router/README.md
```

## Requirements

- Python 3.13.14 is the recommended development interpreter.
- OMLX should be running on `http://127.0.0.1:8005/v1`.
- Runtime dependencies are in `requirements.txt`.
- Development dependencies are in `requirements-dev.txt`.

## Usage

Create the environment and run locally:

```bash
cd /Users/borland/tools/omlx_auto_router
make install
make run
```

Run tests:

```bash
cd /Users/borland/tools/omlx_auto_router
make test
```

Run the full project check after installing development dependencies:

```bash
cd /Users/borland/tools/omlx_auto_router
make install-dev
make check
```

## Output

The router listens on `http://127.0.0.1:8010` by default and exposes:

- `/health`
- `/v1/models`
- `/v1/chat/completions`
- `/v1/embeddings`
- `/v1/rerank`

## Safety Notes

The service is intended for a single local workstation and binds to loopback by
default. Keep it behind `127.0.0.1` unless you deliberately harden auth and
network exposure.

## Known Limitations

- The router does not load models itself; all target models must already exist
  in OMLX.
- Classifier quality depends on the configured classifier model.
- Streaming responses can only expose routing metadata through headers.
