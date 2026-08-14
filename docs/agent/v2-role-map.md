# v2 对话角色映射

状态：当前协作角色记录。用于各对话下一轮快速读取，不替代 `docs/contracts/frozen-v2-integration-contract.md`。

## 权威口径

- 当前权威契约：`docs/contracts/frozen-v2-integration-contract.md`
- 演示纲要：`docs/demo/enterprise-asset-knowledge-demo-guideline.md`
- v1 仅保留为历史 Gate 1-5 本地组合验收基线。
- 对外窄说：资料预评估与银行规则匹配 DEMO。
- 内部宽做：企业资料资产化 + 场景知识库 + 权限检索 + 可解释业务问答。
- 金融资料匹配是第一套可替换业务板块，不把项目改成贷款系统。

## 角色映射

| 对话/任务 | 角色定位 | 主要职责 | 边界 |
| --- | --- | --- | --- |
| Q | Sponsor / 最终裁决人 | 定战略方向、验收口径、范围取舍、关键风险接受 | 不承担日常任务分发细节 |
| `019ff955-f8a9-76a2-a595-2b91fb8115d6` 总集成 | 执行总负责 / 技术交付经理 | 统一集成、推进 v2 Gate、协调 RAG 与中台、维护集成证据 | 不主动扩大 v2 范围；制作中优先不断流 |
| `019ff9fd-7351-7010-bebf-e419937a7b14` 中台控制面 | 控制面 Owner | 可信身份、权限、Asset/AssetVersion、RuleSet/RuleVersion、AssessmentReport、审计权威 | 不让浏览器、Dify、LLM 或 query user_id 成为可信身份源 |
| `019ff9fd-7350-7720-9d23-34b7fcfd6b13` RAG 后台 | 知识库 / 检索 Owner | 解析、切片、索引、权限前置检索、引用输出、规则库样例、最小评分口径 | 不维护第二套资产、规则或权限权威；DENY 必须发生在召回和 LLM 前 |
| `019ff1bc-281f-7df0-af09-35ac3599fcd5` 规划 | 产品经理 / PO + PMO | v2 Backlog、演示故事、范围边界、验收标准、任务优先级、对外口径 | 需要写入规划文档前先取得 Q 明确授权 |
| `019ff1b3-17e7-7911-bd19-c8ae1c9c0108` 横纵分析 | 架构与方案顾问 | 对比外部方案、识别架构盲区、给产品和技术取舍建议 | 输出建议，不直接改实现主线 |
| `019ff69c-e3be-7670-b8b0-7a52cc7830d2` 战略专家 | 市场 / 合规 / 外部趋势顾问 | 关注金融信息服务、资料匹配、个人信息保护、金融产品营销边界和高价值外部信号 | 只同步影响演示边界的高价值信息，不扩大为泛研究 |
| `019ffa1b-a71c-7cf0-a783-ea9177a6b31e` 独立审计 | 架构治理与风险复核 | 检查角色越权、范围漂移、口径一致性和风险低估 | 只做复核和协调记录，不抢总集成制作职责 |

## 统一禁区

- 不宣称贷款审批、授信、额度测算、金融产品销售。
- 不宣称真实公共盘旁路写已阻断。
- 不宣称生产级 Qdrant、PostgreSQL、OS parser sandbox 已完成。
- Dify/LLM 只做候选生成、解释润色和问答草稿，不做授权裁决、执行凭证、最终评分或金融结论。
- 控制面/BFF 继续是可信身份、资产版本、权限、规则版本、匹配报告和审计的权威。
- RAG 只读授权 active AssetVersion；无权限时必须在候选召回、重排、LLM 上下文和引用生成前 DENY。

## 下轮读取要求

各相关对话下一轮开始时，先读取本文件、`docs/contracts/frozen-v2-integration-contract.md` 和 `docs/demo/enterprise-asset-knowledge-demo-guideline.md`，再继续各自职责范围内工作。
