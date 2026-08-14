from dataclasses import dataclass, field
from enum import Enum
from typing import Mapping


class Action(str, Enum):
    UPLOAD = "upload"
    CREATE_FOLDER = "create_folder"
    MOVE_RENAME = "move_rename"
    TRASH = "trash"
    QUERY = "query"


class DecisionState(str, Enum):
    DIRECT = "DIRECT"
    SELF_CONFIRM = "SELF_CONFIRM"
    APPROVAL_REQUIRED = "APPROVAL_REQUIRED"
    DENY = "DENY"


class PrincipalType(str, Enum):
    USER = "user"
    GROUP = "group"
    ROLE = "role"


class GrantEffect(str, Enum):
    ALLOW = "allow"
    DENY = "deny"


@dataclass(frozen=True, slots=True)
class TrustedActorContext:
    actor_id: str
    workspace_id: str
    context_version: str
    session_id: str
    request_id: str
    run_id: str
    role_ids: frozenset[str]
    group_ids: frozenset[str] = frozenset()

    def __post_init__(self) -> None:
        for field_name in ("session_id", "request_id", "run_id"):
            if not getattr(self, field_name):
                raise ValueError(f"{field_name} must be non-empty")
        if not self.role_ids:
            raise ValueError("role_ids must be non-empty")


@dataclass(frozen=True, slots=True)
class PermissionGrant:
    grant_id: str
    workspace_id: str
    context_version: str
    principal_type: PrincipalType
    principal_id: str
    action: Action
    path_prefix: str
    effect: GrantEffect = GrantEffect.ALLOW


@dataclass(frozen=True, slots=True)
class AuthorizationDecision:
    state: DecisionState
    reason: str


@dataclass(frozen=True, slots=True)
class Asset:
    asset_id: str
    workspace_id: str
    path: str
    name: str
    created_by: str
    active_version_id: str | None = None
    path_history: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class AssetVersion:
    asset_version_id: str
    asset_id: str
    version_number: int
    content_fingerprint: str
    source_path: str
    index_state: str = "queued"
    failure_code: str | None = None


@dataclass(frozen=True, slots=True)
class Plan:
    plan_id: str
    workspace_id: str
    created_by: str
    state: str
    decision_state: DecisionState
    decision_id: str
    policy_version: str
    context_version: str
    normalized_operations: tuple[Mapping[str, object], ...]
    asset_snapshots: tuple[Mapping[str, str], ...]
    plan_hash: str
    executor_plan_id: str
    executor_plan_hash: str
    acl_snapshot: Mapping[str, object]
    expires_at: str


@dataclass(frozen=True, slots=True)
class Confirmation:
    confirmation_id: str
    plan_id: str
    confirmed_by: str
    decision: str
    expected_plan_hash: str


@dataclass(frozen=True, slots=True)
class Approval:
    approval_id: str
    plan_id: str
    requester_id: str
    required_role_id: str
    approver_id: str | None = None
    decision: str = "pending"


@dataclass(frozen=True, slots=True)
class ExecutionJob:
    job_id: str
    plan_id: str
    plan_hash: str
    state: str
    idempotency_key: str


@dataclass(frozen=True, slots=True)
class RuleSet:
    rule_set_id: str
    scenario: str
    name: str
    status: str


@dataclass(frozen=True, slots=True)
class RuleVersion:
    rule_version_id: str
    rule_set_id: str
    source_type: str
    version_label: str
    content_fingerprint: str
    created_at: str
    redacted_rule_summary: str = ""


@dataclass(frozen=True, slots=True)
class AssessmentReport:
    report_id: str
    scenario: str
    actor_id: str
    workspace_id: str
    asset_versions: tuple[str, ...]
    rule_version_id: str
    match_score: int
    result_level: str
    missing_materials: tuple[str, ...]
    citations: tuple[Mapping[str, object], ...]
    rule_version_evidence: Mapping[str, object]
    disclaimer: str
    disclaimer_version: str
    query_subject: str
    created_at: str
    audit_event_id: str


@dataclass(frozen=True, slots=True)
class AuditEvent:
    event_id: str
    event_type: str
    actor_id: str
    request_id: str
    run_id: str = ""
    details: Mapping[str, object] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ChunkMetadata:
    chunk_id: str
    asset_version_id: str
    chunk_index: int
    qdrant_point_id: str
