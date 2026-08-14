from control_plane.app.domain import Action, PermissionGrant, PrincipalType
from control_plane.app.main import create_app
from control_plane.app.ports import ExecutionResult
from control_plane.app.sessions import DemoIdentity


def _grant(action: Action, principal_id: str = "user-a", path_prefix: str = "organized"):
    return PermissionGrant(
        grant_id=f"{principal_id}-{action.value}-{path_prefix}",
        workspace_id="workspace-a",
        context_version="acl_2026_08_13",
        principal_type=PrincipalType.USER,
        principal_id=principal_id,
        action=action,
        path_prefix=path_prefix,
    )


def _role_grant(action: Action, role_id: str, path_prefix: str = "organized"):
    return PermissionGrant(
        grant_id=f"{role_id}-{action.value}-{path_prefix}",
        workspace_id="workspace-a",
        context_version="acl_2026_08_13",
        principal_type=PrincipalType.ROLE,
        principal_id=role_id,
        action=action,
        path_prefix=path_prefix,
    )


def _seed_ready_asset(repository):
    asset = repository.get_or_create_asset(
        "workspace-a", "organized/report.txt", "report.txt", "user-a"
    )
    version = repository.create_asset_version(
        asset.asset_id, "sha256:trash-version", "organized/report.txt"
    )
    for state in ("parsing", "indexed", "ready"):
        repository.transition_asset_version(version.asset_version_id, state)
    repository.activate_asset_version(version.asset_version_id)
    return asset, version


def _login(client, username, password):
    response = client.post(
        "/api/session/login",
        json_body={"username": username, "password": password},
    )
    assert response.status_code == 200
    return client


def _create_trash_plan(client):
    response = client.post(
        "/api/plans",
        json_body={
            "operations": [
                {
                    "operation_id": "trash-1",
                    "type": "trash",
                    "source_path": "organized/report.txt",
                }
            ],
            "expires_at": "2099-01-01T00:00:00Z",
        },
    )
    assert response.status_code == 200
    return response.json()


def test_high_risk_creates_pending_approval_only_after_creator_confirms(
    client_as_a, repository, file_executor
) -> None:
    repository.add_permission_grant(_grant(Action.TRASH))
    _seed_ready_asset(repository)

    plan_payload = _create_trash_plan(client_as_a)

    assert plan_payload["decision"]["state"] == "APPROVAL_REQUIRED"
    assert repository.approvals == {}
    assert file_executor.executions == []

    confirmed = client_as_a.post(
        f"/api/plans/{plan_payload['plan']['plan_id']}/confirm",
        headers={"Idempotency-Key": "trash-idem"},
        json_body={"expected_plan_hash": plan_payload["plan"]["plan_hash"]},
    )

    assert confirmed.status_code == 200
    assert confirmed.json()["plan"]["state"] == "pending_approval"
    approvals = list(repository.approvals.values())
    assert len(approvals) == 1
    assert approvals[0].requester_id == "user-a"
    assert approvals[0].required_role_id == "role-approver-demo"
    assert approvals[0].decision == "pending"
    assert file_executor.executions == []

    repeated = client_as_a.post(
        f"/api/plans/{plan_payload['plan']['plan_id']}/confirm",
        headers={"Idempotency-Key": "trash-idem"},
        json_body={"expected_plan_hash": plan_payload["plan"]["plan_hash"]},
    )

    assert repeated.status_code == 200
    assert repeated.json()["approval"]["approval_id"] == approvals[0].approval_id
    assert len(repository.approvals) == 1
    assert file_executor.executions == []


def test_approver_role_id_is_injected_configuration(repository, file_executor, rag_port, client):
    repository.add_permission_grant(_grant(Action.TRASH))
    _seed_ready_asset(repository)
    app = create_app(
        repository=repository,
        file_executor=file_executor,
        rag_port=rag_port,
        demo_identities={
            "alice": DemoIdentity(
                username="alice",
                password="demo-a-password",
                actor_id="user-a",
                workspace_id="workspace-a",
                context_version="acl_2026_08_13",
                role_ids=frozenset({"role-member-demo"}),
            ),
            "bob": DemoIdentity(
                username="bob",
                password="demo-b-password",
                actor_id="user-b",
                workspace_id="workspace-a",
                context_version="acl_2026_08_13",
                role_ids=frozenset({"role-reviewer-demo"}),
            ),
        },
        internal_service_key="demo-internal-key",
        approver_role_id="role-reviewer-demo",
    )
    client.app = app
    _login(client, "alice", "demo-a-password")
    plan_payload = _create_trash_plan(client)

    confirmed = client.post(
        f"/api/plans/{plan_payload['plan']['plan_id']}/confirm",
        headers={"Idempotency-Key": "trash-idem"},
        json_body={"expected_plan_hash": plan_payload["plan"]["plan_hash"]},
    )

    assert confirmed.status_code == 200
    assert confirmed.json()["approval"]["required_role_id"] == "role-reviewer-demo"


def test_configured_non_initiator_approver_executes_after_approval(
    client_as_a, repository, file_executor, client
) -> None:
    repository.add_permission_grant(_grant(Action.TRASH))
    _seed_ready_asset(repository)
    file_executor.execution_result = ExecutionResult(status="completed", operation_id="trash-1")
    plan_payload = _create_trash_plan(client_as_a)
    confirm = client_as_a.post(
        f"/api/plans/{plan_payload['plan']['plan_id']}/confirm",
        headers={"Idempotency-Key": "trash-idem"},
        json_body={"expected_plan_hash": plan_payload["plan"]["plan_hash"]},
    )
    approval_id = confirm.json()["approval"]["approval_id"]

    bob_client = _login(client, "bob", "demo-b-password")
    pending = bob_client.get("/api/approvals/pending")
    decided = bob_client.post(
        f"/api/approvals/{approval_id}/decide",
        headers={"Idempotency-Key": "trash-exec"},
        json_body={
            "decision": "approved",
            "expected_plan_hash": plan_payload["plan"]["plan_hash"],
        },
    )
    repeated = bob_client.post(
        f"/api/approvals/{approval_id}/decide",
        headers={"Idempotency-Key": "trash-exec"},
        json_body={
            "decision": "approved",
            "expected_plan_hash": plan_payload["plan"]["plan_hash"],
        },
    )

    assert pending.status_code == 200
    assert [item["approval_id"] for item in pending.json()["approvals"]] == [approval_id]
    assert decided.status_code == 200
    assert repeated.status_code == 200
    assert decided.json()["execution_job"] == repeated.json()["execution_job"]
    assert decided.json()["execution_job"]["state"] == "completed"
    assert len(file_executor.executions) == 1
    execution = file_executor.executions[0]
    assert execution.actor.actor_id == "user-a"
    assert execution.actor.role_ids == frozenset({"role-member-demo"})
    assert execution.approval_evidence["approver_id"] == "user-b"
    events = repository.list_audit_events()
    assert any(
        event.event_type == "approval_approved" and event.actor_id == "user-b"
        for event in events
    )
    assert any(
        event.event_type == "execution_completed"
        and event.actor_id == "user-a"
        and event.details.get("approval_id") == approval_id
        for event in events
    )


def test_approver_role_grant_cannot_replace_requester_file_grant(
    client_as_a, repository, file_executor, client
) -> None:
    repository.add_permission_grant(_grant(Action.TRASH))
    _seed_ready_asset(repository)
    file_executor.execution_result = ExecutionResult(status="completed", operation_id="trash-1")
    plan_payload = _create_trash_plan(client_as_a)
    confirm = client_as_a.post(
        f"/api/plans/{plan_payload['plan']['plan_id']}/confirm",
        headers={"Idempotency-Key": "trash-idem"},
        json_body={"expected_plan_hash": plan_payload["plan"]["plan_hash"]},
    )
    approval_id = confirm.json()["approval"]["approval_id"]
    repository.permission_grants.clear()
    repository.add_permission_grant(_role_grant(Action.TRASH, "role-approver-demo"))
    bob_client = _login(client, "bob", "demo-b-password")

    response = bob_client.post(
        f"/api/approvals/{approval_id}/decide",
        headers={"Idempotency-Key": "trash-exec"},
        json_body={
            "decision": "approved",
            "expected_plan_hash": plan_payload["plan"]["plan_hash"],
        },
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "plan_revalidation_failed"
    assert file_executor.executions == []
    assert repository.execution_jobs == {}
    events = repository.list_audit_events()
    assert events[-1].event_type == "plan_revalidation_failed"
    assert events[-1].actor_id == "user-b"


def test_same_role_approver_from_another_workspace_cannot_list_or_decide_approval(
    client_as_a, repository, file_executor, client
) -> None:
    repository.add_permission_grant(_grant(Action.TRASH))
    _seed_ready_asset(repository)
    file_executor.execution_result = ExecutionResult(status="completed", operation_id="trash-1")
    plan_payload = _create_trash_plan(client_as_a)
    confirm = client_as_a.post(
        f"/api/plans/{plan_payload['plan']['plan_id']}/confirm",
        headers={"Idempotency-Key": "trash-idem"},
        json_body={"expected_plan_hash": plan_payload["plan"]["plan_hash"]},
    )
    approval_id = confirm.json()["approval"]["approval_id"]
    mallory_client = _login(client, "mallory", "demo-m-password")

    pending = mallory_client.get("/api/approvals/pending")
    decided = mallory_client.post(
        f"/api/approvals/{approval_id}/decide",
        headers={"Idempotency-Key": "trash-cross-workspace"},
        json_body={
            "decision": "approved",
            "expected_plan_hash": plan_payload["plan"]["plan_hash"],
        },
    )

    assert pending.status_code == 200
    assert pending.json() == {"approvals": []}
    assert decided.status_code == 403
    assert decided.json()["error"]["code"] == "approval_forbidden"
    assert file_executor.executions == []
    assert repository.execution_jobs == {}
    approval = repository.get_approval(approval_id)
    assert approval.decision == "pending"
    assert approval.approver_id is None
    events = repository.list_audit_events()
    assert "organized/report.txt" not in repr(events)
    assert "organized/report-renamed.txt" not in repr(events)


def test_initiator_or_actor_without_configured_role_cannot_decide_approval(
    client_as_a, repository, file_executor, client
) -> None:
    repository.add_permission_grant(_grant(Action.TRASH))
    _seed_ready_asset(repository)
    plan_payload = _create_trash_plan(client_as_a)
    confirm = client_as_a.post(
        f"/api/plans/{plan_payload['plan']['plan_id']}/confirm",
        headers={"Idempotency-Key": "trash-idem"},
        json_body={"expected_plan_hash": plan_payload["plan"]["plan_hash"]},
    )
    approval_id = confirm.json()["approval"]["approval_id"]

    self_decision = client_as_a.post(
        f"/api/approvals/{approval_id}/decide",
        headers={"Idempotency-Key": "trash-self"},
        json_body={
            "decision": "approved",
            "expected_plan_hash": plan_payload["plan"]["plan_hash"],
            "role_ids": ["role-approver-demo"],
        },
    )
    carol_client = _login(client, "carol", "demo-c-password")
    no_role_decision = carol_client.post(
        f"/api/approvals/{approval_id}/decide",
        headers={"Idempotency-Key": "trash-carol"},
        json_body={
            "decision": "approved",
            "expected_plan_hash": plan_payload["plan"]["plan_hash"],
        },
    )

    assert self_decision.status_code == 403
    assert no_role_decision.status_code == 403
    assert file_executor.executions == []


def test_rejected_approval_is_terminal_and_never_executes(
    client_as_a, repository, file_executor, client
) -> None:
    repository.add_permission_grant(_grant(Action.TRASH))
    _seed_ready_asset(repository)
    plan_payload = _create_trash_plan(client_as_a)
    confirm = client_as_a.post(
        f"/api/plans/{plan_payload['plan']['plan_id']}/confirm",
        headers={"Idempotency-Key": "trash-idem"},
        json_body={"expected_plan_hash": plan_payload["plan"]["plan_hash"]},
    )
    approval_id = confirm.json()["approval"]["approval_id"]
    bob_client = _login(client, "bob", "demo-b-password")

    rejected = bob_client.post(
        f"/api/approvals/{approval_id}/decide",
        headers={"Idempotency-Key": "trash-reject"},
        json_body={
            "decision": "rejected",
            "expected_plan_hash": plan_payload["plan"]["plan_hash"],
        },
    )
    retry = bob_client.post(
        f"/api/approvals/{approval_id}/decide",
        headers={"Idempotency-Key": "trash-retry"},
        json_body={
            "decision": "approved",
            "expected_plan_hash": plan_payload["plan"]["plan_hash"],
        },
    )

    assert rejected.status_code == 200
    assert rejected.json()["approval"]["decision"] == "rejected"
    assert retry.status_code == 409
    assert file_executor.executions == []

