# Windows 登录后自动启动设计

## 目标

为本机 FastAPI 文件服务提供可审计、可重复安装和可撤销的 Windows 自动启动方案。当前用户登录后，计划任务在后台启动服务并监听 `0.0.0.0:8890`，供 Docker 内的 Dify 通过 `host.docker.internal:8890` 访问。

## 范围

项目内新增启动、安装和卸载脚本及操作说明。安装脚本创建当前用户级计划任务；卸载脚本只删除该任务。脚本不注册 Windows Service，不修改防火墙，不复制或输出 API Key，不改变 Dify 配置。

## 配置与安全边界

- 工作区：`D:\AI\AgentWorkspace`。
- 权限数据库：`D:\AI\AgentWorkspace\.file-manager\permissions.db`。
- API Key：仅通过 `DIFY_AGENT_WORKSPACE_API_KEY_FILE` 指向现有密钥文件，脚本和任务参数不保存密钥明文。
- Python：使用项目 `service\.venv\Scripts\python.exe`。
- 服务入口：`uvicorn service.app.main:app --host 0.0.0.0 --port 8890`。
- 计划任务以当前登录用户身份运行，不请求管理员权限。

## 组件

1. `scripts/start-service.ps1`：校验 Python、密钥文件、工作区和权限数据库，设置进程级环境变量并启动 Uvicorn。
2. `scripts/install-auto-start.ps1`：创建或更新固定名称的登录触发计划任务，动作指向启动脚本；失败后按计划任务策略重试。
3. `scripts/uninstall-auto-start.ps1`：只移除固定名称计划任务，可重复运行。
4. `docs/windows-auto-start.md`：记录安装、验证、停止、卸载和故障排查步骤。

## 行为与错误处理

- 安装前验证所有路径，任何必要文件缺失时终止，不创建残缺任务。
- 重复安装更新同名任务，不产生重复任务。
- 若 8890 已被占用，Uvicorn 启动失败并由计划任务重试，不结束或替换未知进程。
- 日志写入工作区管理目录下的服务日志文件，避免进入插件包和 Workflow。
- 卸载计划任务不会终止当前已运行的服务；停止操作由文档提供明确命令并按进程命令行精准识别。

## 验证标准

- 脚本静态语法检查通过。
- 安装脚本可在当前用户下创建唯一计划任务，任务动作不含 API Key 明文。
- 手动触发任务后，`http://127.0.0.1:8890/health` 返回成功。
- Docker 容器可访问 `http://host.docker.internal:8890/health`。
- 注销或重启后登录，服务自动恢复。
- 卸载后计划任务不存在，项目文件和工作区数据不受影响。

## 非目标

- 不实现 Windows Service、系统启动前运行、多用户会话共享、自动修改防火墙或密钥轮换。
- 不更改 FastAPI 的权限、审批令牌和文件写入边界。
