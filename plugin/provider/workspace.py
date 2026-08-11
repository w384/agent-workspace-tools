from typing import Any

from dify_plugin import ToolProvider
from dify_plugin.errors.tool import ToolProviderCredentialValidationError

from plugin.internal.client import WorkspaceClient


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
            raise ToolProviderCredentialValidationError(
                f"本机文件服务凭据验证失败：{error}"
            ) from error
