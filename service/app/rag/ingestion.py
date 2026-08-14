from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol, Sequence

from service.app.rag.contracts import (
    ActiveAssetVersion,
    Chunk,
)


class IngestionStatus(StrEnum):
    QUEUED = "QUEUED"
    PARSING = "PARSING"
    INDEXED = "INDEXED"
    READY = "READY"
    FAILED = "FAILED"


class IngestionFailureCode(StrEnum):
    PARSER_FAILED = "PARSER_FAILED"
    INDEX_FAILED = "INDEX_FAILED"


@dataclass(frozen=True, slots=True)
class IngestionRequest:
    """Opaque source reference for a control-plane-owned version."""

    tenant_id: str
    target_version: ActiveAssetVersion
    source_ref: str
    content_fingerprint: str
    mime_type: str
    size_bytes: int


@dataclass(frozen=True, slots=True)
class IngestionResult:
    status: IngestionStatus
    chunk_count: int
    activated: bool
    failure_code: IngestionFailureCode | None


class ParserWorker(Protocol):
    """Port implemented by an isolated, resource-limited worker."""

    def parse(
        self,
        request: IngestionRequest,
    ) -> Sequence[Chunk]: ...


class IndexWriter(Protocol):
    def replace_version(
        self,
        *,
        tenant_id: str,
        active_version: ActiveAssetVersion,
        chunks: Sequence[Chunk],
    ) -> None: ...


class StatusReporter(Protocol):
    def report_status(
        self,
        request: IngestionRequest,
        status: IngestionStatus,
    ) -> None: ...

    def report_failure(
        self,
        request: IngestionRequest,
        failure_code: IngestionFailureCode,
    ) -> None: ...


class ControlPlaneActivator(Protocol):
    def activate_version(
        self,
        request: IngestionRequest,
    ) -> bool: ...


class IngestionService:
    """Orchestrate a version without storing AssetVersion authority."""

    def __init__(
        self,
        *,
        parser_worker: ParserWorker,
        index_writer: IndexWriter,
        status_reporter: StatusReporter,
        control_plane: ControlPlaneActivator,
    ) -> None:
        self._parser_worker = parser_worker
        self._index_writer = index_writer
        self._status_reporter = status_reporter
        self._control_plane = control_plane

    def process(
        self,
        request: IngestionRequest,
    ) -> IngestionResult:
        self._status_reporter.report_status(
            request,
            IngestionStatus.PARSING,
        )
        try:
            chunks = tuple(self._parser_worker.parse(request))
            _validate_chunks(request, chunks)
        except Exception:
            return self._report_failure(
                request,
                IngestionFailureCode.PARSER_FAILED,
                chunk_count=0,
            )

        try:
            self._index_writer.replace_version(
                tenant_id=request.tenant_id,
                active_version=request.target_version,
                chunks=chunks,
            )
        except Exception:
            return self._report_failure(
                request,
                IngestionFailureCode.INDEX_FAILED,
                chunk_count=len(chunks),
            )

        self._status_reporter.report_status(
            request,
            IngestionStatus.INDEXED,
        )
        self._status_reporter.report_status(
            request,
            IngestionStatus.READY,
        )
        activated = self._control_plane.activate_version(
            request
        )
        return IngestionResult(
            status=IngestionStatus.READY,
            chunk_count=len(chunks),
            activated=activated,
            failure_code=None,
        )

    def _report_failure(
        self,
        request: IngestionRequest,
        failure_code: IngestionFailureCode,
        *,
        chunk_count: int,
    ) -> IngestionResult:
        self._status_reporter.report_failure(
            request,
            failure_code,
        )
        return IngestionResult(
            status=IngestionStatus.FAILED,
            chunk_count=chunk_count,
            activated=False,
            failure_code=failure_code,
        )


def _validate_chunks(
    request: IngestionRequest,
    chunks: Sequence[Chunk],
) -> None:
    if not chunks:
        raise ValueError("parser returned no chunks")
    if any(
        chunk.tenant_id != request.tenant_id
        or chunk.asset_id != request.target_version.asset_id
        or chunk.asset_version_id
        != request.target_version.asset_version_id
        for chunk in chunks
    ):
        raise ValueError(
            "parsed chunks do not match the ingestion target"
        )

