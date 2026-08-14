from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from service.app.permissions import is_path_allowed


_MANAGEMENT_DIRECTORIES = frozenset({
    ".trash",
    ".file-manager",
})


class PageSizeLimitError(ValueError):
    """请求的单页文件数不符合限制。"""


def _is_visible_file(
    workspace_root: Path,
    path: Path,
) -> bool:
    relative_path = path.relative_to(workspace_root)

    return (
        path.is_file()
        and not any(
            part in _MANAGEMENT_DIRECTORIES
            for part in relative_path.parts
        )
    )

def _file_metadata(
    workspace_root: Path,
    path: Path,
) -> dict[str, Any]:
    file_stat = path.stat()

    return {
        "path": path.relative_to(workspace_root).as_posix(),
        "name": path.name,
        "extension": path.suffix.lower(),
        "size_bytes": file_stat.st_size,
        "modified_at": datetime.fromtimestamp(
            file_stat.st_mtime,
            tz=timezone.utc,
        ).isoformat(),
    }

def list_files(
    workspace_root: Path,
    *,
    page: int,
    page_size: int,
    path_prefixes: list[str] | None = None,
) -> dict[str, Any]:
    if not 1 <= page_size <= 10:
        raise PageSizeLimitError(
            "page_size 必须在1到10之间"
        )

    all_files = sorted(
        (
            path
            for path in workspace_root.rglob("*")
            if _is_visible_file(workspace_root, path)
            and (
                path_prefixes is None
                or is_path_allowed(
                    path_prefixes,
                    path.relative_to(workspace_root).as_posix(),
                )
            )
        ),
        key=lambda path: path.relative_to(workspace_root)
        .as_posix()
        .casefold(),
    )

    start = (page - 1) * page_size
    end = start + page_size
    current_files = all_files[start:end]

    return {
        "total": len(all_files),
        "page": page,
        "page_size": page_size,
        "has_more": end < len(all_files),
        "files": [
            _file_metadata(workspace_root, path)
            for path in current_files
        ],
    }