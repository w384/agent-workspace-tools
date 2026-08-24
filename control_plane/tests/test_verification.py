"""Independent read-back verification adapter tests.

验证「可验证执行」原则：执行器声称完成后，控制面独立读回受控目录的真实状态
（文件存在性 + SHA-256），仅在读回结果与计划期望目标状态一致时才标记 VERIFIED。
若执行器谎报成功但实际未写入，job/plan 落入 MISMATCH 并抛 VerificationMismatchError。

覆盖四类场景：
  1. 正例：真实写盘 executor -> 读回指纹一致 -> VERIFIED（job/plan=verified + 审计留痕）
  2. 反例：执行器谎报（completed 但磁盘无文件）-> MISMATCH + 异常
  3. 兼容性：未注入 verification_port -> 保持旧行为 completed
  4. UNKNOWN：非文件级操作无法独立读回 -> UNKNOWN
"""

import hashlib
from pathlib import Path

import pytest

from control_plane.app.domain import (
    DecisionState,
    Plan,
    TrustedActorContext,
)
from control_plane.app.ports import (
    ExecutionResult,
    UploadResult,
    VerificationStatus,
)
from control_plane.app.service import (
    ControlPlaneService,
    VerificationMismatchError,
)
from control_plane.app.verification import ControlledDirectoryVerifier

from conftest import RecordingFileExecutor


EXPIRES_AT = "2099-01-01T00:00:00+08:00"


def _actor() -> TrustedActorContext:
    return TrustedActorContext(
        actor_id="user-a",
        workspace_id="workspace-a",
        context_version="acl_2026_08_13",
        session_id="session-verif-a",
        request_id="request-verif-a",
        run_id="run-verif-a",
        group_ids=frozenset({"staff"}),
        role_ids=frozenset({"role-member-demo"}),
    )


def _activate_uploaded_version(repository, version) -> None:
    for state in ("parsing", "indexed", "ready"):
        repository.transition_asset_version(version.asset_version_id, state)
    activated = repository.activate_asset_version(version.asset_version_id)
    assert activated is not None


class RealWritingExecutor(RecordingFileExecutor):
    """Executor that actually writes the file to disk and reports the real SHA-256."""

    def __init__(self, base_dir: Path) -> None:
        super().__init__()
        self._base_dir = base_dir

    def upload(self, actor, directory, file_name, content, request_id):
        super().upload(actor, directory, file_name, content, request_id)
        target = self._base_dir / directory / file_name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
        digest = hashlib.sha256(content).hexdigest()
        self.result = UploadResult(
            path=f"{directory.rstrip('/')}/{file_name}",
            name=file_name,
            size_bytes=len(content),
            content_fingerprint=f"sha256:{digest}",
        )
        return self.result


def _seed_uploaded_asset(
    service, repository, executor, content=b"verification read-back real content"
):
    actor = _actor()
    outcome = service.upload(actor, "organized", "report.txt", content)
    _activate_uploaded_version(repository, outcome.asset_version)
    return actor, outcome


def _plan_upload_operation() -> dict[str, object]:
    return {
        "operation_id": "op-upload-1",
        "type": "upload",
        "source_path": "organized/report.txt",
    }


def test_verified_when_real_readback_matches(repository, rag_port, tmp_path) -> None:
    executor = RealWritingExecutor(tmp_path)
    service = ControlPlaneService(
        repository,
        executor,
        rag_port,
        approver_role_id="role-approver-demo",
        verification_port=ControlledDirectoryVerifier(tmp_path),
    )
    content = b"verification read-back real content 2026"
    actor, _ = _seed_uploaded_asset(service, repository, executor, content)

    plan_outcome = service.create_plan(actor, (_plan_upload_operation(),), EXPIRES_AT)
    confirmed = service.confirm_plan(
        actor,
        plan_outcome.plan.plan_id,
        plan_outcome.plan.plan_hash,
        "idem-verif-ok-1",
    )

    assert confirmed.execution_job.state == "verified"
    assert repository.get_plan(plan_outcome.plan.plan_id).state == "verified"
    verified_events = [
        event
        for event in repository.list_audit_events()
        if event.event_type == "execution_verified"
    ]
    assert len(verified_events) == 1
    details = verified_events[0].details
    assert details["verification_status"] == "verified"
    assert details["evidence"]["entries_checked"] == 1
    expected_entries = details["expected_state"]["entries"]
    assert expected_entries[0]["expected_fingerprint"].startswith("sha256:")
    assert executor.executions, "executor must actually have been invoked"


def test_mismatch_when_executor_lies_about_writing(repository, rag_port, tmp_path) -> None:
    # RecordingFileExecutor 声称 completed 并返回固定指纹，但从不写盘：
    # 读回找不到文件 -> fingerprint_matches=False -> MISMATCH。
    executor = RecordingFileExecutor()
    service = ControlPlaneService(
        repository,
        executor,
        rag_port,
        approver_role_id="role-approver-demo",
        verification_port=ControlledDirectoryVerifier(tmp_path),
    )
    actor, _ = _seed_uploaded_asset(service, repository, executor)

    plan_outcome = service.create_plan(actor, (_plan_upload_operation(),), EXPIRES_AT)
    with pytest.raises(VerificationMismatchError):
        service.confirm_plan(
            actor,
            plan_outcome.plan.plan_id,
            plan_outcome.plan.plan_hash,
            "idem-verif-lie-1",
        )

    assert repository.get_plan(plan_outcome.plan.plan_id).state == "mismatch"
    job = repository.find_execution_job(
        plan_outcome.plan.plan_id,
        plan_outcome.plan.plan_hash,
        "idem-verif-lie-1",
    )
    assert job is not None
    assert job.state == "mismatch"
    failed_events = [
        event
        for event in repository.list_audit_events()
        if event.event_type == "execution_verification_failed"
    ]
    assert len(failed_events) == 1
    assert failed_events[0].details["verification_status"] == "mismatch"
    assert failed_events[0].details["reason"] == "readback_fingerprint_mismatch"


def test_without_verification_port_keeps_completed(
    repository, file_executor, rag_port
) -> None:
    service = ControlPlaneService(
        repository,
        file_executor,
        rag_port,
        approver_role_id="role-approver-demo",
    )
    actor, _ = _seed_uploaded_asset(service, repository, file_executor)

    plan_outcome = service.create_plan(actor, (_plan_upload_operation(),), EXPIRES_AT)
    confirmed = service.confirm_plan(
        actor,
        plan_outcome.plan.plan_id,
        plan_outcome.plan.plan_hash,
        "idem-verif-none-1",
    )
    assert confirmed.execution_job.state == "completed"
    assert repository.get_plan(plan_outcome.plan.plan_id).state == "completed"


def test_verifier_returns_unknown_for_non_file_operation(tmp_path) -> None:
    verifier = ControlledDirectoryVerifier(tmp_path)
    plan = Plan(
        plan_id="plan-unknown",
        workspace_id="workspace-a",
        created_by="user-a",
        state="executing",
        decision_state=DecisionState.DIRECT,
        decision_id="decision-unknown",
        policy_version="policy_2026_08_13",
        context_version="acl_2026_08_13",
        normalized_operations=(
            {
                "operation_id": "op-folder-1",
                "type": "create_folder",
                "source_path": "organized/newfolder",
            },
        ),
        asset_snapshots=(
            {
                "asset_id": "asset-1",
                "asset_version_id": "version-1",
                "content_fingerprint": "sha256:abc",
            },
        ),
        plan_hash="plan-hash",
        executor_plan_id="executor-plan",
        executor_plan_hash="executor-plan-hash",
        acl_snapshot={},
        expires_at=EXPIRES_AT,
    )
    result = verifier.verify(
        _actor(),
        plan,
        ExecutionResult(status="completed", operation_id="op-folder-1"),
    )
    assert result.status is VerificationStatus.UNKNOWN
    assert result.reason == "independent_readback_unavailable"
    assert result.matched is False
    assert result.evidence["unverifiable_operation_ids"] == ["op-folder-1"]
