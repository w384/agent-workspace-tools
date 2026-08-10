from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from service.app.paths import resolve_workspace_path


_MAX_CONTENT_BYTES = 15 * 1024 * 1024


def _file_metadata(target_path: Path) -> dict[str, Any]:
    file_stat = target_path.stat()

    return {
        "name": target_path.name,
        "extension": target_path.suffix.lower(),
        "size_bytes": file_stat.st_size,
        "modified_at": datetime.fromtimestamp(
            file_stat.st_mtime,
            tz=timezone.utc,
        ).isoformat(),
    }


def read_file(
    workspace_root: Path,
    relative_path: str,
) -> dict[str, Any]:
    target_path = resolve_workspace_path(
        workspace_root,
        relative_path,
    )
    metadata = _file_metadata(target_path)

    if metadata["size_bytes"] > _MAX_CONTENT_BYTES:
        return {
            **metadata,
            "content_available": False,
            "content": None,
        }

    return {
        **metadata,
        "content_available": True,
        "content": target_path.read_bytes(),
    }