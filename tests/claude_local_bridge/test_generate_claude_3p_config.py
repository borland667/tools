import json
import subprocess
import sys
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
    assert config["builtinToolPolicy"] == {"*": "allow"}
    assert config["disabledBuiltinTools"] == []
    assert config["disableBundledSkills"] is False
    assert config["orgPluginSettings"] == {
        "mcpServers": {"*": {"toolPolicy": {"*": "allow"}}}
    }
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


def write_json(path, payload):
    path.write_text(json.dumps(payload, indent=2) + "\n")


def read_json(path):
    return json.loads(path.read_text())
