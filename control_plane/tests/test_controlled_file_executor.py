"""受控目录真实执行器测试（批次 C）。

演示服务接线前的真实缺口：init 脚本里 file_executor=object() 且未注入
verification_port，导致「计划→确认→执行→独立读回验证」链路在运行中的演示
服务上不可用。本文件覆盖 ControlledFileExecutor + ControlledDirectoryVerifier
在受控目录上的真实闭环：

  1. 正例（move_rename / SELF_CONFIRM）：真实移动文件 -> 读回 VERIFIED
     （job/plan=verified + 审计 execution_verified + 目标存在、源消失）
  2. 正例（trash / APPROVAL_REQUIRED）：真实删除 -> 读回 VERIFIED
  3. 反例（路径逃逸）：create_plan 传入越界路径 -> PermissionError
     （执行器层 fail-closed 防御，不依赖 policy 层先拦截）
  4. 单测：upload 真实写盘并返回真实 SHA-256 UploadResult
"""

import hashlib
from pathlib import Path

import pytest

from control_plane.app.controlled_file_executor import ControlledFileExecutor
from control_plane.app.domain import (
    Action,
    DecisionState,
    PermissionGrant,
    PrincipalType,
    TrustedActorContext,
)
from control_plane.app.ports import UploadResult
from control_plane.app.service import ControlPlaneService
from control_plane.app.verification import ControlledDirectoryVerifier

from conftest import AsgiClient
from test_trash_verification import _approver_actor, _add_trash_grant
from test_verification import EXPIRES_AT, _activate_uploaded_version, _actor


def _add_move_grant(repository) -> None:
    repository.add_permission_grant(
        PermissionGrant(
            grant_id="user-a-move",
            workspace_id="workspace-a",
            context_version="acl_2026_08_13",
            principal_type=PrincipalType.USER,
            principal_id="user-a",
            action=Action.MOVE_RENAME,
            path_prefix="organized",
        )
    )


def _executor_service(repository, rag_port, tmp_path) -> ControlPlaneService:
    return ControlPlaneService(
        repository,
        ControlledFileExecutor(tmp_path),
        rag_port,
        approver_role_id="role-approver-demo",
        verification_port=ControlledDirectoryVerifier(tmp_path),
    )


def _seed_uploaded_file(service, repository, content: bytes) -> tuple:
    actor = _actor()
    outcome = service.upload(actor, "organized", "report.txt", content)
    _activate_uploaded_version(repository, outcome.asset_version)
    return actor, outcome


def test_move_rename_verified_after_real_execution(
    repository, rag_port, tmp_path
) -> None:
    _add_move_grant(repository)
    service = _executor_service(repository, rag_port, tmp_path)
    content = b"controlled move real content 2026"
    actor, _ = _seed_uploaded_file(service, repository, content)
    assert (tmp_path / "organized" / "report.txt").read_bytes() == content

    plan_outcome = service.create_plan(
        actor,
        (
            {
                "operation_id": "op-move-1",
                "type": "move_rename",
                "source_path": "organized/report.txt",
                "target_path": "organized/report-moved.txt",
            },
        ),
        EXPIRES_AT,
    )
    assert plan_outcome.plan.decision_state is DecisionState.SELF_CONFIRM
    confirmed = service.confirm_plan(
        actor,
        plan_outcome.plan.plan_id,
        plan_outcome.plan.plan_hash,
        "idem-move-ok-1",
    )

    assert confirmed.execution_job is not None
    assert confirmed.execution_job.state == "verified"
    assert repository.get_plan(plan_outcome.plan.plan_id).state == "verified"
    assert not (tmp_path / "organized" / "report.txt").exists()
    assert (tmp_path / "organized" / "report-moved.txt").read_bytes() == content
    verified_events = [
        event
        for event in repository.list_audit_events()
        if event.event_type == "execution_verified"
    ]
    assert len(verified_events) == 1
    assert verified_events[0].details["verification_status"] == "verified"


def test_trash_verified_after_real_delete(repository, rag_port, tmp_path) -> None:
    _add_trash_grant(repository)
    service = _executor_service(repository, rag_port, tmp_path)
    content = b"controlled trash real content 2026"
    actor, _ = _seed_uploaded_file(service, repository, content)
    assert (tmp_path / "organized" / "report.txt").exists()

    plan_outcome = service.create_plan(
        actor,
        (
            {
                "operation_id": "op-trash-1",
                "type": "trash",
                "source_path": "organized/report.txt",
            },
        ),
        EXPIRES_AT,
    )
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

    assert approved.execution_job is not None
    assert approved.execution_job.state == "verified"
    assert repository.get_plan(plan_outcome.plan.plan_id).state == "verified"
    assert not (tmp_path / "organized" / "report.txt").exists()


def test_executor_rejects_path_escape_on_create_plan(tmp_path) -> None:
    executor = ControlledFileExecutor(tmp_path)
    escaping_operation = {
        "operation_id": "op-move-escape",
        "type": "move_rename",
        "source_path": "organized/ok.txt",
        "target_path": "../escape.txt",
    }
    with pytest.raises(PermissionError):
        executor.create_plan(
            actor=_actor(),
            normalized_operations=(escaping_operation,),
            asset_snapshots=(
                {
                    "asset_id": "asset-1",
                    "asset_version_id": "version-1",
                    "content_fingerprint": "sha256:" + "a" * 64,
                },
            ),
            acl_snapshot={},
            policy_version="policy_2026_08_13",
            expires_at=EXPIRES_AT,
            idempotency_key="idem-escape-1",
        )


def test_executor_upload_writes_real_file_and_fingerprint(tmp_path) -> None:
    executor = ControlledFileExecutor(tmp_path)
    content = b"controlled upload real content 2026"
    result = executor.upload(
        actor=_actor(),
        directory="organized",
        file_name="report.txt",
        content=content,
        request_id="request-upload-1",
    )
    expected_digest = "sha256:" + hashlib.sha256(content).hexdigest()
    assert result.path == "organized/report.txt"
    assert result.name == "report.txt"
    assert result.size_bytes == len(content)
    assert result.content_fingerprint == expected_digest
    written = (tmp_path / "organized" / "report.txt").read_bytes()
    assert written == content


def test_executor_upload_rejects_duplicate_target(tmp_path) -> None:
    executor = ControlledFileExecutor(tmp_path)
    content = b"controlled duplicate content 2026"
    executor.upload(
        actor=_actor(),
        directory="organized",
        file_name="report.txt",
        content=content,
        request_id="request-upload-dup-1",
    )
    with pytest.raises(FileExistsError):
        executor.upload(
            actor=_actor(),
            directory="organized",
            file_name="report.txt",
            content=content,
            request_id="request-upload-dup-2",
        )


def test_demo_wiring_plan_loop_verified_via_http(
    repository, rag_port, demo_identities, tmp_path
) -> None:
    """镜像 init 脚本 main() 的接线：真实执行器 + 验证器传入 create_app。

    验证「计划→确认→执行→读回验证」在演示服务上可用（SELF_CONFIRM 直通）。
    """
    _add_move_grant(repository)
    from control_plane.app.main import create_app

    app = create_app(
        repository=repository,
        file_executor=ControlledFileExecutor(tmp_path),
        rag_port=rag_port,
        demo_identities=demo_identities,
        internal_service_key="demo-internal-key",
        approver_role_id="role-approver-demo",
        verification_port=ControlledDirectoryVerifier(tmp_path),
    )
    client = AsgiClient(app)
    login = client.post(
        "/api/session/login",
        json_body={"username": "alice", "password": "demo-a-password"},
    )
    assert login.status_code == 200

    uploaded = client.post(
        "/api/uploads",
        data={"directory": "organized"},
        files={"file": ("report.txt", b"demo wiring content 2026", "text/plain")},
    )
    assert uploaded.status_code == 200
    version_id = uploaded.json()["asset_version"]["asset_version_id"]
    for state in ("parsing", "indexed", "ready"):
        repository.transition_asset_version(version_id, state)
    repository.activate_asset_version(version_id)

    plan_resp = client.post(
        "/api/plans",
        json_body={
            "operations": [
                {
                    "operation_id": "op-move-1",
                    "type": "move_rename",
                    "source_path": "organized/report.txt",
                    "target_path": "organized/report-moved.txt",
                }
            ],
            "expires_at": EXPIRES_AT,
        },
    )
    assert plan_resp.status_code == 200
    plan = plan_resp.json()["plan"]
    assert plan["decision_state"] == "SELF_CONFIRM"

    confirmed = client.post(
        f"/api/plans/{plan['plan_id']}/confirm",
        json_body={"expected_plan_hash": plan["plan_hash"]},
        headers={"Idempotency-Key": "idem-demo-wiring-1"},
    )
    assert confirmed.status_code == 200
    assert confirmed.json()["execution_job"]["state"] == "verified"
    assert not (tmp_path / "organized" / "report.txt").exists()
    assert (tmp_path / "organized" / "report-moved.txt").read_bytes() == (
        b"demo wiring content 2026"
    )
    verified_events = [
        event
        for event in repository.list_audit_events()
        if event.event_type == "execution_verified"
    ]
    assert len(verified_events) == 1
    assert verified_events[0].details["verification_status"] == "verified"
    assert repository.get_plan(plan["plan_id"]).state == "verified"
