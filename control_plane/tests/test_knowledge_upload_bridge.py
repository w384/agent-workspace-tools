"""Real-material upload -> auto-index -> authorized query (v3 knowledge pipeline).

Covers:
  1. Uploading a real PDF/DOCX builds the in-memory vector index, transitions
     the asset version to ready, activates it and binds a real SHA-256 fingerprint.
  2. The uploader is auto-granted QUERY on that exact file and can ask ->
     ANSWERED with a real LLM answer and citations.
  3. Another identity (bob) without a grant gets DENIED with zero LLM calls.
  4. Input guards: non PDF/DOCX, oversize, path-traversal names and duplicate
     uploads are rejected; audit never retains content or credentials.
"""

import hashlib
import io
from pathlib import Path

import httpx
import pytest

from conftest import AsgiClient, RecordingHttpxClient, llm_environment
from control_plane.app.repository import InMemoryControlPlaneRepository


PROJECT_ROOT = Path(__file__).parents[2]
DEMO_ROOT = PROJECT_ROOT / "work" / "demo" / "financial-preassessment"
SOURCE_ROOT = DEMO_ROOT / "source"
IMPORT_MANIFEST_PATH = DEMO_ROOT / "import-manifest.json"
RULES_PATH = DEMO_ROOT / "rules" / "demo-bank-rules-v1.json"
WORKSPACE_ID = "workspace-a"
MAX_SOURCE_BYTES = 2 * 1024 * 1024

UPLOADED_DIR = "客户上传资料"
SAMPLE_PDF_NAME = "收入情况说明.pdf"

DOCX_TEXT = (
    "海川智能主营业务为智能装备制造，2025 年营业收入较上年增长约 22%，"
    "主要客户为华东地区制造企业，法定代表人陈国华。"
)


def _make_docx_bytes(text: str = DOCX_TEXT) -> bytes:
    from docx import Document

    document = Document()
    for line in text.split("\n"):
        document.add_paragraph(line)
    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()


def _sample_bytes(file_name: str) -> bytes:
    return (SOURCE_ROOT / "客户模拟资料" / file_name).read_bytes()


def _login(client: AsgiClient, username: str, password: str) -> None:
    response = client.post(
        "/api/session/login",
        json_body={"username": username, "password": password},
    )
    assert response.status_code == 200


def _upload(client: AsgiClient, content: bytes, file_name: str):
    return client.post(
        "/api/demo/knowledge/upload",
        files={"file": (file_name, content, "application/octet-stream")},
    )


def _ask_uploaded(client: AsgiClient, question: str, file_name: str):
    return client.post(
        "/api/demo/knowledge/query",
        json_body={"question": question, "file_name": file_name},
    )


def _build_client(repository, monkeypatch, demo_identities) -> AsgiClient:
    from control_plane.app.finance_demo_llm_rag import FinanceDemoLlmRagPort
    from control_plane.app.main import create_app
    from service.app.rag.llm import build_llm_answer_generator

    RecordingHttpxClient.requests = []
    monkeypatch.setattr(httpx, "Client", RecordingHttpxClient)
    rag_port = FinanceDemoLlmRagPort(
        repository=repository,
        source_root=SOURCE_ROOT,
        import_manifest_path=IMPORT_MANIFEST_PATH,
        rules_path=RULES_PATH,
        workspace_id=WORKSPACE_ID,
        answer_generator=build_llm_answer_generator(llm_environment()),
    )
    app = create_app(
        repository=repository,
        file_executor=object(),
        rag_port=rag_port,
        demo_identities=demo_identities,
        internal_service_key="demo-internal-key",
        approver_role_id="role-approver-demo",
        demo_rules_fixture_path=RULES_PATH,
    )
    return AsgiClient(app)


def test_upload_docx_builds_index_ready_with_real_fingerprint(
    repository, demo_identities, monkeypatch
) -> None:
    client = _build_client(repository, monkeypatch, demo_identities)
    _login(client, "alice", "demo-a-password")

    content = _make_docx_bytes()
    response = _upload(client, content, "海川智能-资料.docx")

    assert response.status_code == 200
    payload = response.json()
    assert payload["index_state"] == "ready"
    assert payload["content_fingerprint"] == (
        "sha256:" + hashlib.sha256(content).hexdigest()
    )
    assert payload["chunk_count"] >= 1
    assert payload["path"] == f"{UPLOADED_DIR}/海川智能-资料.docx"

    asset = repository.get_asset(payload["asset_id"])
    assert asset.active_version_id == payload["version_id"]


def test_uploader_can_query_uploaded_docx_answered_with_llm_and_citations(
    repository, demo_identities, monkeypatch
) -> None:
    client = _build_client(repository, monkeypatch, demo_identities)
    _login(client, "alice", "demo-a-password")

    content = _make_docx_bytes()
    uploaded = _upload(client, content, "海川智能-资料.docx").json()

    response = _ask_uploaded(
        client, "海川智能的主营业务是什么？", uploaded["file_name"]
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ANSWERED"
    assert payload["answer"] == "LLM 依据授权证据生成的回答"
    assert payload["llm_invoked"] is True
    assert payload["retrieved_count"] >= 1
    assert payload["citations"]
    assert payload["citations"][0]["asset_id"] == uploaded["asset_id"]
    assert payload["citations"][0]["asset_version_id"] == uploaded["version_id"]
    assert len(RecordingHttpxClient.requests) == 1


def test_pdf_upload_builds_index_ready(
    repository, demo_identities, monkeypatch
) -> None:
    client = _build_client(repository, monkeypatch, demo_identities)
    _login(client, "alice", "demo-a-password")

    content = _sample_bytes(SAMPLE_PDF_NAME)
    response = _upload(client, content, "新上传-收入说明.pdf")

    assert response.status_code == 200
    payload = response.json()
    assert payload["index_state"] == "ready"
    assert payload["chunk_count"] >= 1
    assert payload["content_fingerprint"] == (
        "sha256:" + hashlib.sha256(content).hexdigest()
    )


def test_bob_without_grant_denied_on_alice_uploaded_file_zero_llm_calls(
    repository, demo_identities, monkeypatch
) -> None:
    client = _build_client(repository, monkeypatch, demo_identities)
    _login(client, "alice", "demo-a-password")

    content = _make_docx_bytes()
    uploaded = _upload(client, content, "海川智能-资料.docx").json()

    _login(client, "bob", "demo-b-password")
    response = _ask_uploaded(
        client, "海川智能的主营业务是什么？", uploaded["file_name"]
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "DENIED"
    assert payload["reason"] == "ACCESS_DENIED"
    assert payload["answer"] is None
    assert payload["llm_invoked"] is False
    assert payload["retrieved_count"] == 0
    assert payload["citations"] == []
    assert RecordingHttpxClient.requests == []


def test_bob_can_upload_and_query_his_own_file(
    repository, demo_identities, monkeypatch
) -> None:
    client = _build_client(repository, monkeypatch, demo_identities)
    _login(client, "bob", "demo-b-password")

    content = _make_docx_bytes("宏图贸易主营电子元器件批发，2025 年回款稳定。")
    uploaded = _upload(client, content, "宏图贸易-资料.docx").json()

    response = _ask_uploaded(client, "宏图贸易的主营业务是什么？", uploaded["file_name"])

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ANSWERED"
    assert payload["llm_invoked"] is True


def test_upload_rejects_non_pdf_docx(
    repository, demo_identities, monkeypatch
) -> None:
    client = _build_client(repository, monkeypatch, demo_identities)
    _login(client, "alice", "demo-a-password")

    response = _upload(client, b"plain text not a document", "notes.txt")

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "unsupported_file_type"
    assert repository.list_assets(WORKSPACE_ID) == []


def test_upload_rejects_oversize_file(
    repository, demo_identities, monkeypatch
) -> None:
    client = _build_client(repository, monkeypatch, demo_identities)
    _login(client, "alice", "demo-a-password")

    response = _upload(client, b"x" * (MAX_SOURCE_BYTES + 1), "big.pdf")

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "file_too_large"


@pytest.mark.parametrize(
    "file_name",
    ("../escape.pdf", "a\\b.pdf", ".hidden.pdf", "dir/a.pdf"),
)
def test_upload_rejects_path_traversal_names(
    repository, demo_identities, monkeypatch, file_name
) -> None:
    client = _build_client(repository, monkeypatch, demo_identities)
    _login(client, "alice", "demo-a-password")

    response = _upload(client, _make_docx_bytes(), file_name)

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_file_name"
    assert repository.list_assets(WORKSPACE_ID) == []


def test_duplicate_upload_of_same_name_conflicts(
    repository, demo_identities, monkeypatch
) -> None:
    client = _build_client(repository, monkeypatch, demo_identities)
    _login(client, "alice", "demo-a-password")

    content = _make_docx_bytes()
    first = _upload(client, content, "海川智能-资料.docx")
    assert first.status_code == 200

    second = _upload(client, content, "海川智能-资料.docx")

    assert second.status_code == 409
    assert second.json()["error"]["code"] == "upload_target_exists"


def test_query_unknown_uploaded_file_not_found(
    repository, demo_identities, monkeypatch
) -> None:
    client = _build_client(repository, monkeypatch, demo_identities)
    _login(client, "alice", "demo-a-password")

    response = _ask_uploaded(client, "问题", "从未上传过的文件.pdf")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "uploaded_file_not_found"


def test_upload_audit_never_retains_content_or_credentials(
    repository, demo_identities, monkeypatch
) -> None:
    client = _build_client(repository, monkeypatch, demo_identities)
    _login(client, "alice", "demo-a-password")

    content = _make_docx_bytes("海川智能 内部敏感经营数据 2025")
    _upload(client, content, "海川智能-资料.docx")

    serialized = repr(repository.list_audit_events())
    for sensitive in (
        "海川智能 内部敏感经营数据 2025",
        "demo-a-password",
        client.cookies["cp_session"],
        "demo-internal-key",
    ):
        assert sensitive not in serialized
