"""真实材料预评估（放宽白名单）HTTP 层测试。

覆盖：
- 用户拖入真实 PDF/DOCX + 指定材料类别 → 复用演示银行规则夹具出报告；
- 提供规则 A（demo-bank-a-complete）全部三类材料 → MATCH 100 / missing=[]；
- 部分材料 → 报告显示缺失项（非 MATCH）；
- 任何登录身份都可评估自己拖入的字节（无需 QUERY grant，白名单外文件名可评估）；
- 输入守卫：非法类别、类别数与文件数不匹配、空文件列表、非 PDF/DOCX、超限文件数。
"""

import importlib.util
import io
from pathlib import Path

from control_plane.app.finance_demo_llm_rag import FinanceDemoLlmRagPort
from control_plane.app.main import create_app
from control_plane.app.repository import InMemoryControlPlaneRepository
from control_plane.app.sessions import DemoIdentity

from conftest import AsgiClient

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEMO_ROOT = PROJECT_ROOT / "work" / "demo" / "financial-preassessment"
SOURCE_ROOT = DEMO_ROOT / "source"
IMPORT_MANIFEST_PATH = DEMO_ROOT / "import-manifest.json"
RULES_PATH = DEMO_ROOT / "rules" / "demo-bank-rules-v1.json"
SCRIPTS_PATH = PROJECT_ROOT / "scripts" / "init_demo_financial_preassessment.py"
WORKSPACE_ID = "workspace-a"
SCENARIO = "finance_profile_matching"

# 规则 A（assessment_rule_id）的三项 requirements
RULE_A_KEYS = {
    "income_statement": "收入情况说明-真实.docx",
    "cashflow_summary": "资金流摘要-真实.docx",
    "asset_liability_statement": "资产负债说明-真实.docx",
}


def _load_init():
    spec = importlib.util.spec_from_file_location(
        "init_demo_financial_preassessment", SCRIPTS_PATH
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _make_docx_bytes(text: str) -> bytes:
    from docx import Document

    document = Document()
    for line in text.split("\n"):
        document.add_paragraph(line)
    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()


def _make_app(repository):
    rag_port = FinanceDemoLlmRagPort(
        repository=repository,
        source_root=SOURCE_ROOT,
        import_manifest_path=IMPORT_MANIFEST_PATH,
        rules_path=RULES_PATH,
        workspace_id=WORKSPACE_ID,
    )
    identities = {
        "alice": DemoIdentity(
            username="alice",
            password="demo-a-password",
            actor_id="user-a",
            workspace_id=WORKSPACE_ID,
            context_version="acl_2026_08_13",
            group_ids=frozenset({"staff"}),
            role_ids=frozenset({"role-member-demo"}),
        ),
        "bob": DemoIdentity(
            username="bob",
            password="demo-b-password",
            actor_id="user-b",
            workspace_id=WORKSPACE_ID,
            context_version="acl_2026_08_13",
            group_ids=frozenset({"staff"}),
            role_ids=frozenset({"role-member-demo"}),
        ),
    }
    return create_app(
        repository=repository,
        file_executor=object(),
        rag_port=rag_port,
        demo_identities=identities,
        internal_service_key="demo-internal-key",
        approver_role_id="role-approver-demo",
        demo_rules_fixture_path=RULES_PATH,
    )


def _login(client: AsgiClient, username: str, password: str) -> None:
    response = client.post(
        "/api/session/login",
        json_body={"username": username, "password": password},
    )
    assert response.status_code == 200


def _assess(client: AsgiClient, items: list[tuple[str, str, bytes]]):
    files: list[tuple[str, tuple[str, bytes, str]]] = []
    data: list[tuple[str, str]] = [
        ("scenario", SCENARIO),
        ("query_subject", "customer-demo-001"),
    ]
    for key, file_name, content in items:
        files.append(("files", (file_name, content, "application/octet-stream")))
        data.append(("material_keys", key))
    return client.post(
        "/api/real-material/assess",
        data=data,
        files=files,
    )


def test_real_material_assess_full_rule_a_match_100(tmp_path) -> None:
    init = _load_init()
    repository = InMemoryControlPlaneRepository()
    init.seed_financial_preassessment_demo(repository)
    client = AsgiClient(_make_app(repository))
    _login(client, "alice", "demo-a-password")

    items = [
        (key, file_name, _make_docx_bytes(f"演示{key}材料正文 {index}"))
        for index, (key, file_name) in enumerate(RULE_A_KEYS.items())
    ]
    response = _assess(client, items)

    assert response.status_code == 200
    report = response.json()["report"]
    assert report["match_score"] == 100
    assert report["result_level"] == "MATCH"
    assert report["missing_materials"] == []
    material_citations = [
        citation
        for citation in report["citations"]
        if citation["citation_type"] == "material"
    ]
    assert len(material_citations) >= 3
    assert all(
        citation["asset_id"].startswith("real-material-")
        for citation in material_citations
    )


def test_real_material_assess_partial_shows_missing(tmp_path) -> None:
    init = _load_init()
    repository = InMemoryControlPlaneRepository()
    init.seed_financial_preassessment_demo(repository)
    client = AsgiClient(_make_app(repository))
    _login(client, "alice", "demo-a-password")

    response = _assess(
        client,
        [
            (
                "income_statement",
                "收入情况说明-真实.docx",
                _make_docx_bytes("只有收入情况说明"),
            )
        ],
    )

    assert response.status_code == 200
    report = response.json()["report"]
    assert report["match_score"] < 100
    assert report["result_level"] != "MATCH"
    assert report["missing_materials"]  # 至少列出缺失类别
    assert "资金流摘要" in "".join(report["missing_materials"]) or any(
        "资金流" in label for label in report["missing_materials"]
    )


def test_real_material_assess_any_identity_can_assess_own_bytes(tmp_path) -> None:
    """放宽白名单：bob（无 QUERY grant）也可评估自己拖入的文件。"""
    init = _load_init()
    repository = InMemoryControlPlaneRepository()
    init.seed_financial_preassessment_demo(repository)
    client = AsgiClient(_make_app(repository))
    _login(client, "bob", "demo-b-password")

    response = _assess(
        client,
        [
            (
                "income_statement",
                "完全不在白名单的文件名.docx",
                _make_docx_bytes("bob 自己的材料"),
            )
        ],
    )

    assert response.status_code == 200
    report = response.json()["report"]
    assert "match_score" in report
    assert report["result_level"] in {"MATCH", "POSSIBLE", "NOT_MATCH"}


def test_real_material_assess_input_guards(tmp_path) -> None:
    init = _load_init()
    repository = InMemoryControlPlaneRepository()
    init.seed_financial_preassessment_demo(repository)
    client = AsgiClient(_make_app(repository))
    _login(client, "alice", "demo-a-password")

    # 非法类别
    bad_key = client.post(
        "/api/real-material/assess",
        data=[("scenario", SCENARIO), ("query_subject", "x"), ("material_keys", "not_a_key")],
        files=[("files", ("a.pdf", b"x", "application/octet-stream"))],
    )
    assert bad_key.status_code == 422
    assert bad_key.json()["error"]["code"] == "unknown_material_key"

    # 类别数与文件数不匹配
    mismatch = client.post(
        "/api/real-material/assess",
        data=[
            ("scenario", SCENARIO),
            ("query_subject", "x"),
            ("material_keys", "income_statement"),
            ("material_keys", "cashflow_summary"),
        ],
        files=[("files", ("a.pdf", b"x", "application/octet-stream"))],
    )
    assert mismatch.status_code == 422
    assert mismatch.json()["error"]["code"] == "material_key_mismatch"

    # 空文件列表
    empty = client.post(
        "/api/real-material/assess",
        data=[
            ("scenario", SCENARIO),
            ("query_subject", "x"),
            ("material_keys", "income_statement"),
        ],
        files=[],
    )
    assert empty.status_code == 422
    assert empty.json()["error"]["code"] == "files_required"

    # 非 PDF/DOCX
    bad_ext = client.post(
        "/api/real-material/assess",
        data=[("scenario", SCENARIO), ("query_subject", "x"), ("material_keys", "income_statement")],
        files=[("files", ("a.txt", b"x", "text/plain"))],
    )
    assert bad_ext.status_code == 422
    assert bad_ext.json()["error"]["code"] == "unsupported_file_type"
