import base64
import hmac
import os
import re
from pathlib import Path
from typing import Any

from fastapi import (
    Depends,
    FastAPI,
    File,
    Form,
    Header,
    Query,
    Request,
    UploadFile,
)
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from service.app.file_content import read_file
from service.app.listing import list_files
from service.app.paths import resolve_workspace_path
from service.app.plans import (
    PlanStateError,
    create_plan,
    issue_approval_token,
)
from service.app.search import search_files
from service.app.upload import save_uploaded_file


DEFAULT_WORKSPACE_ROOT = Path(r"D:\AI\AgentWorkspace")
MAX_UPLOAD_BYTES = 15 * 1024 * 1024


class CreatePlanRequest(BaseModel):
    operations: list[dict[str, Any]]


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


def _domain_error_code(error: Exception) -> str:
    code = re.sub(
        r"(?<!^)(?=[A-Z])",
        "_",
        type(error).__name__,
    ).lower()
    return code.removesuffix("_error")


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

    @application.exception_handler(PlanStateError)
    @application.exception_handler(FileExistsError)
    @application.exception_handler(FileNotFoundError)
    @application.exception_handler(PermissionError)
    @application.exception_handler(ValueError)
    def handle_domain_error(
        _request: Request,
        error: Exception,
    ) -> JSONResponse:
        if isinstance(error, (PlanStateError, FileExistsError)):
            status_code = 409
        elif isinstance(error, FileNotFoundError):
            status_code = 404
        elif isinstance(error, PermissionError):
            status_code = 403
        else:
            status_code = 400

        return JSONResponse(
            status_code=status_code,
            content={
                "error": {
                    "code": _domain_error_code(error),
                    "message": str(error),
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

    @application.post("/files/upload", status_code=201)
    async def upload_workspace_file(
        directory: str = Form(default=""),
        file: UploadFile = File(),
        _authorized: None = Depends(require_api_key),
    ) -> dict:
        content = await file.read(MAX_UPLOAD_BYTES + 1)
        if len(content) > MAX_UPLOAD_BYTES:
            raise APIError(
                status_code=413,
                code="file_too_large",
                message="单个文件不能超过15MB",
            )
        return save_uploaded_file(
            resolved_workspace_root,
            relative_directory=directory,
            file_name=file.filename or "",
            content=content,
        )

    @application.post("/plans", status_code=201)
    def create_operation_plan(
        request_body: CreatePlanRequest,
        _authorized: None = Depends(require_api_key),
    ) -> dict:
        return create_plan(
            resolved_workspace_root,
            operations=request_body.operations,
        )

    @application.post(
        "/plans/{plan_id}/approval-token",
    )
    def approve_operation_plan(
        plan_id: str,
        _authorized: None = Depends(require_api_key),
    ) -> dict[str, str]:
        return {
            "plan_id": plan_id,
            "approval_token": issue_approval_token(
                resolved_workspace_root,
                plan_id=plan_id,
            ),
        }

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
