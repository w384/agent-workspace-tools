import importlib
from pathlib import Path

from fastapi.testclient import TestClient


def _create_client(
    workspace_root: Path,
    *,
    api_key: str,
) -> TestClient:
    main_module = importlib.import_module("service.app.main")
    application = main_module.create_app(
        workspace_root,
        api_key=api_key,
    )
    return TestClient(application)


def test_health_is_public_and_files_require_api_key(
    tmp_path: Path,
):
    """健康检查公开，文件接口必须验证 API Key。"""
    workspace_root = tmp_path / "workspace"
    workspace_root.mkdir()
    client = _create_client(
        workspace_root,
        api_key="test-secret",
    )

    health_response = client.get("/health")
    missing_key_response = client.get("/files")
    wrong_key_response = client.get(
        "/files",
        headers={"X-API-Key": "wrong-secret"},
    )
    authorized_response = client.get(
        "/files",
        headers={"X-API-Key": "test-secret"},
    )

    assert health_response.status_code == 200
    assert missing_key_response.status_code == 401
    assert missing_key_response.json() == {
        "error": {
            "code": "unauthorized",
            "message": "API Key 无效或缺失",
        }
    }
    assert wrong_key_response.status_code == 401
    assert wrong_key_response.json() == missing_key_response.json()
    assert authorized_response.status_code == 200
    assert authorized_response.json() == {
        "total": 0,
        "page": 1,
        "page_size": 10,
        "has_more": False,
        "files": [],
    }


def test_protected_routes_are_unavailable_without_configured_key(
    tmp_path: Path,
):
    """服务端未配置 API Key 时，受保护接口必须拒绝访问。"""
    workspace_root = tmp_path / "workspace"
    workspace_root.mkdir()
    client = _create_client(workspace_root, api_key="")

    response = client.get(
        "/files",
        headers={"X-API-Key": "anything"},
    )

    assert response.status_code == 503
    assert response.json() == {
        "error": {
            "code": "api_key_not_configured",
            "message": "服务尚未配置 API Key",
        }
    }


def test_unexpected_permission_error_does_not_leak_local_path(
    tmp_path: Path,
    monkeypatch,
):
    """操作系统权限异常必须作为 500 隐藏本机绝对路径。"""
    main_module = importlib.import_module("service.app.main")
    workspace_root = tmp_path / "workspace"
    workspace_root.mkdir()
    secret_path = r"D:\private\secret.txt"

    def raise_permission_error(*_args, **_kwargs):
        raise PermissionError(f"拒绝访问：{secret_path}")

    monkeypatch.setattr(
        main_module,
        "execute_plan",
        raise_permission_error,
    )
    client = TestClient(
        main_module.create_app(
            workspace_root,
            api_key="test-secret",
        ),
        raise_server_exceptions=False,
    )

    response = client.post(
        "/plans/00000000-0000-0000-0000-000000000000/execute",
        json={
            "approval_token": "token",
            "plan_hash": "sha256:test",
        },
        headers={"X-API-Key": "test-secret"},
    )

    assert response.status_code == 500
    assert secret_path not in response.text
