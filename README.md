# Dify 本机安全文件工具

这是一个仅允许在指定 Windows 工作区内操作文件的 FastAPI 服务。当前默认工作区为 `D:\AI\AgentWorkspace`。

当前版本已经完成本机服务核心与 HTTP API，尚未进行 Windows 服务启动配置、Dify 插件、Dify Workflow 或 Human Input。

## 已实现能力

- 分页列出和搜索文件，每页最多 10 个文件。
- 读取单个文件；15MB 以内返回 Base64 内容，超过 15MB 只返回元数据。
- 上传单个不超过 15MB 的文件，不覆盖已有文件。
- 预览创建文件夹、移动/重命名、移入 `.trash` 的整理计划。
- 使用一次性确认令牌执行整批计划，任一预检失败则整批不执行。
- 执行中失败时按逆序自动回滚。
- 操作日志和回收文件保留 14 天。
- 创建恢复计划，经二次确认后由 `restore_operation` 实际恢复文件。
- 每个计划使用独立 `RLock`；并发请求使用同一令牌时只能有一个成功。
- 除 `/health` 外，所有业务接口都要求 `X-API-Key`。

## 配置

模块级 FastAPI 应用读取两个环境变量：

| 环境变量 | 说明 | 默认值 |
| --- | --- | --- |
| `DIFY_AGENT_WORKSPACE_ROOT` | 允许访问的唯一工作区 | `D:\AI\AgentWorkspace` |
| `DIFY_AGENT_WORKSPACE_API_KEY` | 业务接口 API Key | 无；未设置时业务接口返回 503 |

客户端必须在业务请求中加入：

```text
X-API-Key: <DIFY_AGENT_WORKSPACE_API_KEY>
```

API Key 不写入项目文件，也不提供不安全的默认值。

## HTTP 接口

| 方法 | 路径 | 用途 |
| --- | --- | --- |
| `GET` | `/health` | 公开健康检查 |
| `GET` | `/files` | 分页列出文件 |
| `GET` | `/files/search` | 按名称搜索文件 |
| `GET` | `/files/content` | 获取文件元数据和可用的 Base64 内容 |
| `POST` | `/files/upload` | multipart 上传文件 |
| `POST` | `/plans` | 校验并创建待确认整理计划 |
| `POST` | `/plans/{plan_id}/approval-token` | 为待确认计划签发一次性令牌 |
| `POST` | `/plans/{plan_id}/execute` | 消费令牌并执行整理计划 |
| `GET` | `/operations/{operation_id}` | 查询操作日志与恢复期限 |
| `POST` | `/operations/{operation_id}/restore-plans` | 创建待确认恢复计划 |
| `POST` | `/plans/{plan_id}/restore` | 消费令牌并实际恢复操作 |
| `POST` | `/maintenance/cleanup-expired-operations` | 清理过期日志及对应回收目录 |

## 确认与执行顺序

整理文件：

1. 调用 `POST /plans` 创建计划并展示确认摘要。
2. 用户确认后，调用 `POST /plans/{plan_id}/approval-token` 获取一次性令牌。
3. 立即将令牌提交给 `POST /plans/{plan_id}/execute`。

恢复操作：

1. 调用 `POST /operations/{operation_id}/restore-plans` 创建恢复计划。
2. 用户确认后，为恢复计划签发一次性令牌。
3. 将令牌提交给 `POST /plans/{restore_plan_id}/restore`。

明文令牌只在签发响应中出现一次；磁盘计划文件只保存 SHA-256 哈希，消费后哈希会被移除。

## 验证

在项目根目录、虚拟环境可用时运行：

```powershell
& ".\service\.venv\Scripts\python.exe" -m pytest ".\service\tests" -v
```

测试全部使用 pytest 临时目录，不会访问真实工作区 `D:\AI\AgentWorkspace`。

## 当前未实施

- Windows 服务、自启动或后台常驻配置。
- Dify 插件。
- Dify Workflow。
- Human Input 确认节点。

这些内容不属于当前批次。

## 项目资料

- `AGENTS.md`：项目协作规则。
- `docs/implementation-plan.md`：分阶段实施计划。
- `docs/agent/`：Agent 工作流和决策规则。
- `.learnings/`：已确认经验与错误记录。
