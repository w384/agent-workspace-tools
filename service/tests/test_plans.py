import importlib
import json
from pathlib import Path
from uuid import UUID

import pytest


def test_create_plan_persists_confirmation_summary(
    tmp_path: Path,
):
    """整理计划必须持久化，并返回确认界面需要的明细。"""
    try:
        plans_module = importlib.import_module(
            "service.app.plans"
        )
    except ModuleNotFoundError:
        pytest.fail("service.app.plans 尚未实现")

    workspace_root = tmp_path / "workspace"
    incoming_directory = workspace_root / "incoming"
    incoming_directory.mkdir(parents=True)

    (incoming_directory / "report-draft.txt").write_bytes(
        b"report"
    )
    (workspace_root / "old-notes.txt").write_bytes(b"old")

    result = plans_module.create_plan(
        workspace_root,
        operations=[
            {
                "action": "create_folder",
                "destination": "reports",
            },
            {
                "action": "move_rename",
                "source": "incoming/report-draft.txt",
                "destination": "reports/final-report.txt",
            },
            {
                "action": "trash",
                "source": "old-notes.txt",
            },
        ],
    )

    UUID(result["plan_id"])
    assert result["status"] == "pending_confirmation"
    assert result["file_count"] == 2
    assert result["confirmation"] == {
        "folders_to_create": ["reports"],
        "moves": [
            {
                "source": "incoming/report-draft.txt",
                "destination": "reports/final-report.txt",
            }
        ],
        "renames": [
            {
                "source_name": "report-draft.txt",
                "destination_name": "final-report.txt",
            }
        ],
        "trash": ["old-notes.txt"],
    }

    plan_path = (
        workspace_root
        / ".file-manager"
        / "plans"
        / f"{result['plan_id']}.json"
    )
    assert plan_path.is_file()
    assert json.loads(
        plan_path.read_text(encoding="utf-8")
    ) == result


def _create_single_move_plan(
    plans_module,
    tmp_path: Path,
) -> tuple[Path, dict]:
    workspace_root = tmp_path / "workspace"
    workspace_root.mkdir()
    (workspace_root / "notes.txt").write_bytes(b"notes")

    plan = plans_module.create_plan(
        workspace_root,
        operations=[
            {
                "action": "move_rename",
                "source": "notes.txt",
                "destination": "sorted/notes.txt",
            }
        ],
    )
    return workspace_root, plan


def test_approval_token_is_hashed_and_can_only_be_used_once(
    tmp_path: Path,
):
    """确认令牌不能明文保存，而且成功消费后必须失效。"""
    plans_module = importlib.import_module("service.app.plans")
    workspace_root, plan = _create_single_move_plan(
        plans_module,
        tmp_path,
    )

    token = plans_module.issue_approval_token(
        workspace_root,
        plan_id=plan["plan_id"],
    )
    assert token

    plan_path = (
        workspace_root
        / ".file-manager"
        / "plans"
        / f"{plan['plan_id']}.json"
    )
    stored_text = plan_path.read_text(encoding="utf-8")
    stored_plan = json.loads(stored_text)

    assert token not in stored_text
    assert stored_plan["status"] == "approved"
    assert stored_plan["approval_token_hash"]

    consumed_plan = plans_module.consume_approval_token(
        workspace_root,
        plan_id=plan["plan_id"],
        token=token,
    )
    assert consumed_plan["status"] == "executing"

    with pytest.raises(
        plans_module.ApprovalTokenAlreadyUsedError
    ):
        plans_module.consume_approval_token(
            workspace_root,
            plan_id=plan["plan_id"],
            token=token,
        )


def test_invalid_approval_token_does_not_consume_plan(
    tmp_path: Path,
):
    """错误令牌必须被拒绝，且不能影响正确令牌后续使用。"""
    plans_module = importlib.import_module("service.app.plans")
    workspace_root, plan = _create_single_move_plan(
        plans_module,
        tmp_path,
    )
    token = plans_module.issue_approval_token(
        workspace_root,
        plan_id=plan["plan_id"],
    )

    with pytest.raises(
        plans_module.InvalidApprovalTokenError
    ):
        plans_module.consume_approval_token(
            workspace_root,
            plan_id=plan["plan_id"],
            token="incorrect-token",
        )

    consumed_plan = plans_module.consume_approval_token(
        workspace_root,
        plan_id=plan["plan_id"],
        token=token,
    )
    assert consumed_plan["status"] == "executing"
