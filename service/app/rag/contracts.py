from dataclasses import dataclass
from enum import StrEnum


def _require_non_empty(value: str, field_name: str) -> None:
    if not value or not value.strip():
        raise ValueError(f"{field_name} must not be empty")


class AnswerStatus(StrEnum):
    ANSWERED = "ANSWERED"
    DENIED = "DENIED"
    REFUSED = "REFUSED"


class CitationPathKind(StrEnum):
    CURRENT = "CURRENT"
    HISTORICAL = "HISTORICAL"


@dataclass(frozen=True, slots=True)
class PermissionContext:
    """Typed identity created from an authenticated BFF session."""

    tenant_id: str
    principal_id: str
    group_ids: tuple[str, ...]
    session_id: str
    request_id: str

    def __post_init__(self) -> None:
        for field_name in (
            "tenant_id",
            "principal_id",
            "session_id",
            "request_id",
        ):
            _require_non_empty(
                getattr(self, field_name),
                field_name,
            )


@dataclass(frozen=True, slots=True)
class ActiveAssetVersion:
    asset_id: str
    asset_version_id: str


@dataclass(frozen=True, slots=True)
class RetrievalScope:
    """Authoritative effective scope returned by the control plane."""

    tenant_id: str
    allowed_active_versions: tuple[ActiveAssetVersion, ...]
    denied_asset_ids: frozenset[str]


@dataclass(frozen=True, slots=True)
class RetrievalFilter:
    """Server-built filter that every search adapter must apply."""

    tenant_id: str
    allowed_active_versions: tuple[ActiveAssetVersion, ...]
    denied_asset_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class Chunk:
    tenant_id: str
    asset_id: str
    asset_version_id: str
    chunk_id: str
    ordinal: int
    text: str
    page_number: int | None
    paragraph_index: int | None
    parser_version: str
    embedding_version: str
    index_version: str


@dataclass(frozen=True, slots=True)
class SearchHit:
    chunk: Chunk
    score: float


@dataclass(frozen=True, slots=True)
class AssetReference:
    """Read-only path projection resolved by the control plane."""

    asset_id: str
    asset_version_id: str
    current_path: str
    version_path: str


@dataclass(frozen=True, slots=True)
class Citation:
    asset_id: str
    asset_version_id: str
    chunk_id: str
    page_number: int | None
    paragraph_index: int | None
    display_path: str
    path_kind: CitationPathKind
    current_path: str
    version_path: str


@dataclass(frozen=True, slots=True)
class RetrievalAuditEvent:
    """Safe metadata only: never store chunk IDs, text, or paths."""

    request_id: str
    status: AnswerStatus
    authorized_candidate_count: int
    evidence_count: int


@dataclass(frozen=True, slots=True)
class AnswerResult:
    status: AnswerStatus
    answer: str | None
    reason: str | None
    citations: tuple[Citation, ...]
    retrieved_count: int
    llm_invoked: bool

