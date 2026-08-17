# 全局记忆迁移（2026-08-17）

本文件承接自全局 `C:\Users\tianh\.codex\memories\MEMORY.md` 中与本项目相关的内容，
迁移到项目内以便按需读取。历史执行证据（rollout 摘要、thread_id、测试数量）仍保留在
全局 `memories\rollout_summaries\` 与 `memories\raw_memories.md`，不再作为全局常驻记忆。

> 目录名提示：本项目目录已由 `dify-agent-workspace-tools` 更名为 `agent-workspace-tools`。

## 架构与权威边界（复用知识）

- Control Plane / BFF 拥有受信身份、ACL、`Asset` / `AssetVersion`、审批与审计；
  Windows FastAPI / service 是唯一真实文件写边界；RAG 只读；Dify / plugin 负责意图、
  候选计划与交互编排。
- 策略顺序 `DENY > APPROVAL_REQUIRED > SELF_CONFIRM > DIRECT`，fail-closed；执行前重新
  校验 session、plan_hash、ACL、资产版本与有效期；RAG 在检索 / 重排 / LLM / 引用生成前
  必须 fail-closed。
- RAG 查询权威 = 受信 session + 服务端显式 `asset_id` + 活跃 `AssetVersion`（而非浏览器 /
  Dify 裸 `user_id` 或模糊相似度）；评分 / LLM 前应用 `PermissionGrant` 与资产范围索引；
  拒绝返回 `DENIED`、`retrieved_count=0`、`llm_invoked=false`、`citations=[]`。
- 控制面 `plan_hash` 与 FastAPI executor hash 分离；一次性令牌仅在内部适配器链中签发 /
  消费，不得出现在计划、审计、响应或 Dify 上下文中。
- 目标 Dify 流程：`list_files → LLM → create_plan → Human Input →
  execute_confirmed_plan(plan_id, plan_hash)`；LLM 只产出严格候选 `operations_json`，
  授权 / 令牌 / 哈希 / ACL 由服务端与控制面决定。
- Docker Dify 经 `http://host.docker.internal:8890` 访问 Windows 服务（非 `localhost`）；
  API Key 只放 provider credentials，不写入提示词 / 变量 / 日志 / 输出。

## 项目相关用户偏好

- 外部 Dify / Windows / SMB 操作：先给「一步操作 + 预期结果」，由用户手动执行；用户明确
  授权项目本地连续工作后，减少打断并合并汇报；外部系统仍需单独授权。
- 演示仅使用项目内虚构样例，不触碰真实云盘或 Windows/SMB ACL；区分「本地组合行为已验证」
  与「真实环境验收」。
- 声明拥有者 / 权限 / 执行安全，必须以工具或测试证据为据（用户曾问「在哪看出来被识别成
  拥有者了」）。