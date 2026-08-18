"""LLM provider switching: local (Ollama) vs cloud (DeepSeek).

Covers the BFF provider endpoints:
  1. GET /api/llm/provider returns the current provider and non-secret
     descriptors (id/label only; never base_url/api_key/model).
  2. POST /api/llm/provider switches local -> cloud and back.
  3. Unknown provider ids are rejected with 422.
  4. Credentials never leak into the BFF response (no key/base_url/model).
  5. After a switch the path-B query still runs through the new answer
     generator (real LLM call, one request).
"""

import hashlib
import json
from pathlib import Path

import httpx

from conftest import RecordingHttpxClient
from control_plane.app.domain import (
    Action,
    PermissionGrant,
    PrincipalType,
)
from control_plane.app.repository import InMemoryControlPlaneRepository


PROJECT_ROOT = Path(__file__).parents[2]
DEMO_ROOT = PROJECT_ROOT / "work" / "demo" / "financial-preassessment"
SOURCE_ROOT = DEMO_ROOT / "source"
IMPORT_MANIFEST_PATH = DEMO_ROOT / "import-manifest.json"
RULES_PATH = DEMO_ROOT / "rules" / "demo-bank-rules-v1.json"
WORKSPACE_ID = "workspace-a"
ACTOR_A = "user-a"
CONTEXT_VERSION = "acl_2026_08_13"


def _manifest() -> dict[str, object]:
    return json.loads(IMPORT_MANIFEST_PATH.read_text(encoding="utf-8"))


def _add_ready_asset(
    repository: InMemoryControlPlaneRepository,
    relative_path: str,
    *,
    created_by: str,
):
    source_path = SOURCE_ROOT / relative_path
    asset = repository.get_or_create_asset(
        WORKSPACE_ID, relative_path, source_path.name, created_by
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
    repository: InMemoryControlPlaneRepository, *, actor_id: str
) -> None:
    repository.add_permission_grant(
        PermissionGrant(
            grant_id=f"grant-{actor_id}",
            workspace_id=WORKSPACE_ID,
            context_version=CONTEXT_VERSION,
            principal_type=PrincipalType.USER,
            principal_id=actor_id,
            action=Action.QUERY,
            path_prefix="客户模拟资料",
        )
    )


def _demo_environment() -> dict[str, str]:
    return {
        "RAG_LLM_LOCAL_BASE_URL": "http://localhost:11434/v1",
        "RAG_LLM_LOCAL_MODEL": "qwen3.5:9b",
        "RAG_LLM_BASE_URL": "https://api.deepseek.com/v1",
        "RAG_LLM_MODEL": "deepseek-chat",
        "RAG_LLM_API_KEY": "test-cloud-key",
    }


def _patch_httpx_client(monkeypatch) -> None:
    RecordingHttpxClient.requests = []
    monkeypatch.setattr(httpx, "Client", RecordingHttpxClient)


def _build_app(file_executor, demo_identities, monkeypatch):
    """Build the demo app with a provider-switchable composite port."""
    from control_plane.app.finance_demo_llm_rag import FinanceDemoLlmRagPort
    from control_plane.app.llm_providers import LLMProviderRegistry
    from control_plane.app.main import create_app

    manifest = _manifest()
    repository = InMemoryControlPlaneRepository()
    version = _add_ready_asset(
        repository, manifest["assets"][0]["relative_path"], created_by=ACTOR_A
    )
    _grant_query(repository, actor_id=ACTOR_A)
    _patch_httpx_client(monkeypatch)

    registry = LLMProviderRegistry(environment=_demo_environment())
    port = FinanceDemoLlmRagPort(
        repository=repository,
        source_root=SOURCE_ROOT,
        import_manifest_path=IMPORT_MANIFEST_PATH,
        rules_path=RULES_PATH,
        workspace_id=WORKSPACE_ID,
        providers=registry,
    )
    app = create_app(
        llm_providers=registry,
        repository=repository,
        file_executor=file_executor,
        rag_port=port,
        demo_identities=demo_identities,
        internal_service_key="demo-internal-key",
        approver_role_id="role-approver-demo",
        demo_rules_fixture_path=RULES_PATH,
    )
    return app, registry, port, version


def test_provider_default_is_local(
    file_executor, demo_identities, monkeypatch
) -> None:
    from conftest import AsgiClient

    app, registry, _port, _version = _build_app(
        file_executor, demo_identities, monkeypatch
    )
    client = AsgiClient(app)
    client.post(
        "/api/session/login",
        json_body={"username": "alice", "password": "demo-a-password"},
    )

    response = client.get("/api/llm/provider")

    assert response.status_code == 200
    payload = response.json()
    assert payload["current"] == "local"
    ids = [item["id"] for item in payload["providers"]]
    assert ids == ["local", "cloud"]


def test_provider_response_never_leaks_credentials(
    file_executor, demo_identities, monkeypatch
) -> None:
    from conftest import AsgiClient

    app, _registry, _port, _version = _build_app(
        file_executor, demo_identities, monkeypatch
    )
    client = AsgiClient(app)
    client.post(
        "/api/session/login",
        json_body={"username": "alice", "password": "demo-a-password"},
    )

    response = client.get("/api/llm/provider")
    raw = response.content.decode("utf-8")

    assert "test-cloud-key" not in raw
    assert "api.deepseek.com" not in raw
    assert "localhost:11434" not in raw
    assert response.json()["providers"] == [
        {"id": "local", "label": "本地模型（Ollama qwen3.5:9b）"},
        {"id": "cloud", "label": "联网模型（DeepSeek）"},
    ]


def test_provider_switch_local_to_cloud_and_back(
    file_executor, demo_identities, monkeypatch
) -> None:
    from conftest import AsgiClient

    app, registry, _port, _version = _build_app(
        file_executor, demo_identities, monkeypatch
    )
    client = AsgiClient(app)
    client.post(
        "/api/session/login",
        json_body={"username": "alice", "password": "demo-a-password"},
    )

    response = client.post(
        "/api/llm/provider", json_body={"provider": "cloud"}
    )
    assert response.status_code == 200
    assert response.json()["current"] == "cloud"
    assert registry.current == "cloud"

    response = client.post(
        "/api/llm/provider", json_body={"provider": "local"}
    )
    assert response.status_code == 200
    assert response.json()["current"] == "local"
    assert registry.current == "local"


def test_provider_unknown_rejected(
    file_executor, demo_identities, monkeypatch
) -> None:
    from conftest import AsgiClient

    app, registry, _port, _version = _build_app(
        file_executor, demo_identities, monkeypatch
    )
    client = AsgiClient(app)
    client.post(
        "/api/session/login",
        json_body={"username": "alice", "password": "demo-a-password"},
    )

    response = client.post(
        "/api/llm/provider", json_body={"provider": "anthropic"}
    )

    assert response.status_code == 422
    assert registry.current == "local"


def test_query_runs_after_switch_to_cloud(
    file_executor, demo_identities, monkeypatch
) -> None:
    from conftest import AsgiClient

    app, registry, _port, version = _build_app(
        file_executor, demo_identities, monkeypatch
    )
    client = AsgiClient(app)
    client.post(
        "/api/session/login",
        json_body={"username": "alice", "password": "demo-a-password"},
    )

    switch = client.post(
        "/api/llm/provider", json_body={"provider": "cloud"}
    )
    assert switch.status_code == 200

    RecordingHttpxClient.requests = []
    response = client.post(
        "/api/retrieval/query",
        json_body={"question": "该客户资金情况如何？", "asset_id": version.asset_id},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ANSWERED"
    assert payload["llm_invoked"] is True
    assert len(RecordingHttpxClient.requests) == 1
    raw = json.dumps(payload, ensure_ascii=False)
    assert "test-cloud-key" not in raw
    assert "api.deepseek.com" not in raw
