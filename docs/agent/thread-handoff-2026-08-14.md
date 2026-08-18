# 线程交接包 2026-08-14

> 用途：多线程归档重开的**唯一共享交接依据**。线程归档后，新线程开工首轮只读本文件（仅自己章节）+ `docs/contracts/frozen-v2-integration-contract.md`，禁止依赖旧对话记忆。
> 角色权威定义见 `docs/agent/v2-role-map.md`，本文件只记录各线程当前切片、交接证据与下一步，不重复定义角色。

## 1. 阈值与归档口径

- rollout > 5MB 或累计 input > 1000 万 tokens → 归档重开；4–5MB 为临界。
- 2026-08-14 实测：4 个超标（总集成 32.97MB、战略 7.48MB、独立审计 7.35MB、控制面 6.55MB），2 个临界（PO+PMO 5.33MB、横纵 5.02MB），RAG 4.25MB 可继续。
- 证据：PO+PMO 累计 input 3360 万 tokens，其中 3053 万（91%）为历史重放；最近一轮单次 input 15.5 万。

## 2. 工作区路径表（2026-08-14）

| 线程 | 当前路径 | 目标路径 | 动作 |
| --- | --- | --- | --- |
| 总集成 019ff955 | `D:\AI\Codex\Projects\agent-workspace-tools`（主 checkout） | 不变 | 已归档重开，复述确认通过 |
| 战略 019ff69c | 同主 checkout | 不变 | 收尾后归档 |
| 横纵分析 019ff1b3 | 同主 checkout | 不变 | 收尾后归档 |
| 独立审计 019ffa1b | 同主 checkout | 不变 | 收尾后归档 |
| 控制面 019ff9fd-7351 | `D:\AI\Worktree\0328\...` → 已迁移 | `D:\AI\Codex\Worktree\control-plane`（分支 control-plane/main @ 40bbdf8） | 已迁移，待复述确认 |
| PO+PMO 019fff80 / 019ff1bc | `D:\AI\Worktree\12eb\...`（跑偏，非标准） | 同控制面 | 核验→归档→重建→重开 |
| RAG 019ff9fd-7350 | `D:\AI\Worktree\a904\...` → 已迁移 | `D:\AI\Codex\Worktree\rag`（分支 rag/minimal-loop @ c1250a7） | 已迁移，待重开 |

规则：主 checkout 不动；跑偏 worktree 一律迁到 `D:\AI\Codex\Worktree\` 标准目录（与全局 AGENTS.md 约定一致），不与项目目录混用。

## 3. 各线程交接页

### 3.1 总集成（01a000d2-044a-7f71-83e1-6066bcd7c6ec — 归档重开中，2026-08-18）

- 角色：执行总负责 / 技术交付经理，统一集成、推进 v2 Gate、协调 RAG 与控制面、维护集成证据。（权威定义见 `v2-role-map.md`）
- 权威契约：`docs/contracts/frozen-v2-integration-contract.md`（未改动）；配套 `docs/demo/financial-preassessment-demo-runbook.md`（演示 runbook）、`docs/verification/financial-preassessment-v2-demo-checklist.md`（复验清单）；验收矩阵与 Backlog 以 3.6 节 PO+PMO 定稿为权威。
- 当前切片：v2 双路径演示（统一 /demo/ 入口：路径 A 资料预评估报告 + 路径 B LLM 知识库问答），P0「接入真实 LLM」已实现并合入 main；默认 deepseek-chat（`RAG_LLM_BASE_URL=https://api.deepseek.com/v1`），可部署期切换本机 Ollama qwen3.5:9b，全部 `RAG_LLM_*` 环境变量注入、零代码改动。
- 验收（Gate V2-5，2026-08-17~18 最终证据）：
  - RAG LLM 测试 20 passed（真实 LLM 输出、DENY 零调用、citations 版本化绑定、LLM 不裁决、凭证不泄、失败 fail-closed）。
  - control_plane 全量 101 passed（提权跑；93 基线 + 前端 v2 4 项 = 101，含全部安全断言）。
  - service 全量 146 passed（改名遗留已修）。
  - `git diff --check` exit 0。
- 版本状态：main 分支 HEAD = 1477b50，本地 4 个新提交未推送（9480e33 docs → 11b9066 feat(rag) bank_label → 80e4e0c feat(control_plane) E2/E4/E5 → d9007f6 feat(control_plane) E3 → 1477b50 docs(runbook)）；未推送、未发布；origin 推送待 Q 授权。
- 已知归属（跟踪项）：前端切片已由控制面 v2 完成并合入（BFF 桥接 + /demo 双 tab + 凭证不泄前端）；RAG 侧 5 个演示文件（demo-bank-rules-v1.json、import-manifest.json、financial-preassessment-bank-rule-matching-demo.md、finance-demo-rag-bridge.md/checkpoint）待 RAG 线程确认后提交，总集成本次不碰；主 checkout 改名遗留脏改（control_plane/work/sdd、docs、scripts、service/app/main.py、test_health.py 等）按归属拆分提交。
- 边界：DENY 必须在召回/评分/LLM/引用前；缺材料返回 POSSIBLE 或 MISSING_INFO，不推断 NOT_MATCH；match_score 只称资料匹配度；LLM 只做问答草稿/解释润色，不做授权裁决/最终评分/贷款授信额度产品推荐；凭证不落前端静态资源、BFF 响应、审计与仓库；不 push origin（等独立审计最终复核）。
- 归档原因（2026-08-18）：累计 input 2309 万 tokens ≥ 1000 万（ARCHIVE 命中），按 thread-archive-restart 技能触发归档重开。
- 剩余待办（2026-08-18 v3 更新）：
  1. E5「选中即自动发起」BFF 受控样例→资产 ID 映射只读端点：P1 延后，未开始（需 PO+PMO 确认是否纳入本期）。
  2. 前端 /demo 人工演示：待 Q 排期。
  - 历史已完成（v2 期间）：集成证据回填 checklist（5507416）、test_windows_auto_start.py 改名遗留（146 passed）、真实 LLM smoke test、待提交项拆分（A=22f61d8/B=3d9dcf8+8324902/C=7f0f153/D=5507416）、work/demo/public-drive-ai-organizing 忽略裁定。
- 在途项（2026-08-18 控制面 v2 派单 07 回报，79e8 工作树未提交；总集成已只读核验并裁决）：
  - ✅ v3 已回填（2026-08-18）：RAG 4c0b bank_label 已合入 main（11b9066）；控制面 E2/E4/E5 已合入 main（80e4e0c）；E3 初始化脚本已合入（d9007f6）；集成回归 control_plane 101 / RAG LLM 20 / service 146 全绿；runbook 步骤 4 补 E5 操作说明（1477b50）。
  - E2（P0 报告区展示）：control_plane/static/{index.html,app.js,style.css} 结构化报告渲染（虚构示例银行名/免责声明/match_score/result_level/缺失材料/引用/规则版本同屏）+ 403 零证据摘要（DENIED/reason/retrieved_count=0/llm_invoked=false/引用无）。
  - E4（P1 绿系 UI）：绿色主色 #16a34a + 简洁现代卡片布局；浏览器只调 BFF、既有安全断言不变。
  - E5（P1 受控文件选择）：input type=file 真实选择 + import-manifest 6 样例白名单校验，任意上传前端拦截并提示底层拒绝（enqueue_version 仍拒绝任意文件）。
  - 测试：新增 test_demo_frontend_v2.py（4 项），control_plane/tests 全量 97 passed（含全部安全断言）；app.js 经 node --check。
  - 总集成裁决（2026-08-18）：
    1. bank_label：已核验 main 无该字段、RAG 4c0b 已实现未提交 → 随下次 RAG 合入 main；前端缺省容错「示例银行」过渡，最终客户演示前必须合入。bank_label 只允许虚构示例银行名，不得为真实银行名。
    2. E5「选中即自动发起」：批准为 P1 后续（BFF 新增受控样例→资产 ID 映射只读端点，选中后自动发起评估），执行延后至 v3 线程；当前「手动填资产 ID」流程由 v3 在 runbook 补充演示期操作说明。
    3. shu26.cfd 参考站自动截图不可行（浏览器 RPC 受信路径校验失败）→ 接受按派单描述实现，逐像素对照不列为验收项；视觉 QA 并入前端 /demo 人工演示（待 Q 排期）。
  - v3 接续：RAG 4c0b 提交 bank_label → 合入 main → 控制面 E2/E4/E5 提交合入 → 集成回归 → BFF 受控样例端点（P1）。
- 主 checkout 归档共享改动 ✅（v3 已提交）：9480e33（.learnings/LEARNINGS.md、.learnings/ERRORS.md、AGENTS.md、thread-archive-sop.md、thread-handoff）；app.js options.body 修复已并入 80e4e0c 前端完整版（3e0735b/d4e7 保留）。
  - .learnings/LEARNINGS.md（+88）、.learnings/ERRORS.md（+45，含 ERR-20260818-001 线程工具运行时实测）、AGENTS.md（补「工具核查铁律」小节）、docs/agent/thread-archive-sop.md（handoff_thread 实测注记）。
  - control_plane/static/app.js：1 行修复（jsonRequest headers 判据 options.json→options.body），79e8 E2 批次未含此修复，归属待定，v3 核验后并入。
- 下一步：v3 剩余待办 = E5「选中即自动发起」端点（P1，待 PO+PMO 定稿）+ 前端 /demo 人工演示（待 Q 排期）；本轮 runbook/合入/回归已闭环。

- 执行线程（executor，01a00833-d1f3-7130-bc01-31876dc2d7de，worktree D:\AI\Codex\Worktree\ceb0\agent-workspace-tools）：总集成 2026-08-16 拆出的 B 类机械执行子线程，只做执行不做裁决。职责：跑测试、按给定范围/语义拆分/提交信息做 git add/commit（不自行定范围、不 push）、按给定口径合并代码、采集归档集成证据、按给定口径与模板起草 runbook/checklist、执行三步自检并落日志、演示样例机械构建、文档机械同步、只读证据核验。红线：不裁决集成顺序/Gate/范围/契约，不碰控制面/RAG 模块所有权，不做跨线程决策，不 push origin；归属冲突、根因不明、清单外需求一律回总集成裁决。

### 3.2 控制面（019ff9fd-7351）

- 角色：可信身份、权限、Asset/AssetVersion、RuleSet/RuleVersion、AssessmentReport、审计权威；客户端 user_id 不作授权依据。
- 权威契约：`frozen-v2-integration-contract.md`。
- 当前切片：v2 演示可复验基线内，仅允许 `service.py` / `demo_rag.py`（BFF 侧端口，实际文件 `control_plane/app/demo_rag.py`）/ `main.py` 及对应测试最小文档/展示适配。
- 前端切片（归档前核验 2026-08-14 实况）：`control_plane/` 全目录未跟踪（git `?? control_plane/`），已落盘未提交——
  `control_plane/static/index.html`、`static/app.js`、`static/style.css`、`app/main.py`（/demo 挂载 StaticFiles(html=True)）、`tests/test_demo_frontend.py`。
  已完成：静态页可访问、两条路径 UI、浏览器只调 BFF、不泄露密钥/本地路径（测试 4 passed）；控制面非 RAG 依赖子集 75 passed；`git diff --check -- control_plane` 干净。
  未完成：完整工作区大回归由执行总负责统一执行；真实浏览器人工演示未跑，属后续集成验收。
- 口头决策（需与新线程对齐）：停止使用 `.task-sync` 改为直接 ID 消息；TDD 验证节奏改为模块级验证但安全断言不减配；前端切片只改 `control_plane/**`，不接 Dify 页面、不触碰 service/rag/公共盘/ACL；静态页不泄露 API Key 或本地路径；/demo 是统一演示入口且 BFF 保持身份/权限/报告/审计权威。
- 验收：DENY 在桥接前返回固定零证据安全摘要；报告引用绑定 active 授权快照与选定 RuleVersion；指纹错配 fail closed。
- 边界：真实 PostgreSQL、Windows/SMB、Qdrant 等 NOT_DONE / NOT_RUN。
- 工作区：已从 `D:\AI\Worktree\0328\...` 迁移至 `D:\AI\Codex\Worktree\control-plane`（分支 `control-plane/main` @ 40bbdf8）。代码保全提交 40bbdf8（39 文件 7846 行，含整个 control_plane/ 模块与前端切片）。
- 下一步：新控制面线程已开（工作目录 control-plane），待完成六项复述确认；确认后恢复待命。

### 3.3 RAG（019ff9fd-7350）

- 角色：知识库 / 检索 Owner：解析、切片、索引、权限前置检索、引用输出、规则库样例、最小评分口径；不维护第二套权威。
- 当前切片：FinanceDemoRagPort 只读受控样例；规则只从 content_fingerprint 绑定 RuleVersion 读取；import-manifest 仅 asset→material_key 映射。
- 验收：越权时解析/索引/评分/LLM 零调用；MATCH=100、POSSIBLE=覆盖率取整、MISSING_INFO=0。
- 边界：不新增索引类型、不接 Qdrant。
- 工作区：已从 `D:\AI\Worktree\a904\...` 迁移至 `D:\AI\Codex\Worktree\rag`（分支 `rag/minimal-loop` @ c1250a7）。
- 代码保全（2026-08-14）：发现 a904 存在大量未提交工作（50 文件 7009 行），其中 `service/app/rag/`（7 个实现文件）与 `service/tests/rag/`（9 个测试）为 RAG 核心产出，已提交 c1250a7 保全并迁移至新 worktree。
- 跟踪项：c1250a7 混入疑似非 RAG 产物——`docs/windows-auto-start.md`、`scripts/*.ps1`（3 个）、`plugin/tools/upload_file.py|yaml`、`service/app/permissions.py`、`docs/dify/`（4 文件）、`docs/superpowers/`（4 文件）。需总集成/控制面核验归属与是否与主项目重复。
- 下一步：归档旧 RAG 线程 → 在 `D:\AI\Codex\Worktree\rag` 开新线程 → 首条消息只读契约+3.3 节并复述六项确认。

### 3.4 横纵分析（019ff1b3）

- 角色：架构与方案顾问，只输出建议不改实现主线。
- 职责扩展（2026-08-16 Q 裁定）：每日 AI 头部公司与工具风向扫描（automationId ai，heartbeat）划归横纵分析，取代原战略专家归属。
- 当前切片：RAGFlow 等外部方案只读研究结论进入 LATER，不接入。
- 关键结论（归档前核验 2026-08-14）：
  - RAGFlow / Haystack / LlamaIndex 当前不接入、不部署、不 fork、不搬代码，只作研究输入。
  - 可借鉴项进 LATER：chunk 证据卡/引用完整性测试、解析状态机、feature flag 约束的只读 sidecar POC、真实向量库/复杂检索。
  - 控制面/BFF 是可信身份、Asset/AssetVersion、ACL、RuleSet/RuleVersion、AssessmentReport、审计的唯一权威。
  - RAG 只读已授权 active AssetVersion；越权必须 DENY 在召回/评分/LLM/引用前。
  - Dify/LLM 只做候选、解释、润色，不做授权、执行凭证、最终评分或金融结论。
  - Qdrant 仅作权限过滤后的可重建检索副本，不是权限或资产权威。
  - 不扩成 DAM/MAM、贷款审批、授信、额度测算或金融产品销售。
  - 金融监管〔2026〕8号：资料预评估不是信贷审批；个人隐私数据不得用于模型训练；外部模型须准入。
  - 最近定时扫描结论：无需调整架构；第三方 RAG ACL 不可信；Dify 沙箱不是安全边界。
- 风险提示：中台最后一轮只读复核曾因 token 限额中断，未形成独立复核结论——该状态不得被表述为"独立复核通过"。
- 下一步：归档重开；新线程继续按需判断切片盲区。

### 3.5 战略（019ff69c）

- 角色：市场 / 合规 / 外部趋势顾问，关注金融信息服务边界。
- 当前切片：对外窄说"资料预评估与银行规则匹配 DEMO"；内部宽做企业资料资产化。
- 合规与对外口径结论（归档前核验 2026-08-14）：
  - 金融监管〔2026〕8号：资料预评估不属于信贷审批、个人数据不入模。
  - 第三方 RAG ACL 不可信，不能作为企业权限权威。
  - Dify 沙箱不是安全边界。
  - 对外定位：不是"AI 平台"，而是"企业 AI 落地样板间"。
  - 对外口径：公共盘 AI 整理 DEMO（已从广告/多媒体收窄为通用）。
  - 金融资料匹配只是其中一个板块，不是唯一方向。
- 归属说明：AGENTS.md、README.md、.learnings/ 等共享文件的最终口径裁决权不在本线程，应由总集成/PO+PMO 定稿。
- 下一步：归档重开；新线程继续按需补风险提示或对外话术。

### 3.6 PO+PMO（019fff80 / 019ff1bc）

**角色**：v2 Backlog、演示故事、范围边界、验收标准、优先级、对外口径。
**边界**：写规划文档前先取得 Q 明确授权；`financial-preassessment-demo-runbook.md` / `financial-preassessment-v2-demo-checklist.md` 归执行总负责维护，本线程不直接修订。

**定稿状态（2026-08-16）**：v2 演示故事线与验收矩阵已定稿（以本节为权威，经 Q 审阅批准）。执行端 runbook/checklist 仍为旧「资料预评估报告」API 级故事线（主 checkout 未跟踪），需执行总负责按本节对齐。「接入真实 LLM」为新增未落地项，实施归 RAG 后台（AnswerGenerator/ExplanationPort 协议与检索流）+ 控制面（BFF 桥接）统筹，执行总负责推进；本线程只定验收口径，不代实现。

**故事线（双路径并存）**

统一演示入口 `/demo/`（最小自研前端：`control_plane/static/**` + `app/main.py` 的 `/demo` 挂载），登录后同一界面两条路径：

- 路径 A「资料预评估报告」：受控身份登录 → 创建演示规则版本（`/api/rule-sets`，`source_type=demo_fixture`，绑定 `content_fingerprint`）→ 选择已授权受控资产发起评估（`/api/assessments`）→ 前端展示报告（`match_score` 资料匹配度、`result_level`、可匹配/可能匹配示例银行、缺失材料、material/rule 引用、免责声明）。
- 路径 B「LLM 知识库问答」：同一登录态切问答 tab → 输入问题 + 资产 ID（`/api/retrieval/query`）→ 权限前置召回授权证据 → 真实 LLM 依据授权证据生成回答草稿/润色 → 返回 answer + 版本化 citations（`asset_id/asset_version_id/chunk_id/page/paragraph/path_kind`）。DENY/REFUSED 时 LLM 零调用。
- 负向演示（两路径共用）：越权资产 → 403 `DENIED`，`retrieved_count=0`、`llm_invoked=false`、`citations=[]`，解析/索引/评分/LLM 零触发。

**验收矩阵（重写）**

| Gate | 故事线节点 | 最小验收证据 | 前端/接口可见 | 证据来源 |
| --- | --- | --- | --- | --- |
| 前端基线（跨 Gate） | 统一入口 `/demo/` + 双 tab + 登录 | 首页含「资料预评估」「知识库问答」「免责声明」；浏览器只调 BFF；不泄露 api_key/密钥/本地路径 | `/demo/`、`/demo/app.js`、`/demo/style.css` | `control_plane/tests/test_demo_frontend.py` |
| V2-1 场景样例 | 双路径共用的受控样例/规则/免责声明 | 样例与规则均为脱敏/虚构，带 `demo_fixture` + `content_fingerprint` + `version_label`；免责声明无贷款/授信/额度测算字样 | 规则版本标签、免责声明文案 | `test_finance_demo_rag_bridge.py` + runbook 步骤1 |
| V2-2 资产版本 | 路径 A 前置 | 选择/上传后生成 `Asset/AssetVersion`，绑定 SHA-256；失败版本不替换 active | 评估输入 asset_ids | `test_finance_demo_rag_bridge.py` + checklist 关键断言 |
| V2-3 解析索引 | 路径 A/B 共用 | PDF/DOCX 被解析、切片、索引，带版本化引用 | 问答 citations | `test_demo_rag_pipeline.py`（PDF+docx）+ `test_finance_demo_rag_bridge.py`（`parsed_mime_types`/`indexed_chunk_count`） |
| V2-4 规则匹配 | 路径 A | 确定性规则输出 `match_score`（整数）、`result_level`、`missing_materials`、规则版本；MATCH=100、POSSIBLE=覆盖率取整、缺材料不推断 NOT_MATCH | 评估报告 | `test_finance_demo_rag_bridge.py` + `service/app/rag/finance_matching.py` |
| V2-5 可解释问答 | 路径 B | 真实 LLM 依据授权证据生成回答（草稿/润色）；回答带版本化引用（asset_id/asset_version_id/chunk_id/page/paragraph）；DENY/REFUSED 时 `llm_invoked=false` 且 LLM 零调用；LLM 不裁决 | 问答 tab | `test_retrieval_fail_closed.py` + `test_versioned_citations.py`（fail-closed/引用）+ 待执行端新增「真实 LLM 调用」测试 |
| V2-6 权限负向 | 两路径共用 | 无权用户在召回前 `DENY`，`retrieved_count=0`、`llm_invoked=false`、`citations=[]`，评分/回答零调用 | 403 固定零证据摘要 | `test_finance_demo_rag_bridge.py` + `test_retrieval_fail_closed.py` |
| V2-7 审计 | 两路径共用 | 记录资产版本、规则版本、报告、查询主体、时间、免责声明版本；审计不含未授权路径/正文/chunk | 后台（前端不可见） | `test_finance_demo_rag_bridge.py`（`assessment_report_created` 字段）+ `test_retrieval_fail_closed.py`（安全元数据） |

**Backlog（P0/P1/LATER）**

| ID | 条目 | 优先级 | 判定理由 |
| --- | --- | --- | --- |
| P0-1 | 前端统一入口 `/demo/` + 双 tab + 登录 | P0 | 故事线「最小自研前端」承载，双路径并存已落地 |
| P0-2 | 脱敏样例 + demo_fixture 规则 + 免责声明 + 来源标签 | P0 | Gate V2-1，防误读为真实金融数据 |
| P0-3 | Asset/AssetVersion 版本化 + 失败不替换 active | P0 | Gate V2-2，资产权威基础 |
| P0-4 | PDF/DOCX 解析/切片/索引 + 版本化引用 | P0 | Gate V2-3 |
| P0-5 | 确定性规则匹配（评分/等级/缺失材料/规则版本） | P0 | Gate V2-4，LLM 不裁决 |
| P0-6 | 可解释问答：真实 LLM 生成回答草稿/润色 + 版本化引用；DENY 前 LLM 零调用；LLM 不裁决 | P0 | Gate V2-5，故事线「LLM 知识库问答」真实承载 |
| P0-7 | 权限负向（召回前 DENY 零召回） | P0 | Gate V2-6，安全负向 |
| P0-8 | 审计留痕（版本/报告/主体/时间/免责声明） | P0 | Gate V2-7 |
| P0-9 | 前端安全（不泄密钥/路径，只调 BFF，含 LLM 凭证不泄前端） | P0 | 跨 Gate 前端基线 |
| P1-1 | 真实文件上传→自动解析/索引闭环 | P1 | 当前演示用受控样例选择，真实上传 NOT_DONE，不阻塞演示 |
| P1-2 | Dify 页面实机接入 + Workflow 追踪 | P1 | 当前 NOT_RUN；故事线是自研前端，不依赖 Dify 页面 |
| P1-3 | LLM 失败/超时降级策略 + 生产凭证/成本/多租户隔离 | P1 | 「接入真实 LLM」的生产化层面，演示期可用受控 demo 凭证 |
| P1-4 | 示例银行类型/可匹配银行名展示 | P1 | 当前规则按 material_key 匹配，不实际列银行名；对外不夸大为真实银行推荐 |
| LATER-1 | Qdrant/真实 PostgreSQL/OS parser sandbox | LATER | 契约明确不得宣称已完成 |
| LATER-2 | Windows/SMB 独立账号 + UNC + ACL 旁路写实测 | LATER | 契约保留风险，需单独实测 |
| LATER-3 | 真实银行规则/真实金融资料/贷款授信额度产品推荐 | LATER | 契约禁止宣称，需来源授权 + 合规 |

**P0「接入真实 LLM」验收口径与归属**

归属：实施归 RAG 后台（`AnswerGenerator` 问答生成、`ExplanationPort` 解释润色、检索流内 LLM 调用点，位于 `service/app/rag/`），控制面负责 BFF 桥接注入真实实现（`control_plane/app/demo_rag.py`、`finance_demo_rag.py`），执行总负责统筹验收与集成；PO+PMO 只定验收口径、不代实现。演示期使用受控 demo LLM 凭证（脱敏），不落前端、不入库明文。

验收口径（P0-6，全部满足才通过）：

- 真实调用：`/api/retrieval/query` 的 ANSWERED 回答必须由真实 LLM 依据授权证据生成（草稿/润色），不得退化为确定性 chunk 摘录占位。
- 授权前置：DENY/REFUSED 时 `llm_invoked=false`，LLM 零调用；DENY 必须发生在召回、评分、重排、LLM 上下文与引用之前。
- 引用绑定：citations 仍绑定授权证据（asset_id/asset_version_id/chunk_id/page/paragraph）；LLM 不新增、不越出授权范围引用。
- 不裁决：LLM 只做问答草稿/解释润色，不产出授权结论、最终评分权威、贷款/授信/额度/产品推荐。
- 凭证安全：LLM 凭证（api_key/base_url/model）不出现于前端静态资源、BFF 响应与审计；延续前端「不泄 api_key/密钥/本地路径」断言。
- 失败可控：LLM 失败/超时须有明确降级（fail-closed 或回退确定性摘录），并在响应如实标记，不得伪装为真实 LLM 成功；生产化降级/成本/多租户隔离归 P1-3。

验收证据（待执行端新增）：新增「真实 LLM 调用」测试（ANSWERED 时 LLM 被调用、DENY 时 LLM 零调用、引用绑定授权证据、凭证不泄前端）；`test_demo_rag_query.py` 对 answer 的精确相等断言需随真实 LLM 输出同步调整，避免把确定性摘录当验收。

**范围边界**

- 最小自研前端 = `control_plane/static/**` + `/demo` 挂载；不接 Dify 页面，不碰 `service/rag`、公共盘、ACL（与交接包 3.2 控制面一致）。
- 对外窄说「资料预评估与银行规则匹配 DEMO」；对内宽做「企业资料资产化 + 场景知识库 + 权限检索 + 可解释业务问答」。
- 金融资料匹配是可替换板块，不写死为贷款系统/金融决策平台。
- `match_score` 只称资料匹配度，不称信用/授信/审批评分；缺材料返回 POSSIBLE 或 MISSING_INFO，不推断 NOT_MATCH。
- 真实 LLM 仅用于「问答草稿生成 / 解释文本润色」；不用于授权裁决、执行凭证、最终评分权威、贷款/授信/额度/产品推荐；LLM 调用必须发生在授权裁决之后，仅接收已授权证据。演示期使用受控 LLM 凭证（脱敏），不得在前端泄露。

**对外口径**

标准话术：「用户上传或选择模拟资料后，系统把资料版本化、结构化，再根据银行规则库样例做资料匹配度预评估，输出可匹配的示例银行、缺失材料和引用依据。结果仅供信息参考，不参与贷款申请、审批、授信、额度测算或金融产品销售。」

禁用话术：贷款审批 / 授信 / 额度测算 / 金融产品销售 / 信用评分 / 授信评分 / 已覆盖所有行业 / 金融智能决策平台已完成 / 真实公共盘旁路写已阻断 / 生产级 Qdrant·PostgreSQL·OS parser sandbox 已完成。

LLM 口径：不宣称 LLM 做最终裁决或评分；「LLM 知识库问答」＝权限前置检索 + 真实 LLM 依据授权证据生成回答，LLM 不决定谁有权看、不算分。

**引用证据文件**

- 执行端（归执行总负责，未跟踪）：`docs/demo/financial-preassessment-demo-runbook.md`、`docs/verification/financial-preassessment-v2-demo-checklist.md`。
- 前端切片：`control_plane/static/index.html`、`control_plane/static/app.js`、`control_plane/app/main.py`、`control_plane/tests/test_demo_frontend.py`。
- RAG/BFF 桥：`service/app/rag/retrieval.py`、`service/app/rag/finance_matching.py`、`service/app/rag/contracts.py`、`control_plane/app/demo_rag.py`、`control_plane/app/finance_demo_rag.py`、`control_plane/tests/test_demo_rag_query.py`、`control_plane/tests/test_finance_demo_rag_bridge.py`、`service/tests/rag/test_*.py`。

**待执行端跟进（本线程不代改）**

- runbook/checklist 需从旧「资料预评估报告」API 级故事线，对齐到「统一前端入口 + 双路径」故事线与本验收矩阵。
- 新增「接入真实 LLM」：实现 AnswerGenerator（问答）/ ExplanationPort（解释润色）的真实 LLM 实现，并新增对应测试；保持 DENY-before-LLM、版本化引用、凭证不泄前端。
- 两份文档目前在主 checkout 为未跟踪文件，未提交、未推送。

### 3.7 独立审计（019ffa1b）——已并入协调者职责（2026-08-18 归档重开中）

- 角色：架构治理与风险复核 + 多线程治理协调（Q 的协调助手）。
  - 治理协调（可写，边界放宽）：多线程归档重开协调、git 基线管理、交接包维护、阈值监控、执行线程状态跟踪（只跟踪，不派活——派活主体是总集成）。
  - 风险复核（保持只读）：架构治理、越权复核、口径一致性检查。
  - 红线：不实现业务功能、不碰控制面/RAG 模块所有权、不做业务裁决（裁决仍归总集成/Q）。
- 复验证据明细（2026-08-14 记录；重新验证须重跑对应测试取证，不查历史底稿）：
  - 专项 20 passed、control_plane 85、service 126、plugin 103（含 2 条既有第三方 warning）；`git diff --check` exit 0。
- 关键断言核对项（四项）：
  - DENY 前置：越权时 RAG 零调用、零计数审计。
  - 引用绑定控制面快照：material/rule 引用错配 fail closed。
  - 失败注入覆盖：规则指纹 / 资产指纹 / 非导入清单源 fail closed；缺材料不推断 NOT_MATCH。
  - import-manifest 仅 asset→material_key 映射。
- 已完成（2026-08-17，总集成委托三步合入 main，语义拆分提交、未 push、未提交 work fixture）：
  - 4720891 feat(rag) → eaaf8ec feat(control_plane) → 51cdc75 docs（对齐 /demo/ 双路径故事线）；main HEAD = 51cdc75。
- 已完成（2026-08-17~18）：thread-archive-restart skill 开源化为独立仓库并上线：
  - 位置 `C:\Users\tianh\.codex\skills\thread-archive-restart`，本地 aac8e97 + tag v0.1.0，已推送 https://github.com/w384/thread-archive-restart（独立于主项目）。
  - 内容：测量脚本重构（--check 退出码 / 可调阈值 / ROLLOUT 信号）、9 项单测 + 合成 fixture、零依赖 CI、双语 README/LICENSE/CHANGELOG/CONTRIBUTING/SECURITY/docs。
- 归档原因（2026-08-18）：本线程累计 input 2950 万 tokens ≥ 1000 万（ARCHIVE 命中），按 thread-archive-restart 技能触发归档重开。
- 下一步：新协调者线程首条消息 = 只读 coordinator-handoff-2026-08-15.md + 第 1 节 4 份权威文件，复述确认后接续待办；「已归档重开」状态标记由新线程完成。
## 4. 使用规则

- 归档 / 重开 / 迁移的具体操作步骤与验证清单，见 `docs/agent/thread-archive-sop.md`（本文件只存状态，不存流程）。
- 每次归档 / 重开前，由对应线程负责人更新本文件自身章节；不把交接内容贴进多个对话，只引用本文件，避免 N 份副本的 token 开销。
- 新线程开工首轮强制只读：本文件（仅自己章节）+ `docs/contracts/frozen-v2-integration-contract.md`，然后用一段话复述（契约 / 切片 / 验收 / 边界 / 归属 / 工作区路径）等 Q 确认后再执行下一步。
- 发现文件缺失、路径不符或内容矛盾，立即报告，不自行推断。
