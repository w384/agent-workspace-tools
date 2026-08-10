import importlib
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

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
        json={"approval_token": token},
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
        json={"approval_token": token},
        headers=_headers(),
    )
    assert repeated_response.status_code == 409


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
                json={"approval_token": token},
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
        json={"approval_token": token},
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
        json={"approval_token": restore_token},
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
