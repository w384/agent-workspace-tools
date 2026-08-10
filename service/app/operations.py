from pathlib import Path
from typing import Any
from service.app.paths import resolve_workspace_path


class TooManyOperationsError(ValueError):
    """一批文件操作超过允许数量。"""


class SourceFileNotFoundError(FileNotFoundError):
    """源文件不存在或不是普通文件。"""


class DestinationAlreadyExistsError(FileExistsError):
    """目标位置已经存在文件或文件夹。"""


class UnsupportedOperationError(ValueError):
    """操作类型不在允许范围内。"""


class DuplicateSourceError(ValueError):
    """同一个源文件在批次中出现了多次。"""


class DuplicateDestinationError(ValueError):
    """同一个目标位置在批次中出现了多次。"""


def preview_operations(
    workspace_root: Path,
    *,
    operations: list[dict[str, Any]],
) -> dict[str, Any]:
    file_operation_count = sum(
        1
        for operation in operations
        if operation.get("action") in {
            "move_rename",
            "trash",
        }
    )

    if file_operation_count > 10:
        raise TooManyOperationsError(
            "一批整理计划最多包含10个文件"
        )
    normalized_operations: list[dict[str, str]] = []
    file_count = 0
    seen_source_paths: set[str] = set()
    seen_destination_paths: set[str] = set()

    for operation in operations:
        action = operation["action"]
        if action not in {
            "create_folder",
            "move_rename",
            "trash",
        }:
            raise UnsupportedOperationError(
                f"不支持的操作类型：{action}"
            )
        if action == "create_folder":
            destination = operation["destination"]
            destination_path = resolve_workspace_path(
                workspace_root,
                destination,
            )

            if destination_path.exists():
                raise DestinationAlreadyExistsError(
                    f"目标位置已经存在：{destination}"
                )
            destination_key = str(destination_path).casefold()
            if destination_key in seen_destination_paths:
                raise DuplicateDestinationError(
                    f"同一个目标位置不能重复使用：{destination}"
                )
            seen_destination_paths.add(destination_key)

            normalized_operations.append({
                "action": action,
                "destination": destination_path.relative_to(
                    workspace_root
                ).as_posix(),
            })
            continue

        if action == "trash":
            source = operation["source"]
            source_path = resolve_workspace_path(
                workspace_root,
                source,
            )

            if not source_path.is_file():
                raise SourceFileNotFoundError(
                    f"源文件不存在：{source}"
                )
            source_key = str(source_path).casefold()
            if source_key in seen_source_paths:
                raise DuplicateSourceError(
                    f"同一个源文件不能重复操作：{source}"
                )
            seen_source_paths.add(source_key)

            normalized_operations.append({
                "action": action,
                "source": source_path.relative_to(
                    workspace_root
                ).as_posix(),
            })
            file_count += 1
            continue

        source = operation["source"]
        destination = operation["destination"]

        source_path = resolve_workspace_path(
            workspace_root,
            source,
        )
        if not source_path.is_file():
            raise SourceFileNotFoundError(
                f"源文件不存在：{source}"
            )
        source_key = str(source_path).casefold()
        if source_key in seen_source_paths:
            raise DuplicateSourceError(
                f"同一个源文件不能重复操作：{source}"
            )
        seen_source_paths.add(source_key)

        destination_path = resolve_workspace_path(
            workspace_root,
            destination,
        )
        if destination_path.exists():
            raise DestinationAlreadyExistsError(
                f"目标位置已经存在：{destination}"
            )
        destination_key = str(destination_path).casefold()
        if destination_key in seen_destination_paths:
            raise DuplicateDestinationError(
                f"同一个目标位置不能重复使用：{destination}"
            )
        seen_destination_paths.add(destination_key)

        normalized_operations.append({
            "action": action,
            "source": source_path.relative_to(
                workspace_root
            ).as_posix(),
            "destination": destination_path.relative_to(
                workspace_root
            ).as_posix(),
        })
        file_count += 1

    return {
        "file_count": file_count,
        "operations": normalized_operations,
    }
