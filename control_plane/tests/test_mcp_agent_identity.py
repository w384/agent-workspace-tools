"""MCP 暴露层 Agent 身份（agent_id）测试。

Covers:
  1. 正例：alice + agent_id -> query_knowledge ANSWERED / llm_invoked=True，
     响应回带 agent_id，审计出现 agent_action_executed（agent_id/tool/status 正确）。
  2. 负例：bob + agent_id -> DENIED / llm_invoked=False / LLM 零调用，
     越权动作仍在审计留痕。
  3. authz_check + agent_id：返回 agent_id 字段，判定与所属用户一致（ALLOW/DENY）。
  4. assess_materials + agent_id：正常 MATCH 100。
  5. list_audit_events 序列化含 agent_id 字段。
  6. 不传 agent_id 时不产生 agent_action_executed 事件（不回归）。
"""

import json
from pathlib import Path

import httpx

from conftest import RecordingHttpxClient, llm_environment
from control_plane.app.mcp_server import MCPDemoServer, _demo_identities
from control_plane.app.repository import InMemoryControlPlaneRepository


PROJECT_ROOT = Path(__file__).parents[2]
DEMO_ROOT = PROJECT_ROOT / "work" / "demo" / "financial-preassessment"
SOURCE_ROOT = DEMO_ROOT / "source"
IMPORT_MANIFEST_PATH = DEMO_ROOT / "import-manifest.json"
RULES_PATH = DEMO_ROOT / "rules" / "demo-bank-rules-v1.json"
WORKSPACE_ID = "workspace-a"


def _seeded_repository() -> InMemoryControlPlaneRepository:
    from scripts.init_demo_financial_preassessment import seed_financial_preassessment_demo

    repository = InMemoryControlPlaneRepository()
    seed_financial_preassessment_demo(repository)
    return repository


def _build_server(
    *,
    repository: InMemoryControlPlaneRepository | None = None,
    monkeypatch=None,
) -> MCPDemoServer:
    from control_plane.app.finance_demo_llm_rag import FinanceDemoLlmRagPort
    from service.app.rag.llm import build_llm_answer_generator

    if repository is None:
        repository = _seeded_repository()
    if monkeypatch is not None:
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


def _audit_events(server: MCPDemoServer) -> list[dict[str, object]]:
    payload = _tool_text_payload(
        _call(server, "tools/call", {"name": "list_audit_events", "arguments": {"limit": 100}})
    )
    return payload["events"]


def _agent_events(events: list[dict[str, object]]) -> list[dict[str, object]]:
    return [e for e in events if e["event_type"] == "agent_action_executed"]
def _agent_events(events: list[dict[str, object]]) -> list[dict[str, object]]:
    return [e for e in events if e["event_type"] == "agent_action_executed"]


# -- 正例：alice + agent_id ------------------------------------------------


def test_query_knowledge_alice_agent_id_answer_and_audit(monkeypatch) -> None:
    repository = _seeded_repository()
    server = _build_server(repository=repository, monkeypatch=monkeypatch)
    asset_id = _first_asset_id(repository)
    payload = _tool_text_payload(
        _call(
            server,
            "tools/call",
            {
                "name": "query_knowledge",
                "arguments": {
                    "actor_id": "alice",
                    "agent_id": "agent-alice-1",
                    "asset_id": asset_id,
                    "question": "该客户资金情况如何？",
                },
            },
        )
    )
    assert payload["status"] == "ANSWERED"
    assert payload["answer"] == "LLM 依据授权证据生成的回答"
    assert payload["llm_invoked"] is True
    assert payload["agent_id"] == "agent-alice-1"
    assert len(RecordingHttpxClient.requests) == 1

    events = _agent_events(_audit_events(server))
    assert len(events) == 1
    event = events[0]
    assert event["agent_id"] == "agent-alice-1"
    assert event["actor_id"] == "user-a"
    assert event["details"]["tool"] == "query_knowledge"
    assert event["details"]["status"] == "ANSWERED"
    assert event["details"]["asset_id"] == asset_id
    assert event["details"]["llm_invoked"] is True


def test_authz_check_agent_id_matches_owner_and_audits(monkeypatch) -> None:
    repository = _seeded_repository()
    server = _build_server(repository=repository, monkeypatch=monkeypatch)
    path = "客户模拟资料/收入情况说明.pdf"
    payload = _tool_text_payload(
        _call(
            server,
            "tools/call",
            {
                "name": "authz_check",
                "arguments": {
                    "actor_id": "alice",
                    "agent_id": "agent-alice-2",
                    "action": "query",
                    "path": path,
                },
            },
        )
    )
    assert payload["state"] in ("ALLOW", "DIRECT")
    assert payload["agent_id"] == "agent-alice-2"
    assert payload["actor_id"] == "user-a"

    events = _agent_events(_audit_events(server))
    assert any(
        e["agent_id"] == "agent-alice-2"
        and e["details"]["tool"] == "authz_check"
        and e["details"]["status"] in ("ALLOW", "DIRECT")
        for e in events
    )


def test_assess_materials_agent_id_matches_100(monkeypatch) -> None:
    repository = _seeded_repository()
    server = _build_server(repository=repository, monkeypatch=monkeypatch)
    asset_ids = [asset.asset_id for asset in repository.list_assets(WORKSPACE_ID)]
    assert len(asset_ids) >= 1
    payload = _tool_text_payload(
        _call(
            server,
            "tools/call",
            {
                "name": "assess_materials",
                "arguments": {
                    "actor_id": "alice",
                    "agent_id": "agent-alice-3",
                    "asset_ids": asset_ids,
                },
            },
        )
    )
    assert payload["match_score"] == 100
    assert payload["result_level"] == "MATCH"
    assert payload["agent_id"] == "agent-alice-3"

    events = _agent_events(_audit_events(server))
    assert any(
        e["agent_id"] == "agent-alice-3"
        and e["details"]["tool"] == "assess_materials"
        and e["details"]["status"] == "MATCH"
        and e["details"]["asset_count"] == len(asset_ids)
        for e in events
    )


# -- 负例：bob + agent_id ---------------------------------------------------


def test_query_knowledge_bob_agent_id_denied_zero_llm_still_audited(monkeypatch) -> None:
    repository = _seeded_repository()
    server = _build_server(repository=repository, monkeypatch=monkeypatch)
    asset_id = _first_asset_id(repository)
    payload = _tool_text_payload(
        _call(
            server,
            "tools/call",
            {
                "name": "query_knowledge",
                "arguments": {
                    "actor_id": "bob",
                    "agent_id": "agent-bob-1",
                    "asset_id": asset_id,
                    "question": "该客户资金情况如何？",
                },
            },
        )
    )
    assert payload["status"] == "DENIED"
    assert payload["reason"] == "ACCESS_DENIED"
    assert payload["llm_invoked"] is False
    assert payload["retrieved_count"] == 0
    assert payload["agent_id"] == "agent-bob-1"
    assert RecordingHttpxClient.requests == []

    # 越权也要留痕：拒绝同样进入 agent_action_executed 审计
    events = _agent_events(_audit_events(server))
    assert any(
        e["agent_id"] == "agent-bob-1"
        and e["details"]["tool"] == "query_knowledge"
        and e["details"]["status"] == "DENIED"
        and e["details"]["llm_invoked"] is False
        for e in events
    )


def test_authz_check_bob_agent_id_denied_and_audited(monkeypatch) -> None:
    repository = _seeded_repository()
    server = _build_server(repository=repository, monkeypatch=monkeypatch)
    path = "客户模拟资料/收入情况说明.pdf"
    payload = _tool_text_payload(
        _call(
            server,
            "tools/call",
            {
                "name": "authz_check",
                "arguments": {
                    "actor_id": "bob",
                    "agent_id": "agent-bob-2",
                    "action": "query",
                    "path": path,
                },
            },
        )
    )
    assert payload["state"] == "DENY"
    assert payload["agent_id"] == "agent-bob-2"

    events = _agent_events(_audit_events(server))
    assert any(
        e["agent_id"] == "agent-bob-2"
        and e["details"]["tool"] == "authz_check"
        and e["details"]["status"] == "DENY"
        for e in events
    )


# -- 审计序列化 -------------------------------------------------------------


def test_list_audit_events_serializes_agent_id_field(monkeypatch) -> None:
    repository = _seeded_repository()
    server = _build_server(repository=repository, monkeypatch=monkeypatch)
    asset_id = _first_asset_id(repository)
    _call(
        server,
        "tools/call",
        {
            "name": "query_knowledge",
            "arguments": {
                "actor_id": "alice",
                "agent_id": "agent-alice-9",
                "asset_id": asset_id,
                "question": "该客户资金情况如何？",
            },
        },
    )
    events = _audit_events(server)
    # 每个事件都有 agent_id 键（无 agent 时为 None）
    for event in events:
        assert "agent_id" in event
    assert any(e["agent_id"] == "agent-alice-9" for e in events)


# -- 不回归：无 agent_id 不产生 agent 事件 -----------------------------------


def test_without_agent_id_no_agent_action_executed(monkeypatch) -> None:
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
    assert payload.get("agent_id") is None
    assert _agent_events(_audit_events(server)) == []
