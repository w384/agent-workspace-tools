from typing import Any

from dify_plugin import ToolProvider
from dify_plugin.errors.tool import ToolProviderCredentialValidationError

from internal.client import WorkspaceClient
from internal.messages import safe_service_message


class WorkspaceProvider(ToolProvider):
    def _validate_credentials(self, credentials: dict[str, Any]) -> None:
        try:
            WorkspaceClient(
                credentials["service_url"],
                credentials["api_key"],
            ).request(
                "GET",
                "/files",
                params={"page": 1, "page_size": 1},
            )
        except Exception as error:
            message = safe_service_message(
                error,
                api_key=str(credentials.get("api_key", "")),
            )
            raise ToolProviderCredentialValidationError(
                f"本机文件服务凭据验证失败：{message}"
            ) from None
