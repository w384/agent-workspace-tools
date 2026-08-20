from dataclasses import replace
from typing import Protocol
from uuid import uuid4

from .domain import (
    Approval,
    AssessmentReport,
    Asset,
    AssetVersion,
    AuditEvent,
    ChunkMetadata,
    Confirmation,
    ExecutionJob,
    PermissionGrant,
    Plan,
    RuleSet,
    RuleVersion,
    TrustedActorContext,
)


class ControlPlaneRepository(Protocol):
    def add_permission_grant(self, grant: PermissionGrant) -> None: ...

    def list_permission_grants(self, actor: TrustedActorContext) -> list[PermissionGrant]: ...

    def get_or_create_asset(
        self, workspace_id: str, path: str, name: str, created_by: str
    ) -> Asset: ...

    def get_asset(self, asset_id: str) -> Asset: ...

    def list_assets(self, workspace_id: str) -> list[Asset]: ...

    def move_asset_path(self, asset_id: str, path: str) -> Asset: ...

    def remove_asset(self, asset_id: str) -> Asset | None: ...

    def find_asset_by_path(self, workspace_id: str, path: str) -> Asset | None: ...

    def revoke_permission_grants(self, workspace_id: str, path_prefix: str) -> int: ...

    def get_asset_version(self, asset_version_id: str) -> AssetVersion: ...

    def create_asset_version(
        self, asset_id: str, content_fingerprint: str, source_path: str
    ) -> AssetVersion: ...

    def transition_asset_version(
        self, asset_version_id: str, index_state: str, failure_code: str | None = None
    ) -> AssetVersion: ...

    def activate_asset_version(self, asset_version_id: str) -> Asset | None: ...

    def append_audit_event(self, event: AuditEvent) -> None: ...

    def find_asset_version_creation_event(
        self, asset_version_id: str
    ) -> AuditEvent | None: ...

    def create_plan(self, plan: Plan) -> Plan: ...

    def get_plan(self, plan_id: str) -> Plan: ...

    def update_plan(self, plan: Plan) -> Plan: ...

    def add_confirmation(self, confirmation: Confirmation) -> Confirmation: ...

    def find_confirmation_by_plan(self, plan_id: str) -> Confirmation | None: ...

    def add_approval(self, approval: Approval) -> Approval: ...

    def get_approval(self, approval_id: str) -> Approval: ...

    def find_approval_by_plan(self, plan_id: str) -> Approval | None: ...

    def list_pending_approvals(self, actor: TrustedActorContext) -> list[Approval]: ...

    def update_approval(self, approval: Approval) -> Approval: ...

    def add_execution_job(self, job: ExecutionJob) -> ExecutionJob: ...

    def update_execution_job(self, job: ExecutionJob) -> ExecutionJob: ...

    def find_execution_job(
        self, plan_id: str, plan_hash: str, idempotency_key: str
    ) -> ExecutionJob | None: ...

    def create_rule_set(self, rule_set: RuleSet) -> RuleSet: ...

    def get_rule_set(self, rule_set_id: str) -> RuleSet: ...

    def create_rule_version(self, rule_version: RuleVersion) -> RuleVersion: ...

    def get_rule_version(self, rule_version_id: str) -> RuleVersion: ...

    def create_assessment_report(self, report: AssessmentReport) -> AssessmentReport: ...


class InMemoryControlPlaneRepository:
    """Small test repository; PostgreSQL remains the production authority."""

    def __init__(self) -> None:
        self._assets: dict[str, Asset] = {}
        self._asset_versions: dict[str, AssetVersion] = {}
        self.permission_grants: dict[str, PermissionGrant] = {}
        self.plans: dict[str, Plan] = {}
        self.confirmations: dict[str, Confirmation] = {}
        self.approvals: dict[str, Approval] = {}
        self.execution_jobs: dict[str, ExecutionJob] = {}
        self.rule_sets: dict[str, RuleSet] = {}
        self.rule_versions: dict[str, RuleVersion] = {}
        self.assessment_reports: dict[str, AssessmentReport] = {}
        self._audit_events: dict[str, AuditEvent] = {}
        self.chunk_metadata: dict[str, ChunkMetadata] = {}

    def add_permission_grant(self, grant: PermissionGrant) -> None:
        self.permission_grants[grant.grant_id] = grant

    def list_permission_grants(self, actor: TrustedActorContext) -> list[PermissionGrant]:
        return [
            grant
            for grant in self.permission_grants.values()
            if grant.workspace_id == actor.workspace_id
            and grant.context_version == actor.context_version
            and (
                (grant.principal_type.value == "user" and grant.principal_id == actor.actor_id)
                or (grant.principal_type.value == "group" and grant.principal_id in actor.group_ids)
                or (grant.principal_type.value == "role" and grant.principal_id in actor.role_ids)
            )
        ]

    def revoke_permission_grants(self, workspace_id: str, path_prefix: str) -> int:
        """Drop every grant whose path matches the exact revoked path."""
        revoked_ids = [
            grant_id
            for grant_id, grant in self.permission_grants.items()
            if grant.workspace_id == workspace_id
            and grant.path_prefix == path_prefix
        ]
        for grant_id in revoked_ids:
            self.permission_grants.pop(grant_id, None)
        return len(revoked_ids)

    def get_or_create_asset(
        self, workspace_id: str, path: str, name: str, created_by: str
    ) -> Asset:
        for asset in self._assets.values():
            if asset.workspace_id == workspace_id and asset.path == path:
                return asset
        asset = Asset(
            asset_id=str(uuid4()),
            workspace_id=workspace_id,
            path=path,
            name=name,
            created_by=created_by,
            path_history=(path,),
        )
        self._assets[asset.asset_id] = asset
        return asset

    def get_asset(self, asset_id: str) -> Asset:
        return self._assets[asset_id]

    def list_assets(self, workspace_id: str) -> list[Asset]:
        return [
            asset
            for asset in self._assets.values()
            if asset.workspace_id == workspace_id
        ]

    def move_asset_path(self, asset_id: str, path: str) -> Asset:
        asset_before = self._assets[asset_id]
        if asset_before.path == path:
            return asset_before
        path_history = asset_before.path_history
        if asset_before.path not in path_history:
            path_history += (asset_before.path,)
        asset = replace(
            asset_before,
            path=path,
            name=path.rsplit("/", maxsplit=1)[-1],
            path_history=path_history,
        )
        self._assets[asset_id] = asset
        return asset

    def remove_asset(self, asset_id: str) -> Asset | None:
        """Remove an asset together with all of its versions."""
        asset = self._assets.pop(asset_id, None)
        if asset is None:
            return None
        for version_id in [
            version_id
            for version_id, version in self._asset_versions.items()
            if version.asset_id == asset_id
        ]:
            self._asset_versions.pop(version_id, None)
        return asset

    def get_asset_version(self, asset_version_id: str) -> AssetVersion:
        return self._asset_versions[asset_version_id]

    def find_asset_by_path(self, workspace_id: str, path: str) -> Asset | None:
        for asset in self._assets.values():
            if asset.workspace_id == workspace_id and asset.path == path:
                return asset
        return None

    def create_asset_version(
        self, asset_id: str, content_fingerprint: str, source_path: str
    ) -> AssetVersion:
        versions = [
            version for version in self._asset_versions.values() if version.asset_id == asset_id
        ]
        version = AssetVersion(
            asset_version_id=str(uuid4()),
            asset_id=asset_id,
            version_number=max((item.version_number for item in versions), default=0) + 1,
            content_fingerprint=content_fingerprint,
            source_path=source_path,
        )
        self._asset_versions[version.asset_version_id] = version
        return version

    def transition_asset_version(
        self, asset_version_id: str, index_state: str, failure_code: str | None = None
    ) -> AssetVersion:
        version_before = self._asset_versions[asset_version_id]
        transitions = {
            "queued": {"parsing", "failed"},
            "parsing": {"indexed", "failed"},
            "indexed": {"ready", "failed"},
            "ready": set(),
            "failed": set(),
        }
        if index_state not in transitions:
            raise ValueError("invalid index state")
        if index_state not in transitions[version_before.index_state]:
            raise ValueError("invalid index state transition")
        if index_state == "failed" and not failure_code:
            raise ValueError("failed version requires a failure code")
        version = replace(
            version_before,
            index_state=index_state,
            failure_code=failure_code if index_state == "failed" else None,
        )
        self._asset_versions[asset_version_id] = version
        return version

    def activate_asset_version(self, asset_version_id: str) -> Asset | None:
        version = self._asset_versions[asset_version_id]
        if version.index_state != "ready":
            return None
        asset = replace(self._assets[version.asset_id], active_version_id=version.asset_version_id)
        self._assets[asset.asset_id] = asset
        return asset

    def append_audit_event(self, event: AuditEvent) -> None:
        self._audit_events[event.event_id] = event

    def find_asset_version_creation_event(
        self, asset_version_id: str
    ) -> AuditEvent | None:
        for event in self._audit_events.values():
            if (
                event.event_type == "asset_version_created"
                and event.details.get("asset_version_id") == asset_version_id
            ):
                return event
        return None

    def list_audit_events(self) -> list[AuditEvent]:
        return list(self._audit_events.values())

    def create_plan(self, plan: Plan) -> Plan:
        self.plans[plan.plan_id] = plan
        return plan

    def get_plan(self, plan_id: str) -> Plan:
        return self.plans[plan_id]

    def update_plan(self, plan: Plan) -> Plan:
        self.plans[plan.plan_id] = plan
        return plan

    def add_confirmation(self, confirmation: Confirmation) -> Confirmation:
        if confirmation.plan_id in {
            existing.plan_id for existing in self.confirmations.values()
        }:
            raise ValueError("confirmation already exists")
        self.confirmations[confirmation.confirmation_id] = confirmation
        return confirmation

    def find_confirmation_by_plan(self, plan_id: str) -> Confirmation | None:
        for confirmation in self.confirmations.values():
            if confirmation.plan_id == plan_id:
                return confirmation
        return None

    def add_approval(self, approval: Approval) -> Approval:
        if approval.plan_id in {existing.plan_id for existing in self.approvals.values()}:
            raise ValueError("approval already exists")
        self.approvals[approval.approval_id] = approval
        return approval

    def get_approval(self, approval_id: str) -> Approval:
        return self.approvals[approval_id]

    def find_approval_by_plan(self, plan_id: str) -> Approval | None:
        for approval in self.approvals.values():
            if approval.plan_id == plan_id:
                return approval
        return None

    def list_pending_approvals(self, actor: TrustedActorContext) -> list[Approval]:
        return [
            approval
            for approval in self.approvals.values()
            if self.plans[approval.plan_id].workspace_id == actor.workspace_id
            and approval.decision == "pending"
            and approval.requester_id != actor.actor_id
            and approval.required_role_id in actor.role_ids
        ]

    def update_approval(self, approval: Approval) -> Approval:
        self.approvals[approval.approval_id] = approval
        return approval

    def add_execution_job(self, job: ExecutionJob) -> ExecutionJob:
        existing = self.find_execution_job(job.plan_id, job.plan_hash, job.idempotency_key)
        if existing is not None:
            return existing
        self.execution_jobs[job.job_id] = job
        return job

    def update_execution_job(self, job: ExecutionJob) -> ExecutionJob:
        self.execution_jobs[job.job_id] = job
        return job

    def find_execution_job(
        self, plan_id: str, plan_hash: str, idempotency_key: str
    ) -> ExecutionJob | None:
        for job in self.execution_jobs.values():
            if (
                job.plan_id == plan_id
                and job.plan_hash == plan_hash
                and job.idempotency_key == idempotency_key
            ):
                return job
        return None

    def create_rule_set(self, rule_set: RuleSet) -> RuleSet:
        self.rule_sets[rule_set.rule_set_id] = rule_set
        return rule_set

    def get_rule_set(self, rule_set_id: str) -> RuleSet:
        return self.rule_sets[rule_set_id]

    def create_rule_version(self, rule_version: RuleVersion) -> RuleVersion:
        self.rule_versions[rule_version.rule_version_id] = rule_version
        return rule_version

    def get_rule_version(self, rule_version_id: str) -> RuleVersion:
        return self.rule_versions[rule_version_id]

    def create_assessment_report(self, report: AssessmentReport) -> AssessmentReport:
        self.assessment_reports[report.report_id] = report
        return report
