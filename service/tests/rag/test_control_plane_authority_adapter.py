import importlib

import pytest

from control_plane.app.domain import (
    Action,
    GrantEffect,
    PermissionGrant,
    PrincipalType,
    TrustedActorContext,
)
from control_plane.app.repository import InMemoryControlPlaneRepository


def _load_modules():
    contracts = importlib.import_module("service.app.rag.contracts")
    index = importlib.import_module("service.app.rag.index")
    retrieval = importlib.import_module("service.app.rag.retrieval")
    adapter = importlib.import_module(
        "service.app.rag.control_plane_adapter"
    )
    return contracts, index, retrieval, adapter


def _actor() -> TrustedActorContext:
    return TrustedActorContext(
        actor_id="user-a",
        workspace_id="workspace-a",
        context_version="acl-v1",
        session_id="session-a",
        request_id="request-a",
        run_id="run-a",
        role_ids=frozenset({"role-member"}),
        group_ids=frozenset({"group-finance"}),
    )


def _ready_asset(
    repository: InMemoryControlPlaneRepository,
    *,
    path: str,
) -> tuple[object, object]:
    asset = repository.get_or_create_asset(
        "workspace-a", path, path.rsplit("/", maxsplit=1)[-1], "user-a"
    )
    version = repository.create_asset_version(
        asset.asset_id, "sha256:" + "a" * 64, path
    )
    repository.transition_asset_version(version.asset_version_id, "parsing")
    repository.transition_asset_version(version.asset_version_id, "indexed")
    repository.transition_asset_version(version.asset_version_id, "ready")
    repository.activate_asset_version(version.asset_version_id)
    return repository.get_asset(asset.asset_id), repository.get_asset_version(
        version.asset_version_id
    )


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
        return "allowed answer"


class _AuditSink:
    def __init__(self) -> None:
        self.events = []

    def record(self, event) -> None:
        self.events.append(event)


def test_control_plane_acl_scope_excludes_denied_asset_before_scoring_and_llm():
    contracts, index, retrieval, adapter = _load_modules()
    repository = InMemoryControlPlaneRepository()
    allowed_asset, allowed_version = _ready_asset(
        repository, path="organized/allowed.pdf"
    )
    denied_asset, denied_version = _ready_asset(
        repository, path="restricted/secret.pdf"
    )
    repository.add_permission_grant(
        PermissionGrant(
            grant_id="allow-organized-query",
            workspace_id="workspace-a",
            context_version="acl-v1",
            principal_type=PrincipalType.USER,
            principal_id="user-a",
            action=Action.QUERY,
            path_prefix="organized",
        )
    )
    repository.add_permission_grant(
        PermissionGrant(
            grant_id="deny-restricted-query",
            workspace_id="workspace-a",
            context_version="acl-v1",
            principal_type=PrincipalType.USER,
            principal_id="user-a",
            action=Action.QUERY,
            path_prefix="restricted",
            effect=GrantEffect.DENY,
        )
    )
    scored_chunk_ids = []

    def score(_question, chunk):
        scored_chunk_ids.append(chunk.chunk_id)
        return 0.9

    search_index = index.InMemorySearchIndex(scorer=score)
    search_index.rebuild(
        (
            contracts.Chunk(
                tenant_id="workspace-a",
                asset_id=allowed_asset.asset_id,
                asset_version_id=allowed_version.asset_version_id,
                chunk_id="allowed-chunk",
                ordinal=0,
                text="allowed evidence",
                page_number=1,
                paragraph_index=None,
                parser_version="parser-v1",
                embedding_version="embedding-v1",
                index_version="index-v1",
            ),
            contracts.Chunk(
                tenant_id="workspace-a",
                asset_id=denied_asset.asset_id,
                asset_version_id=denied_version.asset_version_id,
                chunk_id="DENIED-CHUNK-SENTINEL",
                ordinal=0,
                text="DENIED-TEXT-SENTINEL",
                page_number=9,
                paragraph_index=None,
                parser_version="parser-v1",
                embedding_version="embedding-v1",
                index_version="index-v1",
            ),
        )
    )
    reranker = _Reranker()
    generator = _Generator()
    audit_sink = _AuditSink()
    service = retrieval.RetrievalService(
        control_plane=adapter.ControlPlaneRetrievalAdapter(
            repository=repository, actor=_actor()
        ),
        search_index=search_index,
        reranker=reranker,
        answer_generator=generator,
        audit_sink=audit_sink,
        minimum_evidence_score=0.75,
    )

    result = service.answer(
        context=contracts.PermissionContext(
            tenant_id="workspace-a",
            principal_id="user-a",
            group_ids=("group-finance",),
            session_id="session-a",
            request_id="request-a",
        ),
        question="show permitted evidence",
    )

    assert result.status is contracts.AnswerStatus.ANSWERED
    assert scored_chunk_ids == ["allowed-chunk"]
    assert [hit.chunk.chunk_id for hit in reranker.seen] == ["allowed-chunk"]
    assert [hit.chunk.chunk_id for hit in generator.seen] == ["allowed-chunk"]
    assert [citation.chunk_id for citation in result.citations] == ["allowed-chunk"]
    assert "DENIED-CHUNK-SENTINEL" not in repr(
        (reranker.seen, generator.seen, audit_sink.events, result)
    )
    assert "DENIED-TEXT-SENTINEL" not in repr(
        (reranker.seen, generator.seen, audit_sink.events, result)
    )


def test_untrusted_permission_context_fails_closed_before_search():
    contracts, index, retrieval, adapter = _load_modules()
    repository = InMemoryControlPlaneRepository()
    asset, version = _ready_asset(repository, path="organized/allowed.pdf")
    repository.add_permission_grant(
        PermissionGrant(
            grant_id="allow-organized-query",
            workspace_id="workspace-a",
            context_version="acl-v1",
            principal_type=PrincipalType.USER,
            principal_id="user-a",
            action=Action.QUERY,
            path_prefix="organized",
        )
    )
    search_index = index.InMemorySearchIndex(scorer=lambda _q, _c: 1.0)
    search_index.rebuild(
        (
            contracts.Chunk(
                tenant_id="workspace-a",
                asset_id=asset.asset_id,
                asset_version_id=version.asset_version_id,
                chunk_id="must-not-score",
                ordinal=0,
                text="must not reach search",
                page_number=None,
                paragraph_index=1,
                parser_version="parser-v1",
                embedding_version="embedding-v1",
                index_version="index-v1",
            ),
        )
    )
    service = retrieval.RetrievalService(
        control_plane=adapter.ControlPlaneRetrievalAdapter(
            repository=repository, actor=_actor()
        ),
        search_index=search_index,
        reranker=_Reranker(),
        answer_generator=_Generator(),
        audit_sink=_AuditSink(),
        minimum_evidence_score=0.75,
    )

    with pytest.raises(PermissionError, match="untrusted retrieval context"):
        service.answer(
            context=contracts.PermissionContext(
                tenant_id="workspace-a",
                principal_id="forged-user",
                group_ids=("group-finance",),
                session_id="session-a",
                request_id="request-a",
            ),
            question="must fail before retrieval",
        )
