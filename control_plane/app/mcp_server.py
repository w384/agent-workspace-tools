"""Minimal MCP (Model Context Protocol) exposure layer for the demo control plane.

Wraps the four showroom capabilities as MCP tools so an external agent host
can drive the control plane through the standard stdio MCP transport:
  - authz_check        -> Policy (PermissionGrant / ACL evaluation)
  - assess_materials   -> Assess (deterministic material matching pre-assessment)
  - query_knowledge    -> Query (permission-aware knowledge-base Q&A)
  - list_audit_events  -> Audit (audit event trail)

Zero external dependency: speaks the MCP JSON-RPC 2.0 subset (initialize,
tools/list, tools/call, ping) over newline-delimited JSON on stdin/stdout.
Runnable as:  python -m control_plane.app.mcp_server

This is the showroom exposure layer for the Agent Control Plane direction;
it does not add a second authority for assets, permissions or audit (the
control-plane repository stays the single source of truth).
"""

from __future__ import annotations

import json
import sys
import uuid
from pathlib import Path
from typing import Mapping

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from control_plane.app.domain import (
    Action,
    RuleVersion,
    TrustedActorContext,
)
from control_plane.app.policy import evaluate_authorization
from control_plane.app.repository import ControlPlaneRepository
from control_plane.app.sessions import DemoIdentity

PROTOCOL_VERSION = "2025-06-18"
SERVER_NAME = "agent-workspace-control-plane"
SERVER_VERSION = "0.1.0"

WORKSPACE_ID = "workspace-a"
CONTEXT_VERSION = "acl_2026_08_13"

_DEMO_ROOT = PROJECT_ROOT / "work" / "demo" / "financial-preassessment"
DEMO_SOURCE_ROOT = _DEMO_ROOT / "source"
DEMO_IMPORT_MANIFEST_PATH = _DEMO_ROOT / "import-manifest.json"
DEMO_RULES_PATH = _DEMO_ROOT / "rules" / "demo-bank-rules-v1.json"


def _require(arguments: Mapping[str, object], key: str, expected_type: type) -> object:
    if key not in arguments:
        raise ValueError(f"missing required argument: {key}")
    value = arguments[key]
    if not isinstance(value, expected_type):
        raise ValueError(f"argument {key} must be {expected_type.__name__}")
    return value


class MCPDemoServer:
    """A tiny dependency-free MCP server over newline-delimited JSON-RPC."""

    def __init__(
        self,
        *,
        repository: ControlPlaneRepository,
        rag_port: object,
        identities: Mapping[str, DemoIdentity],
    ) -> None:
        self._repository = repository
        self._rag_port = rag_port
        self._identities = dict(identities)

    # -- protocol ----------------------------------------------------------

    def handle_message(self, message: Mapping[str, object]) -> list[dict[str, object]]:
        """Dispatch one inbound JSON-RPC message; return the response(s)."""
        request_id = message.get("id")
        method = message.get("method")
        if not isinstance(method, str):
            if request_id is None:
                return []
            return [_error(request_id, -32600, "invalid request")]
        params = message.get("params") or {}
        if not isinstance(params, dict):
            params = {}

        if method == "initialize":
            return [_result(request_id, self._initialize_result(params))]
        if method == "notifications/initialized":
            return []
        if method == "ping":
            return [_result(request_id, {})]
        if method == "tools/list":
            return [_result(request_id, {"tools": self._list_tools()})]
        if method == "tools/call":
            try:
                return [_call_tool_result(request_id, self._call_tool(params))]
            except (ValueError, LookupError, KeyError) as exc:
                if request_id is None:
                    return []
                return [_error(request_id, -32602, f"invalid tool call: {exc}")]
        if request_id is None:
            return []
        return [_error(request_id, -32601, f"method not found: {method}")]

    def _initialize_result(self, params: Mapping[str, object]) -> dict[str, object]:
        requested = params.get("protocolVersion")
        version = requested if isinstance(requested, str) else PROTOCOL_VERSION
        return {
            "protocolVersion": version,
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
            "instructions": (
                "企业 Agent 安全运行样板间控制面 MCP 暴露层：提供 Policy（authz_check）、"
                "Assess（assess_materials）、Query（query_knowledge）、Audit（list_audit_events）"
                "四个工具，均为演示能力，不代表真实授信结论。演示账号：alice（已授权）、"
                "bob（无 QUERY 授权，用于越权负向演示）。"
            ),
        }

    def _list_tools(self) -> list[dict[str, object]]:
        return [
            {
                "name": "authz_check",
                "description": (
                    "评估指定主体对某路径执行某动作的授权决策（Policy 能力）。"
                    "返回 ALLOW / DENY 与原因。"
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "actor_id": {
                            "type": "string",
                            "description": "演示账号：alice（已授权）或 bob（无 QUERY 授权）",
                        },
                        "action": {
                            "type": "string",
                            "description": "动作：query / upload / move_rename / trash / create_folder",
                        },
                        "path": {
                            "type": "string",
                            "description": "待评估资料路径，如 客户模拟资料/收入情况说明.pdf",
                        },
                    },
                    "required": ["actor_id", "action", "path"],
                },
            },
            {
                "name": "assess_materials",
                "description": (
                    "对已授权资料版本执行确定性资料匹配预评估（Assess 能力）。"
                    "输出 match_score、等级、缺失材料与版本化引用。"
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "actor_id": {"type": "string", "description": "演示账号：alice 或 bob"},
                        "asset_ids": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "要评估的资产 ID 列表（取自 seed 摘要）",
                        },
                        "query_subject": {
                            "type": "string",
                            "description": "评估查询主体，默认 模拟客户资料匹配度",
                        },
                    },
                    "required": ["actor_id", "asset_ids"],
                },
            },
            {
                "name": "query_knowledge",
                "description": (
                    "对单个已授权资产执行权限感知知识库问答（Query 能力）。"
                    "未授权主体返回 DENIED 且不调用 LLM。"
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "actor_id": {"type": "string", "description": "演示账号：alice 或 bob"},
                        "asset_id": {"type": "string", "description": "资产 ID"},
                        "question": {"type": "string", "description": "自然语言问题"},
                    },
                    "required": ["actor_id", "asset_id", "question"],
                },
            },
            {
                "name": "list_audit_events",
                "description": (
                    "列出最近审计事件（Audit 能力）：资料/规则版本、查询主体、时间等留痕。"
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "limit": {"type": "integer", "description": "最多返回条数，默认 20"},
                    },
                },
            },
        ]

    def _call_tool(self, params: Mapping[str, object]) -> dict[str, object]:
        name = params.get("name")
        arguments = params.get("arguments") or {}
        if not isinstance(name, str):
            raise ValueError("tools/call requires a tool name")
        if not isinstance(arguments, dict):
            raise ValueError("tools/call arguments must be an object")
        handlers = {
            "authz_check": self._tool_authz_check,
            "assess_materials": self._tool_assess_materials,
            "query_knowledge": self._tool_query_knowledge,
            "list_audit_events": self._tool_list_audit_events,
        }
        handler = handlers.get(name)
        if handler is None:
            raise ValueError(f"unknown tool: {name}")
        return handler(arguments)

    # -- actor resolution ---------------------------------------------------

    def _resolve_actor(self, username: str) -> TrustedActorContext:
        identity = self._identities.get(username)
        if identity is None:
            raise ValueError(f"unknown demo actor: {username!r}")
        return TrustedActorContext(
            actor_id=identity.actor_id,
            workspace_id=identity.workspace_id,
            context_version=identity.context_version,
            session_id="mcp-session",
            request_id=f"mcp-{uuid.uuid4().hex[:12]}",
            run_id=f"run-{uuid.uuid4().hex[:12]}",
            role_ids=frozenset(identity.role_ids),
            group_ids=frozenset(identity.group_ids),
        )

    def _fixture_rule_version(self) -> RuleVersion:
        for rule_version in self._repository.rule_versions.values():
            if rule_version.source_type == "demo_fixture":
                return rule_version
        raise LookupError("no demo fixture rule version seeded")

    # -- tools --------------------------------------------------------------

    def _tool_authz_check(self, arguments: Mapping[str, object]) -> dict[str, object]:
        actor_id = str(_require(arguments, "actor_id", str))
        action_name = str(_require(arguments, "action", str))
        path = str(_require(arguments, "path", str))
        actor = self._resolve_actor(actor_id)
        try:
            action = Action(action_name)
        except ValueError:
            raise ValueError(f"unknown action: {action_name!r}")
        decision = evaluate_authorization(
            actor,
            self._repository.list_permission_grants(actor),
            action,
            (path,),
        )
        return {
            "actor_id": actor.actor_id,
            "workspace_id": actor.workspace_id,
            "action": action.value,
            "path": path,
            "state": decision.state.value,
            "reason": decision.reason,
        }

    def _tool_assess_materials(self, arguments: Mapping[str, object]) -> dict[str, object]:
        actor_id = str(_require(arguments, "actor_id", str))
        asset_ids = list(_require(arguments, "asset_ids", list))
        query_subject = str(arguments.get("query_subject", "模拟客户资料匹配度"))
        actor = self._resolve_actor(actor_id)
        versions = []
        for asset_id in asset_ids:
            asset = self._repository.get_asset(str(asset_id))
            if asset.active_version_id is None:
                raise ValueError(f"asset has no active version: {asset_id}")
            versions.append(
                self._repository.get_asset_version(asset.active_version_id)
            )
        if not versions:
            raise ValueError("no asset versions to assess")
        rule_version = self._fixture_rule_version()
        result = self._rag_port.assess_versions(
            actor,
            tuple(versions),
            rule_version,
            query_subject,
        )
        return {
            "actor_id": actor.actor_id,
            "match_score": result.match_score,
            "result_level": result.result_level,
            "missing_materials": list(result.missing_materials),
            "bank_label": result.bank_label,
            "candidate_banks": list(result.candidate_banks),
            "citations": list(result.citations),
        }

    def _tool_query_knowledge(self, arguments: Mapping[str, object]) -> dict[str, object]:
        actor_id = str(_require(arguments, "actor_id", str))
        asset_id = str(_require(arguments, "asset_id", str))
        question = str(_require(arguments, "question", str))
        actor = self._resolve_actor(actor_id)
        return dict(self._rag_port.query(actor, question, asset_id))

    def _tool_list_audit_events(self, arguments: Mapping[str, object]) -> dict[str, object]:
        limit_raw = arguments.get("limit", 20)
        if not isinstance(limit_raw, int) or isinstance(limit_raw, bool) or limit_raw <= 0:
            raise ValueError("limit must be a positive integer")
        events = self._repository.list_audit_events()
        return {
            "events": [
                {
                    "event_id": event.event_id,
                    "event_type": event.event_type,
                    "actor_id": event.actor_id,
                    "request_id": event.request_id,
                    "run_id": event.run_id,
                    "details": dict(event.details),
                }
                for event in events[-limit_raw:]
            ],
        }

    # -- stdio loop -----------------------------------------------------------

    def run_stdio(self) -> None:
        """Read newline-delimited JSON-RPC from stdin, write responses to stdout."""
        for raw in sys.stdin:
            line = raw.strip()
            if not line:
                continue
            try:
                message = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(message, dict):
                continue
            for response in self.handle_message(message):
                sys.stdout.write(json.dumps(response, ensure_ascii=False) + "\n")
                sys.stdout.flush()


def _result(request_id: object, result: Mapping[str, object]) -> dict[str, object]:
    return {"jsonrpc": "2.0", "id": request_id, "result": dict(result)}


def _call_tool_result(request_id: object, payload: Mapping[str, object]) -> dict[str, object]:
    text = json.dumps(payload, ensure_ascii=False, default=_json_default)
    result: dict[str, object] = {
        "content": [{"type": "text", "text": text}],
        "structuredContent": payload,
    }
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def _error(request_id: object, code: int, message: str) -> dict[str, object]:
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "error": {"code": code, "message": message},
    }


def _json_default(value: object) -> object:
    if isinstance(value, Mapping):
        return dict(value)
    if hasattr(value, "value"):
        return value.value
    return str(value)


def _demo_identities() -> dict[str, DemoIdentity]:
    return {
        "alice": DemoIdentity(
            username="alice",
            password="demo-a-password",
            actor_id="user-a",
            workspace_id=WORKSPACE_ID,
            context_version=CONTEXT_VERSION,
            group_ids=frozenset({"staff"}),
            role_ids=frozenset({"role-member-demo"}),
        ),
        "bob": DemoIdentity(
            username="bob",
            password="demo-b-password",
            actor_id="user-b",
            workspace_id=WORKSPACE_ID,
            context_version=CONTEXT_VERSION,
            group_ids=frozenset({"staff"}),
            role_ids=frozenset({"role-member-demo"}),
        ),
    }


def build_default_server() -> MCPDemoServer:
    """Wire the seeded demo repository + composite RAG bridge into an MCP server."""
    from control_plane.app.finance_demo_llm_rag import FinanceDemoLlmRagPort
    from control_plane.app.llm_providers import LLMProviderRegistry
    from control_plane.app.repository import InMemoryControlPlaneRepository
    from scripts.init_demo_financial_preassessment import seed_financial_preassessment_demo

    repository = InMemoryControlPlaneRepository()
    seed_financial_preassessment_demo(repository)
    providers = LLMProviderRegistry()
    rag_port = FinanceDemoLlmRagPort(
        repository=repository,
        source_root=DEMO_SOURCE_ROOT,
        import_manifest_path=DEMO_IMPORT_MANIFEST_PATH,
        rules_path=DEMO_RULES_PATH,
        workspace_id=WORKSPACE_ID,
        providers=providers,
    )
    return MCPDemoServer(
        repository=repository,
        rag_port=rag_port,
        identities=_demo_identities(),
    )


def main(argv: list[str] | None = None) -> int:
    build_default_server().run_stdio()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
