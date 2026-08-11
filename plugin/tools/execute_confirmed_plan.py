from collections.abc import Generator
from typing import Any

from dify_plugin.entities.tool import ToolInvokeMessage

from internal.client import (
    WorkspaceServiceError,
    WorkspaceTimeoutError,
)
from internal.messages import (
    EXECUTION_STATUS_UNCERTAIN_MESSAGE,
    INVALID_SERVICE_RESPONSE_MESSAGE,
    SERVICE_REQUEST_FAILED_MESSAGE,
    format_execution_result,
    safe_service_message,
)
from internal.tool_base import WorkspaceTool


class ExecuteConfirmedPlanTool(WorkspaceTool):
    def _invoke(
        self,
        tool_parameters: dict[str, Any],
    ) -> Generator[ToolInvokeMessage]:
        plan_id = str(tool_parameters.get("plan_id", "")).strip()
        if not plan_id:
            raise ValueError("计划编号不能为空")

        client = self._workspace_client()
        token_result = client.issue_approval_token(plan_id)
        approval_token = token_result.get("approval_token")
        if not isinstance(approval_token, str) or not approval_token:
            raise WorkspaceServiceError(
                "invalid_service_response",
                INVALID_SERVICE_RESPONSE_MESSAGE,
            )

        pending_error: WorkspaceServiceError | None = None
        result: dict[str, Any] = {}
        try:
            result = client.execute_plan(plan_id, approval_token)
        except WorkspaceTimeoutError:
            try:
                result = client.get_plan(plan_id)
            except Exception:
                result = {}
                pending_error = WorkspaceServiceError(
                    "execution_status_uncertain",
                    EXECUTION_STATUS_UNCERTAIN_MESSAGE,
                )
            else:
                if result.get("status") != "completed":
                    result = {}
                    pending_error = WorkspaceServiceError(
                        "execution_status_uncertain",
                        EXECUTION_STATUS_UNCERTAIN_MESSAGE,
                    )
        except WorkspaceServiceError as error:
            message = safe_service_message(
                error,
                api_key="",
                fallback=SERVICE_REQUEST_FAILED_MESSAGE,
                secrets=(approval_token,),
            )
            pending_error = WorkspaceServiceError(
                "execution_failed",
                message,
                error.status_code,
            )
        except Exception as error:
            message = safe_service_message(
                error,
                api_key="",
                fallback=SERVICE_REQUEST_FAILED_MESSAGE,
                secrets=(approval_token,),
            )
            pending_error = WorkspaceServiceError(
                "execution_failed",
                message,
            )
        finally:
            token_result = {}
            approval_token = ""

        if pending_error is not None:
            raise pending_error

        payload = {
            "plan_id": result["plan_id"],
            "status": result["status"],
            "file_count": result["file_count"],
            "operation_id": result["operation_id"],
        }
        result = {}
        yield self.create_text_message(format_execution_result(payload))
        yield self.create_json_message(payload)
        for name, value in payload.items():
            yield self.create_variable_message(name, value)
