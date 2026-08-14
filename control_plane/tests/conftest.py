import asyncio
import json
from dataclasses import dataclass
from http.cookies import SimpleCookie
from typing import Any
from urllib.parse import urlencode

import pytest

from control_plane.app.domain import (
    Action,
    PermissionGrant,
    PrincipalType,
    RuleVersion,
    TrustedActorContext,
)
from control_plane.app.main import create_app
from control_plane.app.ports import (
    AssessmentResult,
    ExecutionResult,
    FilePlanPreview,
    UploadResult,
)
from control_plane.app.repository import InMemoryControlPlaneRepository
from control_plane.app.sessions import DemoIdentity


@dataclass(frozen=True, slots=True)
class RecordedUpload:
    actor: TrustedActorContext
    directory: str
    file_name: str
    content: bytes
    request_id: str


@dataclass(frozen=True, slots=True)
class RecordedPlanPreview:
    actor: TrustedActorContext
    normalized_operations: tuple[Any, ...]
    asset_snapshots: tuple[Any, ...]
    acl_snapshot: Any
    policy_version: str
    expires_at: str
    idempotency_key: str


@dataclass(frozen=True, slots=True)
class RecordedExecution:
    actor: TrustedActorContext
    control_plan_id: str
    executor_plan_id: str
    executor_plan_hash: str
    expected_plan_hash: str
    asset_snapshots: tuple[Any, ...]
    acl_snapshot: Any
    decision: Any
    confirmation_evidence: Any
    approval_evidence: Any
    idempotency_key: str


class RecordingFileExecutor:
    def __init__(self) -> None:
        self.calls: list[RecordedUpload] = []
        self.plan_previews: list[RecordedPlanPreview] = []
        self.executions: list[RecordedExecution] = []
        self.error: Exception | None = None
        self.execution_error: Exception | None = None
        self.execution_result = ExecutionResult(status="completed", operation_id="op-1")
        self.result = UploadResult(
            path="organized/report.txt",
            name="report.txt",
            size_bytes=7,
            content_fingerprint="sha256:executor-digest",
        )

    def upload(
        self,
        actor: TrustedActorContext,
        directory: str,
        file_name: str,
        content: bytes,
        request_id: str,
    ) -> UploadResult:
        self.calls.append(RecordedUpload(actor, directory, file_name, content, request_id))
        if self.error is not None:
            raise self.error
        return self.result

    def create_plan(
        self,
        actor: TrustedActorContext,
        normalized_operations: tuple[Any, ...],
        asset_snapshots: tuple[Any, ...],
        acl_snapshot: Any,
        policy_version: str,
        expires_at: str,
        idempotency_key: str,
    ) -> FilePlanPreview:
        self.plan_previews.append(
            RecordedPlanPreview(
                actor,
                normalized_operations,
                asset_snapshots,
                acl_snapshot,
                policy_version,
                expires_at,
                idempotency_key,
            )
        )
        return FilePlanPreview(
            impact_summary="1 operation previewed",
            executor_plan_id="executor-plan-1",
            executor_plan_hash="sha256:" + "e" * 64,
        )

    def confirm_and_execute(
        self,
        actor: TrustedActorContext,
        control_plan_id: str,
        executor_plan_id: str,
        executor_plan_hash: str,
        expected_plan_hash: str,
        asset_snapshots: tuple[Any, ...],
        acl_snapshot: Any,
        decision: Any,
        confirmation_evidence: Any,
        approval_evidence: Any,
        idempotency_key: str,
    ) -> ExecutionResult:
        self.executions.append(
            RecordedExecution(
                actor,
                control_plan_id,
                executor_plan_id,
                executor_plan_hash,
                expected_plan_hash,
                asset_snapshots,
                acl_snapshot,
                decision,
                confirmation_evidence,
                approval_evidence,
                idempotency_key,
            )
        )
        if self.execution_error is not None:
            raise self.execution_error
        return self.execution_result


@dataclass(frozen=True, slots=True)
class RecordedEnqueue:
    actor: TrustedActorContext
    asset_version: Any
    request_id: str


@dataclass(frozen=True, slots=True)
class RecordedAssessment:
    actor: TrustedActorContext
    asset_versions: tuple[Any, ...]
    rule_version: RuleVersion
    query_subject: str


class RecordingRagPort:
    def __init__(self) -> None:
        self.calls: list[RecordedEnqueue] = []
        self.error: Exception | None = None
        self.assessment_calls: list[RecordedAssessment] = []
        self.assessment_error: Exception | None = None
        self.assessment_result = AssessmentResult(
            match_score=82,
            result_level="MATCH",
            missing_materials=("近六个月流水",),
            citations=(
                {
                    "asset_version_id": "",
                    "chunk_id": "chunk-demo-1",
                    "page": 1,
                    "paragraph": 3,
                    "text": "must-not-enter-report",
                },
            ),
        )
        self.query_calls: list[tuple[TrustedActorContext, str, str]] = []
        self.query_result: dict[str, object] = {
            "status": "answered",
            "answer": "验收要求一：交付文件需包含最终版本与验收清单。",
            "reason": None,
            "retrieved_count": 1,
            "llm_invoked": True,
            "citations": [
                {
                    "asset_version_id": "version-acceptance-v1",
                    "chunk_id": "chunk-page-1",
                    "page_number": 1,
                    "paragraph_index": None,
                    "current_path": "验收交付/2026春季新品项目验收清单.pdf",
                    "version_path": "验收交付/2026春季新品项目验收清单.pdf",
                }
            ],
        }

    def enqueue_version(
        self, actor: TrustedActorContext, asset_version: Any, request_id: str
    ) -> None:
        self.calls.append(RecordedEnqueue(actor, asset_version, request_id))
        if self.error is not None:
            raise self.error

    def query(
        self, actor: TrustedActorContext, question: str, asset_id: str
    ) -> dict[str, object]:
        self.query_calls.append((actor, question, asset_id))
        return self.query_result

    def assess_versions(
        self,
        actor: TrustedActorContext,
        asset_versions: tuple[Any, ...],
        rule_version: RuleVersion,
        query_subject: str,
    ) -> AssessmentResult:
        self.assessment_calls.append(
            RecordedAssessment(actor, asset_versions, rule_version, query_subject)
        )
        if self.assessment_error is not None:
            raise self.assessment_error
        first_version_id = asset_versions[0].asset_version_id if asset_versions else ""
        citations = tuple(
            {
                **citation,
                "asset_version_id": citation.get("asset_version_id") or first_version_id,
            }
            for citation in self.assessment_result.citations
        )
        return AssessmentResult(
            match_score=self.assessment_result.match_score,
            result_level=self.assessment_result.result_level,
            missing_materials=self.assessment_result.missing_materials,
            citations=citations,
        )


@dataclass(frozen=True, slots=True)
class AsgiResponse:
    status_code: int
    raw_headers: tuple[tuple[bytes, bytes], ...]
    content: bytes

    @property
    def headers(self) -> dict[str, str]:
        return {
            key.decode("latin-1").lower(): value.decode("latin-1")
            for key, value in self.raw_headers
        }

    def json(self) -> Any:
        return json.loads(self.content)


class AsgiClient:
    """Small dependency-free ASGI client for the repository's existing venv."""

    def __init__(self, app: Any) -> None:
        self.app = app
        self.cookies: dict[str, str] = {}

    def get(self, path: str, **kwargs: Any) -> AsgiResponse:
        return self.request("GET", path, **kwargs)

    def post(self, path: str, **kwargs: Any) -> AsgiResponse:
        return self.request("POST", path, **kwargs)

    def request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, str] | None = None,
        headers: dict[str, str] | None = None,
        json_body: dict[str, Any] | None = None,
        data: dict[str, str] | None = None,
        files: dict[str, tuple[str, bytes, str]] | None = None,
    ) -> AsgiResponse:
        body = b""
        request_headers = {key.lower(): value for key, value in (headers or {}).items()}
        if json_body is not None:
            body = json.dumps(json_body).encode("utf-8")
            request_headers["content-type"] = "application/json"
        elif files is not None:
            body, content_type = _multipart_body(data or {}, files)
            request_headers["content-type"] = content_type
        elif data is not None:
            body = urlencode(data).encode("ascii")
            request_headers["content-type"] = "application/x-www-form-urlencoded"

        if self.cookies and "cookie" not in request_headers:
            request_headers["cookie"] = "; ".join(
                f"{name}={value}" for name, value in self.cookies.items()
            )
        request_headers["content-length"] = str(len(body))
        query_string = urlencode(params or {}).encode("ascii")
        response = asyncio.run(
            self._asgi_request(method, path, query_string, request_headers, body)
        )
        self._consume_response_cookies(response.raw_headers)
        return response

    async def _asgi_request(
        self,
        method: str,
        path: str,
        query_string: bytes,
        headers: dict[str, str],
        body: bytes,
    ) -> AsgiResponse:
        request_sent = False
        response_status = 500
        response_headers: tuple[tuple[bytes, bytes], ...] = ()
        response_body = bytearray()

        async def receive() -> dict[str, Any]:
            nonlocal request_sent
            if request_sent:
                return {"type": "http.disconnect"}
            request_sent = True
            return {"type": "http.request", "body": body, "more_body": False}

        async def send(message: dict[str, Any]) -> None:
            nonlocal response_status, response_headers
            if message["type"] == "http.response.start":
                response_status = message["status"]
                response_headers = tuple(message.get("headers", ()))
            elif message["type"] == "http.response.body":
                response_body.extend(message.get("body", b""))

        scope = {
            "type": "http",
            "asgi": {"version": "3.0", "spec_version": "2.3"},
            "http_version": "1.1",
            "method": method,
            "scheme": "http",
            "path": path,
            "raw_path": path.encode("ascii"),
            "query_string": query_string,
            "root_path": "",
            "headers": tuple(
                (key.encode("latin-1"), value.encode("latin-1"))
                for key, value in headers.items()
            ),
            "client": ("testclient", 50000),
            "server": ("testserver", 80),
        }
        try:
            await self.app(scope, receive, send)
        except Exception:
            if not response_headers:
                raise
        return AsgiResponse(response_status, response_headers, bytes(response_body))

    def _consume_response_cookies(
        self, response_headers: tuple[tuple[bytes, bytes], ...]
    ) -> None:
        for key, value in response_headers:
            if key.lower() != b"set-cookie":
                continue
            parsed = SimpleCookie()
            parsed.load(value.decode("latin-1"))
            for name, morsel in parsed.items():
                if morsel["max-age"] == "0" or not morsel.value:
                    self.cookies.pop(name, None)
                else:
                    self.cookies[name] = morsel.value


def _multipart_body(
    data: dict[str, str], files: dict[str, tuple[str, bytes, str]]
) -> tuple[bytes, str]:
    boundary = "control-plane-test-boundary"
    chunks: list[bytes] = []
    for name, value in data.items():
        chunks.extend(
            (
                f"--{boundary}\r\n".encode("ascii"),
                f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode("ascii"),
                value.encode("utf-8"),
                b"\r\n",
            )
        )
    for name, (file_name, content, content_type) in files.items():
        chunks.extend(
            (
                f"--{boundary}\r\n".encode("ascii"),
                (
                    f'Content-Disposition: form-data; name="{name}"; '
                    f'filename="{file_name}"\r\n'
                ).encode("ascii"),
                f"Content-Type: {content_type}\r\n\r\n".encode("ascii"),
                content,
                b"\r\n",
            )
        )
    chunks.append(f"--{boundary}--\r\n".encode("ascii"))
    return b"".join(chunks), f"multipart/form-data; boundary={boundary}"


@pytest.fixture
def repository() -> InMemoryControlPlaneRepository:
    repo = InMemoryControlPlaneRepository()
    repo.add_permission_grant(
        PermissionGrant(
            grant_id="user-a-upload",
            workspace_id="workspace-a",
            context_version="acl_2026_08_13",
            principal_type=PrincipalType.USER,
            principal_id="user-a",
            action=Action.UPLOAD,
            path_prefix="organized",
        )
    )
    return repo


@pytest.fixture
def file_executor() -> RecordingFileExecutor:
    return RecordingFileExecutor()


@pytest.fixture
def rag_port() -> RecordingRagPort:
    return RecordingRagPort()


@pytest.fixture
def demo_identities() -> dict[str, DemoIdentity]:
    return {
        "alice": DemoIdentity(
            username="alice",
            password="demo-a-password",
            actor_id="user-a",
            workspace_id="workspace-a",
            context_version="acl_2026_08_13",
            group_ids=frozenset({"staff"}),
            role_ids=frozenset({"role-member-demo"}),
        ),
        "bob": DemoIdentity(
            username="bob",
            password="demo-b-password",
            actor_id="user-b",
            workspace_id="workspace-a",
            context_version="acl_2026_08_13",
            role_ids=frozenset({"role-member-demo", "role-approver-demo"}),
        ),
        "carol": DemoIdentity(
            username="carol",
            password="demo-c-password",
            actor_id="user-c",
            workspace_id="workspace-a",
            context_version="acl_2026_08_13",
            role_ids=frozenset({"role-member-demo"}),
        ),
        "mallory": DemoIdentity(
            username="mallory",
            password="demo-m-password",
            actor_id="user-m",
            workspace_id="workspace-b",
            context_version="acl_2026_08_13",
            role_ids=frozenset({"role-approver-demo"}),
        ),
    }


@pytest.fixture
def app(repository, file_executor, rag_port, demo_identities):
    return create_app(
        repository=repository,
        file_executor=file_executor,
        rag_port=rag_port,
        demo_identities=demo_identities,
        internal_service_key="demo-internal-key",
        approver_role_id="role-approver-demo",
    )


@pytest.fixture
def client(app) -> AsgiClient:
    return AsgiClient(app)


@pytest.fixture
def client_as_a(client: AsgiClient) -> AsgiClient:
    response = client.post(
        "/api/session/login",
        json_body={"username": "alice", "password": "demo-a-password"},
    )
    assert response.status_code == 200
    return client
