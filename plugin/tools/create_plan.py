import json
from collections.abc import Generator
from typing import Any

from dify_plugin.entities.tool import ToolInvokeMessage

from internal.client import WorkspaceServiceError
from internal.messages import (
    INVALID_SERVICE_RESPONSE_MESSAGE,
    format_plan_confirmation,
)
from internal.tool_base import WorkspaceTool


def _reject_non_json_constant(_value: str) -> None:
    raise ValueError("JSON 不允许非有限数值")


class CreatePlanTool(WorkspaceTool):
    def _invoke(
        self,
        tool_parameters: dict[str, Any],
    ) -> Generator[ToolInvokeMessage]:
        try:
            operations = json.loads(
                str(tool_parameters.get("operations_json", "")),
                parse_constant=_reject_non_json_constant,
            )
        except (TypeError, ValueError):
            raise ValueError("操作列表必须是非空 JSON 数组") from None
        if not isinstance(operations, list) or not operations:
            raise ValueError("操作列表必须是非空 JSON 数组")

        result = self._workspace_client().create_plan(operations)
        pending_error: WorkspaceServiceError | None = None
        payload: dict[str, Any] = {}
        confirmation_text = ""
        try:
            if (
                not isinstance(result, dict)
                or not isinstance(result.get("plan_id"), str)
                or not result["plan_id"]
                or result.get("status") != "pending_confirmation"
                or type(result.get("file_count")) is not int
                or result["file_count"] < 0
            ):
                raise ValueError("计划创建响应格式无效")
            confirmation_text = format_plan_confirmation(result)
            confirmation_json = result["confirmation"]
            payload = {
                "plan_id": result["plan_id"],
                "status": result["status"],
                "file_count": result["file_count"],
                "confirmation_text": confirmation_text,
                "confirmation_json": confirmation_json,
            }
        except (KeyError, TypeError, ValueError):
            pending_error = WorkspaceServiceError(
                "invalid_service_response",
                INVALID_SERVICE_RESPONSE_MESSAGE,
            )

        if pending_error is not None:
            raise pending_error from None

        yield self.create_text_message(confirmation_text)
        yield self.create_json_message(payload)
        for name, value in payload.items():
            yield self.create_variable_message(name, value)
