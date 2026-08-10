from pathlib import Path


_MANAGEMENT_DIRECTORIES = frozenset({
    ".trash",
    ".file-manager",
})


class PathOutsideWorkspaceError(ValueError):
    """目标路径超出允许的工作区。"""


class ProtectedManagementPathError(ValueError):
    """用户路径进入了服务内部管理目录。"""


def resolve_workspace_path(
    workspace_root: Path,
    relative_path: str,
) -> Path:
    root = workspace_root.resolve()
    candidate = (root / relative_path).resolve()

    try:
        relative_candidate = candidate.relative_to(root)
    except ValueError as error:
        raise PathOutsideWorkspaceError(
            "目标路径超出允许的工作区"
        ) from error

    if (
        relative_candidate.parts
        and relative_candidate.parts[0].casefold()
        in _MANAGEMENT_DIRECTORIES
    ):
        raise ProtectedManagementPathError(
            "不能访问服务内部管理目录"
        )

    return candidate
