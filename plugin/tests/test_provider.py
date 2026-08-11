import traceback
from unittest.mock import Mock

import pytest
import requests
from dify_plugin.errors.tool import ToolProviderCredentialValidationError

from internal.client import WorkspaceClient
from provider import workspace as workspace_module
from provider.workspace import WorkspaceProvider


def test_provider_validates_credentials_against_protected_files_endpoint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, str, dict[str, object]]] = []

    class FakeWorkspaceClient:
        def __init__(self, base_url: str, api_key: str) -> None:
            assert base_url == "http://service"
            assert api_key == "key"

        def request(
            self,
            method: str,
            path: str,
            **kwargs: object,
        ) -> dict[str, object]:
            calls.append((method, path, kwargs))
            return {"total": 0}

    monkeypatch.setattr(workspace_module, "WorkspaceClient", FakeWorkspaceClient)

    WorkspaceProvider._validate_credentials(
        None,
        {"service_url": "http://service", "api_key": "key"},
    )

    assert calls == [
        ("GET", "/files", {"params": {"page": 1, "page_size": 1}})
    ]


def test_provider_converts_401_without_leaking_api_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api_key = "do-not-leak"
    session = Mock(spec=requests.Session)
    response = Mock()
    response.status_code = 401
    response.json.return_value = {
        "error": {
            "code": "unauthorized",
            "message": f"Invalid API key: {api_key}",
        }
    }
    session.request.return_value = response

    def build_client(base_url: str, provided_key: str) -> WorkspaceClient:
        return WorkspaceClient(base_url, provided_key, session=session)

    monkeypatch.setattr(workspace_module, "WorkspaceClient", build_client)

    with pytest.raises(ToolProviderCredentialValidationError) as caught:
        WorkspaceProvider._validate_credentials(
            None,
            {"service_url": "http://service", "api_key": api_key},
        )

    assert "本机文件服务凭据验证失败" in str(caught.value)
    assert api_key not in str(caught.value)
    assert session.request.call_args.kwargs["url"] == "http://service/files"


def test_provider_does_not_chain_sensitive_transport_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api_key = "do-not-leak"
    absolute_path = r"\\server\share\private.txt"

    class LeakyWorkspaceClient:
        def __init__(self, base_url: str, provided_key: str) -> None:
            assert base_url == "http://service"
            assert provided_key == api_key

        def request(self, method: str, path: str, **kwargs: object) -> None:
            raise requests.ConnectionError(
                f"transport used {api_key} at {absolute_path}"
            )

    monkeypatch.setattr(workspace_module, "WorkspaceClient", LeakyWorkspaceClient)

    with pytest.raises(ToolProviderCredentialValidationError) as caught:
        WorkspaceProvider._validate_credentials(
            None,
            {"service_url": "http://service", "api_key": api_key},
        )

    formatted_error = "".join(traceback.format_exception(caught.value))
    assert api_key not in str(caught.value)
    assert absolute_path not in str(caught.value)
    assert api_key not in formatted_error
    assert absolute_path not in formatted_error
