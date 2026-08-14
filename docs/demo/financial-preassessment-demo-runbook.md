# 资料预评估与银行规则匹配 DEMO 演示 Runbook

状态：受控金融样例的 API 级可复验演示脚本。当前为项目内受控证据，不是真实上传、生产知识库、真实公共盘或真实金融业务验证。

## 主话术

员工上传或选择模拟资料后，系统把资料版本化、结构化，再根据演示银行规则样例做资料匹配度预评估，输出可匹配的示例银行类型、缺失材料和引用依据。结果仅供信息参考，不参与贷款申请、审批、授信、额度测算或金融产品销售。

## 演示前置条件

- 主项目根：D:\AI\Codex\Projects\dify-agent-workspace-tools
- 受控样例：work/demo/financial-preassessment/source（虚构 PDF/DOCX）
- 导入清单：work/demo/financial-preassessment/import-manifest.json（仅 asset 到 material_key 映射）
- 规则夹具：work/demo/financial-preassessment/rules/demo-bank-rules-v1.json（demo_fixture 且带 content_fingerprint）
- 解释器：service/.venv/Scripts/python.exe
- 本轮演示以控制面 API 契约与测试驱动为准；Dify 页面实机与真实服务部署不在本演示范围。

## 演示步骤

### 步骤 1：演示定位与样例展示

- 展示内容：主话术；受控样例目录结构与虚构 PDF/DOCX；导入清单；规则版本标签。
- 输入：无，只读浏览。
- 预期输出：样例文件集合与样例完整性测试固定集合一致；规则夹具显示 version_label=demo-2026-08-14 与 content_fingerprint。
- 留证点：样例目录列表截图；规则 JSON 的版本标签与指纹截图。

### 步骤 2：建立 Asset/AssetVersion

- 展示内容：受控样例进入控制面仓储，生成 asset_id 与 active ready AssetVersion，并绑定实际文件 SHA-256。
- 输入：以测试夹具选择导入清单内 relative_path 建立版本。
- 预期输出：asset_version_id、index_state=ready、content_fingerprint=sha256:<实际文件摘要>。
- 留证点：测试输出或 API 响应中的 asset_version_id 与内容指纹。

### 步骤 3：创建演示 RuleVersion

- 展示内容：RuleSet/RuleVersion 登记，source_type=demo_fixture，content_fingerprint 来自规则夹具。
- 输入：POST /api/rule-sets（scenario=finance_profile_matching）。
- 预期输出：rule_version_id 与规则版本指纹；报告 rule_version_evidence 含 version_label、content_fingerprint、source_type。
- 留证点：rule_version_id 与指纹截图。

### 步骤 4：正向资料匹配评估

- 展示内容：A 对已授权受控资料发起资料匹配度预评估。
- 输入：POST /api/assessments（可信 session、asset_ids、rule_version_id、query_subject）。
- 预期输出：match_score=100、result_level=MATCH、missing_materials=[]、material/rule 两类引用、免责声明。
- 留证点：报告 JSON 截图；match_score 只称资料匹配度。

### 步骤 5：引用与规则依据

- 展示内容：资料引用（asset_id、asset_version_id、chunk_id、page/paragraph）与规则引用（rule_id、rule_version_id、version_label、content_fingerprint、source_type）。
- 输入：读取步骤 4 报告的 citations。
- 预期输出：两类引用齐全，且与本次授权 active AssetVersion 快照及选定 RuleVersion 一致。
- 留证点：citations 数组截图。

### 步骤 6：审计展示

- 展示内容：assessment_report_created 审计关联 actor、asset_versions、rule_version_id、report_id、免责声明版本与确定性结果。
- 输入：读取控制面审计事件列表。
- 预期输出：审计详情不包含资料正文、路径或未授权材料。
- 留证点：审计事件 JSON 截图。

### 步骤 7：越权负向控制（必须演示）

- 展示内容：A 请求敏感资料（内部资料核验说明）评估。
- 输入：同一评估请求指向敏感资料 asset。
- 预期输出：HTTP 403；status=DENIED、reason=ACCESS_DENIED、retrieved_count=0、llm_invoked=false、citations=[]；解析、索引、评分、LLM 与报告均零触发。
- 留证点：403 响应截图；assessment_denied 审计零计数截图。

## 敏感信息禁显项

- 不得展示真实 API Key、内部服务密钥或一次性凭证。
- 不得展示未授权资料正文、路径或 chunk 文本。
- 不得展示真实身份证、账户、流水、征信或真实银行规则。
- 不得使用贷款审批、授信、额度测算、金融产品销售话术。

## 失败注入备用分支（可选演示）

- 规则指纹错配：评估返回 assessment_failed，零报告。
- 资产指纹错配：解析前 fail closed，零解析、零索引、零报告。
- 引用越出授权快照：控制面保存报告前失败关闭。
- 上述分支以可复验基线检查清单的失败注入为准，不作为主故事。

## 边界声明

- 真实上传自动解析与索引：NOT_DONE。
- Dify 页面实机解释与截图：NOT_RUN。
- Qdrant、真实 PostgreSQL、OS 级 parser sandbox：NOT_DONE。
- Windows/SMB 独立服务账号、UNC 与 ACL 旁路写验证：NOT_RUN。
- 真实金融资料与规则、贷款、授信、额度、金融产品销售能力：禁止宣称。
