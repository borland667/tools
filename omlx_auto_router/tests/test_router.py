from __future__ import annotations

import json

import pytest
from fastapi import HTTPException

import omlx_auto_router as router


def test_auto_mode_aliases() -> None:
    assert router.auto_mode("auto") == "chat"
    assert router.auto_mode("auto-chat") == "chat"
    assert router.auto_mode("auto-agent") == "agent"
    assert router.auto_mode("Qwen3.5-9b-Sushi-Coder-RL-MLX") is None


def test_parse_json_object_plain_json() -> None:
    result = router.parse_json_object(
        '{"route":"coding","confidence":0.9,"reason":"code"}'
    )
    assert result["route"] == "coding"


def test_parse_json_object_markdown_fence() -> None:
    result = router.parse_json_object(
        '```json\n{"route":"summary","confidence":0.8,"reason":"short"}\n```'
    )
    assert result["route"] == "summary"


def test_validate_tool_history_normalizes_dict_arguments() -> None:
    messages = [
        {
            "role": "assistant",
            "tool_calls": [
                {
                    "type": "function",
                    "function": {
                        "name": "example",
                        "arguments": {"filepath": "/tmp/test.md"},
                    },
                }
            ],
        }
    ]

    router.validate_tool_history(messages)

    arguments = messages[0]["tool_calls"][0]["function"]["arguments"]
    assert json.loads(arguments) == {"filepath": "/tmp/test.md"}


def test_validate_tool_history_rejects_malformed_json() -> None:
    messages = [
        {
            "role": "assistant",
            "tool_calls": [
                {
                    "type": "function",
                    "function": {
                        "name": "create_new_file",
                        "arguments": '{"filepath":"/tmp/test.md","contents":}',
                    },
                }
            ],
        }
    ]

    with pytest.raises(HTTPException) as exc_info:
        router.validate_tool_history(messages)

    assert exc_info.value.status_code == 422


def test_heuristic_debugging() -> None:
    decision = router.heuristic(
        {
            "messages": [
                {
                    "role": "user",
                    "content": "Investigate a PostgreSQL timeout and find the root cause.",
                }
            ]
        }
    )

    assert decision.route == "debugging"
    assert decision.model == router.MODELS["reasoner"]


def test_heuristic_architecture() -> None:
    decision = router.heuristic(
        {
            "messages": [
                {
                    "role": "user",
                    "content": "Design a migration plan and compare architecture tradeoffs.",
                }
            ]
        }
    )

    assert decision.route == "architecture"


@pytest.mark.asyncio
async def test_choose_model_pins_agent_to_coder() -> None:
    decision = await router.choose_model(
        {
            "messages": [
                {
                    "role": "user",
                    "content": "Find and fix the authentication issue.",
                }
            ]
        },
        "agent",
    )

    assert decision.route == "coding"
    assert decision.model == router.MODELS["coder"]
    assert decision.source == "hard_rule"
