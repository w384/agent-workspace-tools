import importlib
import json
from pathlib import Path
from uuid import UUID

import pytest


def _execute_recoverable_operation(
    tmp_path: Path,
) -> tuple[Path, dict]:
    plans_module = importlib.import_module("service.app.plans")
    execution_module = importlib.import_module(
        "service.app.execution"
    )

    workspace_root = tmp_path / "workspace"
    incoming_directory = workspace_root / "incoming"
    incoming_directory.mkdir(parents=True)
    (incoming_directory / "draft.txt").write_bytes(b"draft")
    (workspace_root / "old-notes.txt").write_bytes(b"old")

    plan = plans_module.create_plan(
        workspace_root,
        operations=[
            {
                "action": "create_folder",
                "destination": "sorted",
            },
            {
                "action": "move_rename",
                "source": "incoming/draft.txt",
                "destination": "sorted/final.txt",
            },
            {
                "action": "trash",
                "source": "old-notes.txt",
            },
        ],
    )
    token = plans_module.issue_approval_token(
        workspace_root,
        plan_id=plan["plan_id"],
    )
    completed_plan = execution_module.execute_plan(
        workspace_root,
        plan_id=plan["plan_id"],
        approval_token=token,
    )
    return workspace_root, completed_plan


def test_create_restore_plan_persists_confirmation_without_changes(
    tmp_path: Path,
):
    """恢复必须先生成待确认计划，不能立即修改文件。"""
    workspace_root, completed_plan = (
        _execute_recoverable_operation(tmp_path)
    )
    try:
        restore_module = importlib.import_module(
            "service.app.restore"
        )
    except ModuleNotFoundError:
        pytest.fail("service.app.restore 尚未实现")

    restore_plan = restore_module.create_restore_plan(
        workspace_root,
        operation_id=completed_plan["operation_id"],
    )

    UUID(restore_plan["plan_id"])
    assert restore_plan["plan_type"] == "restore"
    assert restore_plan["status"] == "pending_confirmation"
    assert restore_plan["operation_id"] == completed_plan["operation_id"]
    assert restore_plan["file_count"] == 2
    assert restore_plan["confirmation"] == {
        "restore_moves": [
            {
                "current_path": (
                    f".trash/{completed_plan['operation_id']}"
                    "/old-notes.txt"
                ),
                "original_path": "old-notes.txt",
            },
            {
                "current_path": "sorted/final.txt",
                "original_path": "incoming/draft.txt",
            },
        ],
        "folders_to_remove": ["sorted"],
    }

    assert (workspace_root / "sorted" / "final.txt").is_file()
    assert not (
        workspace_root / "incoming" / "draft.txt"
    ).exists()
    assert (
        workspace_root
        / ".trash"
        / completed_plan["operation_id"]
        / "old-notes.txt"
    ).is_file()

    restore_plan_path = (
        workspace_root
        / ".file-manager"
        / "plans"
        / f"{restore_plan['plan_id']}.json"
    )
    assert json.loads(
        restore_plan_path.read_text(encoding="utf-8")
    ) == restore_plan


def test_create_restore_plan_rejects_expired_operation(
    tmp_path: Path,
):
    """超过14天恢复窗口的操作不能再生成恢复计划。"""
    workspace_root, completed_plan = (
        _execute_recoverable_operation(tmp_path)
    )
    restore_module = importlib.import_module("service.app.restore")
    operation_log_path = (
        workspace_root
        / ".file-manager"
        / "operations"
        / f"{completed_plan['operation_id']}.json"
    )
    operation_log = json.loads(
        operation_log_path.read_text(encoding="utf-8")
    )
    operation_log["expires_at"] = "2000-01-01T00:00:00+00:00"
    operation_log_path.write_text(
        json.dumps(operation_log),
        encoding="utf-8",
    )

    with pytest.raises(restore_module.RestoreWindowExpiredError):
        restore_module.create_restore_plan(
            workspace_root,
            operation_id=completed_plan["operation_id"],
        )


def test_restore_operation_restores_files_and_marks_log(
    tmp_path: Path,
):
    """已确认恢复计划必须还原文件、目录和操作状态。"""
    workspace_root, completed_plan = (
        _execute_recoverable_operation(tmp_path)
    )
    plans_module = importlib.import_module("service.app.plans")
    restore_module = importlib.import_module("service.app.restore")

    restore_plan = restore_module.create_restore_plan(
        workspace_root,
        operation_id=completed_plan["operation_id"],
    )
    token = plans_module.issue_approval_token(
        workspace_root,
        plan_id=restore_plan["plan_id"],
    )
    result = restore_module.restore_operation(
        workspace_root,
        plan_id=restore_plan["plan_id"],
        approval_token=token,
    )

    restored_draft = (
        workspace_root / "incoming" / "draft.txt"
    )
    restored_notes = workspace_root / "old-notes.txt"
    assert restored_draft.read_bytes() == b"draft"
    assert restored_notes.read_bytes() == b"old"
    assert not (workspace_root / "sorted").exists()
    assert not (
        workspace_root
        / ".trash"
        / completed_plan["operation_id"]
    ).exists()
    assert result["status"] == "completed"
    assert result["plan_type"] == "restore"

    operation_log_path = (
        workspace_root
        / ".file-manager"
        / "operations"
        / f"{completed_plan['operation_id']}.json"
    )
    original_plan_path = (
        workspace_root
        / ".file-manager"
        / "plans"
        / f"{completed_plan['plan_id']}.json"
    )
    operation_log = json.loads(
        operation_log_path.read_text(encoding="utf-8")
    )
    original_plan = json.loads(
        original_plan_path.read_text(encoding="utf-8")
    )
    assert operation_log["status"] == "restored"
    assert operation_log["restored_at"]
    assert original_plan["status"] == "restored"

    with pytest.raises(
        restore_module.OperationNotRestorableError
    ):
        restore_module.create_restore_plan(
            workspace_root,
            operation_id=completed_plan["operation_id"],
        )


def test_restore_expiring_after_approval_resets_operation_state(
    tmp_path: Path,
):
    """令牌签发后日志过期时，恢复计划不能卡在执行状态。"""
    workspace_root, completed_plan = (
        _execute_recoverable_operation(tmp_path)
    )
    plans_module = importlib.import_module("service.app.plans")
    restore_module = importlib.import_module("service.app.restore")

    restore_plan = restore_module.create_restore_plan(
        workspace_root,
        operation_id=completed_plan["operation_id"],
    )
    token = plans_module.issue_approval_token(
        workspace_root,
        plan_id=restore_plan["plan_id"],
    )

    operation_log_path = (
        workspace_root
        / ".file-manager"
        / "operations"
        / f"{completed_plan['operation_id']}.json"
    )
    operation_log = json.loads(
        operation_log_path.read_text(encoding="utf-8")
    )
    operation_log["expires_at"] = "2000-01-01T00:00:00+00:00"
    operation_log_path.write_text(
        json.dumps(operation_log),
        encoding="utf-8",
    )

    with pytest.raises(restore_module.RestoreWindowExpiredError):
        restore_module.restore_operation(
            workspace_root,
            plan_id=restore_plan["plan_id"],
            approval_token=token,
        )

    restore_plan_path = (
        workspace_root
        / ".file-manager"
        / "plans"
        / f"{restore_plan['plan_id']}.json"
    )
    stored_restore_plan = json.loads(
        restore_plan_path.read_text(encoding="utf-8")
    )
    stored_operation_log = json.loads(
        operation_log_path.read_text(encoding="utf-8")
    )
    assert stored_restore_plan["status"] == "failed"
    assert stored_restore_plan["rollback_status"] == "completed"
    assert stored_operation_log["status"] == "completed"
    assert "restore_plan_id" not in stored_operation_log
    assert (workspace_root / "sorted" / "final.txt").is_file()
