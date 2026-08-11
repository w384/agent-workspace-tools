import hashlib
import hmac
import json
import secrets
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from threading import Lock, RLock
from typing import Any
from uuid import UUID, uuid4

from service.app.operations import preview_operations


_PLAN_LOCKS_GUARD = Lock()
_PLAN_LOCKS: dict[str, RLock] = {}
_PLAN_STATUS_FIELDS = (
    "plan_id", "status", "plan_type", "file_count",
    "created_at", "approved_at", "completed_at",
    "failed_at", "operation_id", "rollback_status",
    "error_type",
)


class PlanNotFoundError(FileNotFoundError):
    """指定计划不存在。"""


class InvalidPlanIdError(ValueError):
    """计划编号不是合法 UUID。"""


class PlanStateError(ValueError):
    """计划当前状态不允许执行请求的操作。"""


class InvalidApprovalTokenError(PermissionError):
    """确认令牌不正确。"""


class ApprovalTokenAlreadyUsedError(PermissionError):
    """确认令牌已经被使用。"""


def _plans_directory(workspace_root: Path) -> Path:
    return (
        workspace_root.resolve()
        / ".file-manager"
        / "plans"
    )


def _normalize_plan_id(plan_id: str) -> str:
    try:
        return str(UUID(plan_id))
    except (AttributeError, TypeError, ValueError) as error:
        raise InvalidPlanIdError(
            f"计划编号无效：{plan_id}"
        ) from error


def _get_plan_lock(plan_id: str) -> RLock:
    normalized_plan_id = _normalize_plan_id(plan_id)
    with _PLAN_LOCKS_GUARD:
        lock = _PLAN_LOCKS.get(normalized_plan_id)
        if lock is None:
            lock = RLock()
            _PLAN_LOCKS[normalized_plan_id] = lock
        return lock


def _plan_path(workspace_root: Path, plan_id: str) -> Path:
    normalized_plan_id = _normalize_plan_id(plan_id)
    return (
        _plans_directory(workspace_root)
        / f"{normalized_plan_id}.json"
    )


def _read_plan(
    workspace_root: Path,
    plan_id: str,
) -> dict[str, Any]:
    with _get_plan_lock(plan_id):
        plan_path = _plan_path(workspace_root, plan_id)
        if not plan_path.is_file():
            raise PlanNotFoundError(f"计划不存在：{plan_id}")

        return json.loads(plan_path.read_text(encoding="utf-8"))


def read_plan_status(
    workspace_root: Path,
    *,
    plan_id: str,
) -> dict[str, Any]:
    plan = _read_plan(workspace_root, plan_id)
    return {
        key: plan[key]
        for key in _PLAN_STATUS_FIELDS
        if key in plan
    }


def _write_plan(
    workspace_root: Path,
    plan: dict[str, Any],
) -> None:
    with _get_plan_lock(plan["plan_id"]):
        plans_directory = _plans_directory(workspace_root)
        plans_directory.mkdir(parents=True, exist_ok=True)

        plan_path = plans_directory / f"{plan['plan_id']}.json"
        temporary_path = plan_path.with_suffix(".json.tmp")
        temporary_path.write_text(
            json.dumps(plan, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        temporary_path.replace(plan_path)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _build_confirmation(
    operations: list[dict[str, str]],
) -> dict[str, Any]:
    folders_to_create: list[str] = []
    moves: list[dict[str, str]] = []
    renames: list[dict[str, str]] = []
    trash: list[str] = []

    for operation in operations:
        action = operation["action"]

        if action == "create_folder":
            folders_to_create.append(operation["destination"])
            continue

        if action == "trash":
            trash.append(operation["source"])
            continue

        source = PurePosixPath(operation["source"])
        destination = PurePosixPath(operation["destination"])

        if source.parent != destination.parent:
            moves.append({
                "source": source.as_posix(),
                "destination": destination.as_posix(),
            })

        if source.name != destination.name:
            renames.append({
                "source_name": source.name,
                "destination_name": destination.name,
            })

    return {
        "folders_to_create": folders_to_create,
        "moves": moves,
        "renames": renames,
        "trash": trash,
    }


def create_plan(
    workspace_root: Path,
    *,
    operations: list[dict[str, Any]],
) -> dict[str, Any]:
    """校验整理操作，生成确认摘要并保存待确认计划。"""
    preview = preview_operations(
        workspace_root,
        operations=operations,
    )
    plan_id = str(uuid4())

    plan = {
        "plan_id": plan_id,
        "status": "pending_confirmation",
        "created_at": _utc_now(),
        "file_count": preview["file_count"],
        "operations": preview["operations"],
        "confirmation": _build_confirmation(
            preview["operations"]
        ),
    }

    _write_plan(workspace_root, plan)

    return plan


def issue_approval_token(
    workspace_root: Path,
    *,
    plan_id: str,
) -> str:
    """为待确认计划签发只返回一次的明文令牌。"""
    with _get_plan_lock(plan_id):
        plan = _read_plan(workspace_root, plan_id)
        if plan["status"] != "pending_confirmation":
            raise PlanStateError(
                f"计划状态不允许确认：{plan['status']}"
            )

        token = secrets.token_urlsafe(32)
        plan["approval_token_hash"] = _hash_token(token)
        plan["approved_at"] = _utc_now()
        plan["status"] = "approved"
        _write_plan(workspace_root, plan)
        return token


def consume_approval_token(
    workspace_root: Path,
    *,
    plan_id: str,
    token: str,
) -> dict[str, Any]:
    """验证并消费一次性令牌，锁定计划进入执行状态。"""
    with _get_plan_lock(plan_id):
        plan = _read_plan(workspace_root, plan_id)

        if plan["status"] == "executing":
            raise ApprovalTokenAlreadyUsedError(
                "确认令牌已经被使用"
            )
        if plan["status"] != "approved":
            raise PlanStateError(
                f"计划状态不允许执行：{plan['status']}"
            )

        expected_hash = plan["approval_token_hash"]
        supplied_hash = _hash_token(token)
        if not hmac.compare_digest(expected_hash, supplied_hash):
            raise InvalidApprovalTokenError("确认令牌不正确")

        plan.pop("approval_token_hash", None)
        plan["approval_token_used_at"] = _utc_now()
        plan["status"] = "executing"
        _write_plan(workspace_root, plan)
        return plan
