import pytest

from service.app.rag.contracts import (
    ActiveAssetVersion,
    AnswerStatus,
    AssetReference,
    Chunk,
    PermissionContext,
    RetrievalScope,
    SearchHit,
)
from service.app.rag.retrieval import RetrievalService


TENANT_ID = "tenant-demo"
ALLOWED_VERSION = ActiveAssetVersion(
    asset_id="asset-allowed",
    asset_version_id="version-allowed-v1",
)
DENIED_VERSION = ActiveAssetVersion(
    asset_id="asset-denied",
    asset_version_id="version-denied-v1",
)


def _chunk(
    *,
    tenant_id: str = TENANT_ID,
    active_version: ActiveAssetVersion = ALLOWED_VERSION,
    chunk_id: str = "chunk-allowed",
    text: str = "authorized evidence",
) -> Chunk:
    return Chunk(
        tenant_id=tenant_id,
        asset_id=active_version.asset_id,
        asset_version_id=active_version.asset_version_id,
        chunk_id=chunk_id,
        ordinal=0,
        text=text,
        page_number=1,
        paragraph_index=None,
        parser_version="parser-v1",
        embedding_version="embedding-v1",
        index_version="index-v1",
    )


def _context(request_id: str) -> PermissionContext:
    return PermissionContext(
        tenant_id=TENANT_ID,
        principal_id="principal-demo",
        group_ids=("group-demo",),
        session_id="authenticated-session",
        request_id=request_id,
    )


class _ControlPlane:
    def __init__(self) -> None:
        self.reference_calls = 0

    def resolve_retrieval_scope(self, _context):
        return RetrievalScope(
            tenant_id=TENANT_ID,
            allowed_active_versions=(
                ALLOWED_VERSION,
                DENIED_VERSION,
            ),
            denied_asset_ids=frozenset(
                {DENIED_VERSION.asset_id}
            ),
        )

    def get_asset_reference(self, **_kwargs):
        self.reference_calls += 1
        return AssetReference(
            asset_id="asset-denied",
            asset_version_id="version-denied-v1",
            current_path="DENIED-PATH-SENTINEL",
            version_path="DENIED-PATH-SENTINEL",
        )


class _Reranker:
    def __init__(self, returned_hits=()) -> None:
        self.call_count = 0
        self.received_hits = ()
        self.returned_hits = tuple(returned_hits)

    def rerank(self, *, hits, **_kwargs):
        self.call_count += 1
        self.received_hits = tuple(hits)
        return self.returned_hits or tuple(hits)


class _AnswerGenerator:
    def __init__(self) -> None:
        self.call_count = 0

    def generate(self, **_kwargs):
        self.call_count += 1
        return "DENIED-TEXT-SENTINEL"


class _AuditSink:
    def __init__(self) -> None:
        self.events = []

    def record(self, event):
        self.events.append(event)


def _assert_safe_scope_violation(
    *,
    result,
    audit_sink: _AuditSink,
) -> None:
    assert result.status is AnswerStatus.DENIED
    assert result.reason == "retrieval_scope_violation"
    assert result.retrieved_count == 0
    assert result.llm_invoked is False
    assert result.citations == ()
    assert result.answer is None
    assert len(audit_sink.events) == 1
    event = audit_sink.events[0]
    assert event.status is AnswerStatus.DENIED
    assert event.authorized_candidate_count == 0
    assert event.evidence_count == 0

    safe_output = repr((result, audit_sink.events))
    assert "DENIED-CHUNK-SENTINEL" not in safe_output
    assert "DENIED-TEXT-SENTINEL" not in safe_output
    assert "DENIED-PATH-SENTINEL" not in safe_output


@pytest.mark.parametrize(
    "invalid_chunk",
    [
        _chunk(
            tenant_id="tenant-other",
            chunk_id="DENIED-CHUNK-SENTINEL",
            text="DENIED-TEXT-SENTINEL",
        ),
        _chunk(
            active_version=ActiveAssetVersion(
                asset_id=ALLOWED_VERSION.asset_id,
                asset_version_id="version-not-active",
            ),
            chunk_id="DENIED-CHUNK-SENTINEL",
            text="DENIED-TEXT-SENTINEL",
        ),
        _chunk(
            active_version=DENIED_VERSION,
            chunk_id="DENIED-CHUNK-SENTINEL",
            text="DENIED-TEXT-SENTINEL",
        ),
    ],
    ids=("cross-tenant", "inactive-pair", "explicit-deny"),
)
def test_search_index_scope_violation_fails_closed_before_reranker(
    invalid_chunk,
):
    control_plane = _ControlPlane()

    class ViolatingSearchIndex:
        def __init__(self) -> None:
            self.call_count = 0

        def search(self, **_kwargs):
            self.call_count += 1
            return (SearchHit(chunk=invalid_chunk, score=0.99),)

    search_index = ViolatingSearchIndex()
    reranker = _Reranker()
    answer_generator = _AnswerGenerator()
    audit_sink = _AuditSink()
    result = RetrievalService(
        control_plane=control_plane,
        search_index=search_index,
        reranker=reranker,
        answer_generator=answer_generator,
        audit_sink=audit_sink,
        minimum_evidence_score=0.75,
    ).answer(
        context=_context("request-search-scope-violation"),
        question="Show authorized evidence",
    )

    assert search_index.call_count == 1
    assert reranker.call_count == 0
    assert answer_generator.call_count == 0
    assert control_plane.reference_calls == 0
    _assert_safe_scope_violation(
        result=result,
        audit_sink=audit_sink,
    )


@pytest.mark.parametrize(
    "injected_chunk",
    [
        _chunk(
            chunk_id="DENIED-CHUNK-SENTINEL",
            text="DENIED-TEXT-SENTINEL",
        ),
        _chunk(
            active_version=DENIED_VERSION,
            chunk_id="DENIED-CHUNK-SENTINEL",
            text="DENIED-TEXT-SENTINEL",
        ),
    ],
    ids=("new-candidate", "out-of-scope"),
)
def test_reranker_violation_fails_closed_before_llm_and_citation(
    injected_chunk,
):
    control_plane = _ControlPlane()
    authorized_chunk = _chunk()
    search_hit = SearchHit(chunk=authorized_chunk, score=0.80)

    class SearchIndex:
        def search(self, **_kwargs):
            return (search_hit,)

    reranker = _Reranker(
        returned_hits=(
            SearchHit(chunk=authorized_chunk, score=0.95),
            SearchHit(chunk=injected_chunk, score=0.99),
        )
    )
    answer_generator = _AnswerGenerator()
    audit_sink = _AuditSink()
    result = RetrievalService(
        control_plane=control_plane,
        search_index=SearchIndex(),
        reranker=reranker,
        answer_generator=answer_generator,
        audit_sink=audit_sink,
        minimum_evidence_score=0.75,
    ).answer(
        context=_context("request-reranker-scope-violation"),
        question="Show authorized evidence",
    )

    assert reranker.call_count == 1
    assert reranker.received_hits == (search_hit,)
    assert answer_generator.call_count == 0
    assert control_plane.reference_calls == 0
    _assert_safe_scope_violation(
        result=result,
        audit_sink=audit_sink,
    )


def test_mismatched_asset_reference_fails_closed_before_llm():
    first_chunk = _chunk(
        chunk_id="chunk-first",
        text="first authorized evidence",
    )
    second_chunk = _chunk(
        chunk_id="chunk-second",
        text="second authorized evidence",
    )

    class ControlPlane(_ControlPlane):
        def __init__(self):
            super().__init__()
            self.requested_chunk_pairs = []

        def get_asset_reference(
            self,
            *,
            tenant_id,
            asset_id,
            asset_version_id,
        ):
            self.reference_calls += 1
            self.requested_chunk_pairs.append(
                (tenant_id, asset_id, asset_version_id)
            )
            if self.reference_calls == 1:
                return AssetReference(
                    asset_id=asset_id,
                    asset_version_id=asset_version_id,
                    current_path="Reports/allowed.pdf",
                    version_path="Reports/allowed.pdf",
                )
            return AssetReference(
                asset_id="asset-other",
                asset_version_id="version-other-secret",
                current_path="DENIED-PATH-SENTINEL",
                version_path="DENIED-PATH-SENTINEL",
            )

    class SearchIndex:
        def search(self, **_kwargs):
            return (
                SearchHit(chunk=first_chunk, score=0.95),
                SearchHit(chunk=second_chunk, score=0.94),
            )

    control_plane = ControlPlane()
    reranker = _Reranker()
    answer_generator = _AnswerGenerator()
    audit_sink = _AuditSink()
    result = RetrievalService(
        control_plane=control_plane,
        search_index=SearchIndex(),
        reranker=reranker,
        answer_generator=answer_generator,
        audit_sink=audit_sink,
        minimum_evidence_score=0.75,
    ).answer(
        context=_context("request-reference-scope-violation"),
        question="Show authorized evidence",
    )

    assert reranker.call_count == 1
    assert control_plane.reference_calls == 2
    assert answer_generator.call_count == 0
    _assert_safe_scope_violation(
        result=result,
        audit_sink=audit_sink,
    )

