import importlib
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient


API_KEY = "test-secret"


def _create_client(workspace_root: Path) -> TestClient:
    main_module = importlib.import_module("service.app.main")
    application = main_module.create_app(
        workspace_root,
        api_key=API_KEY,
    )
    return TestClient(application)


def test_cleanup_endpoint_removes_only_expired_operation(
    tmp_path: Path,
):
    """维护接口必须删除过期日志及其回收目录。"""
    logs_module = importlib.import_module(
        "service.app.operation_logs"
    )
    workspace_root = tmp_path / "workspace"
    workspace_root.mkdir()
    expired_operation_id = str(uuid4())
    active_operation_id = str(uuid4())
    now = datetime.now(timezone.utc)

    for operation_id, expires_at in (
        (expired_operation_id, now - timedelta(seconds=1)),
        (active_operation_id, now + timedelta(days=14)),
    ):
        logs_module.write_operation_log_record(
            workspace_root,
            {
                "operation_id": operation_id,
                "plan_id": operation_id,
                "status": "completed",
                "completed_at": now.isoformat(),
                "expires_at": expires_at.isoformat(),
                "file_count": 1,
                "undo_actions": [],
            },
        )
        trash_directory = (
            workspace_root / ".trash" / operation_id
        )
        trash_directory.mkdir(parents=True)
        (trash_directory / "file.txt").write_bytes(b"content")

    client = _create_client(workspace_root)
    response = client.post(
        "/maintenance/cleanup-expired-operations",
        headers={"X-API-Key": API_KEY},
    )

    assert response.status_code == 200
    assert response.json() == {
        "removed_operation_ids": [expired_operation_id]
    }
    assert not (
        workspace_root
        / ".file-manager"
        / "operations"
        / f"{expired_operation_id}.json"
    ).exists()
    assert not (
        workspace_root / ".trash" / expired_operation_id
    ).exists()
    assert (
        workspace_root
        / ".file-manager"
        / "operations"
        / f"{active_operation_id}.json"
    ).is_file()
    assert (
        workspace_root / ".trash" / active_operation_id
    ).is_dir()


def test_all_business_routes_reject_missing_api_key(
    tmp_path: Path,
):
    """除健康检查外，全部业务接口都必须要求 API Key。"""
    workspace_root = tmp_path / "workspace"
    workspace_root.mkdir()
    client = _create_client(workspace_root)
    resource_id = str(uuid4())

    responses = [
        client.get("/files"),
        client.get("/files/search", params={"query": "x"}),
        client.get(
            "/files/content",
            params={"path": "x.txt"},
        ),
        client.post(
            "/files/upload",
            data={"directory": ""},
            files={"file": ("x.txt", b"x", "text/plain")},
        ),
        client.post("/plans", json={"operations": []}),
        client.get(f"/plans/{resource_id}"),
        client.post(f"/plans/{resource_id}/approval-token"),
        client.post(
            f"/plans/{resource_id}/execute",
            json={
                "approval_token": "token",
                "plan_hash": "sha256:test",
            },
        ),
        client.get(f"/operations/{resource_id}"),
        client.post(
            f"/operations/{resource_id}/restore-plans"
        ),
        client.post(
            f"/plans/{resource_id}/restore",
            json={
                "approval_token": "token",
                "plan_hash": "sha256:test",
            },
        ),
        client.post(
            "/maintenance/cleanup-expired-operations"
        ),
    ]

    assert [response.status_code for response in responses] == [
        401
    ] * len(responses)
    for response in responses:
        assert response.json() == {
            "error": {
                "code": "unauthorized",
                "message": "API Key 无效或缺失",
            }
        }
