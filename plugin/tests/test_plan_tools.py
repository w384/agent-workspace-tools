import importlib
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
import yaml
from dify_plugin.entities.tool import ToolInvokeMessage

from internal.client import (
    WorkspaceClient,
    WorkspaceServiceError,
    WorkspaceTimeoutError,
)


PLUGIN_ROOT = Path(__file__).resolve().parents[1]
PLAN_ID = "123e4567-e89b-12d3-a456-426614174000"


class RecordingWorkspaceClient(WorkspaceClient):
    def __init__(self, responses: list[dict[str, Any]] | None = None) -> None:
        super().__init__("http://service", "key")
        self.calls: list[tuple[str, str, dict[str, Any]]] = []
        self.responses = list(responses or [])

    def request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        self.calls.append((method, path, kwargs))
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


class RecordingPlanClient:
    def __init__(
        self,
        *,
        create_result: dict[str, Any] | None = None,
        token: str = "approval-secret-token",
        token_response: dict[str, Any] | None = None,
        execute_result: dict[str, Any] | Exception | None = None,
        status_result: dict[str, Any] | None = None,
    ) -> None:
        self.calls: list[tuple[str, tuple[Any, ...]]] = []
        self.create_result = create_result or {}
        self.token = token
        self.token_response = token_response
        self.execute_result = execute_result or {}
        self.status_result = status_result or {}

    def create_plan(self, operations: list[dict[str, Any]]) -> dict[str, Any]:
        self.calls.append(("create_plan", (operations,)))
        return self.create_result

    def issue_approval_token(self, plan_id: str) -> dict[str, Any]:
        self.calls.append(("issue_approval_token", (plan_id,)))
        if self.token_response is not None:
            return self.token_response
        return {"plan_id": plan_id, "approval_token": self.token}

    def execute_plan(
        self,
        plan_id: str,
        approval_token: str,
    ) -> dict[str, Any]:
        self.calls.append(("execute_plan", (plan_id, approval_token)))
        if isinstance(self.execute_result, Exception):
            raise self.execute_result
        return self.execute_result

    def get_plan(self, plan_id: str) -> dict[str, Any]:
        self.calls.append(("get_plan", (plan_id,)))
        return self.status_result


def _tool_class(module_name: str, class_name: str) -> type:
    try:
        module = importlib.import_module(f"tools.{module_name}")
    except ModuleNotFoundError:
        pytest.fail(f"tools.{module_name} 尚未实现")
    return getattr(module, class_name)


def _tool(module_name: str, class_name: str, client: object):
    tool_class = _tool_class(module_name, class_name)
    tool = tool_class.__new__(tool_class)
    tool.response_type = ToolInvokeMessage
    tool._workspace_client = lambda: client
    return tool


def _text(messages: list[Any]) -> str:
    texts = [
        message.message.text
        for message in messages
        if message.type.value == "text"
    ]
    assert len(texts) == 1
    return texts[0]


def _json(messages: list[Any]) -> dict[str, Any]:
    payloads = [
        message.message.json_object
        for message in messages
        if message.type.value == "json"
    ]
    assert len(payloads) == 1
    return dict(payloads[0])


def _variables(messages: list[Any]) -> dict[str, Any]:
    return {
        message.message.variable_name: message.message.variable_value
        for message in messages
        if message.type.value == "variable"
    }


def _plan_result() -> dict[str, Any]:
    return {
        "plan_id": PLAN_ID,
        "status": "pending_confirmation",
        "file_count": 3,
        "confirmation": {
            "folders_to_create": ["reports", "archive"],
            "moves": [
                {
                    "source": "incoming/a.txt",
                    "destination": "reports/a.txt",
                }
            ],
            "renames": [
                {
                    "source_name": "a.txt",
                    "destination_name": "final.txt",
                }
            ],
            "trash": ["obsolete.txt"],
        },
    }


def test_client_plan_wrappers_use_expected_endpoints_and_payloads() -> None:
    client = RecordingWorkspaceClient(
        [
            {"plan_id": PLAN_ID},
            {"status": "approved"},
            {"approval_token": "token"},
            {"status": "completed"},
        ]
    )
    operations = [{"action": "trash", "source": "old.txt"}]

    client.create_plan(operations)
    client.get_plan(PLAN_ID)
    client.issue_approval_token(PLAN_ID)
    client.execute_plan(PLAN_ID, "token")

    assert client.calls == [
        ("POST", "/plans", {"json": {"operations": operations}}),
        ("GET", f"/plans/{PLAN_ID}", {}),
        ("POST", f"/plans/{PLAN_ID}/approval-token", {}),
        (
            "POST",
            f"/plans/{PLAN_ID}/execute",
            {"json": {"approval_token": "token"}},
        ),
    ]


def test_client_percent_encodes_every_dynamic_plan_path_segment() -> None:
    client = RecordingWorkspaceClient([{}, {}, {}])
    unsafe_segment = "a/b\\c?d#e%f"
    encoded_segment = "a%2Fb%5Cc%3Fd%23e%25f"

    client.get_plan(unsafe_segment)
    client.issue_approval_token(unsafe_segment)
    client.execute_plan(unsafe_segment, "token")

    assert client.calls == [
        ("GET", f"/plans/{encoded_segment}", {}),
        ("POST", f"/plans/{encoded_segment}/approval-token", {}),
        (
            "POST",
            f"/plans/{encoded_segment}/execute",
            {"json": {"approval_token": "token"}},
        ),
    ]


@pytest.mark.parametrize(
    "operations_json",
    [
        "not-json",
        "null",
        "{}",
        "[]",
        "[NaN]",
        "[Infinity]",
        "[-Infinity]",
    ],
)
def test_create_plan_rejects_invalid_non_array_or_empty_json_before_service(
    operations_json: str,
) -> None:
    client = RecordingPlanClient()
    tool = _tool("create_plan", "CreatePlanTool", client)

    with pytest.raises(ValueError, match="操作列表必须是非空 JSON 数组"):
        list(tool._invoke({"operations_json": operations_json}))

    assert client.calls == []


def test_create_plan_emits_exact_six_item_confirmation_and_real_outputs() -> None:
    result = _plan_result()
    client = RecordingPlanClient(create_result=result)
    tool = _tool("create_plan", "CreatePlanTool", client)
    operations = [{"action": "trash", "source": "obsolete.txt"}]

    messages = list(
        tool._invoke({"operations_json": "  " + str(operations).replace("'", '"')})
    )

    expected_text = "\n".join(
        [
            f"计划编号：{PLAN_ID}",
            "文件数量：3",
            "新建文件夹：reports、archive",
            "移动明细：incoming/a.txt → reports/a.txt",
            "重命名明细：a.txt → final.txt",
            "回收明细：obsolete.txt",
        ]
    )
    expected_payload = {
        "plan_id": PLAN_ID,
        "status": "pending_confirmation",
        "file_count": 3,
        "confirmation_text": expected_text,
        "confirmation_json": result["confirmation"],
    }
    assert client.calls == [("create_plan", (operations,))]
    assert _text(messages) == expected_text
    assert _json(messages) == expected_payload
    assert _variables(messages) == expected_payload


def test_create_plan_confirmation_displays_none_for_all_empty_sections() -> None:
    result = _plan_result()
    result["confirmation"] = {
        "folders_to_create": [],
        "moves": [],
        "renames": [],
        "trash": [],
    }
    tool = _tool(
        "create_plan",
        "CreatePlanTool",
        RecordingPlanClient(create_result=result),
    )

    messages = list(tool._invoke({"operations_json": '[{"action":"noop"}]'}))

    assert _text(messages) == "\n".join(
        [
            f"计划编号：{PLAN_ID}",
            "文件数量：3",
            "新建文件夹：无",
            "移动明细：无",
            "重命名明细：无",
            "回收明细：无",
        ]
    )


def test_execute_confirmed_plan_requests_token_then_executes_without_leaking_it() -> None:
    token = "approval-secret-token"
    result = {
        "plan_id": PLAN_ID,
        "status": "completed",
        "file_count": 2,
        "operation_id": "operation-456",
        "approval_token": token,
        "operations": [{"source": token}],
    }
    client = RecordingPlanClient(token=token, execute_result=result)
    tool = _tool(
        "execute_confirmed_plan",
        "ExecuteConfirmedPlanTool",
        client,
    )

    messages = list(
        tool._invoke({"plan_id": " {123E4567-E89B-12D3-A456-426614174000} "})
    )

    expected_payload = {
        "plan_id": PLAN_ID,
        "status": "completed",
        "file_count": 2,
        "operation_id": "operation-456",
    }
    assert client.calls == [
        ("issue_approval_token", (PLAN_ID,)),
        ("execute_plan", (PLAN_ID, token)),
    ]
    assert _json(messages) == expected_payload
    assert _variables(messages) == expected_payload
    rendered = repr(messages)
    assert token not in rendered
    assert token not in _text(messages)


@pytest.mark.parametrize(
    "malicious_plan_id",
    [
        "..",
        "../maintenance",
        "..\\maintenance",
        f"{PLAN_ID}?ignored=",
        f"{PLAN_ID}#fragment",
        f"{PLAN_ID}%suffix",
        "%2e%2e%2fmaintenance",
        "%252e%252e%252fmaintenance",
        "%2e%2e%5cmaintenance",
        f"{PLAN_ID}%3Fignored%3D",
        f"{PLAN_ID}%23fragment",
        f"{PLAN_ID}%25suffix",
    ],
)
def test_execute_rejects_non_uuid_plan_ids_before_any_service_call(
    malicious_plan_id: str,
) -> None:
    client = RecordingPlanClient()
    tool = _tool(
        "execute_confirmed_plan",
        "ExecuteConfirmedPlanTool",
        client,
    )

    with pytest.raises(ValueError, match="计划编号无效"):
        list(tool._invoke({"plan_id": malicious_plan_id}))

    assert client.calls == []


def test_execute_timeout_returns_completed_status_after_single_status_query() -> None:
    token = "approval-secret-token"
    client = RecordingPlanClient(
        token=token,
        execute_result=WorkspaceTimeoutError(
            "service_timeout",
            "本机文件服务响应超时",
        ),
        status_result={
            "plan_id": PLAN_ID,
            "status": "completed",
            "file_count": 1,
            "operation_id": "operation-456",
        },
    )
    tool = _tool(
        "execute_confirmed_plan",
        "ExecuteConfirmedPlanTool",
        client,
    )

    messages = list(tool._invoke({"plan_id": PLAN_ID}))

    assert client.calls == [
        ("issue_approval_token", (PLAN_ID,)),
        ("execute_plan", (PLAN_ID, token)),
        ("get_plan", (PLAN_ID,)),
    ]
    assert _json(messages)["status"] == "completed"
    assert token not in repr(messages)


def test_execute_timeout_with_other_status_is_uncertain_and_never_reposts() -> None:
    token = "approval-secret-token"
    client = RecordingPlanClient(
        token=token,
        execute_result=WorkspaceTimeoutError(
            "service_timeout",
            "本机文件服务响应超时",
        ),
        status_result={"plan_id": PLAN_ID, "status": "executing"},
    )
    tool = _tool(
        "execute_confirmed_plan",
        "ExecuteConfirmedPlanTool",
        client,
    )

    with pytest.raises(Exception, match="执行状态不确定") as caught:
        list(tool._invoke({"plan_id": PLAN_ID}))

    assert client.calls == [
        ("issue_approval_token", (PLAN_ID,)),
        ("execute_plan", (PLAN_ID, token)),
        ("get_plan", (PLAN_ID,)),
    ]
    assert token not in str(caught.value)


def test_execute_failure_removes_token_from_error_context_code_and_tool_frame() -> None:
    token = "approval-secret-token"
    client = RecordingPlanClient(
        token=token,
        execute_result=WorkspaceServiceError(token, token),
    )
    tool = _tool(
        "execute_confirmed_plan",
        "ExecuteConfirmedPlanTool",
        client,
    )

    with pytest.raises(WorkspaceServiceError) as caught:
        list(tool._invoke({"plan_id": PLAN_ID}))

    assert token not in str(caught.value)
    assert token not in caught.value.code
    assert caught.value.__context__ is None
    tool_frame_locals: list[str] = []
    current = caught.value.__traceback__
    while current is not None:
        if current.tb_frame.f_code.co_filename.endswith(
            "tools\\execute_confirmed_plan.py"
        ):
            tool_frame_locals.append(repr(current.tb_frame.f_locals))
        current = current.tb_next
    assert tool_frame_locals
    assert token not in "\n".join(tool_frame_locals)


@pytest.mark.parametrize(
    "execute_result",
    [
        {
            "plan_id": PLAN_ID,
            "status": "completed",
            "file_count": 1,
            "operation_id": "approval-secret-token",
        },
        {
            "plan_id": PLAN_ID,
            "status": "completed",
            "file_count": 1,
            "approval_token": "approval-secret-token",
        },
    ],
)
def test_malformed_execute_response_cannot_leak_token_anywhere(
    execute_result: dict[str, Any],
) -> None:
    token = "approval-secret-token"
    client = RecordingPlanClient(token=token, execute_result=execute_result)
    tool = _tool(
        "execute_confirmed_plan",
        "ExecuteConfirmedPlanTool",
        client,
    )

    with pytest.raises(WorkspaceServiceError) as caught:
        list(tool._invoke({"plan_id": PLAN_ID}))

    assert caught.value.code == "invalid_service_response"
    assert token not in str(caught.value)
    assert token not in caught.value.code
    assert caught.value.__context__ is None
    tool_frame_locals: list[str] = []
    current = caught.value.__traceback__
    while current is not None:
        if current.tb_frame.f_code.co_filename.endswith(
            "tools\\execute_confirmed_plan.py"
        ):
            tool_frame_locals.append(repr(current.tb_frame.f_locals))
        current = current.tb_next
    assert tool_frame_locals
    assert token not in "\n".join(tool_frame_locals)


@pytest.mark.parametrize(
    "execute_result",
    [
        {
            "plan_id": PLAN_ID,
            "status": "failed",
            "file_count": 1,
            "operation_id": "operation-456",
        },
        {
            "status": "completed",
            "file_count": 1,
            "operation_id": "operation-456",
        },
        {
            "plan_id": "223e4567-e89b-12d3-a456-426614174000",
            "status": "completed",
            "file_count": 1,
            "operation_id": "operation-456",
        },
        {
            "plan_id": PLAN_ID,
            "status": "completed",
            "file_count": "1",
            "operation_id": "operation-456",
        },
        {
            "plan_id": PLAN_ID,
            "status": "completed",
            "file_count": 1,
            "operation_id": None,
        },
    ],
)
def test_normal_execute_response_requires_completed_typed_matching_projection(
    execute_result: dict[str, Any],
) -> None:
    client = RecordingPlanClient(execute_result=execute_result)
    tool = _tool(
        "execute_confirmed_plan",
        "ExecuteConfirmedPlanTool",
        client,
    )

    with pytest.raises(WorkspaceServiceError) as caught:
        list(tool._invoke({"plan_id": PLAN_ID}))

    assert caught.value.code == "invalid_service_response"
    assert caught.value.__context__ is None


@pytest.mark.parametrize(
    "confirmation",
    [
        {
            "folders_to_create": [],
            "moves": [],
            "renames": [],
        },
        {
            "folders_to_create": "reports",
            "moves": [],
            "renames": [],
            "trash": [],
        },
        {
            "folders_to_create": [1],
            "moves": [],
            "renames": [],
            "trash": [],
        },
        {
            "folders_to_create": [],
            "moves": ["bad"],
            "renames": [],
            "trash": [],
        },
        {
            "folders_to_create": [],
            "moves": [{"source": "a.txt"}],
            "renames": [],
            "trash": [],
        },
        {
            "folders_to_create": [],
            "moves": [],
            "renames": [{"source_name": "a.txt", "destination_name": 1}],
            "trash": [],
        },
        {
            "folders_to_create": [],
            "moves": [],
            "renames": [],
            "trash": [1],
        },
        {
            "folders_to_create": [],
            "moves": [],
            "renames": [],
            "trash": [],
            "copies": ["hidden.txt"],
        },
    ],
)
def test_create_plan_rejects_missing_or_malformed_confirmation_sections(
    confirmation: dict[str, Any],
) -> None:
    result = _plan_result()
    result["confirmation"] = confirmation
    client = RecordingPlanClient(create_result=result)
    tool = _tool("create_plan", "CreatePlanTool", client)

    with pytest.raises(WorkspaceServiceError) as caught:
        list(tool._invoke({"operations_json": '[{"action":"noop"}]'}))

    assert caught.value.code == "invalid_service_response"
    assert str(caught.value) == "本机文件服务返回了无法解析的响应"
    assert caught.value.__context__ is None


@pytest.mark.parametrize(
    "token_response",
    [
        {"approval_token": "approval-secret-token"},
        {
            "plan_id": "223e4567-e89b-12d3-a456-426614174000",
            "approval_token": "approval-secret-token",
        },
    ],
)
def test_malformed_token_response_never_reaches_execute_or_leaks_token(
    token_response: dict[str, Any],
) -> None:
    token = "approval-secret-token"
    client = RecordingPlanClient(
        token=token,
        token_response=token_response,
        execute_result={
            "plan_id": PLAN_ID,
            "status": "completed",
            "file_count": 1,
            "operation_id": "operation-456",
        },
    )
    tool = _tool(
        "execute_confirmed_plan",
        "ExecuteConfirmedPlanTool",
        client,
    )

    with pytest.raises(WorkspaceServiceError) as caught:
        list(tool._invoke({"plan_id": PLAN_ID}))

    assert client.calls == [("issue_approval_token", (PLAN_ID,))]
    assert caught.value.code == "invalid_service_response"
    assert token not in str(caught.value)
    assert token not in caught.value.code
    assert caught.value.__context__ is None
    tool_frame_locals: list[str] = []
    current = caught.value.__traceback__
    while current is not None:
        if current.tb_frame.f_code.co_filename.endswith(
            "tools\\execute_confirmed_plan.py"
        ):
            tool_frame_locals.append(repr(current.tb_frame.f_locals))
        current = current.tb_next
    assert tool_frame_locals
    assert token not in "\n".join(tool_frame_locals)


def test_plan_tool_yaml_declares_real_outputs_and_provider_registration() -> None:
    provider = yaml.safe_load(
        (PLUGIN_ROOT / "provider" / "workspace.yaml").read_text(
            encoding="utf-8"
        )
    )
    assert provider["tools"] == [
        "tools/list_files.yaml",
        "tools/search_files.yaml",
        "tools/get_file.yaml",
        "tools/create_plan.yaml",
        "tools/execute_confirmed_plan.yaml",
    ]

    expected_outputs = {
        "create_plan": {
            "plan_id",
            "status",
            "file_count",
            "confirmation_text",
            "confirmation_json",
        },
        "execute_confirmed_plan": {
            "plan_id",
            "status",
            "file_count",
            "operation_id",
        },
    }
    for tool_name, output_names in expected_outputs.items():
        configuration = yaml.safe_load(
            (PLUGIN_ROOT / "tools" / f"{tool_name}.yaml").read_text(
                encoding="utf-8"
            )
        )
        assert set(configuration["output_schema"]["properties"]) == output_names
        assert {
            parameter["name"] for parameter in configuration["parameters"]
        } == ({"operations_json"} if tool_name == "create_plan" else {"plan_id"})


def test_plan_tools_import_from_plugin_runtime_root() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "from tools.create_plan import CreatePlanTool; "
            "from tools.execute_confirmed_plan import ExecuteConfirmedPlanTool",
        ],
        cwd=PLUGIN_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
