import importlib
from pathlib import Path

import pytest


def test_search_files_matches_name_case_insensitively(
    tmp_path: Path,
):
    """搜索文件名时必须忽略字母大小写。"""
    try:
        search_module = importlib.import_module(
            "service.app.search"
        )
    except ModuleNotFoundError:
        pytest.fail("service.app.search 尚未实现")

    workspace_root = tmp_path / "workspace"
    documents = workspace_root / "documents"
    documents.mkdir(parents=True)

    (workspace_root / "Contract.PDF").write_bytes(b"one")
    (documents / "contract-draft.docx").write_bytes(b"two")
    (workspace_root / "notes.txt").write_bytes(b"three")

    result = search_module.search_files(
        workspace_root,
        query="CONTRACT",
        page=1,
        page_size=10,
    )

    assert result["total"] == 2
    assert result["has_more"] is False
    assert [item["path"] for item in result["files"]] == [
        "Contract.PDF",
        "documents/contract-draft.docx",
    ]


def test_search_files_excludes_management_directories(
    tmp_path: Path,
):
    """搜索不能返回内部管理目录中的文件。"""
    search_module = importlib.import_module(
        "service.app.search"
    )

    workspace_root = tmp_path / "workspace"
    trash_directory = workspace_root / ".trash"
    trash_directory.mkdir(parents=True)

    (workspace_root / "contract.txt").write_bytes(b"visible")
    (trash_directory / "contract-old.txt").write_bytes(
        b"hidden"
    )

    result = search_module.search_files(
        workspace_root,
        query="contract",
        page=1,
        page_size=10,
    )

    assert result["total"] == 1
    assert [item["path"] for item in result["files"]] == [
        "contract.txt",
    ]


def test_search_files_rejects_page_size_above_ten(
    tmp_path: Path,
):
    """搜索每页不能请求超过10个文件。"""
    search_module = importlib.import_module(
        "service.app.search"
    )

    workspace_root = tmp_path / "workspace"
    workspace_root.mkdir()

    with pytest.raises(search_module.PageSizeLimitError):
        search_module.search_files(
            workspace_root,
            query="anything",
            page=1,
            page_size=11,
        )


def test_search_files_returns_file_metadata(tmp_path: Path):
    """搜索结果必须返回文件分类所需的元数据。"""
    search_module = importlib.import_module(
        "service.app.search"
    )

    workspace_root = tmp_path / "workspace"
    workspace_root.mkdir()

    (workspace_root / "report.PDF").write_bytes(b"hello")

    result = search_module.search_files(
        workspace_root,
        query="report",
        page=1,
        page_size=10,
    )

    item = result["files"][0]

    assert item["path"] == "report.PDF"
    assert item["name"] == "report.PDF"
    assert item["extension"] == ".pdf"
    assert item["size_bytes"] == 5
    assert isinstance(item["modified_at"], str)