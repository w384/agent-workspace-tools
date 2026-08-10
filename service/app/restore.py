import shutil
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any
from uuid import uuid4

from service.app.operation_logs import (
    read_operation_log,
    write_operation_log_record,
)
from service.app.paths import (
    PathOutsideWorkspaceError,
    resolve_workspace_path,
)
from service.app.plans import (
    _read_plan,
    _utc_now,
    _write_plan,
    consume_approval_token,
)


class RestoreWindowExpiredError(ValueError):
    """操作已经超过允许恢复的14天窗口。"""


class OperationNotRestorableError(ValueError):
    """操作当前状态不允许创建恢复计划。"""


class RestoreConflictError(FileExistsError):
    """恢复目标已经存在，不能覆盖。"""


class RestoreRollbackError(RuntimeError):
    """恢复失败后，至少一项反向撤销也失败。"""


def _build_restore_confirmation(
    undo_actions: list[dict[str, str]],
) -> dict[str, Any]:
    restore_moves: list[dict[str, str]] = []
    folders_to_remove: list[str] = []

    for action in undo_actions:
        if action["action"] == "move":
            restore_moves.append({
                "current_path": action["source"],
                "original_path": action["destination"],
            })
            continue

        folders_to_remove.append(action["path"])

    return {
        "restore_moves": restore_moves,
        "folders_to_remove": folders_to_remove,
    }


def create_restore_plan(
    workspace_root: Path,
    *,
    operation_id: str,
) -> dict[str, Any]:
    """为仍在恢复窗口内的已完成操作创建待确认计划。"""
    operation_log = read_operation_log(
        workspace_root,
        operation_id=operation_id,
    )
    expires_at = datetime.fromisoformat(
        operation_log["expires_at"]
    )
    if expires_at <= datetime.now(timezone.utc):
        raise RestoreWindowExpiredError(
            "操作已经超过14天恢复窗口"
        )
    if operation_log["status"] != "completed":
        raise OperationNotRestorableError(
            f"操作状态不允许恢复：{operation_log['status']}"
        )

    restore_plan = {
        "plan_id": str(uuid4()),
        "plan_type": "restore",
        "operation_id": operation_log["operation_id"],
        "status": "pending_confirmation",
        "created_at": _utc_now(),
        "file_count": operation_log["file_count"],
        "operations": operation_log["undo_actions"],
        "confirmation": _build_restore_confirmation(
            operation_log["undo_actions"]
        ),
    }
    _write_plan(workspace_root, restore_plan)

    operation_log["status"] = "restore_pending"
    operation_log["restore_plan_id"] = restore_plan["plan_id"]
    operation_log["restore_requested_at"] = _utc_now()
    write_operation_log_record(workspace_root, operation_log)
    return restore_plan


def _trusted_internal_path(
    workspace_root: Path,
    relative_path: str,
) -> Path:
    root = workspace_root.resolve()
    candidate = (root / relative_path).resolve()
    try:
        candidate.relative_to(root)
    except ValueError as error:
        raise PathOutsideWorkspaceError(
            "恢复路径超出允许的工作区"
        ) from error
    return candidate


def _restore_source_path(
    workspace_root: Path,
    operation_id: str,
    relative_path: str,
) -> Path:
    relative = PurePosixPath(relative_path)
    if relative.parts and relative.parts[0] == ".trash":
        if (
            len(relative.parts) < 2
            or relative.parts[1] != operation_id
        ):
            raise OperationNotRestorableError(
                "回收来源不属于当前操作"
            )
        return _trusted_internal_path(
            workspace_root,
            relative_path,
        )
    return resolve_workspace_path(workspace_root, relative_path)


def _preflight_restore(
    workspace_root: Path,
    operation_id: str,
    actions: list[dict[str, str]],
) -> None:
    for action in actions:
        if action["action"] == "move":
            source = _restore_source_path(
                workspace_root,
                operation_id,
                action["source"],
            )
            destination = resolve_workspace_path(
                workspace_root,
                action["destination"],
            )
            if not source.is_file():
                raise FileNotFoundError(
                    f"恢复来源不存在：{action['source']}"
                )
            if destination.exists():
                raise RestoreConflictError(
                    f"恢复目标已经存在：{action['destination']}"
                )
            continue

        if action["action"] != "remove_folder":
            raise OperationNotRestorableError(
                f"不支持的恢复动作：{action['action']}"
            )
        folder = resolve_workspace_path(
            workspace_root,
            action["path"],
        )
        if not folder.is_dir():
            raise FileNotFoundError(
                f"待移除文件夹不存在：{action['path']}"
            )


def _rollback_restore_actions(
    applied_actions: list[dict[str, Any]],
) -> None:
    rollback_errors: list[str] = []

    for action in reversed(applied_actions):
        try:
            if action["action"] == "remove_folder":
                action["path"].mkdir(
                    parents=True,
                    exist_ok=True,
                )
                continue

            source = action["source"]
            destination = action["destination"]
            if destination.exists():
                source.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(destination), str(source))
        except Exception as error:
            rollback_errors.append(str(error))

    if rollback_errors:
        raise RestoreRollbackError("；".join(rollback_errors))


def _remove_empty_operation_trash(
    workspace_root: Path,
    operation_id: str,
) -> None:
    operation_trash = (
        workspace_root.resolve() / ".trash" / operation_id
    )
    if not operation_trash.is_dir():
        return

    directories = sorted(
        (
            path
            for path in operation_trash.rglob("*")
            if path.is_dir()
        ),
        key=lambda path: len(path.parts),
        reverse=True,
    )
    for directory in directories:
        directory.rmdir()
    operation_trash.rmdir()


def restore_operation(
    workspace_root: Path,
    *,
    plan_id: str,
    approval_token: str,
) -> dict[str, Any]:
    """消费一次性令牌并实际恢复原操作。"""
    pending_plan = _read_plan(workspace_root, plan_id)
    if pending_plan.get("plan_type") != "restore":
        raise OperationNotRestorableError("指定计划不是恢复计划")

    plan = consume_approval_token(
        workspace_root,
        plan_id=plan_id,
        token=approval_token,
    )
    operation_id = plan["operation_id"]
    operation_log = read_operation_log(
        workspace_root,
        operation_id=operation_id,
    )
    expires_at = datetime.fromisoformat(
        operation_log["expires_at"]
    )
    if expires_at <= datetime.now(timezone.utc):
        raise RestoreWindowExpiredError(
            "操作已经超过14天恢复窗口"
        )
    if (
        operation_log["status"] != "restore_pending"
        or operation_log.get("restore_plan_id") != plan_id
    ):
        raise OperationNotRestorableError(
            "操作日志与恢复计划状态不匹配"
        )

    applied_actions: list[dict[str, Any]] = []
    original_plan = _read_plan(
        workspace_root,
        operation_log["plan_id"],
    )

    try:
        _preflight_restore(
            workspace_root,
            operation_id,
            plan["operations"],
        )

        for action in plan["operations"]:
            if action["action"] == "move":
                source = _restore_source_path(
                    workspace_root,
                    operation_id,
                    action["source"],
                )
                destination = resolve_workspace_path(
                    workspace_root,
                    action["destination"],
                )
                destination.parent.mkdir(
                    parents=True,
                    exist_ok=True,
                )
                shutil.move(str(source), str(destination))
                applied_actions.append({
                    "action": "move",
                    "source": source,
                    "destination": destination,
                })
                continue

            folder = resolve_workspace_path(
                workspace_root,
                action["path"],
            )
            folder.rmdir()
            applied_actions.append({
                "action": "remove_folder",
                "path": folder,
            })

        restored_at = _utc_now()
        _remove_empty_operation_trash(
            workspace_root,
            operation_id,
        )
        plan["status"] = "completed"
        plan["restored_at"] = restored_at
        operation_log["status"] = "restored"
        operation_log["restored_at"] = restored_at
        original_plan["status"] = "restored"
        original_plan["restored_at"] = restored_at
        _write_plan(workspace_root, plan)
        write_operation_log_record(workspace_root, operation_log)
        _write_plan(workspace_root, original_plan)
        return plan
    except Exception as restore_error:
        try:
            _rollback_restore_actions(applied_actions)
            plan["status"] = "failed"
            plan["rollback_status"] = "completed"
            operation_log["status"] = "completed"
            operation_log.pop("restore_plan_id", None)
            operation_log.pop("restore_requested_at", None)
        except RestoreRollbackError as rollback_error:
            plan["status"] = "rollback_failed"
            plan["rollback_status"] = "failed"
            plan["rollback_error"] = str(rollback_error)
            operation_log["status"] = "restore_failed"

        plan["failed_at"] = _utc_now()
        plan["error_type"] = type(restore_error).__name__
        plan["error_message"] = str(restore_error)
        _write_plan(workspace_root, plan)
        write_operation_log_record(workspace_root, operation_log)

        if plan["rollback_status"] == "failed":
            raise RestoreRollbackError(
                "恢复失败，并且反向撤销未能全部完成"
            ) from restore_error
        raise
