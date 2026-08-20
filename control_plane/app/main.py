import hashlib
import hmac
import json
from dataclasses import asdict
from pathlib import Path
from typing import Mapping
from uuid import uuid4

from fastapi import Cookie, Depends, FastAPI, File, Form, Header, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .domain import (
    Action,
    AuditEvent,
    PermissionGrant,
    PrincipalType,
    TrustedActorContext,
)
from .ports import FileExecutorPort, RagPort
from .repository import ControlPlaneRepository
from .service import (
    ActorNotPlanCreatorError,
    AssessmentDeniedError,
    AssessmentFailedError,
    ApprovalForbiddenError,
    ApprovalNotFoundError,
    AssetVersionNotFoundError,
    ControlPlaneService,
    ExecutorAclDeniedError,
    ExecutorExecutionFailedError,
    ExecutorResultMismatchError,
    ExecutorUploadFailedError,
    InvalidIndexTransitionError,
    PlanDeniedError,
    PlanHashMismatchError,
    PlanNotFoundError,
    PlanRevalidationError,
    PlanStateError,
    RagEnqueueFailedError,
    RuleSourceNotAllowedError,
    RuleVersionNotFoundError,
    UploadDeniedError,
    UploadTargetExistsError,
)
from .sessions import (
    DemoIdentity,
    ServerSessionStore,
    authenticate_demo_identity,
)

from service.app.rag.parser_worker import DOCX_MIME_TYPE, PDF_MIME_TYPE


UPLOADED_DIR = "客户上传资料"
MAX_KNOWLEDGE_UPLOAD_BYTES = 2 * 1024 * 1024
ALLOWED_KNOWLEDGE_EXTENSIONS = frozenset({".pdf", ".docx"})


class LoginRequest(BaseModel):
    username: str
    password: str


class IndexStatusRequest(BaseModel):
    state: str
    failure_code: str | None = None


class RagQueryRequest(BaseModel):
    question: str
    asset_id: str


class ProviderSwitchRequest(BaseModel):
    provider: str
    api_key: str | None = None


class ControlledSampleAssessRequest(BaseModel):
    scenario: str
    query_subject: str
    file_names: list[str]


class ControlledSampleQueryRequest(BaseModel):
    question: str
    file_name: str


class KnowledgeQueryRequest(BaseModel):
    question: str
    file_name: str


class CreatePlanRequest(BaseModel):
    operations: list[dict[str, object]]
    expires_at: str
    policy_version: str | None = None
    context_version: str | None = None
    asset_snapshots: list[dict[str, object]] | None = None


class ConfirmPlanRequest(BaseModel):
    expected_plan_hash: str


class DecideApprovalRequest(BaseModel):
    decision: str
    expected_plan_hash: str
    role_ids: list[str] | None = None


class CreateRuleSetRequest(BaseModel):
    scenario: str
    name: str
    status: str
    source_type: str
    version_label: str
    content_fingerprint: str | None = None
    redacted_rule_summary: str


class CreateAssessmentRequest(BaseModel):
    scenario: str
    query_subject: str
    asset_ids: list[str]
    rule_version_id: str
    asset_version_ids: list[str] | None = None
    llm_report: dict[str, object] | None = None


class ApiError(Exception):
    def __init__(self, status_code: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message


def create_app(
    *,
    repository: ControlPlaneRepository,
    file_executor: FileExecutorPort,
    rag_port: RagPort,
    demo_identities: Mapping[str, DemoIdentity],
    internal_service_key: str,
    approver_role_id: str,
    demo_rules_fixture_path: Path | None = None,
    llm_providers: object | None = None,
    disclaimer_version: str = "disclaimer-demo-v1",
    disclaimer_text: str = "仅供资料完整度与规则匹配演示参考",
) -> FastAPI:
    if not internal_service_key.strip():
        raise ValueError("internal service key must be non-empty")
    if not approver_role_id.strip():
        raise ValueError("approver_role_id must be non-empty")

    app = FastAPI()
    static_dir = Path(__file__).resolve().parent.parent / "static"

    @app.middleware("http")
    async def no_cache_for_demo_static(request: Request, call_next):
        """Disable browser caching for demo static assets.

        The in-app browser otherwise reuses stale app.js/style.css via
        ETag/304, hiding frontend updates. Only affects /demo/ so API
        responses keep their normal caching behavior.
        """
        response = await call_next(request)
        if request.url.path.startswith("/demo/"):
            response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
            response.headers["Pragma"] = "no-cache"
        return response

    app.mount(
        "/demo",
        StaticFiles(directory=static_dir, html=True),
        name="demo",
    )
    session_store = ServerSessionStore()
    app.state.repository = repository
    app.state.file_executor = file_executor
    app.state.rag_port = rag_port
    app.state.demo_identities = dict(demo_identities)
    app.state.internal_service_key = internal_service_key
    app.state.approver_role_id = approver_role_id
    app.state.demo_rules_fixture_path = demo_rules_fixture_path
    app.state.llm_providers = llm_providers
    app.state.disclaimer_version = disclaimer_version
    app.state.session_store = session_store
    service = ControlPlaneService(
        repository,
        file_executor,
        rag_port,
        approver_role_id,
        disclaimer_version=disclaimer_version,
        disclaimer_text=disclaimer_text,
    )
    app.state.control_plane_service = service

    @app.exception_handler(ApiError)
    async def handle_api_error(_request: Request, error: ApiError) -> JSONResponse:
        content: dict[str, object] = {
            "error": {"code": error.code, "message": error.message}
        }
        if error.code == "assessment_denied":
            content = {
                "status": "DENIED",
                "reason": "ACCESS_DENIED",
                "retrieved_count": 0,
                "llm_invoked": False,
                "citations": [],
                **content,
            }
        return JSONResponse(
            status_code=error.status_code,
            content=content,
        )

    @app.exception_handler(RequestValidationError)
    async def handle_request_validation_error(
        _request: Request, _error: RequestValidationError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content={
                "error": {
                    "code": "request_validation_error",
                    "message": "Invalid request",
                }
            },
        )

    def require_actor(cp_session: str | None = Cookie(default=None)) -> TrustedActorContext:
        actor = session_store.resolve(cp_session, _new_id())
        if actor is None:
            raise ApiError(401, "authentication_required", "Authentication required")
        return actor

    @app.post("/api/session/login")
    def login(credentials: LoginRequest) -> JSONResponse:
        identity = authenticate_demo_identity(
            app.state.demo_identities, credentials.username, credentials.password
        )
        if identity is None:
            raise ApiError(401, "invalid_credentials", "Invalid credentials")
        bearer, actor = session_store.create(identity, _new_id())
        response = JSONResponse(_actor_payload(actor))
        response.set_cookie(
            key="cp_session",
            value=bearer,
            httponly=True,
            samesite="strict",
            path="/",
        )
        return response

    @app.get("/api/session/me")
    def me(actor: TrustedActorContext = Depends(require_actor)) -> dict[str, object]:
        return _actor_payload(actor)

    @app.post("/api/session/logout", status_code=204)
    def logout(cp_session: str | None = Cookie(default=None)) -> Response:
        session_store.revoke(cp_session)
        rag = getattr(app.state, "rag_port", None)
        if rag is not None and hasattr(rag, "clear_cloud_key"):
            rag.clear_cloud_key()
        response = Response(status_code=204)
        response.delete_cookie("cp_session", path="/", httponly=True, samesite="strict")
        return response

    @app.post("/api/uploads")
    async def upload(
        directory: str = Form(...),
        file: UploadFile = File(...),
        actor: TrustedActorContext = Depends(require_actor),
    ) -> dict[str, object]:
        try:
            outcome = service.upload(
                actor=actor,
                directory=directory,
                file_name=file.filename or "",
                content=await file.read(),
            )
        except UploadDeniedError as error:
            raise ApiError(403, "upload_denied", "Upload is not authorized") from error
        except ExecutorResultMismatchError as error:
            raise ApiError(
                502,
                "executor_result_mismatch",
                "Executor result does not match the authorized upload target",
            ) from error
        except ExecutorUploadFailedError as error:
            raise ApiError(
                502,
                "executor_upload_failed",
                "File upload failed",
            ) from error
        except UploadTargetExistsError as error:
            raise ApiError(
                409,
                "upload_target_exists",
                "Upload target already exists",
            ) from error
        except RagEnqueueFailedError as error:
            raise ApiError(
                502,
                "rag_enqueue_failed",
                "Index enqueue failed",
            ) from error
        return {
            "decision": {
                "state": outcome.decision.state.value,
                "reason": outcome.decision.reason,
            },
            "asset": asdict(outcome.asset),
            "asset_version": asdict(outcome.asset_version),
            "audit_event_id": outcome.audit_event_id,
        }

    @app.post("/api/retrieval/query")
    def query_retrieval(
        request: RagQueryRequest,
        actor: TrustedActorContext = Depends(require_actor),
    ) -> Mapping[str, object]:
        question = request.question.strip()
        if not question:
            raise ApiError(422, "question_required", "Question is required")
        asset_id = request.asset_id.strip()
        if not asset_id:
            raise ApiError(422, "asset_id_required", "Asset ID is required")
        return rag_port.query(actor, question, asset_id)

    @app.post("/api/controlled-sample/assess")
    def controlled_sample_assess(
        request: ControlledSampleAssessRequest,
        actor: TrustedActorContext = Depends(require_actor),
    ) -> dict[str, object]:
        """P1: select controlled sample file -> BFF resolves assets -> auto assess.

        The browser only submits import-manifest controlled file names. The BFF
        resolves them to assets and re-uses create_assessment_report, so the
        existing authorization gates (evaluate_authorization on asset path) and
        the active demo rule-version lookup stay unchanged. asset_id never has
        to be typed by the user.
        """
        if not request.file_names:
            raise ApiError(422, "file_names_required", "At least one file name is required")
        rag = app.state.rag_port
        if not hasattr(rag, "resolve_controlled_asset"):
            raise ApiError(404, "controlled_sample_unavailable", "Controlled sample bridge is not available")
        asset_ids = []
        for file_name in request.file_names:
            asset = rag.resolve_controlled_asset(file_name.strip())
            if asset is None:
                raise ApiError(
                    422,
                    "unknown_controlled_file",
                    f"Not a controlled sample file: {file_name}",
                )
            asset_ids.append(asset.asset_id)
        repository = app.state.repository
        rule_version_id = _active_demo_rule_version(repository, request.scenario)
        if rule_version_id is None:
            raise ApiError(
                422,
                "no_active_demo_rule_version",
                "No active demo rule version is available for the scenario",
            )
        service = app.state.control_plane_service
        try:
            outcome = service.create_assessment_report(
                actor=actor,
                scenario=request.scenario,
                query_subject=request.query_subject,
                asset_ids=tuple(asset_ids),
                rule_version_id=rule_version_id,
            )
        except AssessmentDeniedError as error:
            raise ApiError(403, "assessment_denied", "Assessment is not authorized") from error
        except RuleVersionNotFoundError as error:
            raise ApiError(404, "rule_version_not_found", "Rule version not found") from error
        except AssessmentFailedError as error:
            raise ApiError(502, "assessment_failed", "Assessment failed") from error
        return {"report": _assessment_report_payload(outcome.report)}

    @app.post("/api/controlled-sample/query")
    def controlled_sample_query(
        request: ControlledSampleQueryRequest,
        actor: TrustedActorContext = Depends(require_actor),
    ) -> Mapping[str, object]:
        """P1: select controlled sample file + question -> BFF resolves asset -> query.

        Authorization is still decided inside DemoRagPort.query on the resolved
        asset path; the browser never supplies asset_id.
        """
        question = request.question.strip()
        if not question:
            raise ApiError(422, "question_required", "Question is required")
        file_name = request.file_name.strip()
        if not file_name:
            raise ApiError(422, "file_name_required", "File name is required")
        rag = app.state.rag_port
        if not hasattr(rag, "resolve_controlled_asset"):
            raise ApiError(404, "controlled_sample_unavailable", "Controlled sample bridge is not available")
        asset = rag.resolve_controlled_asset(file_name)
        if asset is None:
            raise ApiError(
                422,
                "unknown_controlled_file",
                f"Not a controlled sample file: {file_name}",
            )
        return rag.query(actor, question, asset.asset_id)

    @app.post("/api/demo/knowledge/upload")
    async def knowledge_upload(
        file: UploadFile = File(...),
        actor: TrustedActorContext = Depends(require_actor),
    ) -> dict[str, object]:
        """Real-material upload -> SHA-256 fingerprint -> auto index + activate.

        The BFF owns validation and fingerprinting; the composite bridge parses
        the bytes into the in-memory vector index, walks the version state
        machine to ready and activates it. The uploader is then granted QUERY
        on the exact uploaded file path, so they can query their own material.
        Audit events never retain file content or credentials.
        """
        rag = app.state.rag_port
        if not hasattr(rag, "ingest_uploaded_version"):
            raise ApiError(
                404,
                "knowledge_upload_unavailable",
                "Knowledge upload bridge is not available",
            )
        file_name = _require_upload_file_name(file.filename or "")
        extension = Path(file_name).suffix.lower()
        if extension not in ALLOWED_KNOWLEDGE_EXTENSIONS:
            raise ApiError(
                422,
                "unsupported_file_type",
                "Only PDF/DOCX uploads are supported",
            )
        content = await file.read()
        if not content:
            raise ApiError(422, "empty_file", "Uploaded file is empty")
        if len(content) > MAX_KNOWLEDGE_UPLOAD_BYTES:
            raise ApiError(
                422,
                "file_too_large",
                "Uploaded file exceeds the 2MB demo limit",
            )
        path = f"{UPLOADED_DIR}/{file_name}"
        repository = app.state.repository
        if repository.find_asset_by_path(actor.workspace_id, path) is not None:
            raise ApiError(
                409,
                "upload_target_exists",
                "Upload target already exists",
            )
        content_fingerprint = "sha256:" + hashlib.sha256(content).hexdigest()
        asset = repository.get_or_create_asset(
            actor.workspace_id, path, file_name, actor.actor_id
        )
        asset_version = repository.create_asset_version(
            asset.asset_id, content_fingerprint, path
        )
        try:
            chunk_count = rag.ingest_uploaded_version(
                actor=actor,
                asset_version=asset_version,
                content=content,
                request_id=actor.request_id,
            )
        except (ValueError, RuntimeError) as error:
            raise ApiError(
                502,
                "knowledge_ingest_failed",
                "Knowledge index build failed",
            ) from error
        repository.add_permission_grant(
            PermissionGrant(
                grant_id=_new_id(),
                workspace_id=actor.workspace_id,
                context_version=actor.context_version,
                principal_type=PrincipalType.USER,
                principal_id=actor.actor_id,
                action=Action.QUERY,
                path_prefix=path,
            )
        )
        _append_knowledge_audit(
            repository,
            actor,
            "upload_authorized",
            {
                "file_name": file_name,
                "size_bytes": len(content),
                "mime_type": _knowledge_mime_label(extension),
            },
        )
        _append_knowledge_audit(
            repository,
            actor,
            "asset_version_created",
            {
                "asset_id": asset.asset_id,
                "asset_version_id": asset_version.asset_version_id,
            },
        )
        _append_knowledge_audit(
            repository,
            actor,
            "query_grant_added",
            {
                "asset_id": asset.asset_id,
                "path_prefix": path,
                "principal_id": actor.actor_id,
            },
        )
        _append_knowledge_audit(
            repository,
            actor,
            "asset_version_activated",
            {
                "asset_id": asset.asset_id,
                "asset_version_id": asset_version.asset_version_id,
            },
        )
        return {
            "asset_id": asset.asset_id,
            "file_name": file_name,
            "path": path,
            "version_id": asset_version.asset_version_id,
            "chunk_count": chunk_count,
            "index_state": "ready",
            "content_fingerprint": content_fingerprint,
        }

    @app.post("/api/demo/knowledge/query")
    def knowledge_query(
        request: KnowledgeQueryRequest,
        actor: TrustedActorContext = Depends(require_actor),
    ) -> Mapping[str, object]:
        """Query one uploaded real material file by its file name.

        The BFF resolves the uploaded asset path (客户上传资料/<file_name>) and
        delegates to the composite bridge query, which still decides
        authorization inside DemoRagPort on the resolved asset path.
        """
        question = request.question.strip()
        if not question:
            raise ApiError(422, "question_required", "Question is required")
        file_name = request.file_name.strip()
        if not file_name:
            raise ApiError(422, "file_name_required", "File name is required")
        if not _is_safe_file_name(file_name):
            raise ApiError(422, "invalid_file_name", "File name is not allowed")
        path = f"{UPLOADED_DIR}/{file_name}"
        asset = app.state.repository.find_asset_by_path(
            actor.workspace_id, path
        )
        if asset is None:
            raise ApiError(
                404,
                "uploaded_file_not_found",
                "Uploaded file not found",
            )
        return app.state.rag_port.query(actor, question, asset.asset_id)



    @app.get("/api/llm/provider")
    def llm_provider_status(
        actor: TrustedActorContext = Depends(require_actor),
    ) -> dict[str, object]:
        rag = app.state.rag_port
        if not hasattr(rag, "current_provider") or not hasattr(rag, "provider_descriptors"):
            raise ApiError(404, "provider_switching_unavailable", "Provider switching is not available")
        providers = [
            {"id": descriptor.id, "label": descriptor.label}
            for descriptor in rag.provider_descriptors()
        ]
        cloud_key_configured = (
            bool(rag.cloud_key_configured())
            if hasattr(rag, "cloud_key_configured")
            else False
        )
        return {
            "current": rag.current_provider(),
            "providers": providers,
            "cloud_key_configured": cloud_key_configured,
        }

    @app.post("/api/llm/provider")
    def llm_provider_switch(
        request: ProviderSwitchRequest,
        actor: TrustedActorContext = Depends(require_actor),
    ) -> dict[str, object]:
        rag = app.state.rag_port
        if not hasattr(rag, "set_provider"):
            raise ApiError(404, "provider_switching_unavailable", "Provider switching is not available")
        provider_id = request.provider.strip()
        try:
            rag.set_provider(provider_id, api_key=request.api_key)
        except (ValueError, RuntimeError) as error:
            raise ApiError(422, "unknown_provider", str(error)) from error
        providers = [
            {"id": descriptor.id, "label": descriptor.label}
            for descriptor in rag.provider_descriptors()
        ]
        cloud_key_configured = (
            bool(rag.cloud_key_configured())
            if hasattr(rag, "cloud_key_configured")
            else False
        )
        return {
            "current": rag.current_provider(),
            "providers": providers,
            "cloud_key_configured": cloud_key_configured,
        }

    @app.post("/api/rule-sets")
    def create_rule_set(
        request: CreateRuleSetRequest,
        actor: TrustedActorContext = Depends(require_actor),
    ) -> dict[str, object]:
        content_fingerprint = _resolve_rule_content_fingerprint(app, request)
        try:
            outcome = service.create_rule_set_with_version(
                actor=actor,
                scenario=request.scenario,
                name=request.name,
                status=request.status,
                source_type=request.source_type,
                version_label=request.version_label,
                content_fingerprint=content_fingerprint,
                redacted_rule_summary=request.redacted_rule_summary,
            )
        except RuleSourceNotAllowedError as error:
            raise ApiError(
                422,
                "rule_source_not_allowed",
                "Rule source is not allowed for the demo",
            ) from error
        return {
            "rule_set": asdict(outcome.rule_set),
            "rule_version": asdict(outcome.rule_version),
            "audit_event_id": outcome.audit_event_id,
        }

    @app.post("/api/assessments")
    def create_assessment(
        request: CreateAssessmentRequest,
        actor: TrustedActorContext = Depends(require_actor),
    ) -> dict[str, object]:
        try:
            outcome = service.create_assessment_report(
                actor=actor,
                scenario=request.scenario,
                query_subject=request.query_subject,
                asset_ids=tuple(request.asset_ids),
                rule_version_id=request.rule_version_id,
            )
        except AssessmentDeniedError as error:
            raise ApiError(
                403,
                "assessment_denied",
                "Assessment is not authorized",
            ) from error
        except RuleVersionNotFoundError as error:
            raise ApiError(404, "rule_version_not_found", "Rule version not found") from error
        except AssessmentFailedError as error:
            raise ApiError(502, "assessment_failed", "Assessment failed") from error
        return {"report": _assessment_report_payload(outcome.report)}

    @app.post("/api/plans")
    def create_plan(
        request: CreatePlanRequest,
        actor: TrustedActorContext = Depends(require_actor),
    ) -> dict[str, object]:
        try:
            outcome = service.create_plan(
                actor=actor,
                operations=tuple(request.operations),
                expires_at=request.expires_at,
            )
        except PlanDeniedError as error:
            raise ApiError(403, "plan_denied", "Plan is not authorized") from error
        return {
            "decision": {
                "state": outcome.decision.state.value,
                "reason": outcome.decision.reason,
            },
            "plan": _plan_payload(outcome.plan),
            "asset_snapshots": list(outcome.plan.asset_snapshots),
            "impact_summary": outcome.impact_summary,
        }

    @app.post("/api/plans/{plan_id}/confirm")
    def confirm_plan(
        plan_id: str,
        request: ConfirmPlanRequest,
        idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
        actor: TrustedActorContext = Depends(require_actor),
    ) -> dict[str, object]:
        if idempotency_key is None or not idempotency_key.strip():
            raise ApiError(422, "idempotency_key_required", "Idempotency-Key is required")
        try:
            outcome = service.confirm_plan(
                actor=actor,
                plan_id=plan_id,
                expected_plan_hash=request.expected_plan_hash,
                idempotency_key=idempotency_key,
            )
        except PlanHashMismatchError as error:
            raise ApiError(409, "plan_hash_mismatch", "Plan hash mismatch") from error
        except ActorNotPlanCreatorError as error:
            raise ApiError(403, "plan_confirmation_forbidden", "Plan confirmation is forbidden") from error
        except PlanNotFoundError as error:
            raise ApiError(404, "plan_not_found", "Plan not found") from error
        except PlanStateError as error:
            raise ApiError(409, "invalid_plan_state", "Invalid plan state") from error
        except PlanRevalidationError as error:
            status_code = 403 if error.denied else 409
            raise ApiError(
                status_code,
                "plan_revalidation_failed",
                "Plan is no longer executable",
            ) from error
        except ExecutorAclDeniedError as error:
            raise ApiError(403, "executor_acl_denied", "Execution is not authorized") from error
        except ExecutorExecutionFailedError as error:
            raise ApiError(502, "executor_execution_failed", "Execution failed") from error
        return _confirmation_payload(outcome)

    @app.get("/api/approvals/pending")
    def pending_approvals(
        actor: TrustedActorContext = Depends(require_actor),
    ) -> dict[str, object]:
        return {
            "approvals": [
                _approval_payload(approval)
                for approval in service.list_pending_approvals(actor)
            ]
        }

    @app.post("/api/approvals/{approval_id}/decide")
    def decide_approval(
        approval_id: str,
        request: DecideApprovalRequest,
        idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
        actor: TrustedActorContext = Depends(require_actor),
    ) -> dict[str, object]:
        if idempotency_key is None or not idempotency_key.strip():
            raise ApiError(422, "idempotency_key_required", "Idempotency-Key is required")
        try:
            outcome = service.decide_approval(
                actor=actor,
                approval_id=approval_id,
                decision=request.decision,
                expected_plan_hash=request.expected_plan_hash,
                idempotency_key=idempotency_key,
            )
        except ApprovalForbiddenError as error:
            raise ApiError(403, "approval_forbidden", "Approval decision is forbidden") from error
        except ApprovalNotFoundError as error:
            raise ApiError(404, "approval_not_found", "Approval not found") from error
        except PlanHashMismatchError as error:
            raise ApiError(409, "plan_hash_mismatch", "Plan hash mismatch") from error
        except PlanStateError as error:
            raise ApiError(409, "invalid_approval_state", "Invalid approval state") from error
        except PlanRevalidationError as error:
            status_code = 403 if error.denied else 409
            raise ApiError(
                status_code,
                "plan_revalidation_failed",
                "Plan is no longer executable",
            ) from error
        except ExecutorAclDeniedError as error:
            raise ApiError(403, "executor_acl_denied", "Execution is not authorized") from error
        except ExecutorExecutionFailedError as error:
            raise ApiError(502, "executor_execution_failed", "Execution failed") from error
        return _approval_decision_payload(outcome)

    @app.post("/internal/asset-versions/{asset_version_id}/index-status")
    def update_index_status(
        asset_version_id: str,
        update: IndexStatusRequest,
        x_internal_service_key: str | None = Header(default=None),
    ) -> dict[str, object]:
        if x_internal_service_key is None or not hmac.compare_digest(
            x_internal_service_key, internal_service_key
        ):
            raise ApiError(
                401,
                "internal_service_unauthorized",
                "Invalid internal service key",
            )
        try:
            version = service.update_index_state(
                asset_version_id=asset_version_id,
                state=update.state,
                failure_code=update.failure_code,
            )
        except InvalidIndexTransitionError as error:
            raise ApiError(
                409,
                "invalid_index_transition",
                "Invalid index transition",
            ) from error
        except AssetVersionNotFoundError as error:
            raise ApiError(
                404,
                "asset_version_not_found",
                "Asset version not found",
            ) from error
        return {"asset_version": asdict(version)}

    return app


def _actor_payload(actor: TrustedActorContext) -> dict[str, object]:
    payload = asdict(actor)
    payload["group_ids"] = sorted(actor.group_ids)
    payload["role_ids"] = sorted(actor.role_ids)
    return payload


def _plan_payload(plan) -> dict[str, object]:
    payload = asdict(plan)
    payload["decision_state"] = plan.decision_state.value
    return payload


def _approval_payload(approval) -> dict[str, object]:
    return asdict(approval)


def _job_payload(job) -> dict[str, object]:
    return asdict(job)


def _confirmation_payload(outcome) -> dict[str, object]:
    payload: dict[str, object] = {
        "plan": _plan_payload(outcome.plan),
        "confirmation": asdict(outcome.confirmation),
    }
    if outcome.approval is not None:
        payload["approval"] = _approval_payload(outcome.approval)
    if outcome.execution_job is not None:
        payload["execution_job"] = _job_payload(outcome.execution_job)
    return payload


def _approval_decision_payload(outcome) -> dict[str, object]:
    payload: dict[str, object] = {"approval": _approval_payload(outcome.approval)}
    if outcome.execution_job is not None:
        payload["execution_job"] = _job_payload(outcome.execution_job)
    return payload



def _active_demo_rule_version(repository, scenario: str) -> str | None:
    """Return the active demo_fixture rule version id for the scenario, or None."""
    for rule_version in repository.rule_versions.values():
        if rule_version.source_type != "demo_fixture":
            continue
        rule_set = repository.rule_sets.get(rule_version.rule_set_id)
        if rule_set is not None and rule_set.scenario == scenario and rule_set.status == "active":
            return rule_version.rule_version_id
    return None


def _assessment_report_payload(report) -> dict[str, object]:
    payload = asdict(report)
    payload["asset_versions"] = list(report.asset_versions)
    payload["missing_materials"] = list(report.missing_materials)
    payload["citations"] = list(report.citations)
    return payload


def _resolve_rule_content_fingerprint(
    app: FastAPI, request: CreateRuleSetRequest
) -> str:
    """BFF-side fingerprint resolution for RuleVersion creation.

    For the controlled demo fixture the fingerprint comes from the fixture file
    (single source of truth), never from the browser. A client-supplied value
    that mismatches the fixture is rejected before a RuleVersion is created.
    """
    rules_path = app.state.demo_rules_fixture_path
    fixture_fingerprint: str | None = None
    if request.source_type == "demo_fixture" and rules_path is not None:
        payload = json.loads(Path(rules_path).read_text(encoding="utf-8"))
        candidate = payload.get("content_fingerprint")
        if not isinstance(candidate, str) or not candidate.startswith("sha256:"):
            raise ApiError(
                422,
                "rule_source_not_allowed",
                "Controlled rule fixture is invalid",
            )
        fixture_fingerprint = candidate
        if (
            request.content_fingerprint is not None
            and request.content_fingerprint != fixture_fingerprint
        ):
            raise ApiError(
                422,
                "rule_fingerprint_mismatch",
                "Rule content fingerprint does not match the controlled demo fixture",
            )
    if request.content_fingerprint is not None:
        return request.content_fingerprint
    if fixture_fingerprint is not None:
        return fixture_fingerprint
    raise ApiError(
        422,
        "content_fingerprint_required",
        "content_fingerprint is required",
    )


def _new_id() -> str:
    return str(uuid4())


def _is_safe_file_name(file_name: str) -> bool:
    """Reject empty, hidden, absolute and path-traversal file names."""
    if not file_name or file_name.startswith("."):
        return False
    if "/" in file_name or "\\" in file_name or ".." in file_name:
        return False
    return True


def _require_upload_file_name(file_name: str) -> str:
    name = (file_name or "").strip()
    if not _is_safe_file_name(name):
        raise ApiError(422, "invalid_file_name", "File name is not allowed")
    return name


def _knowledge_mime_label(extension: str) -> str:
    if extension == ".pdf":
        return PDF_MIME_TYPE
    if extension == ".docx":
        return DOCX_MIME_TYPE
    raise ApiError(422, "unsupported_file_type", "Only PDF/DOCX uploads are supported")


def _append_knowledge_audit(
    repository,
    actor: TrustedActorContext,
    event_type: str,
    details: Mapping[str, object],
) -> None:
    repository.append_audit_event(
        AuditEvent(
            event_id=_new_id(),
            event_type=event_type,
            actor_id=actor.actor_id,
            request_id=actor.request_id,
            details=details,
        )
    )
