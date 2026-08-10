import importlib
from pathlib import Path

import pytest


def test_list_files_returns_recursive_files_sorted(tmp_path: Path):
    """扫描结果必须包含子目录文件，并按相对路径排序。"""
    try:
        listing_module = importlib.import_module("service.app.listing")
    except ModuleNotFoundError:
        pytest.fail("service.app.listing 尚未实现")

    workspace_root = tmp_path / "workspace"
    documents = workspace_root / "documents"
    documents.mkdir(parents=True)

    (workspace_root / "photo.jpg").write_bytes(b"image")
    (documents / "report.pdf").write_bytes(b"pdf")

    result = listing_module.list_files(
        workspace_root,
        page=1,
        page_size=10,
    )

    assert result["total"] == 2
    assert result["page"] == 1
    assert result["page_size"] == 10
    assert result["has_more"] is False
    assert [item["path"] for item in result["files"]] == [
        "documents/report.pdf",
        "photo.jpg",
    ]


def test_list_files_excludes_management_directories(tmp_path: Path):
    """普通扫描不能显示内部管理目录中的文件。"""
    listing_module = importlib.import_module("service.app.listing")

    workspace_root = tmp_path / "workspace"
    trash_directory = workspace_root / ".trash"
    manager_directory = workspace_root / ".file-manager"

    trash_directory.mkdir(parents=True)
    manager_directory.mkdir(parents=True)

    (workspace_root / "visible.txt").write_text(
        "visible",
        encoding="utf-8",
    )
    (trash_directory / "deleted.txt").write_text(
        "hidden",
        encoding="utf-8",
    )
    (manager_directory / "state.json").write_text(
        "{}",
        encoding="utf-8",
    )

    result = listing_module.list_files(
        workspace_root,
        page=1,
        page_size=10,
    )

    assert result["total"] == 1
    assert [item["path"] for item in result["files"]] == [
        "visible.txt",
    ]


def test_list_files_rejects_page_size_above_ten(tmp_path: Path):
    """单次扫描不能请求超过10个文件。"""
    listing_module = importlib.import_module("service.app.listing")

    workspace_root = tmp_path / "workspace"
    workspace_root.mkdir()

    with pytest.raises(listing_module.PageSizeLimitError):
        listing_module.list_files(
            workspace_root,
            page=1,
            page_size=11,
        )


def test_list_files_returns_file_metadata(tmp_path: Path):
    """扫描结果必须提供分类需要的基础元数据。"""
    listing_module = importlib.import_module("service.app.listing")

    workspace_root = tmp_path / "workspace"
    workspace_root.mkdir()

    (workspace_root / "notes.txt").write_bytes(b"hello")

    result = listing_module.list_files(
        workspace_root,
        page=1,
        page_size=10,
    )

    item = result["files"][0]

    assert item["path"] == "notes.txt"
    assert item["name"] == "notes.txt"
    assert item["extension"] == ".txt"
    assert item["size_bytes"] == 5
    assert isinstance(item["modified_at"], str)
    assert item["modified_at"]