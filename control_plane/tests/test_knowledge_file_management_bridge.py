"""Uploaded knowledge-file listing + manual delete (v3 file management).

Covers:
  1. GET /api/demo/knowledge/files lists only uploaded real-material files
     (客户上传资料/*) with name/asset_id/version_id/created_by/can_delete.
  2. The uploader can delete their own file -> removed from the list, the
     vector-index slice removed (so the same file name can be re-uploaded)
     and the QUERY grant revoked (deleted file is no longer queryable).
  3. A non-owner cannot delete someone else's file.
  4. Deleting an unknown file returns 404.
  5. After delete, re-uploading the same file name succeeds (the Q use case:
     clearing built files so the next demo can re-upload).
"""

import hashlib
import httpx
import io
from pathlib import Path

from conftest import AsgiClient, RecordingHttpxClient, llm_environment


PROJECT_ROOT = Path(__file__).parents[2]
DEMO_ROOT = PROJECT_ROOT / "work" / "demo" / "financial-preassessment"
SOURCE_ROOT = DEMO_ROOT / "source"
IMPORT_MANIFEST_PATH = DEMO_ROOT / "import-manifest.json"
RULES_PATH = DEMO_ROOT / "rules" / "demo-bank-rules-v1.json"
WORKSPACE_ID = "workspace-a"

UPLOADED_DIR = "客户上传资料"


def _make_docx_bytes(text: str) -> bytes:
    from docx import Document

    document = Document()
    for line in text.split("\n"):
        document.add_paragraph(line)
    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()


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


def _list_files(client: AsgiClient):
    return client.get("/api/demo/knowledge/files")


def _delete_file(client: AsgiClient, file_name: str):
    return client.post(
        "/api/demo/knowledge/files/delete",
        json_body={"file_name": file_name},
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


def test_list_uploads_shows_only_uploaded_materials_with_owner_flag(
    repository, demo_identities, monkeypatch
) -> None:
    client = _build_client(repository, monkeypatch, demo_identities)
    _login(client, "alice", "demo-a-password")

    content = _make_docx_bytes("海川智能主营智能装备制造。")
    uploaded = _upload(client, content, "海川智能-资料.docx").json()

    response = _list_files(client)

    assert response.status_code == 200
    payload = response.json()
    assert payload["workspace_id"] == WORKSPACE_ID
    names = [item["name"] for item in payload["files"]]
    assert names == ["海川智能-资料.docx"]
    item = payload["files"][0]
    assert item["asset_id"] == uploaded["asset_id"]
    assert item["version_id"] == uploaded["version_id"]
    assert item["created_by"] == "user-a"
    assert item["can_delete"] is True


def test_uploader_can_delete_own_file_then_reupload_same_name(
    repository, demo_identities, monkeypatch
) -> None:
    client = _build_client(repository, monkeypatch, demo_identities)
    _login(client, "alice", "demo-a-password")

    content = _make_docx_bytes("海川智能主营智能装备制造。")
    _upload(client, content, "海川智能-资料.docx").json()

    response = _delete_file(client, "海川智能-资料.docx")

    assert response.status_code == 200
    assert response.json()["deleted"] == "海川智能-资料.docx"

    listed = _list_files(client).json()["files"]
    assert listed == []
    # QUERY grant for the deleted path is revoked: old asset is gone.
    ask = _ask_uploaded(client, "海川智能的主营业务？", "海川智能-资料.docx")
    assert ask.status_code == 404
    assert ask.json()["error"]["code"] == "uploaded_file_not_found"
    # The core Q use case: the same file name can be uploaded again.
    reuploaded = _upload(client, content, "海川智能-资料.docx")
    assert reuploaded.status_code == 200
    assert reuploaded.json()["index_state"] == "ready"


def test_non_owner_cannot_delete_someone_elses_file(
    repository, demo_identities, monkeypatch
) -> None:
    client = _build_client(repository, monkeypatch, demo_identities)
    _login(client, "alice", "demo-a-password")
    _upload(client, _make_docx_bytes("海川智能主营智能装备制造。"), "海川智能-资料.docx")

    _login(client, "bob", "demo-b-password")
    response = _delete_file(client, "海川智能-资料.docx")

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "delete_not_authorized"
    # The file is still there, and bob still cannot query it.
    assert [item["name"] for item in _list_files(client).json()["files"]] == [
        "海川智能-资料.docx"
    ]
    assert _ask_uploaded(client, "问题", "海川智能-资料.docx").status_code == 200


def test_bob_sees_alice_file_but_cannot_delete_and_list_marks_can_delete_false(
    repository, demo_identities, monkeypatch
) -> None:
    client = _build_client(repository, monkeypatch, demo_identities)
    _login(client, "alice", "demo-a-password")
    _upload(client, _make_docx_bytes("海川智能主营智能装备制造。"), "海川智能-资料.docx")

    _login(client, "bob", "demo-b-password")
    listed = _list_files(client).json()["files"]

    assert [item["name"] for item in listed] == ["海川智能-资料.docx"]
    assert listed[0]["can_delete"] is False


def test_delete_unknown_file_returns_not_found(
    repository, demo_identities, monkeypatch
) -> None:
    client = _build_client(repository, monkeypatch, demo_identities)
    _login(client, "alice", "demo-a-password")

    response = _delete_file(client, "从未上传过的文件.pdf")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "uploaded_file_not_found"


def test_delete_rejects_unsafe_file_name(
    repository, demo_identities, monkeypatch
) -> None:
    client = _build_client(repository, monkeypatch, demo_identities)
    _login(client, "alice", "demo-a-password")

    response = _delete_file(client, "../escape.pdf")

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_file_name"

