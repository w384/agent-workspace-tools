# Dify Workflow 配置指导

本项目的安全边界是 Windows FastAPI 服务。Dify Agent/Workflow 只读取文件元数据、生成候选计划并桥接调用；不直接操作本机文件。

## Provider 凭据

- `service_url`：本机服务地址。当前本地 Demo 监听 `8890`，Dify 容器使用 `http://host.docker.internal:8890`。
- `api_key`：在 Dify Provider 凭据界面手工填写，不写入 Workflow、模型输入、日志或仓库。
- Provider 通过受保护的 `list_files` 接口验证凭据。

## 自然语言整理主流程

```text
Start → list_files → LLM → create_plan → Human Input
Human Input.reject → End
Human Input.approve → execute_confirmed_plan(plan_id, plan_hash) → End
```

LLM 输入只包括用户整理要求、当前页文件元数据和当前用户可访问的路径范围；LLM 不读取文件正文，也不接收 API Key 或确认令牌。

LLM 只输出 `operations_json` 数组，允许的操作为 `create_folder`、`move_rename`、`trash`。绝对路径、`..`、越权路径、无法判断的操作和超过批量限制的计划直接停止，不进入 Human Input。

## 工具与确认边界

- `list_files`、`search_files`、`get_file`：只读工具，可在扫描和分析阶段使用。
- `create_plan`：只校验并生成确认计划，不修改文件；输出 `plan_id` 与 `plan_hash`，两者都必须随确认内容保存。
- `execute_confirmed_plan`：只放在 Human Input 批准分支；`plan_id` 和 `plan_hash` 必须分别绑定到同一个 `create_plan` 节点的原始输出，禁止由 LLM 生成、执行前重新查询或手工改写。插件内部申请并立即消费一次性令牌，不把令牌返回给 Workflow 或模型。
- `upload_file`：只放在上传专用 Human Input 批准分支；非覆盖写入，目标目录仍由 FastAPI 按 `user_id` 复核。

拒绝、取消或超时分支不调用任何写入工具。执行超时后先查询计划状态，不重复提交执行请求。

当前仓库内的 `local-workspace-tools-permission-demo-v0.0.6.yml` 是已验证的历史导出，不包含新的 `plan_hash` 连线。发布下一插件版本时必须在 Dify 页面重新绑定工具节点并导出对应新版本 Workflow；在此之前不得把旧导出作为新执行契约的验收证据。

## 上传流程

```text
用户选择文件 → Human Input 确认文件名、大小、目标目录 → upload_file → End
```

## 当前未纳入

操作日志查询和恢复工具尚未注册到当前 Provider；知识库、RAG、向量库和复杂 Agentic RAG 不属于本项目阶段。
