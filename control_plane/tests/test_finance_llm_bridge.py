"""Finance demo bridge injects the RAG real ExplanationPort after authorization."""

import hashlib
import json
from pathlib import Path

import httpx

from conftest import RecordingHttpxClient, llm_environment
from control_plane.app.domain import (
    Action,
    PermissionGrant,
    PrincipalType,
    TrustedActorContext,
)
from control_plane.app.repository import InMemoryControlPlaneRepository


PROJECT_ROOT = Path(__file__).parents[2]
DEMO_ROOT = PROJECT_ROOT / "work" / "demo" / "financial-preassessment"
SOURCE_ROOT = DEMO_ROOT / "source"
IMPORT_MANIFEST_PATH = DEMO_ROOT / "import-manifest.json"
RULES_PATH = DEMO_ROOT / "rules" / "demo-bank-rules-v1.json"


def _actor() -> TrustedActorContext:
    return TrustedActorContext(
        actor_id="user-a",
        workspace_id="workspace-finance-demo",
        context_version="acl-finance-demo-v1",
        session_id="session-finance-demo-a",
        request_id="request-finance-demo-a",
        run_id="run-finance-demo-a",
        role_ids=frozenset({"role-member-demo"}),
    )


def _selected_rule_material_keys(rules: dict[str, object]) -> set[str]:
    selected_rule = next(
        rule
        for rule in rules["rules"]
        if rule["rule_id"] == rules["assessment_rule_id"]
    )
    return {requirement["material_key"] for requirement in selected_rule["requirements"]}


def _add_ready_asset(
    repository: InMemoryControlPlaneRepository,
    actor: TrustedActorContext,
    relative_path: str,
):
    source_path = SOURCE_ROOT / relative_path
    asset = repository.get_or_create_asset(
        actor.workspace_id,
        relative_path,
        source_path.name,
        actor.actor_id,
    )
    version = repository.create_asset_version(
        asset.asset_id,
        "sha256:" + hashlib.sha256(source_path.read_bytes()).hexdigest(),
        relative_path,
    )
    for state in ("parsing", "indexed", "ready"):
        repository.transition_asset_version(version.asset_version_id, state)
    repository.activate_asset_version(version.asset_version_id)
    return repository.get_asset_version(version.asset_version_id)


def _patch_httpx_client(monkeypatch):
    RecordingHttpxClient.requests = []
    monkeypatch.setattr(httpx, "Client", RecordingHttpxClient)


def test_finance_bridge_invokes_rag_explanation_port_after_authorized_match(
    monkeypatch,
) -> None:
    from control_plane.app.finance_demo_rag import FinanceDemoRagPort
    from service.app.rag.llm import build_llm_explanation_port

    manifest = json.loads(IMPORT_MANIFEST_PATH.read_text(encoding="utf-8"))
    rules = json.loads(RULES_PATH.read_text(encoding="utf-8"))
    actor = _actor()
    repository = InMemoryControlPlaneRepository()
    required_keys = _selected_rule_material_keys(rules)
    versions = tuple(
        _add_ready_asset(repository, actor, entry["relative_path"])
        for entry in manifest["assets"]
        if entry["material_key"] in required_keys
    )
    repository.add_permission_grant(
        PermissionGrant(
            grant_id="finance-llm-query",
            workspace_id=actor.workspace_id,
            context_version=actor.context_version,
            principal_type=PrincipalType.USER,
            principal_id=actor.actor_id,
            action=Action.QUERY,
            path_prefix="客户模拟资料",
        )
    )
    _patch_httpx_client(monkeypatch)
    port = FinanceDemoRagPort(
        repository=repository,
        source_root=SOURCE_ROOT,
        import_manifest_path=IMPORT_MANIFEST_PATH,
        rules_path=RULES_PATH,
        explanation_port=build_llm_explanation_port(llm_environment()),
    )
    from control_plane.app.domain import RuleVersion

    rule_version = RuleVersion(
        rule_version_id="rulever-demo-1",
        rule_set_id="ruleset-demo-1",
        source_type="demo_fixture",
        version_label=rules["version_label"],
        content_fingerprint=rules["content_fingerprint"],
        created_at="2026-08-14T00:00:00Z",
        redacted_rule_summary="受控虚构演示规则，不含真实银行规则。",
    )

    result = port.assess_versions(
        actor,
        tuple(versions),
        rule_version,
        "模拟客户资料匹配度",
    )

    assert result.match_score == 100
    assert result.result_level == "MATCH"
    assert len(RecordingHttpxClient.requests) == 1
    assert "chat/completions" in RecordingHttpxClient.requests[0]["url"]


def test_finance_bridge_denied_before_explanation_port_zero_calls(
    monkeypatch,
) -> None:
    from control_plane.app.finance_demo_rag import FinanceDemoRagPort
    from service.app.rag.llm import build_llm_explanation_port

    manifest = json.loads(IMPORT_MANIFEST_PATH.read_text(encoding="utf-8"))
    rules = json.loads(RULES_PATH.read_text(encoding="utf-8"))
    actor = _actor()
    repository = InMemoryControlPlaneRepository()
    asset = _add_ready_asset(
        repository,
        actor,
        manifest["assets"][0]["relative_path"],
    )
    _patch_httpx_client(monkeypatch)
    port = FinanceDemoRagPort(
        repository=repository,
        source_root=SOURCE_ROOT,
        import_manifest_path=IMPORT_MANIFEST_PATH,
        rules_path=RULES_PATH,
        explanation_port=build_llm_explanation_port(llm_environment()),
    )
    from control_plane.app.domain import RuleVersion

    rule_version = RuleVersion(
        rule_version_id="rulever-demo-1",
        rule_set_id="ruleset-demo-1",
        source_type="demo_fixture",
        version_label=rules["version_label"],
        content_fingerprint=rules["content_fingerprint"],
        created_at="2026-08-14T00:00:00Z",
    )

    try:
        port.assess_versions(
            actor,
            (asset,),
            rule_version,
            "无权模拟客户资料",
        )
    except PermissionError:
        pass
    else:
        raise AssertionError("expected PermissionError for denied finance bridge")

    assert RecordingHttpxClient.requests == []
    assert port.indexed_chunk_count == 0