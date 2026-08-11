from pathlib import Path

import yaml
from dify_plugin.entities.tool import ToolProviderConfiguration


def test_workspace_provider_yaml_matches_installed_sdk(
    monkeypatch,
) -> None:
    plugin_root = Path(__file__).resolve().parents[1]
    provider_file = plugin_root / "provider" / "workspace.yaml"

    provider_data = yaml.safe_load(
        provider_file.read_text(encoding="utf-8")
    )

    monkeypatch.chdir(plugin_root)

    configuration = ToolProviderConfiguration.model_validate(
        provider_data
    )

    assert {
        credential.name
        for credential in configuration.credentials_schema
    } == {
        "service_url",
        "api_key",
    }