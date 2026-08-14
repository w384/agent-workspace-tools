import hashlib
from dataclasses import replace
from pathlib import Path

from control_plane.app.domain import Action, GrantEffect, PermissionGrant, PrincipalType
from control_plane.app.ports import ExecutionResult
from control_plane.app.repository import ControlPlaneRepository
from control_plane.app.plan_hash import (
    PlanHashInput,
    PlanHashSnapshot,
    compute_canonical_plan_hash,
    plan_hash_matches,
)


def _grant(action: Action, path_prefix: str, effect: GrantEffect = GrantEffect.ALLOW):
    return PermissionGrant(
        grant_id=f"{effect.value}-{action.value}-{path_prefix}",
        workspace_id="workspace-a",
        context_version="acl_2026_08_13",
        principal_type=PrincipalType.USER,
        principal_id="user-a",
        action=action,
        path_prefix=path_prefix,
        effect=effect,
    )


def _seed_ready_asset(repository, path="organized/report.txt", fingerprint="sha256:v1"):
    asset = repository.get_or_create_asset("workspace-a", path, path.rsplit("/", 1)[-1], "user-a")
    version = repository.create_asset_version(asset.asset_id, fingerprint, path)
    for state in ("parsing", "indexed", "ready"):
        repository.transition_asset_version(version.asset_version_id, state)
    repository.activate_asset_version(version.asset_version_id)
    return asset, version


def _create_move_plan(client, expected_status=200):
    response = client.post(
        "/api/plans",
        params={"user_id": "user-b"},
        headers={"X-User-Id": "user-b", "X-Request-Id": "forged-request"},
        json_body={
            "policy_version": "client-forged-policy",
            "context_version": "client-forged-context",
            "asset_snapshots": [{"asset_id": "forged", "content_fingerprint": "sha256:forged"}],
            "operations": [
                {
                    "operation_id": "op-1",
                    "type": "move_rename",
                    "source_path": "organized/report.txt",
                    "target_path": "organized/report-renamed.txt",
                }
            ],
            "expires_at": "2099-01-01T00:00:00Z",
        },
    )
    assert response.status_code == expected_status
    return response


def test_canonical_plan_hash_is_stable_and_binds_frozen_fields() -> None:
    base = PlanHashInput(
        contract_version="control-plane-demo-v1",
        plan_id="plan-1",
        workspace_id="workspace-a",
        actor_id="user-a",
        decision_state="SELF_CONFIRM",
        decision_id="decision-1",
        policy_version="policy_2026_08_13",
        context_version="acl_2026_08_13",
        normalized_operations=(
            {"type": "move_rename", "operation_id": "op-1"},
        ),
        asset_snapshots=(
            PlanHashSnapshot("asset-b", "version-b", "sha256:b"),
            PlanHashSnapshot("asset-a", "version-a", "sha256:a"),
        ),
        expires_at="2099-01-01T00:00:00Z",
    )
    reordered = PlanHashInput(
        contract_version=base.contract_version,
        plan_id=base.plan_id,
        workspace_id=base.workspace_id,
        actor_id=base.actor_id,
        decision_state=base.decision_state,
        decision_id=base.decision_id,
        policy_version=base.policy_version,
        context_version=base.context_version,
        normalized_operations=base.normalized_operations,
        asset_snapshots=tuple(reversed(base.asset_snapshots)),
        expires_at=base.expires_at,
    )
    changed = PlanHashInput(
        contract_version=base.contract_version,
        plan_id=base.plan_id,
        workspace_id=base.workspace_id,
        actor_id=base.actor_id,
        decision_state=base.decision_state,
        decision_id=base.decision_id,
        policy_version=base.policy_version,
        context_version="acl_changed",
        normalized_operations=base.normalized_operations,
        asset_snapshots=base.asset_snapshots,
        expires_at=base.expires_at,
    )

    digest = compute_canonical_plan_hash(base)

    assert digest.startswith("sha256:")
    assert digest == compute_canonical_plan_hash(reordered)
    assert digest != compute_canonical_plan_hash(changed)
    assert plan_hash_matches(digest, digest)
    assert not plan_hash_matches(digest, compute_canonical_plan_hash(changed))


def test_service_uses_repository_protocol_methods_for_confirmation_and_approval_state() -> None:
    source = (Path(__file__).parents[1] / "app" / "service.py").read_text(encoding="utf-8")

    assert hasattr(ControlPlaneRepository, "find_confirmation_by_plan")
    assert hasattr(ControlPlaneRepository, "get_approval")
    assert hasattr(ControlPlaneRepository, "find_approval_by_plan")
    assert hasattr(ControlPlaneRepository, "list_pending_approvals")
    assert "self._repository.approvals" not in source
    assert "repository.confirmations" not in source


def test_move_plan_returns_self_confirm_preview_without_execution_or_approval(
    client_as_a, repository, file_executor
) -> None:
    repository.add_permission_grant(_grant(Action.MOVE_RENAME, "organized"))
    asset, version = _seed_ready_asset(repository)

    response = _create_move_plan(client_as_a)

    payload = response.json()
    assert payload["decision"]["state"] == "SELF_CONFIRM"
    assert payload["plan"]["state"] == "pending_confirmation"
    assert payload["asset_snapshots"] == [
        {
            "asset_id": asset.asset_id,
            "asset_version_id": version.asset_version_id,
            "content_fingerprint": "sha256:v1",
        }
    ]
    assert payload["plan"]["policy_version"] == "policy_2026_08_13"
    assert payload["plan"]["context_version"] == "acl_2026_08_13"
    assert file_executor.executions == []
    assert repository.approvals == {}


def test_mixed_batch_with_a_denied_target_has_zero_downstream_or_plan_side_effects(
    client_as_a, repository, file_executor, rag_port
) -> None:
    repository.add_permission_grant(_grant(Action.MOVE_RENAME, "organized"))
    repository.add_permission_grant(_grant(Action.MOVE_RENAME, "restricted", GrantEffect.DENY))
    _seed_ready_asset(repository)

    response = client_as_a.post(
        "/api/plans",
        json_body={
            "operations": [
                {
                    "operation_id": "op-1",
                    "type": "move_rename",
                    "source_path": "organized/report.txt",
                    "target_path": "restricted/report-renamed.txt",
                }
            ],
            "expires_at": "2099-01-01T00:00:00Z",
        },
    )

    assert response.status_code == 403
    assert response.json() == {
        "error": {"code": "plan_denied", "message": "Plan is not authorized"}
    }
    assert repository.plans == {}
    assert repository.confirmations == {}
    assert repository.approvals == {}
    assert repository.execution_jobs == {}
    assert file_executor.plan_previews == []
    assert file_executor.executions == []
    assert rag_port.calls == []
    assert [event.event_type for event in repository.list_audit_events()] == ["plan_denied"]
    assert "restricted/report-renamed.txt" not in repr(repository.list_audit_events())


def test_self_confirm_creator_executes_once_by_composite_idempotency(
    client_as_a, repository, file_executor
) -> None:
    repository.add_permission_grant(_grant(Action.MOVE_RENAME, "organized"))
    _seed_ready_asset(repository)
    plan_payload = _create_move_plan(client_as_a).json()

    headers = {"Idempotency-Key": "idem-1"}
    first = client_as_a.post(
        f"/api/plans/{plan_payload['plan']['plan_id']}/confirm",
        headers=headers,
        json_body={"expected_plan_hash": plan_payload["plan"]["plan_hash"]},
    )
    second = client_as_a.post(
        f"/api/plans/{plan_payload['plan']['plan_id']}/confirm",
        headers=headers,
        json_body={"expected_plan_hash": plan_payload["plan"]["plan_hash"]},
    )

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["execution_job"] == second.json()["execution_job"]
    assert first.json()["execution_job"]["state"] == "completed"
    assert len(file_executor.executions) == 1
    assert len(repository.execution_jobs) == 1
    job = next(iter(repository.execution_jobs.values()))
    assert (job.plan_id, job.plan_hash, job.idempotency_key) == (
        plan_payload["plan"]["plan_id"],
        plan_payload["plan"]["plan_hash"],
        "idem-1",
    )
    assert "one-time" not in repr(repository.execution_jobs)
    assert "one-time" not in repr(repository.list_audit_events())


def test_confirm_fails_closed_for_wrong_hash_or_non_creator(client_as_a, repository, file_executor):
    repository.add_permission_grant(_grant(Action.MOVE_RENAME, "organized"))
    _seed_ready_asset(repository)
    plan_payload = _create_move_plan(client_as_a).json()

    wrong_hash = client_as_a.post(
        f"/api/plans/{plan_payload['plan']['plan_id']}/confirm",
        headers={"Idempotency-Key": "idem-1"},
        json_body={"expected_plan_hash": "sha256:wrong"},
    )

    assert wrong_hash.status_code == 409
    assert wrong_hash.json()["error"]["code"] == "plan_hash_mismatch"
    assert file_executor.executions == []


def test_confirm_fails_closed_for_non_creator_session(
    client_as_a, repository, file_executor, client
) -> None:
    repository.add_permission_grant(_grant(Action.MOVE_RENAME, "organized"))
    _seed_ready_asset(repository)
    plan_payload = _create_move_plan(client_as_a).json()
    client.post(
        "/api/session/login",
        json_body={"username": "bob", "password": "demo-b-password"},
    )

    response = client.post(
        f"/api/plans/{plan_payload['plan']['plan_id']}/confirm",
        headers={"Idempotency-Key": "idem-non-creator"},
        json_body={"expected_plan_hash": plan_payload["plan"]["plan_hash"]},
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "plan_confirmation_forbidden"
    assert file_executor.executions == []


def test_confirm_revalidates_expiry_context_acl_and_active_snapshot_before_execution(
    client_as_a, repository, file_executor, app
) -> None:
    repository.add_permission_grant(_grant(Action.MOVE_RENAME, "organized"))
    _seed_ready_asset(repository)
    expired = client_as_a.post(
        "/api/plans",
        json_body={
            "operations": [
                {
                    "operation_id": "op-expired",
                    "type": "move_rename",
                    "source_path": "organized/report.txt",
                    "target_path": "organized/report-expired.txt",
                }
            ],
            "expires_at": "2000-01-01T00:00:00Z",
        },
    ).json()

    expired_response = client_as_a.post(
        f"/api/plans/{expired['plan']['plan_id']}/confirm",
        headers={"Idempotency-Key": "idem-expired"},
        json_body={"expected_plan_hash": expired["plan"]["plan_hash"]},
    )

    assert expired_response.status_code == 409
    assert expired_response.json()["error"]["code"] == "plan_revalidation_failed"
    assert file_executor.executions == []
    assert repository.execution_jobs == {}

    fresh = _create_move_plan(client_as_a).json()
    repository.permission_grants.clear()
    acl_response = client_as_a.post(
        f"/api/plans/{fresh['plan']['plan_id']}/confirm",
        headers={"Idempotency-Key": "idem-acl"},
        json_body={"expected_plan_hash": fresh["plan"]["plan_hash"]},
    )

    assert acl_response.status_code == 403
    assert acl_response.json()["error"]["code"] == "plan_revalidation_failed"
    assert file_executor.executions == []
    assert repository.execution_jobs == {}

    repository.add_permission_grant(_grant(Action.MOVE_RENAME, "organized"))
    context_drift = _create_move_plan(client_as_a).json()
    bearer = client_as_a.cookies["cp_session"]
    digest = hashlib.sha256(bearer.encode("utf-8")).hexdigest()
    stored = app.state.session_store._sessions[digest]
    app.state.session_store._sessions[digest] = replace(stored, context_version="acl_changed")
    context_response = client_as_a.post(
        f"/api/plans/{context_drift['plan']['plan_id']}/confirm",
        headers={"Idempotency-Key": "idem-context"},
        json_body={"expected_plan_hash": context_drift["plan"]["plan_hash"]},
    )

    assert context_response.status_code == 409
    assert context_response.json()["error"]["code"] == "plan_revalidation_failed"
    assert file_executor.executions == []
    assert repository.execution_jobs == {}

    app.state.session_store._sessions[digest] = stored
    snapshot_drift = _create_move_plan(client_as_a).json()
    asset = repository.find_asset_by_path("workspace-a", "organized/report.txt")
    assert asset is not None
    v2 = repository.create_asset_version(
        asset.asset_id,
        "sha256:v2",
        "organized/report.txt",
    )
    for state in ("parsing", "indexed", "ready"):
        repository.transition_asset_version(v2.asset_version_id, state)
    repository.activate_asset_version(v2.asset_version_id)
    snapshot_response = client_as_a.post(
        f"/api/plans/{snapshot_drift['plan']['plan_id']}/confirm",
        headers={"Idempotency-Key": "idem-snapshot"},
        json_body={"expected_plan_hash": snapshot_drift["plan"]["plan_hash"]},
    )

    assert snapshot_response.status_code == 409
    assert snapshot_response.json()["error"]["code"] == "plan_revalidation_failed"
    assert file_executor.executions == []
    assert repository.execution_jobs == {}
    events = repository.list_audit_events()
    assert events[-1].event_type == "plan_revalidation_failed"
    assert "organized/report-renamed.txt" not in repr(events)


def test_missing_active_snapshot_fails_closed_instead_of_500(
    client_as_a, repository, file_executor
) -> None:
    repository.add_permission_grant(_grant(Action.MOVE_RENAME, "organized"))
    asset, version = _seed_ready_asset(repository)
    plan_payload = _create_move_plan(client_as_a).json()
    del repository._asset_versions[version.asset_version_id]

    response = client_as_a.post(
        f"/api/plans/{plan_payload['plan']['plan_id']}/confirm",
        headers={"Idempotency-Key": "idem-missing-snapshot"},
        json_body={"expected_plan_hash": plan_payload["plan"]["plan_hash"]},
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "plan_revalidation_failed"
    assert file_executor.executions == []
    assert repository.execution_jobs == {}
    assert repository.get_asset(asset.asset_id).active_version_id == version.asset_version_id


def test_executor_final_deny_marks_job_failed_and_cannot_be_approved_around(
    client_as_a, repository, file_executor
) -> None:
    repository.add_permission_grant(_grant(Action.MOVE_RENAME, "organized"))
    _seed_ready_asset(repository)
    file_executor.execution_error = PermissionError("executor acl denied secret")
    plan_payload = _create_move_plan(client_as_a).json()

    response = client_as_a.post(
        f"/api/plans/{plan_payload['plan']['plan_id']}/confirm",
        headers={"Idempotency-Key": "idem-deny"},
        json_body={"expected_plan_hash": plan_payload["plan"]["plan_hash"]},
    )

    assert response.status_code == 403
    assert response.json() == {
        "error": {"code": "executor_acl_denied", "message": "Execution is not authorized"}
    }
    job = next(iter(repository.execution_jobs.values()))
    assert job.state == "failed"
    assert "executor acl denied secret" not in repr(repository.list_audit_events())


def test_executor_exception_or_non_completed_result_fails_job_without_false_completion(
    client_as_a, repository, file_executor
) -> None:
    repository.add_permission_grant(_grant(Action.MOVE_RENAME, "organized"))
    _seed_ready_asset(repository)
    file_executor.execution_error = RuntimeError("executor secret boom")
    exception_plan = _create_move_plan(client_as_a).json()

    exception_response = client_as_a.post(
        f"/api/plans/{exception_plan['plan']['plan_id']}/confirm",
        headers={"Idempotency-Key": "idem-exception"},
        json_body={"expected_plan_hash": exception_plan["plan"]["plan_hash"]},
    )

    assert exception_response.status_code == 502
    assert exception_response.json()["error"]["code"] == "executor_execution_failed"
    failed_job = next(iter(repository.execution_jobs.values()))
    assert failed_job.state == "failed"
    assert "executor secret boom" not in repr(repository.list_audit_events())

    file_executor.execution_error = None
    file_executor.execution_result = ExecutionResult(
        status="failed",
        operation_id="op-1",
        failure_code="executor_failed",
    )
    non_completed_plan = _create_move_plan(client_as_a).json()
    non_completed_response = client_as_a.post(
        f"/api/plans/{non_completed_plan['plan']['plan_id']}/confirm",
        headers={"Idempotency-Key": "idem-non-completed"},
        json_body={"expected_plan_hash": non_completed_plan["plan"]["plan_hash"]},
    )

    assert non_completed_response.status_code == 502
    assert non_completed_response.json()["error"]["code"] == "executor_execution_failed"
    jobs = list(repository.execution_jobs.values())
    assert jobs[-1].state == "failed"
    assert all(job.state != "completed" for job in jobs)

