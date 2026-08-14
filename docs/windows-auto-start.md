# Windows 登录后自动启动

本项目使用当前用户级 Windows 计划任务 `DifyAgentWorkspaceTools`，在用户登录后后台启动 FastAPI 服务。它不会注册 Windows Service、修改防火墙或把 API Key 明文写入任务参数。

## 安装

在项目根目录运行，参数值是现有 API Key 文件路径：

```powershell
powershell.exe -ExecutionPolicy Bypass -File .\scripts\install-auto-start.ps1 -ApiKeyFile "<API Key 文件路径>"
```

安装脚本可重复执行；同名任务会被更新，不会产生重复任务。

## 检查与启动

```powershell
Get-ScheduledTask -TaskName DifyAgentWorkspaceTools
Start-ScheduledTask -TaskName DifyAgentWorkspaceTools
Invoke-RestMethod http://127.0.0.1:8890/health
```

Dify 在 Docker 内仍使用：

```text
http://host.docker.internal:8890
```

服务日志位于：

```text
D:\AI\AgentWorkspace\.file-manager\logs\service.log
```

计划任务依赖用户登录，不会在登录前运行，也不会等待 Docker Desktop 启动。Dify 晚于服务启动不影响使用；如果端口 `8890` 已被其他进程占用，服务启动会失败并按任务设置重试。

## 停止

先确认监听 `8890` 的进程确实是本项目 Uvicorn，再结束该进程。不要按名称批量停止所有 Python 进程。

```powershell
Get-NetTCPConnection -LocalPort 8890 -State Listen | Select-Object OwningProcess
Get-CimInstance Win32_Process -Filter "ProcessId=<PID>" | Select-Object ProcessId,CommandLine
Stop-Process -Id <PID>
```

## 卸载自动启动

```powershell
powershell.exe -ExecutionPolicy Bypass -File .\scripts\uninstall-auto-start.ps1
```

卸载只删除计划任务，不停止已运行服务，也不删除项目、工作区、权限数据库、日志或密钥文件。
