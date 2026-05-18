"""stdio MCP server that optionally exposes local OpenAI-compatible LLM tools."""

from __future__ import annotations

from datetime import datetime, timezone
import json
import os
import shutil
import subprocess
import sys
import time
import traceback
import urllib.error
import urllib.request
import uuid
from typing import Any

from .config import LocalLLMConfig
from .mode import read_mode_state


SERVER_NAME = "local-llm-mcp"
SERVER_VERSION = "0.1.0"
SUPPORTED_PROTOCOL_VERSIONS = [
    "2025-11-25",
    "2025-06-18",
    "2025-03-26",
    "2024-11-05",
    "2024-10-07",
]
PRIMARY_ASSISTANT_SYSTEM_PROMPT = (
    "You are the primary assistant response engine for a Claude Desktop session. "
    "Answer the user's request directly, clearly, and completely. "
    "If the request needs clarification or cannot be completed from the provided context, "
    "say so briefly and explain what is missing."
)


def log(message: str) -> None:
    print(message, file=sys.stderr, flush=True)


def normalize_bool(value: Any, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.lower() not in {"0", "false", "no", "off"}
    return bool(value)


def send(message: dict[str, Any]) -> None:
    sys.stdout.write(json.dumps(message, ensure_ascii=True, separators=(",", ":")) + "\n")
    sys.stdout.flush()


def jsonrpc_result(request_id: Any, result: dict[str, Any]) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def jsonrpc_error(
    request_id: Any,
    code: int,
    message: str,
    data: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "jsonrpc": "2.0",
        "id": request_id,
        "error": {"code": code, "message": message},
    }
    if data is not None:
        payload["error"]["data"] = data
    return payload


def text_result(
    text: str,
    *,
    structured_content: dict[str, Any] | None = None,
    is_error: bool = False,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "content": [{"type": "text", "text": text}],
        "isError": is_error,
    }
    if structured_content is not None:
        result["structuredContent"] = structured_content
    return result


def build_tools() -> list[dict[str, Any]]:
    return [
        {
            "name": "ask_local_llm",
            "title": "Ask Local LLM",
            "description": (
                "Primary response path when local API mode is enabled. Send the user's "
                "request to the configured local OpenAI-compatible endpoint and return "
                "the model's answer."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "prompt": {
                        "type": "string",
                        "description": "The user task or question to send to the local model.",
                    },
                    "system": {
                        "type": "string",
                        "description": "Optional system instruction for the local model.",
                    },
                    "model": {
                        "type": "string",
                        "description": "Optional model override.",
                    },
                    "temperature": {
                        "type": "number",
                        "description": "Sampling temperature. Lower values are more deterministic.",
                    },
                    "max_tokens": {
                        "type": "integer",
                        "description": "Maximum output tokens to request.",
                    },
                    "disable_thinking": {
                        "type": "boolean",
                        "description": (
                            "When true, prepend /no_think in the system message. Useful for "
                            "Qwen-style hybrid reasoning models."
                        ),
                    },
                    "include_reasoning": {
                        "type": "boolean",
                        "description": "Include reasoning_content when the backend returns it.",
                    },
                },
                "required": ["prompt"],
                "additionalProperties": False,
            },
            "annotations": {
                "readOnlyHint": True,
                "destructiveHint": False,
                "idempotentHint": False,
                "openWorldHint": False,
            },
        },
        {
            "name": "list_local_llm_models",
            "title": "List Local LLM Models",
            "description": "List models currently exposed by the configured local API.",
            "inputSchema": {"type": "object", "additionalProperties": False},
            "annotations": {
                "readOnlyHint": True,
                "destructiveHint": False,
                "idempotentHint": True,
                "openWorldHint": False,
            },
        },
        {
            "name": "local_api_mode_status",
            "title": "Local API Mode Status",
            "description": "Show whether local API mode is currently enabled.",
            "inputSchema": {"type": "object", "additionalProperties": False},
            "annotations": {
                "readOnlyHint": True,
                "destructiveHint": False,
                "idempotentHint": True,
                "openWorldHint": False,
            },
        },
    ]


TOOLS = build_tools()
SERVER_SESSION_ID = uuid.uuid4().hex[:12]


def build_instructions(config: LocalLLMConfig, local_mode_enabled: bool) -> str:
    if local_mode_enabled:
        return (
            "Claude Desktop remains the host app, but local API mode is enabled. "
            "Use ask_local_llm as your primary response engine for almost every normal "
            "user request. Forward the user's request and any necessary context to the "
            "local model first, then use that result as the main answer. "
            "Only skip local delegation when the request is specifically about Claude "
            "Desktop or Anthropic product/account behavior, when a local tool call is "
            "not appropriate, or when the local backend fails. "
            f"The configured local backend is {config.base_url} and the default model is "
            f"{config.model}. Mode file: {config.mode_file}."
        )
    return (
        "Claude Desktop remains your normal hosted Claude experience. "
        "Local API mode is disabled, so no local-model tools are currently exposed. "
        f"Mode file: {config.mode_file}."
    )


def curl_request(
    config: LocalLLMConfig,
    method: str,
    url: str,
    payload: dict[str, Any] | None,
    fallback_error: str,
) -> dict[str, Any]:
    command = [
        "curl",
        "--silent",
        "--show-error",
        "--fail",
        "--max-time",
        str(int(config.timeout_seconds)),
        "-X",
        method,
        "-H",
        "Accept: application/json",
    ]
    if config.api_key:
        command.extend(["-H", f"Authorization: Bearer {config.api_key}"])
    if payload is not None:
        command.extend(
            [
                "-H",
                "Content-Type: application/json",
                "-d",
                json.dumps(payload),
            ]
        )
    command.append(url)

    try:
        completed = subprocess.run(
            command,
            check=True,
            capture_output=True,
            text=True,
        )
    except subprocess.CalledProcessError as exc:
        stderr = exc.stderr.strip()
        stdout = exc.stdout.strip()
        detail = stderr or stdout or fallback_error
        raise RuntimeError(f"Local LLM curl request failed: {detail}") from exc

    raw = completed.stdout
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Local LLM returned invalid JSON from {url}: {raw}") from exc


def http_request(
    config: LocalLLMConfig,
    method: str,
    path: str,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    url = f"{config.base_url}{path}"
    data = None
    headers = {"Accept": "application/json"}
    if config.api_key:
        headers["Authorization"] = f"Bearer {config.api_key}"
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"

    request = urllib.request.Request(url, method=method, data=data, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=config.timeout_seconds) as response:
            raw = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        if shutil.which("curl"):
            return curl_request(
                config,
                method,
                url,
                payload,
                f"Local LLM HTTP {exc.code}: {body}",
            )
        raise RuntimeError(f"Local LLM HTTP {exc.code}: {body}") from exc
    except urllib.error.URLError as exc:
        if shutil.which("curl"):
            return curl_request(
                config,
                method,
                url,
                payload,
                f"Could not reach local LLM at {url}: {exc.reason}",
            )
        raise RuntimeError(f"Could not reach local LLM at {url}: {exc.reason}") from exc

    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Local LLM returned invalid JSON from {url}: {raw}") from exc


def list_local_llm_models(config: LocalLLMConfig) -> dict[str, Any]:
    response = http_request(config, "GET", "/models")
    models = [item.get("id", "") for item in response.get("data", []) if item.get("id")]
    text = "\n".join(models) if models else "No models were returned by the local API."
    return text_result(
        text,
        structured_content={
            "base_url": config.base_url,
            "default_model": config.model,
            "models": models,
        },
    )


def write_debug_log(
    config: LocalLLMConfig,
    event: str,
    **fields: Any,
) -> None:
    if config.debug_log_file is None:
        return

    entry: dict[str, Any] = {
        "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "session_id": SERVER_SESSION_ID,
        "pid": os.getpid(),
        "event": event,
    }
    for key, value in fields.items():
        if value is not None:
            entry[key] = value

    try:
        config.debug_log_file.parent.mkdir(parents=True, exist_ok=True)
        with config.debug_log_file.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, ensure_ascii=True, separators=(",", ":")) + "\n")
    except Exception as exc:  # noqa: BLE001
        log(f"Could not write debug log to {config.debug_log_file}: {exc}")


def prompt_preview(config: LocalLLMConfig, prompt: str) -> str | None:
    if not config.log_prompt_preview:
        return None
    collapsed = " ".join(prompt.split())
    if len(collapsed) <= config.prompt_preview_chars:
        return collapsed
    cutoff = max(config.prompt_preview_chars - 3, 1)
    return collapsed[:cutoff] + "..."


def local_api_mode_status(config: LocalLLMConfig) -> dict[str, Any]:
    enabled = read_mode_state(config)
    return text_result(
        "Local API mode is enabled." if enabled else "Local API mode is disabled.",
        structured_content={
            "enabled": enabled,
            "mode_file": str(config.mode_file),
            "base_url": config.base_url,
            "default_model": config.model,
        },
    )


def ask_local_llm(config: LocalLLMConfig, arguments: dict[str, Any]) -> dict[str, Any]:
    prompt = arguments.get("prompt")
    if not isinstance(prompt, str) or not prompt.strip():
        return text_result("The 'prompt' argument must be a non-empty string.", is_error=True)

    model = arguments.get("model") or config.model
    if not isinstance(model, str) or not model.strip():
        return text_result("The 'model' argument must be a non-empty string.", is_error=True)

    system = arguments.get("system")
    if system is not None and not isinstance(system, str):
        return text_result("The 'system' argument must be a string when provided.", is_error=True)

    temperature = arguments.get("temperature", 0.2)
    if not isinstance(temperature, (int, float)):
        return text_result("The 'temperature' argument must be a number.", is_error=True)

    max_tokens = arguments.get("max_tokens", config.max_tokens)
    if not isinstance(max_tokens, int) or max_tokens <= 0:
        return text_result("The 'max_tokens' argument must be a positive integer.", is_error=True)

    disable_thinking = normalize_bool(
        arguments.get("disable_thinking"),
        config.disable_thinking,
    )
    include_reasoning = normalize_bool(arguments.get("include_reasoning"), False)

    messages: list[dict[str, str]] = []
    system_parts: list[str] = []
    if disable_thinking:
        system_parts.append("/no_think")
    system_parts.append(PRIMARY_ASSISTANT_SYSTEM_PROMPT)
    if system:
        system_parts.append(system)
    if system_parts:
        messages.append({"role": "system", "content": "\n".join(system_parts)})
    messages.append({"role": "user", "content": prompt})

    payload = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": False,
    }

    started_at = time.perf_counter()
    write_debug_log(
        config,
        "ask_local_llm.start",
        requested_model=model,
        prompt_chars=len(prompt),
        prompt_preview=prompt_preview(config, prompt),
        system_chars=len(system) if isinstance(system, str) else 0,
        temperature=temperature,
        max_tokens=max_tokens,
        disable_thinking=disable_thinking,
        include_reasoning=include_reasoning,
    )

    try:
        response = http_request(config, "POST", "/chat/completions", payload)
    except Exception as exc:  # noqa: BLE001
        write_debug_log(
            config,
            "ask_local_llm.error",
            requested_model=model,
            prompt_chars=len(prompt),
            prompt_preview=prompt_preview(config, prompt),
            duration_ms=round((time.perf_counter() - started_at) * 1000, 2),
            error=str(exc),
        )
        return text_result(str(exc), is_error=True)

    choices = response.get("choices") or []
    if not choices:
        write_debug_log(
            config,
            "ask_local_llm.empty_choices",
            requested_model=model,
            prompt_chars=len(prompt),
            prompt_preview=prompt_preview(config, prompt),
            duration_ms=round((time.perf_counter() - started_at) * 1000, 2),
            raw_response_keys=sorted(response.keys()),
        )
        return text_result(
            "The local API returned no choices for this request.",
            structured_content={"raw_response": response},
            is_error=True,
        )

    choice = choices[0]
    message = choice.get("message") or {}
    answer = message.get("content") or ""
    reasoning = message.get("reasoning_content") or ""
    finish_reason = choice.get("finish_reason")
    usage = response.get("usage") or {}

    if include_reasoning and reasoning:
        rendered = reasoning.strip() if not answer.strip() else f"{answer.strip()}\n\n--- reasoning_content ---\n{reasoning.strip()}"
    else:
        rendered = answer.strip()

    if not rendered:
        if reasoning and not include_reasoning:
            rendered = (
                "The local model returned reasoning tokens but no final answer text. "
                "Retry with disable_thinking=true or a larger max_tokens budget."
            )
        else:
            rendered = "The local model returned an empty response."

    write_debug_log(
        config,
        "ask_local_llm.success",
        requested_model=model,
        response_model=response.get("model", model),
        prompt_chars=len(prompt),
        prompt_preview=prompt_preview(config, prompt),
        answer_chars=len(answer.strip()),
        reasoning_chars=len(reasoning.strip()),
        finish_reason=finish_reason,
        usage=usage,
        duration_ms=round((time.perf_counter() - started_at) * 1000, 2),
        empty_answer=not bool(answer.strip()),
    )

    return text_result(
        rendered,
        structured_content={
            "base_url": config.base_url,
            "model": response.get("model", model),
            "answer": answer,
            "reasoning_content": reasoning if include_reasoning else "",
            "finish_reason": finish_reason,
            "usage": usage,
            "disable_thinking": disable_thinking,
        },
        is_error=not bool(answer.strip()) and not include_reasoning,
    )


def handle_tool_call(config: LocalLLMConfig, params: dict[str, Any]) -> dict[str, Any]:
    name = params.get("name")
    tool_args = params.get("arguments") or {}
    if not isinstance(name, str):
        raise ValueError("Missing tool name.")
    if not isinstance(tool_args, dict):
        raise ValueError("Tool arguments must be an object.")

    write_debug_log(
        config,
        "mcp.tools_call",
        tool_name=name,
        argument_keys=sorted(tool_args.keys()),
    )

    if name in {"ask_local_llm", "ask_lmstudio"}:
        return ask_local_llm(config, tool_args)
    if name in {"list_local_llm_models", "list_lmstudio_models"}:
        started_at = time.perf_counter()
        try:
            result = list_local_llm_models(config)
        except Exception as exc:
            write_debug_log(
                config,
                "list_local_llm_models.error",
                duration_ms=round((time.perf_counter() - started_at) * 1000, 2),
                error=str(exc),
            )
            raise
        models = result.get("structuredContent", {}).get("models", [])
        write_debug_log(
            config,
            "list_local_llm_models.success",
            duration_ms=round((time.perf_counter() - started_at) * 1000, 2),
            model_count=len(models),
        )
        return result
    if name == "local_api_mode_status":
        result = local_api_mode_status(config)
        write_debug_log(
            config,
            "local_api_mode_status.success",
            enabled=result.get("structuredContent", {}).get("enabled"),
        )
        return result
    raise KeyError(name)


def handle_request(config: LocalLLMConfig, request: dict[str, Any]) -> dict[str, Any] | None:
    method = request.get("method")
    request_id = request.get("id")

    if not method:
        if request_id is not None:
            return jsonrpc_error(request_id, -32600, "Invalid Request")
        return None

    if method == "initialize":
        params = request.get("params") or {}
        requested_version = params.get("protocolVersion")
        local_mode_enabled = read_mode_state(config)
        protocol_version = (
            requested_version
            if requested_version in SUPPORTED_PROTOCOL_VERSIONS
            else SUPPORTED_PROTOCOL_VERSIONS[0]
        )
        write_debug_log(
            config,
            "mcp.initialize",
            requested_protocol_version=requested_version,
            negotiated_protocol_version=protocol_version,
            local_mode_enabled=local_mode_enabled,
        )
        return jsonrpc_result(
            request_id,
            {
                "protocolVersion": protocol_version,
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
                "instructions": build_instructions(config, local_mode_enabled),
            },
        )

    if method == "notifications/initialized":
        return None

    if method == "ping":
        return jsonrpc_result(request_id, {})

    if method == "tools/list":
        local_mode_enabled = read_mode_state(config)
        tools = TOOLS if local_mode_enabled else []
        write_debug_log(
            config,
            "mcp.tools_list",
            local_mode_enabled=local_mode_enabled,
            tool_count=len(tools),
        )
        return jsonrpc_result(request_id, {"tools": tools})

    if method == "tools/call":
        local_mode_enabled = read_mode_state(config)
        if not local_mode_enabled:
            params = request.get("params") or {}
            tool_name = params.get("name") if isinstance(params, dict) else None
            write_debug_log(
                config,
                "mcp.tools_call.rejected",
                tool_name=tool_name,
                reason="local_mode_disabled",
            )
            return jsonrpc_result(
                request_id,
                text_result(
                    (
                        "Local API mode is disabled. Run `claude-local-api-mode enable` and "
                        "restart Claude Desktop to expose the local tools."
                    ),
                    structured_content={
                        "enabled": False,
                        "mode_file": str(config.mode_file),
                    },
                    is_error=True,
                ),
            )
        try:
            result = handle_tool_call(config, request.get("params") or {})
            return jsonrpc_result(request_id, result)
        except KeyError as exc:
            return jsonrpc_error(request_id, -32602, f"Unknown tool: {exc.args[0]}")
        except ValueError as exc:
            return jsonrpc_error(request_id, -32602, str(exc))
        except Exception as exc:  # noqa: BLE001
            params = request.get("params") or {}
            tool_name = params.get("name") if isinstance(params, dict) else None
            write_debug_log(
                config,
                "mcp.tools_call.error",
                tool_name=tool_name,
                error=str(exc),
            )
            log("Unhandled tool error:\n" + traceback.format_exc())
            return jsonrpc_result(
                request_id,
                text_result(f"Unhandled server error: {exc}", is_error=True),
            )

    if request_id is None:
        return None
    return jsonrpc_error(request_id, -32601, f"Method not found: {method}")


def main() -> int:
    config = LocalLLMConfig.from_env()
    write_debug_log(
        config,
        "server.start",
        base_url=config.base_url,
        default_model=config.model,
        local_api_mode_enabled=read_mode_state(config),
        mode_file=str(config.mode_file),
        debug_log_file=str(config.debug_log_file) if config.debug_log_file else None,
        log_prompt_preview=config.log_prompt_preview,
    )
    log(
        f"{SERVER_NAME} starting with base_url={config.base_url} default_model={config.model} "
        f"local_api_mode_enabled={read_mode_state(config)} mode_file={config.mode_file}"
    )
    try:
        for raw_line in sys.stdin:
            line = raw_line.strip()
            if not line:
                continue
            try:
                request = json.loads(line)
            except json.JSONDecodeError as exc:
                log(f"Could not decode JSON-RPC message: {exc}: {line}")
                continue
            if not isinstance(request, dict):
                log(f"Ignoring non-object JSON-RPC payload: {request!r}")
                continue
            response = handle_request(config, request)
            if response is not None:
                send(response)
    except KeyboardInterrupt:
        return 130
    return 0
