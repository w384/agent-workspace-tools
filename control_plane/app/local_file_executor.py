from dataclasses import dataclass
from typing import Mapping, Protocol

from .domain import TrustedActorContext
from .ports import ExecutionResult, FilePlanPreview


class WorkspaceServiceClient(Protocol):
    """Trusted internal client for the local FastAPI write boundary."""

    def create_plan(
        self, operations: list[dict[str, object]], *, user_id: str
    ) -> dict[str, object]: ...

    def issue_approval_token(self, plan_id: str) -> dict[str, str]: ...

    def execute_plan(
        self,
        plan_id: str,
        approval_token: str,
        *,
        plan_hash: str,
        user_id: str,
    ) -> dict[str, object]: ...


@dataclass(slots=True)
class LocalWorkspaceFileExecutorAdapter:
    """Bridge a trusted BFF call to the sole local write boundary.

    The executor plan hash is intentionally distinct from the control-plan hash.
    The approval token lives only in ``confirm_and_execute`` local variables.
    """

    workspace_service: WorkspaceServiceClient

    def create_plan(
        self,
        actor: TrustedActorContext,
        normalized_operations: tuple[Mapping[str, object], ...],
        asset_snapshots: tuple[Mapping[str, str], ...],
        acl_snapshot: Mapping[str, object],
        policy_version: str,
        expires_at: str,
        idempotency_key: str,
    ) -> FilePlanPreview:
        del asset_snapshots, acl_snapshot, policy_version, expires_at, idempotency_key
        response = self.workspace_service.create_plan(
            [_to_workspace_operation(operation) for operation in normalized_operations],
            user_id=actor.actor_id,
        )
        return FilePlanPreview(
            impact_summary=_impact_summary(response),
            executor_plan_id=_required_string(response, "plan_id"),
            executor_plan_hash=_required_plan_hash(response, "plan_hash"),
        )

    def confirm_and_execute(
        self,
        actor: TrustedActorContext,
        control_plan_id: str,
        executor_plan_id: str,
        executor_plan_hash: str,
        expected_plan_hash: str,
        asset_snapshots: tuple[Mapping[str, str], ...],
        acl_snapshot: Mapping[str, object],
        decision: Mapping[str, object],
        confirmation_evidence: Mapping[str, object],
        approval_evidence: Mapping[str, object] | None,
        idempotency_key: str,
    ) -> ExecutionResult:
        del (
            control_plan_id,
            expected_plan_hash,
            asset_snapshots,
            acl_snapshot,
            decision,
            confirmation_evidence,
            approval_evidence,
            idempotency_key,
        )
        token_response = self.workspace_service.issue_approval_token(executor_plan_id)
        approval_token = _required_string(token_response, "approval_token")
        response = self.workspace_service.execute_plan(
            executor_plan_id,
            approval_token,
            plan_hash=executor_plan_hash,
            user_id=actor.actor_id,
        )
        return ExecutionResult(
            status=_required_string(response, "status"),
            operation_id=_required_string(response, "operation_id"),
            failure_code=_optional_string(response, "failure_code"),
        )


def _to_workspace_operation(operation: Mapping[str, object]) -> dict[str, object]:
    operation_type = _required_string(operation, "type")
    if operation_type == "move_rename":
        return {
            "action": operation_type,
            "source": _required_string(operation, "source_path"),
            "destination": _required_string(operation, "target_path"),
        }
    if operation_type == "trash":
        return {
            "action": operation_type,
            "source": _required_string(operation, "source_path"),
        }
    raise ValueError("unsupported control-plane operation")


def _impact_summary(response: Mapping[str, object]) -> str:
    confirmation = response.get("confirmation")
    return "local executor plan created" if isinstance(confirmation, Mapping) else ""


def _required_string(response: Mapping[str, object], field_name: str) -> str:
    value = response.get(field_name)
    if not isinstance(value, str) or not value:
        raise ValueError(f"workspace service response missing {field_name}")
    return value


def _required_plan_hash(response: Mapping[str, object], field_name: str) -> str:
    value = _required_string(response, field_name)
    if not value.startswith("sha256:"):
        raise ValueError("workspace service response has invalid plan_hash")
    return value


def _optional_string(response: Mapping[str, object], field_name: str) -> str | None:
    value = response.get(field_name)
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"workspace service response has invalid {field_name}")
    return value
