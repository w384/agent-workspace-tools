from typing import Any

from service.app.rag.contracts import (
    AnswerResult,
    AnswerStatus,
    AssetReference,
    Citation,
    CitationPathKind,
    LLMUnavailableError,
    PermissionContext,
    RetrievalAuditEvent,
    RetrievalFilter,
    RetrievalScope,
    SearchHit,
)


class RetrievalService:
    """Apply authoritative ACL scope before any candidate is recalled."""

    def __init__(
        self,
        *,
        control_plane: Any,
        search_index: Any,
        reranker: Any,
        answer_generator: Any,
        audit_sink: Any,
        minimum_evidence_score: float,
    ) -> None:
        self._control_plane = control_plane
        self._search_index = search_index
        self._reranker = reranker
        self._answer_generator = answer_generator
        self._audit_sink = audit_sink
        self._minimum_evidence_score = minimum_evidence_score

    def answer(
        self,
        *,
        context: PermissionContext,
        question: str,
        limit: int = 5,
    ) -> AnswerResult:
        scope = self._control_plane.resolve_retrieval_scope(
            context
        )
        retrieval_filter = _build_filter(context, scope)
        if not retrieval_filter.allowed_active_versions:
            return self._record_denied_result(context)

        hits = tuple(
            self._search_index.search(
                question=question,
                retrieval_filter=retrieval_filter,
                limit=limit,
            )
        )
        if not _hits_match_filter(hits, retrieval_filter):
            return self._record_scope_violation(context)

        ranked_hits = tuple(
            self._reranker.rerank(
                question=question,
                hits=hits,
                limit=limit,
            )
        )
        if not _ranked_hits_match_candidates(
            ranked_hits,
            candidates=hits,
            retrieval_filter=retrieval_filter,
        ):
            return self._record_scope_violation(context)

        evidence = tuple(
            hit
            for hit in ranked_hits
            if hit.score >= self._minimum_evidence_score
        )
        if not evidence:
            return self._record_refused_result(
                context,
                retrieved_count=len(hits),
            )

        references = tuple(
            self._control_plane.get_asset_reference(
                tenant_id=context.tenant_id,
                asset_id=hit.chunk.asset_id,
                asset_version_id=(
                    hit.chunk.asset_version_id
                ),
            )
            for hit in evidence
        )
        if not _references_match_hits(
            references,
            hits=evidence,
        ):
            return self._record_scope_violation(context)

        try:
            answer = self._answer_generator.generate(
                question=question,
                evidence=evidence,
            )
        except LLMUnavailableError:
            return self._record_llm_unavailable(
                context,
                retrieved_count=len(hits),
            )
        citations = tuple(
            _build_citation(
                hit,
                reference,
            )
            for hit, reference in zip(
                evidence,
                references,
            )
        )
        result = AnswerResult(
            status=AnswerStatus.ANSWERED,
            answer=answer,
            reason=None,
            citations=citations,
            retrieved_count=len(hits),
            llm_invoked=True,
        )
        self._audit_sink.record(
            RetrievalAuditEvent(
                request_id=context.request_id,
                status=result.status,
                authorized_candidate_count=len(hits),
                evidence_count=len(evidence),
            )
        )
        return result

    def _record_refused_result(
        self,
        context: PermissionContext,
        *,
        retrieved_count: int,
    ) -> AnswerResult:
        result = AnswerResult(
            status=AnswerStatus.REFUSED,
            answer=None,
            reason="evidence_insufficient",
            citations=(),
            retrieved_count=retrieved_count,
            llm_invoked=False,
        )
        self._audit_sink.record(
            RetrievalAuditEvent(
                request_id=context.request_id,
                status=result.status,
                authorized_candidate_count=retrieved_count,
                evidence_count=0,
            )
        )
        return result

    def _record_llm_unavailable(
        self,
        context: PermissionContext,
        *,
        retrieved_count: int,
    ) -> AnswerResult:
        result = AnswerResult(
            status=AnswerStatus.REFUSED,
            answer=None,
            reason="llm_unavailable",
            citations=(),
            retrieved_count=retrieved_count,
            llm_invoked=True,
        )
        self._audit_sink.record(
            RetrievalAuditEvent(
                request_id=context.request_id,
                status=result.status,
                authorized_candidate_count=retrieved_count,
                evidence_count=0,
            )
        )
        return result

    def _record_denied_result(
        self,
        context: PermissionContext,
        *,
        reason: str = "ACCESS_DENIED",
    ) -> AnswerResult:
        result = AnswerResult(
            status=AnswerStatus.DENIED,
            answer=None,
            reason=reason,
            citations=(),
            retrieved_count=0,
            llm_invoked=False,
        )
        self._audit_sink.record(
            RetrievalAuditEvent(
                request_id=context.request_id,
                status=result.status,
                authorized_candidate_count=0,
                evidence_count=0,
            )
        )
        return result

    def _record_scope_violation(
        self,
        context: PermissionContext,
    ) -> AnswerResult:
        return self._record_denied_result(
            context,
            reason="retrieval_scope_violation",
        )


def _build_filter(
    context: PermissionContext,
    scope: RetrievalScope,
) -> RetrievalFilter:
    if scope.tenant_id != context.tenant_id:
        raise PermissionError("retrieval scope rejected")

    effective_versions = tuple(
        active_version
        for active_version in scope.allowed_active_versions
        if active_version.asset_id
        not in scope.denied_asset_ids
    )
    return RetrievalFilter(
        tenant_id=context.tenant_id,
        allowed_active_versions=effective_versions,
        denied_asset_ids=tuple(
            sorted(scope.denied_asset_ids)
        ),
    )


def _hits_match_filter(
    hits: tuple[SearchHit, ...],
    retrieval_filter: RetrievalFilter,
) -> bool:
    allowed_pairs = frozenset(
        (
            item.asset_id,
            item.asset_version_id,
        )
        for item in retrieval_filter.allowed_active_versions
    )
    denied_asset_ids = frozenset(
        retrieval_filter.denied_asset_ids
    )
    try:
        return all(
            hit.chunk.tenant_id == retrieval_filter.tenant_id
            and (
                hit.chunk.asset_id,
                hit.chunk.asset_version_id,
            )
            in allowed_pairs
            and hit.chunk.asset_id not in denied_asset_ids
            for hit in hits
        )
    except (AttributeError, TypeError):
        return False


def _ranked_hits_match_candidates(
    ranked_hits: tuple[SearchHit, ...],
    *,
    candidates: tuple[SearchHit, ...],
    retrieval_filter: RetrievalFilter,
) -> bool:
    if not _hits_match_filter(ranked_hits, retrieval_filter):
        return False
    try:
        return all(
            any(
                ranked_hit.chunk == candidate.chunk
                for candidate in candidates
            )
            for ranked_hit in ranked_hits
        )
    except (AttributeError, TypeError):
        return False


def _build_citation(
    hit: SearchHit,
    reference: AssetReference,
) -> Citation:
    if reference.current_path == reference.version_path:
        path_kind = CitationPathKind.CURRENT
        display_path = reference.current_path
    else:
        path_kind = CitationPathKind.HISTORICAL
        display_path = reference.version_path

    return Citation(
        asset_id=hit.chunk.asset_id,
        asset_version_id=hit.chunk.asset_version_id,
        chunk_id=hit.chunk.chunk_id,
        page_number=hit.chunk.page_number,
        paragraph_index=hit.chunk.paragraph_index,
        display_path=display_path,
        path_kind=path_kind,
        current_path=reference.current_path,
        version_path=reference.version_path,
    )


def _references_match_hits(
    references: tuple[AssetReference, ...],
    *,
    hits: tuple[SearchHit, ...],
) -> bool:
    if len(references) != len(hits):
        return False
    try:
        return all(
            reference.asset_id == hit.chunk.asset_id
            and reference.asset_version_id
            == hit.chunk.asset_version_id
            for hit, reference in zip(
                hits,
                references,
            )
        )
    except (AttributeError, TypeError):
        return False

