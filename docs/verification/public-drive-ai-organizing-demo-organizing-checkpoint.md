# 公共盘 AI 整理 DEMO：第二制作检查点

状态：项目内受控样例的本地组合验证。它证明“整理计划到版本化引用”的最小闭环，不代表真实公共盘、Windows/SMB 或生产环境验收。

## 闭环范围

使用 [固定候选计划夹具](../../work/demo/public-drive-ai-organizing/fixtures/a-low-risk-organizing-plan.json) 对两份虚构样例执行低风险移动：

- `输出稿/星河食品春季新品主视觉KV.pdf` 到 `验收交付/输出稿/星河食品有限公司-2026春季新品-主视觉KV-v1.pdf`
- `输出稿/星河食品春季新品视频脚本.docx` 到 `验收交付/输出稿/星河食品有限公司-2026春季新品-视频脚本-v1.docx`

夹具的 `source_type=fixed-demo-fixture-not-llm-runtime`，明确不是 Dify 或 LLM 的实机输出。它只用于在真实 LLM 接线尚未纳入本检查点时，稳定复验“候选计划和服务端执行边界”。

## 复验命令

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
& '.\service\.venv\Scripts\python.exe' -B -m pytest `
  'control_plane\tests\test_demo_organizing_checkpoint.py' -q -p no:cacheprovider
```

本次结果：`2 passed in 0.39s`。

## 已证明的断言

1. A 的两项候选均在已授权的 `输出稿` 与 `验收交付` 范围内，控制面裁决为 `SELF_CONFIRM`；计划处于 `pending_confirmation` 时不写文件。
2. A 使用正确 `plan_hash` 确认后，经 `LocalWorkspaceFileExecutorAdapter` 调用实际本地 FastAPI 计划、内部一次性令牌和执行路径；`ExecutionJob.state=completed`，审计包含 `plan_created` 与 `execution_completed`。
3. 临时受控工作区的两个源文件消失，两个目标文件存在，移动后 SHA-256 与执行前一致。
4. 真实 PDF 在移动前完成页级切片并写入内存索引；移动后，A 通过 BFF `POST /api/retrieval/query` 指定同一 Asset 查询，引用仍绑定原 `asset_version_id`，但 `current_path` 为新路径、`version_path` 保留旧路径。
5. 备用负向分支在确认后修改一个源文件：执行器拒绝执行，两个目标路径均不存在，计划状态为 `failed`，审计包含 `execution_failed`。该分支不替代 A 查询 B 敏感内容的检索前 DENY。

## 演示证据点

实际演示时应依次展示：固定候选 `operations_json` 的来源标签、影响预览、A 的确认、执行前后目录窗口、ExecutionJob/AuditEvent、以及移动后针对已选择 Asset 的版本化引用。A 查询敏感法务 Asset 的 `DENIED/retrieved_count=0/llm_invoked=false/citations=[]` 继续使用 [RAG 查询运行检查点](public-drive-ai-organizing-demo-runtime-checkpoint.md) 的用例和证据。

## 仍是受控样例或未验证项

- 测试只在临时受控工作区复制项目内虚构文件；没有写入真实公共盘，也没有 Windows/SMB ACL 变更。
- `DemoRagPort` 只查询已准备的项目内样例。B 真实上传后经 FastAPI 自动解析、切片、索引的接线尚未完成。
- 固定计划夹具不是 Dify/LLM 的实机输出；Dify 仍只应生成候选 JSON，不能执行文件写入。
- OS 级 parser sandbox、真实 Qdrant、真实 PostgreSQL 仍未接入；Windows/SMB 独立服务账号、普通成员账号、UNC 与 ACL 实测仍为 NOT_RUN。
