# Dify 本机工作区工具集成设计

日期：2026-08-11  
状态：待用户审阅  
项目：`dify-agent-workspace-tools`

## 1. 目标

在不向 Dify 暴露 Windows 任意文件系统权限的前提下，让本机部署的 Dify 通过受控工具读取和整理 `D:\AI\AgentWorkspace`。

第一版以“能安全验证完整流程”为目标：Dify 负责理解任务、生成整理计划和发起人工确认；本机 FastAPI 服务负责路径隔离、计划校验、原子执行、操作日志和恢复；Dify 插件负责把两者连接起来，并隐藏 API Key 和一次性批准令牌。

## 2. 当前基线

- Dify 本机版本：`1.16.1`，源代码提交 `6f8ed69ee1`。
- Dify Plugin CLI：Windows AMD64 `0.6.10`，路径为 `D:\AI\Dify\dify\tools\dify.exe`。
- 本机服务：FastAPI，现有 12 个路由，其中 `/health` 为公开健康检查，其余接口受 `X-API-Key` 保护。
- 本机服务测试：现有 56 项测试通过，后续改动不得破坏这些测试。
- 工作区根目录：`D:\AI\AgentWorkspace`。
- 项目目录：`D:\AI\Codex\Projects\dify-agent-workspace-tools`。

## 3. 范围

### 3.1 第一版包含

- 一个 Dify Tool Provider。
- 九个独立工具：读取、上传、计划、执行、日志和恢复。
- 固定 Dify Workflow。
- 写入操作前使用 Human Input。
- 新增计划状态查询接口，用于执行超时后的状态核对。
- 插件与本机服务的 API Key 配置。
- 端到端验证通过后，使用 WinSW 将本机服务安装为 Windows 服务。

### 3.2 第一版不包含

- Agent 自主调用写入工具。
- 直接暴露移动、重命名、删除、批准令牌签发或原始执行接口。
- 覆盖上传已有文件。
- 永久删除或自动清空 `.trash`。
- 向公网开放本机服务。
- 发布到 Dify Marketplace。
- 一次确认后连续执行多个分页批次；每一批仍须独立确认。

## 4. 总体架构

```text
Dify Workflow / Human Input
        |
        v
Dify Tool 插件
        |  X-API-Key
        v
http://host.docker.internal:8787
        |
        v
Windows 本机 FastAPI
        |
        v
D:\AI\AgentWorkspace
```

组件职责：

1. Dify Workflow：组织读取、模型分析、计划预览、人工确认和执行顺序。
2. Human Input：只确认已经生成的计划，不接触 API Key 或一次性批准令牌。
3. Dify 插件：提供结构稳定的工具，持有服务地址与 API Key，并在确认执行时内部申请和立即消费一次性批准令牌。
4. FastAPI：限制工作区根目录、校验整批操作、原子执行、记录日志、创建恢复计划和执行恢复。
5. WinSW：在端到端流程验证后，负责本机服务的开机启动和故障重启。

## 5. 插件目录与组件

插件放在：

```text
D:\AI\Codex\Projects\dify-agent-workspace-tools\plugin
```

插件和 `service` 使用彼此独立的依赖文件与虚拟环境。插件内部设置一个共享 `WorkspaceClient`，统一负责：

- 添加 `X-API-Key`。
- URL 拼接和请求超时。
- JSON 响应解析。
- 把服务端错误转换为中文可操作提示。
- 屏蔽 API Key、Windows 绝对路径和调用栈。
- 对读取请求进行有限重试。
- 对执行超时先查询计划状态，禁止盲目重复执行。

Provider 凭据：

- `service_url`：默认开发地址 `http://host.docker.internal:8787`。
- `api_key`：密码字段，由 Dify 加密保存。

凭据验证必须调用受保护的 `GET /files?page=1&page_size=1`，不能只调用公开的 `/health`，否则无法证明 API Key 有效。

## 6. 工具清单

| Dify 工具 | 类型 | 本机行为 | 是否需要 Human Input |
|---|---|---|---|
| `list_files` | 读取 | 分页扫描文件并返回元数据 | 否 |
| `search_files` | 读取 | 按名称或路径搜索文件 | 否 |
| `get_file` | 读取 | 读取不超过 15MB 的文件内容 | 否 |
| `upload_file` | 写入 | 上传新文件，禁止覆盖 | 是（上传专用固定流程） |
| `create_plan` | 预览 | 校验并保存整理计划，不改文件 | 否 |
| `execute_confirmed_plan` | 写入 | 内部签发一次性令牌并立即执行计划 | 是 |
| `get_operation` | 读取 | 查询操作日志和恢复期限 | 否 |
| `create_restore_plan` | 预览 | 生成恢复计划，不改文件 | 否 |
| `restore_confirmed_operation` | 写入 | 内部签发一次性令牌并立即执行恢复 | 是 |

禁止暴露为 Dify 工具的底层能力：

- 单独的 `issue_approval_token`。
- 原始 `execute_plan`。
- 直接 `move_rename`。
- 直接 `delete_item`。
- 永久清理回收站。

这些限制确保模型不能绕过计划预览和人工确认。

## 7. 计划格式与确认文本

由于 Dify 工具参数不适合接收长度不定的复杂对象数组，`create_plan` 接收字符串参数 `operations_json`。示例：

```json
[
  {"action":"create_folder","destination":"sorted"},
  {"action":"move_rename","source":"notes.txt","destination":"sorted/notes.txt"},
  {"action":"trash","source":"old-notes.txt"}
]
```

`create_plan` 至少返回：

- `plan_id`
- `status`
- `file_count`
- `confirmation_text`
- `confirmation_json`

Human Input 展示的 `confirmation_text` 固定为：

```text
计划编号：
文件数量：
新建文件夹：
移动明细：原路径 → 新路径
重命名明细：原文件名 → 新文件名
回收明细：哪些文件会移入 .trash
```

每个计划最多处理 10 个文件，创建文件夹不计入文件数量。扫描可以返回总数，但当前批次只向模型提供最多 10 个文件。超过 10 个文件时分页处理，每一批生成独立计划并独立确认。

单个文件最大读取尺寸为 15MB。超过 15MB 时只返回名称、类型、大小和日期，不读取内容。

## 8. Workflow 与 Human Input

主整理流程：

```text
Start
  |
  v
list_files
  |
  v
LLM 生成 operations_json
  |
  v
create_plan
  |
  v
Human Input 展示 confirmation_text
  |--- 拒绝 ---> 结束，不签发令牌，不修改文件
  |
  `--- 批准 ---> execute_confirmed_plan ---> 返回执行结果
```

恢复流程：

```text
get_operation
  |
  v
create_restore_plan
  |
  v
Human Input 展示恢复明细
  |--- 拒绝 ---> 结束，不修改文件
  |
  `--- 批准 ---> restore_confirmed_operation ---> 返回恢复结果
```

上传流程：

```text
选择待上传文件与目标相对路径
  |
  v
Human Input 展示文件名、大小和目标路径
  |--- 拒绝 ---> 结束，不上传
  |
  `--- 批准 ---> upload_file ---> 返回上传结果
```

上传只允许创建新文件，目标已经存在时必须失败，不能覆盖。上传流程不复用整理计划令牌，因为它不执行移动、重命名或回收操作，但仍必须放在固定 Workflow 的 Human Input 批准分支中。

写入工具只能放在固定 Workflow 的 Human Input 批准分支中，第一版不提供给 Agent 自主选择。

## 9. 令牌、原子性与并发

API Key 与一次性批准令牌用途不同：

- API Key 证明调用方是获准的 Dify 插件，每次受保护请求都要携带。
- 一次性批准令牌证明某个已经校验的计划获准执行，只能消费一次。

`execute_confirmed_plan` 和 `restore_confirmed_operation` 在插件内部完成“申请令牌 → 立即执行”，不得把令牌返回给模型或 Workflow。服务端通过并发锁保证同一令牌只能成功消费一次。

批量执行前必须重新做整批预检。任意一项校验失败时整批不执行，避免只整理一半。操作日志保留 14 天；在可恢复期限内，可以根据日志创建恢复计划。

## 10. 状态查询、超时与重试

本机服务新增：

```http
GET /plans/{plan_id}
```

返回计划状态、文件数量、创建时间、执行时间和结果摘要，且与其他业务接口一样受 `X-API-Key` 保护。

重试规则：

- `list_files`、`search_files`、`get_file`、`get_operation` 和计划状态查询可有限重试。
- 创建计划只有在明确确认服务端未接收请求时才可重试。
- 实际执行和恢复不得盲目重试。
- 执行请求超时后，插件先查询 `/plans/{plan_id}`：若已完成则返回既有结果；若仍可执行则提示用户核对后重试；若失败则返回明确失败原因。

## 11. 错误输出

每个工具同时返回适合用户阅读的中文文本和适合 Workflow 判断的 JSON。错误至少包含稳定的错误码、中文说明和下一步建议。

错误输出不得包含：

- API Key 或批准令牌。
- `D:\AI\AgentWorkspace` 的绝对路径。
- Python 调用栈。
- 服务内部密钥或环境变量值。

## 12. 指导案例

以下六个案例必须同时写入插件说明、Workflow 配置指导和验收清单。

### 12.1 成功案例一：只读搜索

用户目标：查找名称或路径中包含“合同”的文件。

执行：Workflow 调用 `search_files`，不创建计划，不进入 Human Input，不执行写入。

预期：返回匹配文件的相对路径、名称、类型、大小和日期；工作区无变化。

指导：如果只是查找或查看文件，必须优先使用只读工具，不能创建整理计划。

### 12.2 成功案例二：批准移动并重命名

输入：

```text
incoming/会议记录.txt
```

目标：

```text
会议资料/2026-08-会议记录.txt
```

执行：模型生成 `operations_json`，`create_plan` 返回确认文本，用户在 Human Input 批准后调用 `execute_confirmed_plan`。

预期：目标文件存在，源文件不存在，操作日志状态为 `completed`；批准前文件保持不变。

指导：移动和重命名可以合并为一个 `move_rename` 操作，但必须在确认文本中分别让用户看清原路径、新路径和名称变化。

### 12.3 成功案例三：批准恢复

前提：`old-notes.txt` 已通过计划移入 `.trash`，对应操作日志仍在 14 天保留期内。

执行：`get_operation` 查询日志，`create_restore_plan` 生成恢复预览，用户批准后调用 `restore_confirmed_operation`。

预期：文件恢复到原位置，原操作日志显示 `restored`，恢复动作也有可追踪记录。

指导：恢复不是直接移动文件，而是基于已记录的操作生成新计划并再次确认。

### 12.4 失败案例一：API Key 错误

触发：插件 Provider 中的 API Key 与本机服务配置不一致。

预期：凭据验证失败，Workflow 不开始扫描；错误中不显示 Key，文件无变化。

提示：检查本机服务的环境变量或密钥文件与插件凭据是否一致，然后重新验证 Provider。

### 12.5 失败案例二：用户拒绝确认

触发：计划已生成，但用户在 Human Input 选择拒绝。

预期：不申请一次性令牌，不调用执行接口，文件保持不变；Workflow 返回“计划已取消”。

提示：如需调整整理方式，修改指令后重新扫描并创建新计划，不能执行被拒绝的旧计划。

### 12.6 失败案例三：确认前出现目标冲突

触发：创建计划时目标为空，但在用户批准前，目标位置出现同名文件。

预期：执行前整批预检失败；所有源文件保持原位，不发生部分移动；返回目标冲突错误。

提示：重新扫描工作区，解决同名冲突后创建新计划。不得通过覆盖目标文件来规避冲突。

## 13. Windows 服务设计

只有在插件和 Workflow 端到端验证通过后，才安装 Windows 服务。

- 服务管理器：WinSW `2.12` 稳定版，不使用 3.x 预览版。
- 服务名：`DifyAgentWorkspaceTools`。
- 运行账户：`LocalService`，不使用高权限 `LocalSystem`。
- 启动：自动延迟启动，失败后自动重启。
- 监听：Uvicorn `0.0.0.0:8787`，供 Docker 通过 `host.docker.internal` 访问。
- 日志：`work\windows-service\logs`，配置滚动与保留策略。
- 密钥文件：`work\windows-service\secrets\api-key.txt`，加入 `.gitignore`。
- 环境变量：新增支持 `DIFY_AGENT_WORKSPACE_API_KEY_FILE`，WinSW XML 只保存密钥文件路径，不保存 Key 本身。
- ACL：密钥文件仅管理员和服务账户可读；服务账户只获得项目运行文件与 `D:\AI\AgentWorkspace` 所需的最小权限。
- 防火墙：只允许本机和 Docker 私有网络访问 8787，不允许公网入站。

本步骤此前没有提前实施，是因为早期范围明确暂不做 Windows 服务、Dify 插件、Workflow 和 Human Input；同时服务化会增加账户权限、日志、启动和网络排错因素，必须放在端到端功能验证之后。

## 14. 测试与验收

按以下顺序验证：

1. 保持现有 56 项本机服务测试全部通过。
2. 为 `GET /plans/{plan_id}` 增加认证、存在、不存在和状态字段测试。
3. 为 `WorkspaceClient` 增加请求头、超时、重试、错误解析和敏感信息屏蔽测试。
4. 为九个 Dify 工具增加参数映射、文本输出和 JSON 输出测试。
5. 使用 Dify CLI 校验插件并打包 `.difypkg`。
6. 从 Dify Docker 容器验证 `host.docker.internal:8787` 可访问。
7. 在真实工作区中只创建 1–3 个受控测试文件。
8. 运行完整 Workflow，验证只读搜索成功案例。
9. Human Input 选择拒绝，确认文件完全不变。
10. Human Input 选择批准，确认移动和重命名只在批准后发生。
11. 验证恢复成功案例。
12. 验证 API Key 错误、用户拒绝和目标冲突三个失败案例。
13. 端到端全部通过后安装 WinSW，再重启计算机或服务验证自动启动、Docker 连通性和日志滚动。

验收标准：

- Dify 能读取和搜索限定工作区。
- 模型不能绕过计划预览与 Human Input 执行写入。
- API Key 和一次性令牌不进入模型上下文。
- 每批最多处理 10 个文件，超过 15MB 不读取正文。
- 任一预检失败时整批零执行。
- 六个指导案例结果与本设计完全一致。
- 所有自动化测试通过，受控端到端测试留下可审计日志。
- Windows 服务以最小权限稳定运行，8787 不向公网开放。

## 15. 实施顺序

1. 为本机服务补充计划状态接口和 API Key 文件读取能力，并采用测试驱动开发。
2. 初始化 Dify 插件骨架，实现 Provider 和共享 `WorkspaceClient`。
3. 先实现读取工具，再实现计划与确认执行工具，最后实现恢复工具。
4. 编写插件说明、Workflow 配置指导和六个案例。
5. 使用 CLI 验证、测试和打包插件。
6. 在 Dify 中安装插件，搭建固定 Workflow 与 Human Input。
7. 运行受控端到端验收。
8. 安装 WinSW Windows 服务并完成最终运行验证。

每个实施阶段都必须先写失败测试、确认失败原因正确，再写最小实现并运行完整回归测试。
