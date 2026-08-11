from collections.abc import Generator
from typing import Any

from dify_plugin.entities.tool import ToolInvokeMessage

from internal.messages import format_file_page
from internal import tool_base


class SearchFilesTool(tool_base.WorkspaceTool):
    def _invoke(
        self,
        tool_parameters: dict[str, Any],
    ) -> Generator[ToolInvokeMessage]:
        query = str(
            tool_parameters.get("query", "")
        ).strip()
        if not query:
            raise ValueError("搜索关键词不能为空")

        result = self._workspace_client().search_files(
            query,
            int(tool_parameters.get("page", 1)),
            int(tool_parameters.get("page_size", 10)),
        )

        yield self.create_text_message(
            format_file_page(result)
        )
        yield self.create_json_message(result)

        for name in (
            "total",
            "page",
            "page_size",
            "has_more",
        ):
            yield self.create_variable_message(
                name,
                result[name],
            )

        yield self.create_variable_message(
            "items",
            result["files"],
        )