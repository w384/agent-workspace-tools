import importlib
from pathlib import Path

import pytest


def test_read_file_returns_small_file_content(tmp_path: Path):
    """15MB以内的文件必须返回内容和元数据。"""
    try:
        content_module = importlib.import_module(
            "service.app.file_content"
        )
    except ModuleNotFoundError:
        pytest.fail("service.app.file_content 尚未实现")

    workspace_root = tmp_path / "workspace"
    workspace_root.mkdir()

    target_file = workspace_root / "notes.txt"
    target_file.write_bytes(b"hello")

    result = content_module.read_file(
        workspace_root,
        "notes.txt",
    )

    assert result["name"] == "notes.txt"
    assert result["extension"] == ".txt"
    assert result["size_bytes"] == 5
    assert isinstance(result["modified_at"], str)
    assert result["content_available"] is True
    assert result["content"] == b"hello"


def test_read_file_returns_only_metadata_above_fifteen_mb(
    tmp_path: Path,
):
    """超过15MB的文件只返回元数据，不读取内容。"""
    content_module = importlib.import_module(
        "service.app.file_content"
    )

    workspace_root = tmp_path / "workspace"
    workspace_root.mkdir()

    target_file = workspace_root / "large.bin"

    with target_file.open("wb") as file_handle:
        file_handle.truncate(
            15 * 1024 * 1024 + 1
        )

    result = content_module.read_file(
        workspace_root,
        "large.bin",
    )

    assert result["name"] == "large.bin"
    assert result["extension"] == ".bin"
    assert result["size_bytes"] == 15 * 1024 * 1024 + 1
    assert isinstance(result["modified_at"], str)
    assert result["content_available"] is False
    assert result["content"] is None