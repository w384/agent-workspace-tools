from pathlib import Path

import pytest

from service.app.main import load_api_key


def test_load_api_key_prefers_direct_value(tmp_path: Path):
    key_file = tmp_path / "api-key.txt"
    key_file.write_text("file-secret\n", encoding="utf-8")
    assert load_api_key({
        "DIFY_AGENT_WORKSPACE_API_KEY": "direct-secret",
        "DIFY_AGENT_WORKSPACE_API_KEY_FILE": str(key_file),
    }) == "direct-secret"


def test_load_api_key_reads_file(tmp_path: Path):
    key_file = tmp_path / "api-key.txt"
    key_file.write_text("file-secret\n", encoding="utf-8")
    assert load_api_key({
        "DIFY_AGENT_WORKSPACE_API_KEY_FILE": str(key_file),
    }) == "file-secret"


def test_load_api_key_rejects_empty_file(tmp_path: Path):
    key_file = tmp_path / "api-key.txt"
    key_file.write_text("\n", encoding="utf-8")
    with pytest.raises(RuntimeError, match="API Key 密钥文件为空"):
        load_api_key({
            "DIFY_AGENT_WORKSPACE_API_KEY_FILE": str(key_file),
        })


def test_load_api_key_rejects_unreadable_file_without_leaking_key(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    key_file = tmp_path / "api-key.txt"
    simulated_secret = "mock-file-secret"

    def raise_read_error(_path: Path, **_kwargs: str) -> str:
        raise OSError(f"cannot read {simulated_secret}")

    monkeypatch.setattr(Path, "read_text", raise_read_error)
    with pytest.raises(
        RuntimeError,
        match="^无法读取 API Key 密钥文件$",
    ) as error_info:
        load_api_key({
            "DIFY_AGENT_WORKSPACE_API_KEY_FILE": str(key_file),
        })

    assert simulated_secret not in str(error_info.value)
