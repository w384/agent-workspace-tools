from typing import Any

from internal.client import WorkspaceClient
from dify_plugin.entities.tool import ToolInvokeMessage
from tools.upload_file import UploadFileTool


class RecordingWorkspaceClient(WorkspaceClient):
    def __init__(self) -> None:
        super().__init__("http://service", "key")
        self.calls: list[tuple[str, str, dict[str, Any]]] = []

    def request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        self.calls.append((method, path, kwargs))
        return {
            "path": "incoming/report.txt",
            "size_bytes": 5,
        }


def test_upload_file_client_uses_multipart_request() -> None:
    client = RecordingWorkspaceClient()

    result = client.upload_file(
        directory="incoming",
        file_name="report.txt",
        content=b"hello",
        mime_type="text/plain",
    )

    assert result == {
        "path": "incoming/report.txt",
        "size_bytes": 5,
    }
    assert client.calls == [
        (
            "POST",
            "/files/upload",
            {
                "data": {"directory": "incoming"},
                "params": None,
                "files": {
                    "file": ("report.txt", b"hello", "text/plain")
                },
            },
        )
    ]


def test_upload_file_client_passes_runtime_user_id() -> None:
    client = RecordingWorkspaceClient()

    client.upload_file(
        directory="organized",
        file_name="report.txt",
        content=b"hello",
        mime_type="text/plain",
        user_id="member-user",
    )

    assert client.calls[0][2]["params"] == {"user_id": "member-user"}


def test_upload_file_tool_emits_safe_result_after_upload() -> None:
    client = RecordingWorkspaceClient()
    tool = UploadFileTool.__new__(UploadFileTool)
    tool.response_type = ToolInvokeMessage
    tool._workspace_client = lambda: client

    messages = list(
        tool._invoke(
            {
                "file": {
                    "name": "report.txt",
                    "content": b"hello",
                    "mime_type": "text/plain",
                },
                "directory": "incoming",
            }
        )
    )

    assert client.calls[0][1] == "/files/upload"
    assert any(
        message.type.value == "json"
        and message.message.json_object == {
            "path": "incoming/report.txt",
            "size_bytes": 5,
        }
        for message in messages
    )
