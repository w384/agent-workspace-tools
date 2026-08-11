from collections.abc import Generator
from typing import Any
from uuid import UUID

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


def _normalize_plan_id(value: object) -> str:
    try:
        return str(UUID(str(value).strip()))
    except (AttributeError, TypeError, ValueError):
        raise ValueError("计划编号无效") from None


def _invalid_response_error() -> WorkspaceServiceError:
    return WorkspaceServiceError(
        "invalid_service_response",
        INVALID_SERVICE_RESPONSE_MESSAGE,
    )


def _safe_execution_payload(
    result: object,
    *,
    expected_plan_id: str,
    approval_token: str,
) -> dict[str, Any]:
    if not isinstance(result, dict):
        raise ValueError("计划执行响应格式无效")

    plan_id = result.get("plan_id")
    status = result.get("status")
    file_count = result.get("file_count")
    operation_id = result.get("operation_id")
    projected_values = (plan_id, status, file_count, operation_id)
    if any(
        isinstance(value, str) and approval_token in value
        for value in projected_values
    ):
        raise ValueError("计划执行响应包含敏感值")
    if (
        plan_id != expected_plan_id
        or status != "completed"
        or type(file_count) is not int
        or file_count < 0
        or not isinstance(operation_id, str)
        or not operation_id
    ):
        raise ValueError("计划执行响应格式无效")
    return {
        "plan_id": plan_id,
        "status": status,
        "file_count": file_count,
        "operation_id": operation_id,
    }


class ExecuteConfirmedPlanTool(WorkspaceTool):
    def _invoke(
        self,
        tool_parameters: dict[str, Any],
    ) -> Generator[ToolInvokeMessage]:
        plan_id = _normalize_plan_id(tool_parameters.get("plan_id", ""))

        client = self._workspace_client()
        token_result: object = {}
        token_plan_id: object = ""
        approval_token = ""
        result: object = {}
        payload: dict[str, Any] = {}
        pending_error: WorkspaceServiceError | None = None
        try:
            token_result = client.issue_approval_token(plan_id)
            if not isinstance(token_result, dict):
                pending_error = _invalid_response_error()
            else:
                token_plan_id = token_result.get("plan_id")
                token_value = token_result.get("approval_token")
                if (
                    token_plan_id == plan_id
                    and isinstance(token_value, str)
                    and token_value
                ):
                    approval_token = token_value
                else:
                    pending_error = _invalid_response_error()

            if pending_error is None:
                try:
                    result = client.execute_plan(plan_id, approval_token)
                except WorkspaceTimeoutError:
                    try:
                        result = client.get_plan(plan_id)
                    except Exception:
                        pending_error = WorkspaceServiceError(
                            "execution_status_uncertain",
                            EXECUTION_STATUS_UNCERTAIN_MESSAGE,
                        )
                    else:
                        if (
                            not isinstance(result, dict)
                            or result.get("status") != "completed"
                        ):
                            pending_error = WorkspaceServiceError(
                                "execution_status_uncertain",
                                EXECUTION_STATUS_UNCERTAIN_MESSAGE,
                            )
                        else:
                            try:
                                payload = _safe_execution_payload(
                                    result,
                                    expected_plan_id=plan_id,
                                    approval_token=approval_token,
                                )
                            except (KeyError, TypeError, ValueError):
                                pending_error = _invalid_response_error()
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
                else:
                    try:
                        payload = _safe_execution_payload(
                            result,
                            expected_plan_id=plan_id,
                            approval_token=approval_token,
                        )
                    except (KeyError, TypeError, ValueError):
                        pending_error = _invalid_response_error()
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
            token_plan_id = ""
            token_value = ""
            approval_token = ""
            result = {}

        if pending_error is not None:
            raise pending_error from None

        yield self.create_text_message(format_execution_result(payload))
        yield self.create_json_message(payload)
        for name, value in payload.items():
            yield self.create_variable_message(name, value)
