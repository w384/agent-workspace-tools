from collections.abc import Generator
from typing import Any

from dify_plugin.entities.tool import ToolInvokeMessage

from internal.messages import format_file_detail
from internal import tool_base


class GetFileTool(tool_base.WorkspaceTool):
    def _invoke(
        self,
        tool_parameters: dict[str, Any],
    ) -> Generator[ToolInvokeMessage]:
        result = self._workspace_client().get_file(
            str(tool_parameters["path"]),
        )
        yield self.create_text_message(format_file_detail(result))
        yield self.create_json_message(result)
        for name in (
            "path",
            "name",
            "extension",
            "size_bytes",
            "modified_at",
            "content_available",
            "content_base64",
        ):
            yield self.create_variable_message(name, result[name])
