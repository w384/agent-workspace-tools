"""BFF controlled-sample bridge: select file -> auto assess / auto query.

Covers the P1 "选中即自动发起" flow. The frontend only submits the
import-manifest controlled file name; the BFF resolves it to the asset and
re-uses the existing authorization gates (evaluate_authorization inside
create_assessment_report and DemoRagPort.query). asset_id never has to be
typed by the user and never bypasses authorization.
"""

import hashlib
import json
from pathlib import Path

from control_plane.app.domain import (
    Action,
    PermissionGrant,
    PrincipalType,
)
from control_plane.app.repository import InMemoryControlPlaneRepository

from conftest import AsgiClient


PROJECT_ROOT = Path(__file__).parents[2]
DEMO_ROOT = PROJECT_ROOT / "work" / "demo" / "financial-preassessment"
SOURCE_ROOT = DEMO_ROOT / "source"
IMPORT_MANIFEST_PATH = DEMO_ROOT / "import-manifest.json"
RULES_PATH = DEMO_ROOT / "rules" / "demo-bank-rules-v1.json"
WORKSPACE_ID = "workspace-a"
ACTOR_A = "user-a"
ACTOR_B = "user-b"
ACTOR_C = "user-c"
CONTEXT_VERSION = "acl_2026_08_13"
VERSION_LABEL = "demo-2026-08-14"
SCENARIO = "finance_profile_matching"


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
    return asset, repository.get_asset_version(version.asset_version_id)


def _seed_all_assets(repository: InMemoryControlPlaneRepository) -> dict[str, object]:
    manifest = _manifest()
    mapping = {}
    for entry in manifest["assets"]:
        asset, version = _add_ready_asset(
            repository, entry["relative_path"], created_by=ACTOR_A
        )
        mapping[entry["relative_path"]] = {
            "asset_id": asset.asset_id,
            "asset_version_id": version.asset_version_id,
        }
    return mapping


def _grant_query(
    repository: InMemoryControlPlaneRepository,
    *,
    actor_id: str,
    path_prefix: str = "客户模拟资料",
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


def _seed_rule_version(repository: InMemoryControlPlaneRepository) -> str:
    rules = _rules()
    from control_plane.app.domain import RuleSet, RuleVersion

    rule_set = repository.create_rule_set(
        RuleSet(
            rule_set_id="ruleset-demo-controlled",
            scenario=SCENARIO,
            name="demo-bank-rules-v1",
            status="active",
        )
    )
    rule_version = repository.create_rule_version(
        RuleVersion(
            rule_version_id="rulever-demo-controlled",
            rule_set_id=rule_set.rule_set_id,
            source_type="demo_fixture",
            version_label=VERSION_LABEL,
            content_fingerprint=rules["content_fingerprint"],
            created_at="2026-08-14T00:00:00Z",
            redacted_rule_summary="受控虚构演示规则，不含真实银行规则。",
        )
    )
    return rule_version.rule_version_id


def _build_app(repository: InMemoryControlPlaneRepository, monkeypatch, identities):
    from control_plane.app.main import create_app

    from control_plane.app.finance_demo_llm_rag import FinanceDemoLlmRagPort
    from service.app.rag.llm import build_llm_answer_generator, build_llm_explanation_port
    from conftest import RecordingHttpxClient, llm_environment

    import httpx

    RecordingHttpxClient.requests = []
    monkeypatch.setattr(httpx, "Client", RecordingHttpxClient)

    port = FinanceDemoLlmRagPort(
        repository=repository,
        source_root=SOURCE_ROOT,
        import_manifest_path=IMPORT_MANIFEST_PATH,
        rules_path=RULES_PATH,
        workspace_id=WORKSPACE_ID,
        answer_generator=build_llm_answer_generator(llm_environment()),
        explanation_port=build_llm_explanation_port(llm_environment()),
    )
    return create_app(
        repository=repository,
        file_executor=object(),
        rag_port=port,
        demo_identities=identities,
        internal_service_key="demo-internal-key",
        approver_role_id="role-approver-demo",
        demo_rules_fixture_path=RULES_PATH,
    )


def _login(client: AsgiClient, username: str, password: str) -> None:
    response = client.post(
        "/api/session/login",
        json_body={"username": username, "password": password},
    )
    assert response.status_code == 200


def _first_file_name() -> str:
    manifest = _manifest()
    return Path(manifest["assets"][0]["relative_path"]).name


def test_alice_controlled_sample_auto_assess(
    demo_identities, monkeypatch
) -> None:
    repository = InMemoryControlPlaneRepository()
    _seed_all_assets(repository)
    _grant_query(repository, actor_id=ACTOR_A)
    _seed_rule_version(repository)
    app = _build_app(repository, monkeypatch, demo_identities)
    client = AsgiClient(app)
    _login(client, "alice", "demo-a-password")

    file_name = _first_file_name()
    response = client.post(
        "/api/controlled-sample/assess",
        json_body={
            "scenario": SCENARIO,
            "query_subject": "customer-demo-001",
            "file_names": [file_name],
        },
    )

    assert response.status_code == 200
    payload = response.json()
    report = payload["report"]
    assert report["scenario"] == SCENARIO
    assert report["rule_version_id"] == "rulever-demo-controlled"
    assert report["actor_id"] == ACTOR_A
    assert "match_score" in report
    assert "result_level" in report
    assert report["bank_label"] is not None


def test_alice_controlled_sample_auto_query_answer_llm(
    demo_identities, monkeypatch
) -> None:
    repository = InMemoryControlPlaneRepository()
    _seed_all_assets(repository)
    _grant_query(repository, actor_id=ACTOR_A)
    app = _build_app(repository, monkeypatch, demo_identities)
    client = AsgiClient(app)
    _login(client, "alice", "demo-a-password")

    file_name = _first_file_name()
    response = client.post(
        "/api/controlled-sample/query",
        json_body={"question": "该客户资金情况如何？", "file_name": file_name},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ANSWERED"
    assert payload["llm_invoked"] is True
    assert payload["citations"], "expected at least one citation"


def test_bob_controlled_sample_denied(
    demo_identities, monkeypatch
) -> None:
    repository = InMemoryControlPlaneRepository()
    _seed_all_assets(repository)
    _grant_query(repository, actor_id=ACTOR_A)  # bob has NO grant
    app = _build_app(repository, monkeypatch, demo_identities)
    client = AsgiClient(app)
    _login(client, "bob", "demo-b-password")

    file_name = _first_file_name()
    response = client.post(
        "/api/controlled-sample/query",
        json_body={"question": "该客户资金情况如何？", "file_name": file_name},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "DENIED"
    assert payload["reason"] == "ACCESS_DENIED"
    assert payload["llm_invoked"] is False


def test_unknown_file_name_rejected(
    demo_identities, monkeypatch
) -> None:
    repository = InMemoryControlPlaneRepository()
    _seed_all_assets(repository)
    _grant_query(repository, actor_id=ACTOR_A)
    app = _build_app(repository, monkeypatch, demo_identities)
    client = AsgiClient(app)
    _login(client, "alice", "demo-a-password")

    response = client.post(
        "/api/controlled-sample/query",
        json_body={"question": "x", "file_name": "not-a-controlled-file.docx"},
    )

    assert response.status_code == 422


def test_carol_no_grant_denied(
    demo_identities, monkeypatch
) -> None:
    repository = InMemoryControlPlaneRepository()
    _seed_all_assets(repository)
    # no grant for carol
    app = _build_app(repository, monkeypatch, demo_identities)
    client = AsgiClient(app)
    _login(client, "carol", "demo-c-password")

    file_name = _first_file_name()
    response = client.post(
        "/api/controlled-sample/query",
        json_body={"question": "x", "file_name": file_name},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "DENIED"
