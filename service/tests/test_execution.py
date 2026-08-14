import importlib
import json
from datetime import datetime, timedelta
from pathlib import Path

import pytest


def test_execute_plan_applies_create_move_and_trash(
    tmp_path: Path,
):
    """已确认计划必须完成创建、移动重命名和回收操作。"""
    plans_module = importlib.import_module("service.app.plans")
    try:
        execution_module = importlib.import_module(
            "service.app.execution"
        )
    except ModuleNotFoundError:
        pytest.fail("service.app.execution 尚未实现")

    workspace_root = tmp_path / "workspace"
    incoming_directory = workspace_root / "incoming"
    incoming_directory.mkdir(parents=True)

    source_file = incoming_directory / "draft.txt"
    source_file.write_bytes(b"draft content")
    trash_source = workspace_root / "old-notes.txt"
    trash_source.write_bytes(b"old content")

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

    result = execution_module.execute_plan(
        workspace_root,
        plan_id=plan["plan_id"],
        approval_token=token,
        expected_plan_hash=plan["plan_hash"],
    )

    destination_file = workspace_root / "sorted" / "final.txt"
    trashed_file = (
        workspace_root
        / ".trash"
        / plan["plan_id"]
        / "old-notes.txt"
    )
    plan_path = (
        workspace_root
        / ".file-manager"
        / "plans"
        / f"{plan['plan_id']}.json"
    )
    stored_plan = json.loads(
        plan_path.read_text(encoding="utf-8")
    )
    operation_log_path = (
        workspace_root
        / ".file-manager"
        / "operations"
        / f"{plan['plan_id']}.json"
    )

    assert not source_file.exists()
    assert destination_file.read_bytes() == b"draft content"
    assert not trash_source.exists()
    assert trashed_file.read_bytes() == b"old content"
    assert result["plan_id"] == plan["plan_id"]
    assert result["status"] == "completed"
    assert result["file_count"] == 2
    assert stored_plan["status"] == "completed"
    assert stored_plan["completed_at"]
    assert result["operation_id"] == plan["plan_id"]
    assert operation_log_path.is_file()

    operation_log = json.loads(
        operation_log_path.read_text(encoding="utf-8")
    )
    completed_at = datetime.fromisoformat(
        operation_log["completed_at"]
    )
    expires_at = datetime.fromisoformat(
        operation_log["expires_at"]
    )
    assert expires_at - completed_at == timedelta(days=14)
    assert operation_log["status"] == "completed"
    assert operation_log["undo_actions"] == [
        {
            "action": "move",
            "source": (
                f".trash/{plan['plan_id']}/old-notes.txt"
            ),
            "destination": "old-notes.txt",
        },
        {
            "action": "move",
            "source": "sorted/final.txt",
            "destination": "incoming/draft.txt",
        },
        {
            "action": "remove_folder",
            "path": "sorted",
        },
    ]


def test_execute_plan_preflight_conflict_changes_no_files(
    tmp_path: Path,
):
    """确认后出现目标冲突时，整批计划必须一个文件也不动。"""
    plans_module = importlib.import_module("service.app.plans")
    operations_module = importlib.import_module(
        "service.app.operations"
    )
    execution_module = importlib.import_module(
        "service.app.execution"
    )

    workspace_root = tmp_path / "workspace"
    incoming_directory = workspace_root / "incoming"
    sorted_directory = workspace_root / "sorted"
    incoming_directory.mkdir(parents=True)
    sorted_directory.mkdir()

    source_file = incoming_directory / "notes.txt"
    source_file.write_bytes(b"source")
    destination_file = sorted_directory / "notes.txt"

    plan = plans_module.create_plan(
        workspace_root,
        operations=[
            {
                "action": "move_rename",
                "source": "incoming/notes.txt",
                "destination": "sorted/notes.txt",
            }
        ],
    )
    token = plans_module.issue_approval_token(
        workspace_root,
        plan_id=plan["plan_id"],
    )

    destination_file.write_bytes(b"new conflict")

    with pytest.raises(
        operations_module.DestinationAlreadyExistsError
    ):
        execution_module.execute_plan(
            workspace_root,
            plan_id=plan["plan_id"],
            approval_token=token,
            expected_plan_hash=plan["plan_hash"],
        )

    stored_plan = json.loads(
        (
            workspace_root
            / ".file-manager"
            / "plans"
            / f"{plan['plan_id']}.json"
        ).read_text(encoding="utf-8")
    )
    assert source_file.read_bytes() == b"source"
    assert destination_file.read_bytes() == b"new conflict"
    assert stored_plan["status"] == "failed"
    assert stored_plan["rollback_status"] == "completed"


def test_execute_plan_rolls_back_completed_actions_on_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    """执行中任一操作失败时，已经完成的操作必须逆序撤销。"""
    plans_module = importlib.import_module("service.app.plans")
    execution_module = importlib.import_module(
        "service.app.execution"
    )

    workspace_root = tmp_path / "workspace"
    incoming_directory = workspace_root / "incoming"
    incoming_directory.mkdir(parents=True)
    first_source = incoming_directory / "first.txt"
    second_source = incoming_directory / "second.txt"
    first_source.write_bytes(b"first")
    second_source.write_bytes(b"second")

    plan = plans_module.create_plan(
        workspace_root,
        operations=[
            {
                "action": "create_folder",
                "destination": "sorted",
            },
            {
                "action": "move_rename",
                "source": "incoming/first.txt",
                "destination": "sorted/first.txt",
            },
            {
                "action": "move_rename",
                "source": "incoming/second.txt",
                "destination": "sorted/second.txt",
            },
        ],
    )
    token = plans_module.issue_approval_token(
        workspace_root,
        plan_id=plan["plan_id"],
    )

    real_move = execution_module.shutil.move
    move_count = 0

    def fail_second_move(source: str, destination: str):
        nonlocal move_count
        move_count += 1
        if move_count == 2:
            raise RuntimeError("simulated move failure")
        return real_move(source, destination)

    monkeypatch.setattr(
        execution_module.shutil,
        "move",
        fail_second_move,
    )

    with pytest.raises(
        RuntimeError,
        match="simulated move failure",
    ):
        execution_module.execute_plan(
            workspace_root,
            plan_id=plan["plan_id"],
            approval_token=token,
            expected_plan_hash=plan["plan_hash"],
        )

    stored_plan = json.loads(
        (
            workspace_root
            / ".file-manager"
            / "plans"
            / f"{plan['plan_id']}.json"
        ).read_text(encoding="utf-8")
    )
    assert first_source.read_bytes() == b"first"
    assert second_source.read_bytes() == b"second"
    assert not (workspace_root / "sorted").exists()
    assert stored_plan["status"] == "failed"
    assert stored_plan["rollback_status"] == "completed"


def test_execute_plan_rejects_tampered_operations_before_writing(
    tmp_path: Path,
):
    """确认后的计划内容变化时，不得消费令牌或移动文件。"""
    plans_module = importlib.import_module("service.app.plans")
    execution_module = importlib.import_module(
        "service.app.execution"
    )

    workspace_root = tmp_path / "workspace"
    workspace_root.mkdir()
    source_file = workspace_root / "source.txt"
    source_file.write_bytes(b"original")

    plan = plans_module.create_plan(
        workspace_root,
        operations=[
            {
                "action": "move_rename",
                "source": "source.txt",
                "destination": "safe.txt",
            }
        ],
    )
    token = plans_module.issue_approval_token(
        workspace_root,
        plan_id=plan["plan_id"],
    )
    plan_path = (
        workspace_root
        / ".file-manager"
        / "plans"
        / f"{plan['plan_id']}.json"
    )
    stored_plan = json.loads(
        plan_path.read_text(encoding="utf-8")
    )
    stored_plan["operations"][0]["destination"] = "tampered.txt"
    plan_path.write_text(
        json.dumps(stored_plan, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(plans_module.PlanIntegrityError):
        execution_module.execute_plan(
            workspace_root,
            plan_id=plan["plan_id"],
            approval_token=token,
            expected_plan_hash=plan["plan_hash"],
        )

    rejected_plan = json.loads(
        plan_path.read_text(encoding="utf-8")
    )
    assert source_file.read_bytes() == b"original"
    assert not (workspace_root / "safe.txt").exists()
    assert not (workspace_root / "tampered.txt").exists()
    assert rejected_plan["status"] == "approved"
    assert "approval_token_hash" in rejected_plan


def test_execute_plan_cannot_bypass_integrity_with_restore_type(
    tmp_path: Path,
):
    """篡改计划类型不得绕过普通计划的完整性校验。"""
    plans_module = importlib.import_module("service.app.plans")
    execution_module = importlib.import_module(
        "service.app.execution"
    )

    workspace_root = tmp_path / "workspace"
    workspace_root.mkdir()
    source_file = workspace_root / "source.txt"
    source_file.write_bytes(b"original")
    plan = plans_module.create_plan(
        workspace_root,
        operations=[
            {
                "action": "move_rename",
                "source": "source.txt",
                "destination": "safe.txt",
            }
        ],
    )
    token = plans_module.issue_approval_token(
        workspace_root,
        plan_id=plan["plan_id"],
    )
    plan_path = (
        workspace_root
        / ".file-manager"
        / "plans"
        / f"{plan['plan_id']}.json"
    )
    stored_plan = json.loads(
        plan_path.read_text(encoding="utf-8")
    )
    stored_plan["plan_type"] = "restore"
    stored_plan["operations"][0]["destination"] = "tampered.txt"
    plan_path.write_text(
        json.dumps(stored_plan, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(plans_module.PlanIntegrityError):
        execution_module.execute_plan(
            workspace_root,
            plan_id=plan["plan_id"],
            approval_token=token,
            expected_plan_hash=plan["plan_hash"],
        )

    rejected_plan = json.loads(
        plan_path.read_text(encoding="utf-8")
    )
    assert source_file.read_bytes() == b"original"
    assert not (workspace_root / "safe.txt").exists()
    assert not (workspace_root / "tampered.txt").exists()
    assert rejected_plan["status"] == "approved"
    assert "approval_token_hash" in rejected_plan


def test_execute_plan_requires_independent_expected_plan_hash(
    tmp_path: Path,
):
    """同步重算同文件摘要也不能绕过确认时的独立哈希。"""
    plans_module = importlib.import_module("service.app.plans")
    execution_module = importlib.import_module(
        "service.app.execution"
    )

    workspace_root = tmp_path / "workspace"
    workspace_root.mkdir()
    source_file = workspace_root / "source.txt"
    source_file.write_bytes(b"original")
    plan = plans_module.create_plan(
        workspace_root,
        operations=[
            {
                "action": "move_rename",
                "source": "source.txt",
                "destination": "safe.txt",
            }
        ],
    )
    expected_plan_hash = plan["plan_hash"]
    token = plans_module.issue_approval_token(
        workspace_root,
        plan_id=plan["plan_id"],
    )
    plan_path = (
        workspace_root
        / ".file-manager"
        / "plans"
        / f"{plan['plan_id']}.json"
    )
    approved_plan = json.loads(
        plan_path.read_text(encoding="utf-8")
    )
    tampered_plan = json.loads(json.dumps(approved_plan))
    tampered_plan["operations"][0]["destination"] = "tampered.txt"
    tampered_plan["plan_hash"] = plans_module._calculate_plan_hash(
        tampered_plan["plan_id"],
        tampered_plan["operations"],
        plan_type=tampered_plan.get("plan_type"),
        operation_id=tampered_plan.get("operation_id"),
    )
    plan_path.write_text(
        json.dumps(tampered_plan, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(plans_module.PlanIntegrityError):
        execution_module.execute_plan(
            workspace_root,
            plan_id=plan["plan_id"],
            approval_token=token,
            expected_plan_hash=expected_plan_hash,
        )

    assert source_file.read_bytes() == b"original"
    assert not (workspace_root / "safe.txt").exists()
    assert not (workspace_root / "tampered.txt").exists()

    plan_path.write_text(
        json.dumps(approved_plan, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    result = execution_module.execute_plan(
        workspace_root,
        plan_id=plan["plan_id"],
        approval_token=token,
        expected_plan_hash=expected_plan_hash,
    )

    assert result["status"] == "completed"
    assert (workspace_root / "safe.txt").read_bytes() == b"original"


def test_execute_plan_revalidates_source_fingerprint_before_consuming_token(
    tmp_path: Path,
):
    plans_module = importlib.import_module("service.app.plans")
    execution_module = importlib.import_module(
        "service.app.execution"
    )

    workspace_root = tmp_path / "workspace"
    workspace_root.mkdir()
    source_file = workspace_root / "source.txt"
    source_file.write_bytes(b"approved content")
    plan = plans_module.create_plan(
        workspace_root,
        operations=[
            {
                "action": "move_rename",
                "source": "source.txt",
                "destination": "safe.txt",
            }
        ],
    )
    token = plans_module.issue_approval_token(
        workspace_root,
        plan_id=plan["plan_id"],
    )

    source_file.write_bytes(b"changed after confirmation")

    with pytest.raises(plans_module.PlanSourceChangedError):
        execution_module.execute_plan(
            workspace_root,
            plan_id=plan["plan_id"],
            approval_token=token,
            expected_plan_hash=plan["plan_hash"],
        )

    plan_path = (
        workspace_root
        / ".file-manager"
        / "plans"
        / f"{plan['plan_id']}.json"
    )
    rejected_plan = json.loads(
        plan_path.read_text(encoding="utf-8")
    )
    assert rejected_plan["status"] == "approved"
    assert "approval_token_hash" in rejected_plan
    assert source_file.read_bytes() == b"changed after confirmation"
    assert not (workspace_root / "safe.txt").exists()

    source_file.write_bytes(b"approved content")
    completed = execution_module.execute_plan(
        workspace_root,
        plan_id=plan["plan_id"],
        approval_token=token,
        expected_plan_hash=plan["plan_hash"],
    )
    assert completed["status"] == "completed"
    assert (workspace_root / "safe.txt").read_bytes() == b"approved content"
