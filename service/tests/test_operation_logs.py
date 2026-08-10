import importlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4


def test_cleanup_removes_only_expired_logs_and_trash(
    tmp_path: Path,
):
    """清理任务只能删除超过14天恢复窗口的操作数据。"""
    logs_module = importlib.import_module(
        "service.app.operation_logs"
    )
    workspace_root = tmp_path / "workspace"
    operations_directory = (
        workspace_root / ".file-manager" / "operations"
    )
    trash_root = workspace_root / ".trash"
    operations_directory.mkdir(parents=True)
    trash_root.mkdir()

    now = datetime(2026, 8, 11, tzinfo=timezone.utc)
    expired_id = str(uuid4())
    active_id = str(uuid4())

    expired_log_path = operations_directory / f"{expired_id}.json"
    active_log_path = operations_directory / f"{active_id}.json"
    expired_log_path.write_text(
        json.dumps({
            "operation_id": expired_id,
            "expires_at": (now - timedelta(seconds=1)).isoformat(),
        }),
        encoding="utf-8",
    )
    active_log_path.write_text(
        json.dumps({
            "operation_id": active_id,
            "expires_at": (now + timedelta(days=1)).isoformat(),
        }),
        encoding="utf-8",
    )

    expired_trash = trash_root / expired_id
    active_trash = trash_root / active_id
    expired_trash.mkdir()
    active_trash.mkdir()
    (expired_trash / "old.txt").write_bytes(b"expired")
    (active_trash / "active.txt").write_bytes(b"active")

    removed_operation_ids = (
        logs_module.cleanup_expired_operations(
            workspace_root,
            now=now,
        )
    )

    assert removed_operation_ids == [expired_id]
    assert not expired_log_path.exists()
    assert not expired_trash.exists()
    assert active_log_path.is_file()
    assert (active_trash / "active.txt").is_file()
