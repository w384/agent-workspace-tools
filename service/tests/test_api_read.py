import base64
import importlib
from pathlib import Path

from fastapi.testclient import TestClient


def _create_client(workspace_root: Path) -> TestClient:
    main_module = importlib.import_module("service.app.main")
    application = main_module.create_app(
        workspace_root,
        api_key="test-secret",
    )
    return TestClient(application)


def _authorized_headers() -> dict[str, str]:
    return {"X-API-Key": "test-secret"}


def test_search_files_endpoint_returns_matching_files(
    tmp_path: Path,
):
    """搜索接口必须返回名称匹配的文件并保留分页信息。"""
    workspace_root = tmp_path / "workspace"
    workspace_root.mkdir()
    (workspace_root / "report-2026.txt").write_text(
        "annual report",
        encoding="utf-8",
    )
    (workspace_root / "notes.txt").write_text(
        "meeting notes",
        encoding="utf-8",
    )
    client = _create_client(workspace_root)

    response = client.get(
        "/files/search",
        params={
            "query": "report",
            "page": 1,
            "page_size": 10,
        },
        headers=_authorized_headers(),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["has_more"] is False
    assert [item["path"] for item in body["files"]] == [
        "report-2026.txt"
    ]


def test_get_file_endpoint_returns_base64_content(
    tmp_path: Path,
):
    """小文件内容必须通过 Base64 安全返回。"""
    workspace_root = tmp_path / "workspace"
    workspace_root.mkdir()
    content = "你好，Dify".encode("utf-8")
    (workspace_root / "notes.txt").write_bytes(content)
    client = _create_client(workspace_root)

    response = client.get(
        "/files/content",
        params={"path": "notes.txt"},
        headers=_authorized_headers(),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["path"] == "notes.txt"
    assert body["content_available"] is True
    assert body["content_base64"] == base64.b64encode(
        content
    ).decode("ascii")


def test_get_file_endpoint_does_not_read_large_file(
    tmp_path: Path,
):
    """超过 15MB 的文件只能通过 API 返回元数据。"""
    workspace_root = tmp_path / "workspace"
    workspace_root.mkdir()
    target_file = workspace_root / "large.bin"
    with target_file.open("wb") as file_handle:
        file_handle.truncate(15 * 1024 * 1024 + 1)
    client = _create_client(workspace_root)

    response = client.get(
        "/files/content",
        params={"path": "large.bin"},
        headers=_authorized_headers(),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["path"] == "large.bin"
    assert body["size_bytes"] == 15 * 1024 * 1024 + 1
    assert body["content_available"] is False
    assert body["content_base64"] is None
