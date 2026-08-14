# 冻结纲要 v2：企业资料资产化与场景知识库契约

> 状态：v2 已启动。本文取代 v1 作为后续演示制作与跨任务协作的当前权威纲要；v1 保留为 Gate 1-5 本地组合验收的历史基线。

## 目标定位

本项目主线升级为企业资料的文件整理、资产版本化、知识库建立、索引检索与可解释业务问答底座。

首个对外演示板块调整为“金融资料匹配”：

- 用户上传或选择模拟资料。
- 系统建立 `Asset / AssetVersion`。
- 系统解析、切片、索引资料。
- 系统基于规则库样例回答资料匹配度、可匹配示例银行、缺失材料与依据。
- 所有结果保留权限、版本、引用和审计边界。

金融板块只是可替换场景之一，不得把主线写死为贷款系统或金融决策平台。

## 对外表达

对外窄说，内部宽做：

- 面对当前金融信息服务客户：说“资料预评估与银行规则匹配 DEMO”。
- 面对其他客户：可替换为投标资料检查、供应商准入、合同审查、项目归档等场景。
- 团队内部：统一称为“企业资料资产化 + 场景知识库 + 权限检索 + 可解释业务问答”。

不得宣称：

- 已覆盖所有行业。
- 已完成金融智能决策平台。
- 可做贷款审批、授信、额度测算或金融产品销售。
- 真实公共盘旁路写已阻断。
- 生产级 Qdrant、PostgreSQL、OS parser sandbox 已完成。

## 架构边界

### 控制面 / BFF

控制面仍是以下对象的唯一权威：

- 可信身份与 session。
- `Asset / AssetVersion`。
- `PermissionGrant` 与 ACL 裁决。
- `RuleSet / RuleVersion`。
- 匹配报告与审计事件。
- 计划、确认、执行和查询的关联证据。

浏览器、Dify、LLM 或普通 query 参数中的 `user_id` 仍不构成可信身份。

### 文件执行器

FastAPI 仍是文件写入执行边界。

在金融资料匹配首板块中，若不需要真实移动公共盘文件，不强行展示写入能力；若展示整理/归档，仍必须走服务端预检、确认、执行前指纹重验、审计和零写入失败分支。

### RAG / 索引

RAG 仍是只读副本：

- 只读取控制面授权的 active `AssetVersion`。
- 不创建第二套资产、规则或权限权威。
- `DENY` 必须发生在候选召回、评分、重排、LLM 上下文和引用生成之前。
- 回答必须带 `asset_id`、`asset_version_id`、`chunk_id`、页码/段落、规则版本或知识来源。

### Dify / LLM

Dify/LLM 只能承担：

- 对话入口或候选计划生成。
- 解释文本润色。
- 问答草稿生成。

Dify/LLM 不能承担：

- 授权裁决。
- 执行凭证。
- 最终评分权威。
- 贷款结论。
- 授信、额度或金融产品推荐决策。

规则匹配优先由确定性规则完成；LLM 只解释确定性结果。

## 新增共同实体

### RuleSet

```json
{
  "rule_set_id": "ruleset_...",
  "scenario": "finance_profile_matching",
  "name": "演示银行规则样例",
  "status": "active"
}
```

### RuleVersion

```json
{
  "rule_version_id": "rulever_...",
  "rule_set_id": "ruleset_...",
  "source_type": "demo_fixture|manual_entry|verified_external_source",
  "version_label": "demo-2026-08-14",
  "content_fingerprint": "sha256:...",
  "created_at": "2026-08-14T00:00:00Z"
}
```

首轮只能使用 `demo_fixture` 或人工录入的脱敏演示规则。不得声称为真实银行内部规则。

### AssessmentReport

```json
{
  "report_id": "report_...",
  "scenario": "finance_profile_matching",
  "actor_id": "user_...",
  "asset_versions": ["asset_version_..."],
  "rule_version_id": "rulever_...",
  "match_score": 82,
  "result_level": "MATCH|POSSIBLE|NOT_MATCH|MISSING_INFO",
  "missing_materials": [],
  "citations": [],
  "disclaimer": "仅供资料完整度与规则匹配演示参考"
}
```

`match_score` 是资料与规则匹配度，不得称为信用评分、授信评分或贷款审批评分。

## v2 首轮演示路径

1. 演示公司身份：一家提供资料匹配与信息服务的公司。
2. 员工上传或选择客户模拟资料。
3. 控制面创建 `Asset / AssetVersion`，记录来源、哈希和状态。
4. RAG 解析 PDF/DOCX，建立最小索引。
5. 系统读取演示银行规则 `RuleVersion`。
6. 用户提问：“这个客户资料匹配度是多少？能匹配哪些示例银行要求？缺哪些材料？”
7. 服务端执行确定性规则匹配。
8. LLM 可将结构化结果润色成人类可读报告。
9. 报告返回匹配度、可匹配/可能匹配/暂不匹配示例银行、缺失材料、引用依据和免责声明。
10. 展示权限负向控制：无权用户不能检索他人资料或敏感规则依据。

## v2 验收 Gate

| Gate | 最小验收证据 |
| --- | --- |
| Gate V2-1 场景样例 | 金融资料模拟数据、演示银行规则、免责声明均为脱敏/虚构，并有明确来源标签。 |
| Gate V2-2 资产版本 | 上传或选择资料后生成 `Asset / AssetVersion`，失败版本不替换旧 active。 |
| Gate V2-3 解析索引 | PDF/DOCX 被解析、切片、索引，并带版本化引用。 |
| Gate V2-4 规则匹配 | 确定性规则输出匹配度、结果等级、缺失材料和规则版本。 |
| Gate V2-5 可解释问答 | 回答引用资料版本、chunk/page/paragraph 和规则版本；LLM 只润色，不做最终裁决。 |
| Gate V2-6 权限负向 | 无权用户在召回前 `DENY`，`retrieved_count=0`、`llm_invoked=false`、`citations=[]`。 |
| Gate V2-7 审计 | 记录资料版本、规则版本、匹配报告、查询主体、时间和免责声明版本。 |

## 任务分工

- 规划任务：统一 v2 口径，防止金融板块被误写成主线全量定位。
- 执行总负责：把现有演示样例调整为金融资料匹配板块，并继续维护共同契约和集成证据。
- RAG 后台：准备规则库样例、规则版本、引用输出、最小评分口径和权限前置检索。
- 中台控制面：保持身份、权限、资产版本、规则版本、匹配报告和审计权威。
- 研究任务：关注金融信息服务、资料匹配、个人信息保护、金融产品网络营销边界；只同步影响演示边界的高价值信息。

## 保留风险

- 真实公共盘、Windows/SMB 独立账号、UNC 与 ACL 仍需单独实测。
- 真实用户上传真实金融资料前，必须补充个人信息授权、删除机制、传输加密、访问控制和日志脱敏。
- Qdrant、真实 PostgreSQL、OS 级 parser sandbox 仍不能因 v2 启动而默认完成。
- 任何真实银行规则、贷款产品要求或金融营销材料必须先确认来源与授权。

