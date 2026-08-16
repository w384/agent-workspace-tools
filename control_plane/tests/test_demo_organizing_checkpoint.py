import hashlib
import json
import shutil
from pathlib import Path

from fastapi.testclient import TestClient
import pytest

import httpx

from control_plane.app.demo_rag import DemoRagPort
from control_plane.app.domain import Action, PermissionGrant, PrincipalType, TrustedActorContext

from conftest import RecordingHttpxClient, llm_environment

from control_plane.app.local_file_executor import LocalWorkspaceFileExecutorAdapter
from control_plane.app.main import create_app as create_control_plane_app
from control_plane.app.repository import InMemoryControlPlaneRepository
from control_plane.app.service import ControlPlaneService, ExecutorExecutionFailedError
from control_plane.app.sessions import DemoIdentity
from service.app.main import create_app as create_workspace_app
from service.app.rag.contracts import ActiveAssetVersion
from service.app.rag.demo_document_parser import DemoDocumentParser
from service.app.rag.ingestion import IngestionRequest
from service.app.rag.index import InMemorySearchIndex

from conftest import AsgiClient


PROJECT_ROOT = Path(__file__).parents[2]
SAMPLE_SOURCE = PROJECT_ROOT / "work" / "demo" / "public-drive-ai-organizing" / "source"
PLAN_FIXTURE = (
    PROJECT_ROOT
    / "work"
    / "demo"
    / "public-drive-ai-organizing"
    / "fixtures"
    / "a-low-risk-organizing-plan.json"
)


class _WorkspaceClient:
    def __init__(self, client: TestClient, api_key: str) -> None:
        self._client = client
        self._headers = {"X-API-Key": api_key}

    def create_plan(self, operations, *, user_id: str):
        response = self._client.post(
            "/plans",
            params={"user_id": user_id},
            json={"operations": operations},
            headers=self._headers,
        )
        assert response.status_code == 201
        return response.json()

    def issue_approval_token(self, plan_id: str):
        response = self._client.post(
            f"/plans/{plan_id}/approval-token", headers=self._headers
        )
        assert response.status_code == 200
        return response.json()

    def execute_plan(self, plan_id: str, approval_token: str, *, plan_hash: str, user_id: str):
        response = self._client.post(
            f"/plans/{plan_id}/execute",
            params={"user_id": user_id},
            json={"approval_token": approval_token, "plan_hash": plan_hash},
            headers=self._headers,
        )
        assert response.status_code == 200
        return response.json()


def test_controlled_sample_plan_moves_files_and_preserves_versioned_rag_reference(
    tmp_path: Path,
    monkeypatch,
):
    RecordingHttpxClient.requests = []
    monkeypatch.setattr(httpx, "Client", RecordingHttpxClient)
    fixture = json.loads(PLAN_FIXTURE.read_text(encoding="utf-8"))
    assert fixture["source_type"] == "fixed-demo-fixture-not-llm-runtime"
    operations = tuple(fixture["operations"])

    workspace_root = tmp_path / "controlled-demo-workspace"
    source_fingerprints = _copy_plan_sources(workspace_root, operations)
    (workspace_root / "验收交付" / "输出稿").mkdir(parents=True)
    actor = _actor()
    repository = _repository_for_plan(actor, operations, source_fingerprints)
    parser = DemoDocumentParser(workspace_root)
    index = InMemorySearchIndex(scorer=lambda _question, _chunk: 0.95)
    assets = _index_before_move(repository, index, parser, actor, operations)
    workspace_api_key = "controlled-demo-api-key"
    executor = LocalWorkspaceFileExecutorAdapter(
        _WorkspaceClient(
            TestClient(create_workspace_app(workspace_root, api_key=workspace_api_key)),
            workspace_api_key,
        )
    )
    service = ControlPlaneService(
        repository,
        executor,
        _NoopRagPort(),
        approver_role_id="role-approver-demo",
    )

    planned = service.create_plan(
        actor,
        operations=operations,
        expires_at="2099-01-01T00:00:00Z",
    )
    confirmed = service.confirm_plan(
        actor,
        planned.plan.plan_id,
        planned.plan.plan_hash,
        "controlled-demo-confirm-1",
    )

    assert planned.decision.state.value == "SELF_CONFIRM"
    assert planned.plan.state == "pending_confirmation"
    assert planned.plan.plan_hash.startswith("sha256:")
    assert confirmed.execution_job is not None
    assert confirmed.execution_job.state == "completed"
    assert {event.event_type for event in repository.list_audit_events()} >= {
        "plan_created",
        "execution_completed",
    }
    for operation in operations:
        source = workspace_root / operation["source_path"]
        target = workspace_root / operation["target_path"]
        assert not source.exists()
        assert target.is_file()
        assert _sha256(target) == source_fingerprints[operation["source_path"]]

    moved_asset = assets[operations[0]["source_path"]]
    moved_version = repository.get_asset_version(moved_asset.active_version_id)
    from service.app.rag.llm import build_llm_answer_generator

    rag_port = DemoRagPort(
        repository=repository,
        search_index=index,
        answer_generator=build_llm_answer_generator(llm_environment()),
    )
    bff = create_control_plane_app(
        repository=repository,
        file_executor=executor,
        rag_port=rag_port,
        demo_identities={
            "alice": DemoIdentity(
                username="alice",
                password="controlled-demo-password",
                actor_id=actor.actor_id,
                workspace_id=actor.workspace_id,
                context_version=actor.context_version,
                role_ids=actor.role_ids,
            )
        },
        internal_service_key="controlled-demo-internal-key",
        approver_role_id="role-approver-demo",
    )
    client = AsgiClient(bff)
    assert client.post(
        "/api/session/login",
        json_body={"username": "alice", "password": "controlled-demo-password"},
    ).status_code == 200
    query = client.post(
        "/api/retrieval/query",
        json_body={
            "question": "主视觉交付要求是什么？",
            "asset_id": moved_asset.asset_id,
        },
    )

    assert query.status_code == 200
    citation = query.json()["citations"][0]
    assert query.json()["status"] == "ANSWERED"
    assert query.json()["answer"] == "LLM 依据授权证据生成的回答"
    assert query.json()["llm_invoked"] is True
    assert len(RecordingHttpxClient.requests) == 1
    assert citation["asset_version_id"] == moved_version.asset_version_id
    assert citation["current_path"] == operations[0]["target_path"]
    assert citation["version_path"] == operations[0]["source_path"]


def test_controlled_sample_plan_fingerprint_change_fails_without_writing(
    tmp_path: Path,
):
    fixture = json.loads(PLAN_FIXTURE.read_text(encoding="utf-8"))
    operations = tuple(fixture["operations"])
    workspace_root = tmp_path / "controlled-demo-workspace"
    source_fingerprints = _copy_plan_sources(workspace_root, operations)
    (workspace_root / "验收交付" / "输出稿").mkdir(parents=True)
    actor = _actor()
    repository = _repository_for_plan(actor, operations, source_fingerprints)
    workspace_api_key = "controlled-demo-api-key"
    executor = LocalWorkspaceFileExecutorAdapter(
        _WorkspaceClient(
            TestClient(create_workspace_app(workspace_root, api_key=workspace_api_key)),
            workspace_api_key,
        )
    )
    service = ControlPlaneService(
        repository,
        executor,
        _NoopRagPort(),
        approver_role_id="role-approver-demo",
    )
    planned = service.create_plan(
        actor,
        operations=operations,
        expires_at="2099-01-01T00:00:00Z",
    )
    changed_source = workspace_root / operations[0]["source_path"]
    changed_source.write_bytes(changed_source.read_bytes() + b"external-change")

    with pytest.raises(ExecutorExecutionFailedError):
        service.confirm_plan(
            actor,
            planned.plan.plan_id,
            planned.plan.plan_hash,
            "controlled-demo-confirm-fingerprint-change",
        )

    assert changed_source.is_file()
    assert not (workspace_root / operations[0]["target_path"]).exists()
    assert not (workspace_root / operations[1]["target_path"]).exists()
    assert repository.get_plan(planned.plan.plan_id).state == "failed"
    assert {event.event_type for event in repository.list_audit_events()} >= {
        "plan_created",
        "execution_failed",
    }


def _actor() -> TrustedActorContext:
    return TrustedActorContext(
        actor_id="user-a",
        workspace_id="workspace-demo",
        context_version="acl-demo-v1",
        session_id="session-demo-a",
        request_id="request-demo-a",
        run_id="run-demo-a",
        role_ids=frozenset({"role-member-demo"}),
    )


def _copy_plan_sources(workspace_root: Path, operations):
    fingerprints = {}
    for operation in operations:
        source_path = str(operation["source_path"])
        source = SAMPLE_SOURCE / source_path
        destination = workspace_root / source_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        fingerprints[source_path] = _sha256(destination)
    return fingerprints


def _repository_for_plan(actor, operations, fingerprints):
    repository = InMemoryControlPlaneRepository()
    for grant_id, prefix in (("move-output", "输出稿"), ("move-delivery", "验收交付")):
        repository.add_permission_grant(
            PermissionGrant(
                grant_id=grant_id,
                workspace_id=actor.workspace_id,
                context_version=actor.context_version,
                principal_type=PrincipalType.USER,
                principal_id=actor.actor_id,
                action=Action.MOVE_RENAME,
                path_prefix=prefix,
            )
        )
        repository.add_permission_grant(
            PermissionGrant(
                grant_id=f"query-{grant_id}",
                workspace_id=actor.workspace_id,
                context_version=actor.context_version,
                principal_type=PrincipalType.USER,
                principal_id=actor.actor_id,
                action=Action.QUERY,
                path_prefix=prefix,
            )
        )
    for operation in operations:
        source_path = str(operation["source_path"])
        asset = repository.get_or_create_asset(
            actor.workspace_id,
            source_path,
            source_path.rsplit("/", maxsplit=1)[-1],
            actor.actor_id,
        )
        version = repository.create_asset_version(
            asset.asset_id,
            f"sha256:{fingerprints[source_path]}",
            source_path,
        )
        for state in ("parsing", "indexed", "ready"):
            repository.transition_asset_version(version.asset_version_id, state)
        repository.activate_asset_version(version.asset_version_id)
    return repository


def _index_before_move(repository, index, parser, actor, operations):
    assets = {}
    for operation in operations:
        source_path = str(operation["source_path"])
        asset = repository.find_asset_by_path(actor.workspace_id, source_path)
        assert asset is not None and asset.active_version_id is not None
        version = repository.get_asset_version(asset.active_version_id)
        mime_type = (
            "application/pdf"
            if source_path.endswith(".pdf")
            else "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        )
        chunks = parser.parse(
            IngestionRequest(
                tenant_id=actor.workspace_id,
                target_version=ActiveAssetVersion(asset.asset_id, version.asset_version_id),
                source_ref=source_path,
                content_fingerprint=version.content_fingerprint,
                mime_type=mime_type,
                size_bytes=(SAMPLE_SOURCE / source_path).stat().st_size,
            )
        )
        index.replace_version(
            tenant_id=actor.workspace_id,
            active_version=ActiveAssetVersion(asset.asset_id, version.asset_version_id),
            chunks=chunks,
        )
        assets[source_path] = asset
    return assets


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class _NoopRagPort:
    def enqueue_version(self, actor, asset_version, request_id) -> None:
        raise AssertionError("RAG enqueue is not part of the fixed-plan checkpoint")
