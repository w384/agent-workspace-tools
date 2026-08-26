"""审批通过后的验证失败 HTTP 层测试（decide_approval → 422 闭环）。

覆盖：高风险破坏性操作（TRASH）经「创建计划 → 确认 → 审批通过 → 执行 →
独立读回验证失败」全链路；decide_approval 在验证失败时返回 422
verification_failed，并附带最新 pending recovery_task（reason=trash_readback_failed）。
同时验证审计留痕（approval_approved + execution_verification_failed +
recovery_task_created）。
"""

from conftest import AsgiClient
from test_recovery_http import (
    EXPIRES_AT,
    _login,
    _make_app,
    _upload_and_activate,
)


def _add_trash_grant(repository) -> None:
    from control_plane.app.domain import Action, PermissionGrant, PrincipalType

    repository.add_permission_grant(
        PermissionGrant(
            grant_id="user-a-trash",
            workspace_id="workspace-a",
            context_version="acl_2026_08_13",
            principal_type=PrincipalType.USER,
            principal_id="user-a",
            action=Action.TRASH,
            path_prefix="organized",
        )
    )


def _create_trash_plan(client: AsgiClient) -> dict[str, object]:
    response = client.post(
        "/api/plans",
        json_body={
            "operations": [
                {
                    "operation_id": "op-trash-1",
                    "type": "trash",
                    "source_path": "organized/report.txt",
                }
            ],
            "expires_at": EXPIRES_AT,
        },
    )
    assert response.status_code == 200
    return response.json()["plan"]


def test_decide_approval_verification_failed_returns_422_with_recovery_task(
    repository, file_executor, rag_port, demo_identities, tmp_path
) -> None:
    app = _make_app(repository, file_executor, rag_port, demo_identities, tmp_path)
    _add_trash_grant(repository)
    alice = _login(AsgiClient(app), "alice", "demo-a-password")
    _upload_and_activate(alice, repository)
    # RecordingFileExecutor 不会写盘：手动落盘让 verifier 能读回「文件仍存在」
    target = tmp_path / "organized" / "report.txt"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(b"http trash approval recovery content 2026")

    plan = _create_trash_plan(alice)
    assert plan["decision_state"] == "APPROVAL_REQUIRED"

    confirmed = alice.post(
        f"/api/plans/{plan['plan_id']}/confirm",
        json_body={"expected_plan_hash": plan["plan_hash"]},
        headers={"Idempotency-Key": "idem-http-approval-1"},
    )
    assert confirmed.status_code == 200
    approval_id = confirmed.json()["approval"]["approval_id"]

    bob = _login(AsgiClient(app), "bob", "demo-b-password")
    response = bob.post(
        f"/api/approvals/{approval_id}/decide",
        json_body={"decision": "approved", "expected_plan_hash": plan["plan_hash"]},
        headers={"Idempotency-Key": "idem-http-approval-2"},
    )

    assert response.status_code == 422
    payload = response.json()
    assert payload["error"]["code"] == "verification_failed"
    recovery = payload["error"]["details"]["recovery_task"]
    assert recovery["plan_id"] == plan["plan_id"]
    assert recovery["state"] == "pending"
    assert recovery["strategy"] == "retry_compensation"
    assert recovery["reason"] == "trash_readback_failed"
    assert recovery["resolved_at"] is None

    event_types = {
        event.event_type
        for event in repository.list_audit_events()
        if event.event_type
        in {
            "approval_approved",
            "execution_verification_failed",
            "recovery_task_created",
        }
    }
    assert event_types == {
        "approval_approved",
        "execution_verification_failed",
        "recovery_task_created",
    }