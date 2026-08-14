# 公共盘 AI 整理 DEMO：可复验演示基线

> 状态：演示验收清单。当前只列已实现的本地组合测试与后续演示所需的真实接线门；不把测试替代为页面演示证据。

## 验收层级

| 层级 | 当前状态 | 可以证明 | 不能证明 |
| --- | --- | --- | --- |
| Gate 1–5 本地组合验收 | 已通过 | 计划、确认、执行前重验、版本化引用、ACL 前置检索与幂等的测试行为 | 真实 Dify/BFF、真实 PDF/DOCX 解析链路、Windows/SMB 旁路阻断 |
| 样例演示验收 | 未开始 | A/B 在同一演示工作区实际跑通脚本 | 生产或企业实机安全闭环 |
| Windows/SMB 环境边界验收 | NOT_RUN | 专用目录的直接 SMB 写是否被普通成员拒绝 | 整个企业公共盘安全性 |

## 当前可复用的代码与测试资产

| 演示节点 | 代码 | 测试证据 | 当前已证明的断言 |
| --- | --- | --- | --- |
| A 上传、版本状态 | `control_plane/app/service.py`、`service/app/rag/ingestion.py` | `control_plane/tests/test_gate1_upload.py`、`service/tests/rag/test_ingestion.py` | 上传授权、`queued -> parsing -> indexed -> ready`、失败 v2 保留旧 active |
| A 自确认移动 | `control_plane/app/local_file_executor.py`、`control_plane/app/service.py`、`service/app/main.py` | `control_plane/tests/test_local_file_executor_integration.py`、`service/tests/test_api_execution.py` | A SELF_CONFIRM、真实临时目录移动、执行前 ACL/指纹/哈希重验、令牌不泄漏 |
| 移动后版本化引用 | `service/app/rag/retrieval.py`、`service/app/rag/control_plane_adapter.py` | `service/tests/rag/test_versioned_citations.py`、`service/tests/rag/test_pipeline_integration.py` | active version、chunk、页码稳定；current_path 与 version_path 分离 |
| A 越权检索失败 | `service/app/rag/control_plane_adapter.py`、`service/app/rag/retrieval.py`、`service/app/rag/index.py` | `service/tests/rag/test_control_plane_authority_adapter.py`、`service/tests/rag/test_retrieval_fail_closed.py` | DENY 在评分前发生；无权内容不进入重排、LLM、引用或安全审计 |
| 索引副本重建 | `service/app/rag/index.py` | `service/tests/rag/test_in_memory_index.py` | tenant/Asset/AssetVersion 精确 replace/delete/rebuild |

## 必须新增的演示实现与证据

下列项不是新增架构，而是将现有冻结 v1 端口接成可演示的最小链路；未完成前不得声称“真实 RAG 查询已展示”。

| 项目 | 最小实现/准备 | 必需证据 |
| --- | --- | --- |
| PDF/DOCX 真实 parser runner | 实现 `ParserSandboxRunner` 的演示专用 runner；只读取演示专用文件，遵守 PDF/DOCX、2MiB、无网络、只读源的固定策略 | 每个入索引文件的 parser 版本、chunk 数、失败安全码；需明确 OS 级隔离若未实现 |
| 演示索引写入 | 以 `InMemorySearchIndex.replace_version` 写入已解析的 active AssetVersion；不新增第二权威 | AssetVersion、chunk ID、页码/段落、index version 的受控输出 |
| 控制面状态回写/显式 active | 将 `IngestionService` 的状态与控制面回调接线，保持 ready 与 activate 分离 | `queued/parsing/indexed/ready` 记录；v2 failed 时 v1 仍可查询 |
| BFF/控制面查询入口 | 建立仅消费可信 session 的内部 RAG 查询适配；禁止浏览器/Dify 原始 `user_id` 直传 | A 有权命中、A 越权 DENY、B 查询 A 与 B 内容均由显式 grant 决定 |
| 页面/命令演示证据 | 保存脱敏截图或日志：状态、影响预览、实际路径前后、AuditEvent/ExecutionJob、引用、DENY | 不显示 API Key、密码或一次性令牌；实际文件路径须为演示专用目录 |

## 样例 ACL 最小矩阵

| 资源 | A：项目执行 | B：项目负责人 | 用途 |
| --- | --- | --- | --- |
| 项目普通目录与交付文件 | ALLOW upload/query/move_rename | ALLOW upload/query/move_rename | A 黄金路径和 B 查询 A 内容 |
| `版权授权证明/内部法务评审意见.docx` | DENY query | ALLOW query | A 越权检索失败、B 有权查询 |
| 高风险 trash/restore | 不在本轮演示 | 不在本轮演示；B 只具备后续 approval evidence 资格 | 防止把审批混入 A 的低风险路径 |

## 运行命令与结果记录

本地组合回归：

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
$py = '.\service\.venv\Scripts\python.exe'
& $py -B -m pytest 'service/tests' 'control_plane/tests' -q -p no:cacheprovider
& '.\plugin\.venv\Scripts\python.exe' -B -m pytest 'plugin/tests' -q -p no:cacheprovider
git diff --check
```

最近已记录结果为：`service/tests + control_plane/tests` 180 passed；`plugin/tests` 103 passed，含 2 个既有第三方警告；详情见 `docs/verification/gate-1-5-local-combination-checklist.md` 和 `D:\AI\Codex\Codex\2026\08\13\project-changes.log`。

真实演示完成后，补充以下证据而不是复用上述测试结果：

1. A/B 登录与长期授权矩阵截图或脱敏审计记录。
2. A 上传后 PDF/DOCX 的 AssetVersion、状态和 chunk 证据。
3. A 的 `operations_json`、影响预览、SELF_CONFIRM 和实际路径前后对照。
4. A 有权 RAG 命中及版本化引用。
5. A 越权 RAG `DENY/retrieved_count=0/llm_invoked=false/citations=[]`。
6. B 上传、查询 A 内容和查询 B 敏感内容的显式 grant 证据。
7. Windows/SMB 专用目录环境实测的独立 PASS/FAIL/NOT_RUN 结果。

## 未提交状态与残余风险

- 当前工作树有既有修改与未跟踪目录，未暂存、未提交、未推送、未发布；演示基线不是发布候选。
- RAG 当前是最小 in-memory 可重建副本；未接 Qdrant、真实 PostgreSQL 或生产 BFF。
- 当前 parser worker 只实施了策略与端口，未实现真实 PDF/DOCX runner，也未取得 OS 级隔离证明。
- Windows/SMB 服务账号、共享 UNC、普通成员四项直写拒绝和 FastAPI 正向受控写仍为 NOT_RUN；因此不能宣称旁路写阻断。
