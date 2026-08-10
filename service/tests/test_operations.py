import importlib
from pathlib import Path

import pytest


def test_preview_move_rename_does_not_change_files(
    tmp_path: Path,
):
    """预览移动重命名时不能修改真实文件。"""
    try:
        operations_module = importlib.import_module(
            "service.app.operations"
        )
    except ModuleNotFoundError:
        pytest.fail("service.app.operations 尚未实现")

    workspace_root = tmp_path / "workspace"
    source_directory = workspace_root / "incoming"
    source_directory.mkdir(parents=True)

    source_file = source_directory / "report.pdf"
    source_file.write_bytes(b"content")

    result = operations_module.preview_operations(
        workspace_root,
        operations=[
            {
                "action": "move_rename",
                "source": "incoming/report.pdf",
                "destination": "reports/final-report.pdf",
            }
        ],
    )

    assert source_file.exists()
    assert not (
        workspace_root / "reports" / "final-report.pdf"
    ).exists()

    assert result == {
        "file_count": 1,
        "operations": [
            {
                "action": "move_rename",
                "source": "incoming/report.pdf",
                "destination": "reports/final-report.pdf",
            }
        ],
    }


def test_preview_operations_rejects_more_than_ten_files(
    tmp_path: Path,
):
    """一批整理计划不能超过10个文件。"""
    operations_module = importlib.import_module(
        "service.app.operations"
    )

    workspace_root = tmp_path / "workspace"
    workspace_root.mkdir()

    operations = []

    for index in range(11):
        source_name = f"source-{index}.txt"
        destination_name = f"sorted/target-{index}.txt"

        (workspace_root / source_name).write_bytes(b"x")

        operations.append({
            "action": "move_rename",
            "source": source_name,
            "destination": destination_name,
        })

    with pytest.raises(
        operations_module.TooManyOperationsError
    ):
        operations_module.preview_operations(
            workspace_root,
            operations=operations,
        )


def test_preview_rejects_missing_source_file(
    tmp_path: Path,
):
    """源文件不存在时，整批计划必须被拒绝。"""
    operations_module = importlib.import_module(
        "service.app.operations"
    )

    workspace_root = tmp_path / "workspace"
    workspace_root.mkdir()

    with pytest.raises(
        operations_module.SourceFileNotFoundError
    ):
        operations_module.preview_operations(
            workspace_root,
            operations=[
                {
                    "action": "move_rename",
                    "source": "missing.txt",
                    "destination": "sorted/missing.txt",
                }
            ],
        )


def test_preview_rejects_existing_destination(
    tmp_path: Path,
):
    """目标文件已存在时不能生成可执行计划。"""
    operations_module = importlib.import_module(
        "service.app.operations"
    )

    workspace_root = tmp_path / "workspace"
    incoming = workspace_root / "incoming"
    sorted_directory = workspace_root / "sorted"

    incoming.mkdir(parents=True)
    sorted_directory.mkdir(parents=True)

    (incoming / "report.txt").write_bytes(b"new")
    existing_file = sorted_directory / "report.txt"
    existing_file.write_bytes(b"existing")

    with pytest.raises(
        operations_module.DestinationAlreadyExistsError
    ):
        operations_module.preview_operations(
            workspace_root,
            operations=[
                {
                    "action": "move_rename",
                    "source": "incoming/report.txt",
                    "destination": "sorted/report.txt",
                }
            ],
        )

    assert existing_file.read_bytes() == b"existing"


def test_preview_create_folder_does_not_create_it(
    tmp_path: Path,
):
    """预览创建文件夹时不能真的创建目录。"""
    operations_module = importlib.import_module(
        "service.app.operations"
    )

    workspace_root = tmp_path / "workspace"
    workspace_root.mkdir()

    result = operations_module.preview_operations(
        workspace_root,
        operations=[
            {
                "action": "create_folder",
                "destination": "reports/2026",
            }
        ],
    )

    assert not (workspace_root / "reports").exists()
    assert result == {
        "file_count": 0,
        "operations": [
            {
                "action": "create_folder",
                "destination": "reports/2026",
            }
        ],
    }
def test_preview_rejects_unsupported_action(
    tmp_path: Path,
):
    """预览必须拒绝未定义的操作类型。"""
    operations_module = importlib.import_module(
        "service.app.operations"
    )

    workspace_root = tmp_path / "workspace"
    workspace_root.mkdir()

    source_file = workspace_root / "notes.txt"
    source_file.write_bytes(b"notes")

    with pytest.raises(
        ValueError,
        match="不支持的操作类型",
    ):
        operations_module.preview_operations(
            workspace_root,
            operations=[
                {
                    "action": "copy",
                    "source": "notes.txt",
                    "destination": "notes-copy.txt",
                }
            ],
        )
def test_preview_limit_counts_files_not_folders(
    tmp_path: Path,
):
    """10个文件加创建文件夹仍应属于合法批次。"""
    operations_module = importlib.import_module(
        "service.app.operations"
    )

    workspace_root = tmp_path / "workspace"
    incoming_directory = workspace_root / "incoming"
    incoming_directory.mkdir(parents=True)

    operations = [
        {
            "action": "create_folder",
            "destination": "sorted",
        }
    ]

    for index in range(10):
        file_name = f"file-{index}.txt"
        source_file = incoming_directory / file_name
        source_file.write_bytes(b"content")

        operations.append({
            "action": "move_rename",
            "source": f"incoming/{file_name}",
            "destination": f"sorted/{file_name}",
        })

    result = operations_module.preview_operations(
        workspace_root,
        operations=operations,
    )

    assert result["file_count"] == 10
    assert len(result["operations"]) == 11
def test_preview_trash_does_not_move_file(
    tmp_path: Path,
):
    """预览回收文件时不能真的移动文件。"""
    operations_module = importlib.import_module(
        "service.app.operations"
    )

    workspace_root = tmp_path / "workspace"
    workspace_root.mkdir()

    source_file = workspace_root / "old-notes.txt"
    source_file.write_bytes(b"old notes")

    result = operations_module.preview_operations(
        workspace_root,
        operations=[
            {
                "action": "trash",
                "source": "old-notes.txt",
            }
        ],
    )

    assert source_file.is_file()
    assert not (workspace_root / ".trash").exists()
    assert result == {
        "file_count": 1,
        "operations": [
            {
                "action": "trash",
                "source": "old-notes.txt",
            }
        ],
    }
def test_preview_rejects_duplicate_source_file(
    tmp_path: Path,
):
    """同一个源文件不能在一批计划中重复操作。"""
    operations_module = importlib.import_module(
        "service.app.operations"
    )

    workspace_root = tmp_path / "workspace"
    workspace_root.mkdir()

    source_file = workspace_root / "notes.txt"
    source_file.write_bytes(b"notes")

    with pytest.raises(
        ValueError,
        match="同一个源文件不能重复操作",
    ):
        operations_module.preview_operations(
            workspace_root,
            operations=[
                {
                    "action": "move_rename",
                    "source": "notes.txt",
                    "destination": "sorted/notes.txt",
                },
                {
                    "action": "trash",
                    "source": "notes.txt",
                },
            ],
        )

    assert source_file.is_file()
    assert not (workspace_root / "sorted").exists()
    assert not (workspace_root / ".trash").exists()
def test_preview_rejects_duplicate_destination(
    tmp_path: Path,
):
    """多个操作不能使用同一个目标位置。"""
    operations_module = importlib.import_module(
        "service.app.operations"
    )

    workspace_root = tmp_path / "workspace"
    incoming_directory = workspace_root / "incoming"
    incoming_directory.mkdir(parents=True)

    first_file = incoming_directory / "first.txt"
    second_file = incoming_directory / "second.txt"
    first_file.write_bytes(b"first")
    second_file.write_bytes(b"second")

    with pytest.raises(
        ValueError,
        match="同一个目标位置不能重复使用",
    ):
        operations_module.preview_operations(
            workspace_root,
            operations=[
                {
                    "action": "move_rename",
                    "source": "incoming/first.txt",
                    "destination": "sorted/result.txt",
                },
                {
                    "action": "move_rename",
                    "source": "incoming/second.txt",
                    "destination": "sorted/result.txt",
                },
            ],
        )

    assert first_file.is_file()
    assert second_file.is_file()
    assert not (workspace_root / "sorted").exists()