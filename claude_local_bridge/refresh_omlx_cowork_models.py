#!/usr/bin/env python3
"""Refresh Claude Desktop/Cowork local bridge routes from live OMLX models."""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path


DEFAULT_OMLX_BASE_URL = "http://127.0.0.1:8005"
DEFAULT_BRIDGE_BASE_URL = "http://127.0.0.1:1245"
DEFAULT_PROVIDER_AUTH_SCHEME = "x-api-key"
DEFAULT_PROVIDER_API_KEY = "local-bridge"
DEFAULT_AGENT_LABEL = "com.borland.claude-local-bridge"

NON_CONVERSATION_RE = re.compile(
    r"(embedding|reranker|hidream|image|visualquality)", re.IGNORECASE
)


def main() -> int:
    args = parse_args()
    omlx_base_url = args.omlx_base_url.rstrip("/")
    models_payload = fetch_models(omlx_base_url, args.api_key)
    conversation_models = filter_conversation_models(models_payload)

    if not conversation_models:
        print("error: OMLX returned no usable conversation models", file=sys.stderr)
        return 2

    route_map = build_route_map(conversation_models)
    claude_desktop_models = build_claude_desktop_models(route_map)
    validate_claude_desktop_models(claude_desktop_models, route_map)
    default_model = claude_desktop_models[0]["name"]
    provider_models = [
        {
            key: value
            for key, value in model.items()
            if key != "target"
        }
        for model in claude_desktop_models
    ]

    print_summary(omlx_base_url, conversation_models, route_map, default_model)

    if args.write_fixture:
        write_json(args.fixture_path, models_payload)
        print(f"wrote fixture: {args.fixture_path}")

    if args.print_json:
        print(json.dumps({
            "routeMap": route_map,
            "claudeDesktopModels": claude_desktop_models,
            "inferenceModels": provider_models,
        }, indent=2))

    if not args.apply:
        print("dry run only; rerun with --apply to update Claude/LaunchAgent files")
        return 0

    provider_path = active_provider_path(resolve_config_lib(args))
    update_provider_config(
        provider_path=provider_path,
        bridge_base_url=args.bridge_base_url.rstrip("/"),
        auth_scheme=args.provider_auth_scheme,
        api_key=args.provider_api_key,
        provider_models=provider_models,
    )
    sync_bridge_on_snapshot(provider_path)
    print(f"updated provider config: {provider_path}")

    update_bridge_config(
        bridge_config=args.bridge_config,
        omlx_base_url=omlx_base_url,
        auth_scheme=args.upstream_auth_scheme,
        default_model=default_model,
        route_map=route_map,
        claude_desktop_models=claude_desktop_models,
        upstream_api_key=args.api_key,
    )
    print(f"updated bridge config: {args.bridge_config}")

    if args.restart_agent:
        restart_launch_agent(args.launch_agent, args.agent_label)
        print(f"restarted LaunchAgent: {args.agent_label}")
    else:
        print("LaunchAgent not restarted; rerun with --restart-agent or restart it manually")

    return 0


def parse_args() -> argparse.Namespace:
    home = Path.home()
    parser = argparse.ArgumentParser(
        description="Refresh Claude Desktop/Cowork local bridge routes from live OMLX models."
    )
    parser.add_argument("--omlx-base-url", default=DEFAULT_OMLX_BASE_URL)
    parser.add_argument("--bridge-base-url", default=DEFAULT_BRIDGE_BASE_URL)
    parser.add_argument("--api-key", default=None, help="optional upstream OMLX API key")
    parser.add_argument("--upstream-auth-scheme", default="x-api-key")
    parser.add_argument("--provider-auth-scheme", default=DEFAULT_PROVIDER_AUTH_SCHEME)
    parser.add_argument("--provider-api-key", default=DEFAULT_PROVIDER_API_KEY)
    parser.add_argument(
        "--config-lib",
        type=Path,
        default=None,
        help="explicit Claude Desktop/Cowork configLibrary path",
    )
    parser.add_argument(
        "--profile",
        default=None,
        help="Claude profile name under ~/.claude-instances; use default for stock profile",
    )
    parser.add_argument(
        "--profile-dir",
        type=Path,
        default=None,
        help="explicit Claude profile user-data directory",
    )
    parser.add_argument(
        "--launch-agent",
        type=Path,
        default=home / "Library/LaunchAgents/com.borland.claude-local-bridge.plist",
    )
    parser.add_argument(
        "--bridge-config",
        type=Path,
        default=Path(__file__).with_name("bridge.local.json"),
    )
    parser.add_argument("--agent-label", default=DEFAULT_AGENT_LABEL)
    parser.add_argument(
        "--fixture-path",
        type=Path,
        default=Path(__file__).with_name("omlx-models.current.example.json"),
    )
    parser.add_argument("--write-fixture", action="store_true")
    parser.add_argument("--print-json", action="store_true")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--restart-agent", action="store_true")
    return parser.parse_args()


def fetch_models(base_url: str, api_key: str | None) -> dict:
    last_error: Exception | None = None
    for suffix in ("/v1/models", "/api/v1/models"):
        request = urllib.request.Request(f"{base_url}{suffix}")
        if api_key:
            request.add_header("x-api-key", api_key)
            request.add_header("authorization", f"Bearer {api_key}")
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                return json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as error:
            last_error = error
    raise SystemExit(f"error: failed to fetch OMLX models from {base_url}: {last_error}")


def filter_conversation_models(payload: dict) -> list[dict]:
    models = payload.get("data") or payload.get("models") or payload.get("items") or []
    conversation_models = []
    for model in models:
        model_id = str(model.get("id") or model.get("model") or model.get("name") or "")
        if not model_id or NON_CONVERSATION_RE.search(model_id):
            continue
        conversation_models.append({"id": model_id, **model})
    return conversation_models


def build_route_map(models: list[dict]) -> dict[str, str]:
    default_model = choose_default_model(models)
    remaining = [model["id"] for model in sort_models_for_routes(models) if model["id"] != default_model]
    ordered_targets = [default_model, *remaining]
    return {f"omlx/{model_id}": model_id for model_id in ordered_targets}


def build_claude_desktop_models(route_map: dict[str, str]) -> list[dict]:
    routes = list(route_map)
    alias_specs = [
        ("claude-sonnet-4-5", "sonnet", [r"qwen3\.5-9b-sushi-coder"], None),
        ("claude-opus-4-5", "opus", [r"qwen3-next-80b-a3b-instruct"], None),
        ("claude-mythos-5", "mythos", [r"qwen3-next-80b-a3b-thinking"], None),
        ("claude-sonnet-4-6", "sonnet", [r"qwen3\.6-27b-heretic"], None),
        ("claude-opus-4-8", "opus", [r"claude-opus-vl-grafted"], None),
        ("claude-opus-4-1", "opus", [r"qwen3\.6-35b-a3b-mlx-4bit"], None),
        ("claude-fable-5", "fable", [r"gemma-4-12b-coder"], None),
        ("claude-haiku-4-5", "haiku", [r"gemma-4-e4b-it"], None),
        ("claude-haiku-4-5-20251001", "haiku", [r"qwen3-vl-4b-instruct"], None),
        ("claude-sonnet-4-5-20250929", "sonnet", [], None),
        ("claude-opus-4-1-20250805", "opus", [], None),
        ("claude-3-7-sonnet-20250219", "sonnet", [], None),
        ("claude-3-5-sonnet-20241022", "sonnet", [], None),
        ("claude-3-5-haiku-20241022", "haiku", [], None),
        ("claude-3-opus-20240229", "opus", [], None),
        ("claude-3-sonnet-20240229", "sonnet", [], None),
    ]
    models = []
    seen_names: set[str] = set()
    used_routes: set[str] = set()
    default_tiers: set[str] = set()
    for name, tier, patterns, label_hint in alias_specs:
        if name in seen_names:
            continue
        target = choose_unused_route(routes, used_routes, patterns)
        if not target:
            continue
        used_routes.add(target)
        seen_names.add(name)
        upstream_id = route_map[target]
        label = label_hint or label_for_model(upstream_id)
        is_family_default = tier not in default_tiers
        default_tiers.add(tier)
        models.append(
            {
                "name": name,
                "target": target,
                "labelOverride": f"{label} via Local Bridge",
                "anthropicFamilyTier": tier,
                "isFamilyDefault": is_family_default,
            }
        )
    return models


def validate_claude_desktop_models(
    models: list[dict],
    route_map: dict[str, str],
) -> None:
    aliases = [str(model.get("name") or "") for model in models]
    targets = [str(model.get("target") or "") for model in models]

    if len(models) != len(route_map):
        raise SystemExit(
            "error: Claude Desktop alias pool did not cover every usable OMLX model "
            f"({len(models)} aliases for {len(route_map)} routes)"
        )
    if len(set(aliases)) != len(aliases):
        raise SystemExit("error: duplicate Claude Desktop model aliases generated")
    if len(set(targets)) != len(targets):
        raise SystemExit("error: duplicate Claude Desktop alias targets generated")

    missing_targets = sorted(set(route_map) - set(targets))
    if missing_targets:
        raise SystemExit(
            "error: Claude Desktop aliases missing OMLX routes: "
            + ", ".join(missing_targets)
        )

    aliases_by_tier: dict[str, set[str]] = {}
    defaults_by_tier: dict[str, int] = {}
    for model in models:
        tier = str(model.get("anthropicFamilyTier") or "")
        alias = str(model.get("name") or "")
        if not tier:
            continue
        aliases_by_tier.setdefault(tier, set()).add(alias)
        if model.get("isFamilyDefault") is True:
            defaults_by_tier[tier] = defaults_by_tier.get(tier, 0) + 1

    for tier, aliases_for_tier in aliases_by_tier.items():
        count_for_tier = sum(
            1 for model in models if model.get("anthropicFamilyTier") == tier
        )
        if len(aliases_for_tier) != count_for_tier:
            raise SystemExit(
                f"error: duplicate Claude Desktop version alias generated for {tier}"
            )
    for tier, default_count in defaults_by_tier.items():
        if default_count > 1:
            raise SystemExit(
                f"error: multiple Claude Desktop family defaults generated for {tier}"
            )


def choose_unused_route(
    routes: list[str],
    used_routes: set[str],
    patterns: list[str],
) -> str | None:
    for pattern in patterns:
        regex = re.compile(pattern, re.IGNORECASE)
        for route in routes:
            if route not in used_routes and regex.search(route):
                return route
    if not patterns:
        for route in routes:
            if route not in used_routes:
                return route
    return None


def choose_default_model(models: list[dict]) -> str:
    return sort_models_for_default(models)[0]["id"]


def sort_models_for_default(models: list[dict]) -> list[dict]:
    return sorted(models, key=lambda model: (-default_score(model["id"]), model["id"].lower()))


def sort_models_for_routes(models: list[dict]) -> list[dict]:
    return sorted(models, key=lambda model: (-route_score(model["id"]), model["id"].lower()))


def default_score(model_id: str) -> int:
    text = model_id.lower()
    score = 0
    if "coder" in text:
        score += 500
    if "qwen" in text:
        score += 225
    if "sushi" in text:
        score += 175
    if "instruct" in text:
        score += 250
    if "thinking" in text:
        score += 150
    if "vl" in text:
        score -= 125
    params = infer_params_b(model_id)
    if params:
        score += min(params, 12)
    return score


def route_score(model_id: str) -> int:
    text = model_id.lower()
    preferred_priority = preferred_route_priority(text)
    if preferred_priority:
        return preferred_priority
    score = 0
    if "coder" in text:
        score += 400
    if "qwen" in text:
        score += 100
    if "instruct" in text:
        score += 350
    if "thinking" in text:
        score += 300
    if "claude" in text:
        score += 250
    if "heretic" in text:
        score += 200
    if "gemma" in text:
        score += 100
    if "vl" in text:
        score -= 50
    params = infer_params_b(model_id)
    if params:
        score += min(params, 80)
    return score


def preferred_route_priority(text: str) -> int:
    if "qwen3-next-80b-a3b-instruct" in text:
        return 1_000
    if "qwen3-next-80b-a3b-thinking" in text:
        return 950
    if "heretic" in text:
        return 900
    if "claude-opus-vl-grafted" in text:
        return 850
    if "qwen3.6-35b-a3b-mlx-4bit" in text:
        return 800
    if "gemma-4-12b-coder" in text:
        return 700
    if "gemma-4-e4b-it" in text:
        return 600
    if "qwen3-vl-4b-instruct" in text:
        return 500
    return 0


def infer_params_b(model_id: str) -> int:
    match = re.search(r"(?<!\d)(\d+)(?:\.\d+)?[bB](?![A-Za-z])", model_id)
    return int(match.group(1)) if match else 0


def label_for_model(model_id: str) -> str:
    label = re.sub(r"[-_]+", " ", model_id).strip()
    label = re.sub(r"\bmlx\b", "MLX", label, flags=re.IGNORECASE)
    label = re.sub(r"\bbf16\b", "bf16", label, flags=re.IGNORECASE)
    label = re.sub(r"\b4bit\b", "4-bit", label, flags=re.IGNORECASE)
    label = re.sub(r"\b8bit\b", "8-bit", label, flags=re.IGNORECASE)
    return label


def print_summary(
    omlx_base_url: str,
    models: list[dict],
    route_map: dict[str, str],
    default_model: str,
) -> None:
    print(f"OMLX: {omlx_base_url}")
    print(f"usable conversation models: {len(models)}")
    print(f"default/tool model: {default_model}")
    print("route map:")
    for route, model in route_map.items():
        print(f"  {route} -> {model}")


def active_provider_path(config_lib: Path) -> Path:
    meta_path = config_lib / "_meta.json"
    meta = json.loads(meta_path.read_text())
    applied_id = meta.get("appliedId")
    if not applied_id:
        raise SystemExit(f"error: appliedId missing from {meta_path}")
    provider_path = config_lib / f"{applied_id}.json"
    if not provider_path.exists():
        raise SystemExit(f"error: active provider config missing: {provider_path}")
    return provider_path


def resolve_config_lib(args: argparse.Namespace) -> Path:
    home = Path.home()
    if args.config_lib:
        return args.config_lib
    if args.profile_dir:
        return args.profile_dir / "configLibrary"
    if args.profile and args.profile != "default":
        return home / ".claude-instances" / args.profile / "configLibrary"
    return home / "Library/Application Support/Claude-3p/configLibrary"


def update_provider_config(
    provider_path: Path,
    bridge_base_url: str,
    auth_scheme: str,
    api_key: str,
    provider_models: list[dict],
) -> None:
    config = json.loads(provider_path.read_text())
    backup_path(provider_path)
    config.update(
        {
            "inferenceGatewayApiKey": config.get("inferenceGatewayApiKey") or api_key,
            "inferenceGatewayAuthScheme": auth_scheme,
            "inferenceGatewayBaseUrl": bridge_base_url,
            "inferenceProvider": "gateway",
            "isDesktopExtensionEnabled": True,
            "modelDiscoveryEnabled": False,
            "inferenceModels": provider_models,
        }
    )
    provider_path.write_text(json.dumps(config, indent=2) + "\n")


def sync_bridge_on_snapshot(provider_path: Path) -> None:
    snapshot = provider_path.with_name(f"{provider_path.name}.bridge-on.bak")
    if snapshot.exists():
        shutil.copy2(provider_path, snapshot)


def update_bridge_config(
    bridge_config: Path,
    omlx_base_url: str,
    auth_scheme: str,
    default_model: str,
    route_map: dict[str, str],
    claude_desktop_models: list[dict],
    upstream_api_key: str | None,
) -> None:
    if bridge_config.exists():
        with bridge_config.open("r", encoding="utf-8") as handle:
            config = json.load(handle)
        backup_path(bridge_config)
    else:
        config = {}
    env = dict(config.get("env") or {})
    env.update({"OMLX_API_KEY": upstream_api_key or env.get("OMLX_API_KEY") or DEFAULT_PROVIDER_API_KEY})
    config.update(
        {
            "bridge": config.get("bridge") or {"host": "127.0.0.1", "port": 1245},
            "providersFile": config.get("providersFile") or "providers.local.json",
            "models": {
                **dict(config.get("models") or {}),
                "main": default_model,
                "small": first_alias_name(claude_desktop_models, "haiku") or default_model,
                "tool": default_model,
            },
            "modelMap": route_map,
            "claudeDesktopModels": claude_desktop_models,
            "env": env,
        }
    )
    providers_path = bridge_config.with_name(str(config["providersFile"]))
    if not providers_path.is_absolute():
        providers_path = bridge_config.parent / providers_path
    providers_payload = {
        "providers": [
            {
                "id": "omlx",
                "type": "anthropic",
                "baseUrl": omlx_base_url,
                "authScheme": auth_scheme,
                "apiKeyEnv": "OMLX_API_KEY",
                "label": "OMLX",
            }
        ]
    }
    if providers_path.exists():
        backup_path(providers_path)
    write_json(providers_path, providers_payload)
    if upstream_api_key:
        env["OMLX_API_KEY"] = upstream_api_key
    write_json(bridge_config, config)


def restart_launch_agent(launch_agent: Path, label: str) -> None:
    domain = f"gui/{subprocess.check_output(['id', '-u'], text=True).strip()}"
    subprocess.run(["launchctl", "bootout", domain, str(launch_agent)], check=False)
    subprocess.run(["launchctl", "bootstrap", domain, str(launch_agent)], check=True)
    subprocess.run(["launchctl", "kickstart", "-k", f"{domain}/{label}"], check=True)


def write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, indent=2) + "\n")


def first_alias_name(models: list[dict], tier: str) -> str | None:
    for model in models:
        if model.get("anthropicFamilyTier") == tier:
            return str(model["name"])
    return None


def backup_path(path: Path) -> None:
    stamp = time.strftime("%Y%m%d-%H%M%S")
    shutil.copy2(path, path.with_suffix(path.suffix + f".bak-refresh-{stamp}"))


if __name__ == "__main__":
    raise SystemExit(main())
