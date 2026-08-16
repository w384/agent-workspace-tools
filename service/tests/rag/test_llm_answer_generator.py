"""Real LLM answer generator: prompt contract, invocation, and fail-closed."""

from __future__ import annotations

import httpx
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
ACTIVE_VERSION = ActiveAssetVersion(
    asset_id="asset-llm-demo",
    asset_version_id="version-llm-demo-v1",
)


def _chunk(
    *,
    chunk_id: str = "chunk-llm-1",
    text: str = "Authorized demo evidence for the question.",
    page_number: int | None = 3,
    paragraph_index: int | None = 7,
) -> Chunk:
    return Chunk(
        tenant_id=TENANT_ID,
        asset_id=ACTIVE_VERSION.asset_id,
        asset_version_id=ACTIVE_VERSION.asset_version_id,
        chunk_id=chunk_id,
        ordinal=0,
        text=text,
        page_number=page_number,
        paragraph_index=paragraph_index,
        parser_version="parser-v1",
        embedding_version="embedding-v1",
        index_version="index-v1",
    )


def _context(request_id: str = "request-llm-demo") -> PermissionContext:
    return PermissionContext(
        tenant_id=TENANT_ID,
        principal_id="principal-demo",
        group_ids=("group-demo",),
        session_id="authenticated-session",
        request_id=request_id,
    )


class _ControlPlane:
    def resolve_retrieval_scope(self, _context):
        return RetrievalScope(
            tenant_id=TENANT_ID,
            allowed_active_versions=(ACTIVE_VERSION,),
            denied_asset_ids=frozenset(),
        )

    def get_asset_reference(self, **_kwargs):
        return AssetReference(
            asset_id=ACTIVE_VERSION.asset_id,
            asset_version_id=ACTIVE_VERSION.asset_version_id,
            current_path="Reports/llm-demo.pdf",
            version_path="Reports/llm-demo.pdf",
        )


class _Reranker:
    def rerank(self, *, hits, **_kwargs):
        return tuple(hits)


class _AuditSink:
    def __init__(self) -> None:
        self.events = []

    def record(self, event) -> None:
        self.events.append(event)


class _DeniedControlPlane:
    def resolve_retrieval_scope(self, _context):
        return RetrievalScope(
            tenant_id=TENANT_ID,
            allowed_active_versions=(),
            denied_asset_ids=frozenset({ACTIVE_VERSION.asset_id}),
        )


class _SearchIndex:
    def __init__(self, *, chunk: Chunk | None = None) -> None:
        self._chunk = chunk

    def search(self, *, question, retrieval_filter, limit):
        if self._chunk is None:
            return ()
        return (SearchHit(chunk=self._chunk, score=0.95),)


def _capturing_transport():
    captured = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        body = {"choices": [{"message": {"content": "LLM drafted answer"}}]}
        return httpx.Response(200, json=body)

    return captured, httpx.MockTransport(handler)


def _llm_config():
    from service.app.rag.llm import LLMConfig

    return LLMConfig(
        base_url="https://llm.demo.example/v1",
        api_key="demo-secret-key-not-for-frontend",
        model="demo-llm-model",
        timeout_seconds=5.0,
    )


def _build_service(*, answer_generator, control_plane=None, search_index=None):
    return RetrievalService(
        control_plane=control_plane or _ControlPlane(),
        search_index=search_index or _SearchIndex(chunk=_chunk()),
        reranker=_Reranker(),
        answer_generator=answer_generator,
        audit_sink=_AuditSink(),
        minimum_evidence_score=0.75,
    )


def test_answered_answer_comes_from_real_llm():
    """ANSWERED must invoke the LLM once and return its output verbatim."""
    from service.app.rag.llm import (
        LLMAnswerGenerator,
        LLMClient,
    )

    captured, transport = _capturing_transport()
    generator = LLMAnswerGenerator(
        client=LLMClient(
            config=_llm_config(),
            transport=transport,
        )
    )
    result = _build_service(answer_generator=generator).answer(
        context=_context(),
        question="What does the evidence say?",
    )

    assert result.status is AnswerStatus.ANSWERED
    assert result.answer == "LLM drafted answer"
    assert result.llm_invoked is True
    assert len(captured) == 1


def test_llm_request_carries_question_and_authorized_evidence_only():
    from service.app.rag.llm import (
        LLMAnswerGenerator,
        LLMClient,
    )

    captured, transport = _capturing_transport()
    generator = LLMAnswerGenerator(
        client=LLMClient(
            config=_llm_config(),
            transport=transport,
        )
    )
    chunk = _chunk(text="ONLY-AUTHORIZED-EVIDENCE-SENTINEL")
    result = _build_service(
        answer_generator=generator,
        search_index=_SearchIndex(chunk=chunk),
    ).answer(
        context=_context(),
        question="Quote the evidence",
    )

    assert result.status is AnswerStatus.ANSWERED
    request = captured[0]
    request_body = request.read().decode("utf-8")
    assert "Quote the evidence" in request_body
    assert "ONLY-AUTHORIZED-EVIDENCE-SENTINEL" in request_body


def test_llm_request_does_not_require_adjudication_fields():
    """LLM must not be asked to decide authorization or emit scores."""
    from service.app.rag.llm import (
        LLMAnswerGenerator,
        LLMClient,
    )

    captured, transport = _capturing_transport()
    generator = LLMAnswerGenerator(
        client=LLMClient(
            config=_llm_config(),
            transport=transport,
        )
    )
    _build_service(answer_generator=generator).answer(
        context=_context(),
        question="Summarize",
    )

    request_body = captured[0].read().decode("utf-8")
    assert "authorized" in request_body.lower()
    assert "evidence" in request_body.lower()
    assert "loan" not in request_body.lower()
    assert "credit score" not in request_body.lower()
    assert "approve" not in request_body.lower()


def test_llm_credentials_never_leak_into_answer_or_citations():
    from service.app.rag.llm import (
        LLMAnswerGenerator,
        LLMClient,
    )

    captured, transport = _capturing_transport()
    generator = LLMAnswerGenerator(
        client=LLMClient(
            config=_llm_config(),
            transport=transport,
        )
    )
    result = _build_service(answer_generator=generator).answer(
        context=_context(),
        question="Summarize",
    )

    assert "demo-secret-key-not-for-frontend" not in result.answer
    safe_output = repr((result,))
    assert "demo-secret-key-not-for-frontend" not in safe_output
    authorization = captured[0].headers.get("authorization", "")
    assert "demo-secret-key-not-for-frontend" in authorization


def test_denied_scope_never_invokes_llm():
    from service.app.rag.llm import (
        LLMAnswerGenerator,
        LLMClient,
    )

    captured, transport = _capturing_transport()
    generator = LLMAnswerGenerator(
        client=LLMClient(
            config=_llm_config(),
            transport=transport,
        )
    )
    result = _build_service(
        answer_generator=generator,
        control_plane=_DeniedControlPlane(),
        search_index=_SearchIndex(),
    ).answer(
        context=_context(),
        question="Should I see this?",
    )

    assert result.status is AnswerStatus.DENIED
    assert result.llm_invoked is False
    assert result.answer is None
    assert result.citations == ()
    assert captured == []


def test_llm_failure_fails_closed_without_masking():
    from service.app.rag.llm import (
        LLMAnswerGenerator,
        LLMClient,
    )

    def failing_handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="upstream failure")

    generator = LLMAnswerGenerator(
        client=LLMClient(
            config=_llm_config(),
            transport=httpx.MockTransport(failing_handler),
        )
    )
    result = _build_service(answer_generator=generator).answer(
        context=_context(),
        question="What does the evidence say?",
    )

    assert result.status is AnswerStatus.REFUSED
    assert result.reason == "llm_unavailable"
    assert result.answer is None
    assert result.llm_invoked is True
    assert result.citations == ()


def test_llm_timeout_fails_closed():
    from service.app.rag.llm import (
        LLMAnswerGenerator,
        LLMClient,
    )

    def timeout_handler(_request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("upstream timed out")

    generator = LLMAnswerGenerator(
        client=LLMClient(
            config=_llm_config(),
            transport=httpx.MockTransport(timeout_handler),
        )
    )
    result = _build_service(answer_generator=generator).answer(
        context=_context(),
        question="What does the evidence say?",
    )

    assert result.status is AnswerStatus.REFUSED
    assert result.reason == "llm_unavailable"
    assert result.answer is None
    assert result.llm_invoked is True


def test_llm_config_requires_environment_injection():
    from service.app.rag.llm import LLMConfigurationError, load_llm_config

    with pytest.raises(LLMConfigurationError):
        load_llm_config({})


def test_llm_config_reads_injected_credentials():
    from service.app.rag.llm import load_llm_config

    config = load_llm_config(
        {
            "RAG_LLM_BASE_URL": "https://llm.demo.example/v1",
            "RAG_LLM_API_KEY": "injected-demo-key",
            "RAG_LLM_MODEL": "demo-model",
            "RAG_LLM_TIMEOUT_SECONDS": "7",
        }
    )
    assert config.base_url == "https://llm.demo.example/v1"
    assert config.api_key == "injected-demo-key"
    assert config.model == "demo-model"
    assert config.timeout_seconds == 7.0


def test_llm_config_allows_empty_api_key_for_local_ollama():
    """Local Ollama does not require an API key."""
    from service.app.rag.llm import load_llm_config

    config = load_llm_config(
        {
            "RAG_LLM_BASE_URL": "http://localhost:11434/v1",
            "RAG_LLM_API_KEY": "",
            "RAG_LLM_MODEL": "qwen3.5:9b",
        }
    )
    assert config.base_url == "http://localhost:11434/v1"
    assert config.api_key == ""
    assert config.model == "qwen3.5:9b"


def test_build_answer_generator_uses_injected_credentials():
    from service.app.rag.llm import (
        build_llm_answer_generator,
        load_llm_config,
    )

    environment = {
        "RAG_LLM_BASE_URL": "https://llm.demo.example/v1",
        "RAG_LLM_API_KEY": "injected-demo-key",
        "RAG_LLM_MODEL": "demo-model",
    }
    generator = build_llm_answer_generator(environment)
    assert generator is not None
    assert load_llm_config(environment).model == "demo-model"


def test_citations_bind_authorized_evidence_when_llm_answers():
    from service.app.rag.llm import (
        LLMAnswerGenerator,
        LLMClient,
    )

    captured, transport = _capturing_transport()
    generator = LLMAnswerGenerator(
        client=LLMClient(
            config=_llm_config(),
            transport=transport,
        )
    )
    chunk = _chunk()
    result = _build_service(
        answer_generator=generator,
        search_index=_SearchIndex(chunk=chunk),
    ).answer(
        context=_context(),
        question="Where is this evidence?",
    )

    assert result.status is AnswerStatus.ANSWERED
    assert len(result.citations) == 1
    citation = result.citations[0]
    assert citation.asset_id == ACTIVE_VERSION.asset_id
    assert citation.asset_version_id == ACTIVE_VERSION.asset_version_id
    assert citation.chunk_id == "chunk-llm-1"
    assert citation.page_number == 3
    assert citation.paragraph_index == 7
