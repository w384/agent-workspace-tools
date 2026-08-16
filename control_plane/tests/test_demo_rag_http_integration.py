from pathlib import Path

import httpx

from control_plane.app.demo_rag import DemoRagPort

from conftest import RecordingHttpxClient, llm_environment
from control_plane.app.domain import (
    Action,
    GrantEffect,
    PermissionGrant,
    PrincipalType,
)
from service.app.rag.contracts import ActiveAssetVersion
from service.app.rag.demo_document_parser import DemoDocumentParser
from service.app.rag.ingestion import IngestionRequest
from service.app.rag.index import InMemorySearchIndex
from service.app.rag.llm import build_llm_answer_generator


DEMO_SOURCE = (
    Path(__file__).parents[2]
    / "work"
    / "demo"
    / "public-drive-ai-organizing"
    / "source"
)
PDF_PATH = "验收交付/2026春季新品项目验收清单.pdf"
PDF_MIME_TYPE = "application/pdf"


def _patch_httpx_client(monkeypatch):
    RecordingHttpxClient.requests = []
    monkeypatch.setattr(httpx, "Client", RecordingHttpxClient)


def test_bff_query_returns_real_parsed_pdf_citation_for_authenticated_a(
    client_as_a, repository, demo_identities, file_executor, monkeypatch
):
    asset = repository.get_or_create_asset(
        "workspace-a", PDF_PATH, "2026春季新品项目验收清单.pdf", "user-a"
    )
    version = repository.create_asset_version(
        asset.asset_id, "sha256:" + "a" * 64, PDF_PATH
    )
    for state in ("parsing", "indexed", "ready"):
        repository.transition_asset_version(version.asset_version_id, state)
    repository.activate_asset_version(version.asset_version_id)
    repository.add_permission_grant(
        PermissionGrant(
            grant_id="a-query-acceptance",
            workspace_id="workspace-a",
            context_version="acl_2026_08_13",
            principal_type=PrincipalType.USER,
            principal_id="user-a",
            action=Action.QUERY,
            path_prefix="验收交付",
        )
    )
    parser = DemoDocumentParser(DEMO_SOURCE)
    index = InMemorySearchIndex(scorer=lambda _question, _chunk: 0.95)
    index.replace_version(
        tenant_id="workspace-a",
        active_version=ActiveAssetVersion(asset.asset_id, version.asset_version_id),
        chunks=parser.parse(
            IngestionRequest(
                tenant_id="workspace-a",
                target_version=ActiveAssetVersion(
                    asset.asset_id, version.asset_version_id
                ),
                source_ref=PDF_PATH,
                content_fingerprint=version.content_fingerprint,
                mime_type=PDF_MIME_TYPE,
                size_bytes=(DEMO_SOURCE / PDF_PATH).stat().st_size,
            )
        ),
    )
    from control_plane.app.main import create_app
    from conftest import AsgiClient

    _patch_httpx_client(monkeypatch)
    rag_port = DemoRagPort(
        repository=repository,
        search_index=index,
        answer_generator=build_llm_answer_generator(llm_environment()),
    )
    app = create_app(
        repository=repository,
        file_executor=file_executor,
        rag_port=rag_port,
        demo_identities=demo_identities,
        internal_service_key="demo-internal-key",
        approver_role_id="role-approver-demo",
    )
    client = AsgiClient(app)
    login = client.post(
        "/api/session/login",
        json_body={"username": "alice", "password": "demo-a-password"},
    )
    assert login.status_code == 200

    response = client.post(
        "/api/retrieval/query",
        json_body={
            "question": "项目验收要求是什么？",
            "asset_id": asset.asset_id,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ANSWERED"
    assert payload["answer"] == "LLM 依据授权证据生成的回答"
    assert payload["llm_invoked"] is True
    assert len(RecordingHttpxClient.requests) == 1
    assert payload["citations"] == [
        {
            "asset_id": asset.asset_id,
            "asset_version_id": version.asset_version_id,
            "chunk_id": f"{version.asset_version_id}:0",
            "page_number": 1,
            "paragraph_index": None,
            "display_path": PDF_PATH,
            "path_kind": "CURRENT",
            "current_path": PDF_PATH,
            "version_path": PDF_PATH,
        }
    ]


def test_bff_query_denies_a_before_scoring_and_allows_b_explicit_a_b_scope(
    repository, demo_identities, file_executor, monkeypatch
):
    acceptance_asset, acceptance_version = _add_ready_asset(
        repository, path=PDF_PATH, created_by="user-a"
    )
    legal_asset, legal_version = _add_ready_asset(
        repository, path=LEGAL_PATH, created_by="user-b"
    )
    for grant_id, principal_id, path_prefix, effect in (
        ("a-allow-acceptance", "user-a", "验收交付", GrantEffect.ALLOW),
        ("a-deny-legal", "user-a", "版权授权证明", GrantEffect.DENY),
        ("b-allow-acceptance", "user-b", "验收交付", GrantEffect.ALLOW),
        ("b-allow-legal", "user-b", "版权授权证明", GrantEffect.ALLOW),
    ):
        repository.add_permission_grant(
            PermissionGrant(
                grant_id=grant_id,
                workspace_id="workspace-a",
                context_version="acl_2026_08_13",
                principal_type=PrincipalType.USER,
                principal_id=principal_id,
                action=Action.QUERY,
                path_prefix=path_prefix,
                effect=effect,
            )
        )
    parser = DemoDocumentParser(DEMO_SOURCE)
    scored_chunk_ids: list[str] = []

    def score(_question, chunk):
        scored_chunk_ids.append(chunk.chunk_id)
        return 0.95

    index = InMemorySearchIndex(scorer=score)
    _index_demo_source(
        index,
        parser,
        asset_id=acceptance_asset.asset_id,
        version_id=acceptance_version.asset_version_id,
        source_ref=PDF_PATH,
        mime_type=PDF_MIME_TYPE,
    )
    _index_demo_source(
        index,
        parser,
        asset_id=legal_asset.asset_id,
        version_id=legal_version.asset_version_id,
        source_ref=LEGAL_PATH,
        mime_type=DOCX_MIME_TYPE,
    )
    from control_plane.app.main import create_app
    from conftest import AsgiClient

    _patch_httpx_client(monkeypatch)
    rag_port = DemoRagPort(
        repository=repository,
        search_index=index,
        answer_generator=build_llm_answer_generator(llm_environment()),
    )
    app = create_app(
        repository=repository,
        file_executor=file_executor,
        rag_port=rag_port,
        demo_identities=demo_identities,
        internal_service_key="demo-internal-key",
        approver_role_id="role-approver-demo",
    )
    a_client = _login(AsgiClient(app), username="alice", password="demo-a-password")
    denied = a_client.post(
        "/api/retrieval/query",
        json_body={
            "question": "内部法务评审意见有哪些版权风险？",
            "asset_id": legal_asset.asset_id,
        },
    )

    assert denied.status_code == 200
    assert denied.json()["status"] == "DENIED"
    assert denied.json()["retrieved_count"] == 0
    assert denied.json()["llm_invoked"] is False
    assert denied.json()["citations"] == []
    assert scored_chunk_ids == []
    assert rag_port.audit_events[-1].authorized_candidate_count == 0
    assert RecordingHttpxClient.requests == []

    b_client = _login(AsgiClient(app), username="bob", password="demo-b-password")
    b_legal = b_client.post(
        "/api/retrieval/query",
        json_body={
            "question": "内部法务评审意见有哪些版权风险？",
            "asset_id": legal_asset.asset_id,
        },
    )

    assert b_legal.status_code == 200
    assert b_legal.json()["status"] == "ANSWERED"
    assert b_legal.json()["llm_invoked"] is True
    assert b_legal.json()["answer"] == "LLM 依据授权证据生成的回答"
    assert len(RecordingHttpxClient.requests) == 1
    assert {citation["current_path"] for citation in b_legal.json()["citations"]} == {
        LEGAL_PATH
    }

    b_acceptance = b_client.post(
        "/api/retrieval/query",
        json_body={
            "question": "项目验收要求是什么？",
            "asset_id": acceptance_asset.asset_id,
        },
    )

    assert b_acceptance.status_code == 200
    assert b_acceptance.json()["status"] == "ANSWERED"
    assert len(RecordingHttpxClient.requests) == 2
    assert {citation["current_path"] for citation in b_acceptance.json()["citations"]} == {
        PDF_PATH
    }


LEGAL_PATH = "版权授权证明/内部法务评审意见.docx"
DOCX_MIME_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


def _add_ready_asset(repository, *, path: str, created_by: str):
    asset = repository.get_or_create_asset(
        "workspace-a", path, path.rsplit("/", maxsplit=1)[-1], created_by
    )
    version = repository.create_asset_version(
        asset.asset_id, "sha256:" + "a" * 64, path
    )
    for state in ("parsing", "indexed", "ready"):
        repository.transition_asset_version(version.asset_version_id, state)
    repository.activate_asset_version(version.asset_version_id)
    return repository.get_asset(asset.asset_id), repository.get_asset_version(
        version.asset_version_id
    )


def _index_demo_source(
    index, parser, *, asset_id: str, version_id: str, source_ref: str, mime_type: str
):
    index.replace_version(
        tenant_id="workspace-a",
        active_version=ActiveAssetVersion(asset_id, version_id),
        chunks=parser.parse(
            IngestionRequest(
                tenant_id="workspace-a",
                target_version=ActiveAssetVersion(asset_id, version_id),
                source_ref=source_ref,
                content_fingerprint="sha256:" + "a" * 64,
                mime_type=mime_type,
                size_bytes=(DEMO_SOURCE / source_ref).stat().st_size,
            )
        ),
    )


def _login(client, *, username: str, password: str):
    response = client.post(
        "/api/session/login",
        json_body={"username": username, "password": password},
    )
    assert response.status_code == 200
    return client


def test_bff_query_never_leaks_env_llm_credentials_in_response_or_audit(
    repository, demo_identities, file_executor, monkeypatch
):
    from control_plane.app.main import create_app
    from conftest import AsgiClient

    acceptance_asset, acceptance_version = _add_ready_asset(
        repository, path=PDF_PATH, created_by="user-a"
    )
    repository.add_permission_grant(
        PermissionGrant(
            grant_id="a-query-llm-credential",
            workspace_id="workspace-a",
            context_version="acl_2026_08_13",
            principal_type=PrincipalType.USER,
            principal_id="user-a",
            action=Action.QUERY,
            path_prefix="验收交付",
        )
    )
    parser = DemoDocumentParser(DEMO_SOURCE)
    index = InMemorySearchIndex(scorer=lambda _question, _chunk: 0.95)
    _index_demo_source(
        index,
        parser,
        asset_id=acceptance_asset.asset_id,
        version_id=acceptance_version.asset_version_id,
        source_ref=PDF_PATH,
        mime_type=PDF_MIME_TYPE,
    )

    _patch_httpx_client(monkeypatch)
    monkeypatch.setenv("RAG_LLM_BASE_URL", "https://llm.example.test/v1")
    monkeypatch.setenv("RAG_LLM_API_KEY", "llm-super-secret-key")
    monkeypatch.setenv("RAG_LLM_MODEL", "demo-llm-model")
    rag_port = DemoRagPort(repository=repository, search_index=index)
    app = create_app(
        repository=repository,
        file_executor=file_executor,
        rag_port=rag_port,
        demo_identities=demo_identities,
        internal_service_key="demo-internal-key",
        approver_role_id="role-approver-demo",
    )
    client = _login(AsgiClient(app), username="alice", password="demo-a-password")

    response = client.post(
        "/api/retrieval/query",
        json_body={
            "question": "项目验收要求是什么？",
            "asset_id": acceptance_asset.asset_id,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ANSWERED"
    assert payload["answer"] == "LLM 依据授权证据生成的回答"
    assert payload["llm_invoked"] is True
    serialized = str(payload)
    assert "llm-super-secret-key" not in serialized
    assert "llm.example.test" not in serialized
    assert "demo-llm-model" not in serialized
    assert "llm-super-secret-key" not in repr(rag_port.audit_events)
    assert "llm-super-secret-key" not in repr(repository.list_audit_events())
    authorization = RecordingHttpxClient.requests[-1]["headers"].get(
        "Authorization", ""
    )
    assert authorization == "Bearer llm-super-secret-key"