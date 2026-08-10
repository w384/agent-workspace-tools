import base64
import hmac
import os
from pathlib import Path

from fastapi import Depends, FastAPI, Header, Query, Request
from fastapi.responses import JSONResponse

from service.app.file_content import read_file
from service.app.listing import list_files
from service.app.paths import resolve_workspace_path
from service.app.search import search_files


DEFAULT_WORKSPACE_ROOT = Path(r"D:\AI\AgentWorkspace")


class APIError(Exception):
    """可安全返回给 API 调用方的结构化错误。"""

    def __init__(
        self,
        *,
        status_code: int,
        code: str,
        message: str,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message


def create_app(
    workspace_root: Path,
    *,
    api_key: str,
) -> FastAPI:
    """创建绑定到指定工作区和 API Key 的 FastAPI 应用。"""
    application = FastAPI(
        title="Dify Agent Workspace Tools",
    )
    resolved_workspace_root = workspace_root.resolve()

    @application.exception_handler(APIError)
    def handle_api_error(
        _request: Request,
        error: APIError,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=error.status_code,
            content={
                "error": {
                    "code": error.code,
                    "message": error.message,
                }
            },
        )

    def require_api_key(
        x_api_key: str | None = Header(
            default=None,
            alias="X-API-Key",
        ),
    ) -> None:
        if not api_key:
            raise APIError(
                status_code=503,
                code="api_key_not_configured",
                message="服务尚未配置 API Key",
            )

        if x_api_key is None or not hmac.compare_digest(
            x_api_key,
            api_key,
        ):
            raise APIError(
                status_code=401,
                code="unauthorized",
                message="API Key 无效或缺失",
            )

    @application.get("/health")
    def health() -> dict[str, str]:
        return {
            "status": "ok",
            "service": "dify-agent-workspace-tools",
        }

    @application.get("/files")
    def get_files(
        page: int = Query(default=1, ge=1),
        page_size: int = Query(default=10, ge=1, le=10),
        _authorized: None = Depends(require_api_key),
    ) -> dict:
        return list_files(
            resolved_workspace_root,
            page=page,
            page_size=page_size,
        )

    @application.get("/files/search")
    def search_workspace_files(
        query: str = Query(min_length=1),
        page: int = Query(default=1, ge=1),
        page_size: int = Query(default=10, ge=1, le=10),
        _authorized: None = Depends(require_api_key),
    ) -> dict:
        return search_files(
            resolved_workspace_root,
            query=query,
            page=page,
            page_size=page_size,
        )

    @application.get("/files/content")
    def get_file_content(
        path: str = Query(min_length=1),
        _authorized: None = Depends(require_api_key),
    ) -> dict:
        result = read_file(
            resolved_workspace_root,
            path,
        )
        content = result.pop("content")
        result["path"] = resolve_workspace_path(
            resolved_workspace_root,
            path,
        ).relative_to(resolved_workspace_root).as_posix()
        result["content_base64"] = (
            base64.b64encode(content).decode("ascii")
            if content is not None
            else None
        )
        return result

    return application


app = create_app(
    Path(
        os.environ.get(
            "DIFY_AGENT_WORKSPACE_ROOT",
            str(DEFAULT_WORKSPACE_ROOT),
        )
    ),
    api_key=os.environ.get(
        "DIFY_AGENT_WORKSPACE_API_KEY",
        "",
    ),
)
