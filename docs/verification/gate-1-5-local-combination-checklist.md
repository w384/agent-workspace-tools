# Gate 1–5 本地组合验收可复验清单

> 状态：2026-08-13 本地组合验收已通过。本清单不构成生产、企业实机、Windows/SMB ACL 或正式发布基线。

## 复验边界与当前工作树

- 工作目录：`D:\AI\Codex\Projects\agent-workspace-tools`。
- 复验解释器：`D:\AI\Codex\Projects\agent-workspace-tools\service\.venv\Scripts\python.exe`。
- 最近完整回归（2026-08-13）：`service/tests + control_plane/tests` 为 `180 passed in 2.18s`；`plugin/tests` 为 `103 passed in 1.94s`，含 2 个既有第三方警告；`git diff --check` 退出码为 0，仅打印既有 LF/CRLF 转换警告。
- 当前提交状态：未暂存、未提交、未推送、未发布。最近核对的 porcelain 为 48 条（目录聚合），`staged=0`，`git ls-files --others --exclude-standard` 为 64 个未跟踪文件；不得把本清单误读为干净工作树或发布候选。
- 所有测试均使用临时目录、内存控制面或可重建索引副本；未访问 `D:\AI\AgentWorkspace` 真实公共盘，未改变 Windows/SMB ACL。
- 本轮变更、RED/GREEN 和回归记录：`D:\AI\Codex\Codex\2026\08\13\project-changes.log`。

运行前，在项目根目录执行：

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
$py = '.\service\.venv\Scripts\python.exe'
git status --short
```

## Gate 1：上传、版本状态与旧 active 保留

**复验命令：**

```powershell
& $py -B -m pytest `
  'control_plane/tests/test_gate1_upload.py' `
  'service/tests/rag/test_ingestion.py' `
  'service/tests/rag/test_pipeline_integration.py' `
  -q -p no:cacheprovider
```

**最近结果：** `22 passed in 0.21s`。

**关键断言：**

- 可信 session actor 发起授权目录、不覆盖的上传，控制面直接使用执行器返回的 `sha256:` 指纹创建同一 `Asset` 的 `AssetVersion`。
- 状态仅按 `queued -> parsing -> indexed -> ready` 推进；`ready` 与 active 切换分离；v2 失败或解析为空时，v1 保持 active 且继续可检索。
- 解析、索引失败只回写安全失败枚举，不将路径、正文或异常字符串写入安全审计。
- 已知同路径 Asset、执行器目标冲突、未授权上传或内部索引回调认证失败均不能创建新版本或触发下游副作用。

**失败注入点：** `test_denied_upload_has_no_executor_rag_asset_or_version_side_effect`、`test_executor_target_conflict_maps_to_stable_conflict_without_asset_version`、`test_rag_exception_fails_queued_version_and_returns_safe_correlated_error`、`test_failure_reports_safe_code_and_preserves_old_active`、`test_empty_parsed_chunk_tuple_fails_as_parser_error`。

**代码与证据：**

- `control_plane/app/service.py`
- `control_plane/app/repository.py`
- `service/app/rag/ingestion.py`
- `service/tests/rag/test_ingestion.py`
- `service/tests/rag/test_pipeline_integration.py`
- `D:\AI\Codex\Codex\2026\08\13\project-changes.log`

**残余风险：** 控制面仓储是内存实现，PostgreSQL DDL 尚未在真实实例执行；解析器仅验证隔离 runner 契约，未证明 OS 级无网络、限时、内存或 CPU 强制。

## Gate 2：A 自确认整理与执行前重验

**复验命令：**

```powershell
& $py -B -m pytest `
  'control_plane/tests/test_gate2_plans.py' `
  'control_plane/tests/test_local_file_executor_integration.py' `
  'service/tests/test_api_execution.py' `
  -q -p no:cacheprovider
```

**最近结果：** `21 passed in 0.76s`。

**关键断言：**

- 授权目录内普通移动/重命名生成 `SELF_CONFIRM` 预览；A 自己带正确控制面 `plan_hash` 确认后才执行，B 没有审批待办。
- 控制面 `plan_hash` 与 FastAPI 执行器 `executor_plan_hash` 明确分离；内部适配器在单次调用链内签发并消费一次性令牌，令牌不出现在 Plan、审计、响应或 Dify 上下文。
- 执行前重验 expiry、context、ACL、active AssetVersion 和内容指纹；执行器仍独立重验其自身计划摘要、源快照、身份和路径权限。
- 真正的本地 FastAPI 临时工作区中，文件只在确认后从 `organized/report.txt` 移动到目标路径。

**失败注入点：** `test_mixed_batch_with_a_denied_target_has_zero_downstream_or_plan_side_effects`、`test_confirm_fails_closed_for_wrong_hash_or_non_creator`、`test_confirm_revalidates_expiry_context_acl_and_active_snapshot_before_execution`、`test_executor_final_deny_marks_job_failed_and_cannot_be_approved_around`、`test_execute_plan_rejects_operations_outside_user_permissions`、`test_execute_endpoint_rejects_missing_or_wrong_plan_hash_without_consuming_token`。

**代码与证据：**

- `control_plane/app/service.py`
- `control_plane/app/local_file_executor.py`
- `control_plane/app/plan_hash.py`
- `service/app/main.py`
- `service/app/plans.py`
- `service/app/execution.py`
- `control_plane/tests/test_local_file_executor_integration.py`
- `service/tests/test_api_execution.py`

**残余风险：** 本测试调用临时本机目录中的 FastAPI ASGI 应用，不等同于实际 Windows 服务账号、Dify/BFF 进程或 SMB 共享权限下的执行。

## Gate 3：移动后版本化引用

**复验命令：**

```powershell
& $py -B -m pytest `
  'service/tests/rag/test_versioned_citations.py' `
  'service/tests/rag/test_pipeline_integration.py' `
  'control_plane/tests/test_local_file_executor_integration.py' `
  -q -p no:cacheprovider
```

**最近结果：** `5 passed in 0.15s`。

**关键断言：**

- Asset 的稳定 ID、active version ID、chunk ID 与页码在移动/重命名后保持绑定。
- 成功移动后控制面更新同一 Asset 的 `current_path`，同时保留 version 的 `source_path`；引用为移动后 `HISTORICAL` 路径语义。
- v2 必须在显式 activate 后替换 v1；在 ready 回写期间查询仍只见 v1。

**失败注入点：** `test_failed_v2_keeps_v1_scope_and_v2_out_of_retrieval`、`test_ready_then_explicit_activation_switches_scope_atomically`，以及本地执行集成测试中先断言旧路径未同步的 RED 记录。

**代码与证据：**

- `control_plane/app/repository.py`
- `control_plane/app/service.py`
- `service/app/rag/retrieval.py`
- `service/tests/rag/test_versioned_citations.py`
- `service/tests/rag/test_pipeline_integration.py`
- `control_plane/tests/test_local_file_executor_integration.py`

**残余风险：** 引用使用内存控制面投影与测试索引；尚未接入真实 PostgreSQL、Qdrant 或真实文件系统变更订阅。

## Gate 4：越权检索在召回前失败

**复验命令：**

```powershell
& $py -B -m pytest `
  'service/tests/rag/test_acl_retrieval.py' `
  'service/tests/rag/test_retrieval_fail_closed.py' `
  'service/tests/rag/test_control_plane_authority_adapter.py' `
  -q -p no:cacheprovider
```

**最近结果：** `12 passed in 0.06s`。

**关键断言：**

- RAG `PermissionContext` 必须与可信 BFF actor 的 workspace、actor、groups、session 和 request 精确一致；伪造主体在检索前失败。
- 按每个 Asset 当前路径重算 `QUERY` ACL，显式 DENY 优先；仅把 `(asset_id, active_version_id)` 原子对传给索引。
- 明确拒绝的 chunk 在评分前即缺席，因而不会进入候选、重排、LLM、引用或安全审计。
- 即使坏 SearchIndex、reranker 或 AssetReference 适配器返回越域数据，RAG 仍在下游前 fail-closed。

**失败注入点：** `test_full_deny_short_circuits_before_search_and_returns_safe_metadata`、`test_search_index_scope_violation_fails_closed_before_reranker`、`test_reranker_violation_fails_closed_before_llm_and_citation`、`test_mismatched_asset_reference_fails_closed_before_llm`、`test_untrusted_permission_context_fails_closed_before_search`。

**代码与证据：**

- `service/app/rag/control_plane_adapter.py`
- `service/app/rag/retrieval.py`
- `service/app/rag/index.py`
- `service/tests/rag/test_control_plane_authority_adapter.py`
- `service/tests/rag/test_retrieval_fail_closed.py`
- `docs/contracts/frozen-v1-integration-contract.md`

**残余风险：** 当前 SearchIndex 为可删除可重建的内存副本；没有真实 Qdrant、跨进程 BFF 身份凭证或生产日志管道的实机证明。

## Gate 5：重复演示、幂等与副本重建

**复验命令：**

```powershell
& $py -B -m pytest `
  'control_plane/tests/test_local_file_executor_integration.py' `
  'service/tests/rag/test_in_memory_index.py' `
  'service/tests/test_api_maintenance.py' `
  -q -p no:cacheprovider
```

**最近结果：** `7 passed in 0.25s`。

**关键断言：**

- 同一 `plan_id + plan_hash + idempotency_key` 的重复确认复用同一 `ExecutionJob`，不重复执行。
- 索引副本按 tenant、Asset、AssetVersion 精确 replace/delete/rebuild；相邻 asset、旧版本与其他 tenant 不受影响。
- 清理接口只删除已过期 operation 日志和对应 `.trash` 目录，保留未过期记录。

**失败注入点：** `test_replace_delete_and_rebuild_exact_version_preserves_neighbors`、`test_non_positive_limit_returns_empty_without_scoring`、`test_cleanup_endpoint_removes_only_expired_operation`。

**代码与证据：**

- `control_plane/app/repository.py`
- `service/app/rag/index.py`
- `service/app/operation_logs.py`
- `service/tests/rag/test_in_memory_index.py`
- `service/tests/test_api_maintenance.py`

**残余风险：** 清理与重建验证只覆盖临时目录和内存副本；没有对真实 SMB 目录进行任何删除、重建或重置。

## 完整回归与结论口径

```powershell
& $py -B -m pytest 'service/tests' 'control_plane/tests' -q -p no:cacheprovider
& '.\plugin\.venv\Scripts\python.exe' -B -m pytest 'plugin/tests' -q -p no:cacheprovider
git diff --check
```

本清单只证明当前未提交代码在本地临时目录、内存控制面与可重建 RAG 副本中的 Gate 1–5 行为。Windows/SMB ACL 旁路写、真实服务账号、真实 PostgreSQL、真实 BFF/Dify、Qdrant 与 OS 级 parser sandbox 必须在独立环境实测后才能加入更强的安全结论。
