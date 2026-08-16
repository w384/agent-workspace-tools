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
| 总集成 019ff955 | `D:\AI\Codex\Projects\dify-agent-workspace-tools`（主 checkout） | 不变 | 已归档重开，复述确认通过 |
| 战略 019ff69c | 同主 checkout | 不变 | 收尾后归档 |
| 横纵分析 019ff1b3 | 同主 checkout | 不变 | 收尾后归档 |
| 独立审计 019ffa1b | 同主 checkout | 不变 | 收尾后归档 |
| 控制面 019ff9fd-7351 | `D:\AI\Worktree\0328\...` → 已迁移 | `D:\AI\Codex\Worktree\control-plane`（分支 control-plane/main @ 40bbdf8） | 已迁移，待复述确认 |
| PO+PMO 019fff80 / 019ff1bc | `D:\AI\Worktree\12eb\...`（跑偏，非标准） | 同控制面 | 核验→归档→重建→重开 |
| RAG 019ff9fd-7350 | `D:\AI\Worktree\a904\...` → 已迁移 | `D:\AI\Codex\Worktree\rag`（分支 rag/minimal-loop @ c1250a7） | 已迁移，待重开 |

规则：主 checkout 不动；跑偏 worktree 一律迁到 `D:\AI\Codex\Worktree\` 标准目录（与全局 AGENTS.md 约定一致），不与项目目录混用。

## 3. 各线程交接页

### 3.1 总集成（019ff955 — 已归档重开，复述确认通过）

- 角色：执行总负责 / 技术交付经理，统一集成、推进 v2 Gate、协调 RAG 与控制面、维护集成证据。（权威定义见 `v2-role-map.md`）
- 权威契约：`docs/contracts/frozen-v2-integration-contract.md`（未改动）；配套 `docs/demo/financial-preassessment-demo-runbook.md`（演示 runbook）、`docs/verification/financial-preassessment-v2-demo-checklist.md`（复验清单）。
- 当前切片：v2 演示可复验基线（受控金融样例）——demo runbook + v2 demo checklist，最小文档/展示适配，不改权威字段与契约。
- 验收（2026-08-14 最终证据）：专项 20 passed (0.44s)、control_plane 85 (1.42s)、service 126 (2.23s)、plugin 103 (2.19s，含 2 条既有第三方 warning)；`git diff --check` exit 0（仅既有 LF→CRLF warning）；运行日志 `D:\AI\Codex\Codex\2026\08\14\project-changes.log`；自检日志 `work/demo/financial-preassessment/verification/`（完整性、失败注入、重置回归三份）。
- 版本状态：HEAD = origin/main = 29a8b2c，staged = 0，未提交变更 57 项（含大量既有脏改），未推送、未发布。
- 已知归属（跟踪项）：前端切片（static + /demo 挂载）由控制面在其 0328 worktree 进行中，主项目尚未集成，不属本基线范围——新线程需持续跟踪该归属。
- 边界：DENY 必须在召回/评分/LLM/引用前；缺材料返回 POSSIBLE 或 MISSING_INFO，不推断 NOT_MATCH；match_score 只称资料匹配度。
- 下一步：新线程已重开并完成六项复述（2026-08-14 确认通过），待 Q 下达执行指令；持续跟踪前端切片归属。

- 执行线程（executor，01a00833-d1f3-7130-bc01-31876dc2d7de，worktree D:\AI\Codex\Worktree\ceb0\dify-agent-workspace-tools）：总集成 2026-08-16 拆出的 B 类机械执行子线程，只做执行不做裁决。职责：跑测试、按给定范围/语义拆分/提交信息做 git add/commit（不自行定范围、不 push）、按给定口径合并代码、采集归档集成证据、按给定口径与模板起草 runbook/checklist、执行三步自检并落日志、演示样例机械构建、文档机械同步、只读证据核验。红线：不裁决集成顺序/Gate/范围/契约，不碰控制面/RAG 模块所有权，不做跨线程决策，不 push origin；归属冲突、根因不明、清单外需求一律回总集成裁决。

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

- 角色：v2 Backlog、演示故事、范围边界、验收标准、优先级、对外口径。
- 下一步：核验执行端检查点证据，定稿 v2 演示验收矩阵与故事线（落盘前先向 Q 申请授权）；产出物直接写入本文件对应章节，不另建副本。

### 3.7 独立审计（019ffa1b）——已并入协调者职责

- 角色：架构治理与风险复核 + 多线程治理协调（Q 的协调助手）。
  - 治理协调（可写，边界放宽）：多线程归档重开协调、git 基线管理、交接包维护、阈值监控、执行线程状态跟踪（只跟踪，不派活——派活主体是总集成）。
  - 风险复核（保持只读）：架构治理、越权复核、口径一致性检查。
  - 红线：不实现业务功能、不碰控制面/RAG 模块所有权、不做业务裁决（裁决仍归总集成/Q）。
- 已完成：v2 检查点独立复核并回填结论；发现执行端同步文件与实际产出物文件名不一致（已解决）。
- 复验证据明细（2026-08-14）：
  - 专项 20 passed、control_plane 85、service 126、plugin 103（含 2 条既有第三方 warning）。
  - `git diff --check` exit 0。
- 关键断言核对项：
  - DENY 前置：越权时 RAG 零调用、零计数审计。
  - 引用绑定控制面快照：material/rule 引用错配 fail closed。
  - 失败注入覆盖：规则指纹 / 资产指纹 / 非导入清单源 fail closed；缺材料不推断 NOT_MATCH。
  - import-manifest 仅 asset→material_key 映射。
- 协调者交接详情（git 基线、线程状态、剩余待办、阈值口径、方法论教训）：见 `docs/agent/coordinator-handoff-2026-08-15.md`，本节不重复。
- 下一步：新独立审计线程已开（复述通过），接续协调者待办清单执行。

## 4. 使用规则

- 归档 / 重开 / 迁移的具体操作步骤与验证清单，见 `docs/agent/thread-archive-sop.md`（本文件只存状态，不存流程）。
- 每次归档 / 重开前，由对应线程负责人更新本文件自身章节；不把交接内容贴进多个对话，只引用本文件，避免 N 份副本的 token 开销。
- 新线程开工首轮强制只读：本文件（仅自己章节）+ `docs/contracts/frozen-v2-integration-contract.md`，然后用一段话复述（契约 / 切片 / 验收 / 边界 / 归属 / 工作区路径）等 Q 确认后再执行下一步。
- 发现文件缺失、路径不符或内容矛盾，立即报告，不自行推断。
