from dify_plugin import Tool

from plugin.internal.client import WorkspaceClient


class WorkspaceTool(Tool):
    def _workspace_client(self) -> WorkspaceClient:
        return WorkspaceClient(
            self.runtime.credentials["service_url"],
            self.runtime.credentials["api_key"],
        )
