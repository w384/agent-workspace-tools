import importlib.util
import json
from pathlib import Path

import pytest

from control_plane.app.repository import InMemoryControlPlaneRepository

PROJECT_ROOT = Path(__file__).parents[2]
DEMO_ROOT = PROJECT_ROOT / "work" / "demo" / "financial-preassessment"
SOURCE_ROOT = DEMO_ROOT / "source"
IMPORT_MANIFEST_PATH = DEMO_ROOT / "import-manifest.json"
INTEGRITY_PATH = DEMO_ROOT / "fixture-integrity.json"
RULES_PATH = DEMO_ROOT / "rules" / "demo-bank-rules-v1.json"
SCRIPTS_PATH = PROJECT_ROOT / "scripts" / "init_demo_financial_preassessment.py"


def _load_init_script():
    spec = importlib.util.spec_from_file_location(
        "init_demo_financial_preassessment", SCRIPTS_PATH
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _real_manifest() -> dict[str, object]:
    return json.loads(IMPORT_MANIFEST_PATH.read_text(encoding="utf-8"))


def _real_integrity() -> dict[str, object]:
    return json.loads(INTEGRITY_PATH.read_text(encoding="utf-8"))


def _real_rules() -> dict[str, object]:
    return json.loads(RULES_PATH.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def test_verify_passes_on_real_fixture():
    init = _load_init_script()
    result = init.verify_demo_fixture_integrity()
    assert result["ok"] is True
    names = [check["name"] for check in result["checks"]]
    assert "manifest" in names
    assert "integrity" in names
    assert "declared-set" in names
    assert "rules" in names
    assert sum(name.startswith("file:") for name in names) == 6


def test_verify_detects_tampered_file_fingerprint(tmp_path):
    init = _load_init_script()
    integrity = _real_integrity()
    integrity["assets"][0]["sha256"] = "0" * 64
    integrity_path = tmp_path / "fixture-integrity.json"
    _write_json(integrity_path, integrity)
    result = init.verify_demo_fixture_integrity(
        source_root=SOURCE_ROOT,
        import_manifest_path=IMPORT_MANIFEST_PATH,
        integrity_path=integrity_path,
        rules_path=RULES_PATH,
    )
    assert result["ok"] is False
    file_check = next(
        check for check in result["checks"] if check["name"].startswith("file:")
    )
    assert file_check["ok"] is False
    assert "actual" in str(file_check["detail"])


def test_verify_detects_missing_file(tmp_path):
    init = _load_init_script()
    missing_path = "客户模拟资料/不存在.docx"
    manifest = _real_manifest()
    integrity = _real_integrity()
    manifest["assets"][0]["relative_path"] = missing_path
    integrity["assets"][0]["relative_path"] = missing_path
    manifest_path = tmp_path / "import-manifest.json"
    integrity_path = tmp_path / "fixture-integrity.json"
    _write_json(manifest_path, manifest)
    _write_json(integrity_path, integrity)
    result = init.verify_demo_fixture_integrity(
        source_root=SOURCE_ROOT,
        import_manifest_path=manifest_path,
        integrity_path=integrity_path,
        rules_path=RULES_PATH,
    )
    assert result["ok"] is False
    file_check = next(
        check for check in result["checks"] if check["name"].startswith("file:")
    )
    assert file_check["ok"] is False
    assert "does not exist" in str(file_check["detail"])


def test_verify_detects_path_escape(tmp_path):
    init = _load_init_script()
    escape_path = "../outside.pdf"
    manifest = _real_manifest()
    integrity = _real_integrity()
    manifest["assets"][0]["relative_path"] = escape_path
    integrity["assets"][0]["relative_path"] = escape_path
    manifest_path = tmp_path / "import-manifest.json"
    integrity_path = tmp_path / "fixture-integrity.json"
    _write_json(manifest_path, manifest)
    _write_json(integrity_path, integrity)
    result = init.verify_demo_fixture_integrity(
        source_root=SOURCE_ROOT,
        import_manifest_path=manifest_path,
        integrity_path=integrity_path,
        rules_path=RULES_PATH,
    )
    assert result["ok"] is False
    file_check = next(
        check for check in result["checks"] if check["name"].startswith("file:")
    )
    assert file_check["ok"] is False
    assert "escapes controlled root" in str(file_check["detail"])


def test_verify_detects_rules_fingerprint_mismatch(tmp_path):
    init = _load_init_script()
    rules = _real_rules()
    rules["content_fingerprint"] = "sha256:" + "0" * 64
    rules_path = tmp_path / "demo-bank-rules-v1.json"
    _write_json(rules_path, rules)
    result = init.verify_demo_fixture_integrity(
        source_root=SOURCE_ROOT,
        import_manifest_path=IMPORT_MANIFEST_PATH,
        integrity_path=INTEGRITY_PATH,
        rules_path=rules_path,
    )
    assert result["ok"] is False
    rules_check = next(
        check for check in result["checks"] if check["name"] == "rules"
    )
    assert rules_check["ok"] is False


def test_verify_detects_declared_set_mismatch(tmp_path):
    init = _load_init_script()
    manifest = _real_manifest()
    manifest["assets"][0]["relative_path"] = "客户模拟资料/另一样例.pdf"
    manifest_path = tmp_path / "import-manifest.json"
    _write_json(manifest_path, manifest)
    result = init.verify_demo_fixture_integrity(
        source_root=SOURCE_ROOT,
        import_manifest_path=manifest_path,
        integrity_path=INTEGRITY_PATH,
        rules_path=RULES_PATH,
    )
    assert result["ok"] is False
    set_check = next(
        check for check in result["checks"] if check["name"] == "declared-set"
    )
    assert set_check["ok"] is False


def test_seed_succeeds_with_real_integrity_declaration():
    init = _load_init_script()
    repository = InMemoryControlPlaneRepository()
    summary = init.seed_financial_preassessment_demo(
        repository, integrity_path=INTEGRITY_PATH
    )
    assert summary["asset_count"] == 6
    assert summary["active_version_count"] == 6


def test_seed_fails_closed_on_integrity_mismatch(tmp_path):
    init = _load_init_script()
    integrity = _real_integrity()
    integrity["assets"][0]["sha256"] = "0" * 64
    integrity_path = tmp_path / "fixture-integrity.json"
    _write_json(integrity_path, integrity)
    repository = InMemoryControlPlaneRepository()
    with pytest.raises(ValueError, match="integrity check failed"):
        init.seed_financial_preassessment_demo(
            repository, integrity_path=integrity_path
        )
