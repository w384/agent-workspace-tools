from dataclasses import dataclass
from types import SimpleNamespace

from control_plane.app.domain import (
    Action,
    PermissionGrant,
    PrincipalType,
    TrustedActorContext,
)
from control_plane.app.local_file_executor import LocalWorkspaceFileExecutorAdapter
from control_plane.app.ports import ExecutionResult
from control_plane.app.repository import InMemoryControlPlaneRepository
from control_plane.app.service import ControlPlaneService


EXECUTOR_HASH = "sha256:" + "e" * 64


@dataclass
class RecordingWorkspaceService:
    create_requests: list[tuple[list[dict[str, object]], str]]
    issued_plan_ids: list[str]
    execute_requests: list[tuple[str, str, str, str]]

    def create_plan(
        self, operations: list[dict[str, object]], *, user_id: str
    ) -> dict[str, object]:
        self.create_requests.append((operations, user_id))
        return {
            "plan_id": "executor-plan-1",
            "plan_hash": EXECUTOR_HASH,
            "confirmation": {"moves": []},
        }

    def issue_approval_token(self, plan_id: str) -> dict[str, str]:
        self.issued_plan_ids.append(plan_id)
        return {"plan_id": plan_id, "approval_token": "one-time-token"}

    def execute_plan(
        self,
        plan_id: str,
        approval_token: str,
        *,
        plan_hash: str,
        user_id: str,
    ) -> dict[str, object]:
        self.execute_requests.append((plan_id, approval_token, plan_hash, user_id))
        return {"status": "completed", "operation_id": "op-1"}


class NoopRagPort:
    def enqueue_version(self, actor, asset_version, request_id) -> None:
        raise AssertionError("RAG must not be called")


class ReferencingExecutor:
    def __init__(self) -> None:
        self.confirm_requests: list[dict[str, object]] = []

    def create_plan(self, *args, **kwargs):
        return SimpleNamespace(
            impact_summary="safe preview",
            executor_plan_id="executor-plan-1",
            executor_plan_hash=EXECUTOR_HASH,
        )

    def confirm_and_execute(self, **kwargs):
        self.confirm_requests.append(kwargs)
        return ExecutionResult(status="completed", operation_id="op-1")


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


def _seed_ready_asset(repository: InMemoryControlPlaneRepository) -> None:
    asset = repository.get_or_create_asset(
        "workspace-a", "organized/report.txt", "report.txt", "user-a"
    )
    version = repository.create_asset_version(
        asset.asset_id, "sha256:content-v1", "organized/report.txt"
    )
    for state in ("parsing", "indexed", "ready"):
        repository.transition_asset_version(version.asset_version_id, state)
    repository.activate_asset_version(version.asset_version_id)


def test_control_plan_binds_executor_plan_reference_before_confirmation() -> None:
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
    _seed_ready_asset(repository)
    executor = ReferencingExecutor()
    service = ControlPlaneService(
        repository, executor, NoopRagPort(), approver_role_id="role-approver-a"
    )

    outcome = service.create_plan(
        _actor(),
        operations=(
            {
                "operation_id": "op-1",
                "type": "move_rename",
                "source_path": "organized/report.txt",
                "target_path": "organized/report-renamed.txt",
            },
        ),
        expires_at="2099-01-01T00:00:00Z",
    )

    assert outcome.plan.executor_plan_id == "executor-plan-1"
    assert outcome.plan.executor_plan_hash == EXECUTOR_HASH


def test_local_adapter_consumes_token_without_exposing_it() -> None:
    workspace_service = RecordingWorkspaceService([], [], [])
    adapter = LocalWorkspaceFileExecutorAdapter(workspace_service)

    preview = adapter.create_plan(
        _actor(),
        normalized_operations=(
            {
                "operation_id": "op-1",
                "type": "move_rename",
                "source_path": "organized/report.txt",
                "target_path": "organized/report-renamed.txt",
            },
        ),
        asset_snapshots=(),
        acl_snapshot={},
        policy_version="policy-v1",
        expires_at="2099-01-01T00:00:00Z",
        idempotency_key="preview-1",
    )
    result = adapter.confirm_and_execute(
        actor=_actor(),
        control_plan_id="control-plan-1",
        executor_plan_id=preview.executor_plan_id,
        executor_plan_hash=preview.executor_plan_hash,
        expected_plan_hash="sha256:" + "c" * 64,
        asset_snapshots=(),
        acl_snapshot={},
        decision={},
        confirmation_evidence={},
        approval_evidence=None,
        idempotency_key="execute-1",
    )

    assert workspace_service.create_requests == [
        (
            [
                {
                    "action": "move_rename",
                    "source": "organized/report.txt",
                    "destination": "organized/report-renamed.txt",
                }
            ],
            "user-a",
        )
    ]
    assert workspace_service.issued_plan_ids == ["executor-plan-1"]
    assert workspace_service.execute_requests == [
        ("executor-plan-1", "one-time-token", EXECUTOR_HASH, "user-a")
    ]
    assert result == ExecutionResult(status="completed", operation_id="op-1")
    assert "one-time-token" not in repr(result)

