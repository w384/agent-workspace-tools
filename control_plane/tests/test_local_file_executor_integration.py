import hashlib
from pathlib import Path

from fastapi.testclient import TestClient

from control_plane.app.domain import (
    Action,
    PermissionGrant,
    PrincipalType,
    TrustedActorContext,
)
from control_plane.app.local_file_executor import LocalWorkspaceFileExecutorAdapter
from control_plane.app.repository import InMemoryControlPlaneRepository
from control_plane.app.service import ControlPlaneService
from service.app.rag.control_plane_adapter import ControlPlaneRetrievalAdapter
from service.app.main import create_app as create_workspace_app


class WorkspaceAsgiClient:
    """Test-only client that exercises the real local FastAPI handlers."""

    def __init__(self, client: TestClient, api_key: str) -> None:
        self._client = client
        self._headers = {"X-API-Key": api_key}

    def create_plan(self, operations: list[dict[str, object]], *, user_id: str) -> dict:
        response = self._client.post(
            "/plans",
            params={"user_id": user_id},
            json={"operations": operations},
            headers=self._headers,
        )
        assert response.status_code == 201
        return response.json()

    def issue_approval_token(self, plan_id: str) -> dict[str, str]:
        response = self._client.post(
            f"/plans/{plan_id}/approval-token",
            headers=self._headers,
        )
        assert response.status_code == 200
        return response.json()

    def execute_plan(
        self,
        plan_id: str,
        approval_token: str,
        *,
        plan_hash: str,
        user_id: str,
    ) -> dict:
        response = self._client.post(
            f"/plans/{plan_id}/execute",
            params={"user_id": user_id},
            json={"approval_token": approval_token, "plan_hash": plan_hash},
            headers=self._headers,
        )
        assert response.status_code == 200
        return response.json()


class NoopRagPort:
    def enqueue_version(self, actor, asset_version, request_id) -> None:
        raise AssertionError("RAG must not be called by a file plan")


def _actor() -> TrustedActorContext:
    return TrustedActorContext(
        actor_id="user-a",
        workspace_id="workspace-a",
        context_version="acl-v1",
        session_id="session-a",
        request_id="request-a",
        run_id="run-a",
        role_ids=frozenset({"role-member-a"}),
    )


def test_self_confirm_flow_uses_real_local_fastapi_without_exposing_token(
    tmp_path: Path,
) -> None:
    workspace_root = tmp_path / "workspace"
    source = workspace_root / "organized" / "report.txt"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"version one")
    api_key = "integration-api-key"
    workspace_client = WorkspaceAsgiClient(
        TestClient(create_workspace_app(workspace_root, api_key=api_key)), api_key
    )

    repository = InMemoryControlPlaneRepository()
    repository.add_permission_grant(
        PermissionGrant(
            grant_id="move-allow",
            workspace_id="workspace-a",
            context_version="acl-v1",
            principal_type=PrincipalType.USER,
            principal_id="user-a",
            action=Action.MOVE_RENAME,
            path_prefix="organized",
        )
    )
    asset = repository.get_or_create_asset(
        "workspace-a", "organized/report.txt", "report.txt", "user-a"
    )
    version = repository.create_asset_version(
        asset.asset_id,
        "sha256:" + hashlib.sha256(source.read_bytes()).hexdigest(),
        "organized/report.txt",
    )
    for state in ("parsing", "indexed", "ready"):
        repository.transition_asset_version(version.asset_version_id, state)
    repository.activate_asset_version(version.asset_version_id)
    service = ControlPlaneService(
        repository,
        LocalWorkspaceFileExecutorAdapter(workspace_client),
        NoopRagPort(),
        approver_role_id="role-approver-a",
    )

    planned = service.create_plan(
        _actor(),
        operations=(
            {
                "operation_id": "control-op-1",
                "type": "move_rename",
                "source_path": "organized/report.txt",
                "target_path": "organized/report-renamed.txt",
            },
        ),
        expires_at="2099-01-01T00:00:00Z",
    )
    confirmed = service.confirm_plan(
        _actor(),
        planned.plan.plan_id,
        planned.plan.plan_hash,
        "control-idempotency-1",
    )
    repeated = service.confirm_plan(
        _actor(),
        planned.plan.plan_id,
        planned.plan.plan_hash,
        "control-idempotency-1",
    )

    assert confirmed.execution_job is not None
    assert confirmed.execution_job.state == "completed"
    assert repeated.execution_job is not None
    assert repeated.execution_job.job_id == confirmed.execution_job.job_id
    assert len(repository.execution_jobs) == 1
    assert planned.plan.executor_plan_id != planned.plan.plan_id
    assert planned.plan.executor_plan_hash != planned.plan.plan_hash
    assert (workspace_root / "organized" / "report-renamed.txt").read_bytes() == b"version one"
    assert not source.exists()
    moved_asset = repository.get_asset(asset.asset_id)
    assert moved_asset.asset_id == asset.asset_id
    assert moved_asset.active_version_id == version.asset_version_id
    assert moved_asset.path == "organized/report-renamed.txt"
    assert "organized/report.txt" in moved_asset.path_history
    reference = ControlPlaneRetrievalAdapter(
        repository=repository, actor=_actor()
    ).get_asset_reference(
        tenant_id="workspace-a",
        asset_id=asset.asset_id,
        asset_version_id=version.asset_version_id,
    )
    assert reference.current_path == "organized/report-renamed.txt"
    assert reference.version_path == "organized/report.txt"
    assert "approval_token" not in repr(repository.plans)
    assert "approval_token" not in repr(repository.list_audit_events())
