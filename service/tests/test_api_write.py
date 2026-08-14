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


def test_upload_file_endpoint_saves_without_overwrite(
    tmp_path: Path,
):
    """上传接口必须保存文件，并拒绝覆盖已有文件。"""
    workspace_root = tmp_path / "workspace"
    workspace_root.mkdir()
    client = _create_client(workspace_root)

    response = client.post(
        "/files/upload",
        data={"directory": "incoming"},
        files={
            "file": (
                "notes.txt",
                b"hello",
                "text/plain",
            )
        },
        headers=_authorized_headers(),
    )

    assert response.status_code == 201
    assert response.json() == {
        "path": "incoming/notes.txt",
        "name": "notes.txt",
        "size_bytes": 5,
        "content_fingerprint": (
            "sha256:2cf24dba5fb0a30e26e83b2ac5b9e29e"
            "1b161e5c1fa7425e73043362938b9824"
        ),
    }
    assert (
        workspace_root / "incoming" / "notes.txt"
    ).read_bytes() == b"hello"

    duplicate_response = client.post(
        "/files/upload",
        data={"directory": "incoming"},
        files={
            "file": (
                "notes.txt",
                b"replacement",
                "text/plain",
            )
        },
        headers=_authorized_headers(),
    )

    assert duplicate_response.status_code == 409
    assert duplicate_response.json()["error"]["code"] == (
        "file_already_exists"
    )
    assert (
        workspace_root / "incoming" / "notes.txt"
    ).read_bytes() == b"hello"


def test_create_plan_endpoint_only_previews_operations(
    tmp_path: Path,
):
    """创建计划接口只能生成确认摘要，不能移动文件。"""
    workspace_root = tmp_path / "workspace"
    incoming_directory = workspace_root / "incoming"
    incoming_directory.mkdir(parents=True)
    source_file = incoming_directory / "notes.txt"
    source_file.write_bytes(b"hello")
    client = _create_client(workspace_root)

    response = client.post(
        "/plans",
        json={
            "operations": [
                {
                    "action": "create_folder",
                    "destination": "sorted",
                },
                {
                    "action": "move_rename",
                    "source": "incoming/notes.txt",
                    "destination": "sorted/notes.txt",
                },
            ]
        },
        headers=_authorized_headers(),
    )

    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "pending_confirmation"
    assert body["file_count"] == 1
    assert body["confirmation"]["folders_to_create"] == [
        "sorted"
    ]
    assert source_file.is_file()
    assert not (workspace_root / "sorted").exists()


def test_issue_approval_token_endpoint_returns_plaintext_once(
    tmp_path: Path,
):
    """确认令牌只在签发响应中返回一次，磁盘仅保存哈希。"""
    workspace_root = tmp_path / "workspace"
    incoming_directory = workspace_root / "incoming"
    incoming_directory.mkdir(parents=True)
    (incoming_directory / "notes.txt").write_bytes(b"hello")
    client = _create_client(workspace_root)
    plan_response = client.post(
        "/plans",
        json={
            "operations": [
                {
                    "action": "move_rename",
                    "source": "incoming/notes.txt",
                    "destination": "notes.txt",
                }
            ]
        },
        headers=_authorized_headers(),
    )
    plan_id = plan_response.json()["plan_id"]

    token_response = client.post(
        f"/plans/{plan_id}/approval-token",
        headers=_authorized_headers(),
    )

    assert token_response.status_code == 200
    approval_token = token_response.json()["approval_token"]
    assert isinstance(approval_token, str)
    assert len(approval_token) >= 32
    stored_plan = (
        workspace_root
        / ".file-manager"
        / "plans"
        / f"{plan_id}.json"
    ).read_text(encoding="utf-8")
    assert approval_token not in stored_plan
    assert "approval_token_hash" in stored_plan

    repeated_response = client.post(
        f"/plans/{plan_id}/approval-token",
        headers=_authorized_headers(),
    )
    assert repeated_response.status_code == 409
    assert repeated_response.json()["error"]["code"] == (
        "plan_state"
    )
def test_create_plan_rejects_destination_outside_user_permissions(
    tmp_path: Path,
):
    """创建计划时必须拒绝超出用户授权前缀的目标路径。"""
    from service.app.permissions import (
        add_path_prefix,
        initialize_database,
        upsert_employee,
    )

    workspace_root = tmp_path / "workspace"
    workspace_root.mkdir()
    (workspace_root / "source.txt").write_text(
        "source",
        encoding="utf-8",
    )

    permissions_db = tmp_path / "permissions.db"
    initialize_database(permissions_db)
    upsert_employee(
        permissions_db,
        user_id="user-1",
        email="user-1@example.com",
        business_unit="事业部A",
        department="部门A",
        position="岗位A",
        enabled=True,
    )
    add_path_prefix(
        permissions_db,
        user_id="user-1",
        path_prefix="1",
    )

    main_module = importlib.import_module("service.app.main")
    application = main_module.create_app(
        workspace_root,
        api_key="test-secret",
        permissions_database=permissions_db,
    )
    client = TestClient(application)

    response = client.post(
        "/plans",
        params={"user_id": "user-1"},
        json={
            "operations": [
                {
                    "action": "move_rename",
                    "source": "source.txt",
                    "destination": "outside/source.txt",
                }
            ]
        },
        headers=_authorized_headers(),
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "path_not_allowed"


def test_upload_rejects_directory_outside_user_permissions(
    tmp_path: Path,
):
    from service.app.permissions import (
        add_path_prefix,
        initialize_database,
        upsert_employee,
    )

    workspace_root = tmp_path / "workspace"
    workspace_root.mkdir()
    permissions_db = tmp_path / "permissions.db"
    initialize_database(permissions_db)
    upsert_employee(
        permissions_db,
        user_id="user-1",
        email="user-1@example.com",
        business_unit="unit",
        department="department",
        position="member",
        enabled=True,
    )
    add_path_prefix(
        permissions_db,
        user_id="user-1",
        path_prefix="organized",
    )

    main_module = importlib.import_module("service.app.main")
    client = TestClient(
        main_module.create_app(
            workspace_root,
            api_key="test-secret",
            permissions_database=permissions_db,
        )
    )
    response = client.post(
        "/files/upload",
        params={"user_id": "user-1"},
        files={"file": ("notes.txt", b"hello", "text/plain")},
        data={"directory": ""},
        headers=_authorized_headers(),
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "path_not_allowed"
