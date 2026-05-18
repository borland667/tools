"""Configuration helpers for the local_llm_mcp package."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import os


def _first_env(names: list[str], default: str) -> str:
    for name in names:
        value = os.environ.get(name)
        if value is not None and value != "":
            return value
    return default


def _bool_env(names: list[str], default: bool) -> bool:
    raw = _first_env(names, "true" if default else "false")
    return raw.lower() not in {"0", "false", "no", "off"}


def _float_env(names: list[str], default: float) -> float:
    raw = _first_env(names, str(default))
    return float(raw)


def _int_env(names: list[str], default: int) -> int:
    raw = _first_env(names, str(default))
    return int(raw)


def _optional_path_env(names: list[str]) -> Path | None:
    raw = _first_env(names, "")
    if raw == "":
        return None
    return Path(os.path.expanduser(raw))


@dataclass(frozen=True)
class LocalLLMConfig:
    base_url: str = "http://localhost:1234/v1"
    model: str = "qwen3.6-35b-a3b-abliterated-heretic-mlx"
    api_key: str = "lmstudio"
    timeout_seconds: float = 180.0
    max_tokens: int = 2048
    disable_thinking: bool = False
    mode_file: Path = field(
        default_factory=lambda: Path.home() / ".claude-local-api-mode.json"
    )
    mode_default: bool = False
    debug_log_file: Path | None = None
    log_prompt_preview: bool = False
    prompt_preview_chars: int = 120

    def __post_init__(self) -> None:
        normalized_mode_file = Path(os.path.expanduser(str(self.mode_file)))
        object.__setattr__(self, "mode_file", normalized_mode_file)
        if self.debug_log_file is not None:
            normalized_debug_log_file = Path(
                os.path.expanduser(str(self.debug_log_file))
            )
            object.__setattr__(self, "debug_log_file", normalized_debug_log_file)

    @classmethod
    def from_env(cls) -> "LocalLLMConfig":
        return cls(
            base_url=_first_env(
                ["LOCAL_LLM_BASE_URL", "LMSTUDIO_BASE_URL"],
                "http://localhost:1234/v1",
            ).rstrip("/"),
            model=_first_env(
                ["LOCAL_LLM_MODEL", "LMSTUDIO_MODEL"],
                "qwen3.6-35b-a3b-abliterated-heretic-mlx",
            ),
            api_key=_first_env(
                ["LOCAL_LLM_API_KEY", "LMSTUDIO_API_KEY"],
                "lmstudio",
            ),
            timeout_seconds=_float_env(
                ["LOCAL_LLM_TIMEOUT_SECONDS", "LMSTUDIO_TIMEOUT_SECONDS"],
                180.0,
            ),
            max_tokens=_int_env(
                ["LOCAL_LLM_MAX_TOKENS", "LMSTUDIO_MAX_TOKENS"],
                2048,
            ),
            disable_thinking=_bool_env(
                ["LOCAL_LLM_DISABLE_THINKING", "LMSTUDIO_DISABLE_THINKING"],
                False,
            ),
            mode_file=Path(
                os.path.expanduser(
                    _first_env(
                        ["LOCAL_LLM_MODE_FILE", "LMSTUDIO_MODE_FILE"],
                        "~/.claude-local-api-mode.json",
                    )
                )
            ),
            mode_default=_bool_env(
                ["LOCAL_LLM_MODE_DEFAULT", "LMSTUDIO_MODE_DEFAULT"],
                False,
            ),
            debug_log_file=_optional_path_env(
                ["LOCAL_LLM_DEBUG_LOG_FILE", "LMSTUDIO_DEBUG_LOG_FILE"]
            ),
            log_prompt_preview=_bool_env(
                ["LOCAL_LLM_LOG_PROMPT_PREVIEW", "LMSTUDIO_LOG_PROMPT_PREVIEW"],
                False,
            ),
            prompt_preview_chars=_int_env(
                [
                    "LOCAL_LLM_PROMPT_PREVIEW_CHARS",
                    "LMSTUDIO_PROMPT_PREVIEW_CHARS",
                ],
                120,
            ),
        )
