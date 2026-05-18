"""Mode-file helpers and CLI for enabling/disabling local API mode."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .config import LocalLLMConfig


def read_mode_state(config: LocalLLMConfig) -> bool:
    try:
        payload = json.loads(config.mode_file.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return config.mode_default
    except Exception:
        return config.mode_default

    if isinstance(payload, dict):
        return bool(payload.get("enabled", config.mode_default))
    return config.mode_default


def write_mode_state(config: LocalLLMConfig, enabled: bool) -> Path:
    config.mode_file.parent.mkdir(parents=True, exist_ok=True)
    payload: dict[str, Any] = {"enabled": enabled}
    config.mode_file.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return config.mode_file


def cli_main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="claude-local-api-mode",
        description="Enable, disable, or inspect local API mode for the local_llm_mcp bridge.",
    )
    parser.add_argument("command", choices=["enable", "disable", "status"])
    args = parser.parse_args(argv)

    config = LocalLLMConfig.from_env()

    if args.command == "status":
        enabled = read_mode_state(config)
        print(f"Local API mode is {'enabled' if enabled else 'disabled'}.")
        print(f"Mode file: {config.mode_file}")
        return 0

    if args.command == "enable":
        write_mode_state(config, True)
        print("Local API mode enabled.")
        print("Restart Claude Desktop to load the local tools.")
        return 0

    write_mode_state(config, False)
    print("Local API mode disabled.")
    print("Restart Claude Desktop to hide the local tools and use normal Claude only.")
    return 0
