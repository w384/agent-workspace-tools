from pathlib import Path

from control_plane.app.domain import (
    Action,
    GrantEffect,
    PermissionGrant,
    PrincipalType,
    TrustedActorContext,
)
from control_plane.app.repository import InMemoryControlPlaneRepository

from service.app.rag.control_plane_adapter import ControlPlaneRetrievalAdapter
from service.app.rag.contracts import ActiveAssetVersion, PermissionContext
from service.app.rag.demo_document_parser import DemoDocumentParser
from service.app.rag.index import InMemorySearchIndex
from service.app.rag.ingestion import IngestionRequest
from service.app.rag.retrieval import RetrievalService


DEMO_SOURCE = (
    Path(__file__).parents[3]
    / "work"
    / "demo"
    / "financial-preassessment"
    / "source"
)
PDF_MIME_TYPE = "application/pdf"
DOCX_MIME_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


class _Reranker:
    def __init__(self) -> None:
        self.seen = ()

    def rerank(self, *, hits, **_kwargs):
        self.seen = tuple(hits)
        return tuple(hits)


class _Generator:
    def __init__(self) -> None:
        self.seen = ()

    def generate(self, *, evidence, **_kwargs):
        self.seen = tuple(evidence)
        return evidence[0].chunk.text


class _AuditSink:
    def __init__(self) -> None:
        self.events = []

    def record(self, event) -> None:
        self.events.append(event)


def _actor(actor_id: str, groups: frozenset[str]) -> TrustedActorContext:
    return TrustedActorContext(
        actor_id=actor_id,
        workspace_id="workspace-demo",
        context_version="acl-demo-v1",
        session_id=f"session-{actor_id}",
        request_id=f"request-{actor_id}",
        run_id=f"run-{actor_id}",
        role_ids=frozenset({f"role-{actor_id}"}),
        group_ids=groups,
    )


def _add_ready_asset(
    repository: InMemoryControlPlaneRepository,
    *,
    path: str,
) -> tuple[object, object]:
    asset = repository.get_or_create_asset(
        "workspace-demo", path, path.rsplit("/", maxsplit=1)[-1], "user-a"
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


def _grant(
    repository: InMemoryControlPlaneRepository,
    *,
    grant_id: str,
    principal_id: str,
    path_prefix: str,
    effect: GrantEffect = GrantEffect.ALLOW,
) -> None:
    repository.add_permission_grant(
        PermissionGrant(
            grant_id=grant_id,
            workspace_id="workspace-demo",
            context_version="acl-demo-v1",
            principal_type=PrincipalType.USER,
            principal_id=principal_id,
            action=Action.QUERY,
            path_prefix=path_prefix,
            effect=effect,
        )
    )


def _ingest(
    parser: DemoDocumentParser,
    *,
    asset_id: str,
    asset_version_id: str,
    source_ref: str,
    mime_type: str,
):
    return parser.parse(
        IngestionRequest(
            tenant_id="workspace-demo",
            target_version=ActiveAssetVersion(asset_id, asset_version_id),
            source_ref=source_ref,
            content_fingerprint="sha256:" + "a" * 64,
            mime_type=mime_type,
            size_bytes=(DEMO_SOURCE / source_ref).stat().st_size,
        )
    )


def test_demo_rag_pipeline_answers_authorized_pdf_with_versioned_citation():
    repository = InMemoryControlPlaneRepository()
    asset, version = _add_ready_asset(
        repository, path="客户模拟资料/收入情况说明.pdf"
    )
    _grant(
        repository,
        grant_id="a-income",
        principal_id="user-a",
        path_prefix="客户模拟资料",
    )
    parser = DemoDocumentParser(DEMO_SOURCE)
    index = InMemorySearchIndex(scorer=lambda _question, _chunk: 0.95)
    index.replace_version(
        tenant_id="workspace-demo",
        active_version=ActiveAssetVersion(asset.asset_id, version.asset_version_id),
        chunks=_ingest(
            parser,
            asset_id=asset.asset_id,
            asset_version_id=version.asset_version_id,
            source_ref="客户模拟资料/收入情况说明.pdf",
            mime_type=PDF_MIME_TYPE,
        ),
    )
    actor = _actor("user-a", frozenset())
    reranker = _Reranker()
    generator = _Generator()
    audit_sink = _AuditSink()
    result = RetrievalService(
        control_plane=ControlPlaneRetrievalAdapter(repository=repository, actor=actor),
        search_index=index,
        reranker=reranker,
        answer_generator=generator,
        audit_sink=audit_sink,
        minimum_evidence_score=0.75,
    ).answer(
        context=PermissionContext(
            tenant_id="workspace-demo",
            principal_id="user-a",
            group_ids=(),
            session_id="session-user-a",
            request_id="request-user-a",
        ),
        question="2024年度营业收入是多少？",
    )

    assert "4,860万元" in result.answer
    assert "营业收入" in result.answer
    assert result.citations[0].asset_version_id == version.asset_version_id
    assert result.citations[0].page_number == 1
    assert result.citations[0].current_path == "客户模拟资料/收入情况说明.pdf"
    assert result.citations[0].version_path == "客户模拟资料/收入情况说明.pdf"
    assert len(reranker.seen) == len(generator.seen) == 1


def test_demo_rag_pipeline_denies_sensitive_docx_before_scoring():
    repository = InMemoryControlPlaneRepository()
    asset, version = _add_ready_asset(
        repository, path="敏感资料/内部资料核验说明.docx"
    )
    _grant(
        repository,
        grant_id="a-deny-sensitive",
        principal_id="user-a",
        path_prefix="敏感资料",
        effect=GrantEffect.DENY,
    )
    parser = DemoDocumentParser(DEMO_SOURCE)
    scored_chunk_ids = []

    def score(_question, chunk):
        scored_chunk_ids.append(chunk.chunk_id)
        return 0.95

    index = InMemorySearchIndex(scorer=score)
    index.replace_version(
        tenant_id="workspace-demo",
        active_version=ActiveAssetVersion(asset.asset_id, version.asset_version_id),
        chunks=_ingest(
            parser,
            asset_id=asset.asset_id,
            asset_version_id=version.asset_version_id,
            source_ref="敏感资料/内部资料核验说明.docx",
            mime_type=DOCX_MIME_TYPE,
        ),
    )
    actor = _actor("user-a", frozenset())
    reranker = _Reranker()
    generator = _Generator()
    audit_sink = _AuditSink()
    result = RetrievalService(
        control_plane=ControlPlaneRetrievalAdapter(repository=repository, actor=actor),
        search_index=index,
        reranker=reranker,
        answer_generator=generator,
        audit_sink=audit_sink,
        minimum_evidence_score=0.75,
    ).answer(
        context=PermissionContext(
            tenant_id="workspace-demo",
            principal_id="user-a",
            group_ids=(),
            session_id="session-user-a",
            request_id="request-user-a",
        ),
        question="内部资料核验说明有什么内容？",
    )

    assert result.status.value == "DENIED"
    assert result.retrieved_count == 0
    assert result.llm_invoked is False
    assert result.citations == ()
    assert scored_chunk_ids == []
    assert reranker.seen == ()
    assert generator.seen == ()
    assert "普通成员不应查询" not in repr((audit_sink.events, result))
