import json
from pathlib import Path

from local_llm_mcp.config import LocalLLMConfig
from local_llm_mcp.mode import read_mode_state, write_mode_state
from local_llm_mcp.server import ask_local_llm, build_instructions, handle_request


def test_direct_config_expands_default_mode_file() -> None:
    config = LocalLLMConfig()
    assert config.mode_file == Path.home() / ".claude-local-api-mode.json"


def test_direct_config_expands_tilde_mode_file() -> None:
    config = LocalLLMConfig(mode_file=Path("~/.claude-local-api-mode-test.json"))
    assert config.mode_file == Path.home() / ".claude-local-api-mode-test.json"


def test_mode_defaults_when_file_missing(tmp_path: Path) -> None:
    config = LocalLLMConfig(mode_file=tmp_path / "missing.json", mode_default=False)
    assert read_mode_state(config) is False


def test_mode_write_and_read(tmp_path: Path) -> None:
    config = LocalLLMConfig(mode_file=tmp_path / "mode.json", mode_default=False)
    write_mode_state(config, True)
    assert read_mode_state(config) is True
    write_mode_state(config, False)
    assert read_mode_state(config) is False


def test_tools_hidden_when_mode_disabled(tmp_path: Path) -> None:
    config = LocalLLMConfig(mode_file=tmp_path / "mode.json", mode_default=False)
    response = handle_request(
        config,
        {"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
    )
    assert response == {"jsonrpc": "2.0", "id": 1, "result": {"tools": []}}


def test_tools_visible_when_mode_enabled(tmp_path: Path) -> None:
    config = LocalLLMConfig(mode_file=tmp_path / "mode.json", mode_default=False)
    write_mode_state(config, True)
    response = handle_request(
        config,
        {"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
    )
    tools = response["result"]["tools"]
    names = {tool["name"] for tool in tools}
    assert names == {
        "ask_local_llm",
        "list_local_llm_models",
        "local_api_mode_status",
    }


def test_initialize_instructions_push_local_delegation_when_enabled(tmp_path: Path) -> None:
    config = LocalLLMConfig(mode_file=tmp_path / "mode.json", mode_default=False)
    write_mode_state(config, True)
    response = handle_request(
        config,
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {"protocolVersion": "2025-06-18"},
        },
    )
    instructions = response["result"]["instructions"]
    assert "primary response engine" in instructions
    assert "ask_local_llm" in instructions


def test_disabled_instructions_make_normal_claude_behavior_clear(tmp_path: Path) -> None:
    config = LocalLLMConfig(mode_file=tmp_path / "missing.json", mode_default=False)
    instructions = build_instructions(config, local_mode_enabled=False)
    assert "normal hosted Claude experience" in instructions
    assert "disabled" in instructions


def test_ask_local_llm_writes_debug_log_entries(
    tmp_path: Path,
    monkeypatch,
) -> None:
    log_file = tmp_path / "local-llm-debug.jsonl"
    config = LocalLLMConfig(
        mode_file=tmp_path / "mode.json",
        debug_log_file=log_file,
        log_prompt_preview=True,
        prompt_preview_chars=12,
    )

    def fake_http_request(
        _config: LocalLLMConfig,
        method: str,
        path: str,
        payload: dict[str, object] | None = None,
    ) -> dict[str, object]:
        assert method == "POST"
        assert path == "/chat/completions"
        assert payload is not None
        return {
            "model": "debug-qwen",
            "choices": [
                {
                    "message": {"content": "Local answer"},
                    "finish_reason": "stop",
                }
            ],
            "usage": {"prompt_tokens": 10, "completion_tokens": 4},
        }

    monkeypatch.setattr("local_llm_mcp.server.http_request", fake_http_request)

    result = ask_local_llm(config, {"prompt": "Hello from Claude Desktop"})

    assert result["isError"] is False
    events = [json.loads(line) for line in log_file.read_text(encoding="utf-8").splitlines()]
    assert [event["event"] for event in events] == [
        "ask_local_llm.start",
        "ask_local_llm.success",
    ]
    assert events[0]["prompt_preview"] == "Hello fro..."
    assert events[1]["response_model"] == "debug-qwen"
    assert events[1]["answer_chars"] == len("Local answer")


def test_initialize_writes_debug_log_when_configured(tmp_path: Path) -> None:
    log_file = tmp_path / "local-llm-debug.jsonl"
    config = LocalLLMConfig(
        mode_file=tmp_path / "mode.json",
        mode_default=False,
        debug_log_file=log_file,
    )
    write_mode_state(config, True)

    handle_request(
        config,
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {"protocolVersion": "2025-06-18"},
        },
    )

    events = [json.loads(line) for line in log_file.read_text(encoding="utf-8").splitlines()]
    assert len(events) == 1
    assert events[0]["event"] == "mcp.initialize"
    assert events[0]["local_mode_enabled"] is True
