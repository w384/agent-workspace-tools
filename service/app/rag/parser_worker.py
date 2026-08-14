from dataclasses import dataclass
from typing import Protocol, Sequence

from service.app.rag.contracts import Chunk
from service.app.rag.ingestion import IngestionRequest


PDF_MIME_TYPE = "application/pdf"
DOCX_MIME_TYPE = (
    "application/vnd.openxmlformats-officedocument."
    "wordprocessingml.document"
)
FROZEN_DEMO_MIME_TYPES = frozenset(
    {PDF_MIME_TYPE, DOCX_MIME_TYPE}
)
FROZEN_DEMO_MAX_SOURCE_BYTES = 2 * 1024 * 1024


@dataclass(frozen=True, slots=True)
class ParserExecutionPolicy:
    allowed_mime_types: frozenset[str]
    max_source_bytes: int
    timeout_seconds: int
    memory_limit_mb: int
    cpu_time_seconds: int
    network_access: bool = False
    source_read_only: bool = True


@dataclass(frozen=True, slots=True)
class ParserJob:
    request: IngestionRequest
    policy: ParserExecutionPolicy


class ParserSandboxRunner(Protocol):
    """Runner port; its implementation must provide OS isolation."""

    def run(self, job: ParserJob) -> Sequence[Chunk]: ...


class PolicyEnforcedParserWorker:
    """Validate policy before delegating; this is not an OS sandbox."""

    def __init__(
        self,
        *,
        policy: ParserExecutionPolicy,
        runner: ParserSandboxRunner,
    ) -> None:
        _validate_policy(policy)
        self._policy = policy
        self._runner = runner

    def parse(
        self,
        request: IngestionRequest,
    ) -> tuple[Chunk, ...]:
        if request.mime_type not in self._policy.allowed_mime_types:
            raise ValueError("source MIME type is not allowed")
        if (
            request.size_bytes < 0
            or request.size_bytes
            > self._policy.max_source_bytes
        ):
            raise ValueError("source size exceeds parser policy")

        return tuple(
            self._runner.run(
                ParserJob(
                    request=request,
                    policy=self._policy,
                )
            )
        )


def _validate_policy(policy: ParserExecutionPolicy) -> None:
    if policy.network_access or not policy.source_read_only:
        raise ValueError("parser policy is not isolated")
    if not policy.allowed_mime_types:
        raise ValueError("parser policy must allow a fixed format")
    if any(
        not mime_type or not mime_type.strip()
        for mime_type in policy.allowed_mime_types
    ):
        raise ValueError("parser MIME types must not be empty")
    if not policy.allowed_mime_types.issubset(
        FROZEN_DEMO_MIME_TYPES
    ):
        raise ValueError("parser MIME policy exceeds frozen formats")
    if (
        policy.max_source_bytes <= 0
        or policy.timeout_seconds <= 0
        or policy.memory_limit_mb <= 0
        or policy.cpu_time_seconds <= 0
    ):
        raise ValueError("parser resource limits must be positive")
    if (
        policy.max_source_bytes
        > FROZEN_DEMO_MAX_SOURCE_BYTES
    ):
        raise ValueError("parser size policy exceeds frozen limit")

