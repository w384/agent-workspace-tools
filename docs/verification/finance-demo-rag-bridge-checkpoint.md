# 资料预评估与银行规则匹配 DEMO：受控桥接检查点

状态：v2 受控金融样例 Assessment API 真实桥接检查点。不是生产发布、真实上传自动处理或真实金融业务验证。

## 本检查点证明的内容

- 只读取 `work/demo/financial-preassessment/source` 下的虚构 PDF/DOCX；导入清单 `import-manifest.json` 是 `material_key` 的唯一来源。
- 控制面先以可信 session、同源 `PermissionGrant`、active 且 `ready` 的 `AssetVersion` 选择范围；桥接不接收客户端 `user_id`，不创建第二套资产、规则或权限权威。
- `FinanceDemoRagPort` 对清单声明的资料调用现有 PDF/DOCX parser，按页或非空段落切片，并写入可删除、可重建的 `InMemorySearchIndex`。
- 确定性规则只按受控清单中的 `{rule_id, material_key, label}` 计算：完整命中为 `MATCH=100`；分数不是信用、授信、审批或额度评分。
- 结果引用包含 `asset_version_id`、`chunk_id`、PDF 页码或 DOCX 段落；控制面报告保留 RuleVersion 指纹与免责声明版本。
- BFF 的越权资料匹配在桥接前返回 `assessment_denied` / HTTP 403；解析、索引、评分、LLM 与报告均不触发，安全审计仅记录零计数。

## Assessment API 证据

- `POST /api/assessments` 仅消费可信 session、控制面选择的 active `ready` AssetVersion 和已登记的 `demo_fixture` RuleVersion；请求自报的身份、旧版本和 LLM 报告不构成权威输入。
- 成功响应的每条安全引用包含 `asset_id`、`asset_version_id`、`chunk_id`、`page` 或 `paragraph` 和 `rule_version_id`；不返回路径、正文或未授权材料。
- `assessment_report_created` 审计关联 actor、asset version 列表、RuleVersion、report_id、规则来源、免责声明版本、确定性匹配结果和报告创建时间。
- 无权响应固定为 HTTP 403 与 `status=DENIED`、`retrieved_count=0`、`llm_invoked=false`、`citations=[]`；同一安全计数写入审计，且不创建报告。
- RuleVersion 指纹错配或非导入清单声明的资料均 fail closed，不解析、不索引、不创建报告；资料不完整时返回 `POSSIBLE` 或 `MISSING_INFO`，不因缺材料推断 `NOT_MATCH`。

## 可复验命令

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
& '.\service\.venv\Scripts\python.exe' -B -m pytest `
  'control_plane\tests\test_finance_demo_rag_bridge.py' `
  'control_plane\tests\test_v2_rules_assessment.py' `
  'service\tests\rag\test_finance_material_matching.py' `
  'service\tests\test_financial_preassessment_demo_assets.py' -q -p no:cacheprovider
```

本检查点实际结果：`20 passed in 0.40s`。

## 规则与版本证据安全加固

- `import-manifest.json` 仅声明受控源文件相对路径与预声明 `material_key`，不得包含 `requirements`、分数或规则裁决字段。
- 参与评估的 requirement 只能由规则夹具的 `assessment_rule_id` 选择；该规则夹具整体受 `RuleVersion.content_fingerprint` 校验保护。
- 每个 `AssetVersion` 在解析前重新计算受控源文件 SHA-256；与版本指纹不一致时 fail closed，不解析、不索引、不创建报告。
- 报告引用区分 `material` 与 `rule`：资料引用绑定 asset/version/chunk/page-or-paragraph；规则引用绑定 rule_id、rule_version_id、version_label、source_type 与 content_fingerprint。
- 控制面在保存报告前再次校验 RAG 返回引用：资料引用必须属于本次授权的 active `AssetVersion`；规则引用必须精确匹配本次选定 RuleVersion。任一错配均以 `assessment_failed` 失败关闭，不保存报告。
- 权限拒绝响应除零召回、零 LLM、零引用外，固定返回 `reason=ACCESS_DENIED`；拒绝审计记录请求主体、规则版本和尝试资产 ID，不写入资料正文或路径。

## V2 Gate 覆盖范围

| Gate | 本检查点证据 | 未覆盖部分 |
| --- | --- | --- |
| V2-1 场景样例 | 虚构 PDF/DOCX、`demo_fixture` 规则和免责声明由样例完整性测试固定 | 不含真实客户、银行或业务规则 |
| V2-2 资产版本 | 测试创建 active `ready` AssetVersion，并将实际文件 SHA-256 绑定到版本 | 不是任意真实上传自动解析 |
| V2-3 解析索引 | PDF 页、DOCX 段落真实解析并进入 InMemorySearchIndex | 不含 Qdrant 或 OS 级 parser sandbox |
| V2-4 规则匹配 | 3 项受控材料完整命中，输出 `MATCH=100` 与 RuleVersion 指纹 | 未实现真实银行规则或业务决策 |
| V2-5 可解释问答 | Assessment API 返回资料版本化引用和规则版本证据；LLM 未参与最终裁决 | 没有 Dify 页面实机解释截图 |
| V2-6 权限负向 | BFF 403 的安全响应与审计均为零召回/零 LLM/零引用，桥接零解析/零索引/零报告 | 不替代真实公共盘或 SMB ACL 验证 |
| V2-7 审计 | 控制面保留 assessment report 与 `assessment_denied` 审计，关联报告、规则来源、版本、免责声明和结果 | PostgreSQL 持久化未实测 |

## 仍为 NOT_DONE / NOT_RUN

- 任意真实上传的自动解析、切片、索引与匹配。
- Dify 页面或 LLM 对确定性报告的实机解释链路。
- Qdrant、真实 PostgreSQL、OS 级无网络/资源隔离 parser worker。
- Windows/SMB 独立服务账号、UNC 与 ACL 旁路写环境验证。
- 贷款申请、审批、授信、额度测算、金融产品销售或真实银行规则能力。
