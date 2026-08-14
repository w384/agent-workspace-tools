import importlib
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient


API_KEY = "test-secret"


def _create_application(workspace_root: Path):
    main_module = importlib.import_module("service.app.main")
    return main_module.create_app(
        workspace_root,
        api_key=API_KEY,
    )


def _headers() -> dict[str, str]:
    return {"X-API-Key": API_KEY}


def _create_plan(
    client: TestClient,
    operations: list[dict[str, str]],
) -> dict:
    response = client.post(
        "/plans",
        json={"operations": operations},
        headers=_headers(),
    )
    assert response.status_code == 201
    return response.json()


def _issue_token(client: TestClient, plan_id: str) -> str:
    response = client.post(
        f"/plans/{plan_id}/approval-token",
        headers=_headers(),
    )
    assert response.status_code == 200
    return response.json()["approval_token"]


def test_get_plan_status_returns_safe_projection(
    tmp_path: Path,
):
    workspace_root = tmp_path / "workspace"
    workspace_root.mkdir()
    (workspace_root / "notes.txt").write_bytes(b"hello")
    client = TestClient(_create_application(workspace_root))
    plan = _create_plan(
        client,
        [{
            "action": "move_rename",
            "source": "notes.txt",
            "destination": "archive/notes.txt",
        }],
    )

    response = client.get(
        f"/plans/{plan['plan_id']}",
        headers=_headers(),
    )

    assert response.status_code == 200
    assert response.json()["status"] == "pending_confirmation"
    assert "operations" not in response.json()


def test_get_plan_status_returns_plan_not_found(
    tmp_path: Path,
):
    workspace_root = tmp_path / "workspace"
    workspace_root.mkdir()
    client = TestClient(_create_application(workspace_root))

    response = client.get(
        f"/plans/{uuid4()}",
        headers=_headers(),
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "plan_not_found"


def test_execute_plan_and_read_operation_log_endpoints(
    tmp_path: Path,
):
    """API 必须执行已确认计划，并能读取对应操作日志。"""
    workspace_root = tmp_path / "workspace"
    incoming_directory = workspace_root / "incoming"
    incoming_directory.mkdir(parents=True)
    (incoming_directory / "notes.txt").write_bytes(b"hello")
    client = TestClient(_create_application(workspace_root))
    plan = _create_plan(
        client,
        [
            {
                "action": "move_rename",
                "source": "incoming/notes.txt",
                "destination": "notes.txt",
            }
        ],
    )
    token = _issue_token(client, plan["plan_id"])

    execute_response = client.post(
        f"/plans/{plan['plan_id']}/execute",
        json={"approval_token": token, "plan_hash": plan["plan_hash"]},
        headers=_headers(),
    )

    assert execute_response.status_code == 200
    executed_plan = execute_response.json()
    assert executed_plan["status"] == "completed"
    assert (workspace_root / "notes.txt").read_bytes() == b"hello"
    assert not (incoming_directory / "notes.txt").exists()

    log_response = client.get(
        f"/operations/{executed_plan['operation_id']}",
        headers=_headers(),
    )
    assert log_response.status_code == 200
    operation_log = log_response.json()
    assert operation_log["status"] == "completed"
    assert operation_log["file_count"] == 1
    assert operation_log["undo_actions"] == [
        {
            "action": "move",
            "source": "notes.txt",
            "destination": "incoming/notes.txt",
        }
    ]

    repeated_response = client.post(
        f"/plans/{plan['plan_id']}/execute",
        json={"approval_token": token, "plan_hash": plan["plan_hash"]},
        headers=_headers(),
    )
    assert repeated_response.status_code == 409


def test_execute_plan_rejects_operations_outside_user_permissions(
    tmp_path: Path,
):
    """执行阶段必须再次校验当前用户权限，不能复用创建者权限。"""
    from service.app.permissions import (
        add_path_prefix,
        initialize_database,
        upsert_employee,
    )

    workspace_root = tmp_path / "workspace"
    workspace_root.mkdir()
    source_file = workspace_root / "notes.txt"
    source_file.write_bytes(b"hello")

    permissions_db = tmp_path / "permissions.db"
    initialize_database(permissions_db)
    upsert_employee(
        permissions_db,
        user_id="owner-user",
        email="owner@example.com",
        business_unit="unit",
        department="department",
        position="owner",
        enabled=True,
    )
    add_path_prefix(
        permissions_db,
        user_id="owner-user",
        path_prefix="",
    )
    upsert_employee(
        permissions_db,
        user_id="member-user",
        email="member@example.com",
        business_unit="unit",
        department="department",
        position="member",
        enabled=True,
    )
    add_path_prefix(
        permissions_db,
        user_id="member-user",
        path_prefix="organized",
    )

    main_module = importlib.import_module("service.app.main")
    client = TestClient(
        main_module.create_app(
            workspace_root,
            api_key=API_KEY,
            permissions_database=permissions_db,
        )
    )
    plan_response = client.post(
        "/plans",
        params={"user_id": "owner-user"},
        json={
            "operations": [
                {
                    "action": "move_rename",
                    "source": "notes.txt",
                    "destination": "renamed-notes.txt",
                }
            ]
        },
        headers=_headers(),
    )
    assert plan_response.status_code == 201
    plan = plan_response.json()
    plan_id = plan["plan_id"]
    token = _issue_token(client, plan_id)

    response = client.post(
        f"/plans/{plan_id}/execute",
        params={"user_id": "member-user"},
        json={"approval_token": token, "plan_hash": plan["plan_hash"]},
        headers=_headers(),
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "path_not_allowed"
    assert source_file.is_file()
    retry_response = client.post(
        f"/plans/{plan_id}/execute",
        params={"user_id": "owner-user"},
        json={"approval_token": token, "plan_hash": plan["plan_hash"]},
        headers=_headers(),
    )
    assert retry_response.status_code == 200


def test_execute_endpoint_rejects_wrong_token_without_consuming_it(
    tmp_path: Path,
):
    """错误令牌返回 403，并且不能消耗正确令牌。"""
    workspace_root = tmp_path / "workspace"
    workspace_root.mkdir()
    (workspace_root / "notes.txt").write_bytes(b"hello")
    client = TestClient(_create_application(workspace_root))
    plan = _create_plan(
        client,
        [
            {
                "action": "move_rename",
                "source": "notes.txt",
                "destination": "sorted-notes.txt",
            }
        ],
    )
    token = _issue_token(client, plan["plan_id"])

    wrong_response = client.post(
        f"/plans/{plan['plan_id']}/execute",
        json={
            "approval_token": "wrong-token",
            "plan_hash": plan["plan_hash"],
        },
        headers=_headers(),
    )

    assert wrong_response.status_code == 403
    assert wrong_response.json()["error"]["code"] == (
        "invalid_approval_token"
    )
    assert (workspace_root / "notes.txt").is_file()

    correct_response = client.post(
        f"/plans/{plan['plan_id']}/execute",
        json={"approval_token": token, "plan_hash": plan["plan_hash"]},
        headers=_headers(),
    )
    assert correct_response.status_code == 200
    assert (workspace_root / "sorted-notes.txt").is_file()


@pytest.mark.parametrize(
    ("request_json", "expected_status", "expected_code"),
    [
        ({"approval_token": "{token}"}, 422, None),
        (
            {
                "approval_token": "{token}",
                "plan_hash": "sha256:" + "b" * 64,
            },
            400,
            "plan_integrity",
        ),
    ],
)
def test_execute_endpoint_rejects_missing_or_wrong_plan_hash_without_consuming_token(
    tmp_path: Path,
    request_json: dict[str, str],
    expected_status: int,
    expected_code: str | None,
):
    workspace_root = tmp_path / "workspace"
    workspace_root.mkdir()
    source_file = workspace_root / "notes.txt"
    source_file.write_bytes(b"hello")
    client = TestClient(_create_application(workspace_root))
    plan = _create_plan(
        client,
        [
            {
                "action": "move_rename",
                "source": "notes.txt",
                "destination": "sorted-notes.txt",
            }
        ],
    )
    token = _issue_token(client, plan["plan_id"])
    payload = {
        key: token if value == "{token}" else value
        for key, value in request_json.items()
    }

    rejected_response = client.post(
        f"/plans/{plan['plan_id']}/execute",
        json=payload,
        headers=_headers(),
    )

    assert rejected_response.status_code == expected_status
    if expected_code is not None:
        assert rejected_response.json()["error"]["code"] == expected_code
    assert source_file.is_file()

    retry_response = client.post(
        f"/plans/{plan['plan_id']}/execute",
        json={"approval_token": token, "plan_hash": plan["plan_hash"]},
        headers=_headers(),
    )
    assert retry_response.status_code == 200
    assert (workspace_root / "sorted-notes.txt").is_file()


def test_execute_endpoint_consumes_token_once_under_concurrency(
    tmp_path: Path,
):
    """并发请求使用同一令牌时，只能有一个请求执行成功。"""
    workspace_root = tmp_path / "workspace"
    incoming_directory = workspace_root / "incoming"
    incoming_directory.mkdir(parents=True)
    (incoming_directory / "notes.txt").write_bytes(b"hello")
    application = _create_application(workspace_root)
    setup_client = TestClient(application)
    plan = _create_plan(
        setup_client,
        [
            {
                "action": "move_rename",
                "source": "incoming/notes.txt",
                "destination": "notes.txt",
            }
        ],
    )
    token = _issue_token(setup_client, plan["plan_id"])

    def execute_once() -> tuple[int, dict]:
        with TestClient(application) as client:
            response = client.post(
                f"/plans/{plan['plan_id']}/execute",
                json={
                    "approval_token": token,
                    "plan_hash": plan["plan_hash"],
                },
                headers=_headers(),
            )
            return response.status_code, response.json()

    with ThreadPoolExecutor(max_workers=6) as executor:
        responses = list(
            executor.map(lambda _index: execute_once(), range(6))
        )

    status_codes = [status_code for status_code, _body in responses]
    assert status_codes.count(200) == 1, responses
    assert status_codes.count(409) == 5, responses
    assert (workspace_root / "notes.txt").read_bytes() == b"hello"


def test_restore_operation_endpoints_restore_actual_file(
    tmp_path: Path,
):
    """恢复计划经二次确认后必须实际恢复原文件。"""
    workspace_root = tmp_path / "workspace"
    workspace_root.mkdir()
    source_file = workspace_root / "old-notes.txt"
    source_file.write_bytes(b"restore me")
    client = TestClient(_create_application(workspace_root))
    plan = _create_plan(
        client,
        [
            {
                "action": "trash",
                "source": "old-notes.txt",
            }
        ],
    )
    token = _issue_token(client, plan["plan_id"])
    execute_response = client.post(
        f"/plans/{plan['plan_id']}/execute",
        json={"approval_token": token, "plan_hash": plan["plan_hash"]},
        headers=_headers(),
    )
    operation_id = execute_response.json()["operation_id"]
    assert not source_file.exists()

    restore_plan_response = client.post(
        f"/operations/{operation_id}/restore-plans",
        headers=_headers(),
    )
    assert restore_plan_response.status_code == 201
    restore_plan = restore_plan_response.json()
    assert restore_plan["plan_type"] == "restore"
    assert restore_plan["status"] == "pending_confirmation"

    restore_token = _issue_token(client, restore_plan["plan_id"])
    restore_response = client.post(
        f"/plans/{restore_plan['plan_id']}/restore",
        json={
            "approval_token": restore_token,
            "plan_hash": restore_plan["plan_hash"],
        },
        headers=_headers(),
    )

    assert restore_response.status_code == 200
    assert restore_response.json()["status"] == "completed"
    assert source_file.read_bytes() == b"restore me"
    log_response = client.get(
        f"/operations/{operation_id}",
        headers=_headers(),
    )
    assert log_response.json()["status"] == "restored"
