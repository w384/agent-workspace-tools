import json
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from uuid import UUID


RETENTION_DAYS = 14


class OperationLogNotFoundError(FileNotFoundError):
    """指定操作日志不存在。"""


class InvalidOperationIdError(ValueError):
    """操作编号不是合法 UUID。"""


def _operations_directory(workspace_root: Path) -> Path:
    return (
        workspace_root.resolve()
        / ".file-manager"
        / "operations"
    )


def _normalize_operation_id(operation_id: str) -> str:
    try:
        return str(UUID(operation_id))
    except (AttributeError, TypeError, ValueError) as error:
        raise InvalidOperationIdError(
            f"操作编号无效：{operation_id}"
        ) from error


def _operation_path(
    workspace_root: Path,
    operation_id: str,
) -> Path:
    normalized_operation_id = _normalize_operation_id(operation_id)
    return (
        _operations_directory(workspace_root)
        / f"{normalized_operation_id}.json"
    )


def read_operation_log(
    workspace_root: Path,
    *,
    operation_id: str,
) -> dict[str, Any]:
    operation_path = _operation_path(
        workspace_root,
        operation_id,
    )
    if not operation_path.is_file():
        raise OperationLogNotFoundError(
            f"操作日志不存在：{operation_id}"
        )
    return json.loads(
        operation_path.read_text(encoding="utf-8")
    )


def write_operation_log_record(
    workspace_root: Path,
    operation_log: dict[str, Any],
) -> None:
    operation_path = _operation_path(
        workspace_root,
        operation_log["operation_id"],
    )
    operation_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = operation_path.with_suffix(".json.tmp")
    temporary_path.write_text(
        json.dumps(
            operation_log,
            ensure_ascii=False,
            indent=2,
        ) + "\n",
        encoding="utf-8",
    )
    temporary_path.replace(operation_path)


def _relative_path(workspace_root: Path, path: Path) -> str:
    return path.relative_to(
        workspace_root.resolve()
    ).as_posix()


def _build_undo_actions(
    workspace_root: Path,
    applied_actions: list[dict[str, Any]],
) -> list[dict[str, str]]:
    undo_actions: list[dict[str, str]] = []

    for applied_action in reversed(applied_actions):
        if applied_action["action"] == "create_folder":
            undo_actions.append({
                "action": "remove_folder",
                "path": _relative_path(
                    workspace_root,
                    applied_action["path"],
                ),
            })
            continue

        undo_actions.append({
            "action": "move",
            "source": _relative_path(
                workspace_root,
                applied_action["destination"],
            ),
            "destination": _relative_path(
                workspace_root,
                applied_action["source"],
            ),
        })

    return undo_actions


def write_operation_log(
    workspace_root: Path,
    *,
    plan: dict[str, Any],
    applied_actions: list[dict[str, Any]],
) -> dict[str, Any]:
    """保存成功操作及其逆序恢复动作。"""
    completed_at = datetime.fromisoformat(plan["completed_at"])
    expires_at = completed_at + timedelta(days=RETENTION_DAYS)
    operation_id = plan["plan_id"]

    operation_log = {
        "operation_id": operation_id,
        "plan_id": plan["plan_id"],
        "status": "completed",
        "completed_at": plan["completed_at"],
        "expires_at": expires_at.isoformat(),
        "file_count": plan["file_count"],
        "undo_actions": _build_undo_actions(
            workspace_root,
            applied_actions,
        ),
    }

    write_operation_log_record(workspace_root, operation_log)
    return operation_log


def cleanup_expired_operations(
    workspace_root: Path,
    *,
    now: datetime | None = None,
) -> list[str]:
    """永久清理超过恢复窗口的日志和对应回收目录。"""
    current_time = now or datetime.now(timezone.utc)
    operations_directory = _operations_directory(workspace_root)
    if not operations_directory.is_dir():
        return []

    removed_operation_ids: list[str] = []
    trash_root = workspace_root.resolve() / ".trash"

    for operation_path in sorted(
        operations_directory.glob("*.json")
    ):
        operation_id = operation_path.stem
        try:
            normalized_operation_id = str(UUID(operation_id))
            operation_log = json.loads(
                operation_path.read_text(encoding="utf-8")
            )
            expires_at = datetime.fromisoformat(
                operation_log["expires_at"]
            )
        except (
            KeyError,
            TypeError,
            ValueError,
            json.JSONDecodeError,
        ):
            continue

        if operation_log.get("operation_id") != normalized_operation_id:
            continue
        if expires_at > current_time:
            continue

        trash_directory = trash_root / normalized_operation_id
        if trash_directory.is_dir():
            shutil.rmtree(trash_directory)
        operation_path.unlink()
        removed_operation_ids.append(normalized_operation_id)

    return removed_operation_ids
