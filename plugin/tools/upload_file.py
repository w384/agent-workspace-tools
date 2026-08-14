from collections.abc import Generator
from typing import Any

from dify_plugin.entities.tool import ToolInvokeMessage

from internal import tool_base


class UploadFileTool(tool_base.WorkspaceTool):
    def _invoke(
        self,
        tool_parameters: dict[str, Any],
    ) -> Generator[ToolInvokeMessage]:
        file_value = tool_parameters.get("file")
        if not isinstance(file_value, dict):
            raise ValueError("file 必须是 Dify 文件对象")

        file_name = file_value.get("name")
        content = file_value.get("content")
        mime_type = file_value.get("mime_type") or "application/octet-stream"
        if not isinstance(file_name, str) or not file_name:
            raise ValueError("文件名不能为空")
        if not isinstance(content, bytes):
            raise ValueError("文件内容必须是二进制数据")
        if not isinstance(mime_type, str) or not mime_type:
            raise ValueError("文件 MIME 类型无效")

        result = self._workspace_client().upload_file(
            directory=str(tool_parameters.get("directory", "")),
            file_name=file_name,
            content=content,
            mime_type=mime_type,
            user_id=getattr(
                getattr(self, "runtime", None),
                "user_id",
                None,
            ),
        )
        path = result.get("path")
        size_bytes = result.get("size_bytes")
        if not isinstance(path, str) or not isinstance(size_bytes, int):
            raise ValueError("上传服务响应格式无效")

        payload = {"path": path, "size_bytes": size_bytes}
        yield self.create_text_message(
            f"已上传文件：{path}（{size_bytes} bytes）"
        )
        yield self.create_json_message(payload)
        yield self.create_variable_message("path", path)
        yield self.create_variable_message("size_bytes", size_bytes)
