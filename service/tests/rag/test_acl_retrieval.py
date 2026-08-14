import importlib

import pytest


def _load_rag_modules():
    try:
        contracts = importlib.import_module(
            "service.app.rag.contracts"
        )
        retrieval = importlib.import_module(
            "service.app.rag.retrieval"
        )
    except ModuleNotFoundError as error:
        pytest.fail(
            f"RAG retrieval boundary is not implemented: {error}"
        )
    return contracts, retrieval


def test_deny_filter_is_applied_before_recall_and_never_reaches_downstream():
    """Removing the server ACL filter must expose the denied sentinel and fail."""
    contracts, retrieval = _load_rag_modules()

    allowed_chunk = contracts.Chunk(
        tenant_id="tenant-demo",
        asset_id="asset-allowed",
        asset_version_id="version-allowed-v1",
        chunk_id="chunk-allowed",
        ordinal=0,
        text="approved operating margin evidence",
        page_number=1,
        paragraph_index=None,
        parser_version="parser-v1",
        embedding_version="embedding-v1",
        index_version="index-v1",
    )
    denied_chunk = contracts.Chunk(
        tenant_id="tenant-demo",
        asset_id="asset-denied",
        asset_version_id="version-denied-v1",
        chunk_id="DENIED-CHUNK-SENTINEL",
        ordinal=0,
        text="DENIED-TEXT-SENTINEL",
        page_number=9,
        paragraph_index=None,
        parser_version="parser-v1",
        embedding_version="embedding-v1",
        index_version="index-v1",
    )

    scope = contracts.RetrievalScope(
        tenant_id="tenant-demo",
        allowed_active_versions=(
            contracts.ActiveAssetVersion(
                asset_id="asset-allowed",
                asset_version_id="version-allowed-v1",
            ),
            contracts.ActiveAssetVersion(
                asset_id="asset-denied",
                asset_version_id="version-denied-v1",
            ),
        ),
        denied_asset_ids=frozenset({"asset-denied"}),
    )

    class ControlPlaneStub:
        def resolve_retrieval_scope(self, context):
            assert context.principal_id == "principal-a"
            return scope

        def get_asset_reference(
            self,
            *,
            tenant_id,
            asset_id,
            asset_version_id,
        ):
            assert tenant_id == "tenant-demo"
            assert asset_id == "asset-allowed"
            assert asset_version_id == "version-allowed-v1"
            return contracts.AssetReference(
                asset_id=asset_id,
                asset_version_id=asset_version_id,
                current_path="Finance/approved.pdf",
                version_path="Finance/approved.pdf",
            )

    class SearchIndexStub:
        def __init__(self):
            self.received_filter = None

        def search(self, *, question, retrieval_filter, limit):
            assert question == "What is the approved margin?"
            assert limit == 5
            self.received_filter = retrieval_filter
            all_chunks = (allowed_chunk, denied_chunk)
            allowed_pairs = {
                (item.asset_id, item.asset_version_id)
                for item in (
                    retrieval_filter.allowed_active_versions
                )
            }
            return tuple(
                contracts.SearchHit(chunk=chunk, score=0.91)
                for chunk in all_chunks
                if (
                    chunk.asset_id,
                    chunk.asset_version_id,
                ) in allowed_pairs
                and chunk.asset_id
                not in retrieval_filter.denied_asset_ids
            )

    class RerankerStub:
        def __init__(self):
            self.received_chunks = ()

        def rerank(self, *, question, hits, limit):
            self.received_chunks = tuple(hit.chunk for hit in hits)
            return tuple(hits[:limit])

    class AnswerGeneratorStub:
        def __init__(self):
            self.received_chunks = ()

        def generate(self, *, question, evidence):
            self.received_chunks = tuple(
                hit.chunk for hit in evidence
            )
            return "The approved margin is supported by the cited page."

    class AuditSinkStub:
        def __init__(self):
            self.events = []

        def record(self, event):
            self.events.append(event)

    search_index = SearchIndexStub()
    reranker = RerankerStub()
    answer_generator = AnswerGeneratorStub()
    audit_sink = AuditSinkStub()
    service = retrieval.RetrievalService(
        control_plane=ControlPlaneStub(),
        search_index=search_index,
        reranker=reranker,
        answer_generator=answer_generator,
        audit_sink=audit_sink,
        minimum_evidence_score=0.75,
    )

    result = service.answer(
        context=contracts.PermissionContext(
            tenant_id="tenant-demo",
            principal_id="principal-a",
            group_ids=("group-finance",),
            session_id="session-authenticated-by-bff",
            request_id="request-001",
        ),
        question="What is the approved margin?",
    )

    assert search_index.received_filter.allowed_active_versions == (
        contracts.ActiveAssetVersion(
            asset_id="asset-allowed",
            asset_version_id="version-allowed-v1",
        ),
    )
    assert search_index.received_filter.denied_asset_ids == (
        "asset-denied",
    )
    assert [chunk.chunk_id for chunk in reranker.received_chunks] == [
        "chunk-allowed"
    ]
    assert [
        chunk.chunk_id
        for chunk in answer_generator.received_chunks
    ] == ["chunk-allowed"]
    assert result.status == contracts.AnswerStatus.ANSWERED
    assert [citation.chunk_id for citation in result.citations] == [
        "chunk-allowed"
    ]

    downstream_evidence = repr(
        (
            reranker.received_chunks,
            answer_generator.received_chunks,
            audit_sink.events,
            result,
        )
    )
    assert "DENIED-CHUNK-SENTINEL" not in downstream_evidence
    assert "DENIED-TEXT-SENTINEL" not in downstream_evidence


def test_filter_keeps_asset_and_active_version_as_atomic_pairs():
    """Independent IN filters must not admit an unauthorized cross-pair."""
    contracts, retrieval = _load_rag_modules()
    chunks = (
        contracts.Chunk(
            tenant_id="tenant-demo",
            asset_id="asset-a",
            asset_version_id="version-a-v1",
            chunk_id="chunk-a-v1",
            ordinal=0,
            text="approved evidence A",
            page_number=1,
            paragraph_index=None,
            parser_version="parser-v1",
            embedding_version="embedding-v1",
            index_version="index-v1",
        ),
        contracts.Chunk(
            tenant_id="tenant-demo",
            asset_id="asset-b",
            asset_version_id="version-b-v2",
            chunk_id="chunk-b-v2",
            ordinal=0,
            text="approved evidence B",
            page_number=2,
            paragraph_index=None,
            parser_version="parser-v1",
            embedding_version="embedding-v1",
            index_version="index-v1",
        ),
        contracts.Chunk(
            tenant_id="tenant-demo",
            asset_id="asset-a",
            asset_version_id="version-b-v2",
            chunk_id="CROSS-VERSION-CHUNK-SENTINEL",
            ordinal=0,
            text="CROSS-VERSION-TEXT-SENTINEL",
            page_number=99,
            paragraph_index=None,
            parser_version="parser-v1",
            embedding_version="embedding-v1",
            index_version="index-v1",
        ),
    )
    scope = contracts.RetrievalScope(
        tenant_id="tenant-demo",
        allowed_active_versions=(
            contracts.ActiveAssetVersion(
                asset_id="asset-a",
                asset_version_id="version-a-v1",
            ),
            contracts.ActiveAssetVersion(
                asset_id="asset-b",
                asset_version_id="version-b-v2",
            ),
        ),
        denied_asset_ids=frozenset(),
    )

    class ControlPlaneStub:
        def resolve_retrieval_scope(self, _context):
            return scope

        def get_asset_reference(
            self,
            *,
            asset_id,
            asset_version_id,
            **_kwargs,
        ):
            return contracts.AssetReference(
                asset_id=asset_id,
                asset_version_id=asset_version_id,
                current_path=f"Current/{asset_id}.pdf",
                version_path=f"Current/{asset_id}.pdf",
            )

    class PairAwareSearchIndexStub:
        def search(
            self,
            *,
            retrieval_filter,
            **_kwargs,
        ):
            expected_pairs = (
                contracts.ActiveAssetVersion(
                    asset_id="asset-a",
                    asset_version_id="version-a-v1",
                ),
                contracts.ActiveAssetVersion(
                    asset_id="asset-b",
                    asset_version_id="version-b-v2",
                ),
            )
            actual_pairs = getattr(
                retrieval_filter,
                "allowed_active_versions",
                (),
            )
            assert actual_pairs == expected_pairs
            allowed_pairs = {
                (item.asset_id, item.asset_version_id)
                for item in actual_pairs
            }
            return tuple(
                contracts.SearchHit(chunk=chunk, score=0.9)
                for chunk in chunks
                if (
                    chunk.asset_id,
                    chunk.asset_version_id,
                ) in allowed_pairs
            )

    class RerankerStub:
        def rerank(self, *, hits, **_kwargs):
            return tuple(hits)

    class AnswerGeneratorStub:
        def generate(self, **_kwargs):
            return "answer"

    class AuditSinkStub:
        def record(self, _event):
            return None

    result = retrieval.RetrievalService(
        control_plane=ControlPlaneStub(),
        search_index=PairAwareSearchIndexStub(),
        reranker=RerankerStub(),
        answer_generator=AnswerGeneratorStub(),
        audit_sink=AuditSinkStub(),
        minimum_evidence_score=0.75,
    ).answer(
        context=contracts.PermissionContext(
            tenant_id="tenant-demo",
            principal_id="principal-a",
            group_ids=(),
            session_id="session-authenticated-by-bff",
            request_id="request-pairs",
        ),
        question="Show approved evidence",
    )

    result_dump = repr(result)
    assert "chunk-a-v1" in result_dump
    assert "chunk-b-v2" in result_dump
    assert "CROSS-VERSION-CHUNK-SENTINEL" not in result_dump
    assert "CROSS-VERSION-TEXT-SENTINEL" not in result_dump


def test_full_deny_short_circuits_before_search_and_returns_safe_metadata():
    """A future search call on a fully denied scope must fail this test."""
    contracts, retrieval = _load_rag_modules()
    scope = contracts.RetrievalScope(
        tenant_id="tenant-demo",
        allowed_active_versions=(
            contracts.ActiveAssetVersion(
                asset_id="asset-denied",
                asset_version_id="version-denied-v1",
            ),
        ),
        denied_asset_ids=frozenset({"asset-denied"}),
    )

    class ControlPlaneStub:
        denied_path = "Secret/DENIED-PATH-SENTINEL.pdf"
        denied_text = "DENIED-TEXT-SENTINEL"

        def resolve_retrieval_scope(self, context):
            return scope

        def get_asset_reference(self, **_kwargs):
            raise AssertionError(
                "citation lookup must not run for a denied request"
            )

    class SearchIndexStub:
        def __init__(self):
            self.call_count = 0

        def search(self, **_kwargs):
            self.call_count += 1
            return ()

    class RerankerStub:
        def __init__(self):
            self.call_count = 0

        def rerank(self, **_kwargs):
            self.call_count += 1
            return ()

    class AnswerGeneratorStub:
        def __init__(self):
            self.call_count = 0

        def generate(self, **_kwargs):
            self.call_count += 1
            return "must not be generated"

    class AuditSinkStub:
        def __init__(self):
            self.events = []

        def record(self, event):
            self.events.append(event)

    search_index = SearchIndexStub()
    reranker = RerankerStub()
    answer_generator = AnswerGeneratorStub()
    audit_sink = AuditSinkStub()
    service = retrieval.RetrievalService(
        control_plane=ControlPlaneStub(),
        search_index=search_index,
        reranker=reranker,
        answer_generator=answer_generator,
        audit_sink=audit_sink,
        minimum_evidence_score=0.75,
    )

    result = service.answer(
        context=contracts.PermissionContext(
            tenant_id="tenant-demo",
            principal_id="principal-a",
            group_ids=(),
            session_id="session-authenticated-by-bff",
            request_id="request-denied",
        ),
        question="Reveal the denied document",
    )

    assert search_index.call_count == 0
    assert reranker.call_count == 0
    assert answer_generator.call_count == 0
    assert result.status == contracts.AnswerStatus.DENIED
    assert result.retrieved_count == 0
    assert result.llm_invoked is False
    assert result.citations == ()
    assert result.answer is None

    safe_output = repr((result, audit_sink.events))
    assert "DENIED-PATH-SENTINEL" not in safe_output
    assert "DENIED-TEXT-SENTINEL" not in safe_output
    assert "asset-denied" not in safe_output
    assert "version-denied-v1" not in safe_output


def test_low_evidence_refuses_before_answer_generation():
    """Lowering evidence quality must never be masked by fluent LLM output."""
    contracts, retrieval = _load_rag_modules()
    low_evidence_chunk = contracts.Chunk(
        tenant_id="tenant-demo",
        asset_id="asset-a",
        asset_version_id="version-a-v1",
        chunk_id="chunk-low-evidence",
        ordinal=0,
        text="weakly related text",
        page_number=None,
        paragraph_index=3,
        parser_version="parser-v1",
        embedding_version="embedding-v1",
        index_version="index-v1",
    )
    scope = contracts.RetrievalScope(
        tenant_id="tenant-demo",
        allowed_active_versions=(
            contracts.ActiveAssetVersion(
                asset_id="asset-a",
                asset_version_id="version-a-v1",
            ),
        ),
        denied_asset_ids=frozenset(),
    )

    class ControlPlaneStub:
        def resolve_retrieval_scope(self, _context):
            return scope

        def get_asset_reference(self, **_kwargs):
            return contracts.AssetReference(
                asset_id="asset-a",
                asset_version_id="version-a-v1",
                current_path="Current/a.txt",
                version_path="Current/a.txt",
            )

    class SearchIndexStub:
        def search(self, **_kwargs):
            return (
                contracts.SearchHit(
                    chunk=low_evidence_chunk,
                    score=0.40,
                ),
            )

    class RerankerStub:
        def __init__(self):
            self.call_count = 0

        def rerank(self, *, hits, **_kwargs):
            self.call_count += 1
            return tuple(hits)

    class AnswerGeneratorStub:
        def __init__(self):
            self.call_count = 0

        def generate(self, **_kwargs):
            self.call_count += 1
            return "unsupported fluent answer"

    class AuditSinkStub:
        def __init__(self):
            self.events = []

        def record(self, event):
            self.events.append(event)

    reranker = RerankerStub()
    answer_generator = AnswerGeneratorStub()
    audit_sink = AuditSinkStub()
    result = retrieval.RetrievalService(
        control_plane=ControlPlaneStub(),
        search_index=SearchIndexStub(),
        reranker=reranker,
        answer_generator=answer_generator,
        audit_sink=audit_sink,
        minimum_evidence_score=0.75,
    ).answer(
        context=contracts.PermissionContext(
            tenant_id="tenant-demo",
            principal_id="principal-a",
            group_ids=(),
            session_id="session-authenticated-by-bff",
            request_id="request-low-evidence",
        ),
        question="What is the unsupported conclusion?",
    )

    assert reranker.call_count == 1
    assert answer_generator.call_count == 0
    assert result.status == contracts.AnswerStatus.REFUSED
    assert result.reason == "evidence_insufficient"
    assert result.retrieved_count == 1
    assert result.llm_invoked is False
    assert result.citations == ()
    assert result.answer is None
    assert len(audit_sink.events) == 1
    assert audit_sink.events[0].status == (
        contracts.AnswerStatus.REFUSED
    )

