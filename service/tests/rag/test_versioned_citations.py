from service.app.rag.contracts import (
    ActiveAssetVersion,
    AnswerStatus,
    AssetReference,
    Chunk,
    CitationPathKind,
    PermissionContext,
    RetrievalScope,
    SearchHit,
)
from service.app.rag.retrieval import RetrievalService


def test_rename_preserves_asset_identity_and_versioned_citation_paths():
    """A path rename must not become a new asset or orphan its citation."""
    chunk = Chunk(
        tenant_id="tenant-demo",
        asset_id="asset-stable",
        asset_version_id="version-stable-v1",
        chunk_id="chunk-page-4",
        ordinal=0,
        text="versioned evidence",
        page_number=4,
        paragraph_index=None,
        parser_version="parser-v1",
        embedding_version="embedding-v1",
        index_version="index-v1",
    )

    class ControlPlaneStub:
        def __init__(self):
            self.current_path = "Incoming/report.pdf"
            self.version_path = "Incoming/report.pdf"

        def resolve_retrieval_scope(self, _context):
            return RetrievalScope(
                tenant_id="tenant-demo",
                allowed_active_versions=(
                    ActiveAssetVersion(
                        asset_id="asset-stable",
                        asset_version_id="version-stable-v1",
                    ),
                ),
                denied_asset_ids=frozenset(),
            )

        def get_asset_reference(self, **_kwargs):
            return AssetReference(
                asset_id="asset-stable",
                asset_version_id="version-stable-v1",
                current_path=self.current_path,
                version_path=self.version_path,
            )

        def rename_asset(self, new_path):
            self.current_path = new_path

    class SearchIndexStub:
        def search(self, *, retrieval_filter, **_kwargs):
            assert retrieval_filter.allowed_active_versions == (
                ActiveAssetVersion(
                    asset_id="asset-stable",
                    asset_version_id="version-stable-v1",
                ),
            )
            return (SearchHit(chunk=chunk, score=0.95),)

    class RerankerStub:
        def rerank(self, *, hits, **_kwargs):
            return tuple(hits)

    class AnswerGeneratorStub:
        def generate(self, **_kwargs):
            return "answer"

    class AuditSinkStub:
        def record(self, _event):
            return None

    control_plane = ControlPlaneStub()
    service = RetrievalService(
        control_plane=control_plane,
        search_index=SearchIndexStub(),
        reranker=RerankerStub(),
        answer_generator=AnswerGeneratorStub(),
        audit_sink=AuditSinkStub(),
        minimum_evidence_score=0.75,
    )
    context = PermissionContext(
        tenant_id="tenant-demo",
        principal_id="principal-a",
        group_ids=(),
        session_id="session-authenticated-by-bff",
        request_id="request-citation",
    )

    before_rename = service.answer(
        context=context,
        question="Where is the evidence?",
    )
    control_plane.rename_asset("Organized/renamed-report.pdf")
    after_rename = service.answer(
        context=context,
        question="Where is the evidence?",
    )

    assert before_rename.status == AnswerStatus.ANSWERED
    before_citation = before_rename.citations[0]
    assert before_citation.asset_id == "asset-stable"
    assert before_citation.asset_version_id == "version-stable-v1"
    assert before_citation.chunk_id == "chunk-page-4"
    assert before_citation.page_number == 4
    assert before_citation.paragraph_index is None
    assert before_citation.path_kind == CitationPathKind.CURRENT
    assert before_citation.display_path == "Incoming/report.pdf"
    assert getattr(before_citation, "version_path", None) == (
        "Incoming/report.pdf"
    )

    assert after_rename.status == AnswerStatus.ANSWERED
    after_citation = after_rename.citations[0]
    assert after_citation.asset_id == "asset-stable"
    assert after_citation.asset_version_id == "version-stable-v1"
    assert after_citation.chunk_id == "chunk-page-4"
    assert after_citation.page_number == 4
    assert after_citation.path_kind == CitationPathKind.HISTORICAL
    assert after_citation.display_path == "Incoming/report.pdf"
    assert after_citation.current_path == (
        "Organized/renamed-report.pdf"
    )
    assert getattr(after_citation, "version_path", None) == (
        "Incoming/report.pdf"
    )


