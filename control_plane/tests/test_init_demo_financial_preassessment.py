import importlib.util
import json
from pathlib import Path

from control_plane.app.finance_demo_rag import FinanceDemoRagPort
from control_plane.app.main import create_app
from control_plane.app.repository import InMemoryControlPlaneRepository
from control_plane.app.sessions import DemoIdentity

from conftest import AsgiClient

PROJECT_ROOT = Path(__file__).parents[2]
DEMO_ROOT = PROJECT_ROOT / "work" / "demo" / "financial-preassessment"
SOURCE_ROOT = DEMO_ROOT / "source"
IMPORT_MANIFEST_PATH = DEMO_ROOT / "import-manifest.json"
RULES_PATH = DEMO_ROOT / "rules" / "demo-bank-rules-v1.json"
SCRIPTS_PATH = (
    PROJECT_ROOT / "scripts" / "init_demo_financial_preassessment.py"
)


def _load_init_script():
    spec = importlib.util.spec_from_file_location(
        "init_demo_financial_preassessment", SCRIPTS_PATH
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_init_demo_seed_is_idempotent_and_reaches_match_100():
    init = _load_init_script()
    rules = json.loads(RULES_PATH.read_text(encoding="utf-8"))
    repository = InMemoryControlPlaneRepository()

    first = init.seed_financial_preassessment_demo(repository)
    assert first["asset_count"] == 6
    assert first["active_version_count"] == 6
    assert first["rule_version_count"] == 1
    assert first["assets_created"] == 6
    assert first["rule_versions_created"] == 1
    active_after_first = {
        asset.asset_id: asset.active_version_id
        for asset in repository.list_assets("workspace-a")
    }
    audit_count_after_first = len(repository.list_audit_events())

    second = init.seed_financial_preassessment_demo(repository)
    assert second["assets_created"] == 0
    assert second["rule_versions_created"] == 0
    assert second["asset_count"] == first["asset_count"]
    assert second["active_version_count"] == first["active_version_count"]
    assert second["rule_version_count"] == first["rule_version_count"]
    assert {
        asset.asset_id: asset.active_version_id
        for asset in repository.list_assets("workspace-a")
    } == active_after_first
    assert len(repository.list_audit_events()) == audit_count_after_first

    rule_version = next(iter(repository.rule_versions.values()))
    assert rule_version.source_type == "demo_fixture"
    assert rule_version.version_label == "demo-2026-08-14"
    assert rule_version.content_fingerprint == rules["content_fingerprint"]
    assert len(first["assets"]) == 6
    assert all(
        {"asset_id", "path", "active_version_id"} <= set(item)
        for item in first["assets"]
    )
    assert len(first["rule_versions"]) == 1
    assert first["rule_versions"][0]["rule_version_id"] == rule_version.rule_version_id
    assert second["assets"] == first["assets"]
    assert second["rule_versions"] == first["rule_versions"]

    required_keys = _selected_rule_material_keys(rules)
    manifest = json.loads(IMPORT_MANIFEST_PATH.read_text(encoding="utf-8"))
    selected_entries = [
        entry for entry in manifest["assets"] if entry["material_key"] in required_keys
    ]
    asset_ids = [
        repository.find_asset_by_path("workspace-a", entry["relative_path"]).asset_id
        for entry in selected_entries
    ]

    port = FinanceDemoRagPort(
        repository=repository,
        source_root=SOURCE_ROOT,
        import_manifest_path=IMPORT_MANIFEST_PATH,
        rules_path=RULES_PATH,
    )
    app = create_app(
        repository=repository,
        file_executor=object(),
        rag_port=port,
        demo_identities={
            "alice": DemoIdentity(
                username="alice",
                password="demo-a-password",
                actor_id="user-a",
                workspace_id="workspace-a",
                context_version="acl_2026_08_13",
                group_ids=frozenset({"staff"}),
                role_ids=frozenset({"role-member-demo"}),
            )
        },
        internal_service_key="demo-internal-key",
        approver_role_id="role-approver-demo",
        demo_rules_fixture_path=RULES_PATH,
    )
    client = AsgiClient(app)
    login = client.post(
        "/api/session/login",
        json_body={"username": "alice", "password": "demo-a-password"},
    )
    assert login.status_code == 200

    response = client.post(
        "/api/assessments",
        json_body={
            "scenario": "finance_profile_matching",
            "query_subject": "模拟客户资料匹配度",
            "asset_ids": asset_ids,
            "rule_version_id": rule_version.rule_version_id,
        },
    )

    assert response.status_code == 200
    report = response.json()["report"]
    assert report["match_score"] == 100
    assert report["result_level"] == "MATCH"
    assert report["missing_materials"] == []
    assert report["rule_version_evidence"]["content_fingerprint"] == rules[
        "content_fingerprint"
    ]


def _selected_rule_material_keys(rules):
    selected_rule = next(
        rule
        for rule in rules["rules"]
        if rule["rule_id"] == rules["assessment_rule_id"]
    )
    return {
        requirement["material_key"] for requirement in selected_rule["requirements"]
    }
