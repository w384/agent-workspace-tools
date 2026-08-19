from dataclasses import dataclass
from typing import Mapping
from typing import Protocol

from .domain import AssetVersion, RuleVersion, TrustedActorContext


@dataclass(frozen=True, slots=True)
class FilePlanPreview:
    impact_summary: str
    executor_plan_id: str
    executor_plan_hash: str


@dataclass(frozen=True, slots=True)
class ExecutionResult:
    status: str
    operation_id: str
    failure_code: str | None = None


@dataclass(frozen=True, slots=True)
class UploadResult:
    path: str
    name: str
    size_bytes: int
    content_fingerprint: str

    def __post_init__(self) -> None:
        if not self.path or not self.name:
            raise ValueError("upload result path and name must be non-empty")
        if isinstance(self.size_bytes, bool) or self.size_bytes < 0:
            raise ValueError("size_bytes must be a non-negative integer")
        algorithm, separator, digest = self.content_fingerprint.partition(":")
        if algorithm != "sha256" or separator != ":" or not digest:
            raise ValueError("content_fingerprint must use sha256:<digest> format")


@dataclass(frozen=True, slots=True)
class AssessmentResult:
    match_score: int
    result_level: str
    missing_materials: tuple[str, ...]
    citations: tuple[Mapping[str, object], ...]
    bank_label: str | None = None
    candidate_banks: tuple[Mapping[str, object], ...] = ()


class FileExecutorPort(Protocol):
    def upload(
        self,
        actor: TrustedActorContext,
        directory: str,
        file_name: str,
        content: bytes,
        request_id: str,
    ) -> UploadResult: ...

    def create_plan(
        self,
        actor: TrustedActorContext,
        normalized_operations: tuple[Mapping[str, object], ...],
        asset_snapshots: tuple[Mapping[str, str], ...],
        acl_snapshot: Mapping[str, object],
        policy_version: str,
        expires_at: str,
        idempotency_key: str,
    ) -> FilePlanPreview: ...

    def confirm_and_execute(
        self,
        actor: TrustedActorContext,
        control_plan_id: str,
        executor_plan_id: str,
        executor_plan_hash: str,
        expected_plan_hash: str,
        asset_snapshots: tuple[Mapping[str, str], ...],
        acl_snapshot: Mapping[str, object],
        decision: Mapping[str, object],
        confirmation_evidence: Mapping[str, object],
        approval_evidence: Mapping[str, object] | None,
        idempotency_key: str,
    ) -> ExecutionResult: ...


class RagPort(Protocol):
    def enqueue_version(
        self,
        actor: TrustedActorContext,
        asset_version: AssetVersion,
        request_id: str,
    ) -> None: ...

    def query(
        self,
        actor: TrustedActorContext,
        question: str,
        asset_id: str,
    ) -> Mapping[str, object]: ...

    def assess_versions(
        self,
        actor: TrustedActorContext,
        asset_versions: tuple[AssetVersion, ...],
        rule_version: RuleVersion,
        query_subject: str,
    ) -> AssessmentResult: ...
