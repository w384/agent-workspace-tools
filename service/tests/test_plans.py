import importlib
import json
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier
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


def test_read_plan_status_excludes_operations_and_token_hash(
    tmp_path: Path,
):
    plans_module = importlib.import_module("service.app.plans")
    workspace_root = tmp_path / "workspace"
    workspace_root.mkdir()
    (workspace_root / "notes.txt").write_text(
        "hello",
        encoding="utf-8",
    )
    plan = plans_module.create_plan(
        workspace_root,
        operations=[{
            "action": "move_rename",
            "source": "notes.txt",
            "destination": "archive/notes.txt",
        }],
    )
    plans_module.issue_approval_token(
        workspace_root,
        plan_id=plan["plan_id"],
    )

    result = plans_module.read_plan_status(
        workspace_root,
        plan_id=plan["plan_id"],
    )

    assert result["status"] == "approved"
    assert "operations" not in result
    assert "approval_token_hash" not in result


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
        expected_plan_hash=plan["plan_hash"],
    )
    assert consumed_plan["status"] == "executing"

    with pytest.raises(
        plans_module.ApprovalTokenAlreadyUsedError
    ):
        plans_module.consume_approval_token(
            workspace_root,
            plan_id=plan["plan_id"],
            token=token,
            expected_plan_hash=plan["plan_hash"],
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
            expected_plan_hash=plan["plan_hash"],
        )

    consumed_plan = plans_module.consume_approval_token(
        workspace_root,
        plan_id=plan["plan_id"],
        token=token,
        expected_plan_hash=plan["plan_hash"],
    )
    assert consumed_plan["status"] == "executing"


def test_plan_id_rejects_path_traversal(
    tmp_path: Path,
):
    """外部输入的计划编号不能逃出内部 plans 目录。"""
    plans_module = importlib.import_module("service.app.plans")
    workspace_root = tmp_path / "workspace"
    plans_directory = (
        workspace_root / ".file-manager" / "plans"
    )
    plans_directory.mkdir(parents=True)

    escaped_plan_path = workspace_root / "escaped.json"
    escaped_plan = {
        "plan_id": "../../escaped",
        "status": "pending_confirmation",
    }
    escaped_plan_path.write_text(
        json.dumps(escaped_plan),
        encoding="utf-8",
    )
    original_text = escaped_plan_path.read_text(
        encoding="utf-8"
    )

    with pytest.raises(
        ValueError,
        match="计划编号无效",
    ):
        plans_module.issue_approval_token(
            workspace_root,
            plan_id="../../escaped",
        )

    assert escaped_plan_path.read_text(
        encoding="utf-8"
    ) == original_text


def test_concurrent_token_consumption_allows_one_success(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    """并发消费同一令牌时只能有一个请求进入执行状态。"""
    plans_module = importlib.import_module("service.app.plans")
    workspace_root, plan = _create_single_move_plan(
        plans_module,
        tmp_path,
    )
    token = plans_module.issue_approval_token(
        workspace_root,
        plan_id=plan["plan_id"],
    )

    real_write_plan = plans_module._write_plan

    def slow_executing_write(root: Path, stored_plan: dict):
        if stored_plan.get("status") == "executing":
            time.sleep(0.05)
        return real_write_plan(root, stored_plan)

    monkeypatch.setattr(
        plans_module,
        "_write_plan",
        slow_executing_write,
    )

    worker_count = 6
    start_barrier = Barrier(worker_count)

    def consume_once():
        start_barrier.wait()
        try:
            plans_module.consume_approval_token(
                workspace_root,
                plan_id=plan["plan_id"],
                token=token,
                expected_plan_hash=plan["plan_hash"],
            )
            return "success"
        except Exception as error:
            return error

    with ThreadPoolExecutor(
        max_workers=worker_count
    ) as executor:
        results = list(
            executor.map(
                lambda _: consume_once(),
                range(worker_count),
            )
        )

    successes = [result for result in results if result == "success"]
    failures = [result for result in results if result != "success"]
    assert len(successes) == 1
    assert len(failures) == worker_count - 1
    assert all(
        isinstance(
            failure,
            plans_module.ApprovalTokenAlreadyUsedError,
        )
        for failure in failures
    )
