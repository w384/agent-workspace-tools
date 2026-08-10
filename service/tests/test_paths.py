import importlib
from pathlib import Path

import pytest


def test_resolve_workspace_path_returns_path_inside_root(tmp_path: Path):
    """正常的相对路径必须被解析到工作区内部。"""
    try:
        paths_module = importlib.import_module("service.app.paths")
    except ModuleNotFoundError:
        pytest.fail("service.app.paths 尚未实现")

    workspace_root = tmp_path / "workspace"
    workspace_root.mkdir()

    resolved = paths_module.resolve_workspace_path(
        workspace_root,
        "documents/report.pdf",
    )

    assert resolved == workspace_root / "documents" / "report.pdf"


def test_resolve_workspace_path_rejects_parent_escape(tmp_path: Path):
    """使用 .. 不能访问工作区外部。"""
    paths_module = importlib.import_module("service.app.paths")

    workspace_root = tmp_path / "workspace"
    workspace_root.mkdir()

    with pytest.raises(paths_module.PathOutsideWorkspaceError):
        paths_module.resolve_workspace_path(
            workspace_root,
            r"..\outside.txt",
        )


@pytest.mark.parametrize(
    "relative_path",
    [
        ".trash/recycled.txt",
        ".file-manager/plans/plan.json",
    ],
)
def test_resolve_workspace_path_rejects_management_directories(
    tmp_path: Path,
    relative_path: str,
):
    """用户提供的路径不能进入服务内部管理目录。"""
    paths_module = importlib.import_module("service.app.paths")

    workspace_root = tmp_path / "workspace"
    workspace_root.mkdir()

    with pytest.raises(
        paths_module.ProtectedManagementPathError
    ):
        paths_module.resolve_workspace_path(
            workspace_root,
            relative_path,
        )
