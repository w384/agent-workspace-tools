"""TRASH 读回验证测试（破坏性操作的 VERIFIED/MISMATCH 闭环）。

TRASH（移入回收站）是高风险破坏性操作：政策层为 APPROVAL_REQUIRED。
执行器声称完成后，verifier 独立读回受控目录：
  - 源文件已从受控目录消失 -> VERIFIED（破坏性操作完成且有据可查）；
  - 源文件仍存在（执行器谎报） -> MISMATCH + VerificationMismatchError + 恢复任务。

覆盖：
  1. 正例：真实删除 executor -> 文件消失 -> VERIFIED（job/plan=verified + 审计留痕）
  2. 反例：执行器谎报 completed 但未删文件 -> MISMATCH + 异常 + 恢复任务
"""

from pathlib import Path

import pytest

from control_plane.app.domain import (
    Action,
    DecisionState,
    PermissionGrant,
    PrincipalType,
    TrustedActorContext,
)
from control_plane.app.service import (
    ControlPlaneService,
    VerificationMismatchError,
)
from control_plane.app.verification import ControlledDirectoryVerifier

from conftest import RecordingFileExecutor
from test_verification import (
    EXPIRES_AT,
    _activate_uploaded_version,
    _actor,
)


def _approver_actor() -> TrustedActorContext:
    return TrustedActorContext(
        actor_id="user-approver",
        workspace_id="workspace-a",
        context_version="acl_2026_08_13",
        session_id="session-approver",
        request_id="request-approver",
        run_id="run-approver",
        group_ids=frozenset({"staff"}),
        role_ids=frozenset({"role-approver-demo"}),
    )


def _add_trash_grant(repository) -> None:
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


def _plan_trash_operation() -> dict[str, object]:
    return {
        "operation_id": "op-trash-1",
        "type": "trash",
        "source_path": "organized/report.txt",
    }


class RealTrashExecutor(RecordingFileExecutor):
    """Executor that actually deletes the source file and reports completed."""

    def __init__(self, base_dir: Path) -> None:
        super().__init__()
        self._base_dir = base_dir
        self.delete_called = False

    def confirm_and_execute(
        self,
        actor,
        control_plan_id,
        executor_plan_id,
        executor_plan_hash,
        expected_plan_hash,
        asset_snapshots,
        acl_snapshot,
        decision,
        confirmation_evidence,
        approval_evidence,
        idempotency_key,
    ):
        result = super().confirm_and_execute(
            actor,
            control_plan_id,
            executor_plan_id,
            executor_plan_hash,
            expected_plan_hash,
            asset_snapshots,
            acl_snapshot,
            decision,
            confirmation_evidence,
            approval_evidence,
            idempotency_key,
        )
        target = self._base_dir / "organized" / "report.txt"
        if target.exists():
            target.unlink()
        self.delete_called = True
        return result


def _seed_trash_asset(service, repository, executor, base_dir: Path) -> tuple:
    actor = _actor()
    content = b"trash read-back real content 2026"
    outcome = service.upload(actor, "organized", "report.txt", content)
    _activate_uploaded_version(repository, outcome.asset_version)
    target = base_dir / "organized" / "report.txt"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(content)
    return actor, outcome


def _trash_service(repository, rag_port, tmp_path, executor) -> ControlPlaneService:
    service = ControlPlaneService(
        repository,
        executor,
        rag_port,
        approver_role_id="role-approver-demo",
        verification_port=ControlledDirectoryVerifier(tmp_path),
    )
    _add_trash_grant(repository)
    return service


def test_trash_verified_when_file_disappears(repository, rag_port, tmp_path) -> None:
    executor = RealTrashExecutor(tmp_path)
    service = _trash_service(repository, rag_port, tmp_path, executor)
    actor, _ = _seed_trash_asset(service, repository, executor, tmp_path)
    assert (tmp_path / "organized" / "report.txt").exists()

    plan_outcome = service.create_plan(actor, (_plan_trash_operation(),), EXPIRES_AT)
    assert plan_outcome.plan.decision_state is DecisionState.APPROVAL_REQUIRED
    confirmed = service.confirm_plan(
        actor,
        plan_outcome.plan.plan_id,
        plan_outcome.plan.plan_hash,
        "idem-trash-ok-1",
    )
    assert confirmed.approval is not None
    approved = service.decide_approval(
        _approver_actor(),
        confirmed.approval.approval_id,
        "approved",
        plan_outcome.plan.plan_hash,
        "idem-trash-ok-2",
    )

    assert executor.delete_called
    assert not (tmp_path / "organized" / "report.txt").exists()
    assert approved.execution_job is not None
    assert approved.execution_job.state == "verified"
    assert repository.get_plan(plan_outcome.plan.plan_id).state == "verified"
    verified_events = [
        event
        for event in repository.list_audit_events()
        if event.event_type == "execution_verified"
    ]
    assert len(verified_events) == 1
    assert verified_events[0].details["verification_status"] == "verified"


def test_trash_mismatch_when_file_still_exists(repository, rag_port, tmp_path) -> None:
    # RecordingFileExecutor 谎报 completed 但不删文件：
    # 读回发现文件仍存在 -> MISMATCH + VerificationMismatchError + 恢复任务。
    executor = RecordingFileExecutor()
    service = _trash_service(repository, rag_port, tmp_path, executor)
    actor, _ = _seed_trash_asset(service, repository, executor, tmp_path)
    assert (tmp_path / "organized" / "report.txt").exists()

    plan_outcome = service.create_plan(actor, (_plan_trash_operation(),), EXPIRES_AT)
    confirmed = service.confirm_plan(
        actor,
        plan_outcome.plan.plan_id,
        plan_outcome.plan.plan_hash,
        "idem-trash-lie-1",
    )
    assert confirmed.approval is not None
    with pytest.raises(VerificationMismatchError):
        service.decide_approval(
            _approver_actor(),
            confirmed.approval.approval_id,
            "approved",
            plan_outcome.plan.plan_hash,
            "idem-trash-lie-2",
        )

    assert (tmp_path / "organized" / "report.txt").exists()
    assert repository.get_plan(plan_outcome.plan.plan_id).state == "mismatch"
    job = repository.find_execution_job(
        plan_outcome.plan.plan_id,
        plan_outcome.plan.plan_hash,
        "idem-trash-lie-2",
    )
    assert job is not None
    assert job.state == "mismatch"
    failed_events = [
        event
        for event in repository.list_audit_events()
        if event.event_type == "execution_verification_failed"
    ]
    assert len(failed_events) == 1
    assert failed_events[0].details["reason"] == "trash_readback_failed"