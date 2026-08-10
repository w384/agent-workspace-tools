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


class ExecutionRollbackError(RuntimeError):
    """执行失败后，至少一项回滚操作也失败。"""


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


def _create_directory(
    destination: Path,
    applied_actions: list[dict[str, Any]],
) -> None:
    missing_directories: list[Path] = []
    current = destination

    while not current.exists():
        missing_directories.append(current)
        current = current.parent

    destination.mkdir(parents=True, exist_ok=False)
    for directory in reversed(missing_directories):
        applied_actions.append({
            "action": "create_folder",
            "path": directory,
        })


def _remove_empty_trash_directories(
    workspace_root: Path,
    destination: Path,
) -> None:
    trash_root = workspace_root.resolve() / ".trash"
    current = destination.parent

    while current != trash_root and current.exists():
        try:
            current.rmdir()
        except OSError:
            break
        current = current.parent


def _rollback_actions(
    workspace_root: Path,
    applied_actions: list[dict[str, Any]],
) -> None:
    rollback_errors: list[str] = []

    for applied_action in reversed(applied_actions):
        try:
            action = applied_action["action"]

            if action == "create_folder":
                path = applied_action["path"]
                if path.exists():
                    path.rmdir()
                continue

            source = applied_action["source"]
            destination = applied_action["destination"]
            if destination.exists():
                source.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(destination), str(source))

            if action == "trash":
                _remove_empty_trash_directories(
                    workspace_root,
                    destination,
                )
        except Exception as error:
            rollback_errors.append(str(error))

    if rollback_errors:
        raise ExecutionRollbackError(
            "；".join(rollback_errors)
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

    applied_actions: list[dict[str, Any]] = []

    try:
        preview_operations(
            workspace_root,
            operations=plan["operations"],
        )

        for operation in plan["operations"]:
            if operation["action"] != "trash":
                continue

            destination = _trash_destination(
                workspace_root,
                plan_id,
                operation["source"],
            )
            if destination.exists():
                raise FileExistsError(
                    f"回收目标已经存在：{operation['source']}"
                )

        for operation in plan["operations"]:
            if operation["action"] != "create_folder":
                continue

            destination = resolve_workspace_path(
                workspace_root,
                operation["destination"],
            )
            _create_directory(destination, applied_actions)

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
                applied_actions.append({
                    "action": action,
                    "source": source,
                    "destination": destination,
                })
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
                destination.parent.mkdir(
                    parents=True,
                    exist_ok=True,
                )
                shutil.move(str(source), str(destination))
                applied_actions.append({
                    "action": action,
                    "source": source,
                    "destination": destination,
                })

        plan["status"] = "completed"
        plan["completed_at"] = _utc_now()
        _write_plan(workspace_root, plan)
        return plan
    except Exception as execution_error:
        try:
            _rollback_actions(workspace_root, applied_actions)
            plan["status"] = "failed"
            plan["rollback_status"] = "completed"
        except ExecutionRollbackError as rollback_error:
            plan["status"] = "rollback_failed"
            plan["rollback_status"] = "failed"
            plan["rollback_error"] = str(rollback_error)

        plan["failed_at"] = _utc_now()
        plan["error_type"] = type(execution_error).__name__
        plan["error_message"] = str(execution_error)
        _write_plan(workspace_root, plan)

        if plan["rollback_status"] == "failed":
            raise ExecutionRollbackError(
                "执行失败，并且自动回滚未能全部完成"
            ) from execution_error
        raise
