from pathlib import Path
from typing import Any
from service.app.listing import (
    PageSizeLimitError,
    _file_metadata,
    _is_visible_file,
)


def search_files(
    workspace_root: Path,
    *,
    query: str,
    page: int,
    page_size: int,
) -> dict[str, Any]:
    if not 1 <= page_size <= 10:
        raise PageSizeLimitError(
            "page_size 必须在1到10之间"
        )

    normalized_query = query.casefold()

    matching_files = sorted(
        (
            path
            for path in workspace_root.rglob("*")
            if (
                _is_visible_file(workspace_root, path)
                and normalized_query in path.name.casefold()
            )
        ),
        key=lambda path: path.relative_to(workspace_root)
        .as_posix()
        .casefold(),
    )

    start = (page - 1) * page_size
    end = start + page_size
    current_files = matching_files[start:end]

    return {
        "total": len(matching_files),
        "page": page,
        "page_size": page_size,
        "has_more": end < len(matching_files),
        "files": [
            _file_metadata(workspace_root, path)
            for path in current_files
        ],
    }