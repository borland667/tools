#!/usr/bin/env python3
"""Generate Claude Desktop/Cowork third-party inference profile configs."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path
from typing import Any


DEFAULT_PROFILE = "local-3p"
DEFAULT_BRIDGE_BASE_URL = "http://127.0.0.1:1245"
DEFAULT_GATEWAY_API_KEY = "local-bridge"
DEFAULT_GATEWAY_AUTH_SCHEME = "x-api-key"
DEFAULT_CONFIG_NAME = "Local Claude Bridge API"
SENSITIVE_KEYS = {
    "inferenceGatewayApiKey",
    "inferenceGatewayOidc",
    "inferenceCustomHeaders",
    "customInferenceHeaders",
}


def main() -> int:
    args = parse_args()
    base_config = load_base_config(args)
    spec = load_spec(args.spec) if args.spec else {}

    target_config_lib = resolve_config_lib(args)
    target_meta_path = target_config_lib / "_meta.json"
    target_config_id = args.config_id or spec.get("configId") or read_applied_id(target_meta_path) or str(uuid.uuid4())
    target_config_path = target_config_lib / f"{target_config_id}.json"
    config_name = args.name or spec.get("name") or DEFAULT_CONFIG_NAME

    inference_models = resolve_inference_models(args, spec, base_config)
    config = build_config(args, spec, base_config, inference_models)
    validate_config(config)

    meta = {
        "appliedId": target_config_id,
        "entries": [{"id": target_config_id, "name": config_name}],
    }

    if args.print_json:
        print(json.dumps({"meta": meta, "config": redact_config(config)}, indent=2))

    print_summary(target_config_lib, target_config_id, config_name, config)

    if not args.apply:
        print("dry run only; rerun with --apply to write configLibrary files")
        return 0

    target_config_lib.mkdir(parents=True, exist_ok=True)
    backup_if_exists(target_meta_path)
    backup_if_exists(target_config_path)
    write_json(target_config_path, config)
    write_json(target_meta_path, meta)
    print(f"wrote provider config: {target_config_path}")
    print(f"wrote config metadata: {target_meta_path}")
    print("restart the exact Claude profile for the 3P config to take effect")
    return 0


def parse_args() -> argparse.Namespace:
    home = Path.home()
    parser = argparse.ArgumentParser(
        description="Generate a Claude Desktop/Cowork third-party inference configLibrary entry."
    )
    parser.add_argument("--spec", type=Path, help="optional generator JSON spec")
    parser.add_argument("--name", help="profile config entry name shown in Claude setup")
    parser.add_argument("--config-id", help="stable configLibrary entry id; defaults to active id or a UUID")
    parser.add_argument("--profile", default=DEFAULT_PROFILE, help="target Claude profile under ~/.claude-instances")
    parser.add_argument("--profile-dir", type=Path, help="explicit target Claude profile directory")
    parser.add_argument("--config-lib", type=Path, help="explicit target configLibrary path")
    parser.add_argument("--base-profile", default=DEFAULT_PROFILE, help="base profile to copy defaults from")
    parser.add_argument("--base-profile-dir", type=Path, help="explicit base Claude profile directory")
    parser.add_argument("--base-config-lib", type=Path, help="explicit base configLibrary path")
    parser.add_argument("--base-config", type=Path, help="explicit base provider config JSON")
    parser.add_argument("--no-base", action="store_true", help="start from generator defaults instead of a base config")
    parser.add_argument("--bridge-base-url", default=None)
    parser.add_argument("--gateway-api-key", default=None)
    parser.add_argument("--gateway-auth-scheme", default=None)
    parser.add_argument("--credential-kind", default=None)
    parser.add_argument("--provider", default=None, choices=["gateway", "anthropic", "bedrock", "mantle", "vertex", "foundry"])
    parser.add_argument("--model-discovery", choices=["true", "false"], default=None)
    parser.add_argument("--egress-host", action="append", default=None, help="repeatable Cowork egress host; use '*' for all")
    parser.add_argument("--no-egress-wildcard", action="store_true", help="do not default Cowork egress to ['*']")
    parser.add_argument("--deployment-organization-uuid", default=None)
    parser.add_argument("--disable-deployment-mode-chooser", choices=["true", "false"], default=None)
    parser.add_argument(
        "--models-source",
        choices=["bridge-config", "bridge-live", "base", "file", "none"],
        default=None,
        help="where inferenceModels should come from",
    )
    parser.add_argument("--bridge-config", type=Path, default=Path(__file__).with_name("bridge.local.json"))
    parser.add_argument("--models-file", type=Path, help="JSON file with inferenceModels or OpenAI-style data[]")
    parser.add_argument("--models-url", default=None, help="bridge model endpoint for --models-source bridge-live")
    parser.add_argument("--api-key-header", default="x-api-key")
    parser.add_argument("--api-key", default=None, help="optional key for fetching live bridge models")
    parser.add_argument("--preserve-secret-values", action="store_true")
    parser.add_argument("--print-json", action="store_true")
    parser.add_argument("--apply", action="store_true")
    parser.set_defaults(home=home)
    return parser.parse_args()


def load_base_config(args: argparse.Namespace) -> dict[str, Any]:
    if args.no_base:
        return {}
    if args.base_config:
        return read_json_object(args.base_config)

    base_config_lib = resolve_base_config_lib(args)
    provider_path = active_provider_path(base_config_lib)
    if provider_path and provider_path.exists():
        return read_json_object(provider_path)
    return {}


def resolve_base_config_lib(args: argparse.Namespace) -> Path:
    if args.base_config_lib:
        return args.base_config_lib
    if args.base_profile_dir:
        return args.base_profile_dir / "configLibrary"
    if args.base_profile and args.base_profile != "default":
        return args.home / ".claude-instances" / args.base_profile / "configLibrary"
    return args.home / "Library/Application Support/Claude-3p/configLibrary"


def resolve_config_lib(args: argparse.Namespace) -> Path:
    if args.config_lib:
        return args.config_lib
    if args.profile_dir:
        return args.profile_dir / "configLibrary"
    if args.profile and args.profile != "default":
        return args.home / ".claude-instances" / args.profile / "configLibrary"
    return args.home / "Library/Application Support/Claude-3p/configLibrary"


def active_provider_path(config_lib: Path) -> Path | None:
    applied_id = read_applied_id(config_lib / "_meta.json")
    if not applied_id:
        return None
    return config_lib / f"{applied_id}.json"


def read_applied_id(meta_path: Path) -> str | None:
    if not meta_path.exists():
        return None
    meta = read_json_object(meta_path)
    applied_id = meta.get("appliedId")
    return str(applied_id) if applied_id else None


def load_spec(path: Path) -> dict[str, Any]:
    return read_json_object(path)


def build_config(
    args: argparse.Namespace,
    spec: dict[str, Any],
    base_config: dict[str, Any],
    inference_models: list[dict[str, Any]],
) -> dict[str, Any]:
    config = dict(base_config)
    if not args.preserve_secret_values:
        for key in SENSITIVE_KEYS:
            config.pop(key, None)

    gateway = dict(spec.get("gateway") or {})
    features = dict(spec.get("features") or {})
    telemetry = dict(spec.get("telemetry") or {})
    source = dict(spec.get("source") or {})

    config.update(
        {
            "inferenceProvider": cli_or_spec(args.provider, spec.get("inferenceProvider"), config.get("inferenceProvider"), "gateway"),
            "inferenceCredentialKind": cli_or_spec(args.credential_kind, gateway.get("credentialKind"), config.get("inferenceCredentialKind"), "static"),
            "inferenceGatewayBaseUrl": normalize_base_url(
                cli_or_spec(args.bridge_base_url, gateway.get("baseUrl"), config.get("inferenceGatewayBaseUrl"), DEFAULT_BRIDGE_BASE_URL)
            ),
            "inferenceGatewayApiKey": cli_or_spec(
                args.gateway_api_key,
                gateway.get("apiKey"),
                config.get("inferenceGatewayApiKey") if args.preserve_secret_values else None,
                DEFAULT_GATEWAY_API_KEY,
            ),
            "inferenceGatewayAuthScheme": cli_or_spec(args.gateway_auth_scheme, gateway.get("authScheme"), config.get("inferenceGatewayAuthScheme"), DEFAULT_GATEWAY_AUTH_SCHEME),
            "modelDiscoveryEnabled": parse_bool(cli_or_spec(args.model_discovery, spec.get("modelDiscoveryEnabled"), config.get("modelDiscoveryEnabled"), False)),
            "isDesktopExtensionEnabled": parse_bool(features.get("desktopExtensionsEnabled", config.get("isDesktopExtensionEnabled", True))),
            "chatTabEnabled": parse_bool(features.get("chatTabEnabled", config.get("chatTabEnabled", True))),
            "chatAdvancedFileAnalysisEnabled": parse_bool(features.get("chatAdvancedFileAnalysisEnabled", config.get("chatAdvancedFileAnalysisEnabled", True))),
            "autoModeEnabled": parse_bool(features.get("autoModeEnabled", config.get("autoModeEnabled", True))),
            "toolSearchEnabled": parse_bool(features.get("toolSearchEnabled", config.get("toolSearchEnabled", True))),
            "disableEssentialTelemetry": parse_bool(telemetry.get("disableEssential", config.get("disableEssentialTelemetry", True))),
            "disableNonessentialTelemetry": parse_bool(telemetry.get("disableNonessential", config.get("disableNonessentialTelemetry", True))),
            "coworkEgressAllowedHosts": resolve_egress_hosts(args, spec, config),
            "inferenceModels": inference_models,
        }
    )

    custom_headers = cli_or_spec(gateway.get("customHeaders"), gateway.get("headers"), config.get("inferenceCustomHeaders"), None)
    if custom_headers is not None:
        config["inferenceCustomHeaders"] = custom_headers

    oidc = cli_or_spec(gateway.get("oidc"), config.get("inferenceGatewayOidc"), None)
    if oidc is not None:
        config["inferenceGatewayOidc"] = oidc

    session_lifetime = cli_or_spec(gateway.get("sessionLifetimeSec"), config.get("inferenceSessionLifetimeSec"), None)
    if session_lifetime is not None:
        config["inferenceSessionLifetimeSec"] = session_lifetime

    deployment_uuid = cli_or_spec(args.deployment_organization_uuid, source.get("deploymentOrganizationUuid"), config.get("deploymentOrganizationUuid"), None)
    if deployment_uuid:
        config["deploymentOrganizationUuid"] = deployment_uuid

    chooser = cli_or_spec(args.disable_deployment_mode_chooser, source.get("disableDeploymentModeChooser"), config.get("disableDeploymentModeChooser"), None)
    if chooser is not None:
        config["disableDeploymentModeChooser"] = parse_bool(chooser)

    for key, value in dict(spec.get("extra") or {}).items():
        config[key] = value

    return order_config(config)


def resolve_inference_models(
    args: argparse.Namespace,
    spec: dict[str, Any],
    base_config: dict[str, Any],
) -> list[dict[str, Any]]:
    explicit_models = spec.get("inferenceModels")
    if isinstance(explicit_models, list):
        return normalize_inference_models(explicit_models)

    source = args.models_source or spec.get("modelsSource") or "bridge-config"
    if source == "none":
        return []
    if source == "base":
        return normalize_inference_models(list(base_config.get("inferenceModels") or []))
    if source == "file":
        if not args.models_file:
            raise SystemExit("error: --models-source file requires --models-file")
        return normalize_models_payload(read_json_object(args.models_file))
    if source == "bridge-live":
        url = args.models_url or spec.get("modelsUrl") or f"{DEFAULT_BRIDGE_BASE_URL}/v1/models"
        return normalize_models_payload(fetch_json(url, args.api_key, args.api_key_header))
    if source == "bridge-config":
        bridge_config = read_json_object(args.bridge_config)
        aliases = bridge_config.get("claudeDesktopModels")
        if not isinstance(aliases, list):
            raise SystemExit(f"error: claudeDesktopModels missing from {args.bridge_config}")
        return normalize_inference_models(aliases)
    raise SystemExit(f"error: unsupported models source: {source}")


def normalize_models_payload(payload: dict[str, Any]) -> list[dict[str, Any]]:
    if isinstance(payload.get("inferenceModels"), list):
        return normalize_inference_models(payload["inferenceModels"])
    items = payload.get("data") or payload.get("models") or payload.get("items") or []
    return normalize_inference_models(items)


def normalize_inference_models(models: list[Any]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    seen: set[str] = set()
    for model in models:
        if not isinstance(model, dict):
            continue
        name = first_string(model.get("name"), model.get("id"), model.get("model"))
        if not name or name in seen:
            continue
        seen.add(name)
        next_model: dict[str, Any] = {"name": name}
        for key in (
            "labelOverride",
            "anthropicFamilyTier",
            "isFamilyDefault",
            "supports1m",
            "prefer1m",
            "displayName",
            "description",
        ):
            if key in model:
                next_model[key] = model[key]
        normalized.append(next_model)
    return normalized


def validate_config(config: dict[str, Any]) -> None:
    required = [
        "inferenceProvider",
        "inferenceGatewayBaseUrl",
        "inferenceGatewayApiKey",
        "inferenceGatewayAuthScheme",
        "inferenceCredentialKind",
        "inferenceModels",
    ]
    missing = [key for key in required if key not in config]
    if missing:
        raise SystemExit("error: generated config missing required keys: " + ", ".join(missing))
    if config["inferenceProvider"] == "gateway" and not str(config["inferenceGatewayBaseUrl"]).startswith(("http://", "https://")):
        raise SystemExit("error: inferenceGatewayBaseUrl must be http(s)")
    if not isinstance(config["inferenceModels"], list):
        raise SystemExit("error: inferenceModels must be a list")
    names = [model.get("name") for model in config["inferenceModels"] if isinstance(model, dict)]
    if len(names) != len(set(names)):
        raise SystemExit("error: duplicate inferenceModels names generated")


def resolve_egress_hosts(args: argparse.Namespace, spec: dict[str, Any], config: dict[str, Any]) -> list[str]:
    if args.egress_host is not None:
        return args.egress_host
    if "coworkEgressAllowedHosts" in spec:
        return list(spec["coworkEgressAllowedHosts"] or [])
    if "egressAllowedHosts" in spec:
        return list(spec["egressAllowedHosts"] or [])
    if isinstance(config.get("coworkEgressAllowedHosts"), list):
        return list(config["coworkEgressAllowedHosts"])
    if args.no_egress_wildcard:
        return []
    return ["*"]


def fetch_json(url: str, api_key: str | None, api_key_header: str) -> dict[str, Any]:
    request = urllib.request.Request(url)
    if api_key:
        request.add_header(api_key_header, api_key)
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as error:
        raise SystemExit(f"error: failed to fetch models from {url}: {error}") from error


def order_config(config: dict[str, Any]) -> dict[str, Any]:
    preferred_order = [
        "deploymentOrganizationUuid",
        "disableDeploymentModeChooser",
        "inferenceProvider",
        "inferenceCredentialKind",
        "inferenceGatewayBaseUrl",
        "inferenceGatewayApiKey",
        "inferenceGatewayAuthScheme",
        "modelDiscoveryEnabled",
        "inferenceModels",
        "coworkEgressAllowedHosts",
        "isDesktopExtensionEnabled",
        "chatTabEnabled",
        "chatAdvancedFileAnalysisEnabled",
        "autoModeEnabled",
        "toolSearchEnabled",
        "disableEssentialTelemetry",
        "disableNonessentialTelemetry",
    ]
    ordered = {key: config[key] for key in preferred_order if key in config}
    for key in sorted(config):
        if key not in ordered:
            ordered[key] = config[key]
    return ordered


def normalize_base_url(value: Any) -> str:
    text = str(value).strip()
    return text or DEFAULT_BRIDGE_BASE_URL


def parse_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


def cli_or_spec(*values: Any) -> Any:
    for value in values:
        if value is not None:
            return value
    return None


def first_string(*values: Any) -> str | None:
    for value in values:
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def read_json_object(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise SystemExit(f"error: file not found: {path}") from error
    except json.JSONDecodeError as error:
        raise SystemExit(f"error: invalid JSON in {path}: {error}") from error
    if not isinstance(payload, dict):
        raise SystemExit(f"error: expected JSON object in {path}")
    return payload


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def backup_if_exists(path: Path) -> None:
    if not path.exists():
        return
    stamp = time.strftime("%Y%m%d-%H%M%S")
    shutil.copy2(path, path.with_suffix(path.suffix + f".bak-generate-{stamp}"))


def redact_config(config: dict[str, Any]) -> dict[str, Any]:
    redacted = dict(config)
    for key in SENSITIVE_KEYS:
        if key in redacted:
            redacted[key] = "<redacted>"
    return redacted


def print_summary(config_lib: Path, config_id: str, name: str, config: dict[str, Any]) -> None:
    print(f"target configLibrary: {config_lib}")
    print(f"config id:            {config_id}")
    print(f"config name:          {name}")
    print(f"provider:             {config.get('inferenceProvider')}")
    print(f"gateway URL:          {config.get('inferenceGatewayBaseUrl')}")
    print(f"auth scheme:          {config.get('inferenceGatewayAuthScheme')}")
    print(f"model discovery:      {config.get('modelDiscoveryEnabled')}")
    print(f"inference models:     {len(config.get('inferenceModels') or [])}")


if __name__ == "__main__":
    raise SystemExit(main())
