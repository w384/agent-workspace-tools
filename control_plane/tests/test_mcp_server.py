"""MCP 暴露层测试：Policy / Assess / Query / Audit 四个工具 + stdio 协议子集。

Covers:
  1. initialize 握手返回 protocolVersion / serverInfo / capabilities。
  2. tools/list 暴露 4 个演示工具。
  3. authz_check：alice（已授权）-> ALLOW，bob（无 QUERY grant）-> DENY。
  4. assess_materials：alice 用 seed 资产 -> MATCH 100 + bank_label。
  5. query_knowledge：alice 真实 LLM -> ANSWERED / llm_invoked=True；
     bob -> DENIED / llm_invoked=False / LLM 零调用。
  6. list_audit_events 返回留痕列表。
  7. 错误路径：未知工具 / 缺参数 -> MCP error（-32602），不崩 stdio 循环。
"""

import json
from pathlib import Path

import httpx

from conftest import RecordingHttpxClient, llm_environment
from control_plane.app.mcp_server import (
    PROTOCOL_VERSION,
    MCPDemoServer,
    _demo_identities,
)
from control_plane.app.repository import InMemoryControlPlaneRepository


PROJECT_ROOT = Path(__file__).parents[2]
DEMO_ROOT = PROJECT_ROOT / "work" / "demo" / "financial-preassessment"
SOURCE_ROOT = DEMO_ROOT / "source"
IMPORT_MANIFEST_PATH = DEMO_ROOT / "import-manifest.json"
RULES_PATH = DEMO_ROOT / "rules" / "demo-bank-rules-v1.json"
WORKSPACE_ID = "workspace-a"


def _manifest() -> dict[str, object]:
    return json.loads(IMPORT_MANIFEST_PATH.read_text(encoding="utf-8"))


def _seeded_repository() -> InMemoryControlPlaneRepository:
    from scripts.init_demo_financial_preassessment import seed_financial_preassessment_demo

    repository = InMemoryControlPlaneRepository()
    seed_financial_preassessment_demo(repository)
    return repository


def _build_server(
    *,
    repository: InMemoryControlPlaneRepository | None = None,
    answer_generator: object | None = None,
    monkeypatch=None,
) -> MCPDemoServer:
    from control_plane.app.finance_demo_llm_rag import FinanceDemoLlmRagPort
    from service.app.rag.llm import build_llm_answer_generator

    if repository is None:
        repository = _seeded_repository()
    if answer_generator is None and monkeypatch is not None:
        RecordingHttpxClient.requests = []
        monkeypatch.setattr(httpx, "Client", RecordingHttpxClient)
        answer_generator = build_llm_answer_generator(llm_environment())
    rag_port = FinanceDemoLlmRagPort(
        repository=repository,
        source_root=SOURCE_ROOT,
        import_manifest_path=IMPORT_MANIFEST_PATH,
        rules_path=RULES_PATH,
        workspace_id=WORKSPACE_ID,
        answer_generator=answer_generator,
    )
    return MCPDemoServer(
        repository=repository,
        rag_port=rag_port,
        identities=_demo_identities(),
    )


def _call(server: MCPDemoServer, method: str, params: dict[str, object]) -> dict[str, object]:
    message = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params}
    responses = server.handle_message(message)
    assert len(responses) == 1, responses
    return responses[0]


def _result_payload(response: dict[str, object]) -> dict[str, object]:
    assert "error" not in response, response
    result = response["result"]
    assert isinstance(result, dict)
    return result


def _tool_text_payload(response: dict[str, object]) -> dict[str, object]:
    result = _result_payload(response)
    content = result["content"]
    assert isinstance(content, list) and content
    return json.loads(content[0]["text"])


def _first_asset_id(repository: InMemoryControlPlaneRepository) -> str:
    assets = repository.list_assets(WORKSPACE_ID)
    assert assets
    return assets[0].asset_id


# -- 协议子集 ---------------------------------------------------------------


def test_initialize_handshake() -> None:
    server = _build_server()
    response = _call(
        server,
        "initialize",
        {"protocolVersion": PROTOCOL_VERSION, "capabilities": {}, "clientInfo": {}},
    )
    payload = _result_payload(response)
    assert payload["protocolVersion"] == PROTOCOL_VERSION
    assert payload["serverInfo"]["name"] == "agent-workspace-control-plane"
    assert payload["capabilities"]["tools"]["listChanged"] is False
    assert "authz_check" in payload["instructions"]


def test_tools_list_exposes_four_tools() -> None:
    server = _build_server()
    response = _call(server, "tools/list", {})
    payload = _result_payload(response)
    names = [tool["name"] for tool in payload["tools"]]
    assert names == ["authz_check", "assess_materials", "query_knowledge", "list_audit_events"]
    for tool in payload["tools"]:
        assert tool["inputSchema"]["type"] == "object"


def test_unknown_method_returns_application_error() -> None:
    server = _build_server()
    response = _call(server, "bogus/method", {})
    assert response["error"]["code"] == -32601


# -- Policy ----------------------------------------------------------------


def test_authz_check_alice_allowed_bob_denied() -> None:
    server = _build_server()
    path = "客户模拟资料/收入情况说明.pdf"
    allowed = _tool_text_payload(
        _call(server, "tools/call", {"name": "authz_check", "arguments": {"actor_id": "alice", "action": "query", "path": path}})
    )
    assert allowed["state"] in ("ALLOW", "DIRECT")
    assert allowed["action"] == "query"

    denied = _tool_text_payload(
        _call(server, "tools/call", {"name": "authz_check", "arguments": {"actor_id": "bob", "action": "query", "path": path}})
    )
    assert denied["state"] == "DENY"


# -- Assess ----------------------------------------------------------------


def test_assess_materials_alice_matches_100() -> None:
    repository = _seeded_repository()
    server = _build_server(repository=repository)
    asset_ids = [asset.asset_id for asset in repository.list_assets(WORKSPACE_ID)]
    assert len(asset_ids) >= 1
    payload = _tool_text_payload(
        _call(
            server,
            "tools/call",
            {
                "name": "assess_materials",
                "arguments": {"actor_id": "alice", "asset_ids": asset_ids},
            },
        )
    )
    assert payload["match_score"] == 100
    assert payload["result_level"] == "MATCH"
    assert payload["missing_materials"] == []
    assert payload["bank_label"]


# -- Query -----------------------------------------------------------------


def test_query_knowledge_alice_real_llm_answer(monkeypatch) -> None:
    repository = _seeded_repository()
    server = _build_server(repository=repository, monkeypatch=monkeypatch)
    asset_id = _first_asset_id(repository)
    payload = _tool_text_payload(
        _call(
            server,
            "tools/call",
            {
                "name": "query_knowledge",
                "arguments": {"actor_id": "alice", "asset_id": asset_id, "question": "该客户资金情况如何？"},
            },
        )
    )
    assert payload["status"] == "ANSWERED"
    assert payload["answer"] == "LLM 依据授权证据生成的回答"
    assert payload["llm_invoked"] is True
    assert len(RecordingHttpxClient.requests) == 1


def test_query_knowledge_bob_denied_zero_llm(monkeypatch) -> None:
    repository = _seeded_repository()
    server = _build_server(repository=repository, monkeypatch=monkeypatch)
    asset_id = _first_asset_id(repository)
    payload = _tool_text_payload(
        _call(
            server,
            "tools/call",
            {
                "name": "query_knowledge",
                "arguments": {"actor_id": "bob", "asset_id": asset_id, "question": "该客户资金情况如何？"},
            },
        )
    )
    assert payload["status"] == "DENIED"
    assert payload["reason"] == "ACCESS_DENIED"
    assert payload["llm_invoked"] is False
    assert payload["retrieved_count"] == 0
    assert RecordingHttpxClient.requests == []


# -- Audit -----------------------------------------------------------------


def test_list_audit_events_returns_trail() -> None:
    repository = _seeded_repository()
    server = _build_server(repository=repository)
    payload = _tool_text_payload(
        _call(server, "tools/call", {"name": "list_audit_events", "arguments": {"limit": 5}})
    )
    events = payload["events"]
    assert isinstance(events, list)
    assert events, "seeded demo should leave audit events"
    for event in events:
        assert event["event_id"]
        assert event["event_type"] in ("asset_version_created", "rule_version_created")


# -- 错误路径 ---------------------------------------------------------------


def test_unknown_tool_returns_mcp_error_not_crash() -> None:
    server = _build_server()
    response = _call(server, "tools/call", {"name": "no_such_tool", "arguments": {}})
    assert response["error"]["code"] == -32602


def test_missing_argument_returns_mcp_error() -> None:
    server = _build_server()
    response = _call(
        server,
        "tools/call",
        {"name": "authz_check", "arguments": {"actor_id": "alice", "action": "query"}},
    )
    assert response["error"]["code"] == -32602
    assert "missing required argument" in response["error"]["message"]
