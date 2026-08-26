"""恢复/升级路径测试（Recovery / Escalation）。

验证失败（MISMATCH / UNKNOWN）后控制面不再只停留在 mismatch / unknown
状态，而是进入可处理的恢复/升级闭环：
  1. 自动创建 RecoveryTask（state=pending + strategy + evidence），审计
     recovery_task_created；
  2. list_recovery_tasks 按 workspace 隔离可见；
  3. resolve_recovery_task(recovered) -> task/plan -> recovered + 审计
     recovery_resolved；
  4. resolve_recovery_task(escalated) -> task/plan -> escalated + 审计
     recovery_escalated；
  5. 边界：跨 workspace 不可见不可处理；非 pending 重复处理报错；
     未知 recovery_id / 非法 decision 报错。
"""

import pytest

from control_plane.app.domain import TrustedActorContext
from control_plane.app.ports import (
    ExecutionResult,
    VerificationResult,
    VerificationStatus,
)
from control_plane.app.service import (
    ControlPlaneService,
    RecoveryTaskNotFoundError,
    RecoveryTaskStateError,
    VerificationMismatchError,
)
from control_plane.app.verification import ControlledDirectoryVerifier

from conftest import RecordingFileExecutor
from test_verification import (
    EXPIRES_AT,
    _actor,
    _plan_upload_operation,
    _seed_uploaded_asset,
)


class AlwaysUnknownVerifier:
    """Verifier stub that reports UNKNOWN for every execution (read-back unavailable)."""

    def verify(self, actor, plan, execution_result: ExecutionResult) -> VerificationResult:
        del actor, plan
        return VerificationResult(
            status=VerificationStatus.UNKNOWN,
            operation_id=execution_result.operation_id,
            matched=False,
            expected_state={},
            actual_state={},
            evidence={"read_back": "stub-unavailable"},
            reason="independent_readback_unavailable",
        )


def _mismatch_service(
    repository, rag_port, tmp_path
) -> tuple[ControlPlaneService, RecordingFileExecutor]:
    executor = RecordingFileExecutor()
    service = ControlPlaneService(
        repository,
        executor,
        rag_port,
        approver_role_id="role-approver-demo",
        verification_port=ControlledDirectoryVerifier(tmp_path),
    )
    return service, executor


def _trigger_unverified(
    service: ControlPlaneService,
    repository,
    executor: RecordingFileExecutor,
    idempotency_key: str,
):
    actor, _ = _seed_uploaded_asset(service, repository, executor)
    plan_outcome = service.create_plan(actor, (_plan_upload_operation(),), EXPIRES_AT)
    with pytest.raises(VerificationMismatchError):
        service.confirm_plan(
            actor,
            plan_outcome.plan.plan_id,
            plan_outcome.plan.plan_hash,
            idempotency_key,
        )
    return actor, plan_outcome


def _events_of(repository, event_type: str):
    return [
        event
        for event in repository.list_audit_events()
        if event.event_type == event_type
    ]


def test_mismatch_creates_pending_recovery_task(repository, rag_port, tmp_path) -> None:
    service, executor = _mismatch_service(repository, rag_port, tmp_path)
    actor, plan_outcome = _trigger_unverified(
        service, repository, executor, "idem-rec-mismatch-1"
    )

    tasks = service.list_recovery_tasks(actor)
    assert len(tasks) == 1
    task = tasks[0]
    assert task.state == "pending"
    assert task.plan_id == plan_outcome.plan.plan_id
    assert task.workspace_id == "workspace-a"
    assert task.strategy == "retry_compensation"
    assert task.reason == "readback_fingerprint_mismatch"
    assert task.details["verification_status"] == "mismatch"
    assert task.resolved_at is None

    job = repository.find_execution_job(
        plan_outcome.plan.plan_id,
        plan_outcome.plan.plan_hash,
        "idem-rec-mismatch-1",
    )
    assert job is not None
    assert job.state == "mismatch"
    assert task.job_id == job.job_id

    created_events = _events_of(repository, "recovery_task_created")
    assert len(created_events) == 1
    assert created_events[0].details["recovery_id"] == task.recovery_id
    assert created_events[0].details["strategy"] == "retry_compensation"


def test_resolve_recovery_task_recovered(repository, rag_port, tmp_path) -> None:
    service, executor = _mismatch_service(repository, rag_port, tmp_path)
    actor, _ = _trigger_unverified(service, repository, executor, "idem-rec-ok-1")
    task = service.list_recovery_tasks(actor)[0]

    outcome = service.resolve_recovery_task(actor, task.recovery_id, "recovered")
    assert outcome.task.state == "recovered"
    assert outcome.task.resolved_by == actor.actor_id
    assert outcome.task.resolved_at is not None
    assert outcome.plan.state == "recovered"
    assert repository.get_plan(task.plan_id).state == "recovered"

    resolved_events = _events_of(repository, "recovery_resolved")
    assert len(resolved_events) == 1
    assert resolved_events[0].details["recovery_id"] == task.recovery_id
    assert resolved_events[0].details["decision"] == "recovered"


def test_resolve_recovery_task_escalated(repository, rag_port, tmp_path) -> None:
    service, executor = _mismatch_service(repository, rag_port, tmp_path)
    actor, _ = _trigger_unverified(service, repository, executor, "idem-rec-esc-1")
    task = service.list_recovery_tasks(actor)[0]

    outcome = service.resolve_recovery_task(actor, task.recovery_id, "escalated")
    assert outcome.task.state == "escalated"
    assert outcome.task.resolved_by == actor.actor_id
    assert repository.get_plan(task.plan_id).state == "escalated"

    escalated_events = _events_of(repository, "recovery_escalated")
    assert len(escalated_events) == 1
    assert escalated_events[0].details["recovery_id"] == task.recovery_id
    assert escalated_events[0].details["decision"] == "escalated"


def test_unknown_creates_manual_review_recovery_task(repository, rag_port) -> None:
    executor = RecordingFileExecutor()
    service = ControlPlaneService(
        repository,
        executor,
        rag_port,
        approver_role_id="role-approver-demo",
        verification_port=AlwaysUnknownVerifier(),
    )
    actor, _ = _trigger_unverified(service, repository, executor, "idem-rec-unk-1")

    tasks = service.list_recovery_tasks(actor)
    assert len(tasks) == 1
    assert tasks[0].state == "pending"
    assert tasks[0].strategy == "manual_review"
    assert tasks[0].reason == "independent_readback_unavailable"
    assert repository.get_plan(tasks[0].plan_id).state == "unknown"


def test_recovery_task_workspace_scope(repository, rag_port, tmp_path) -> None:
    service, executor = _mismatch_service(repository, rag_port, tmp_path)
    actor, _ = _trigger_unverified(service, repository, executor, "idem-rec-scope-1")
    outsider = TrustedActorContext(
        actor_id="user-d",
        workspace_id="workspace-b",
        context_version="acl_2026_08_13",
        session_id="session-d",
        request_id="request-d",
        run_id="run-d",
        group_ids=frozenset(),
        role_ids=frozenset({"role-member-demo"}),
    )

    assert service.list_recovery_tasks(outsider) == []
    task = service.list_recovery_tasks(actor)[0]
    with pytest.raises(RecoveryTaskNotFoundError):
        service.resolve_recovery_task(outsider, task.recovery_id, "escalated")


def test_resolve_pending_task_twice_raises_state_error(repository, rag_port, tmp_path) -> None:
    service, executor = _mismatch_service(repository, rag_port, tmp_path)
    actor, _ = _trigger_unverified(service, repository, executor, "idem-rec-twice-1")
    task = service.list_recovery_tasks(actor)[0]
    service.resolve_recovery_task(actor, task.recovery_id, "recovered")
    with pytest.raises(RecoveryTaskStateError):
        service.resolve_recovery_task(actor, task.recovery_id, "recovered")


def test_resolve_unknown_recovery_id_raises(repository, rag_port, tmp_path) -> None:
    service, executor = _mismatch_service(repository, rag_port, tmp_path)
    actor, _ = _trigger_unverified(service, repository, executor, "idem-rec-noid-1")
    with pytest.raises(RecoveryTaskNotFoundError):
        service.resolve_recovery_task(actor, "recovery-does-not-exist", "recovered")


def test_resolve_invalid_decision_raises(repository, rag_port, tmp_path) -> None:
    service, executor = _mismatch_service(repository, rag_port, tmp_path)
    actor, _ = _trigger_unverified(service, repository, executor, "idem-rec-baddec-1")
    task = service.list_recovery_tasks(actor)[0]
    with pytest.raises(RecoveryTaskStateError):
        service.resolve_recovery_task(actor, task.recovery_id, "something-else")