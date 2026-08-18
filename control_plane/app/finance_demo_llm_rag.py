"""Composite finance-demo bridge: real LLM query (path B) + deterministic assess (path A).

Path A ("资料预评估报告") reuses FinanceDemoRagPort.assess_versions unchanged.
Path B ("LLM 知识库问答") reuses DemoRagPort.query, which runs the RAG
RetrievalService with a real LLM answer generator over the controlled
pre-assessment samples, so different authorized assets/questions get real
answers instead of a hard-coded stub.

The shared in-memory search index is built once from the import-manifest
declared controlled samples (same source_root as the assess path), so both
paths operate over the same controlled evidence set.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from control_plane.app.demo_rag import DemoRagPort
from control_plane.app.domain import AssetVersion, RuleVersion, TrustedActorContext
from control_plane.app.finance_demo_rag import FinanceDemoRagPort
from control_plane.app.ports import AssessmentResult
from control_plane.app.repository import ControlPlaneRepository

from service.app.rag.contracts import ActiveAssetVersion, LLMConfigurationError
from service.app.rag.demo_document_parser import DemoDocumentParser
from service.app.rag.index import InMemorySearchIndex
from service.app.rag.ingestion import IngestionRequest
from service.app.rag.llm import build_llm_answer_generator
from service.app.rag.parser_worker import DOCX_MIME_TYPE, PDF_MIME_TYPE

_SCENARIO = "finance_profile_matching"
_SOURCE_TYPE = "demo_fixture"


@dataclass(frozen=True, slots=True)
class _DeclaredAsset:
    relative_path: str
    material_key: str


class FinanceDemoLlmRagPort:
    """Composite port: real-LLM path-B query + deterministic path-A assess.

    enqueue_version stays denied for arbitrary uploads (unchanged safety).
    """

    def __init__(
        self,
        *,
        repository: ControlPlaneRepository,
        source_root: Path,
        import_manifest_path: Path,
        rules_path: Path,
        workspace_id: str,
        answer_generator: object | None = None,
        explanation_port: object | None = None,
    ) -> None:
        self._repository = repository
        self._source_root = source_root.resolve()
        self._workspace_id = workspace_id
        self._declared_assets = _load_import_manifest(import_manifest_path)

        self._assess_port = FinanceDemoRagPort(
            repository=repository,
            source_root=source_root,
            import_manifest_path=import_manifest_path,
            rules_path=rules_path,
            explanation_port=explanation_port,
        )

        search_index = InMemorySearchIndex(scorer=lambda _question, _chunk: 1.0)
        self._index_declared_samples(search_index)

        if answer_generator is None:
            answer_generator = _build_default_answer_generator()
        self._query_port = DemoRagPort(
            repository=repository,
            search_index=search_index,
            minimum_evidence_score=0.75,
            answer_generator=answer_generator,
        )

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
        return self._query_port.query(actor, question, asset_id)

    def assess_versions(
        self,
        actor: TrustedActorContext,
        asset_versions: tuple[AssetVersion, ...],
        rule_version: RuleVersion,
        query_subject: str,
    ) -> AssessmentResult:
        return self._assess_port.assess_versions(
            actor, asset_versions, rule_version, query_subject
        )

    def _index_declared_samples(self, index: InMemorySearchIndex) -> None:
        parser = DemoDocumentParser(self._source_root)
        for declared in self._declared_assets.values():
            source_path = self._declared_source_path(declared)
            mime_type = _mime_type_for(declared.relative_path)
            asset = self._repository.find_asset_by_path(
                self._workspace_id, declared.relative_path
            )
            if asset is None or asset.active_version_id is None:
                # Unseeded assets are intentionally absent from the search
                # replica; querying them resolves to DENIED via get_asset.
                continue
            asset_id = asset.asset_id
            asset_version_id = asset.active_version_id
            chunks = parser.parse(
                IngestionRequest(
                    tenant_id=self._workspace_id,
                    target_version=ActiveAssetVersion(
                        asset_id,
                        asset_version_id,
                    ),
                    source_ref=declared.relative_path,
                    content_fingerprint="demo-index",
                    mime_type=mime_type,
                    size_bytes=source_path.stat().st_size,
                )
            )
            index.replace_version(
                tenant_id=self._workspace_id,
                active_version=ActiveAssetVersion(asset_id, asset_version_id),
                chunks=chunks,
            )

    def _declared_source_path(self, declared: _DeclaredAsset) -> Path:
        source_path = (self._source_root / declared.relative_path).resolve()
        try:
            source_path.relative_to(self._source_root)
        except ValueError as error:
            raise ValueError("finance demo source path escapes controlled root") from error
        if not source_path.is_file():
            raise ValueError("finance demo declared source does not exist")
        return source_path


def _load_import_manifest(path: Path) -> dict[str, _DeclaredAsset]:
    import json

    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("source_type") != _SOURCE_TYPE or payload.get("scenario") != _SCENARIO:
        raise ValueError("finance demo import manifest is not a controlled fixture")
    assets = payload.get("assets")
    if set(payload) != {"source_type", "scenario", "assets"} or not isinstance(assets, list):
        raise ValueError("finance demo import manifest is incomplete")
    declared = {
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
    if len(declared) != len(assets) or not declared:
        raise ValueError("finance demo asset declarations are invalid")
    return declared


def _mime_type_for(relative_path: str) -> str:
    if relative_path.endswith(".pdf"):
        return PDF_MIME_TYPE
    if relative_path.endswith(".docx"):
        return DOCX_MIME_TYPE
    raise ValueError("finance demo manifest permits PDF/DOCX only")


def _build_default_answer_generator() -> object | None:
    try:
        return build_llm_answer_generator(os.environ)
    except LLMConfigurationError:
        return None
