import shutil
from pathlib import Path
from typing import Any

from service.app.operations import preview_operations
from service.app.paths import resolve_workspace_path
from service.app.plans import (
    _utc_now,
    _write_plan,
    consume_approval_token,
)


def _trash_destination(
    workspace_root: Path,
    plan_id: str,
    source: str,
) -> Path:
    return (
        workspace_root.resolve()
        / ".trash"
        / plan_id
        / Path(source)
    )


def execute_plan(
    workspace_root: Path,
    *,
    plan_id: str,
    approval_token: str,
) -> dict[str, Any]:
    """消费一次性令牌并执行已经确认的整理计划。"""
    plan = consume_approval_token(
        workspace_root,
        plan_id=plan_id,
        token=approval_token,
    )

    preview_operations(
        workspace_root,
        operations=plan["operations"],
    )

    for operation in plan["operations"]:
        if operation["action"] != "create_folder":
            continue

        destination = resolve_workspace_path(
            workspace_root,
            operation["destination"],
        )
        destination.mkdir(parents=True, exist_ok=False)

    for operation in plan["operations"]:
        action = operation["action"]

        if action == "move_rename":
            source = resolve_workspace_path(
                workspace_root,
                operation["source"],
            )
            destination = resolve_workspace_path(
                workspace_root,
                operation["destination"],
            )
            shutil.move(str(source), str(destination))
            continue

        if action == "trash":
            source = resolve_workspace_path(
                workspace_root,
                operation["source"],
            )
            destination = _trash_destination(
                workspace_root,
                plan_id,
                operation["source"],
            )
            if destination.exists():
                raise FileExistsError(
                    f"回收目标已经存在：{operation['source']}"
                )
            destination.parent.mkdir(
                parents=True,
                exist_ok=True,
            )
            shutil.move(str(source), str(destination))

    plan["status"] = "completed"
    plan["completed_at"] = _utc_now()
    _write_plan(workspace_root, plan)
    return plan
