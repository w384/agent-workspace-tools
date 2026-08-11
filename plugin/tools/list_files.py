from collections.abc import Generator
from typing import Any

from dify_plugin.entities.tool import ToolInvokeMessage

from internal.messages import format_file_page
from internal.tool_base import WorkspaceTool


class ListFilesTool(WorkspaceTool):
    def _invoke(
        self,
        tool_parameters: dict[str, Any],
    ) -> Generator[ToolInvokeMessage]:
        result = self._workspace_client().list_files(
            int(tool_parameters.get("page", 1)),
            int(tool_parameters.get("page_size", 10)),
        )
        yield self.create_text_message(format_file_page(result))
        yield self.create_json_message(result)
        for name in ("total", "page", "page_size", "has_more", "files"):
            yield self.create_variable_message(name, result[name])
