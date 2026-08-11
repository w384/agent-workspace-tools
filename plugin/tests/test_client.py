import traceback
from unittest.mock import Mock

import pytest
import requests

from plugin.internal.client import (
    WorkspaceClient,
    WorkspaceServiceError,
    WorkspaceTimeoutError,
)


def _response(status_code: int, payload: dict[str, object]) -> Mock:
    response = Mock()
    response.status_code = status_code
    response.json.return_value = payload
    return response


def test_request_normalizes_url_and_adds_api_key_header() -> None:
    session = Mock(spec=requests.Session)
    session.request.return_value = _response(200, {"total": 0})
    client = WorkspaceClient(
        "http://host.docker.internal:8787/",
        "do-not-leak",
        session=session,
    )

    result = client.request("GET", "/files", params={"page": 1})

    assert result["total"] == 0
    assert session.request.call_args.kwargs == {
        "method": "GET",
        "url": "http://host.docker.internal:8787/files",
        "headers": {"X-API-Key": "do-not-leak"},
        "timeout": 15.0,
        "params": {"page": 1},
    }


def test_get_retries_twice_before_returning_success() -> None:
    session = Mock(spec=requests.Session)
    session.request.side_effect = [
        requests.Timeout("first timeout"),
        requests.Timeout("second timeout"),
        _response(200, {"total": 0}),
    ]
    client = WorkspaceClient("http://service", "key", session=session)

    result = client.request("get", "/files")

    assert result == {"total": 0}
    assert session.request.call_count == 3


def test_post_is_not_retried_and_timeout_is_sanitized() -> None:
    api_key = "do-not-leak"
    absolute_path = r"D:\AI\AgentWorkspace\private.txt"
    session = Mock(spec=requests.Session)
    session.request.side_effect = requests.Timeout(
        f"request with {api_key} failed while reading {absolute_path}"
    )
    client = WorkspaceClient(
        "http://host.docker.internal:8787",
        api_key,
        timeout_seconds=2.5,
        session=session,
    )

    with pytest.raises(WorkspaceTimeoutError) as caught:
        client.request("POST", "/plans")

    assert caught.value.code == "service_timeout"
    assert caught.value.status_code is None
    assert str(caught.value) == "本机文件服务响应超时"
    assert api_key not in str(caught.value)
    assert absolute_path not in str(caught.value)
    formatted_error = "".join(traceback.format_exception(caught.value))
    assert api_key not in formatted_error
    assert absolute_path not in formatted_error
    assert session.request.call_count == 1
    assert session.request.call_args.kwargs["timeout"] == 2.5


def test_get_timeout_stops_after_three_attempts() -> None:
    session = Mock(spec=requests.Session)
    session.request.side_effect = requests.Timeout("timed out")
    client = WorkspaceClient("http://service", "key", session=session)

    with pytest.raises(WorkspaceTimeoutError):
        client.request("GET", "/files")

    assert session.request.call_count == 3


def test_invalid_json_becomes_structured_service_error() -> None:
    session = Mock(spec=requests.Session)
    response = Mock()
    response.status_code = 502
    response.json.side_effect = ValueError(r"bad JSON at D:\private\response.json")
    session.request.return_value = response
    client = WorkspaceClient("http://service", "key", session=session)

    with pytest.raises(WorkspaceServiceError) as caught:
        client.request("GET", "/files")

    assert caught.value.code == "invalid_service_response"
    assert caught.value.status_code == 502
    assert str(caught.value) == "本机文件服务返回了无法解析的响应"
    assert r"D:\private\response.json" not in "".join(
        traceback.format_exception(caught.value)
    )


def test_service_error_parses_code_and_sanitizes_sensitive_message() -> None:
    api_key = "do-not-leak"
    absolute_path = r"D:\AI\AgentWorkspace\secrets.json"
    session = Mock(spec=requests.Session)
    session.request.return_value = _response(
        401,
        {
            "error": {
                "code": "unauthorized",
                "message": f"Invalid {api_key} loaded from {absolute_path}",
            }
        },
    )
    client = WorkspaceClient("http://service", api_key, session=session)

    with pytest.raises(WorkspaceServiceError) as caught:
        client.request("GET", "/files")

    assert caught.value.code == "unauthorized"
    assert caught.value.status_code == 401
    assert str(caught.value) == "本机文件服务请求失败"
    assert api_key not in str(caught.value)
    assert absolute_path not in str(caught.value)
