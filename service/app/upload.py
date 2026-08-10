from pathlib import Path
from typing import Any
from service.app.paths import resolve_workspace_path


class FileAlreadyExistsError(FileExistsError):
    """目标位置已经存在同名文件。"""


class InvalidFileNameError(ValueError):
    """上传文件名不合法。"""


def save_uploaded_file(
    workspace_root: Path,
    *,
    relative_directory: str,
    file_name: str,
    content: bytes,
) -> dict[str, Any]:
    normalized_name = Path(file_name).name

    if (
        not file_name
        or normalized_name != file_name
        or file_name in {".", ".."}
    ):
        raise InvalidFileNameError(
            "file_name 只能是文件名，不能包含路径"
        )
    target_directory = resolve_workspace_path(
        workspace_root,
        relative_directory,
    )
    target_directory.mkdir(
        parents=True,
        exist_ok=True,
    )

    target_path = resolve_workspace_path(
        workspace_root,
        str(Path(relative_directory) / file_name),
    )
    if target_path.exists():
        raise FileAlreadyExistsError(
            f"目标文件已经存在：{target_path.name}"
        )
    target_path.write_bytes(content)

    return {
        "path": target_path.relative_to(
            workspace_root
        ).as_posix(),
        "name": target_path.name,
        "size_bytes": len(content),
    }