from collections.abc import Mapping
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from uuid import uuid4

from .domain import (
    Action,
    AssessmentReport,
    Asset,
    AssetVersion,
    AuditEvent,
    AuthorizationDecision,
    Approval,
    Confirmation,
    DecisionState,
    ExecutionJob,
    Plan,
    RuleSet,
    RuleVersion,
    TrustedActorContext,
)
from .plan_hash import PlanHashInput, PlanHashSnapshot, compute_canonical_plan_hash, plan_hash_matches
from .policy import evaluate_authorization
from .ports import FileExecutorPort, RagPort
from .repository import ControlPlaneRepository


class UploadDeniedError(Exception):
    pass


class ExecutorResultMismatchError(Exception):
    pass


class ExecutorUploadFailedError(Exception):
    pass


class UploadTargetExistsError(Exception):
    pass


class RagEnqueueFailedError(Exception):
    pass


class InvalidIndexTransitionError(Exception):
    pass


class AssetVersionNotFoundError(Exception):
    pass


class PlanDeniedError(Exception):
    pass


class PlanNotFoundError(Exception):
    pass


class PlanHashMismatchError(Exception):
    pass


class PlanStateError(Exception):
    pass


class ActorNotPlanCreatorError(Exception):
    pass


class ApprovalForbiddenError(Exception):
    pass


class ApprovalNotFoundError(Exception):
    pass


class ExecutorAclDeniedError(Exception):
    pass


class PlanRevalidationError(Exception):
    def __init__(self, reason: str, denied: bool = False) -> None:
        super().__init__(reason)
        self.reason = reason
        self.denied = denied


class ExecutorExecutionFailedError(Exception):
    pass


class RuleSourceNotAllowedError(Exception):
    pass


class RuleVersionNotFoundError(Exception):
    pass


class AssessmentDeniedError(Exception):
    pass


class AssessmentFailedError(Exception):
    pass


@dataclass(frozen=True, slots=True)
class UploadOutcome:
    decision: AuthorizationDecision
    asset: Asset
    asset_version: AssetVersion
    audit_event_id: str


@dataclass(frozen=True, slots=True)
class PlanOutcome:
    decision: AuthorizationDecision
    plan: Plan
    impact_summary: str


@dataclass(frozen=True, slots=True)
class ConfirmationOutcome:
    plan: Plan
    confirmation: Confirmation
    approval: Approval | None
    execution_job: ExecutionJob | None


@dataclass(frozen=True, slots=True)
class ApprovalOutcome:
    approval: Approval
    execution_job: ExecutionJob | None


@dataclass(frozen=True, slots=True)
class RuleVersionOutcome:
    rule_set: RuleSet
    rule_version: RuleVersion
    audit_event_id: str


@dataclass(frozen=True, slots=True)
class AssessmentOutcome:
    report: AssessmentReport


class ControlPlaneService:
    def __init__(
        self,
        repository: ControlPlaneRepository,
        file_executor: FileExecutorPort,
        rag_port: RagPort,
        approver_role_id: str,
        disclaimer_version: str = "disclaimer-demo-v1",
        disclaimer_text: str = "仅供资料完整度与规则匹配演示参考",
    ) -> None:
        if not approver_role_id.strip():
            raise ValueError("approver_role_id must be non-empty")
        if not disclaimer_version.strip():
            raise ValueError("disclaimer_version must be non-empty")
        if not disclaimer_text.strip():
            raise ValueError("disclaimer_text must be non-empty")
        self._repository = repository
        self._file_executor = file_executor
        self._rag_port = rag_port
        self._approver_role_id = approver_role_id
        self._disclaimer_version = disclaimer_version
        self._disclaimer_text = disclaimer_text

    def upload(
        self,
        actor: TrustedActorContext,
        directory: str,
        file_name: str,
        content: bytes,
    ) -> UploadOutcome:
        final_path = _final_upload_path(directory, file_name)
        overwrite = (
            self._repository.find_asset_by_path(actor.workspace_id, final_path) is not None
        )
        decision = evaluate_authorization(
            actor=actor,
            grants=self._repository.list_permission_grants(actor),
            action=Action.UPLOAD,
            paths=(final_path,),
            overwrite=overwrite,
        )
        if decision.state is not DecisionState.DIRECT:
            self._repository.append_audit_event(
                _audit_event(
                    event_type="upload_denied",
                    actor_id=actor.actor_id,
                    request_id=actor.request_id,
                    run_id=actor.run_id,
                    details={
                        "action": Action.UPLOAD.value,
                        "decision": decision.state.value,
                        "reason": decision.reason,
                    },
                )
            )
            raise UploadDeniedError

        self._repository.append_audit_event(
            _audit_event(
                event_type="upload_authorized",
                actor_id=actor.actor_id,
                request_id=actor.request_id,
                run_id=actor.run_id,
                details={"action": Action.UPLOAD.value, "decision": decision.state.value},
            )
        )
        try:
            executor_result = self._file_executor.upload(
                actor=actor,
                directory=directory,
                file_name=file_name,
                content=content,
                request_id=actor.request_id,
            )
        except FileExistsError as error:
            self._repository.append_audit_event(
                _audit_event(
                    event_type="upload_failed",
                    actor_id=actor.actor_id,
                    request_id=actor.request_id,
                    run_id=actor.run_id,
                    details={
                        "action": Action.UPLOAD.value,
                        "stage": "executor",
                        "reason": "target_exists",
                    },
                )
            )
            raise UploadTargetExistsError from error
        except Exception as error:
            self._repository.append_audit_event(
                _audit_event(
                    event_type="upload_failed",
                    actor_id=actor.actor_id,
                    request_id=actor.request_id,
                    run_id=actor.run_id,
                    details={
                        "action": Action.UPLOAD.value,
                        "stage": "executor",
                        "reason": "executor_error",
                    },
                )
            )
            raise ExecutorUploadFailedError from error
        if executor_result.path != final_path or executor_result.name != file_name:
            raise ExecutorResultMismatchError

        asset = self._repository.get_or_create_asset(
            workspace_id=actor.workspace_id,
            path=executor_result.path,
            name=executor_result.name,
            created_by=actor.actor_id,
        )
        asset_version = self._repository.create_asset_version(
            asset_id=asset.asset_id,
            content_fingerprint=executor_result.content_fingerprint,
            source_path=executor_result.path,
        )
        created_event = _audit_event(
            event_type="asset_version_created",
            actor_id=actor.actor_id,
            request_id=actor.request_id,
            run_id=actor.run_id,
            details={
                "asset_id": asset.asset_id,
                "asset_version_id": asset_version.asset_version_id,
                "version_number": asset_version.version_number,
            },
        )
        self._repository.append_audit_event(created_event)
        try:
            self._rag_port.enqueue_version(actor, asset_version, actor.request_id)
        except Exception as error:
            self.update_index_state(
                asset_version.asset_version_id,
                "failed",
                "index_enqueue_failed",
            )
            self._repository.append_audit_event(
                _audit_event(
                    event_type="rag_enqueue_failed",
                    actor_id=actor.actor_id,
                    request_id=actor.request_id,
                    run_id=actor.run_id,
                    details={
                        "action": Action.UPLOAD.value,
                        "asset_version_id": asset_version.asset_version_id,
                        "stage": "rag",
                        "reason": "enqueue_failed",
                    },
                )
            )
            raise RagEnqueueFailedError from error
        return UploadOutcome(decision, asset, asset_version, created_event.event_id)

    def update_index_state(
        self,
        asset_version_id: str,
        state: str,
        failure_code: str | None,
    ) -> AssetVersion:
        creation_event = self._repository.find_asset_version_creation_event(asset_version_id)
        if creation_event is None:
            raise AssetVersionNotFoundError
        try:
            version = self._repository.transition_asset_version(
                asset_version_id=asset_version_id,
                index_state=state,
                failure_code=failure_code,
            )
        except KeyError as error:
            raise AssetVersionNotFoundError from error
        except ValueError as error:
            raise InvalidIndexTransitionError from error

        self._repository.append_audit_event(
            _audit_event(
                event_type="asset_version_state_changed",
                actor_id=creation_event.actor_id,
                request_id=creation_event.request_id,
                run_id=creation_event.run_id,
                details={"asset_version_id": asset_version_id, "state": state},
            )
        )
        return version

    def create_rule_set_with_version(
        self,
        actor: TrustedActorContext,
        *,
        scenario: str,
        name: str,
        status: str,
        source_type: str,
        version_label: str,
        content_fingerprint: str,
        redacted_rule_summary: str,
    ) -> RuleVersionOutcome:
        if source_type not in {"demo_fixture", "manual_entry"}:
            raise RuleSourceNotAllowedError
        if not redacted_rule_summary.strip():
            raise RuleSourceNotAllowedError
        _require_sha256_fingerprint(content_fingerprint)
        rule_set = self._repository.create_rule_set(
            RuleSet(str(uuid4()), scenario, name, status)
        )
        rule_version = self._repository.create_rule_version(
            RuleVersion(
                rule_version_id=str(uuid4()),
                rule_set_id=rule_set.rule_set_id,
                source_type=source_type,
                version_label=version_label,
                content_fingerprint=content_fingerprint,
                created_at=_utc_now(),
                redacted_rule_summary=redacted_rule_summary,
            )
        )
        event = _audit_event(
            event_type="rule_version_created",
            actor_id=actor.actor_id,
            request_id=actor.request_id,
            run_id=actor.run_id,
            details={
                "scenario": scenario,
                "rule_set_id": rule_set.rule_set_id,
                "rule_version_id": rule_version.rule_version_id,
                "source_type": source_type,
                "version_label": version_label,
            },
        )
        self._repository.append_audit_event(event)
        return RuleVersionOutcome(rule_set, rule_version, event.event_id)

    def create_assessment_report(
        self,
        actor: TrustedActorContext,
        *,
        scenario: str,
        query_subject: str,
        asset_ids: tuple[str, ...],
        rule_version_id: str,
    ) -> AssessmentOutcome:
        try:
            rule_version = self._repository.get_rule_version(rule_version_id)
            rule_set = self._repository.get_rule_set(rule_version.rule_set_id)
        except KeyError as error:
            raise RuleVersionNotFoundError from error
        if rule_set.scenario != scenario or rule_set.status != "active":
            self._append_assessment_denied(
                actor,
                scenario,
                query_subject=query_subject,
                rule_version_id=rule_version_id,
                requested_asset_ids=asset_ids,
            )
            raise AssessmentDeniedError

        asset_versions: list[AssetVersion] = []
        paths: list[str] = []
        for asset_id in asset_ids:
            try:
                asset = self._repository.get_asset(asset_id)
                version = self._repository.get_asset_version(asset.active_version_id)
            except (KeyError, TypeError) as error:
                self._append_assessment_denied(
                    actor,
                    scenario,
                    query_subject=query_subject,
                    rule_version_id=rule_version_id,
                    requested_asset_ids=asset_ids,
                )
                raise AssessmentDeniedError from error
            if (
                asset.workspace_id != actor.workspace_id
                or asset.active_version_id is None
                or version.index_state != "ready"
            ):
                self._append_assessment_denied(
                    actor,
                    scenario,
                    query_subject=query_subject,
                    rule_version_id=rule_version_id,
                    requested_asset_ids=asset_ids,
                )
                raise AssessmentDeniedError
            paths.append(asset.path)
            asset_versions.append(version)

        decision = evaluate_authorization(
            actor=actor,
            grants=self._repository.list_permission_grants(actor),
            action=Action.QUERY,
            paths=tuple(paths),
        )
        if decision.state is DecisionState.DENY:
            self._append_assessment_denied(
                actor,
                scenario,
                query_subject=query_subject,
                rule_version_id=rule_version_id,
                requested_asset_ids=asset_ids,
            )
            raise AssessmentDeniedError

        try:
            result = self._rag_port.assess_versions(
                actor, tuple(asset_versions), rule_version, query_subject
            )
            _validate_assessment_result(
                result.match_score,
                result.result_level,
                result.citations,
                tuple(asset_versions),
                rule_version,
            )
        except AssessmentFailedError:
            self._append_assessment_failed(
                actor,
                scenario,
                rule_version.rule_version_id,
                "invalid_assessment_result",
            )
            raise
        except Exception as error:
            self._append_assessment_failed(
                actor,
                scenario,
                rule_version.rule_version_id,
                "rag_assessment_failed",
            )
            raise AssessmentFailedError from error

        report_id = str(uuid4())
        event_id = str(uuid4())
        asset_version_ids = tuple(version.asset_version_id for version in asset_versions)
        report = AssessmentReport(
            report_id=report_id,
            scenario=scenario,
            actor_id=actor.actor_id,
            workspace_id=actor.workspace_id,
            asset_versions=asset_version_ids,
            rule_version_id=rule_version.rule_version_id,
            match_score=result.match_score,
            result_level=result.result_level,
            missing_materials=tuple(result.missing_materials),
            citations=tuple(_safe_citation(citation) for citation in result.citations),
            rule_version_evidence={
                "rule_version_id": rule_version.rule_version_id,
                "version_label": rule_version.version_label,
                "content_fingerprint": rule_version.content_fingerprint,
                "source_type": rule_version.source_type,
            },
            disclaimer=self._disclaimer_text,
            disclaimer_version=self._disclaimer_version,
            query_subject=query_subject,
            created_at=_utc_now(),
            audit_event_id=event_id,
            bank_label=result.bank_label,
            candidate_banks=result.candidate_banks,
        )
        self._repository.create_assessment_report(report)
        self._repository.append_audit_event(
            AuditEvent(
                event_id=event_id,
                event_type="assessment_report_created",
                actor_id=actor.actor_id,
                request_id=actor.request_id,
                run_id=actor.run_id,
                details={
                    "report_id": report_id,
                    "scenario": scenario,
                    "query_subject": query_subject,
                    "asset_version_ids": list(asset_version_ids),
                    "rule_version_id": rule_version.rule_version_id,
                    "disclaimer_version": self._disclaimer_version,
                    "rule_source_type": rule_version.source_type,
                    "match_score": result.match_score,
                    "result_level": result.result_level,
                    "report_created_at": report.created_at,
                },
            )
        )
        return AssessmentOutcome(report)

    def _append_assessment_denied(
        self,
        actor: TrustedActorContext,
        scenario: str,
        *,
        query_subject: str,
        rule_version_id: str,
        requested_asset_ids: tuple[str, ...],
    ) -> None:
        self._repository.append_audit_event(
            _audit_event(
                event_type="assessment_denied",
                actor_id=actor.actor_id,
                request_id=actor.request_id,
                run_id=actor.run_id,
                details={
                    "scenario": scenario,
                    "decision": DecisionState.DENY.value,
                    "query_subject": query_subject,
                    "rule_version_id": rule_version_id,
                    "requested_asset_ids": list(requested_asset_ids),
                    "retrieved_count": 0,
                    "llm_invoked": False,
                    "citations": [],
                },
            )
        )

    def _append_assessment_failed(
        self,
        actor: TrustedActorContext,
        scenario: str,
        rule_version_id: str,
        reason: str,
    ) -> None:
        self._repository.append_audit_event(
            _audit_event(
                event_type="assessment_failed",
                actor_id=actor.actor_id,
                request_id=actor.request_id,
                run_id=actor.run_id,
                details={
                    "scenario": scenario,
                    "rule_version_id": rule_version_id,
                    "reason": reason,
                },
            )
        )

    def create_plan(
        self,
        actor: TrustedActorContext,
        operations: tuple[dict[str, object], ...],
        expires_at: str,
    ) -> PlanOutcome:
        normalized_operations = tuple(_normalize_operation(operation) for operation in operations)
        paths = tuple(
            path
            for operation in normalized_operations
            for path in _operation_paths(operation)
        )
        action = _operation_action(normalized_operations)
        decision = evaluate_authorization(
            actor=actor,
            grants=self._repository.list_permission_grants(actor),
            action=action,
            paths=paths,
        )
        if decision.state is DecisionState.DENY:
            self._repository.append_audit_event(
                _audit_event(
                    event_type="plan_denied",
                    actor_id=actor.actor_id,
                    request_id=actor.request_id,
                    run_id=actor.run_id,
                    details={
                        "action": action.value,
                        "decision": decision.state.value,
                        "reason": decision.reason,
                    },
                )
            )
            raise PlanDeniedError

        try:
            asset_snapshots = tuple(
                _asset_snapshot(self._repository, actor.workspace_id, operation["source_path"])
                for operation in normalized_operations
            )
        except PlanDeniedError:
            self._repository.append_audit_event(
                _audit_event(
                    event_type="plan_denied",
                    actor_id=actor.actor_id,
                    request_id=actor.request_id,
                    run_id=actor.run_id,
                    details={
                        "action": action.value,
                        "decision": DecisionState.DENY.value,
                        "reason": "asset_snapshot_unavailable",
                    },
                )
            )
            raise
        decision_id = str(uuid4())
        plan_id = str(uuid4())
        policy_version = "policy_2026_08_13"
        acl_snapshot = {
            "decision": decision.state.value,
            "decision_id": decision_id,
            "context_version": actor.context_version,
            "creator_session_id": actor.session_id,
            "creator_run_id": actor.run_id,
            "creator_group_ids": sorted(actor.group_ids),
            "creator_role_ids": sorted(actor.role_ids),
        }
        plan_hash = compute_canonical_plan_hash(
            PlanHashInput(
                contract_version="control-plane-demo-v1",
                plan_id=plan_id,
                workspace_id=actor.workspace_id,
                actor_id=actor.actor_id,
                decision_state=decision.state.value,
                decision_id=decision_id,
                policy_version=policy_version,
                context_version=actor.context_version,
                normalized_operations=normalized_operations,
                asset_snapshots=tuple(
                    PlanHashSnapshot(
                        snapshot["asset_id"],
                        snapshot["asset_version_id"],
                        snapshot["content_fingerprint"],
                    )
                    for snapshot in asset_snapshots
                ),
                expires_at=expires_at,
            )
        )
        preview = self._file_executor.create_plan(
            actor,
            normalized_operations,
            asset_snapshots,
            acl_snapshot,
            policy_version,
            expires_at,
            idempotency_key=f"preview:{plan_id}",
        )
        plan = Plan(
            plan_id=plan_id,
            workspace_id=actor.workspace_id,
            created_by=actor.actor_id,
            state="pending_confirmation",
            decision_state=decision.state,
            decision_id=decision_id,
            policy_version=policy_version,
            context_version=actor.context_version,
            normalized_operations=normalized_operations,
            asset_snapshots=asset_snapshots,
            plan_hash=plan_hash,
            executor_plan_id=preview.executor_plan_id,
            executor_plan_hash=preview.executor_plan_hash,
            acl_snapshot=acl_snapshot,
            expires_at=expires_at,
        )
        self._repository.create_plan(plan)
        self._repository.append_audit_event(
            _audit_event(
                event_type="plan_created",
                actor_id=actor.actor_id,
                request_id=actor.request_id,
                run_id=actor.run_id,
                details={
                    "plan_id": plan.plan_id,
                    "decision": decision.state.value,
                    "action": action.value,
                },
            )
        )
        return PlanOutcome(decision, plan, preview.impact_summary)

    def confirm_plan(
        self,
        actor: TrustedActorContext,
        plan_id: str,
        expected_plan_hash: str,
        idempotency_key: str,
    ) -> ConfirmationOutcome:
        plan = self._get_plan(plan_id)
        if actor.actor_id != plan.created_by:
            raise ActorNotPlanCreatorError
        if not plan_hash_matches(expected_plan_hash, plan.plan_hash):
            raise PlanHashMismatchError
        existing_job = self._repository.find_execution_job(
            plan.plan_id, plan.plan_hash, idempotency_key
        )
        if existing_job is not None:
            return ConfirmationOutcome(
                plan,
                _existing_confirmation(self._repository, plan_id),
                None,
                existing_job,
            )
        existing_confirmation = self._repository.find_confirmation_by_plan(plan.plan_id)
        if (
            existing_confirmation is not None
            and plan.decision_state is DecisionState.APPROVAL_REQUIRED
            and plan.state == "pending_approval"
        ):
            approval = _existing_approval_for_plan(self._repository, plan.plan_id)
            return ConfirmationOutcome(plan, existing_confirmation, approval, None)
        if plan.state != "pending_confirmation":
            raise PlanStateError
        confirmation = self._repository.add_confirmation(
            Confirmation(
                confirmation_id=str(uuid4()),
                plan_id=plan.plan_id,
                confirmed_by=actor.actor_id,
                decision="confirmed",
                expected_plan_hash=expected_plan_hash,
            )
        )
        if plan.decision_state is DecisionState.APPROVAL_REQUIRED:
            updated_plan = self._repository.update_plan(replace(plan, state="pending_approval"))
            approval = self._repository.add_approval(
                Approval(
                    approval_id=str(uuid4()),
                    plan_id=plan.plan_id,
                    requester_id=actor.actor_id,
                    required_role_id=self._approver_role_id,
                )
            )
            self._repository.append_audit_event(
                _audit_event(
                    event_type="approval_requested",
                    actor_id=actor.actor_id,
                    request_id=actor.request_id,
                    run_id=actor.run_id,
                    details={"plan_id": plan.plan_id, "approval_id": approval.approval_id},
                )
            )
            return ConfirmationOutcome(updated_plan, confirmation, approval, None)
        job = self._execute_plan(actor, plan, idempotency_key, confirmation, None)
        return ConfirmationOutcome(self._repository.get_plan(plan.plan_id), confirmation, None, job)

    def list_pending_approvals(self, actor: TrustedActorContext) -> list[Approval]:
        return self._repository.list_pending_approvals(actor)

    def decide_approval(
        self,
        actor: TrustedActorContext,
        approval_id: str,
        decision: str,
        expected_plan_hash: str,
        idempotency_key: str,
    ) -> ApprovalOutcome:
        try:
            approval = self._repository.get_approval(approval_id)
        except KeyError as error:
            raise ApprovalNotFoundError
        except ApprovalNotFoundError:
            raise
        plan = self._get_plan(approval.plan_id)
        if (
            plan.workspace_id != actor.workspace_id
            or approval.requester_id == actor.actor_id
            or approval.required_role_id not in actor.role_ids
        ):
            raise ApprovalForbiddenError
        if not plan_hash_matches(expected_plan_hash, plan.plan_hash):
            raise PlanHashMismatchError
        existing_job = self._repository.find_execution_job(
            plan.plan_id, plan.plan_hash, idempotency_key
        )
        if existing_job is not None:
            return ApprovalOutcome(approval, existing_job)
        if approval.decision != "pending" or plan.state != "pending_approval":
            raise PlanStateError
        if decision == "rejected":
            updated_approval = self._repository.update_approval(
                replace(approval, approver_id=actor.actor_id, decision="rejected")
            )
            self._repository.update_plan(replace(plan, state="rejected"))
            self._repository.append_audit_event(
                _audit_event(
                    event_type="approval_rejected",
                    actor_id=actor.actor_id,
                    request_id=actor.request_id,
                    run_id=actor.run_id,
                    details={"plan_id": plan.plan_id, "approval_id": approval.approval_id},
                )
            )
            return ApprovalOutcome(updated_approval, None)
        if decision != "approved":
            raise PlanStateError
        self._revalidate_before_execution(actor, plan)
        updated_approval = self._repository.update_approval(
            replace(approval, approver_id=actor.actor_id, decision="approved")
        )
        self._repository.append_audit_event(
            _audit_event(
                event_type="approval_approved",
                actor_id=actor.actor_id,
                request_id=actor.request_id,
                run_id=actor.run_id,
                details={"plan_id": plan.plan_id, "approval_id": approval.approval_id},
            )
        )
        self._repository.update_plan(replace(plan, state="approved"))
        confirmation = _existing_confirmation(self._repository, plan.plan_id)
        job = self._execute_plan(actor, plan, idempotency_key, confirmation, updated_approval)
        return ApprovalOutcome(updated_approval, job)

    def _get_plan(self, plan_id: str) -> Plan:
        try:
            return self._repository.get_plan(plan_id)
        except KeyError as error:
            raise PlanNotFoundError from error

    def _execute_plan(
        self,
        actor: TrustedActorContext,
        plan: Plan,
        idempotency_key: str,
        confirmation: Confirmation,
        approval: Approval | None,
    ) -> ExecutionJob:
        existing_job = self._repository.find_execution_job(
            plan.plan_id, plan.plan_hash, idempotency_key
        )
        if existing_job is not None:
            return existing_job
        execution_actor = self._execution_actor(actor, plan)
        self._revalidate_before_execution(actor, plan, execution_actor)
        queued = self._repository.add_execution_job(
            ExecutionJob(
                job_id=str(uuid4()),
                plan_id=plan.plan_id,
                plan_hash=plan.plan_hash,
                state="queued",
                idempotency_key=idempotency_key,
            )
        )
        self._repository.update_plan(replace(plan, state="executing"))
        try:
            result = self._file_executor.confirm_and_execute(
                actor=execution_actor,
                control_plan_id=plan.plan_id,
                executor_plan_id=plan.executor_plan_id,
                executor_plan_hash=plan.executor_plan_hash,
                expected_plan_hash=plan.plan_hash,
                asset_snapshots=plan.asset_snapshots,
                acl_snapshot=plan.acl_snapshot,
                decision={
                    "state": plan.decision_state.value,
                    "decision_id": plan.decision_id,
                },
                confirmation_evidence={
                    "confirmation_id": confirmation.confirmation_id,
                    "confirmed_by": confirmation.confirmed_by,
                },
                approval_evidence=None
                if approval is None
                else {
                    "approval_id": approval.approval_id,
                    "approver_id": approval.approver_id,
                },
                idempotency_key=idempotency_key,
            )
        except PermissionError as error:
            self._fail_execution(
                execution_actor, plan, queued, "execution_denied", "executor_acl_denied", approval
            )
            raise ExecutorAclDeniedError from error
        except Exception as error:
            self._fail_execution(
                execution_actor, plan, queued, "execution_failed", "executor_error", approval
            )
            raise ExecutorExecutionFailedError from error
        if (
            result.status != "completed"
            or not result.operation_id
        ):
            self._fail_execution(
                execution_actor,
                plan,
                queued,
                "execution_failed",
                "executor_not_completed",
                approval,
            )
            raise ExecutorExecutionFailedError
        self._apply_completed_path_updates(plan)
        completed = self._repository.update_execution_job(replace(queued, state="completed"))
        self._repository.update_plan(replace(plan, state="completed"))
        details: dict[str, object] = {"plan_id": plan.plan_id, "job_id": completed.job_id}
        if approval is not None:
            details["approval_id"] = approval.approval_id
            details["approver_id"] = approval.approver_id or ""
        self._repository.append_audit_event(
            _audit_event(
                event_type="execution_completed",
                actor_id=execution_actor.actor_id,
                request_id=execution_actor.request_id,
                run_id=execution_actor.run_id,
                details=details,
            )
        )
        return completed

    def _apply_completed_path_updates(self, plan: Plan) -> None:
        for operation, snapshot in zip(
            plan.normalized_operations,
            plan.asset_snapshots,
        ):
            if operation["type"] != Action.MOVE_RENAME.value:
                continue
            self._repository.move_asset_path(
                snapshot["asset_id"],
                str(operation["target_path"]),
            )

    def _execution_actor(
        self, caller_actor: TrustedActorContext, plan: Plan
    ) -> TrustedActorContext:
        return TrustedActorContext(
            actor_id=plan.created_by,
            workspace_id=plan.workspace_id,
            context_version=plan.context_version,
            session_id=str(plan.acl_snapshot["creator_session_id"]),
            request_id=caller_actor.request_id,
            run_id=str(plan.acl_snapshot["creator_run_id"]),
            group_ids=frozenset(str(item) for item in plan.acl_snapshot["creator_group_ids"]),
            role_ids=frozenset(str(item) for item in plan.acl_snapshot["creator_role_ids"]),
        )

    def _revalidate_before_execution(
        self,
        caller_actor: TrustedActorContext,
        plan: Plan,
        execution_actor: TrustedActorContext | None = None,
    ) -> None:
        subject_actor = execution_actor or self._execution_actor(caller_actor, plan)
        reason: str | None = None
        denied = False
        if _is_expired(plan.expires_at):
            reason = "expired"
        elif caller_actor.context_version != plan.context_version:
            reason = "context_drift"
        else:
            action = _operation_action(plan.normalized_operations)
            decision = evaluate_authorization(
                actor=subject_actor,
                grants=self._repository.list_permission_grants(subject_actor),
                action=action,
                paths=tuple(
                    path
                    for operation in plan.normalized_operations
                    for path in _operation_paths(operation)
                ),
            )
            if decision.state is DecisionState.DENY:
                reason = f"acl_{decision.reason}"
                denied = True
            elif not _asset_snapshots_match(
                self._repository, subject_actor.workspace_id, plan.asset_snapshots
            ):
                reason = "asset_snapshot_drift"
        if reason is None:
            return
        self._repository.append_audit_event(
            _audit_event(
                event_type="plan_revalidation_failed",
                actor_id=caller_actor.actor_id,
                request_id=caller_actor.request_id,
                run_id=caller_actor.run_id,
                details={"plan_id": plan.plan_id, "reason": reason},
            )
        )
        raise PlanRevalidationError(reason, denied)

    def _fail_execution(
        self,
        actor: TrustedActorContext,
        plan: Plan,
        job: ExecutionJob,
        event_type: str,
        reason: str,
        approval: Approval | None = None,
    ) -> ExecutionJob:
        failed = self._repository.update_execution_job(replace(job, state="failed"))
        self._repository.update_plan(replace(plan, state="failed"))
        details: dict[str, object] = {
            "plan_id": plan.plan_id,
            "job_id": failed.job_id,
            "reason": reason,
        }
        if approval is not None:
            details["approval_id"] = approval.approval_id
            details["approver_id"] = approval.approver_id or ""
        self._repository.append_audit_event(
            _audit_event(
                event_type=event_type,
                actor_id=actor.actor_id,
                request_id=actor.request_id,
                run_id=actor.run_id,
                details=details,
            )
        )
        return failed


def _final_upload_path(directory: str, file_name: str) -> str:
    normalized_directory = directory.rstrip("/")
    return f"{normalized_directory}/{file_name}" if normalized_directory else file_name


def _normalize_operation(operation: dict[str, object]) -> dict[str, object]:
    operation_type = str(operation["type"])
    normalized: dict[str, object] = {
        "operation_id": str(operation["operation_id"]),
        "type": operation_type,
        "source_path": str(operation["source_path"]),
    }
    if operation_type == Action.MOVE_RENAME.value:
        normalized["target_path"] = str(operation["target_path"])
    return normalized


def _operation_action(operations: tuple[dict[str, object], ...]) -> Action:
    actions = {Action(str(operation["type"])) for operation in operations}
    if len(actions) != 1:
        return Action.TRASH if Action.TRASH in actions else Action.MOVE_RENAME
    return next(iter(actions))


def _operation_paths(operation: dict[str, object]) -> tuple[str, ...]:
    if operation["type"] == Action.MOVE_RENAME.value:
        return (str(operation["source_path"]), str(operation["target_path"]))
    return (str(operation["source_path"]),)


def _asset_snapshot(
    repository: ControlPlaneRepository,
    workspace_id: str,
    source_path: object,
) -> dict[str, str]:
    asset = repository.find_asset_by_path(workspace_id, str(source_path))
    if asset is None or asset.active_version_id is None:
        raise PlanDeniedError
    version = repository.get_asset_version(asset.active_version_id)
    return {
        "asset_id": asset.asset_id,
        "asset_version_id": version.asset_version_id,
        "content_fingerprint": version.content_fingerprint,
    }


def _asset_snapshots_match(
    repository: ControlPlaneRepository,
    workspace_id: str,
    expected_snapshots: tuple[dict[str, str], ...],
) -> bool:
    for snapshot in expected_snapshots:
        try:
            asset = repository.get_asset(snapshot["asset_id"])
        except KeyError:
            return False
        if asset.workspace_id != workspace_id:
            return False
        if asset.active_version_id != snapshot["asset_version_id"]:
            return False
        try:
            version = repository.get_asset_version(snapshot["asset_version_id"])
        except KeyError:
            return False
        if version.content_fingerprint != snapshot["content_fingerprint"]:
            return False
    return True


def _existing_confirmation(
    repository: ControlPlaneRepository, plan_id: str
) -> Confirmation:
    confirmation = repository.find_confirmation_by_plan(plan_id)
    if confirmation is not None:
        return confirmation
    raise PlanStateError


def _existing_approval_for_plan(
    repository: ControlPlaneRepository, plan_id: str
) -> Approval:
    approval = repository.find_approval_by_plan(plan_id)
    if approval is not None:
        return approval
    raise PlanStateError


def _is_expired(expires_at: str) -> bool:
    try:
        normalized = expires_at.replace("Z", "+00:00")
        expires = datetime.fromisoformat(normalized)
    except ValueError:
        return True
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)
    return expires <= datetime.now(timezone.utc)


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _require_sha256_fingerprint(content_fingerprint: str) -> None:
    algorithm, separator, digest = content_fingerprint.partition(":")
    if algorithm != "sha256" or separator != ":" or not digest:
        raise RuleSourceNotAllowedError


def _validate_assessment_result(
    match_score: int,
    result_level: str,
    citations: tuple[Mapping[str, object], ...],
    asset_versions: tuple[AssetVersion, ...],
    rule_version: RuleVersion,
) -> None:
    if isinstance(match_score, bool) or not 0 <= match_score <= 100:
        raise AssessmentFailedError
    if result_level not in {"MATCH", "POSSIBLE", "NOT_MATCH", "MISSING_INFO"}:
        raise AssessmentFailedError
    if result_level == "NOT_MATCH" and not any(
        citation.get("fictional_conflict") is True for citation in citations
    ):
        raise AssessmentFailedError
    assets_by_version_id = {
        version.asset_version_id: version.asset_id for version in asset_versions
    }
    for citation in citations:
        citation_type = citation.get("citation_type", "material")
        if citation_type == "material":
            asset_version_id = citation.get("asset_version_id")
            if asset_version_id not in assets_by_version_id:
                raise AssessmentFailedError
            asset_id = citation.get("asset_id")
            if asset_id is not None and asset_id != assets_by_version_id[asset_version_id]:
                raise AssessmentFailedError
        elif citation_type == "rule":
            if not isinstance(citation.get("rule_id"), str) or not citation["rule_id"]:
                raise AssessmentFailedError
            if (
                citation.get("rule_version_id") != rule_version.rule_version_id
                or citation.get("version_label") != rule_version.version_label
                or citation.get("content_fingerprint") != rule_version.content_fingerprint
                or citation.get("source_type") != rule_version.source_type
            ):
                raise AssessmentFailedError
        else:
            raise AssessmentFailedError


def _safe_citation(citation: dict[str, object]) -> dict[str, object]:
    allowed_keys = (
        "citation_type",
        "asset_id",
        "asset_version_id",
        "chunk_id",
        "page",
        "paragraph",
        "rule_version_id",
        "rule_id",
        "version_label",
        "content_fingerprint",
        "source_type",
    )
    return {key: citation[key] for key in allowed_keys if key in citation}


def _audit_event(
    event_type: str,
    actor_id: str,
    request_id: str,
    run_id: str,
    details: dict[str, object],
) -> AuditEvent:
    return AuditEvent(
        event_id=str(uuid4()),
        event_type=event_type,
        actor_id=actor_id,
        request_id=request_id,
        run_id=run_id,
        details=details,
    )
