import importlib
from pathlib import Path

import pytest


def test_save_uploaded_file_writes_inside_workspace(
    tmp_path: Path,
):
    """上传文件必须保存到工作区指定子目录。"""
    try:
        upload_module = importlib.import_module(
            "service.app.upload"
        )
    except ModuleNotFoundError:
        pytest.fail("service.app.upload 尚未实现")

    workspace_root = tmp_path / "workspace"
    workspace_root.mkdir()

    result = upload_module.save_uploaded_file(
        workspace_root,
        relative_directory="incoming",
        file_name="report.txt",
        content=b"hello",
    )

    saved_file = workspace_root / "incoming" / "report.txt"

    assert saved_file.read_bytes() == b"hello"
    assert result == {
        "path": "incoming/report.txt",
        "name": "report.txt",
        "size_bytes": 5,
        "content_fingerprint": (
            "sha256:2cf24dba5fb0a30e26e83b2ac5b9e29e"
            "1b161e5c1fa7425e73043362938b9824"
        ),
    }


def test_save_uploaded_file_refuses_to_overwrite(
    tmp_path: Path,
):
    """上传不能覆盖已经存在的同名文件。"""
    upload_module = importlib.import_module(
        "service.app.upload"
    )

    workspace_root = tmp_path / "workspace"
    target_directory = workspace_root / "incoming"
    target_directory.mkdir(parents=True)

    existing_file = target_directory / "report.txt"
    existing_file.write_bytes(b"original")

    with pytest.raises(
        upload_module.FileAlreadyExistsError
    ):
        upload_module.save_uploaded_file(
            workspace_root,
            relative_directory="incoming",
            file_name="report.txt",
            content=b"replacement",
        )

    assert existing_file.read_bytes() == b"original"


def test_save_uploaded_file_rejects_path_in_file_name(
    tmp_path: Path,
):
    """文件名不能携带目录或路径穿越字符。"""
    upload_module = importlib.import_module(
        "service.app.upload"
    )

    workspace_root = tmp_path / "workspace"
    workspace_root.mkdir()

    with pytest.raises(upload_module.InvalidFileNameError):
        upload_module.save_uploaded_file(
            workspace_root,
            relative_directory="incoming",
            file_name=r"..\escape.txt",
            content=b"unsafe",
        )

    assert not (workspace_root / "escape.txt").exists()
