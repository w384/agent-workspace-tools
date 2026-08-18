"""Composite finance-demo bridge: real-LLM path B + deterministic path A.

Covers:
  1. alice (authorized) asks about an authorized controlled asset -> ANSWERED,
     llm_invoked=True, real LLM answer, versioned citations.
  2. bob (no QUERY grant) asks about the same asset -> DENIED/ACCESS_DENIED,
     llm_invoked=False, zero retrieval, zero LLM calls.
  3. Path A assess_versions still matches MATCH 100 through the composite port.
"""

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
WORKSPACE_ID = "workspace-a"
ACTOR_A = "user-a"
ACTOR_B = "user-b"
CONTEXT_VERSION = "acl_2026_08_13"


def _manifest() -> dict[str, object]:
    return json.loads(IMPORT_MANIFEST_PATH.read_text(encoding="utf-8"))


def _rules() -> dict[str, object]:
    return json.loads(RULES_PATH.read_text(encoding="utf-8"))


def _add_ready_asset(
    repository: InMemoryControlPlaneRepository,
    relative_path: str,
    *,
    created_by: str,
):
    source_path = SOURCE_ROOT / relative_path
    asset = repository.get_or_create_asset(
        WORKSPACE_ID,
        relative_path,
        source_path.name,
        created_by,
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


def _grant_query(
    repository: InMemoryControlPlaneRepository,
    *,
    actor_id: str,
    path_prefix: str,
) -> None:
    repository.add_permission_grant(
        PermissionGrant(
            grant_id=f"grant-{actor_id}-{len(repository.permission_grants)}",
            workspace_id=WORKSPACE_ID,
            context_version=CONTEXT_VERSION,
            principal_type=PrincipalType.USER,
            principal_id=actor_id,
            action=Action.QUERY,
            path_prefix=path_prefix,
        )
    )


def _actor(actor_id: str) -> TrustedActorContext:
    return TrustedActorContext(
        actor_id=actor_id,
        workspace_id=WORKSPACE_ID,
        context_version=CONTEXT_VERSION,
        session_id=f"session-{actor_id}",
        request_id=f"request-{actor_id}",
        run_id=f"run-{actor_id}",
        role_ids=frozenset({"role-member-demo"}),
    )


def _patch_httpx_client(monkeypatch) -> None:
    RecordingHttpxClient.requests = []
    monkeypatch.setattr(httpx, "Client", RecordingHttpxClient)


def _build_port(repository: InMemoryControlPlaneRepository, monkeypatch):
    from control_plane.app.finance_demo_llm_rag import FinanceDemoLlmRagPort
    from service.app.rag.llm import build_llm_answer_generator

    _patch_httpx_client(monkeypatch)
    return FinanceDemoLlmRagPort(
        repository=repository,
        source_root=SOURCE_ROOT,
        import_manifest_path=IMPORT_MANIFEST_PATH,
        rules_path=RULES_PATH,
        workspace_id=WORKSPACE_ID,
        answer_generator=build_llm_answer_generator(llm_environment()),
    )


def test_path_b_alice_authorized_real_llm_answer(
    file_executor, demo_identities, monkeypatch
) -> None:
    from control_plane.app.main import create_app
    from conftest import AsgiClient

    manifest = _manifest()
    first = manifest["assets"][0]
    relative_path = first["relative_path"]
    repository = InMemoryControlPlaneRepository()
    version = _add_ready_asset(repository, relative_path, created_by=ACTOR_A)
    _grant_query(repository, actor_id=ACTOR_A, path_prefix="客户模拟资料")
    port = _build_port(repository, monkeypatch)
    app = create_app(
        repository=repository,
        file_executor=file_executor,
        rag_port=port,
        demo_identities=demo_identities,
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
        "/api/retrieval/query",
        json_body={"question": "该客户资金情况如何？", "asset_id": version.asset_id},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ANSWERED"
    assert payload["answer"] == "LLM 依据授权证据生成的回答"
    assert payload["llm_invoked"] is True
    assert len(RecordingHttpxClient.requests) == 1
    assert payload["citations"], "expected at least one versioned citation"
    citation = payload["citations"][0]
    assert citation["asset_id"] == version.asset_id
    assert citation["asset_version_id"] == version.asset_version_id


def test_path_b_bob_denied_zero_llm_calls(
    file_executor, demo_identities, monkeypatch
) -> None:
    from control_plane.app.main import create_app
    from conftest import AsgiClient

    manifest = _manifest()
    first = manifest["assets"][0]
    relative_path = first["relative_path"]
    repository = InMemoryControlPlaneRepository()
    version = _add_ready_asset(repository, relative_path, created_by=ACTOR_A)
    _grant_query(repository, actor_id=ACTOR_A, path_prefix="客户模拟资料")
    # bob has NO QUERY grant -> denied before retrieval/LLM
    port = _build_port(repository, monkeypatch)
    app = create_app(
        repository=repository,
        file_executor=file_executor,
        rag_port=port,
        demo_identities=demo_identities,
        internal_service_key="demo-internal-key",
        approver_role_id="role-approver-demo",
        demo_rules_fixture_path=RULES_PATH,
    )
    client = AsgiClient(app)
    login = client.post(
        "/api/session/login",
        json_body={"username": "bob", "password": "demo-b-password"},
    )
    assert login.status_code == 200

    response = client.post(
        "/api/retrieval/query",
        json_body={"question": "该客户资金情况如何？", "asset_id": version.asset_id},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "DENIED"
    assert payload["reason"] == "ACCESS_DENIED"
    assert payload["answer"] is None
    assert payload["llm_invoked"] is False
    assert payload["retrieved_count"] == 0
    assert payload["citations"] == []
    assert RecordingHttpxClient.requests == []


def test_path_a_assess_still_matches_100(
    monkeypatch,
) -> None:
    from control_plane.app.domain import RuleVersion
    from service.app.rag.llm import build_llm_explanation_port

    manifest = _manifest()
    rules = _rules()
    actor = _actor(ACTOR_A)
    repository = InMemoryControlPlaneRepository()
    versions = tuple(
        _add_ready_asset(repository, entry["relative_path"], created_by=ACTOR_A)
        for entry in manifest["assets"]
    )
    _grant_query(repository, actor_id=ACTOR_A, path_prefix="客户模拟资料")
    _patch_httpx_client(monkeypatch)
    from control_plane.app.finance_demo_llm_rag import FinanceDemoLlmRagPort

    port = FinanceDemoLlmRagPort(
        repository=repository,
        source_root=SOURCE_ROOT,
        import_manifest_path=IMPORT_MANIFEST_PATH,
        rules_path=RULES_PATH,
        workspace_id=WORKSPACE_ID,
        explanation_port=build_llm_explanation_port(llm_environment()),
    )
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
        versions,
        rule_version,
        "模拟客户资料匹配度",
    )

    assert result.match_score == 100
    assert result.result_level == "MATCH"
    assert result.missing_materials == ()
    assert result.bank_label
