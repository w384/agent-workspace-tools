import pytest

from service.app.rag.contracts import (
    ActiveAssetVersion,
    AnswerStatus,
    AssetReference,
    Chunk,
    PermissionContext,
    RetrievalScope,
)
from service.app.rag.index import InMemorySearchIndex
from service.app.rag.ingestion import (
    IngestionFailureCode,
    IngestionRequest,
    IngestionService,
    IngestionStatus,
)
from service.app.rag.retrieval import RetrievalService


TENANT_ID = "tenant-demo"
ACTIVE_V1 = ActiveAssetVersion(
    asset_id="asset-stable",
    asset_version_id="version-v1",
)
TARGET_V2 = ActiveAssetVersion(
    asset_id="asset-stable",
    asset_version_id="version-v2",
)


def _chunk(
    active_version: ActiveAssetVersion,
    *,
    chunk_id: str,
    text: str,
) -> Chunk:
    return Chunk(
        tenant_id=TENANT_ID,
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


class _ControlPlaneStub:
    """Own the active pointer and expose only read/write ports to RAG."""

    def __init__(self) -> None:
        self.active_version = ACTIVE_V1
        self.events: list[tuple[str, str, str]] = [
            ("control_plane", "QUEUED", "version-v1")
        ]
        self.failure_codes: list[IngestionFailureCode] = []
        self.ready_probe = None

    def resolve_retrieval_scope(
        self,
        context: PermissionContext,
    ) -> RetrievalScope:
        assert context.tenant_id == TENANT_ID
        self.events.append(
            (
                "scope",
                self.active_version.asset_version_id,
                self.active_version.asset_version_id,
            )
        )
        return RetrievalScope(
            tenant_id=TENANT_ID,
            allowed_active_versions=(self.active_version,),
            denied_asset_ids=frozenset(),
        )

    def get_asset_reference(
        self,
        *,
        tenant_id: str,
        asset_id: str,
        asset_version_id: str,
    ) -> AssetReference:
        assert tenant_id == TENANT_ID
        assert asset_id == ACTIVE_V1.asset_id
        return AssetReference(
            asset_id=asset_id,
            asset_version_id=asset_version_id,
            current_path="Reports/current-report.pdf",
            version_path=f"Versions/{asset_version_id}.pdf",
        )

    def report_status(
        self,
        request: IngestionRequest,
        status: IngestionStatus,
    ) -> None:
        self.events.append(
            (
                "status",
                status.value,
                self.active_version.asset_version_id,
            )
        )
        if status is IngestionStatus.READY and self.ready_probe:
            self.ready_probe()

    def report_failure(
        self,
        request: IngestionRequest,
        failure_code: IngestionFailureCode,
    ) -> None:
        assert request.target_version == TARGET_V2
        self.failure_codes.append(failure_code)
        self.events.append(
            (
                "status",
                IngestionStatus.FAILED.value,
                self.active_version.asset_version_id,
            )
        )

    def activate_version(
        self,
        request: IngestionRequest,
    ) -> bool:
        assert request.target_version == TARGET_V2
        self.events.append(
            (
                "activate",
                request.target_version.asset_version_id,
                self.active_version.asset_version_id,
            )
        )
        self.active_version = request.target_version
        return True


class _RetrievalTrace:
    def __init__(self) -> None:
        self.scored_chunk_ids: list[str] = []
        self.reranked_chunk_ids: list[str] = []
        self.generated_chunk_ids: list[str] = []

    def reset(self) -> None:
        self.scored_chunk_ids.clear()
        self.reranked_chunk_ids.clear()
        self.generated_chunk_ids.clear()

    def score(self, _question: str, chunk: Chunk) -> float:
        self.scored_chunk_ids.append(chunk.chunk_id)
        return 0.95

    def rerank(self, *, hits, **_kwargs):
        self.reranked_chunk_ids.extend(
            hit.chunk.chunk_id for hit in hits
        )
        return tuple(hits)

    def generate(self, *, evidence, **_kwargs):
        self.generated_chunk_ids.extend(
            hit.chunk.chunk_id for hit in evidence
        )
        return "answer supported by the active version"


class _AuditSink:
    def __init__(self) -> None:
        self.events = []

    def record(self, event) -> None:
        self.events.append(event)


def _answer(
    *,
    control_plane: _ControlPlaneStub,
    index: InMemorySearchIndex,
    trace: _RetrievalTrace,
    request_id: str,
):
    trace.reset()
    return RetrievalService(
        control_plane=control_plane,
        search_index=index,
        reranker=trace,
        answer_generator=trace,
        audit_sink=_AuditSink(),
        minimum_evidence_score=0.75,
    ).answer(
        context=PermissionContext(
            tenant_id=TENANT_ID,
            principal_id="principal-demo",
            group_ids=("group-demo",),
            session_id="authenticated-session",
            request_id=request_id,
        ),
        question="Which active version is supported?",
    )


def _assert_only_version(
    *,
    result,
    trace: _RetrievalTrace,
    expected_version: ActiveAssetVersion,
    expected_chunk_id: str,
) -> None:
    assert result.status is AnswerStatus.ANSWERED
    assert trace.scored_chunk_ids == [expected_chunk_id]
    assert trace.reranked_chunk_ids == [expected_chunk_id]
    assert trace.generated_chunk_ids == [expected_chunk_id]
    assert len(result.citations) == 1
    citation = result.citations[0]
    assert citation.asset_id == expected_version.asset_id
    assert citation.asset_version_id == (
        expected_version.asset_version_id
    )
    assert citation.chunk_id == expected_chunk_id


@pytest.mark.parametrize(
    ("failure_stage", "expected_failure"),
    [
        ("parser", IngestionFailureCode.PARSER_FAILED),
        ("index", IngestionFailureCode.INDEX_FAILED),
    ],
)
def test_failed_v2_keeps_v1_scope_and_v2_out_of_retrieval(
    failure_stage,
    expected_failure,
):
    v1_chunk = _chunk(
        ACTIVE_V1,
        chunk_id="chunk-v1",
        text="active v1 evidence",
    )
    v2_chunk = _chunk(
        TARGET_V2,
        chunk_id="V2-CHUNK-SENTINEL",
        text="V2-TEXT-SENTINEL",
    )
    trace = _RetrievalTrace()
    index = InMemorySearchIndex(scorer=trace.score)
    # A disposable replica may contain an unactivated or failed version.
    index.rebuild((v1_chunk, v2_chunk))
    control_plane = _ControlPlaneStub()
    index_calls = []

    class Parser:
        def parse(self, _request):
            if failure_stage == "parser":
                raise RuntimeError(
                    "V2-PATH-SENTINEL V2-TEXT-SENTINEL"
                )
            return (v2_chunk,)

    class IndexWriter:
        def replace_version(self, **kwargs):
            index_calls.append(kwargs)
            raise RuntimeError(
                "V2-PATH-SENTINEL V2-TEXT-SENTINEL"
            )

    request = IngestionRequest(
        tenant_id=TENANT_ID,
        target_version=TARGET_V2,
        source_ref="control-plane://asset-stable/version-v2",
        content_fingerprint="sha256:fixed-v2",
        mime_type="application/pdf",
        size_bytes=1024,
    )
    ingestion_result = IngestionService(
        parser_worker=Parser(),
        index_writer=IndexWriter(),
        status_reporter=control_plane,
        control_plane=control_plane,
    ).process(request)

    result = _answer(
        control_plane=control_plane,
        index=index,
        trace=trace,
        request_id=f"request-{failure_stage}-failed",
    )

    assert ingestion_result.status is IngestionStatus.FAILED
    assert ingestion_result.failure_code is expected_failure
    assert control_plane.active_version == ACTIVE_V1
    assert len(index_calls) == (0 if failure_stage == "parser" else 1)
    _assert_only_version(
        result=result,
        trace=trace,
        expected_version=ACTIVE_V1,
        expected_chunk_id="chunk-v1",
    )
    safe_output = repr(
        (
            ingestion_result,
            control_plane.events,
            result,
            trace.reranked_chunk_ids,
            trace.generated_chunk_ids,
        )
    )
    assert "V2-CHUNK-SENTINEL" not in safe_output
    assert "V2-TEXT-SENTINEL" not in safe_output
    assert "V2-PATH-SENTINEL" not in safe_output


def test_ready_then_explicit_activation_switches_scope_atomically():
    v1_chunk = _chunk(
        ACTIVE_V1,
        chunk_id="chunk-v1",
        text="active v1 evidence",
    )
    v2_chunk = _chunk(
        TARGET_V2,
        chunk_id="chunk-v2",
        text="ready v2 evidence",
    )
    trace = _RetrievalTrace()
    index = InMemorySearchIndex(scorer=trace.score)
    index.rebuild((v1_chunk,))
    control_plane = _ControlPlaneStub()
    ready_observation = {}

    def query_while_ready_but_not_activated():
        ready_result = _answer(
            control_plane=control_plane,
            index=index,
            trace=trace,
            request_id="request-ready-before-activate",
        )
        ready_observation["result"] = ready_result
        ready_observation["scored"] = tuple(
            trace.scored_chunk_ids
        )
        ready_observation["reranked"] = tuple(
            trace.reranked_chunk_ids
        )
        ready_observation["generated"] = tuple(
            trace.generated_chunk_ids
        )

    control_plane.ready_probe = query_while_ready_but_not_activated

    class Parser:
        def parse(self, _request):
            return (v2_chunk,)

    ingestion_result = IngestionService(
        parser_worker=Parser(),
        index_writer=index,
        status_reporter=control_plane,
        control_plane=control_plane,
    ).process(
        IngestionRequest(
            tenant_id=TENANT_ID,
            target_version=TARGET_V2,
            source_ref="control-plane://asset-stable/version-v2",
            content_fingerprint="sha256:fixed-v2",
            mime_type="application/pdf",
            size_bytes=1024,
        )
    )

    ready_result = ready_observation["result"]
    assert ready_observation["scored"] == ("chunk-v1",)
    assert ready_observation["reranked"] == ("chunk-v1",)
    assert ready_observation["generated"] == ("chunk-v1",)
    assert ready_result.citations[0].asset_version_id == "version-v1"

    assert ingestion_result.status is IngestionStatus.READY
    assert ingestion_result.activated is True
    assert control_plane.active_version == TARGET_V2
    ready_event_index = control_plane.events.index(
        ("status", "READY", "version-v1")
    )
    activate_event_index = control_plane.events.index(
        ("activate", "version-v2", "version-v1")
    )
    assert ready_event_index < activate_event_index

    activated_result = _answer(
        control_plane=control_plane,
        index=index,
        trace=trace,
        request_id="request-after-activate",
    )
    _assert_only_version(
        result=activated_result,
        trace=trace,
        expected_version=TARGET_V2,
        expected_chunk_id="chunk-v2",
    )

