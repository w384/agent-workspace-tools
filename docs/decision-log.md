# 决策记录（Decision Log）

> 仅记录用户正式确认的长期项目决策。格式：决策标题 → 背景 → 决策内容 → 证据 → 边界 → 影响。最新在上。

## 2026-08-23 · 方向修正：站位企业 Agent 控制平面（Control Plane）

### 决策
本项目从「企业资料预评估与知识库问答演示系统」对外叙事，**升级为「企业 Agent 安全运行样板间」（Agent Control Plane 能力样板）**，主动站到市场三层结构的第二层——Agent 基础设施层。

### 背景
- Q 提供两层行业资讯（2026-08-23）：
  1. 云上 Agent 场景已被企业微信 / 飞书 / WorkBuddy 等覆盖，真正未解决的是**内网、隔离网、涉密环境**中如何安全运行、授权、审计和管理大量 Agent。
  2. 市场呈三层：模型公司 / Agent 基础设施（Runtime + MCP + Security + Memory）/ 行业 Agent。行业 Agent 将快速红海化，而「管理 1000 个企业 Agent 如何安全运行」尚无成熟答案——护城河在 Agent 的操作系统能力。
- 战略专家 v2 与 PO 已下线，方向修正由总集成（本线程）直接分析与决策，Q 已确认「方向判断成立」。

### 决策内容
1. **站位第二层：企业 Agent Control Plane**。核心关键词：Runtime + MCP + Skill + Context + Policy + Audit。
2. **叙事修正**：对外口径从「金融资料匹配 DEMO」升级为「企业 Agent 安全运行样板间」，金融资料匹配降为第一套可替换场景板块；「对外窄说，内部宽做」原则照旧。
3. **能力补课**：补齐最小 MCP 暴露层（把 permission / assess / query / audit 包成 MCP 工具），中等工程，可后置，不与当前待办冲突。
4. **待办不变**：等待免费云服务器部署后继续；不 push 无关内容，仓库只保留演示 demo 相关文件。

### 证据（现状对照，均有实测）
| 维度 | 现状 | 证据 |
| --- | --- | --- |
| Policy | 已实现 | PermissionGrant / ACL，DENY 前置：bob 无授权在召回前被拒（retrieved_count=0、llm_invoked=false） |
| Audit | 已实现 | 审计事件：资料 / 规则版本、查询主体、时间、免责声明版本 |
| Context | 已实现 | Asset / AssetVersion、哈希 / 状态、版本化引用、chunk/page 级引用 |
| Runtime | 雏形 | 本地 Ollama + 联网 DeepSeek 切换、BFF 为执行边界、单进程离线可跑 |
| Skill | 雏形 | 受控样例 + 规则库样例 + 可替换场景板块 |
| MCP | 唯一真实缺口 | 无对外 MCP server 暴露层 |

回归基线：控制面 112 passed、service/tests/rag 72 passed、RAG LLM 20 passed、git diff --check 通过（2026-08-23 实测）。

### 三个真实能力缺口（对照第二层）
1. **MCP 暴露层**：把 permission / assess / query / audit 能力包成 MCP 工具暴露。
2. **多 Agent / 多主体**：Agent 身份 + 授权粒度（当前仅为用户级 alice / bob）。
3. **隔离部署的可信启动**：密钥注入、离线模型准入、可离线校验完整性。

### 边界（照旧收紧，不扩）
- 只做样板间 / 控制面能力展示，**不宣称**生产级 AgentOS、等保 / 涉密资质、生产级知识库。
- 涉密与个人信息保护是硬边界；不参与、不代表贷款 / 授信 / 额度测算结论。
- 主线不写成「行业 Agent」（红海），金融板块只是一套可替换场景。
- 不推翻 frozen-v2-integration-contract 的架构边界，只升级对外叙事。

### 影响
- 对外沟通 / README / 演示话术口径随之调整（本次同步更新演示纲要一句话定位与 README 定位行）。
- 后续工程优先补齐 MCP 最小暴露层（是否立即开工由 Q 定夺）。
