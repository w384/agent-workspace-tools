from pathlib import Path
from typing import Any

import pytest
import yaml
from dify_plugin.entities.tool import ToolInvokeMessage

from internal.client import WorkspaceClient
from tools.get_file import GetFileTool
from tools.list_files import ListFilesTool
from tools.search_files import SearchFilesTool


PLUGIN_ROOT = Path(__file__).resolve().parents[1]


class RecordingWorkspaceClient(WorkspaceClient):
    def __init__(self, responses: list[dict[str, Any]] | None = None) -> None:
        super().__init__("http://service", "key")
        self.calls: list[tuple[str, str, dict[str, Any]]] = []
        self.responses = list(responses or [])

    def request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        self.calls.append((method, path, kwargs))
        return self.responses.pop(0) if self.responses else {}


def _tool(tool_class: type, client: RecordingWorkspaceClient):
    tool = tool_class.__new__(tool_class)
    tool.response_type = ToolInvokeMessage
    tool._workspace_client = lambda: client
    return tool


def _text(messages: list[Any]) -> str:
    return "\n".join(
        message.message.text
        for message in messages
        if message.type.value == "text"
    )


def _json(messages: list[Any]) -> dict[str, Any]:
    json_messages = [
        message.message.json_object
        for message in messages
        if message.type.value == "json"
    ]
    assert len(json_messages) == 1
    return dict(json_messages[0])


def _variables(messages: list[Any]) -> dict[str, Any]:
    return {
        message.message.variable_name: message.message.variable_value
        for message in messages
        if message.type.value == "variable"
    }


def _file_page() -> dict[str, Any]:
    return {
        "total": 1,
        "page": 1,
        "page_size": 10,
        "has_more": False,
        "files": [
            {
                "path": "contracts/合同.txt",
                "name": "合同.txt",
                "extension": ".txt",
                "size_bytes": 128,
                "modified_at": "2026-08-11T01:02:03+00:00",
            }
        ],
    }


def test_client_read_wrappers_use_expected_endpoints_and_parameters() -> None:
    client = RecordingWorkspaceClient([{}, {}, {}])

    client.list_files(2, 7)
    client.search_files("合同", 3, 4)
    client.get_file("contracts/合同.txt")

    assert client.calls == [
        ("GET", "/files", {"params": {"page": 2, "page_size": 7}}),
        (
            "GET",
            "/files/search",
            {"params": {"query": "合同", "page": 3, "page_size": 4}},
        ),
        (
            "GET",
            "/files/content",
            {"params": {"path": "contracts/合同.txt"}},
        ),
    ]


def test_list_files_yields_text_json_and_all_declared_variables() -> None:
    result = _file_page()
    client = RecordingWorkspaceClient([result])
    tool = _tool(ListFilesTool, client)

    messages = list(tool._invoke({"page": 1, "page_size": 10}))

    assert client.calls == [
        ("GET", "/files", {"params": {"page": 1, "page_size": 10}})
    ]
    assert "合同.txt" in _text(messages)
    assert _json(messages) == result
    assert _variables(messages) == result


def test_search_files_yields_results_and_uses_trimmed_nonblank_query() -> None:
    result = _file_page()
    client = RecordingWorkspaceClient([result])
    tool = _tool(SearchFilesTool, client)

    messages = list(
        tool._invoke({"query": "  合同  ", "page": 1, "page_size": 10})
    )

    assert client.calls == [
        (
            "GET",
            "/files/search",
            {"params": {"query": "合同", "page": 1, "page_size": 10}},
        )
    ]
    assert "合同.txt" in _text(messages)
    assert _json(messages) == result
    assert _variables(messages) == result


def test_search_files_rejects_blank_query_before_calling_service() -> None:
    client = RecordingWorkspaceClient()
    tool = _tool(SearchFilesTool, client)

    with pytest.raises(ValueError, match="搜索关键词不能为空"):
        list(tool._invoke({"query": "   ", "page": 1, "page_size": 10}))

    assert client.calls == []


@pytest.mark.parametrize(
    ("result", "expected_text"),
    [
        (
            {
                "path": "notes.txt",
                "name": "notes.txt",
                "extension": ".txt",
                "size_bytes": 5,
                "modified_at": "2026-08-11T01:02:03+00:00",
                "content_available": True,
                "content_base64": "aGVsbG8=",
            },
            "内容已作为 Base64 返回",
        ),
        (
            {
                "path": "large.bin",
                "name": "large.bin",
                "extension": ".bin",
                "size_bytes": 15 * 1024 * 1024 + 1,
                "modified_at": "2026-08-11T01:02:03+00:00",
                "content_available": False,
                "content_base64": None,
            },
            "超过 15MB，已仅返回元数据",
        ),
    ],
)
def test_get_file_yields_text_json_and_all_declared_variables(
    result: dict[str, Any],
    expected_text: str,
) -> None:
    client = RecordingWorkspaceClient([result])
    tool = _tool(GetFileTool, client)

    messages = list(tool._invoke({"path": result["path"]}))

    assert client.calls == [
        (
            "GET",
            "/files/content",
            {"params": {"path": result["path"]}},
        )
    ]
    assert expected_text in _text(messages)
    assert _json(messages) == result
    assert _variables(messages) == result


def test_read_tool_yaml_declares_real_outputs_limits_and_registration() -> None:
    provider = yaml.safe_load(
        (PLUGIN_ROOT / "provider" / "workspace.yaml").read_text(encoding="utf-8")
    )
    assert provider["tools"][:3] == [
        "tools/list_files.yaml",
        "tools/search_files.yaml",
        "tools/get_file.yaml",
    ]

    expected_outputs = {
        "list_files": {"total", "page", "page_size", "has_more", "files"},
        "search_files": {"total", "page", "page_size", "has_more", "files"},
        "get_file": {
            "path",
            "name",
            "extension",
            "size_bytes",
            "modified_at",
            "content_available",
            "content_base64",
        },
    }
    for tool_name, output_names in expected_outputs.items():
        configuration = yaml.safe_load(
            (PLUGIN_ROOT / "tools" / f"{tool_name}.yaml").read_text(
                encoding="utf-8"
            )
        )
        assert set(configuration["output_schema"]["properties"]) == output_names
        parameters = {
            parameter["name"]: parameter
            for parameter in configuration.get("parameters", [])
        }
        if "page_size" in parameters:
            assert parameters["page_size"]["max"] == 10
