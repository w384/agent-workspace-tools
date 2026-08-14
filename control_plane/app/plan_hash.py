import hashlib
import hmac
import json
from dataclasses import dataclass
from typing import Mapping


@dataclass(frozen=True, slots=True)
class PlanHashSnapshot:
    asset_id: str
    asset_version_id: str
    content_fingerprint: str


@dataclass(frozen=True, slots=True)
class PlanHashInput:
    contract_version: str
    plan_id: str
    workspace_id: str
    actor_id: str
    decision_state: str
    decision_id: str
    policy_version: str
    context_version: str
    normalized_operations: tuple[Mapping[str, object], ...]
    asset_snapshots: tuple[PlanHashSnapshot, ...]
    expires_at: str


def compute_canonical_plan_hash(value: PlanHashInput) -> str:
    payload = {
        "contract_version": value.contract_version,
        "plan_id": value.plan_id,
        "workspace_id": value.workspace_id,
        "actor_id": value.actor_id,
        "decision_state": value.decision_state,
        "decision_id": value.decision_id,
        "policy_version": value.policy_version,
        "context_version": value.context_version,
        "normalized_operations": value.normalized_operations,
        "asset_snapshots": [
            {
                "asset_id": snapshot.asset_id,
                "asset_version_id": snapshot.asset_version_id,
                "content_fingerprint": snapshot.content_fingerprint,
            }
            for snapshot in sorted(value.asset_snapshots, key=lambda item: item.asset_id)
        ],
        "expires_at": value.expires_at,
    }
    canonical = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return f"sha256:{hashlib.sha256(canonical).hexdigest()}"


def plan_hash_matches(expected: str, actual: str) -> bool:
    return hmac.compare_digest(expected, actual)

