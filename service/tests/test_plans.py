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
