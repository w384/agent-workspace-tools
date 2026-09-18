"""In-process RAG query bridge for the controlled public-drive demo assets."""

import os
from dataclasses import asdict
from typing import Mapping

from control_plane.app.domain import Action, DecisionState, AssetVersion, TrustedActorContext
from control_plane.app.policy import evaluate_authorization
from control_plane.app.repository import ControlPlaneRepository

from service.app.rag.control_plane_adapter import ControlPlaneRetrievalAdapter
from service.app.rag.contracts import (
    AnswerStatus,
    LLMConfigurationError,
    PermissionContext,
    RetrievalAuditEvent,
    RetrievalFilter,
)
from service.app.rag.llm import build_llm_answer_generator
from service.app.rag.retrieval import RetrievalService


class DemoRagPort:
    """Expose only trusted-session query results from the in-memory demo index."""

    def __init__(
        self,
        *,
        repository: ControlPlaneRepository,
        search_index: object,
        minimum_evidence_score: float = 0.75,
        answer_generator: object | None = None,
    ) -> None:
        self._repository = repository
        self._search_index = search_index
        self._minimum_evidence_score = minimum_evidence_score
        if answer_generator is None:
            answer_generator = _build_default_answer_generator()
        self._answer_generator = answer_generator
        self.audit_events: list[RetrievalAuditEvent] = []

    def set_answer_generator(self, answer_generator: object | None) -> None:
        """Replace the answer generator at runtime (provider switch)."""
        self._answer_generator = answer_generator

    def enqueue_version(
        self,
        actor: TrustedActorContext,
        asset_version: AssetVersion,
        request_id: str,
    ) -> None:
        raise RuntimeError(
            "demo query bridge does not ingest arbitrary uploaded files"
        )

    def query(
        self,
        actor: TrustedActorContext,
        question: str,
        asset_id: str,
    ) -> Mapping[str, object]:
        asset = self._get_authorized_asset(actor, asset_id)
        if asset is None:
            return self._denied_payload(actor)
        if self._answer_generator is None:
            return self._llm_unavailable_payload(actor)
        result = RetrievalService(
            control_plane=ControlPlaneRetrievalAdapter(
                repository=self._repository,
                actor=actor,
            ),
            search_index=_AssetScopedSearchIndex(
                self._search_index,
                scopes=frozenset({(asset.asset_id, asset.active_version_id)}),
            ),
            reranker=_IdentityReranker(),
            answer_generator=self._answer_generator,
            audit_sink=self,
            minimum_evidence_score=self._minimum_evidence_score,
        ).answer(
            context=PermissionContext(
                tenant_id=actor.workspace_id,
                principal_id=actor.actor_id,
                group_ids=tuple(sorted(actor.group_ids)),
                session_id=actor.session_id,
                request_id=actor.request_id,
            ),
            question=question,
        )
        return {
            "status": result.status.value,
            "answer": result.answer,
            "reason": result.reason,
            "retrieved_count": result.retrieved_count,
            "llm_invoked": result.llm_invoked,
            "citations": [
                {
                    **asdict(citation),
                    "path_kind": citation.path_kind.value,
                }
                for citation in result.citations
            ],
        }

    def query_multi(
        self,
        actor: TrustedActorContext,
        question: str,
        asset_ids: tuple[str, ...],
    ) -> Mapping[str, object]:
        """Query across several authorized uploaded assets (all-or-nothing).

        Every requested asset must be authorized for the actor; if any is not,
        the whole query is DENIED with zero recall and zero LLM calls
        (fail-closed). The shared index is scoped to the union of the active
        versions, so evidence may span all requested files in one LLM call.
        """
        scopes: set[tuple[str, str]] = set()
        for asset_id in asset_ids:
            asset = self._get_authorized_asset(actor, asset_id)
            if asset is None:
                return self._denied_payload(actor)
            scopes.add((asset.asset_id, asset.active_version_id))
        if self._answer_generator is None:
            return self._llm_unavailable_payload(actor)
        result = RetrievalService(
            control_plane=ControlPlaneRetrievalAdapter(
                repository=self._repository,
                actor=actor,
            ),
            search_index=_AssetScopedSearchIndex(
                self._search_index,
                scopes=frozenset(scopes),
            ),
            reranker=_IdentityReranker(),
            answer_generator=self._answer_generator,
            audit_sink=self,
            minimum_evidence_score=self._minimum_evidence_score,
        ).answer(
            context=PermissionContext(
                tenant_id=actor.workspace_id,
                principal_id=actor.actor_id,
                group_ids=tuple(sorted(actor.group_ids)),
                session_id=actor.session_id,
                request_id=actor.request_id,
            ),
            question=question,
        )
        return {
            "status": result.status.value,
            "answer": result.answer,
            "reason": result.reason,
            "retrieved_count": result.retrieved_count,
            "llm_invoked": result.llm_invoked,
            "citations": [
                {
                    **asdict(citation),
                    "path_kind": citation.path_kind.value,
                }
                for citation in result.citations
            ],
        }

    def record(self, event: RetrievalAuditEvent) -> None:
        self.audit_events.append(event)

    def _get_authorized_asset(
        self, actor: TrustedActorContext, asset_id: str
    ) -> object | None:
        try:
            asset = self._repository.get_asset(asset_id)
        except KeyError:
            return None
        if asset.workspace_id != actor.workspace_id or asset.active_version_id is None:
            return None
        decision = evaluate_authorization(
            actor,
            self._repository.list_permission_grants(actor),
            Action.QUERY,
            paths=(asset.path,),
        )
        if decision.state is DecisionState.DENY:
            return None
        return asset

    def _denied_payload(self, actor: TrustedActorContext) -> Mapping[str, object]:
        self.record(
            RetrievalAuditEvent(
                request_id=actor.request_id,
                status=AnswerStatus.DENIED,
                authorized_candidate_count=0,
                evidence_count=0,
            )
        )
        return {
            "status": AnswerStatus.DENIED.value,
            "answer": None,
            "reason": "ACCESS_DENIED",
            "retrieved_count": 0,
            "llm_invoked": False,
            "citations": [],
        }

    def _llm_unavailable_payload(
        self, actor: TrustedActorContext
    ) -> Mapping[str, object]:
        self.record(
            RetrievalAuditEvent(
                request_id=actor.request_id,
                status=AnswerStatus.REFUSED,
                authorized_candidate_count=0,
                evidence_count=0,
            )
        )
        return {
            "status": AnswerStatus.REFUSED.value,
            "answer": None,
            "reason": "llm_not_configured",
            "retrieved_count": 0,
            "llm_invoked": False,
            "citations": [],
        }


class _IdentityReranker:
    def rerank(self, *, hits: object, **_kwargs: object) -> object:
        return hits


class _AssetScopedSearchIndex:
    """Narrow a server-built filter to authorized control-plane assets.

    scopes is a set of (asset_id, asset_version_id) pairs; the single-asset
    query passes a one-element set, the multi-asset query passes the union.
    """

    def __init__(
        self,
        search_index: object,
        *,
        scopes: frozenset[tuple[str, str]],
    ) -> None:
        self._search_index = search_index
        self._scopes = scopes

    def search(self, *, question: str, retrieval_filter: RetrievalFilter, limit: int):
        narrowed = RetrievalFilter(
            tenant_id=retrieval_filter.tenant_id,
            allowed_active_versions=tuple(
                item
                for item in retrieval_filter.allowed_active_versions
                if (item.asset_id, item.asset_version_id) in self._scopes
            ),
            denied_asset_ids=retrieval_filter.denied_asset_ids,
        )
        return self._search_index.search(
            question=question,
            retrieval_filter=narrowed,
            limit=limit,
        )


def _build_default_answer_generator() -> object | None:
    """Build the RAG real LLM answer generator from the environment."""
    try:
        return build_llm_answer_generator(os.environ)
    except LLMConfigurationError:
        return None