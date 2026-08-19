import json
from pathlib import Path


PROJECT_ROOT = Path(__file__).parents[2]
DEMO_ROOT = PROJECT_ROOT / "work" / "demo" / "financial-preassessment"
SOURCE_ROOT = DEMO_ROOT / "source"
RULES_PATH = DEMO_ROOT / "rules" / "demo-bank-rules-v1.json"
IMPORT_MANIFEST_PATH = DEMO_ROOT / "import-manifest.json"


def test_financial_preassessment_demo_assets_are_fictional_and_versioned():
    expected_files = {
        "客户模拟资料/资料概览与授权说明.docx",
        "客户模拟资料/收入情况说明.pdf",
        "客户模拟资料/资金流摘要.pdf",
        "客户模拟资料/资产负债说明.docx",
        "客户模拟资料/经营情况说明.docx",
        "客户模拟资料/补充材料清单.pdf",
        "敏感资料/内部资料核验说明.docx",
        "规则依据/演示规则适用说明.pdf",
    }

    actual_files = {
        path.relative_to(SOURCE_ROOT).as_posix()
        for path in SOURCE_ROOT.rglob("*")
        if path.is_file()
    }
    assert actual_files == expected_files
    for path in SOURCE_ROOT.rglob("*"):
        if path.suffix == ".pdf":
            assert path.read_bytes().startswith(b"%PDF")
        elif path.suffix == ".docx":
            assert path.read_bytes().startswith(b"PK")

    rules = json.loads(RULES_PATH.read_text(encoding="utf-8"))
    assert rules["source_type"] == "demo_fixture"
    assert rules["scenario"] == "finance_profile_matching"
    assert rules["version_label"] == "demo-2026-08-14"
    assert rules["assessment_rule_id"] == "demo-bank-a-complete"
    assert "仅供资料完整度与规则匹配演示参考" in rules["disclaimer"]
    assert len(rules["rules"]) == 5
    assert {rule["result_level"] for rule in rules["rules"]} == {
        "MATCH",
        "POSSIBLE",
        "NOT_MATCH",
    }


def test_financial_preassessment_import_manifest_declares_material_keys() -> None:
    manifest = json.loads(IMPORT_MANIFEST_PATH.read_text(encoding="utf-8"))
    rules = json.loads(RULES_PATH.read_text(encoding="utf-8"))

    assert set(manifest) == {"source_type", "scenario", "assets"}
    assert manifest["source_type"] == "demo_fixture"
    assert manifest["scenario"] == "finance_profile_matching"
    assert {
        entry["relative_path"] for entry in manifest["assets"]
    } <= {
        path.relative_to(SOURCE_ROOT).as_posix()
        for path in SOURCE_ROOT.rglob("*")
        if path.is_file()
    }
    assert {
        entry["material_key"] for entry in manifest["assets"]
    } >= {"income_statement", "cashflow_summary", "asset_liability_statement"}
    selected_rule = next(
        rule for rule in rules["rules"] if rule["rule_id"] == rules["assessment_rule_id"]
    )
    assert all(
        set(requirement) == {"rule_id", "material_key", "label"}
        for requirement in selected_rule["requirements"]
    )
    assert all("score" not in requirement for requirement in selected_rule["requirements"])
