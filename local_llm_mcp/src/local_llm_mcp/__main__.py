"""CLI entrypoint for the local_llm_mcp MCP server."""

from __future__ import annotations

import argparse

from . import __version__
from .server import main as serve_stdio


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="local-llm-mcp",
        description=(
            "Start the stdio MCP server that optionally exposes local "
            "OpenAI-compatible LLM tools to Claude Desktop."
        ),
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    parser.parse_args(argv)
    return serve_stdio()


if __name__ == "__main__":
    raise SystemExit(main())
