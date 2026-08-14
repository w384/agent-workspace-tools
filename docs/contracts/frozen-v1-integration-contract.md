# 冻结纲要 v1：执行端最小集成契约

## 状态与范围

- 状态：冻结 v1；本文件只固定首轮 Gate 1 至 Gate 5 所需字段与边界。
- 非目标：GraphRAG、知识图谱、全格式解析、HA、多 Agent、第二套用户/ACL/文档权威。
- 权威关系：`Asset`、`AssetVersion`、权限主体与 ACL 由中台控制面持有；FastAPI 是公共盘唯一写入边界；Qdrant 仅保存可删除、可重建的索引副本。

## 已裁决的首轮接线口径

- `Asset`、`AssetVersion` 与 `PermissionGrant` 的权威仓储归中台控制面；RAG 不创建平行表或副本权威，只通过端口读取有效的资源范围。
- Gate 1 的上传版本状态由中台控制面发起并回写；RAG 只报告解析与索引状态。新版本在 `ready` 前或失败时，旧 active 版本持续服务。
- BFF 在已认证 session 中生成类型化 `PermissionContext`，再通过内部适配器传入文件执行器和 RAG。首轮同进程/受控内部调用可使用依赖注入；未来跨进程适配器必须验证服务间凭证。浏览器、LLM 和普通 query 参数中的 `user_id` 都不是可信主体。
- Gate 3 是版本化引用；Gate 4 是召回前越权拒绝。Gate 4 的 `DENY` 必须在候选、重排、LLM 上下文和可泄漏审计日志之前发生。

## 模块所有权

| 模块 | 所有者 | 可修改范围 | 不可修改范围 |
| --- | --- | --- | --- |
| 共同契约、本地文件执行、安全验收、跨线集成 | 执行端总负责 | `docs/contracts/`、本项目 FastAPI/插件适配层、集成测试 | 中台与 RAG 独立 worktree 文件 |
| 可信 session、控制面实体、权限/风险状态机、BFF 与审计关联 | 中台控制面 | 其独立 worktree 的 BFF、领域模型、迁移、UI/API、测试 | 本项目 FastAPI 文件执行器与 RAG 索引实现 |
| 解析、版本索引、ACL 前置检索、引用/拒答、Qdrant 副本 | RAG 后台 | 其独立 worktree 的解析、检索、索引、测试 | 本项目 FastAPI 文件执行器与中台控制面 |

跨域改动必须先在本文件的契约内完成；字段或语义变化由执行端总负责裁决，范围或架构变化上报 Q。

## 共同实体

所有标识符均为不可猜测字符串；时间为 UTC ISO 8601；路径只使用工作区相对路径。

### Asset

```json
{
  "asset_id": "asset_...",
  "workspace_id": "workspace_...",
  "current_path": "organized/report.docx",
  "path_history": ["incoming/report.docx"],
  "active_version_id": "asset_version_...",
  "status": "active"
}
```

`Asset` 是逻辑文件身份；移动或重命名只更新路径与历史，不创建第二个逻辑文档。

### AssetVersion

```json
{
  "asset_version_id": "asset_version_...",
  "asset_id": "asset_...",
  "content_fingerprint": "sha256:...",
  "source_path": "organized/report.docx",
  "state": "queued|parsing|indexed|ready|failed",
  "failure_code": null,
  "created_at": "2026-08-13T00:00:00Z"
}
```

仅 `ready` 版本可作为检索 active 版本。新版本未 `ready` 或失败时，旧 active 版本继续服务。

### PermissionGrant 与裁决

```json
{
  "actor_id": "user_...",
  "workspace_id": "workspace_...",
  "allow_prefixes": ["organized"],
  "explicit_denies": ["organized/restricted"],
  "context_version": "acl_..."
}
```

中台 BFF 仅向内部服务发送可信 `actor_id`、`workspace_id`、`allow_prefixes`、`explicit_denies` 与 `context_version`；浏览器提交的 `user_id` 不构成可信主体。

裁决枚举：`DIRECT`、`SELF_CONFIRM`、`APPROVAL_REQUIRED`、`DENY`。授权目录内、不覆盖已有文件的低风险上传为 `DIRECT`；`DENY` 为终态，不能由确认或审批绕过。

### Plan、Confirmation 与 ExecutionJob

```json
{
  "plan_id": "plan_...",
  "plan_hash": "sha256:...",
  "actor_id": "user_...",
  "asset_versions": [{"asset_id": "asset_...", "asset_version_id": "asset_version_...", "content_fingerprint": "sha256:..."}],
  "decision": "SELF_CONFIRM|APPROVAL_REQUIRED|DENY",
  "operations": [],
  "status": "pending_confirmation|approved|executing|completed|failed|denied"
}
```

`Confirmation` 只关联 `plan_id` 与决策结果；内部一次性凭证不得进入浏览器、LLM、审计展示或跨服务持久化。

`plan_hash` 使用版本化 canonical JSON 计算：UTF-8、对象键排序、固定分隔符，输入至少包含 `contract_version`、`plan_id`、`workspace_id`、`actor_id`、`decision_state`、`decision_id`、`policy_version`、`context_version`、规范化 `operations`、按 `asset_id` 稳定排序的 `asset_versions`（含 `asset_id`、`asset_version_id`、`content_fingerprint`）和 `expires_at`。`policy_version` 与 `context_version` 是两个独立、不可猜测且必填的版本标识，不能互相代替。`idempotency_key` 属于执行请求，不进入 `plan_hash`。

当前本地执行器的兼容安全增量已将操作源文件的相对路径与流式 SHA-256 快照写入计划、绑定到其本地 `plan_hash`，并在一次性令牌消费前重算比较；普通计划继续禁止访问管理目录，恢复计划仅允许快照解析后仍位于工作区 `.trash` 内的受控源。该实现不替代控制面权威 `AssetVersion` 快照，也不能消除“重验完成后、实际移动前”的文件系统 TOCTOU 窗口；企业接线仍须由可信内部调用提供并重验权威资产版本与指纹。

`SELF_CONFIRM` 由计划发起人本人确认后直接进入执行，管理员 B 不产生待办。`APPROVAL_REQUIRED` 必须先由发起人 A 确认意图，再创建 B 的待审批项；B 必须不是发起人，并且持有由服务端配置注入的稳定审批角色 ID。角色显示名称不能作为授权依据。`DENY` 不创建 Confirmation 或 Approval。

一次性凭证只由 BFF 的执行器内部适配层在单次内部调用链中临时持有、签发并消费；不得进入控制面实体、浏览器、Dify、接口响应、持久化审计或模型上下文。

控制面 `plan_id/plan_hash` 与本地文件执行器生成的 `executor_plan_id/executor_plan_hash` 是两组不同的标识和摘要，不能互相替换。控制面仅在服务端 Plan 记录中保存执行器计划引用；浏览器、Dify 与审计响应不返回该引用。BFF 先验证控制面 `plan_hash`、可信身份、ACL、版本/指纹和过期时间，再由内部适配器使用执行器自己的 `executor_plan_hash` 签发并立即消费一次性令牌。执行器仍独立重验自己的计划摘要、源文件快照、身份和路径权限。

```json
{
  "execution_job_id": "job_...",
  "plan_id": "plan_...",
  "idempotency_key": "request_...",
  "status": "queued|running|completed|failed|rolled_back",
  "operation_id": "operation_..."
}
```

同一 `plan_id + plan_hash + idempotency_key` 只产生一个执行结果；执行器在写入前重新验证可信身份上下文、ACL 裁决、`plan_hash`、资产版本/指纹和目标冲突。任一预检失败为整批零写入；执行中失败回滚并留下审计证据。

控制面存储对 `(plan_id, plan_hash, idempotency_key)` 建立复合唯一约束；状态统一为 `queued|running|completed|failed|rolled_back`。BFF 的 `DENY` 必须零下游调用；文件执行器仍消费受信 ACL 快照与裁决做最终防线，任一层 `DENY` 都不能由确认或审批绕过。

### AuditEvent 与 Chunk

```json
{
  "audit_event_id": "audit_...",
  "actor_id": "user_...",
  "correlation_id": "request_...",
  "event_type": "plan_created|confirmation_recorded|execution_completed|retrieval_denied",
  "decision": "SELF_CONFIRM|APPROVAL_REQUIRED|DENY",
  "asset_id": "asset_...",
  "asset_version_id": "asset_version_...",
  "outcome": "success|denied|failed"
}
```

```json
{
  "chunk_id": "chunk_...",
  "asset_id": "asset_...",
  "asset_version_id": "asset_version_...",
  "content_fingerprint": "sha256:...",
  "index_state": "indexed|superseded|deleted"
}
```

`Chunk` 只索引 `ready` 的 `AssetVersion`；不存为第二份权威文档。Qdrant 按 `asset_version_id` 可删除、可重建。

## 内部接口

### BFF -> 文件执行器

`POST /internal/file-plans`

请求必须包含可信权限上下文、候选操作、资产版本与 `idempotency_key`；响应必须含 `plan_id`、`plan_hash`、`decision`、影响摘要和 `audit_event_id`。`DENY` 返回 403 语义，不创建可批准计划。

`POST /internal/file-plans/{plan_id}/confirm`

仅 `SELF_CONFIRM` 或已完成独立审批的 `APPROVAL_REQUIRED` 可调用；执行器内部签发并消费一次性凭证。响应含 `execution_job_id` 与状态，不返回凭证。

### BFF -> RAG

RAG 的 `PermissionContext` 必须与 BFF 已认证会话中的 `TrustedActorContext` 精确绑定：`tenant_id/workspace_id`、`principal_id/actor_id`、`group_ids`、`session_id` 和 `request_id` 任一不一致即在检索前拒绝。RAG 适配层只读取控制面权威 Asset、active ready AssetVersion 和 PermissionGrant；它按每个 Asset 的当前路径重算 `QUERY` 裁决，显式 `DENY` 优先，且只向检索索引下发 `(asset_id, active_version_id)` 原子对。索引、重排或引用适配器的任何越域返回仍由 RAG 二次 fail-closed 校验。

`POST /internal/retrieval/query`

请求必须包含可信权限上下文和查询；RAG 必须先应用 `explicit_denies` 与 `allow_prefixes`，再进行候选召回、重排或 LLM 上下文组装。

`DENY` 响应必须至少含：

```json
{
  "decision": "DENY",
  "retrieved_count": 0,
  "llm_invoked": false,
  "citations": [],
  "audit_event_id": "audit_..."
}
```

无证据回答返回 `evidence_insufficient`，并提供仅包含当前 active `asset_version_id` 的版本化引用。

### AssetVersion -> RAG 索引状态

`POST /internal/asset-versions/{asset_version_id}/index-status`

允许状态转换：`queued -> parsing -> indexed -> ready`，或任意非 ready 状态转 `failed`。`failed` 不替换 `Asset.active_version_id`。

## 首轮 Gate 对应证据

| Gate | 最小验收证据 |
| --- | --- |
| Gate 1 上传版本 | `AssetVersion` 从 `queued` 到 `ready`；失败 v2 不替换 v1 active。 |
| Gate 2 自确认整理 | 授权 A 的低风险操作得到 `SELF_CONFIRM`；B 无审批项；执行前重验并产生审计。 |
| Gate 3 版本化引用 | 检索结果只引用 active `asset_version_id` 与对应 `chunk_id`。 |
| Gate 4 越权检索前失败 | `DENY`、`retrieved_count=0`、`llm_invoked=false`；被拒 chunk 不出现于候选、LLM 上下文或安全日志。 |
| Gate 5 重复演示与重置 | 重复请求按幂等键返回同一执行结果；重置只删除演示副本与可重建索引。 |
