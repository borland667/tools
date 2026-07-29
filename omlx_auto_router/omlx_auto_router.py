#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import time
from dataclasses import asdict, dataclass
from typing import Any, Literal, Optional

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse


OMLX_BASE_URL = os.getenv("OMLX_BASE_URL", "http://127.0.0.1:8005/v1").rstrip("/")
OMLX_API_KEY = os.getenv("OMLX_API_KEY", "sk-local")

AUTO_MODEL = os.getenv("AUTO_MODEL", "auto")
AUTO_CHAT_MODEL = os.getenv("AUTO_CHAT_MODEL", "auto-chat")
AUTO_AGENT_MODEL = os.getenv("AUTO_AGENT_MODEL", "auto-agent")

CLASSIFIER_MODEL = os.getenv("CLASSIFIER_MODEL", "gemma-4-e4b-it-4bit")
CLASSIFIER_TIMEOUT = float(os.getenv("CLASSIFIER_TIMEOUT", "10"))
CLASSIFIER_THRESHOLD = float(os.getenv("CLASSIFIER_THRESHOLD", "0.65"))
CLASSIFIER_MAX_CHARS = int(os.getenv("CLASSIFIER_MAX_CHARS", "12000"))
CACHE_TTL = int(os.getenv("CLASSIFIER_CACHE_TTL", "300"))
ALLOW_HEAVY_MODELS = os.getenv("ALLOW_HEAVY_MODELS", "true").lower() in {
    "1",
    "true",
    "yes",
    "on",
}

MODELS = {
    "coder": os.getenv("MODEL_CODER", "Qwen3.5-9b-Sushi-Coder-RL-MLX"),
    "embedding": os.getenv(
        "MODEL_EMBEDDING",
        "Qwen3-Embedding-0.6B-4bit-DWQ",
    ),
    "reranker": os.getenv(
        "MODEL_RERANKER",
        "Qwen3-Reranker-0.6B-4bit",
    ),
    "reasoner": os.getenv(
        "MODEL_REASONER",
        "Qwen3-Next-80B-A3B-Thinking-4bit",
    ),
    "thinking": os.getenv(
        "MODEL_THINKING",
        "Qwen3-Next-80B-A3B-Thinking-4bit",
    ),
    "review": os.getenv(
        "MODEL_REVIEW",
        "Qwen3.6-35B-A3B-Claude-Opus-VL-grafted-MLX-8bit",
    ),
    "fast": os.getenv(
        "MODEL_FAST",
        "gemma-4-e4b-it-4bit",
    ),
    "vision": os.getenv(
        "MODEL_VISION",
        "Qwen3-VL-4B-Instruct-4bit",
    ),
    "visual_quality": os.getenv(
        "MODEL_VISUAL_QUALITY",
        "VisualQuality-R1-7B-4bit",
    ),
}

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(message)s",
)
log = logging.getLogger("omlx-auto-router")
__version__ = "1.0.0"
app = FastAPI(title="oMLX Auto Router", version=__version__)


Route = Literal[
    "coding",
    "debugging",
    "architecture",
    "deep_review",
    "summary",
    "general",
    "vision",
    "visual_quality",
]


@dataclass(frozen=True)
class Decision:
    route: Route
    model: str
    confidence: float
    reason: str
    source: str


_cache: dict[str, tuple[float, Decision]] = {}


def upstream_headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {OMLX_API_KEY}",
        "Content-Type": "application/json",
    }


def content_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""

    parts: list[str] = []

    for item in content:
        if not isinstance(item, dict):
            continue

        kind = item.get("type")

        if kind in {"text", "input_text"}:
            parts.append(str(item.get("text", "")))
        elif kind in {"image_url", "input_image", "image"}:
            parts.append("[image]")

    return "\n".join(parts)


def latest_user_text(messages: list[dict[str, Any]]) -> str:
    for message in reversed(messages):
        if message.get("role") == "user":
            return content_text(message.get("content"))

    return ""


def recent_text(
    messages: list[dict[str, Any]],
    limit: int = 8,
) -> str:
    chunks: list[str] = []

    for message in messages[-limit:]:
        text = content_text(message.get("content"))

        if text:
            chunks.append(f"{message.get('role', 'unknown')}: {text}")

    return "\n".join(chunks)


def contains_image(messages: list[dict[str, Any]]) -> bool:
    return any(
        "[image]" in content_text(message.get("content"))
        for message in messages
    )


def auto_mode(model: Optional[str]) -> Optional[str]:
    if not model:
        return None

    value = model.strip().lower()

    if value in {
        AUTO_MODEL.lower(),
        AUTO_CHAT_MODEL.lower(),
        "omlx-auto",
        "omlx-auto-chat",
    }:
        return "chat"

    if value in {
        AUTO_AGENT_MODEL.lower(),
        "omlx-auto-agent",
    }:
        return "agent"

    return None


def route_model(route: Route) -> str:
    mapping = {
        "coding": MODELS["coder"],
        "debugging": MODELS["reasoner"],
        "architecture": (
            MODELS["thinking"]
            if ALLOW_HEAVY_MODELS
            else MODELS["reasoner"]
        ),
        "deep_review": (
            MODELS["review"]
            if ALLOW_HEAVY_MODELS
            else MODELS["coder"]
        ),
        "summary": MODELS["fast"],
        "general": MODELS["coder"],
        "vision": MODELS["vision"],
        "visual_quality": MODELS["visual_quality"],
    }

    return mapping[route]


def validate_tool_history(
    messages: list[dict[str, Any]],
) -> None:
    """
    OpenAI tool-call arguments must be JSON-encoded object strings.

    Dict arguments are normalized to strings. Malformed prior tool calls are
    rejected before they reach oMLX so Continue gets a useful error.
    """
    for message_index, message in enumerate(messages):
        tool_calls = message.get("tool_calls")

        if not isinstance(tool_calls, list):
            continue

        for tool_index, tool_call in enumerate(tool_calls):
            function = (
                tool_call.get("function")
                if isinstance(tool_call, dict)
                else None
            )

            if not isinstance(function, dict):
                continue

            arguments = function.get("arguments")

            if isinstance(arguments, dict):
                function["arguments"] = json.dumps(
                    arguments,
                    separators=(",", ":"),
                )
                continue

            if not isinstance(arguments, str):
                raise HTTPException(
                    status_code=422,
                    detail={
                        "message": (
                            "tool_call.arguments must be a "
                            "JSON-encoded object string"
                        ),
                        "message_index": message_index,
                        "tool_index": tool_index,
                    },
                )

            try:
                parsed = json.loads(arguments)
            except json.JSONDecodeError as exc:
                raise HTTPException(
                    status_code=422,
                    detail={
                        "message": (
                            "Malformed prior tool call; "
                            "start a new chat"
                        ),
                        "message_index": message_index,
                        "tool_index": tool_index,
                        "error": str(exc),
                        "arguments": arguments[:500],
                    },
                ) from exc

            if not isinstance(parsed, dict):
                raise HTTPException(
                    status_code=422,
                    detail=(
                        "tool_call.arguments must decode "
                        "to a JSON object"
                    ),
                )


CLASSIFIER_PROMPT = """
Classify the software-development request into exactly one route.

Routes:
- coding: implementation, refactoring, tests, APIs, SQL, infrastructure code
- debugging: root cause, incidents, errors, timeouts, performance, query plans
- architecture: system design, migrations, tradeoffs, broad technical plans
- deep_review: code/design/security/operational review without implementation
- summary: concise explanation, documentation, or summarization
- vision: understanding screenshots, diagrams, images, or user interfaces
- visual_quality: blur, sharpness, lighting, artifacts, aesthetics, image quality
- general: anything else

Return JSON only:
{"route":"<route>","confidence":0.0,"reason":"<short reason>"}
""".strip()


def classifier_input(
    body: dict[str, Any],
    mode: str,
) -> dict[str, Any]:
    messages = body.get("messages") or []
    prompt = recent_text(messages)

    return {
        "mode": mode,
        "has_tools": bool(body.get("tools")),
        "has_images": contains_image(messages),
        "estimated_tokens": max(1, len(prompt) // 4),
        "user_request": latest_user_text(messages)[
            -CLASSIFIER_MAX_CHARS:
        ],
    }


def parse_json_object(text: str) -> dict[str, Any]:
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)

    try:
        value = json.loads(text)

        if isinstance(value, dict):
            return value
    except json.JSONDecodeError:
        pass

    start = text.find("{")
    end = text.rfind("}")

    if start >= 0 and end > start:
        value = json.loads(text[start : end + 1])

        if isinstance(value, dict):
            return value

    raise ValueError("Classifier did not return a JSON object")


def cache_key(data: dict[str, Any]) -> str:
    raw = json.dumps(
        data,
        sort_keys=True,
        ensure_ascii=False,
    )

    return hashlib.sha256(raw.encode()).hexdigest()


def cache_get(key: str) -> Optional[Decision]:
    entry = _cache.get(key)

    if not entry:
        return None

    created_at, decision = entry

    if time.monotonic() - created_at > CACHE_TTL:
        _cache.pop(key, None)
        return None

    return decision


def cache_set(
    key: str,
    decision: Decision,
) -> None:
    if len(_cache) >= 1000:
        oldest = min(
            _cache,
            key=lambda item: _cache[item][0],
        )
        _cache.pop(oldest, None)

    _cache[key] = (
        time.monotonic(),
        decision,
    )


async def classify_with_model(
    data: dict[str, Any],
) -> Decision:
    allowed: list[Route] = [
        "coding",
        "debugging",
        "architecture",
        "deep_review",
        "summary",
        "general",
        "vision",
        "visual_quality",
    ]

    payload: dict[str, Any] = {
        "model": CLASSIFIER_MODEL,
        "messages": [
            {
                "role": "system",
                "content": CLASSIFIER_PROMPT,
            },
            {
                "role": "user",
                "content": json.dumps(
                    data,
                    ensure_ascii=False,
                ),
            },
        ],
        "temperature": 0,
        "max_tokens": 128,
        "stream": False,
        "response_format": {
            "type": "json_schema",
            "json_schema": {
                "name": "route_decision",
                "strict": True,
                "schema": {
                    "type": "object",
                    "properties": {
                        "route": {
                            "type": "string",
                            "enum": allowed,
                        },
                        "confidence": {
                            "type": "number",
                            "minimum": 0,
                            "maximum": 1,
                        },
                        "reason": {
                            "type": "string",
                        },
                    },
                    "required": [
                        "route",
                        "confidence",
                        "reason",
                    ],
                    "additionalProperties": False,
                },
            },
        },
    }

    async with httpx.AsyncClient(
        timeout=CLASSIFIER_TIMEOUT,
    ) as client:
        response = await client.post(
            f"{OMLX_BASE_URL}/chat/completions",
            json=payload,
            headers=upstream_headers(),
        )

        if response.status_code in {
            400,
            404,
            415,
            422,
        }:
            payload.pop("response_format", None)

            response = await client.post(
                f"{OMLX_BASE_URL}/chat/completions",
                json=payload,
                headers=upstream_headers(),
            )

        response.raise_for_status()
        result = response.json()

    content = (
        result["choices"][0]["message"]
        .get("content", "")
    )
    parsed = parse_json_object(content)
    raw_route = str(parsed.get("route", "general"))

    route: Route = (
        raw_route
        if raw_route in allowed
        else "general"
    )  # type: ignore[assignment]

    confidence = max(
        0.0,
        min(
            1.0,
            float(parsed.get("confidence", 0)),
        ),
    )

    return Decision(
        route=route,
        model=route_model(route),
        confidence=confidence,
        reason=str(
            parsed.get(
                "reason",
                "No reason returned",
            )
        ),
        source="classifier",
    )


def heuristic(
    body: dict[str, Any],
) -> Decision:
    messages = body.get("messages") or []
    text = recent_text(messages).lower()

    if contains_image(messages):
        quality_words = {
            "quality",
            "blur",
            "blurry",
            "sharpness",
            "lighting",
            "artifact",
            "aesthetic",
            "resolution",
            "noise",
        }

        route: Route = (
            "visual_quality"
            if any(
                word in text
                for word in quality_words
            )
            else "vision"
        )

        return Decision(
            route=route,
            model=route_model(route),
            confidence=0.95,
            reason="Image route",
            source="heuristic",
        )

    tests: list[
        tuple[Route, tuple[str, ...]]
    ] = [
        (
            "debugging",
            (
                "root cause",
                "debug",
                "investigate",
                "timeout",
                "latency",
                "outage",
                "oom",
                "memory leak",
                "race condition",
                "query plan",
            ),
        ),
        (
            "architecture",
            (
                "architecture",
                "system design",
                "migration plan",
                "tradeoff",
                "roadmap",
                "phased plan",
                "technical strategy",
            ),
        ),
        (
            "deep_review",
            (
                "security review",
                "design review",
                "operational risk",
                "pr review",
                "review this module",
                "review this service",
            ),
        ),
        (
            "coding",
            (
                "implement",
                "refactor",
                "write tests",
                "fix this",
                "patch",
                "edit",
                "apply",
                "python",
                "django",
                "typescript",
                "sql",
                "postgres",
                "kubernetes",
                "terraform",
                "helm",
            ),
        ),
        (
            "summary",
            (
                "summarize",
                "summary",
                "tl;dr",
                "explain briefly",
                "what does this file do",
                "document this",
            ),
        ),
    ]

    for route, keywords in tests:
        if any(
            keyword in text
            for keyword in keywords
        ):
            return Decision(
                route=route,
                model=route_model(route),
                confidence=0.75,
                reason=f"Matched {route} keywords",
                source="heuristic",
            )

    return Decision(
        route="general",
        model=route_model("general"),
        confidence=0.5,
        reason="No specialized route matched",
        source="heuristic",
    )


async def choose_model(
    body: dict[str, Any],
    mode: str,
) -> Decision:
    messages = body.get("messages") or []

    if mode == "agent" or body.get("tools"):
        return Decision(
            route="coding",
            model=MODELS["coder"],
            confidence=1.0,
            reason="Agent/tool request pinned to coder",
            source="hard_rule",
        )

    if contains_image(messages):
        return heuristic(body)

    data = classifier_input(
        body,
        mode,
    )
    key = cache_key(data)
    cached = cache_get(key)

    if cached:
        return Decision(
            route=cached.route,
            model=cached.model,
            confidence=cached.confidence,
            reason=cached.reason,
            source="cache",
        )

    try:
        decision = await classify_with_model(data)

        if decision.confidence < CLASSIFIER_THRESHOLD:
            fallback = heuristic(body)

            decision = Decision(
                route=fallback.route,
                model=fallback.model,
                confidence=decision.confidence,
                reason=(
                    "Low confidence; "
                    f"{fallback.reason}"
                ),
                source="heuristic_fallback",
            )

    except (
        httpx.HTTPError,
        ValueError,
        KeyError,
        IndexError,
        TypeError,
    ) as exc:
        fallback = heuristic(body)

        decision = Decision(
            route=fallback.route,
            model=fallback.model,
            confidence=0.0,
            reason=(
                f"Classifier failed "
                f"({type(exc).__name__}); "
                f"{fallback.reason}"
            ),
            source="heuristic_fallback",
        )

        log.warning(
            "Classifier failed: %r",
            exc,
        )

    cache_set(
        key,
        decision,
    )

    return decision


async def upstream_json(
    path: str,
    body: dict[str, Any],
) -> JSONResponse:
    async with httpx.AsyncClient(
        timeout=None,
    ) as client:
        response = await client.post(
            f"{OMLX_BASE_URL}{path}",
            json=body,
            headers=upstream_headers(),
        )

    try:
        payload = response.json()
    except ValueError:
        payload = {
            "error": {
                "message": response.text,
            }
        }

    return JSONResponse(
        status_code=response.status_code,
        content=payload,
    )


@app.get("/health")
async def health() -> dict[str, Any]:
    return {
        "ok": True,
        "omlx_base_url": OMLX_BASE_URL,
        "classifier_model": CLASSIFIER_MODEL,
        "models": MODELS,
    }


@app.get("/v1/models")
async def models() -> JSONResponse:
    async with httpx.AsyncClient(
        timeout=30,
    ) as client:
        response = await client.get(
            f"{OMLX_BASE_URL}/models",
            headers=upstream_headers(),
        )

    data = response.json()
    aliases = [
        AUTO_MODEL,
        AUTO_CHAT_MODEL,
        AUTO_AGENT_MODEL,
    ]
    existing = {
        item.get("id")
        for item in data.get("data", [])
    }

    for alias in reversed(aliases):
        if alias not in existing:
            data.setdefault(
                "data",
                [],
            ).insert(
                0,
                {
                    "id": alias,
                    "object": "model",
                    "created": 0,
                    "owned_by": "omlx-auto-router",
                    "max_model_len": 262144,
                },
            )

    return JSONResponse(
        status_code=response.status_code,
        content=data,
    )


@app.post("/v1/chat/completions")
async def chat_completions(
    request: Request,
):
    body: dict[str, Any] = await request.json()
    messages = body.get("messages")

    if not isinstance(
        messages,
        list,
    ):
        raise HTTPException(
            status_code=422,
            detail="'messages' must be an array",
        )

    validate_tool_history(messages)

    requested_model = body.get("model")
    mode = auto_mode(requested_model)
    decision: Optional[Decision] = None

    if mode:
        decision = await choose_model(
            body,
            mode,
        )
        body["model"] = decision.model

        log.info(
            "route=%s",
            json.dumps(
                asdict(decision),
                ensure_ascii=False,
            ),
        )

    headers: dict[str, str] = {}

    if decision:
        headers = {
            "X-Auto-Router-Model": decision.model,
            "X-Auto-Router-Route": decision.route,
            "X-Auto-Router-Source": decision.source,
        }

    if body.get("stream"):

        async def generate():
            async with httpx.AsyncClient(
                timeout=None,
            ) as client:
                async with client.stream(
                    "POST",
                    f"{OMLX_BASE_URL}/chat/completions",
                    json=body,
                    headers=upstream_headers(),
                ) as response:
                    async for chunk in response.aiter_bytes():
                        yield chunk

        return StreamingResponse(
            generate(),
            media_type="text/event-stream",
            headers=headers,
        )

    async with httpx.AsyncClient(
        timeout=None,
    ) as client:
        response = await client.post(
            f"{OMLX_BASE_URL}/chat/completions",
            json=body,
            headers=upstream_headers(),
        )

    try:
        data = response.json()
    except ValueError:
        data = {
            "error": {
                "message": response.text,
            }
        }

    if decision and isinstance(
        data,
        dict,
    ):
        data["auto_router"] = {
            "requested_model": requested_model,
            "classifier_model": CLASSIFIER_MODEL,
            **asdict(decision),
        }

    return JSONResponse(
        status_code=response.status_code,
        content=data,
        headers=headers,
    )


@app.post("/v1/embeddings")
async def embeddings(
    request: Request,
) -> JSONResponse:
    body: dict[str, Any] = await request.json()

    if auto_mode(body.get("model")):
        body["model"] = MODELS["embedding"]

    return await upstream_json(
        "/embeddings",
        body,
    )


@app.post("/v1/rerank")
async def rerank(
    request: Request,
) -> JSONResponse:
    body: dict[str, Any] = await request.json()

    if auto_mode(body.get("model")):
        body["model"] = MODELS["reranker"]

    return await upstream_json(
        "/rerank",
        body,
    )


def main() -> None:
    """Run the router with Uvicorn using environment-based settings."""
    import uvicorn

    uvicorn.run(
        "omlx_auto_router:app",
        host=os.getenv(
            "ROUTER_HOST",
            "127.0.0.1",
        ),
        port=int(
            os.getenv(
                "ROUTER_PORT",
                "8010",
            )
        ),
        reload=(
            os.getenv(
                "ROUTER_RELOAD",
                "false",
            ).lower()
            in {
                "1",
                "true",
                "yes",
                "on",
            }
        ),
    )


if __name__ == "__main__":
    main()
