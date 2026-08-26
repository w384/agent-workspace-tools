"""Recovery / escalation HTTP 层测试。

验证失败（MISMATCH）经 HTTP 端点的完整闭环：
  1. confirm_plan 触发验证失败 -> 422 verification_failed，并附带最新 pending
     recovery_task（details.recovery_task）；
  2. GET /api/recovery-tasks 列出该 workspace 的 pending 恢复任务；
  3. POST /api/recovery-tasks/{id}/resolve（recovered / escalated）-> task/plan
     状态更新 + 审计留痕；
  4. 边界：未知 recovery_id -> 404；非法 decision -> 409。
"""

from control_plane.app.verification import ControlledDirectoryVerifier
from conftest import AsgiClient


EXPIRES_AT = "2099-01-01T00:00:00+08:00"


def _make_app(repository, file_executor, rag_port, demo_identities, tmp_path):
    from control_plane.app.main import create_app

    return create_app(
        repository=repository,
        file_executor=file_executor,
        rag_port=rag_port,
        demo_identities=demo_identities,
        internal_service_key="demo-internal-key",
        approver_role_id="role-approver-demo",
        verification_port=ControlledDirectoryVerifier(tmp_path),
    )


def _login(client: AsgiClient, username: str, password: str) -> AsgiClient:
    response = client.post(
        "/api/session/login",
        json_body={"username": username, "password": password},
    )
    assert response.status_code == 200
    return client


def _upload_and_activate(client: AsgiClient, repository) -> str:
    """Upload report.txt via HTTP then walk the version state machine to ready."""
    response = client.post(
        "/api/uploads",
        data={"directory": "organized"},
        files={"file": ("report.txt", b"http recovery content 2026", "text/plain")},
    )
    assert response.status_code == 200
    version_id = response.json()["asset_version"]["asset_version_id"]
    for state in ("parsing", "indexed", "ready"):
        repository.transition_asset_version(version_id, state)
    repository.activate_asset_version(version_id)
    return version_id


def _create_upload_plan(client: AsgiClient) -> dict[str, object]:
    response = client.post(
        "/api/plans",
        json_body={
            "operations": [
                {
                    "operation_id": "op-upload-1",
                    "type": "upload",
                    "source_path": "organized/report.txt",
                }
            ],
            "expires_at": EXPIRES_AT,
        },
    )
    assert response.status_code == 200
    return response.json()["plan"]


def test_confirm_verification_failed_returns_422_with_recovery_task(
    repository, file_executor, rag_port, demo_identities, tmp_path
) -> None:
    client = _login(
        AsgiClient(_make_app(repository, file_executor, rag_port, demo_identities, tmp_path)),
        "alice",
        "demo-a-password",
    )
    _upload_and_activate(client, repository)
    plan = _create_upload_plan(client)

    response = client.post(
        f"/api/plans/{plan['plan_id']}/confirm",
        json_body={"expected_plan_hash": plan["plan_hash"]},
        headers={"Idempotency-Key": "idem-http-rec-1"},
    )

    assert response.status_code == 422
    payload = response.json()
    assert payload["error"]["code"] == "verification_failed"
    recovery = payload["error"]["details"]["recovery_task"]
    assert recovery["plan_id"] == plan["plan_id"]
    assert recovery["state"] == "pending"
    assert recovery["strategy"] == "retry_compensation"
    assert recovery["reason"] == "readback_fingerprint_mismatch"
    assert recovery["resolved_at"] is None


def test_list_and_resolve_recovery_task_recovered_over_http(
    repository, file_executor, rag_port, demo_identities, tmp_path
) -> None:
    client = _login(
        AsgiClient(_make_app(repository, file_executor, rag_port, demo_identities, tmp_path)),
        "alice",
        "demo-a-password",
    )
    _upload_and_activate(client, repository)
    plan = _create_upload_plan(client)
    client.post(
        f"/api/plans/{plan['plan_id']}/confirm",
        json_body={"expected_plan_hash": plan["plan_hash"]},
        headers={"Idempotency-Key": "idem-http-rec-2"},
    )

    listed = client.get("/api/recovery-tasks")
    assert listed.status_code == 200
    tasks = listed.json()["tasks"]
    assert len(tasks) == 1
    assert tasks[0]["state"] == "pending"
    recovery_id = tasks[0]["recovery_id"]

    resolved = client.post(
        f"/api/recovery-tasks/{recovery_id}/resolve",
        json_body={"decision": "recovered"},
    )
    assert resolved.status_code == 200
    outcome = resolved.json()
    assert outcome["task"]["state"] == "recovered"
    assert outcome["task"]["resolved_by"] == "user-a"
    assert outcome["plan"]["state"] == "recovered"

    events = [
        event
        for event in repository.list_audit_events()
        if event.event_type in {"recovery_task_created", "recovery_resolved"}
    ]
    assert {event.event_type for event in events} == {
        "recovery_task_created",
        "recovery_resolved",
    }


def test_resolve_recovery_task_escalated_over_http(
    repository, file_executor, rag_port, demo_identities, tmp_path
) -> None:
    client = _login(
        AsgiClient(_make_app(repository, file_executor, rag_port, demo_identities, tmp_path)),
        "alice",
        "demo-a-password",
    )
    _upload_and_activate(client, repository)
    plan = _create_upload_plan(client)
    client.post(
        f"/api/plans/{plan['plan_id']}/confirm",
        json_body={"expected_plan_hash": plan["plan_hash"]},
        headers={"Idempotency-Key": "idem-http-rec-3"},
    )

    recovery_id = client.get("/api/recovery-tasks").json()["tasks"][0]["recovery_id"]
    resolved = client.post(
        f"/api/recovery-tasks/{recovery_id}/resolve",
        json_body={"decision": "escalated"},
    )
    assert resolved.status_code == 200
    outcome = resolved.json()
    assert outcome["task"]["state"] == "escalated"
    assert outcome["plan"]["state"] == "escalated"

    events = [
        event
        for event in repository.list_audit_events()
        if event.event_type in {"recovery_task_created", "recovery_escalated"}
    ]
    assert {event.event_type for event in events} == {
        "recovery_task_created",
        "recovery_escalated",
    }


def test_resolve_recovery_task_boundaries_over_http(
    repository, file_executor, rag_port, demo_identities, tmp_path
) -> None:
    client = _login(
        AsgiClient(_make_app(repository, file_executor, rag_port, demo_identities, tmp_path)),
        "alice",
        "demo-a-password",
    )
    _upload_and_activate(client, repository)
    plan = _create_upload_plan(client)
    client.post(
        f"/api/plans/{plan['plan_id']}/confirm",
        json_body={"expected_plan_hash": plan["plan_hash"]},
        headers={"Idempotency-Key": "idem-http-rec-4"},
    )
    recovery_id = client.get("/api/recovery-tasks").json()["tasks"][0]["recovery_id"]

    missing = client.post(
        "/api/recovery-tasks/recovery-does-not-exist/resolve",
        json_body={"decision": "recovered"},
    )
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "recovery_task_not_found"

    invalid = client.post(
        f"/api/recovery-tasks/{recovery_id}/resolve",
        json_body={"decision": "whatever"},
    )
    assert invalid.status_code == 409
    assert invalid.json()["error"]["code"] == "recovery_task_state_error"
