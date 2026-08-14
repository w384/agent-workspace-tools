"""Controlled PDF/DOCX finance-demo bridge; never ingests arbitrary uploads."""

from __future__ import annotations

import hashlib
import hmac
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from control_plane.app.domain import (
    Action,
    AssetVersion,
    DecisionState,
    RuleVersion,
    TrustedActorContext,
)
from control_plane.app.policy import evaluate_authorization
from control_plane.app.ports import AssessmentResult
from control_plane.app.repository import ControlPlaneRepository

from service.app.rag.contracts import (
    ActiveAssetVersion,
    PermissionContext,
    RetrievalFilter,
)
from service.app.rag.demo_document_parser import DemoDocumentParser
from service.app.rag.finance_matching import (
    ControlPlanePort,
    FinanceMaterialMatchingService,
    MaterialFact,
    MaterialFactHit,
    MaterialMatchingScope,
    MaterialRequirement,
    RuleSourceType,
    RuleVersionSnapshot,
)
from service.app.rag.index import InMemorySearchIndex
from service.app.rag.ingestion import IngestionRequest
from service.app.rag.parser_worker import DOCX_MIME_TYPE, PDF_MIME_TYPE


_SCENARIO = "finance_profile_matching"
_SOURCE_TYPE = "demo_fixture"


@dataclass(frozen=True, slots=True)
class _DeclaredAsset:
    relative_path: str
    material_key: str


class FinanceDemoRagPort:
    """Bridge only predeclared project-local samples into deterministic matching."""

    def __init__(
        self,
        *,
        repository: ControlPlaneRepository,
        source_root: Path,
        import_manifest_path: Path,
        rules_path: Path,
    ) -> None:
        self._repository = repository
        self._source_root = source_root.resolve()
        self._declared_assets = _load_import_manifest(import_manifest_path)
        self._rules_payload = _load_rules_fixture(rules_path)
        self.indexed_chunk_count = 0
        self.parsed_mime_types: frozenset[str] = frozenset()

    def enqueue_version(
        self,
        actor: TrustedActorContext,
        asset_version: AssetVersion,
        request_id: str,
    ) -> None:
        raise RuntimeError(
            "finance demo bridge does not ingest arbitrary uploaded files"
        )

    def query(
        self,
        actor: TrustedActorContext,
        question: str,
        asset_id: str,
    ) -> Mapping[str, object]:
        return {
            "status": "DENIED",
            "answer": None,
            "reason": "FINANCE_DEMO_ASSESSMENT_ONLY",
            "retrieved_count": 0,
            "llm_invoked": False,
            "citations": [],
        }

    def assess_versions(
        self,
        actor: TrustedActorContext,
        asset_versions: tuple[AssetVersion, ...],
        rule_version: RuleVersion,
        query_subject: str,
    ) -> AssessmentResult:
        del query_subject
        active_versions = self._require_authorized_active_versions(
            actor, asset_versions
        )
        rule_snapshot = self._rule_snapshot(rule_version)
        index, facts, parsed_mime_types = self._index_declared_facts(
            actor,
            asset_versions,
        )
        self.indexed_chunk_count = len(facts)
        self.parsed_mime_types = frozenset(parsed_mime_types)
        context = PermissionContext(
            tenant_id=actor.workspace_id,
            principal_id=actor.actor_id,
            group_ids=tuple(sorted(actor.group_ids)),
            session_id=actor.session_id,
            request_id=actor.request_id,
        )
        result = FinanceMaterialMatchingService(
            control_plane=_FixedMatchingScope(
                context=context,
                active_versions=active_versions,
                rule_version=rule_snapshot,
            ),
            fact_index=_IndexedFacts(index=index, facts=facts),
        ).match(
            context=context,
            limit=len(facts),
            include_explanation=False,
        )
        if result.status is None:
            raise PermissionError("finance demo matching scope denied")
        return AssessmentResult(
            match_score=result.match_score,
            result_level=result.status.value,
            missing_materials=tuple(
                requirement.label for requirement in result.missing_materials
            ),
            citations=tuple(
                [
                    {
                        "citation_type": "material",
                        "asset_id": citation.asset_id,
                        "asset_version_id": citation.asset_version_id,
                        "chunk_id": citation.chunk_id,
                        "page": citation.page_number,
                        "paragraph": citation.paragraph_index,
                        "rule_version_id": rule_version.rule_version_id,
                    }
                    for citation in result.material_citations
                ]
                + [
                    {
                        "citation_type": "rule",
                        "rule_id": citation.rule_id,
                        "rule_version_id": citation.rule_version_id,
                        "version_label": citation.version_label,
                        "content_fingerprint": citation.content_fingerprint,
                        "source_type": citation.source_type.value,
                    }
                    for citation in result.rule_citations
                ]
            ),
        )

    def _require_authorized_active_versions(
        self,
        actor: TrustedActorContext,
        asset_versions: tuple[AssetVersion, ...],
    ) -> tuple[ActiveAssetVersion, ...]:
        if not asset_versions:
            raise PermissionError("finance demo requires authorized versions")
        paths: list[str] = []
        active_versions: list[ActiveAssetVersion] = []
        for version in asset_versions:
            asset = self._repository.get_asset(version.asset_id)
            if (
                asset.workspace_id != actor.workspace_id
                or asset.active_version_id != version.asset_version_id
                or version.index_state != "ready"
            ):
                raise PermissionError("finance demo version is not active")
            paths.append(asset.path)
            active_versions.append(
                ActiveAssetVersion(asset.asset_id, version.asset_version_id)
            )
        decision = evaluate_authorization(
            actor,
            self._repository.list_permission_grants(actor),
            Action.QUERY,
            paths=tuple(paths),
        )
        if decision.state is DecisionState.DENY:
            raise PermissionError("finance demo access denied")
        return tuple(active_versions)

    def _rule_snapshot(self, rule_version: RuleVersion) -> RuleVersionSnapshot:
        expected_fingerprint = self._rules_payload["content_fingerprint"]
        if (
            rule_version.source_type != _SOURCE_TYPE
            or rule_version.content_fingerprint != expected_fingerprint
            or rule_version.version_label != self._rules_payload["version_label"]
        ):
            raise ValueError("rule version does not match controlled demo fixture")
        return RuleVersionSnapshot(
            rule_set_id=rule_version.rule_set_id,
            rule_version_id=rule_version.rule_version_id,
            version_label=rule_version.version_label,
            source_type=RuleSourceType.DEMO_FIXTURE,
            content_fingerprint=rule_version.content_fingerprint,
            disclaimer=self._rules_payload["disclaimer"],
            requirements=_selected_rule_requirements(self._rules_payload),
        )

    def _index_declared_facts(
        self,
        actor: TrustedActorContext,
        asset_versions: tuple[AssetVersion, ...],
    ) -> tuple[InMemorySearchIndex, tuple[MaterialFact, ...], set[str]]:
        parser = DemoDocumentParser(self._source_root)
        index = InMemorySearchIndex(scorer=lambda _question, _chunk: 1.0)
        chunks = []
        facts = []
        parsed_mime_types: set[str] = set()
        for version in asset_versions:
            declared_asset = self._declared_assets.get(version.source_path)
            if declared_asset is None:
                raise ValueError("asset is not declared by the finance demo manifest")
            source_path = self._declared_source_path(declared_asset)
            actual_fingerprint = "sha256:" + hashlib.sha256(
                source_path.read_bytes()
            ).hexdigest()
            if not hmac.compare_digest(
                version.content_fingerprint,
                actual_fingerprint,
            ):
                raise ValueError("finance demo source content fingerprint mismatches version")
            mime_type = _mime_type_for(declared_asset.relative_path)
            parsed_chunks = parser.parse(
                IngestionRequest(
                    tenant_id=actor.workspace_id,
                    target_version=ActiveAssetVersion(
                        version.asset_id,
                        version.asset_version_id,
                    ),
                    source_ref=declared_asset.relative_path,
                    content_fingerprint=version.content_fingerprint,
                    mime_type=mime_type,
                    size_bytes=source_path.stat().st_size,
                )
            )
            chunks.extend(parsed_chunks)
            facts.extend(
                MaterialFact(
                    material_key=declared_asset.material_key,
                    chunk=chunk,
                )
                for chunk in parsed_chunks
            )
            parsed_mime_types.add(mime_type)
        index.rebuild(chunks)
        return index, tuple(facts), parsed_mime_types

    def _declared_source_path(self, declared_asset: _DeclaredAsset) -> Path:
        source_path = (self._source_root / declared_asset.relative_path).resolve()
        try:
            source_path.relative_to(self._source_root)
        except ValueError as error:
            raise ValueError("finance demo source path escapes controlled root") from error
        if not source_path.is_file():
            raise ValueError("finance demo declared source does not exist")
        return source_path


class _FixedMatchingScope(ControlPlanePort):
    def __init__(
        self,
        *,
        context: PermissionContext,
        active_versions: tuple[ActiveAssetVersion, ...],
        rule_version: RuleVersionSnapshot,
    ) -> None:
        self._context = context
        self._active_versions = active_versions
        self._rule_version = rule_version

    def resolve_material_matching_scope(
        self,
        context: PermissionContext,
    ) -> MaterialMatchingScope:
        if context != self._context:
            raise PermissionError("untrusted finance demo context")
        return MaterialMatchingScope(
            tenant_id=context.tenant_id,
            allowed_active_versions=self._active_versions,
            denied_asset_ids=frozenset(),
            rule_version=self._rule_version,
        )


class _IndexedFacts:
    def __init__(
        self,
        *,
        index: InMemorySearchIndex,
        facts: tuple[MaterialFact, ...],
    ) -> None:
        self._index = index
        self._facts_by_chunk_id = {
            fact.chunk.chunk_id: fact for fact in facts
        }

    def search(
        self,
        *,
        retrieval_filter: RetrievalFilter,
        limit: int,
    ) -> Sequence[MaterialFactHit]:
        hits = self._index.search(
            question="controlled-finance-demo-material-facts",
            retrieval_filter=retrieval_filter,
            limit=limit,
        )
        return tuple(
            MaterialFactHit(
                fact=self._facts_by_chunk_id[hit.chunk.chunk_id],
                score=hit.score,
            )
            for hit in hits
        )


def _load_import_manifest(
    path: Path,
) -> dict[str, _DeclaredAsset]:
    payload = _read_json(path)
    if payload.get("source_type") != _SOURCE_TYPE or payload.get("scenario") != _SCENARIO:
        raise ValueError("finance demo import manifest is not a controlled fixture")
    assets = payload.get("assets")
    if set(payload) != {"source_type", "scenario", "assets"} or not isinstance(assets, list):
        raise ValueError("finance demo import manifest is incomplete")
    declared_assets = {
        entry["relative_path"]: _DeclaredAsset(
            relative_path=entry["relative_path"],
            material_key=entry["material_key"],
        )
        for entry in assets
        if isinstance(entry, dict)
        and set(entry) == {"relative_path", "material_key"}
        and isinstance(entry["relative_path"], str)
        and isinstance(entry["material_key"], str)
    }
    if len(declared_assets) != len(assets) or not declared_assets:
        raise ValueError("finance demo asset declarations are invalid")
    return declared_assets


def _load_rules_fixture(path: Path) -> dict[str, object]:
    payload = _read_json(path)
    fingerprint = payload.get("content_fingerprint")
    canonical_payload = {
        key: value for key, value in payload.items() if key != "content_fingerprint"
    }
    expected_fingerprint = "sha256:" + hashlib.sha256(
        json.dumps(
            canonical_payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    if (
        payload.get("source_type") != _SOURCE_TYPE
        or payload.get("scenario") != _SCENARIO
        or fingerprint != expected_fingerprint
        or not isinstance(payload.get("version_label"), str)
        or not isinstance(payload.get("disclaimer"), str)
    ):
        raise ValueError("finance demo rules fixture is invalid")
    _selected_rule_requirements(payload)
    return payload


def _selected_rule_requirements(
    rules_payload: Mapping[str, object],
) -> tuple[MaterialRequirement, ...]:
    selected_rule_id = rules_payload.get("assessment_rule_id")
    rules = rules_payload.get("rules")
    if not isinstance(selected_rule_id, str) or not isinstance(rules, list):
        raise ValueError("finance demo assessment rule is invalid")
    selected_rules = [
        rule
        for rule in rules
        if isinstance(rule, dict) and rule.get("rule_id") == selected_rule_id
    ]
    if len(selected_rules) != 1:
        raise ValueError("finance demo assessment rule is invalid")
    requirements = selected_rules[0].get("requirements")
    if not isinstance(requirements, list):
        raise ValueError("finance demo rule requirements are invalid")
    parsed_requirements = tuple(
        MaterialRequirement(
            rule_id=entry["rule_id"],
            material_key=entry["material_key"],
            label=entry["label"],
        )
        for entry in requirements
        if isinstance(entry, dict)
        and set(entry) == {"rule_id", "material_key", "label"}
        and all(isinstance(entry[key], str) and entry[key] for key in entry)
    )
    if len(parsed_requirements) != len(requirements) or not parsed_requirements:
        raise ValueError("finance demo rule requirements are invalid")
    return parsed_requirements


def _read_json(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("finance demo fixture must be a JSON object")
    return payload


def _mime_type_for(relative_path: str) -> str:
    if relative_path.endswith(".pdf"):
        return PDF_MIME_TYPE
    if relative_path.endswith(".docx"):
        return DOCX_MIME_TYPE
    raise ValueError("finance demo manifest permits PDF/DOCX only")
