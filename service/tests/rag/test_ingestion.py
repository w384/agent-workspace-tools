from dataclasses import FrozenInstanceError
import importlib

import pytest

from service.app.rag.contracts import (
    ActiveAssetVersion,
    Chunk,
)
from service.app.rag.index import InMemorySearchIndex


def _load_ingestion_module():
    try:
        return importlib.import_module(
            "service.app.rag.ingestion"
        )
    except ModuleNotFoundError as error:
        pytest.fail(
            f"RAG ingestion boundary is not implemented: {error}"
        )


def test_success_indexes_and_reports_ready_before_activation():
    """Activating before READY must change the shared event order and fail."""
    ingestion = _load_ingestion_module()
    active_v1 = ActiveAssetVersion(
        asset_id="asset-stable",
        asset_version_id="version-v1",
    )
    target_v2 = ActiveAssetVersion(
        asset_id="asset-stable",
        asset_version_id="version-v2",
    )
    request = ingestion.IngestionRequest(
        tenant_id="tenant-demo",
        target_version=target_v2,
        source_ref="control-plane://asset-stable/version-v2",
        content_fingerprint="sha256:fixed-v2",
        mime_type="application/pdf",
        size_bytes=1024,
    )
    with pytest.raises(FrozenInstanceError):
        request.source_ref = "untrusted-replacement"

    events = [("control_plane", "QUEUED", "version-v1")]

    class ControlPlaneStub:
        def __init__(self):
            self.active_version = active_v1

        def report_status(self, request, status):
            assert request.target_version == target_v2
            events.append(
                (
                    "status",
                    status.value,
                    self.active_version.asset_version_id,
                )
            )

        def activate_version(self, request):
            events.append(
                (
                    "activate",
                    request.target_version.asset_version_id,
                    self.active_version.asset_version_id,
                )
            )
            self.active_version = request.target_version
            return True

    class ParserWorkerStub:
        def __init__(self, control_plane):
            self._control_plane = control_plane

        def parse(self, request):
            events.append(
                (
                    "parser",
                    request.target_version.asset_version_id,
                    self._control_plane.active_version.asset_version_id,
                )
            )
            return (
                Chunk(
                    tenant_id=request.tenant_id,
                    asset_id=request.target_version.asset_id,
                    asset_version_id=(
                        request.target_version.asset_version_id
                    ),
                    chunk_id="chunk-v2-page-1",
                    ordinal=0,
                    text="fixed parsed evidence",
                    page_number=1,
                    paragraph_index=None,
                    parser_version="parser-v1",
                    embedding_version="embedding-v1",
                    index_version="index-v1",
                ),
            )

    class EventingIndexWriter:
        def __init__(self, control_plane):
            self._control_plane = control_plane
            self._replica = InMemorySearchIndex(
                scorer=lambda _question, _chunk: 1.0
            )

        def replace_version(
            self,
            *,
            tenant_id,
            active_version,
            chunks,
        ):
            events.append(
                (
                    "index_replace",
                    active_version.asset_version_id,
                    self._control_plane.active_version.asset_version_id,
                )
            )
            self._replica.replace_version(
                tenant_id=tenant_id,
                active_version=active_version,
                chunks=chunks,
            )

    control_plane = ControlPlaneStub()
    result = ingestion.IngestionService(
        parser_worker=ParserWorkerStub(control_plane),
        index_writer=EventingIndexWriter(control_plane),
        status_reporter=control_plane,
        control_plane=control_plane,
    ).process(request)

    assert events == [
        ("control_plane", "QUEUED", "version-v1"),
        ("status", "PARSING", "version-v1"),
        ("parser", "version-v2", "version-v1"),
        ("index_replace", "version-v2", "version-v1"),
        ("status", "INDEXED", "version-v1"),
        ("status", "READY", "version-v1"),
        ("activate", "version-v2", "version-v1"),
    ]
    assert control_plane.active_version == target_v2
    assert result.status == ingestion.IngestionStatus.READY
    assert result.chunk_count == 1
    assert result.activated is True


@pytest.mark.parametrize(
    ("failure_stage", "expected_code", "expected_index_calls"),
    [
        ("parser", "PARSER_FAILED", 0),
        ("index", "INDEX_FAILED", 1),
    ],
)
def test_failure_reports_safe_code_and_preserves_old_active(
    failure_stage,
    expected_code,
    expected_index_calls,
):
    """Parser and index failures must not activate or leak the exception."""
    ingestion = _load_ingestion_module()
    active_v1 = ActiveAssetVersion(
        asset_id="asset-stable",
        asset_version_id="version-v1",
    )
    target_v2 = ActiveAssetVersion(
        asset_id="asset-stable",
        asset_version_id="version-v2",
    )
    request = ingestion.IngestionRequest(
        tenant_id="tenant-demo",
        target_version=target_v2,
        source_ref="control-plane://asset-stable/version-v2",
        content_fingerprint="sha256:fixed-v2",
        mime_type="application/pdf",
        size_bytes=1024,
    )
    secret_path = r"D:\private\DENIED-PATH-SENTINEL.pdf"
    secret_text = "DENIED-TEXT-SENTINEL"
    exception = RuntimeError(f"{secret_path}: {secret_text}")
    events = []

    class ControlPlaneStub:
        def __init__(self):
            self.active_version = active_v1
            self.activate_calls = 0

        def report_status(self, _request, status):
            events.append(
                (
                    "status",
                    status.value,
                    self.active_version.asset_version_id,
                )
            )

        def report_failure(self, _request, failure_code):
            events.append(
                (
                    "status",
                    "FAILED",
                    failure_code.value,
                    self.active_version.asset_version_id,
                )
            )

        def activate_version(self, _request):
            self.activate_calls += 1
            self.active_version = target_v2
            return True

    class ParserWorkerStub:
        def __init__(self, control_plane):
            self._control_plane = control_plane

        def parse(self, _request):
            events.append(
                (
                    "parser",
                    self._control_plane.active_version.asset_version_id,
                )
            )
            if failure_stage == "parser":
                raise exception
            return (
                Chunk(
                    tenant_id="tenant-demo",
                    asset_id="asset-stable",
                    asset_version_id="version-v2",
                    chunk_id="chunk-v2",
                    ordinal=0,
                    text="safe parsed evidence",
                    page_number=1,
                    paragraph_index=None,
                    parser_version="parser-v1",
                    embedding_version="embedding-v1",
                    index_version="index-v1",
                ),
            )

    class IndexWriterStub:
        def __init__(self, control_plane):
            self._control_plane = control_plane
            self.call_count = 0

        def replace_version(self, **_kwargs):
            self.call_count += 1
            events.append(
                (
                    "index",
                    self._control_plane.active_version.asset_version_id,
                )
            )
            if failure_stage == "index":
                raise exception

    control_plane = ControlPlaneStub()
    index_writer = IndexWriterStub(control_plane)
    result = ingestion.IngestionService(
        parser_worker=ParserWorkerStub(control_plane),
        index_writer=index_writer,
        status_reporter=control_plane,
        control_plane=control_plane,
    ).process(request)

    expected_events = [
        ("status", "PARSING", "version-v1"),
        ("parser", "version-v1"),
    ]
    if failure_stage == "index":
        expected_events.append(("index", "version-v1"))
    expected_events.append(
        ("status", "FAILED", expected_code, "version-v1")
    )
    assert events == expected_events
    assert index_writer.call_count == expected_index_calls
    assert control_plane.activate_calls == 0
    assert control_plane.active_version == active_v1
    assert result.status == ingestion.IngestionStatus.FAILED
    assert result.activated is False
    assert result.failure_code.value == expected_code

    safe_output = repr((result, events))
    assert "DENIED-PATH-SENTINEL" not in safe_output
    assert "DENIED-TEXT-SENTINEL" not in safe_output


def test_empty_parsed_chunk_tuple_fails_as_parser_error():
    ingestion = _load_ingestion_module()
    active_v1 = ActiveAssetVersion(
        asset_id="asset-stable",
        asset_version_id="version-v1",
    )
    target_v2 = ActiveAssetVersion(
        asset_id="asset-stable",
        asset_version_id="version-v2",
    )
    request = ingestion.IngestionRequest(
        tenant_id="tenant-demo",
        target_version=target_v2,
        source_ref="control-plane://asset-stable/version-v2",
        content_fingerprint="sha256:fixed-v2",
        mime_type="application/pdf",
        size_bytes=1024,
    )
    events = []

    class ControlPlaneStub:
        def __init__(self):
            self.active_version = active_v1
            self.activate_calls = 0

        def report_status(self, _request, status):
            events.append(
                (
                    "status",
                    status.value,
                    self.active_version.asset_version_id,
                )
            )

        def report_failure(self, _request, failure_code):
            events.append(
                (
                    "status",
                    "FAILED",
                    failure_code.value,
                    self.active_version.asset_version_id,
                )
            )

        def activate_version(self, _request):
            self.activate_calls += 1
            self.active_version = target_v2
            return True

    class ParserWorkerStub:
        def parse(self, _request):
            events.append(("parser", "empty"))
            return ()

    class IndexWriterStub:
        def __init__(self):
            self.call_count = 0

        def replace_version(self, **_kwargs):
            self.call_count += 1

    control_plane = ControlPlaneStub()
    index_writer = IndexWriterStub()
    result = ingestion.IngestionService(
        parser_worker=ParserWorkerStub(),
        index_writer=index_writer,
        status_reporter=control_plane,
        control_plane=control_plane,
    ).process(request)

    assert events == [
        ("status", "PARSING", "version-v1"),
        ("parser", "empty"),
        ("status", "FAILED", "PARSER_FAILED", "version-v1"),
    ]
    assert index_writer.call_count == 0
    assert control_plane.activate_calls == 0
    assert control_plane.active_version == active_v1
    assert result.status == ingestion.IngestionStatus.FAILED
    assert result.failure_code == (
        ingestion.IngestionFailureCode.PARSER_FAILED
    )
    assert result.chunk_count == 0
    assert result.activated is False

