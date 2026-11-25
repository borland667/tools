import json
import subprocess
import sys
import threading
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "claude_local_bridge" / "generate_claude_3p_config.py"


def test_generate_config_from_bridge_aliases(tmp_path):
    base_lib = tmp_path / "base" / "configLibrary"
    target_lib = tmp_path / "target" / "configLibrary"
    bridge_config = tmp_path / "bridge.local.json"
    spec = tmp_path / "spec.json"
    base_lib.mkdir(parents=True)

    write_json(base_lib / "_meta.json", {
        "appliedId": "base-config",
        "entries": [{"id": "base-config", "name": "Base"}],
    })
    write_json(base_lib / "base-config.json", {
        "inferenceGatewayBaseUrl": "http://localhost:1245/",
        "inferenceGatewayApiKey": "test-placeholder-key",
        "inferenceGatewayAuthScheme": "x-api-key",
        "inferenceProvider": "gateway",
        "inferenceCredentialKind": "static",
        "modelDiscoveryEnabled": True,
        "inferenceModels": [{"name": "claude-sonnet-4-5"}],
        "coworkEgressAllowedHosts": ["*"],
        "toolSearchEnabled": False,
    })
    write_json(bridge_config, {
        "claudeDesktopModels": [
            {
                "name": "claude-sonnet-4-5",
                "target": "omlx/sushi",
                "labelOverride": "Sushi via Local Bridge",
                "anthropicFamilyTier": "sonnet",
                "toolCapable": True,
                "isFamilyDefault": True,
            },
            {
                "name": "claude-sonnet-4-6",
                "target": "omlx/heretic",
                "labelOverride": "Heretic via Local Bridge",
                "anthropicFamilyTier": "sonnet",
                "toolCapable": True,
                "visionCapable": True,
                "isFamilyDefault": False,
            },
        ],
    })
    write_json(spec, {
        "name": "Generated Local",
        "configId": "generated-config",
        "gateway": {
            "baseUrl": "http://127.0.0.1:1245",
            "apiKey": "local-bridge",
            "authScheme": "x-api-key",
        },
        "modelDiscoveryEnabled": False,
        "features": {"toolSearchEnabled": True},
        "workspace": {
            "allowedWorkspaceFolders": [{"path": "/", "isDefaultSelected": True}],
            "builtinToolPolicy": {"*": "allow"},
        },
        "connectors": {
            "localDevMcpEnabled": True,
            "mcpPersistentAlwaysAllowEnabled": True,
            "managedMcpServers": [],
        },
        "plugins": {
            "allowedPluginMarketplaces": [
                {
                    "source": "github",
                    "repo": "anthropics/knowledge-work-plugins",
                    "installationPreference": "available",
                    "credentialKind": "anonymous",
                }
            ],
            "orgPluginSettings": {
                "mcpServers": {"*": {"toolPolicy": {"*": "allow"}}}
            },
        },
    })

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--base-config-lib",
            str(base_lib),
            "--config-lib",
            str(target_lib),
            "--bridge-config",
            str(bridge_config),
            "--spec",
            str(spec),
            "--apply",
            "--print-json",
        ],
        check=True,
        text=True,
        capture_output=True,
    )

    assert "Generated Local" in result.stdout
    assert "<redacted>" in result.stdout

    meta = read_json(target_lib / "_meta.json")
    config = read_json(target_lib / "generated-config.json")
    assert meta == {
        "appliedId": "generated-config",
        "entries": [{"id": "generated-config", "name": "Generated Local"}],
    }
    assert config["inferenceGatewayBaseUrl"] == "http://127.0.0.1:1245"
    assert config["inferenceGatewayApiKey"] == "local-bridge"
    assert config["modelDiscoveryEnabled"] is False
    assert config["toolSearchEnabled"] is True
    assert config["isDesktopExtensionEnabled"] is True
    assert config["isDesktopExtensionSignatureRequired"] is False
    assert config["isLocalDevMcpEnabled"] is True
    assert config["mcpPersistentAlwaysAllowEnabled"] is True
    assert config["managedMcpServers"] == []
    assert config["coworkEgressAllowedHosts"] == ["*"]
    assert config["allowedWorkspaceFolders"] == [{"path": "/", "isDefaultSelected": True}]
    # Claude Desktop rejects both shapes, so the generator drops them with a warning.
    assert "builtinToolPolicy" not in config
    assert "orgPluginSettings" not in config
    assert "builtinToolPolicy: kept only built-in tool names" in result.stderr
    assert "orgPluginSettings: dropped" in result.stderr
    assert config["disabledBuiltinTools"] == []
    assert config["disableBundledSkills"] is False
    assert config["allowedPluginMarketplaces"] == [
        {
            "source": "github",
            "repo": "anthropics/knowledge-work-plugins",
            "installationPreference": "available",
            "credentialKind": "anonymous",
        }
    ]
    assert config["inferenceModels"] == [
        {
            "name": "claude-sonnet-4-5",
            "labelOverride": "Sushi via Local Bridge",
            "anthropicFamilyTier": "sonnet",
            "isFamilyDefault": True,
        },
        {
            "name": "claude-sonnet-4-6",
            "labelOverride": "Heretic via Local Bridge",
            "anthropicFamilyTier": "sonnet",
            "isFamilyDefault": False,
        },
    ]


def test_dry_run_does_not_write_target_files(tmp_path):
    base_config = tmp_path / "base.json"
    target_lib = tmp_path / "target" / "configLibrary"
    models_file = tmp_path / "models.json"
    write_json(base_config, {
        "inferenceProvider": "gateway",
        "inferenceGatewayBaseUrl": "http://localhost:1245/",
        "inferenceGatewayApiKey": "test-placeholder-key",
        "inferenceGatewayAuthScheme": "x-api-key",
        "inferenceCredentialKind": "static",
        "inferenceModels": [{"name": "old-model"}],
    })
    write_json(models_file, {"data": [{"id": "claude-sonnet-4-5", "owned_by": "omlx"}]})

    subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--base-config",
            str(base_config),
            "--config-lib",
            str(target_lib),
            "--models-source",
            "file",
            "--models-file",
            str(models_file),
        ],
        check=True,
        text=True,
        capture_output=True,
    )

    assert not target_lib.exists()


def test_bridge_live_models_are_schema_clean_and_keep_tiers(tmp_path):
    payload = {
        "object": "list",
        "data": [
            {"id": "claude-auto-routing", "owned_by": "bridge", "label": "Auto Routing",
             "description": "Routes chat, tool, and image requests."},
            {"id": "claude-opus-5-404289", "owned_by": "aggregator", "label": "gateway: Claude Opus 5.5",
             "description": "gateway source model: anthropic/claude-opus-5-5"},
            {"id": "claude-opus-5-111111", "owned_by": "aggregator", "label": "gateway: GPT 5",
             "description": "gateway source model: gpt-5"},
            {"id": "claude-haiku-5-222222", "owned_by": "omlx", "label": "OMLX: Qwen3.8 9B"},
            {"id": "claude-omlx-gemma-e4b", "owned_by": "omlx", "label": "OMLX: Gemma 4 E4B"},
            {"id": "claude-omlx-e4b", "owned_by": "omlx", "label": "OMLX: Gemma 4 E4B"},
            {"id": "omlx/gemma-4-e4b-it-4bit", "owned_by": "omlx"},
        ],
    }
    bridge_config = tmp_path / "bridge.local.json"
    write_json(bridge_config, {
        "claudeDesktopModels": [
            {"name": "claude-opus-5-404289", "target": "aggregator/anthropic/claude-opus-5-5",
             "anthropicFamilyTier": "opus", "isFamilyDefault": True},
            {"name": "claude-opus-5-111111", "target": "aggregator/gpt-5",
             "anthropicFamilyTier": "opus", "isFamilyDefault": True},
        ],
    })
    target_lib = tmp_path / "target" / "configLibrary"

    with serve_json(payload) as url:
        result = subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "--no-base",
                "--config-lib",
                str(target_lib),
                "--config-id",
                "live",
                "--bridge-config",
                str(bridge_config),
                "--models-source",
                "bridge-live",
                "--models-url",
                url,
                "--apply",
            ],
            check=True,
            text=True,
            capture_output=True,
        )

    config = read_json(target_lib / "live.json")
    assert config["inferenceModels"] == [
        {"name": "claude-auto-routing", "labelOverride": "Auto Routing"},
        {"name": "claude-opus-5-404289", "labelOverride": "gateway: Claude Opus 5.5",
         "anthropicFamilyTier": "opus", "isFamilyDefault": True},
        {"name": "claude-opus-5-111111", "labelOverride": "gateway: GPT 5",
         "anthropicFamilyTier": "opus", "isFamilyDefault": False},
        {"name": "claude-haiku-5-222222", "labelOverride": "OMLX: Qwen3.8 9B",
         "anthropicFamilyTier": "haiku"},
        {"name": "claude-omlx-e4b", "labelOverride": "OMLX: Gemma 4 E4B"},
    ]
    assert "skipped inferenceModels name 'claude-omlx-gemma-e4b'" in result.stderr
    assert "builtinToolPolicy" not in config
    assert "orgPluginSettings" not in config


@contextmanager
def serve_json(payload):
    body = json.dumps(payload).encode()

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header("content-type", "application/json")
            self.send_header("content-length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format, *args):
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}/v1/models"
    finally:
        server.shutdown()
        server.server_close()


def write_json(path, payload):
    path.write_text(json.dumps(payload, indent=2) + "\n")


def read_json(path):
    return json.loads(path.read_text())
