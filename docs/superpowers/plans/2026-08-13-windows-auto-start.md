# Windows Auto-Start Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在当前用户登录后自动、安全地启动本机 FastAPI 文件服务，并提供可重复安装、验证和卸载能力。

**Architecture:** 项目内 PowerShell 启动脚本负责校验路径、设置进程级环境变量和启动 Uvicorn；独立安装/卸载脚本只管理一个固定名称的当前用户计划任务。测试通过静态契约与 PowerShell 语法解析验证脚本，不接触真实密钥内容。

**Tech Stack:** Windows PowerShell 5.1、Task Scheduler、Python 3.12、Uvicorn、pytest

## Global Constraints

- 服务监听 `0.0.0.0:8890`，Dify 使用 `http://host.docker.internal:8890`。
- 工作区固定为 `D:\AI\AgentWorkspace`，权限数据库固定为 `D:\AI\AgentWorkspace\.file-manager\permissions.db`。
- API Key 只通过 `DIFY_AGENT_WORKSPACE_API_KEY_FILE` 指向现有密钥文件，禁止读取后写入任务参数、日志或源码。
- 使用项目 `service\.venv\Scripts\python.exe`，不注册 Windows Service、不修改防火墙。
- 安装任务以当前用户登录为触发器；卸载只删除固定任务，不删除项目或工作区文件。

---

### Task 1: 启动脚本与静态契约测试

**Files:**
- Create: `scripts/start-service.ps1`
- Create: `service/tests/test_windows_auto_start.py`

**Interfaces:**
- Consumes: 项目根目录、现有 API Key 文件路径。
- Produces: `start-service.ps1 -ApiKeyFile <path>`，成功时以前台 Uvicorn 进程运行，失败时返回非零退出码。

- [ ] **Step 1: 写失败测试**

  在 `test_windows_auto_start.py` 中断言脚本存在，并包含四个进程级环境变量赋值、路径校验、固定 host/port，以及不包含任何密钥值。

- [ ] **Step 2: 验证测试失败**

  Run: `service\.venv\Scripts\python.exe -m pytest service\tests\test_windows_auto_start.py -v`

  Expected: FAIL，因为 `scripts/start-service.ps1` 尚不存在。

- [ ] **Step 3: 最小实现**

  脚本参数仅接收 `ApiKeyFile`；通过 `$PSScriptRoot` 解析项目根目录，依次用 `Test-Path -LiteralPath` 验证 Python、密钥文件、工作区和权限数据库；设置 `DIFY_AGENT_WORKSPACE_ROOT`、`DIFY_AGENT_WORKSPACE_PERMISSIONS_DB`、`DIFY_AGENT_WORKSPACE_API_KEY_FILE`，再执行：

  ```powershell
  & $pythonPath -m uvicorn service.app.main:app --host 0.0.0.0 --port 8890
  exit $LASTEXITCODE
  ```

- [ ] **Step 4: 语法与测试验证**

  Run: PowerShell Parser 静态解析脚本；随后运行目标 pytest。

  Expected: 无解析错误，测试 PASS。

### Task 2: 计划任务安装与卸载脚本

**Files:**
- Create: `scripts/install-auto-start.ps1`
- Create: `scripts/uninstall-auto-start.ps1`
- Modify: `service/tests/test_windows_auto_start.py`

**Interfaces:**
- Consumes: Task 1 的 `start-service.ps1 -ApiKeyFile`。
- Produces: 固定任务名 `DifyAgentWorkspaceTools`；安装脚本支持重复执行，卸载脚本在任务不存在时也成功。

- [ ] **Step 1: 写失败测试**

  断言安装脚本使用 `New-ScheduledTaskAction`、`New-ScheduledTaskTrigger -AtLogOn`、`Register-ScheduledTask -Force` 和重试设置；断言任务参数只有密钥文件路径而没有密钥内容；断言卸载脚本使用固定名称和 `Unregister-ScheduledTask -Confirm:$false`。

- [ ] **Step 2: 验证测试失败**

  Run: `service\.venv\Scripts\python.exe -m pytest service\tests\test_windows_auto_start.py -v`

  Expected: FAIL，因为安装和卸载脚本尚不存在。

- [ ] **Step 3: 最小实现**

  安装脚本先验证启动脚本与密钥文件，构造隐藏窗口 PowerShell 动作和当前用户登录触发器，设置每分钟重试、最多三次，然后用 `Register-ScheduledTask -Force` 创建或更新任务。卸载脚本只查询并删除 `DifyAgentWorkspaceTools`。

- [ ] **Step 4: 语法与测试验证**

  Run: 对三个 PowerShell 文件执行 Parser 静态解析；运行目标 pytest。

  Expected: 无解析错误，测试 PASS。

### Task 3: 运维文档、真实安装与端到端验证

**Files:**
- Create: `docs/windows-auto-start.md`
- Modify: `README.md`

**Interfaces:**
- Consumes: 三个 PowerShell 脚本和现有密钥文件路径。
- Produces: 可执行安装、健康检查、任务检查、停止和卸载说明；当前机器上存在有效登录触发任务。

- [ ] **Step 1: 更新文档**

  文档给出安装命令、`Get-ScheduledTask` 检查、`Start-ScheduledTask` 手动触发、`/health` 验证和卸载命令；明确不会输出 API Key，且计划任务不会等待 Docker 启动。

- [ ] **Step 2: 运行完整测试**

  Run: `service\.venv\Scripts\python.exe -m pytest service\tests -q`

  Expected: 全部 PASS。

- [ ] **Step 3: 安装当前用户计划任务**

  Run: `powershell.exe -ExecutionPolicy Bypass -File scripts\install-auto-start.ps1 -ApiKeyFile <现有密钥文件>`

  Expected: 唯一任务 `DifyAgentWorkspaceTools` 为 Ready，动作参数不包含密钥明文。

- [ ] **Step 4: 触发并验证服务**

  手动触发任务，验证 `http://127.0.0.1:8890/health` 和 Docker 内 `http://host.docker.internal:8890/health`；不打印受保护接口凭据。

- [ ] **Step 5: 最终检查与日志**

  Run: `git diff --check`

  Expected: 无 whitespace error。将脚本、文档、测试、计划任务安装和验证结果写入当天 `project-changes.log`。
