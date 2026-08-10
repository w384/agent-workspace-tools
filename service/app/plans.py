import json
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any
from uuid import uuid4

from service.app.operations import preview_operations


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
        "created_at": datetime.now(timezone.utc).isoformat(),
        "file_count": preview["file_count"],
        "operations": preview["operations"],
        "confirmation": _build_confirmation(
            preview["operations"]
        ),
    }

    plans_directory = (
        workspace_root.resolve()
        / ".file-manager"
        / "plans"
    )
    plans_directory.mkdir(parents=True, exist_ok=True)
    plan_path = plans_directory / f"{plan_id}.json"
    plan_path.write_text(
        json.dumps(plan, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    return plan
