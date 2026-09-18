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

import hashlib
import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from control_plane.app.demo_rag import DemoRagPort
from control_plane.app.domain import AssetVersion, RuleVersion, TrustedActorContext
from control_plane.app.finance_demo_rag import FinanceDemoRagPort
from control_plane.app.ports import AssessmentResult
from control_plane.app.repository import ControlPlaneRepository

from service.app.rag.contracts import (
    ActiveAssetVersion,
    LLMConfigurationError,
    PermissionContext,
)
from service.app.rag.demo_document_parser import DemoDocumentParser
from service.app.rag.finance_matching import MaterialFact
from service.app.rag.index import InMemorySearchIndex
from service.app.rag.ingestion import IngestionRequest
from service.app.rag.llm import build_llm_answer_generator
from service.app.rag.parser_worker import DOCX_MIME_TYPE, PDF_MIME_TYPE
from service.app.rag.vector_retrieval import make_retrieval_scorer

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
        providers: object | None = None,
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

        # Real vector retrieval: char n-gram cosine scorer ranks chunks by
        # how well they answer the question, instead of the previous
        # constant 1.0 (every chunk equally "matched"). The demo evidence
        # threshold is 0.0 so the top ranked chunks become the evidence;
        # the "evidence insufficient" REFUSED path still triggers whenever
        # retrieval returns nothing (no index / no authorized chunks).
        self._search_index = InMemorySearchIndex(scorer=make_retrieval_scorer())
        self._index_declared_samples(self._search_index)

        if providers is not None:
            self._providers = providers
            answer_generator = providers.answer_generator
        else:
            self._providers = None
            if answer_generator is None:
                answer_generator = _build_default_answer_generator()
        self._query_port = DemoRagPort(
            repository=repository,
            search_index=self._search_index,
            minimum_evidence_score=0.0,
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

    def ingest_uploaded_version(
        self,
        actor: TrustedActorContext,
        asset_version: AssetVersion,
        content: bytes,
        request_id: str,
    ) -> int:
        """Build the in-memory vector index for one real uploaded document.

        Verifies the recorded SHA-256 fingerprint against the actual payload,
        parses the bytes (PDF/DOCX) via the demo parser, atomically replaces
        the search-index slice, walks the version state machine
        queued -> parsing -> indexed -> ready and activates the version. The
        upload itself is authorized by the BFF before this is called; the
        uploader is then granted QUERY on the exact file path.
        """
        expected = "sha256:" + hashlib.sha256(content).hexdigest()
        if asset_version.content_fingerprint != expected:
            raise ValueError("uploaded content fingerprint mismatch")
        parser = DemoDocumentParser(self._source_root)
        request = IngestionRequest(
            tenant_id=self._workspace_id,
            target_version=ActiveAssetVersion(
                asset_version.asset_id,
                asset_version.asset_version_id,
            ),
            source_ref=asset_version.source_path,
            content_fingerprint=asset_version.content_fingerprint,
            mime_type=_mime_type_for(asset_version.source_path),
            size_bytes=len(content),
        )
        chunks = parser.parse_bytes(request, content)
        if not chunks:
            raise ValueError("uploaded document parsed to no chunks")
        self._search_index.replace_version(
            tenant_id=self._workspace_id,
            active_version=ActiveAssetVersion(
                asset_version.asset_id,
                asset_version.asset_version_id,
            ),
            chunks=chunks,
        )
        self._repository.transition_asset_version(
            asset_version.asset_version_id, "parsing"
        )
        self._repository.transition_asset_version(
            asset_version.asset_version_id, "indexed"
        )
        self._repository.transition_asset_version(
            asset_version.asset_version_id, "ready"
        )
        self._repository.activate_asset_version(asset_version.asset_version_id)
        return len(chunks)

    def delete_uploaded_version(
        self,
        actor: TrustedActorContext,
        asset,
        request_id: str,
    ) -> int:
        """Drop one uploaded asset from the search replica and revoke its QUERY grant.

        Called only after the BFF has verified the caller owns the asset (so
        the next demo can re-upload the same file name). The asset record
        itself is removed by the BFF via repository.remove_asset afterwards.
        """
        removed = 0
        if asset.active_version_id is not None:
            removed = self._search_index.delete_version(
                tenant_id=self._workspace_id,
                active_version=ActiveAssetVersion(
                    asset.asset_id,
                    asset.active_version_id,
                ),
            )
        self._repository.revoke_permission_grants(
            self._workspace_id, asset.path
        )
        return removed

    def set_provider(self, provider_id: str, api_key: str | None = None) -> None:
        """Switch the path-B answer provider at runtime."""
        if self._providers is None:
            raise RuntimeError("provider switching is not wired for this bridge")
        self._providers.switch(provider_id, api_key=api_key)
        self._query_port.set_answer_generator(self._providers.answer_generator)

    def current_provider(self) -> str:
        if self._providers is None:
            raise RuntimeError("provider switching is not wired for this bridge")
        return self._providers.current

    def cloud_key_configured(self) -> bool:
        """Whether a cloud (DeepSeek) key is available (env or runtime)."""
        if self._providers is None:
            return False
        return bool(self._providers.cloud_key_configured)

    def clear_cloud_key(self) -> None:
        """Drop the runtime-typed cloud key on logout (BFF delegate).

        The registry falls back to local when the cloud provider can no
        longer be used; the path-B answer generator is rebuilt accordingly.
        """
        if self._providers is None:
            return
        self._providers.clear_cloud_key()
        self._query_port.set_answer_generator(self._providers.answer_generator)

    def provider_descriptors(self) -> list[object]:
        if self._providers is None:
            raise RuntimeError("provider switching is not wired for this bridge")
        return self._providers.descriptors()

    def query(
        self,
        actor: TrustedActorContext,
        question: str,
        asset_id: str,
    ) -> Mapping[str, object]:
        return self._query_port.query(actor, question, asset_id)

    def query_multi(
        self,
        actor: TrustedActorContext,
        question: str,
        asset_ids: tuple[str, ...],
    ) -> Mapping[str, object]:
        return self._query_port.query_multi(actor, question, asset_ids)

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

    def assess_real_materials(
        self,
        actor: TrustedActorContext,
        rule_version: RuleVersion,
        query_subject: str,
        materials: tuple[tuple[str, str, bytes], ...],
    ) -> AssessmentResult:
        """Assess user-dragged real PDF/DOCX materials by material category.

        The user brings their own bytes, so authorization is just the
        authenticated session (no asset / no grant needed). The deterministic
        rules fixture is matched the same way as the controlled samples, with
        explicit material_key per file; citations carry synthetic
        "real-material-N" ids so the report renders identically.
        """
        if not materials:
            raise ValueError("real-material assessment requires at least one file")
        parser = DemoDocumentParser(self._source_root)
        index = InMemorySearchIndex(scorer=lambda _question, _chunk: 1.0)
        chunks: list[object] = []
        facts = []
        active_versions: list[ActiveAssetVersion] = []
        for item_index, (material_key, file_name, content) in enumerate(materials):
            version = ActiveAssetVersion(
                f"real-material-{item_index + 1}", f"real-material-{item_index + 1}"
            )
            active_versions.append(version)
            parsed_chunks = parser.parse_bytes(
                IngestionRequest(
                    tenant_id=self._workspace_id,
                    target_version=version,
                    source_ref=file_name,
                    content_fingerprint="sha256:" + hashlib.sha256(content).hexdigest(),
                    mime_type=_mime_type_for(file_name),
                    size_bytes=len(content),
                ),
                content,
            )
            chunks.extend(parsed_chunks)
            facts.extend(
                MaterialFact(material_key=material_key, chunk=chunk)
                for chunk in parsed_chunks
            )
        index.rebuild(chunks)
        rule_snapshot = self._assess_port._rule_snapshot(rule_version)
        context = PermissionContext(
            tenant_id=actor.workspace_id,
            principal_id=actor.actor_id,
            group_ids=tuple(sorted(actor.group_ids)),
            session_id=actor.session_id,
            request_id=actor.request_id,
        )
        result, hits = self._assess_port._match_with_explanation(
            context=context,
            facts=tuple(facts),
            index=index,
            active_versions=tuple(active_versions),
            rule_snapshot=rule_snapshot,
            include_explanation=False,
        )
        if result.status is None:
            raise PermissionError("finance demo matching scope denied")
        candidate_banks = self._assess_port._candidate_bank_entries(
            rule_version=rule_version,
            hits=hits,
        )
        return AssessmentResult(
            match_score=result.match_score,
            result_level=result.status.value,
            missing_materials=tuple(
                requirement.label for requirement in result.missing_materials
            ),
            bank_label=result.bank_label,
            candidate_banks=candidate_banks,
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

    def resolve_controlled_asset(
        self,
        file_name: str,
    ) -> object | None:
        """Resolve an import-manifest controlled file name to its asset.

        The BFF translates a selected sample file into the asset record;
        authorization still happens later via evaluate_authorization on the
        asset path (unchanged gates). Returns None for unknown names.
        """
        relative_path = self._relative_path_for_name(file_name)
        if relative_path is None:
            return None
        return self._repository.find_asset_by_path(
            self._workspace_id, relative_path
        )

    def _relative_path_for_name(self, file_name: str) -> str | None:
        for declared in self._declared_assets.values():
            path = declared.relative_path
            if path.rsplit("/", maxsplit=1)[-1] == file_name:
                return path
        return None

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
