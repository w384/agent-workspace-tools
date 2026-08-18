import hashlib
import json
from dataclasses import replace
from pathlib import Path

from control_plane.app.domain import (
    Action,
    PermissionGrant,
    PrincipalType,
    TrustedActorContext,
)
from control_plane.app.main import create_app
from control_plane.app.repository import InMemoryControlPlaneRepository
from control_plane.app.service import ControlPlaneService
from control_plane.app.sessions import DemoIdentity

from conftest import AsgiClient


PROJECT_ROOT = Path(__file__).parents[2]
DEMO_ROOT = PROJECT_ROOT / "work" / "demo" / "financial-preassessment"
SOURCE_ROOT = DEMO_ROOT / "source"
IMPORT_MANIFEST_PATH = DEMO_ROOT / "import-manifest.json"
RULES_PATH = DEMO_ROOT / "rules" / "demo-bank-rules-v1.json"


def test_finance_demo_rag_port_parses_manifest_declared_pdf_docx_and_matches_rule():
    from control_plane.app.finance_demo_rag import FinanceDemoRagPort

    manifest = json.loads(IMPORT_MANIFEST_PATH.read_text(encoding="utf-8"))
    rules = json.loads(RULES_PATH.read_text(encoding="utf-8"))
    actor = _actor()
    repository = InMemoryControlPlaneRepository()
    required_keys = _selected_rule_material_keys(rules)
    selected_assets = [
        entry
        for entry in manifest["assets"]
        if entry["material_key"] in required_keys
    ]
    versions = tuple(
        _add_ready_asset(repository, actor, entry["relative_path"])
        for entry in selected_assets
    )
    repository.add_permission_grant(
        PermissionGrant(
            grant_id="finance-demo-query",
            workspace_id=actor.workspace_id,
            context_version=actor.context_version,
            principal_type=PrincipalType.USER,
            principal_id=actor.actor_id,
            action=Action.QUERY,
            path_prefix="客户模拟资料",
        )
    )
    port = FinanceDemoRagPort(
        repository=repository,
        source_root=SOURCE_ROOT,
        import_manifest_path=IMPORT_MANIFEST_PATH,
        rules_path=RULES_PATH,
    )
    service = ControlPlaneService(
        repository,
        object(),
        port,
        approver_role_id="role-approver-demo",
    )
    rule = service.create_rule_set_with_version(
        actor,
        scenario="finance_profile_matching",
        name=rules["rule_set_name"],
        status="active",
        source_type=rules["source_type"],
        version_label=rules["version_label"],
        content_fingerprint=rules["content_fingerprint"],
        redacted_rule_summary="受控虚构演示规则，不含真实银行规则。",
    ).rule_version

    outcome = service.create_assessment_report(
        actor,
        scenario="finance_profile_matching",
        query_subject="模拟客户资料匹配度",
        asset_ids=tuple(
            repository.get_asset(version.asset_id).asset_id for version in versions
        ),
        rule_version_id=rule.rule_version_id,
    )

    report = outcome.report
    assert report.match_score == 100
    assert report.result_level == "MATCH"
    assert report.missing_materials == ()
    assert report.bank_label == "示例银行A"
    assert report.asset_versions == tuple(
        version.asset_version_id for version in versions
    )
    assert report.rule_version_evidence["rule_version_id"] == rule.rule_version_id
    assert report.rule_version_evidence["content_fingerprint"] == rules[
        "content_fingerprint"
    ]
    material_citations = [
        citation for citation in report.citations if citation["citation_type"] == "material"
    ]
    rule_citations = [
        citation for citation in report.citations if citation["citation_type"] == "rule"
    ]
    assert rule_citations
    assert {citation["asset_version_id"] for citation in material_citations} == {
        version.asset_version_id for version in versions
    }
    assert any(citation["page"] == 1 for citation in material_citations)
    assert any(citation["paragraph"] is not None for citation in material_citations)
    assert all(
        {
            "rule_id",
            "rule_version_id",
            "version_label",
            "content_fingerprint",
            "source_type",
        }
        <= set(citation)
        for citation in rule_citations
    )
    assert port.indexed_chunk_count >= len(material_citations)
    assert port.parsed_mime_types == {
        "application/pdf",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    }


def test_finance_demo_rag_port_is_not_called_when_bff_denies_access():
    from control_plane.app.finance_demo_rag import FinanceDemoRagPort

    manifest = json.loads(IMPORT_MANIFEST_PATH.read_text(encoding="utf-8"))
    rules = json.loads(RULES_PATH.read_text(encoding="utf-8"))
    actor = _actor()
    repository = InMemoryControlPlaneRepository()
    asset = _add_ready_asset(
        repository,
        actor,
        manifest["assets"][0]["relative_path"],
    )
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
                password="controlled-finance-demo-password",
                actor_id=actor.actor_id,
                workspace_id=actor.workspace_id,
                context_version=actor.context_version,
                role_ids=actor.role_ids,
            )
        },
        internal_service_key="controlled-finance-demo-internal-key",
        approver_role_id="role-approver-demo",
    )
    client = AsgiClient(app)
    assert client.post(
        "/api/session/login",
        json_body={
            "username": "alice",
            "password": "controlled-finance-demo-password",
        },
    ).status_code == 200
    rule_response = client.post(
        "/api/rule-sets",
        json_body={
            "scenario": "finance_profile_matching",
            "name": rules["rule_set_name"],
            "status": "active",
            "source_type": rules["source_type"],
            "version_label": rules["version_label"],
            "content_fingerprint": rules["content_fingerprint"],
            "redacted_rule_summary": "受控虚构演示规则，不含真实银行规则。",
        },
    )
    assert rule_response.status_code == 200

    response = client.post(
        "/api/assessments",
        json_body={
            "scenario": "finance_profile_matching",
            "query_subject": "无权模拟客户资料",
            "asset_ids": [asset.asset_id],
            "rule_version_id": rule_response.json()["rule_version"]["rule_version_id"],
        },
    )

    assert response.status_code == 403
    assert response.json() == {
        "status": "DENIED",
        "reason": "ACCESS_DENIED",
        "retrieved_count": 0,
        "llm_invoked": False,
        "citations": [],
        "error": {
            "code": "assessment_denied",
            "message": "Assessment is not authorized",
        },
    }
    assert port.indexed_chunk_count == 0
    assert port.parsed_mime_types == frozenset()
    assert repository.assessment_reports == {}
    denied_details = repository.list_audit_events()[-1].details
    assert denied_details == {
        "scenario": "finance_profile_matching",
        "decision": "DENY",
        "query_subject": "无权模拟客户资料",
        "rule_version_id": rule_response.json()["rule_version"]["rule_version_id"],
        "requested_asset_ids": [asset.asset_id],
        "retrieved_count": 0,
        "llm_invoked": False,
        "citations": [],
    }


def test_assessment_api_returns_real_finance_bridge_evidence_and_audit_fields():
    from control_plane.app.finance_demo_rag import FinanceDemoRagPort

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
            grant_id="finance-api-query",
            workspace_id=actor.workspace_id,
            context_version=actor.context_version,
            principal_type=PrincipalType.USER,
            principal_id=actor.actor_id,
            action=Action.QUERY,
            path_prefix="客户模拟资料",
        )
    )
    port = FinanceDemoRagPort(
        repository=repository,
        source_root=SOURCE_ROOT,
        import_manifest_path=IMPORT_MANIFEST_PATH,
        rules_path=RULES_PATH,
    )
    client = _finance_demo_client(repository, actor, port)
    rule_version_id = _create_rule_version(client, rules)

    response = client.post(
        "/api/assessments",
        json_body={
            "scenario": "finance_profile_matching",
            "query_subject": "模拟客户资料匹配度",
            "asset_ids": [version.asset_id for version in versions],
            "rule_version_id": rule_version_id,
        },
    )

    assert response.status_code == 200
    report = response.json()["report"]
    assert report["match_score"] == 100
    assert isinstance(report["match_score"], int)
    assert report["result_level"] == "MATCH"
    assert report["missing_materials"] == []
    assert report["bank_label"] == "示例银行A"
    assert report["disclaimer"]
    assert all(
        term not in report["disclaimer"]
        for term in ("贷款审批", "授信", "额度测算")
    )
    material_citations = [
        citation for citation in report["citations"] if citation["citation_type"] == "material"
    ]
    rule_citations = [
        citation for citation in report["citations"] if citation["citation_type"] == "rule"
    ]
    assert rule_citations
    assert all(
        {
            "asset_id",
            "asset_version_id",
            "chunk_id",
            "page",
            "paragraph",
            "rule_version_id",
        }
        <= set(citation)
        for citation in material_citations
    )
    assert {citation["asset_version_id"] for citation in material_citations} == {
        version.asset_version_id for version in versions
    }
    assert all(
        {
            "rule_id",
            "rule_version_id",
            "version_label",
            "content_fingerprint",
            "source_type",
        }
        <= set(citation)
        for citation in rule_citations
    )
    assert report["rule_version_evidence"]["rule_version_id"] == rule_version_id
    audit = repository.list_audit_events()[-1]
    assert audit.event_type == "assessment_report_created"
    assert audit.actor_id == actor.actor_id
    assert audit.details["asset_version_ids"] == [
        version.asset_version_id for version in versions
    ]
    assert audit.details["rule_version_id"] == rule_version_id
    assert audit.details["report_id"] == report["report_id"]
    assert audit.details["disclaimer_version"] == report["disclaimer_version"]
    assert audit.details["rule_source_type"] == "demo_fixture"
    assert audit.details["match_score"] == 100
    assert audit.details["result_level"] == "MATCH"
    assert audit.details["report_created_at"] == report["created_at"]


def test_assessment_api_fails_closed_when_rule_version_fingerprint_mismatches():
    from control_plane.app.finance_demo_rag import FinanceDemoRagPort

    manifest = json.loads(IMPORT_MANIFEST_PATH.read_text(encoding="utf-8"))
    rules = json.loads(RULES_PATH.read_text(encoding="utf-8"))
    actor = _actor()
    repository = InMemoryControlPlaneRepository()
    asset = _add_ready_asset(
        repository,
        actor,
        manifest["assets"][0]["relative_path"],
    )
    repository.add_permission_grant(
        PermissionGrant(
            grant_id="finance-rule-mismatch-query",
            workspace_id=actor.workspace_id,
            context_version=actor.context_version,
            principal_type=PrincipalType.USER,
            principal_id=actor.actor_id,
            action=Action.QUERY,
            path_prefix="客户模拟资料",
        )
    )
    port = FinanceDemoRagPort(
        repository=repository,
        source_root=SOURCE_ROOT,
        import_manifest_path=IMPORT_MANIFEST_PATH,
        rules_path=RULES_PATH,
    )
    client = _finance_demo_client(repository, actor, port)
    rule_version_id = _create_rule_version(client, rules)
    repository.rule_versions[rule_version_id] = replace(
        repository.get_rule_version(rule_version_id),
        content_fingerprint="sha256:mismatched-demo-rule",
    )

    response = client.post(
        "/api/assessments",
        json_body={
            "scenario": "finance_profile_matching",
            "query_subject": "规则指纹错配",
            "asset_ids": [asset.asset_id],
            "rule_version_id": rule_version_id,
        },
    )

    assert response.status_code == 502
    assert response.json()["error"]["code"] == "assessment_failed"
    assert repository.assessment_reports == {}
    assert port.indexed_chunk_count == 0
    assert port.parsed_mime_types == frozenset()
    assert repository.list_audit_events()[-1].event_type == "assessment_failed"


def test_assessment_api_fails_closed_when_asset_version_fingerprint_mismatches():
    from control_plane.app.finance_demo_rag import FinanceDemoRagPort

    manifest = json.loads(IMPORT_MANIFEST_PATH.read_text(encoding="utf-8"))
    rules = json.loads(RULES_PATH.read_text(encoding="utf-8"))
    actor = _actor()
    repository = InMemoryControlPlaneRepository()
    version = _add_ready_asset(repository, actor, manifest["assets"][0]["relative_path"])
    repository._asset_versions[version.asset_version_id] = replace(
        version,
        content_fingerprint="sha256:" + "0" * 64,
    )
    repository.add_permission_grant(
        PermissionGrant(
            grant_id="finance-asset-fingerprint-mismatch-query",
            workspace_id=actor.workspace_id,
            context_version=actor.context_version,
            principal_type=PrincipalType.USER,
            principal_id=actor.actor_id,
            action=Action.QUERY,
            path_prefix="客户模拟资料",
        )
    )
    port = FinanceDemoRagPort(
        repository=repository,
        source_root=SOURCE_ROOT,
        import_manifest_path=IMPORT_MANIFEST_PATH,
        rules_path=RULES_PATH,
    )
    client = _finance_demo_client(repository, actor, port)
    rule_version_id = _create_rule_version(client, rules)

    response = client.post(
        "/api/assessments",
        json_body={
            "scenario": "finance_profile_matching",
            "query_subject": "asset-fingerprint-mismatch",
            "asset_ids": [version.asset_id],
            "rule_version_id": rule_version_id,
        },
    )

    assert response.status_code == 502
    assert response.json()["error"]["code"] == "assessment_failed"
    assert repository.assessment_reports == {}
    assert port.indexed_chunk_count == 0
    assert port.parsed_mime_types == frozenset()
    assert repository.list_audit_events()[-1].event_type == "assessment_failed"


def test_assessment_api_fails_closed_for_source_not_declared_by_import_manifest():
    from control_plane.app.finance_demo_rag import FinanceDemoRagPort

    manifest = json.loads(IMPORT_MANIFEST_PATH.read_text(encoding="utf-8"))
    rules = json.loads(RULES_PATH.read_text(encoding="utf-8"))
    declared_paths = {entry["relative_path"] for entry in manifest["assets"]}
    undeclared_path = next(
        path.relative_to(SOURCE_ROOT).as_posix()
        for path in SOURCE_ROOT.rglob("*")
        if path.is_file() and path.relative_to(SOURCE_ROOT).as_posix() not in declared_paths
    )
    actor = _actor()
    repository = InMemoryControlPlaneRepository()
    asset = _add_ready_asset(repository, actor, undeclared_path)
    repository.add_permission_grant(
        PermissionGrant(
            grant_id="finance-undeclared-source-query",
            workspace_id=actor.workspace_id,
            context_version=actor.context_version,
            principal_type=PrincipalType.USER,
            principal_id=actor.actor_id,
            action=Action.QUERY,
            path_prefix=undeclared_path.rsplit("/", 1)[0],
        )
    )
    port = FinanceDemoRagPort(
        repository=repository,
        source_root=SOURCE_ROOT,
        import_manifest_path=IMPORT_MANIFEST_PATH,
        rules_path=RULES_PATH,
    )
    client = _finance_demo_client(repository, actor, port)
    rule_version_id = _create_rule_version(client, rules)

    response = client.post(
        "/api/assessments",
        json_body={
            "scenario": "finance_profile_matching",
            "query_subject": "未声明资料",
            "asset_ids": [asset.asset_id],
            "rule_version_id": rule_version_id,
        },
    )

    assert response.status_code == 502
    assert response.json()["error"]["code"] == "assessment_failed"
    assert repository.assessment_reports == {}
    assert port.indexed_chunk_count == 0
    assert port.parsed_mime_types == frozenset()


def test_assessment_api_returns_possible_when_authorized_materials_are_incomplete():
    from control_plane.app.finance_demo_rag import FinanceDemoRagPort

    manifest = json.loads(IMPORT_MANIFEST_PATH.read_text(encoding="utf-8"))
    rules = json.loads(RULES_PATH.read_text(encoding="utf-8"))
    actor = _actor()
    repository = InMemoryControlPlaneRepository()
    income_entry = next(
        entry
        for entry in manifest["assets"]
        if entry["material_key"] == "income_statement"
    )
    asset = _add_ready_asset(repository, actor, income_entry["relative_path"])
    repository.add_permission_grant(
        PermissionGrant(
            grant_id="finance-incomplete-query",
            workspace_id=actor.workspace_id,
            context_version=actor.context_version,
            principal_type=PrincipalType.USER,
            principal_id=actor.actor_id,
            action=Action.QUERY,
            path_prefix="客户模拟资料",
        )
    )
    port = FinanceDemoRagPort(
        repository=repository,
        source_root=SOURCE_ROOT,
        import_manifest_path=IMPORT_MANIFEST_PATH,
        rules_path=RULES_PATH,
    )
    client = _finance_demo_client(repository, actor, port)
    rule_version_id = _create_rule_version(client, rules)

    response = client.post(
        "/api/assessments",
        json_body={
            "scenario": "finance_profile_matching",
            "query_subject": "材料不完整",
            "asset_ids": [asset.asset_id],
            "rule_version_id": rule_version_id,
        },
    )

    assert response.status_code == 200
    report = response.json()["report"]
    assert report["match_score"] == 33
    assert report["result_level"] == "POSSIBLE"
    assert report["result_level"] != "NOT_MATCH"
    assert report["bank_label"] == "示例银行A"
    assert len(report["missing_materials"]) == 2


def test_bff_rule_set_api_uses_controlled_fixture_fingerprint_and_assessment_closes_loop():
    from control_plane.app.finance_demo_rag import FinanceDemoRagPort

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
            grant_id="finance-frontend-loop-query",
            workspace_id=actor.workspace_id,
            context_version=actor.context_version,
            principal_type=PrincipalType.USER,
            principal_id=actor.actor_id,
            action=Action.QUERY,
            path_prefix="客户模拟资料",
        )
    )
    port = FinanceDemoRagPort(
        repository=repository,
        source_root=SOURCE_ROOT,
        import_manifest_path=IMPORT_MANIFEST_PATH,
        rules_path=RULES_PATH,
    )
    client = _finance_demo_client(repository, actor, port, demo_rules_fixture_path=RULES_PATH)

    # The frontend "创建演示规则版本" button no longer sends a hardcoded
    # fingerprint; the BFF resolves the controlled fixture fingerprint itself.
    rule_response = client.post(
        "/api/rule-sets",
        json_body={
            "scenario": "finance_profile_matching",
            "name": rules["rule_set_name"],
            "status": "active",
            "source_type": rules["source_type"],
            "version_label": rules["version_label"],
            "redacted_rule_summary": "受控虚构演示规则，不含真实银行规则。",
        },
    )
    assert rule_response.status_code == 200
    rule_version = rule_response.json()["rule_version"]
    assert rule_version["source_type"] == "demo_fixture"
    assert rule_version["version_label"] == "demo-2026-08-14"
    assert rule_version["content_fingerprint"] == rules["content_fingerprint"]

    response = client.post(
        "/api/assessments",
        json_body={
            "scenario": "finance_profile_matching",
            "query_subject": "模拟客户资料匹配度",
            "asset_ids": [version.asset_id for version in versions],
            "rule_version_id": rule_version["rule_version_id"],
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


def test_bff_rule_set_api_fails_closed_when_client_fingerprint_mismatches_controlled_fixture():
    from control_plane.app.finance_demo_rag import FinanceDemoRagPort

    rules = json.loads(RULES_PATH.read_text(encoding="utf-8"))
    actor = _actor()
    repository = InMemoryControlPlaneRepository()
    port = FinanceDemoRagPort(
        repository=repository,
        source_root=SOURCE_ROOT,
        import_manifest_path=IMPORT_MANIFEST_PATH,
        rules_path=RULES_PATH,
    )
    client = _finance_demo_client(repository, actor, port, demo_rules_fixture_path=RULES_PATH)

    response = client.post(
        "/api/rule-sets",
        json_body={
            "scenario": "finance_profile_matching",
            "name": rules["rule_set_name"],
            "status": "active",
            "source_type": rules["source_type"],
            "version_label": rules["version_label"],
            "content_fingerprint": "sha256:rule-demo-v1",
            "redacted_rule_summary": "受控虚构演示规则，不含真实银行规则。",
        },
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "rule_fingerprint_mismatch"
    assert repository.rule_sets == {}
    assert repository.rule_versions == {}


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


def _finance_demo_client(repository, actor, port, demo_rules_fixture_path=None):
    app = create_app(
        repository=repository,
        file_executor=object(),
        rag_port=port,
        demo_identities={
            "alice": DemoIdentity(
                username="alice",
                password="controlled-finance-demo-password",
                actor_id=actor.actor_id,
                workspace_id=actor.workspace_id,
                context_version=actor.context_version,
                role_ids=actor.role_ids,
            )
        },
        internal_service_key="controlled-finance-demo-internal-key",
        approver_role_id="role-approver-demo",
        demo_rules_fixture_path=demo_rules_fixture_path,
    )
    client = AsgiClient(app)
    response = client.post(
        "/api/session/login",
        json_body={
            "username": "alice",
            "password": "controlled-finance-demo-password",
        },
    )
    assert response.status_code == 200
    return client


def _create_rule_version(client, rules):
    response = client.post(
        "/api/rule-sets",
        json_body={
            "scenario": "finance_profile_matching",
            "name": rules["rule_set_name"],
            "status": "active",
            "source_type": rules["source_type"],
            "version_label": rules["version_label"],
            "content_fingerprint": rules["content_fingerprint"],
            "redacted_rule_summary": "受控虚构演示规则，不含真实银行规则。",
        },
    )
    assert response.status_code == 200
    return response.json()["rule_version"]["rule_version_id"]
