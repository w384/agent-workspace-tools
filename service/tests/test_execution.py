import importlib
import json
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

    assert not source_file.exists()
    assert destination_file.read_bytes() == b"draft content"
    assert not trash_source.exists()
    assert trashed_file.read_bytes() == b"old content"
    assert result["plan_id"] == plan["plan_id"]
    assert result["status"] == "completed"
    assert result["file_count"] == 2
    assert stored_plan["status"] == "completed"
    assert stored_plan["completed_at"]
