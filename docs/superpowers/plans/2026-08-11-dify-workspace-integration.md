# Dify Workspace Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让本机 Dify 通过一个受控 Tool Provider 安全读取、计划、人工确认、执行并恢复 D:\AI\AgentWorkspace 中的文件操作，并在端到端通过后把 FastAPI 安装为最小权限 Windows 服务。

**Architecture:** 现有 FastAPI 继续作为唯一文件系统边界，只增加计划状态查询和密钥文件读取。Dify 插件通过共享 WorkspaceClient 调用受 API Key 保护的接口，九个工具各自拥有 YAML 与 Python 入口；实际整理和恢复工具在 Human Input 批准分支中内部签发并消费一次性令牌。插件与 Workflow 验证通过后，再用 WinSW 托管 FastAPI。

**Tech Stack:** Python 3.12、FastAPI 0.141.1、pytest 9.1.1、Dify 1.16.1、Dify Plugin CLI 0.6.10、Dify Python Plugin SDK、requests、Docker Desktop、WinSW 2.12、PowerShell。

## Global Constraints

- 工作区根目录固定为 D:\AI\AgentWorkspace，不得接受任意绝对路径。
- Dify 服务地址为 http://host.docker.internal:8787；本机手工测试使用 http://127.0.0.1:8787。
- 每批最多处理 10 个文件；创建文件夹不计数；超过 10 个文件分页并逐批确认。
- 单个文件最大读取或上传尺寸为 15MB；超限文件只返回元数据。
- 所有业务接口使用 X-API-Key；API Key 和一次性令牌不得进入模型上下文、日志或错误文本。
- 一次性令牌只在插件的一次工具调用内存在；实际执行不得盲目重试，超时后先查询计划状态。
- 任一执行前校验失败时整批零执行；不得覆盖已存在目标。
- 操作日志保留 14 天；恢复必须先生成恢复计划并再次进行 Human Input。
- upload_file、execute_confirmed_plan、restore_confirmed_operation 只能位于固定 Workflow 的 Human Input 批准分支。
- 现有 56 项服务测试必须持续通过；每个实现任务采用红—绿—重构循环并单独提交。
- 所有 PowerShell 执行均须先取得用户批准；所有文件变更同步写入当日中文 project-changes.log。
- 不发布 Marketplace，不开放公网，不提供永久删除，不清空 .trash。

## File Map

Service changes:

- service/app/plans.py：安全计划状态投影。
- service/app/main.py：GET /plans/{plan_id} 和 API Key 文件加载。
- service/tests/test_plans.py、test_api_execution.py、test_api_auth.py、test_api_maintenance.py：计划状态覆盖。
- service/tests/test_configuration.py：密钥文件配置覆盖。
- .gitignore：忽略密钥、插件环境、包和端到端工作文件。

Plugin files:

- plugin/manifest.yaml、main.py、requirements.txt：插件入口。
- plugin/provider/workspace.yaml、workspace.py：Provider 凭据与验证。
- plugin/internal/client.py：唯一 HTTP 客户端。
- plugin/internal/tool_base.py：从 Dify Provider 凭据创建客户端的工具基类。
- plugin/internal/messages.py：中文文本、JSON、自定义变量输出。
- plugin/tools 下九组 YAML/Python：九个独立工具。
- plugin/tests：客户端、Provider、工具和文档测试。

Workflow/deployment files:

- docs/dify/workflow-setup.md：Workflow 与 Human Input 配置。
- docs/dify/acceptance-cases.md：3 个成功、3 个失败案例。
- deployment/windows-service/DifyAgentWorkspaceTools.xml：WinSW 配置。
- deployment/windows-service/install.ps1、uninstall.ps1：受控安装与卸载。
- service/tests/test_windows_service_config.py：部署文件静态安全测试。

---

### Task 1: Add authenticated plan status API

**Files:**
- Modify: service/app/plans.py
- Modify: service/app/main.py
- Modify: service/tests/test_plans.py
- Modify: service/tests/test_api_execution.py
- Modify: service/tests/test_api_auth.py
- Modify: service/tests/test_api_maintenance.py

**Interfaces:**
- Consumes: _read_plan(workspace_root: Path, plan_id: str) -> dict[str, Any]
- Produces: read_plan_status(workspace_root: Path, *, plan_id: str) -> dict[str, Any]
- Produces: GET /plans/{plan_id}
- Safe fields: plan_id, status, plan_type, file_count, created_at, approved_at, completed_at, failed_at, operation_id, rollback_status, error_type.

- [ ] **Step 1: Write the failing domain test**

Add to service/tests/test_plans.py:

~~~python
def test_read_plan_status_excludes_operations_and_token_hash(tmp_path: Path):
    plans_module = importlib.import_module("service.app.plans")
    workspace_root = tmp_path / "workspace"
    workspace_root.mkdir()
    (workspace_root / "notes.txt").write_text("hello", encoding="utf-8")
    plan = plans_module.create_plan(
        workspace_root,
        operations=[{
            "action": "move_rename",
            "source": "notes.txt",
            "destination": "archive/notes.txt",
        }],
    )
    plans_module.issue_approval_token(
        workspace_root,
        plan_id=plan["plan_id"],
    )

    result = plans_module.read_plan_status(
        workspace_root,
        plan_id=plan["plan_id"],
    )

    assert result["status"] == "approved"
    assert "operations" not in result
    assert "approval_token_hash" not in result
~~~

- [ ] **Step 2: Run the test and confirm RED**

Run: python -m pytest service/tests/test_plans.py::test_read_plan_status_excludes_operations_and_token_hash -v

Expected: FAIL with AttributeError because read_plan_status does not exist.

- [ ] **Step 3: Implement the safe projection**

Add to service/app/plans.py:

~~~python
_PLAN_STATUS_FIELDS = (
    "plan_id", "status", "plan_type", "file_count",
    "created_at", "approved_at", "completed_at",
    "failed_at", "operation_id", "rollback_status",
    "error_type",
)


def read_plan_status(
    workspace_root: Path,
    *,
    plan_id: str,
) -> dict[str, Any]:
    plan = _read_plan(workspace_root, plan_id)
    return {
        key: plan[key]
        for key in _PLAN_STATUS_FIELDS
        if key in plan
    }
~~~

- [ ] **Step 4: Add failing API tests**

Add one test for HTTP 200 safe projection and one for HTTP 404 plan_not_found. Add an unauthorized GET /plans/{id} request to the existing all-business-routes authentication test.

~~~python
response = client.get(
    f"/plans/{plan['plan_id']}",
    headers=_headers(),
)
assert response.status_code == 200
assert response.json()["status"] == "pending_confirmation"
assert "operations" not in response.json()
~~~

- [ ] **Step 5: Run API tests and confirm RED**

Run: python -m pytest service/tests/test_api_execution.py -k get_plan_status -v

Expected: FAIL with HTTP 404 because the route is absent.

- [ ] **Step 6: Register the protected route**

Import read_plan_status in service/app/main.py and add:

~~~python
    @application.get("/plans/{plan_id}")
    def get_operation_plan(
        plan_id: str,
        _authorized: None = Depends(require_api_key),
    ) -> dict:
        return read_plan_status(
            resolved_workspace_root,
            plan_id=plan_id,
        )
~~~

- [ ] **Step 7: Verify and commit**

Run: python -m pytest service/tests -v

Expected: all service tests PASS.

~~~powershell
git add service/app/plans.py service/app/main.py service/tests/test_plans.py service/tests/test_api_execution.py service/tests/test_api_auth.py service/tests/test_api_maintenance.py
git commit -m "feat: expose authenticated plan status"
~~~

---

### Task 2: Load API Key from a protected file

**Files:**
- Create: service/tests/test_configuration.py
- Modify: service/app/main.py
- Modify: .gitignore

**Interfaces:**
- Produces: load_api_key(environment: Mapping[str, str]) -> str
- Precedence: non-empty DIFY_AGENT_WORKSPACE_API_KEY; otherwise DIFY_AGENT_WORKSPACE_API_KEY_FILE; otherwise empty string.

- [ ] **Step 1: Write failing configuration tests**

Create service/tests/test_configuration.py:

~~~python
from pathlib import Path

import pytest

from service.app.main import load_api_key


def test_load_api_key_prefers_direct_value(tmp_path: Path):
    key_file = tmp_path / "api-key.txt"
    key_file.write_text("file-secret\n", encoding="utf-8")
    assert load_api_key({
        "DIFY_AGENT_WORKSPACE_API_KEY": "direct-secret",
        "DIFY_AGENT_WORKSPACE_API_KEY_FILE": str(key_file),
    }) == "direct-secret"


def test_load_api_key_reads_file(tmp_path: Path):
    key_file = tmp_path / "api-key.txt"
    key_file.write_text("file-secret\n", encoding="utf-8")
    assert load_api_key({
        "DIFY_AGENT_WORKSPACE_API_KEY_FILE": str(key_file),
    }) == "file-secret"


def test_load_api_key_rejects_empty_file(tmp_path: Path):
    key_file = tmp_path / "api-key.txt"
    key_file.write_text("\n", encoding="utf-8")
    with pytest.raises(RuntimeError, match="API Key 密钥文件为空"):
        load_api_key({
            "DIFY_AGENT_WORKSPACE_API_KEY_FILE": str(key_file),
        })
~~~

- [ ] **Step 2: Confirm RED**

Run: python -m pytest service/tests/test_configuration.py -v

Expected: collection ERROR because load_api_key is absent.

- [ ] **Step 3: Implement loading and precedence**

Add Mapping import and:

~~~python
def load_api_key(environment: Mapping[str, str]) -> str:
    direct_value = environment.get(
        "DIFY_AGENT_WORKSPACE_API_KEY", ""
    ).strip()
    if direct_value:
        return direct_value

    key_file_value = environment.get(
        "DIFY_AGENT_WORKSPACE_API_KEY_FILE", ""
    ).strip()
    if not key_file_value:
        return ""

    try:
        file_value = Path(key_file_value).read_text(
            encoding="utf-8"
        ).strip()
    except OSError as error:
        raise RuntimeError(
            "无法读取 API Key 密钥文件"
        ) from error
    if not file_value:
        raise RuntimeError("API Key 密钥文件为空")
    return file_value
~~~

Use api_key=load_api_key(os.environ) when creating the module-level app.

- [ ] **Step 4: Ignore generated secrets and packages**

Append to .gitignore:

~~~gitignore
plugin/.venv/
plugin/.env
*.difypkg
work/windows-service/secrets/
work/e2e/
~~~

- [ ] **Step 5: Verify and commit**

Run: python -m pytest service/tests -v

Expected: all service tests PASS.

~~~powershell
git add .gitignore service/app/main.py service/tests/test_configuration.py
git commit -m "feat: load service api key from file"
~~~

---

### Task 3: Scaffold Provider and implement WorkspaceClient

**Files:**
- Create: plugin/manifest.yaml, plugin/main.py, plugin/requirements.txt
- Create: plugin/provider/workspace.yaml, plugin/provider/workspace.py
- Create: plugin/internal/__init__.py, plugin/internal/client.py, plugin/internal/messages.py, plugin/internal/tool_base.py
- Create: plugin/tests/test_client.py, plugin/tests/test_provider.py

**Interfaces:**
- WorkspaceClient(base_url: str, api_key: str, timeout_seconds: float = 15.0)
- request(method: str, path: str, **kwargs) -> dict[str, Any]
- WorkspaceServiceError(code, message, status_code)
- WorkspaceTimeoutError
- Provider validates GET /files?page=1&page_size=1, never public /health.

- [ ] **Step 1: Generate the official scaffold**

Run from project root:

~~~powershell
& "D:\AI\Dify\dify\tools\dify.exe" plugin init
~~~

Choose Tool; project directory plugin; Provider workspace; author tianh. Keep the SDK version generated by CLI 0.6.10.

- [ ] **Step 2: Create the isolated plugin environment**

~~~powershell
& "D:\AI\Python3.12.10\python.exe" -m venv ".\plugin\.venv"
& ".\plugin\.venv\Scripts\python.exe" -m pip install -r ".\plugin\requirements.txt"
& ".\plugin\.venv\Scripts\python.exe" -m pip install pytest
~~~

Expected: the environment imports dify_plugin, requests and pytest without using service/.venv.

- [ ] **Step 3: Write failing client tests**

Tests inject a Mock requests.Session and assert normalized URL, X-API-Key, GET retry count 3, POST retry count 1, timeout conversion, structured error parsing, and absence of secrets/absolute paths in exception text.

~~~python
client = WorkspaceClient(
    "http://host.docker.internal:8787/",
    "do-not-leak",
    session=session,
)
result = client.request("GET", "/files", params={"page": 1})
assert result["total"] == 0
assert session.request.call_args.kwargs["headers"] == {
    "X-API-Key": "do-not-leak"
}
~~~

- [ ] **Step 4: Confirm RED**

Run: plugin\.venv\Scripts\python.exe -m pytest plugin/tests/test_client.py -v

Expected: FAIL because plugin.internal.client is absent.

- [ ] **Step 5: Implement the client**

~~~python
class WorkspaceServiceError(RuntimeError):
    def __init__(
        self,
        code: str,
        message: str,
        status_code: int | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.status_code = status_code


class WorkspaceTimeoutError(WorkspaceServiceError):
    pass


class WorkspaceClient:
    def __init__(
        self,
        base_url: str,
        api_key: str,
        *,
        timeout_seconds: float = 15.0,
        session: requests.Session | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout_seconds = timeout_seconds
        self.session = session or requests.Session()

    def request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        attempts = 3 if method.upper() == "GET" else 1
        for attempt in range(attempts):
            try:
                response = self.session.request(
                    method=method.upper(),
                    url=f"{self.base_url}/{path.lstrip('/')}",
                    headers={"X-API-Key": self.api_key},
                    timeout=self.timeout_seconds,
                    **kwargs,
                )
            except requests.Timeout as error:
                if attempt + 1 < attempts:
                    continue
                raise WorkspaceTimeoutError(
                    "service_timeout",
                    "本机文件服务响应超时",
                ) from error
            try:
                payload = response.json()
            except ValueError as error:
                raise WorkspaceServiceError(
                    "invalid_service_response",
                    "本机文件服务返回了无法解析的响应",
                    response.status_code,
                ) from error
            if response.status_code >= 400:
                detail = payload.get("error", {})
                raise WorkspaceServiceError(
                    str(detail.get("code", "service_error")),
                    str(detail.get("message", "本机文件服务请求失败")),
                    response.status_code,
                )
            return payload
        raise AssertionError("request retry loop exited unexpectedly")
~~~

- [ ] **Step 6: Add the credential-aware tool base**

Create plugin/internal/tool_base.py:

~~~python
class WorkspaceTool(Tool):
    def _workspace_client(self) -> WorkspaceClient:
        return WorkspaceClient(
            self.runtime.credentials["service_url"],
            self.runtime.credentials["api_key"],
        )
~~~

Tool tests construct a small subclass that overrides _workspace_client and returns a FakeWorkspaceClient. Production tool classes never store or emit credentials.

- [ ] **Step 7: Implement and test Provider validation**

workspace.yaml defines required service_url as text-input and api_key as secret-input. workspace.py uses:

~~~python
class WorkspaceProvider(ToolProvider):
    def _validate_credentials(
        self,
        credentials: dict[str, Any],
    ) -> None:
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
~~~

test_provider.py asserts /files is called and 401 becomes ToolProviderCredentialValidationError without the Key.

- [ ] **Step 8: Verify and commit**

Run: plugin\.venv\Scripts\python.exe -m pytest plugin/tests/test_client.py plugin/tests/test_provider.py -v

Expected: PASS.

~~~powershell
git add plugin .gitignore
git commit -m "feat: scaffold Dify workspace provider"
~~~

---

### Task 4: Implement list_files, search_files, and get_file

**Files:**
- Create: plugin/tools/list_files.yaml, list_files.py
- Create: plugin/tools/search_files.yaml, search_files.py
- Create: plugin/tools/get_file.yaml, get_file.py
- Create: plugin/tests/test_read_tools.py
- Modify: plugin/internal/client.py, plugin/internal/messages.py

**Interfaces:**
- list_files(page, page_size)
- search_files(query, page, page_size)
- get_file(path)
- Each tool yields Chinese text, JSON, and variables declared in output_schema.

- [ ] **Step 1: Write failing tool tests**

Assert URL/parameters, blank-query rejection, 15MB metadata-only text, and text/JSON/variable outputs.

~~~python
messages = list(tool._invoke({
    "query": "合同",
    "page": 1,
    "page_size": 10,
}))
assert tool.client.calls[0][1] == "/files/search"
assert message_json(messages)["total"] == 1
assert "合同.txt" in message_text(messages)
~~~

- [ ] **Step 2: Confirm RED**

Run: plugin\.venv\Scripts\python.exe -m pytest plugin/tests/test_read_tools.py -v

Expected: FAIL because read tool modules are absent.

- [ ] **Step 3: Add client wrappers**

~~~python
def list_files(self, page: int, page_size: int) -> dict[str, Any]:
    return self.request(
        "GET", "/files",
        params={"page": page, "page_size": page_size},
    )

def search_files(
    self, query: str, page: int, page_size: int
) -> dict[str, Any]:
    return self.request(
        "GET", "/files/search",
        params={
            "query": query,
            "page": page,
            "page_size": page_size,
        },
    )

def get_file(self, path: str) -> dict[str, Any]:
    return self.request(
        "GET", "/files/content",
        params={"path": path},
    )
~~~

- [ ] **Step 4: Implement three Tool classes and YAML schemas**

Each YAML sets page_size maximum 10 and declares its true output variables. Each class calls one wrapper only; no HTTP code is copied.

~~~python
class ListFilesTool(WorkspaceTool):
    def _invoke(
        self,
        tool_parameters: dict[str, Any],
    ) -> Generator[ToolInvokeMessage]:
        client = self._workspace_client()
        result = client.list_files(
            int(tool_parameters.get("page", 1)),
            int(tool_parameters.get("page_size", 10)),
        )
        yield self.create_text_message(format_file_page(result))
        yield self.create_json_message(result)
        for name in ("total", "page", "page_size", "items"):
            yield self.create_variable_message(name, result[name])
~~~

- [ ] **Step 5: Verify and commit**

Run: plugin\.venv\Scripts\python.exe -m pytest plugin/tests -v

Expected: all plugin tests PASS.

~~~powershell
git add plugin/internal plugin/tools plugin/tests/test_read_tools.py
git commit -m "feat: add Dify workspace read tools"
~~~

---

### Task 5: Implement confirmed non-overwriting upload

**Files:**
- Create: plugin/tools/upload_file.yaml, upload_file.py
- Create: plugin/tests/test_upload_tool.py
- Modify: plugin/internal/client.py

**Interfaces:**
- Input: Dify file and target relative directory.
- Output: relative path and size_bytes.
- Workflow, not Agent, places the tool after Human Input.

- [ ] **Step 1: Write failing multipart tests**

~~~python
assert call.kwargs["files"] == {
    "file": ("report.txt", b"hello", "text/plain")
}
assert call.kwargs["data"] == {"directory": "incoming"}
~~~

Also assert file_already_exists is preserved as a safe code.

- [ ] **Step 2: Confirm RED**

Run: plugin\.venv\Scripts\python.exe -m pytest plugin/tests/test_upload_tool.py -v

Expected: FAIL because UploadFileTool is absent.

- [ ] **Step 3: Implement wrapper and tool**

~~~python
def upload_file(
    self,
    *,
    directory: str,
    file_name: str,
    content: bytes,
    mime_type: str,
) -> dict[str, Any]:
    return self.request(
        "POST",
        "/files/upload",
        data={"directory": directory},
        files={"file": (file_name, content, mime_type)},
    )
~~~

UploadFileTool reads the Dify file object, calls the wrapper, and emits text, JSON, path and size_bytes. Its YAML description says it must only run after Human Input and never overwrites.

- [ ] **Step 4: Verify and commit**

Run: plugin\.venv\Scripts\python.exe -m pytest plugin/tests/test_upload_tool.py plugin/tests/test_client.py -v

Expected: PASS.

~~~powershell
git add plugin/internal/client.py plugin/tools/upload_file.yaml plugin/tools/upload_file.py plugin/tests/test_upload_tool.py
git commit -m "feat: add confirmed upload tool"
~~~

---

### Task 6: Implement create_plan and execute_confirmed_plan

**Files:**
- Create: plugin/tools/create_plan.yaml, create_plan.py
- Create: plugin/tools/execute_confirmed_plan.yaml, execute_confirmed_plan.py
- Create: plugin/tests/test_plan_tools.py
- Modify: plugin/internal/client.py, plugin/internal/messages.py

**Interfaces:**
- create_plan receives operations_json: str.
- Outputs: plan_id, status, file_count, confirmation_text, confirmation_json.
- execute_confirmed_plan receives only plan_id; token remains local.
- Timeout handling calls GET /plans/{plan_id}; it never blindly repeats POST.

- [ ] **Step 1: Write failing parsing and confirmation tests**

Cover valid array, invalid JSON, non-array JSON and exact six-field confirmation.

~~~python
assert confirmation_text == (
    f"计划编号：{plan_id}\n"
    "文件数量：1\n"
    "新建文件夹：archive\n"
    "移动明细：notes.txt → archive/notes-2026.txt\n"
    "重命名明细：notes.txt → notes-2026.txt\n"
    "回收明细：无"
)
~~~

- [ ] **Step 2: Confirm RED**

Run: plugin\.venv\Scripts\python.exe -m pytest plugin/tests/test_plan_tools.py -k create_plan -v

Expected: FAIL because CreatePlanTool is absent.

- [ ] **Step 3: Implement create-plan mapping**

~~~python
def create_plan(
    self,
    operations: list[dict[str, Any]],
) -> dict[str, Any]:
    return self.request(
        "POST", "/plans",
        json={"operations": operations},
    )
~~~

CreatePlanTool uses json.loads, requires a list root, calls the wrapper, and formats every confirmation field. Empty sections display 无.

- [ ] **Step 4: Write failing confirmed-execution tests**

~~~python
assert tool.client.calls == [
    ("issue_approval_token", plan_id),
    ("execute_plan", plan_id, "one-time-token"),
]
assert "one-time-token" not in message_text(messages)
assert "one-time-token" not in json.dumps(message_json(messages))
~~~

For timeout, assert get_plan(plan_id) follows. completed returns known status; other states raise execution_status_uncertain and do not POST again.

- [ ] **Step 5: Implement execution wrappers and tool**

~~~python
def get_plan(self, plan_id: str) -> dict[str, Any]:
    return self.request("GET", f"/plans/{plan_id}")

def issue_approval_token(self, plan_id: str) -> str:
    result = self.request(
        "POST", f"/plans/{plan_id}/approval-token"
    )
    return str(result["approval_token"])

def execute_plan(
    self,
    plan_id: str,
    approval_token: str,
) -> dict[str, Any]:
    return self.request(
        "POST",
        f"/plans/{plan_id}/execute",
        json={"approval_token": approval_token},
    )
~~~

The tool keeps approval_token in a local variable only. On timeout it calls get_plan. It returns completed state or raises a Chinese uncertain-status error instructing a fresh status check and rescan.

- [ ] **Step 6: Verify and commit**

Run: service\.venv\Scripts\python.exe -m pytest service/tests -v

Run: plugin\.venv\Scripts\python.exe -m pytest plugin/tests -v

Expected: all tests PASS.

~~~powershell
git add plugin/internal plugin/tools/create_plan.yaml plugin/tools/create_plan.py plugin/tools/execute_confirmed_plan.yaml plugin/tools/execute_confirmed_plan.py plugin/tests/test_plan_tools.py
git commit -m "feat: add confirmed Dify execution tools"
~~~

---

### Task 7: Implement operation and confirmed restore tools

**Files:**
- Create: plugin/tools/get_operation.yaml, get_operation.py
- Create: plugin/tools/create_restore_plan.yaml, create_restore_plan.py
- Create: plugin/tools/restore_confirmed_operation.yaml, restore_confirmed_operation.py
- Create: plugin/tests/test_restore_tools.py
- Modify: plugin/internal/client.py

**Interfaces:**
- get_operation(operation_id)
- create_restore_plan(operation_id)
- restore_plan(plan_id, approval_token)
- Restore tool receives plan_id only and follows Task 6 status reconciliation.

- [ ] **Step 1: Write failing restore tests**

Cover expiry/status display, preview without writes, token absence, successful restored state, and HTTP 410 restore_window_expired guidance.

~~~python
assert tool.client.calls == [
    ("issue_approval_token", restore_plan_id),
    ("restore_plan", restore_plan_id, "restore-token"),
]
assert "restore-token" not in message_text(messages)
~~~

- [ ] **Step 2: Confirm RED**

Run: plugin\.venv\Scripts\python.exe -m pytest plugin/tests/test_restore_tools.py -v

Expected: FAIL because restore tools are absent.

- [ ] **Step 3: Implement wrappers and tools**

~~~python
def get_operation(self, operation_id: str) -> dict[str, Any]:
    return self.request(
        "GET", f"/operations/{operation_id}"
    )

def create_restore_plan(
    self,
    operation_id: str,
) -> dict[str, Any]:
    return self.request(
        "POST",
        f"/operations/{operation_id}/restore-plans",
    )

def restore_plan(
    self,
    plan_id: str,
    approval_token: str,
) -> dict[str, Any]:
    return self.request(
        "POST",
        f"/plans/{plan_id}/restore",
        json={"approval_token": approval_token},
    )
~~~

Create separate YAML output schemas. create_restore_plan returns recovery confirmation text. restore_confirmed_operation never accepts an external token.

- [ ] **Step 4: Verify and commit**

Run: service\.venv\Scripts\python.exe -m pytest service/tests -v

Run: plugin\.venv\Scripts\python.exe -m pytest plugin/tests -v

Expected: all tests PASS.

~~~powershell
git add plugin/internal/client.py plugin/tools/get_operation.yaml plugin/tools/get_operation.py plugin/tools/create_restore_plan.yaml plugin/tools/create_restore_plan.py plugin/tools/restore_confirmed_operation.yaml plugin/tools/restore_confirmed_operation.py plugin/tests/test_restore_tools.py
git commit -m "feat: add operation restore tools"
~~~

---

### Task 8: Document, validate, and package the plugin

**Files:**
- Create: plugin/tests/test_documentation.py
- Modify: plugin/README.md
- Create: docs/dify/workflow-setup.md
- Create: docs/dify/acceptance-cases.md
- Modify: README.md

**Interfaces:**
- Produces: installable .difypkg outside Git.
- Documents credentials, nine tools, Human Input mappings and six cases.

- [ ] **Step 1: Write failing documentation assertions**

The test reads all three documents and asserts nine tool names, host.docker.internal:8787, Human Input, three success headings and three failure headings. It rejects a literal X-API-Key value.

- [ ] **Step 2: Confirm RED**

Run: plugin\.venv\Scripts\python.exe -m pytest plugin/tests/test_documentation.py -v

Expected: FAIL because required documents or sections are absent.

- [ ] **Step 3: Write exact setup and case documents**

workflow-setup.md contains:

~~~text
Start → list_files → LLM → create_plan → Human Input
Human Input.reject → End
Human Input.approve → execute_confirmed_plan → End
~~~

It also contains separate upload and restore approval flows. acceptance-cases.md copies the approved 3 success and 3 failure cases with preparation, input, Human Input choice, expected file state, expected log state and correction guidance.

- [ ] **Step 4: Run all unit tests**

Run: service\.venv\Scripts\python.exe -m pytest service/tests -v

Run: plugin\.venv\Scripts\python.exe -m pytest plugin/tests -v

Expected: all tests PASS.

- [ ] **Step 5: Package with CLI**

~~~powershell
& "D:\AI\Dify\dify\tools\dify.exe" plugin package ".\plugin"
~~~

Expected: exit 0 and a .difypkg that excludes credentials and .env.

- [ ] **Step 6: Commit without the package binary**

~~~powershell
git add README.md plugin/README.md plugin/tests/test_documentation.py docs/dify
git commit -m "docs: add Dify workflow and acceptance guide"
~~~

---

### Task 9: Run controlled Workflow and Human Input acceptance

**Files:**
- Ignored evidence: work/e2e/acceptance-results.md
- Modify after validation: docs/dify/acceptance-cases.md

**Interfaces:**
- Consumes packaged plugin, running FastAPI, Dify Docker and 1–3 controlled files.
- Produces verified six-case result without secrets.

- [ ] **Step 1: Start FastAPI with an ignored temporary key file**

Run only after approval:

~~~powershell
& ".\service\.venv\Scripts\python.exe" -m uvicorn service.app.main:app --host 0.0.0.0 --port 8787
~~~

Set DIFY_AGENT_WORKSPACE_ROOT and DIFY_AGENT_WORKSPACE_API_KEY_FILE in that process without printing the Key.

- [ ] **Step 2: Verify Docker-to-host authentication**

From the Dify API container, call /files?page=1&page_size=1 at host.docker.internal:8787. Expected: 200 with correct Key and 401 without it.

- [ ] **Step 3: Install and configure the package**

Install the local .difypkg in Dify. Set service_url to http://host.docker.internal:8787 and the matching Key. Provider validation must succeed through protected /files.

- [ ] **Step 4: Build the fixed workflows**

Map create_plan.confirmation_text to Human Input and plan_id to the approved execute node. The reject branch ends without a write tool. Create separate approved branches for upload and restore.

- [ ] **Step 5: Prepare only controlled files**

~~~text
incoming/会议记录.txt
合同-测试.txt
old-notes.txt
~~~

Record SHA-256 before testing. Do not touch unrelated files.

- [ ] **Step 6: Execute all six cases**

For each approved case, record start state, Human Input choice, result code, end state, hashes and operation ID. For API Key error, rejection and target conflict, verify zero file changes.

- [ ] **Step 7: Fresh regression and evidence**

Run: service\.venv\Scripts\python.exe -m pytest service/tests -v

Run: plugin\.venv\Scripts\python.exe -m pytest plugin/tests -v

Expected: all tests PASS.

Run: git status --short

Expected: only intentional documentation changes; work/e2e and secrets remain ignored.

- [ ] **Step 8: Commit verified result**

~~~powershell
git add docs/dify/acceptance-cases.md
git commit -m "test: verify Dify human approval workflow"
~~~

---

### Task 10: Install the verified FastAPI with WinSW

**Files:**
- Create: deployment/windows-service/DifyAgentWorkspaceTools.xml
- Create: deployment/windows-service/install.ps1
- Create: deployment/windows-service/uninstall.ps1
- Create: service/tests/test_windows_service_config.py
- Modify: README.md

**Interfaces:**
- Service: DifyAgentWorkspaceTools
- Account: NT AUTHORITY\LocalService
- Key file: work\windows-service\secrets\api-key.txt
- Logs: work\windows-service\logs
- Listener: 0.0.0.0:8787 with no Public-profile rule.

- [ ] **Step 1: Write failing static tests**

~~~python
assert root.findtext("id") == "DifyAgentWorkspaceTools"
assert root.findtext("serviceaccount/username") == (
    r"NT AUTHORITY\LocalService"
)
assert "--host 0.0.0.0 --port 8787" in root.findtext("arguments")
assert "DIFY_AGENT_WORKSPACE_API_KEY_FILE" in xml_text
assert "DIFY_AGENT_WORKSPACE_API_KEY=" not in xml_text
assert "restart" in xml_text.lower()
~~~

Also assert install.ps1 configures restricted ACL/firewall and uninstall.ps1 never deletes D:\AI\AgentWorkspace, .file-manager or .trash.

- [ ] **Step 2: Confirm RED**

Run: python -m pytest service/tests/test_windows_service_config.py -v

Expected: FAIL because deployment files are absent.

- [ ] **Step 3: Write WinSW XML**

~~~xml
<service>
  <id>DifyAgentWorkspaceTools</id>
  <name>Dify Agent Workspace Tools</name>
  <description>受 Dify 调用的本机安全文件服务</description>
  <executable>D:\AI\Codex\Projects\dify-agent-workspace-tools\service\.venv\Scripts\python.exe</executable>
  <arguments>-m uvicorn service.app.main:app --host 0.0.0.0 --port 8787</arguments>
  <workingdirectory>D:\AI\Codex\Projects\dify-agent-workspace-tools</workingdirectory>
  <serviceaccount>
    <username>NT AUTHORITY\LocalService</username>
    <allowservicelogon>true</allowservicelogon>
  </serviceaccount>
  <env name="DIFY_AGENT_WORKSPACE_ROOT" value="D:\AI\AgentWorkspace" />
  <env name="DIFY_AGENT_WORKSPACE_API_KEY_FILE" value="%BASE%\secrets\api-key.txt" />
  <logpath>%BASE%\logs</logpath>
  <log mode="roll-by-size-time">
    <sizeThreshold>10240</sizeThreshold>
    <pattern>yyyyMMdd</pattern>
    <autoRollAtTime>00:00:00</autoRollAtTime>
    <zipOlderThanNumDays>14</zipOlderThanNumDays>
    <zipDateFormat>yyyyMMdd</zipDateFormat>
  </log>
  <onfailure action="restart" delay="10 sec" />
  <startmode>Automatic</startmode>
  <delayedAutoStart>true</delayedAutoStart>
</service>
~~~

- [ ] **Step 4: Write guarded install and uninstall scripts**

install.ps1 verifies administrator identity, project paths, Python, WinSW 2.12 and completed acceptance evidence. It copies the WinSW 2.12 executable and XML into work/windows-service with the common base name DifyAgentWorkspaceTools, creates secrets/logs, generates a Key only when absent, grants secrets access only to Administrators, SYSTEM and LocalService, grants the minimum workspace modify rights, creates a Private-profile 8787 rule limited to local/Docker addresses, then installs and starts the service.

uninstall.ps1 stops/uninstalls the service and removes only its firewall rule. It retains the Key, workspace, .trash, .file-manager and logs.

- [ ] **Step 5: Verify and commit before system changes**

Run: python -m pytest service/tests/test_windows_service_config.py -v

Run: service\.venv\Scripts\python.exe -m pytest service/tests -v

Run: plugin\.venv\Scripts\python.exe -m pytest plugin/tests -v

Run: git diff --check

Expected: all tests PASS; diff check has no output.

~~~powershell
git add deployment/windows-service service/tests/test_windows_service_config.py README.md
git commit -m "feat: add WinSW service deployment"
~~~

- [ ] **Step 6: Install only after explicit approval**

Run from elevated PowerShell:

~~~powershell
& ".\deployment\windows-service\install.ps1"
~~~

Expected: service Running; /health returns 200; /files returns 401 without Key and 200 with Key; Dify Provider validates.

- [ ] **Step 7: Verify restart and final behavior**

Restart the service. Reboot Windows only with explicit user approval. Verify service autostart, Docker connectivity, rolling logs, six Workflow cases and absence of a Public-profile 8787 firewall rule.

---

## Final Verification Gate

Run fresh:

~~~powershell
service\.venv\Scripts\python.exe -m pytest service/tests -v
plugin\.venv\Scripts\python.exe -m pytest plugin/tests -v
& "D:\AI\Dify\dify\tools\dify.exe" plugin package ".\plugin"
git diff --check
git status --short
~~~

Then verify:

- Provider credential validation succeeds only with the protected /files call.
- Read-only search creates no plan and changes no files.
- Human Input rejection causes zero writes.
- Approved move/rename records completed.
- Approved restore records restored.
- Wrong API Key, user rejection and target conflict match the three documented failure cases.
- API Key, approval token, absolute workspace path and Python stack never appear in Dify outputs or committed files.
- WinSW installation occurs only after every earlier gate passes.

## Official References

- Dify Tool Plugin: https://docs.dify.ai/en/develop-plugin/dev-guides-and-walkthroughs/tool-plugin
- Dify Tool Return: https://docs.dify.ai/en/develop-plugin/features-and-specs/plugin-types/tool
- Dify Plugin CLI: https://docs.dify.ai/en/develop-plugin/getting-started/cli
- WinSW: https://github.com/winsw/winsw
