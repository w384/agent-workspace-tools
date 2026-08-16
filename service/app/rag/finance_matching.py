from dataclasses import dataclass, replace
from enum import StrEnum
from typing import Protocol, Sequence

from service.app.rag.contracts import (
    ActiveAssetVersion,
    Chunk,
    LLMUnavailableError,
    PermissionContext,
    RetrievalFilter,
)


class RuleSourceType(StrEnum):
    DEMO_FIXTURE = "demo_fixture"
    MANUAL_ENTRY = "manual_entry"


class MaterialMatchStatus(StrEnum):
    MATCH = "MATCH"
    POSSIBLE = "POSSIBLE"
    NOT_MATCH = "NOT_MATCH"
    MISSING_INFO = "MISSING_INFO"


@dataclass(frozen=True, slots=True)
class MaterialRequirement:
    rule_id: str
    material_key: str
    label: str


@dataclass(frozen=True, slots=True)
class RuleVersionSnapshot:
    rule_set_id: str
    rule_version_id: str
    version_label: str
    source_type: RuleSourceType
    content_fingerprint: str
    disclaimer: str
    requirements: tuple[MaterialRequirement, ...]


@dataclass(frozen=True, slots=True)
class MaterialMatchingScope:
    tenant_id: str
    allowed_active_versions: tuple[ActiveAssetVersion, ...]
    denied_asset_ids: frozenset[str]
    rule_version: RuleVersionSnapshot


@dataclass(frozen=True, slots=True)
class MaterialFact:
    material_key: str
    chunk: Chunk


@dataclass(frozen=True, slots=True)
class MaterialFactHit:
    fact: MaterialFact
    score: float


@dataclass(frozen=True, slots=True)
class MaterialCitation:
    asset_id: str
    asset_version_id: str
    chunk_id: str
    page_number: int | None
    paragraph_index: int | None


@dataclass(frozen=True, slots=True)
class RuleCitation:
    rule_set_id: str
    rule_version_id: str
    rule_id: str
    version_label: str
    source_type: RuleSourceType
    content_fingerprint: str
    disclaimer: str


@dataclass(frozen=True, slots=True)
class MaterialMatchResult:
    status: MaterialMatchStatus | None
    match_score: int
    missing_materials: tuple[MaterialRequirement, ...]
    material_citations: tuple[MaterialCitation, ...]
    rule_citations: tuple[RuleCitation, ...]
    rule_version: RuleVersionSnapshot
    retrieved_count: int
    llm_invoked: bool
    explanation: str | None
    reason: str | None = None


class ControlPlanePort(Protocol):
    def resolve_material_matching_scope(
        self,
        context: PermissionContext,
    ) -> MaterialMatchingScope: ...


class MaterialFactIndex(Protocol):
    def search(
        self,
        *,
        retrieval_filter: RetrievalFilter,
        limit: int,
    ) -> Sequence[MaterialFactHit]: ...


class ExplanationPort(Protocol):
    def explain(
        self,
        structured_result: MaterialMatchResult,
    ) -> str: ...


class FinanceMaterialMatchingService:
    """Deterministically match authorized material facts to a rule version."""

    def __init__(
        self,
        *,
        control_plane: ControlPlanePort,
        fact_index: MaterialFactIndex,
        explanation_port: ExplanationPort | None = None,
    ) -> None:
        self._control_plane = control_plane
        self._fact_index = fact_index
        self._explanation_port = explanation_port

    def match(
        self,
        *,
        context: PermissionContext,
        limit: int = 5,
        include_explanation: bool = False,
    ) -> MaterialMatchResult:
        scope = self._control_plane.resolve_material_matching_scope(
            context
        )
        retrieval_filter = _build_filter(context, scope)
        if not retrieval_filter.allowed_active_versions:
            return _denied_result(scope.rule_version)
        hits = tuple(
            self._fact_index.search(
                retrieval_filter=retrieval_filter,
                limit=limit,
            )
        )
        if not _hits_match_filter(hits, retrieval_filter):
            return _denied_result(scope.rule_version)
        result = _score_matches(
            rule_version=scope.rule_version,
            hits=hits,
        )
        if include_explanation and self._explanation_port:
            try:
                explanation = self._explanation_port.explain(result)
            except LLMUnavailableError:
                return replace(
                    result,
                    explanation=None,
                    llm_invoked=True,
                    reason="llm_unavailable",
                )
            return replace(
                result,
                explanation=explanation,
                llm_invoked=True,
            )
        return result


def _build_filter(
    context: PermissionContext,
    scope: MaterialMatchingScope,
) -> RetrievalFilter:
    if scope.tenant_id != context.tenant_id:
        raise PermissionError("material matching scope rejected")

    active_versions = tuple(
        active_version
        for active_version in scope.allowed_active_versions
        if active_version.asset_id not in scope.denied_asset_ids
    )
    return RetrievalFilter(
        tenant_id=context.tenant_id,
        allowed_active_versions=active_versions,
        denied_asset_ids=tuple(sorted(scope.denied_asset_ids)),
    )


def _score_matches(
    *,
    rule_version: RuleVersionSnapshot,
    hits: tuple[MaterialFactHit, ...],
) -> MaterialMatchResult:
    matched_keys = frozenset(hit.fact.material_key for hit in hits)
    requirements = rule_version.requirements
    matched_requirements = tuple(
        requirement
        for requirement in requirements
        if requirement.material_key in matched_keys
    )
    missing_materials = tuple(
        requirement
        for requirement in requirements
        if requirement.material_key not in matched_keys
    )

    required_count = len(requirements)
    matched_count = len(matched_requirements)
    match_score = (
        round(100 * matched_count / required_count)
        if required_count
        else 0
    )
    if matched_count == required_count and required_count:
        status = MaterialMatchStatus.MATCH
    elif matched_count:
        status = MaterialMatchStatus.POSSIBLE
    else:
        status = MaterialMatchStatus.MISSING_INFO

    return MaterialMatchResult(
        status=status,
        match_score=match_score,
        missing_materials=missing_materials,
        material_citations=_material_citations(hits),
        rule_citations=tuple(
            _rule_citation(
                rule_version=rule_version,
                requirement=requirement,
            )
            for requirement in matched_requirements
        ),
        rule_version=rule_version,
        retrieved_count=len(hits),
        llm_invoked=False,
        explanation=None,
    )


def _denied_result(
    rule_version: RuleVersionSnapshot,
) -> MaterialMatchResult:
    return MaterialMatchResult(
        status=None,
        match_score=0,
        missing_materials=(),
        material_citations=(),
        rule_citations=(),
        rule_version=rule_version,
        retrieved_count=0,
        llm_invoked=False,
        explanation=None,
        reason="ACCESS_DENIED",
    )


def _hits_match_filter(
    hits: tuple[MaterialFactHit, ...],
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
            hit.fact.chunk.tenant_id == retrieval_filter.tenant_id
            and (
                hit.fact.chunk.asset_id,
                hit.fact.chunk.asset_version_id,
            )
            in allowed_pairs
            and hit.fact.chunk.asset_id not in denied_asset_ids
            for hit in hits
        )
    except (AttributeError, TypeError):
        return False


def _material_citations(
    hits: tuple[MaterialFactHit, ...],
) -> tuple[MaterialCitation, ...]:
    citations = []
    seen = set()
    for hit in hits:
        chunk = hit.fact.chunk
        key = (
            chunk.asset_id,
            chunk.asset_version_id,
            chunk.chunk_id,
            chunk.page_number,
            chunk.paragraph_index,
        )
        if key in seen:
            continue
        seen.add(key)
        citations.append(
            MaterialCitation(
                asset_id=chunk.asset_id,
                asset_version_id=chunk.asset_version_id,
                chunk_id=chunk.chunk_id,
                page_number=chunk.page_number,
                paragraph_index=chunk.paragraph_index,
            )
        )
    return tuple(citations)


def _rule_citation(
    *,
    rule_version: RuleVersionSnapshot,
    requirement: MaterialRequirement,
) -> RuleCitation:
    return RuleCitation(
        rule_set_id=rule_version.rule_set_id,
        rule_version_id=rule_version.rule_version_id,
        rule_id=requirement.rule_id,
        version_label=rule_version.version_label,
        source_type=rule_version.source_type,
        content_fingerprint=rule_version.content_fingerprint,
        disclaimer=rule_version.disclaimer,
    )
