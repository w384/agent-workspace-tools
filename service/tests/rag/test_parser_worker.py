import importlib

import pytest

from service.app.rag.contracts import (
    ActiveAssetVersion,
    Chunk,
)
from service.app.rag.ingestion import IngestionRequest


PDF_MIME = "application/pdf"
DOCX_MIME = (
    "application/vnd.openxmlformats-officedocument."
    "wordprocessingml.document"
)


def _load_parser_module():
    try:
        return importlib.import_module(
            "service.app.rag.parser_worker"
        )
    except ModuleNotFoundError as error:
        pytest.fail(
            f"Parser worker boundary is not implemented: {error}"
        )


def _request(*, mime_type: str, size_bytes: int) -> IngestionRequest:
    return IngestionRequest(
        tenant_id="tenant-demo",
        target_version=ActiveAssetVersion(
            asset_id="asset-stable",
            asset_version_id="version-v2",
        ),
        source_ref="opaque-control-plane-ref://version-v2",
        content_fingerprint="sha256:fixed-v2",
        mime_type=mime_type,
        size_bytes=size_bytes,
    )


def _policy(parser_module, **overrides):
    values = {
        "allowed_mime_types": frozenset(
            {PDF_MIME, DOCX_MIME}
        ),
        "max_source_bytes": 2 * 1024 * 1024,
        "timeout_seconds": 15,
        "memory_limit_mb": 256,
        "cpu_time_seconds": 5,
        "network_access": False,
        "source_read_only": True,
    }
    values.update(overrides)
    return parser_module.ParserExecutionPolicy(**values)


@pytest.mark.parametrize("mime_type", [PDF_MIME, DOCX_MIME])
def test_allowed_fixed_formats_pass_full_policy_to_runner(mime_type):
    """The adapter must pass an opaque source ref and every hard limit."""
    parser_module = _load_parser_module()
    request = _request(mime_type=mime_type, size_bytes=1024)
    policy = _policy(parser_module)

    class RunnerStub:
        def __init__(self):
            self.jobs = []

        def run(self, job):
            self.jobs.append(job)
            return (
                Chunk(
                    tenant_id=job.request.tenant_id,
                    asset_id=job.request.target_version.asset_id,
                    asset_version_id=(
                        job.request.target_version.asset_version_id
                    ),
                    chunk_id="fixed-sample-chunk",
                    ordinal=0,
                    text="fixed sample output",
                    page_number=(1 if mime_type == PDF_MIME else None),
                    paragraph_index=(
                        0 if mime_type == DOCX_MIME else None
                    ),
                    parser_version="parser-v1",
                    embedding_version="embedding-v1",
                    index_version="index-v1",
                ),
            )

    runner = RunnerStub()
    worker = parser_module.PolicyEnforcedParserWorker(
        policy=policy,
        runner=runner,
    )
    chunks = worker.parse(request)

    assert len(runner.jobs) == 1
    job = runner.jobs[0]
    assert job.request is request
    assert job.request.source_ref == (
        "opaque-control-plane-ref://version-v2"
    )
    assert job.policy == policy
    assert job.policy.allowed_mime_types == frozenset(
        {PDF_MIME, DOCX_MIME}
    )
    assert job.policy.max_source_bytes == 2 * 1024 * 1024
    assert job.policy.timeout_seconds == 15
    assert job.policy.memory_limit_mb == 256
    assert job.policy.cpu_time_seconds == 5
    assert job.policy.network_access is False
    assert job.policy.source_read_only is True
    assert [chunk.chunk_id for chunk in chunks] == [
        "fixed-sample-chunk"
    ]


@pytest.mark.parametrize(
    ("mime_type", "size_bytes"),
    [
        ("image/png", 1024),
        (PDF_MIME, 2 * 1024 * 1024 + 1),
    ],
)
def test_unsupported_or_oversized_source_is_rejected_before_runner(
    mime_type,
    size_bytes,
):
    parser_module = _load_parser_module()

    class RunnerStub:
        def __init__(self):
            self.call_count = 0

        def run(self, _job):
            self.call_count += 1
            return ()

    runner = RunnerStub()
    worker = parser_module.PolicyEnforcedParserWorker(
        policy=_policy(parser_module),
        runner=runner,
    )

    with pytest.raises(ValueError):
        worker.parse(
            _request(
                mime_type=mime_type,
                size_bytes=size_bytes,
            )
        )

    assert runner.call_count == 0


@pytest.mark.parametrize(
    "unsafe_override",
    [
        {"network_access": True},
        {"source_read_only": False},
    ],
)
def test_unsafe_policy_is_rejected_when_adapter_is_constructed(
    unsafe_override,
):
    parser_module = _load_parser_module()

    class RunnerStub:
        def run(self, _job):
            return ()

    with pytest.raises(ValueError):
        parser_module.PolicyEnforcedParserWorker(
            policy=_policy(parser_module, **unsafe_override),
            runner=RunnerStub(),
        )


@pytest.mark.parametrize(
    "frozen_boundary_override",
    [
        {
            "allowed_mime_types": frozenset(
                {PDF_MIME, DOCX_MIME, "image/png"}
            )
        },
        {"max_source_bytes": 2 * 1024 * 1024 + 1},
    ],
    ids=("unsupported-mime-superset", "over-2-mib-limit"),
)
def test_policy_cannot_relax_frozen_demo_boundaries(
    frozen_boundary_override,
):
    parser_module = _load_parser_module()

    class RunnerStub:
        def __init__(self):
            self.call_count = 0

        def run(self, _job):
            self.call_count += 1
            return ()

    runner = RunnerStub()
    with pytest.raises(ValueError):
        parser_module.PolicyEnforcedParserWorker(
            policy=_policy(
                parser_module,
                **frozen_boundary_override,
            ),
            runner=runner,
        )

    assert runner.call_count == 0


def test_policy_may_use_a_frozen_format_subset_and_tighter_limit():
    parser_module = _load_parser_module()

    class RunnerStub:
        def run(self, _job):
            return ()

    worker = parser_module.PolicyEnforcedParserWorker(
        policy=_policy(
            parser_module,
            allowed_mime_types=frozenset({PDF_MIME}),
            max_source_bytes=1024,
        ),
        runner=RunnerStub(),
    )

    assert worker.parse(
        _request(mime_type=PDF_MIME, size_bytes=1024)
    ) == ()

