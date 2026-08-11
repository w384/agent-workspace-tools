import json
from collections.abc import Generator
from typing import Any

from dify_plugin.entities.tool import ToolInvokeMessage

from internal.messages import format_plan_confirmation
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
        confirmation_text = format_plan_confirmation(result)
        confirmation_json = result["confirmation"]
        payload = {
            "plan_id": result["plan_id"],
            "status": result["status"],
            "file_count": result["file_count"],
            "confirmation_text": confirmation_text,
            "confirmation_json": confirmation_json,
        }

        yield self.create_text_message(confirmation_text)
        yield self.create_json_message(payload)
        for name, value in payload.items():
            yield self.create_variable_message(name, value)
