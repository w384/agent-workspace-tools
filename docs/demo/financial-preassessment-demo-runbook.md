# 资料预评估与银行规则匹配 DEMO 演示 Runbook（统一入口 /demo/ 双路径）

状态：受控金融样例的统一前端 /demo/ 双路径可复验演示脚本。当前为项目内受控证据，不是真实上传、生产知识库、真实公共盘或真实金融业务验证。

## 主话术

统一演示入口 /demo/（最小自研前端），员工登录后同一界面两条路径并存：路径 A「资料预评估报告」与路径 B「LLM 知识库问答」。

- 路径 A：员工上传或选择模拟资料后，系统把资料版本化、结构化，再根据演示银行规则样例做资料匹配度预评估，输出可匹配的示例银行类型、缺失材料和引用依据。
- 路径 B：同一登录态下，员工基于已授权资料提出知识库问答；系统先做权限前置召回，再由真实 LLM 依据授权证据生成回答草稿/润色，返回 answer 与版本化 citations。
- 两路径结果仅供信息参考，不参与贷款申请、审批、授信、额度测算或金融产品销售。

## 演示前置条件

- 主项目根：D:\AI\Codex\Projects\agent-workspace-tools
- 统一演示入口：control_plane/static/** + /demo 挂载（最小自研前端）
- 受控样例：work/demo/financial-preassessment/source（虚构 PDF/DOCX）
- 导入清单：work/demo/financial-preassessment/import-manifest.json（仅 asset 到 material_key 映射）
- 规则夹具：work/demo/financial-preassessment/rules/demo-bank-rules-v1.json（demo_fixture 且带 content_fingerprint）
- 解释器：service/.venv/Scripts/python.exe
- 一键初始化：scripts/init_demo_financial_preassessment.py（E3 幂等种子脚本：登录态 alice/demo-a-password + 按 import-manifest 建受控资产 + demo_fixture 规则）
- 本轮演示以控制面 API 契约与测试驱动为准；Dify 页面实机与真实服务部署不在本演示范围。

## 演示步骤

### 步骤 0：一键初始化演示环境（E3）

- 展示内容：幂等可重复的初始化脚本一键建立「可演示」状态——登录态（alice/demo-a-password）、按 import-manifest 声明创建 Asset/AssetVersion（绑定真实文件 SHA-256、index_state=ready、active）、demo_fixture 规则版本（content_fingerprint 取自受控夹具）。
- 输入：运行 service/.venv/Scripts/python.exe scripts/init_demo_financial_preassessment.py（默认在 http://127.0.0.1:8891 提供 /demo/）；仅建状态不启动服务用 --seed-only。
- 预期输出：打印 seed summary（asset_count=6、active_version_count=6、rule_version_count=1）；重复执行资产/规则数量不增长（assets_created/rule_versions_created=0）；初始化后路径 A 评估 MATCH 100。
- 留证点：seed summary 输出；重复执行前后数量对比。

### 步骤 1：统一入口 /demo/ 与演示定位

- 展示内容：主话术；登录态下统一入口 /demo/ 首页含「资料预评估」「知识库问答」双 tab 与「免责声明」；受控样例目录结构与虚构 PDF/DOCX；导入清单；规则版本标签。
- 输入：浏览器打开 /demo/ 并完成受控身份登录。
- 预期输出：首页显示双 tab + 免责声明；浏览器只调 BFF，不泄露 api_key/密钥/本地路径；样例文件集合与样例完整性测试固定集合一致；规则夹具显示 version_label=demo-2026-08-14 与 content_fingerprint。
- 留证点：首页双 tab 与免责声明截图；样例目录列表截图；规则 JSON 的版本标签与指纹截图。

### 路径 A「资料预评估报告」

#### 步骤 2：建立 Asset/AssetVersion（路径 A 前置）

- 展示内容：受控样例进入控制面仓储，生成 asset_id 与 active ready AssetVersion，并绑定实际文件 SHA-256。
- 输入：以测试夹具选择导入清单内 relative_path 建立版本。
- 预期输出：asset_version_id、index_state=ready、content_fingerprint=sha256:<实际文件摘要>。
- 留证点：测试输出或 API 响应中的 asset_version_id 与内容指纹。

#### 步骤 3：创建演示 RuleVersion

- 展示内容：RuleSet/RuleVersion 登记，source_type=demo_fixture，content_fingerprint 来自规则夹具。
- 输入：POST /api/rule-sets（scenario=finance_profile_matching；前端不传 content_fingerprint，由 BFF 以受控夹具真实指纹创建；前端若传入与夹具不符的指纹，BFF 在创建前 422 拒绝，fail closed）。
- 预期输出：rule_version_id 与规则版本指纹；报告 rule_version_evidence 含 version_label、content_fingerprint、source_type。
- 留证点：rule_version_id 与指纹截图。

#### 步骤 4：正向资料匹配评估

- 展示内容：A 对已授权受控资料发起资料匹配度预评估。前端提供 E5 受控文件选择器（input type=file）。
- E5 受控文件选择器：仅接受 import-manifest 白名单内 6 个受控样例文件名（资料概览与授权说明.docx / 收入情况说明.pdf / 资金流摘要.pdf / 资产负债说明.docx / 经营情况说明.docx / 补充材料清单.pdf）；选择白名单外文件，前端拦截并提示「底层拒绝」，enqueue_version 仍拒绝任意上传文件（安全断言不变）。
- 演示期操作路径（「选中即自动发起评估」的 BFF 端点为 P1 延后，不属当前演示承诺）：① 在 E5 文件选择器中选择受控样例文件（通过白名单校验）→ ② 从初始化脚本 seed summary（scripts/init_demo_financial_preassessment.py --seed-only 输出）中取得对应 asset_id → ③ 手动填入 asset_ids → ④ 发起评估。
- 输入：POST /api/assessments（可信 session、asset_ids、rule_version_id、query_subject）。
- 预期输出：match_score=100、result_level=MATCH、missing_materials=[]、material/rule 两类引用、免责声明。
- 留证点：报告 JSON 截图；match_score 只称资料匹配度。

#### 步骤 5：引用与规则依据

- 展示内容：资料引用（asset_id、asset_version_id、chunk_id、page/paragraph）与规则引用（rule_id、rule_version_id、version_label、content_fingerprint、source_type）。
- 输入：读取步骤 4 报告的 citations。
- 预期输出：两类引用齐全，且与本次授权 active AssetVersion 快照及选定 RuleVersion 一致。
- 留证点：citations 数组截图。

#### 步骤 6：审计展示

- 展示内容：assessment_report_created 审计关联 actor、asset_versions、rule_version_id、report_id、免责声明版本与确定性结果。
- 输入：读取控制面审计事件列表。
- 预期输出：审计详情不包含资料正文、路径或未授权材料。
- 留证点：审计事件 JSON 截图。

### 路径 B「LLM 知识库问答」

#### 步骤 7：权限前置召回与授权证据

- 展示内容：同一登录态切换「知识库问答」tab。
- 输入：输入问题 + asset_id，POST /api/retrieval/query。
- 预期输出：权限前置召回先于 LLM 完成，返回授权证据（retrieved_count 等）；未授权资产在召回前 DENY，不进入 LLM。
- 留证点：问答请求与授权证据截图；LLM 调用点位于授权裁决之后。

#### 步骤 8：真实 LLM 生成回答

- 展示内容：真实 LLM 依据授权证据生成回答草稿/润色，非确定性 chunk 摘录占位。
- 输入：步骤 7 的授权证据进入 LLM。
- 预期输出：返回 answer + 版本化 citations（asset_id/asset_version_id/chunk_id/page/paragraph/path_kind）；LLM 不裁决（不产出授权结论、最终评分权威、贷款/授信/额度/产品推荐）；LLM 凭证（api_key/base_url/model）不落前端、BFF 响应与审计。
- 留证点：answer 与 citations 截图；llm_invoked=true 审计截图。

#### 步骤 9：路径 B 负向演示（必须演示）

- 展示内容：请求无权限资产的问答。
- 输入：问答请求指向越权资产。
- 预期输出：DENY/REFUSED；llm_invoked=false、LLM 零调用、retrieved_count=0、citations=[]。
- 留证点：DENY 响应与 LLM 零调用审计截图。

### 步骤 10：越权负向控制（两路径共用，必须演示）

- 展示内容：A 请求敏感资料（内部资料核验说明）评估。
- 输入：同一评估请求指向敏感资料 asset。
- 预期输出：HTTP 403；status=DENIED、reason=ACCESS_DENIED、retrieved_count=0、llm_invoked=false、citations=[]；解析、索引、评分、LLM 与报告均零触发。
- 留证点：403 响应截图；assessment_denied 审计零计数截图。

## 敏感信息禁显项

- 不得展示真实 API Key、内部服务密钥或一次性凭证。
- 不得在静态资源、BFF 响应与审计中展示 LLM 凭证（api_key/base_url/model）。
- 不得展示未授权资料正文、路径或 chunk 文本。
- 不得展示真实身份证、账户、流水、征信或真实银行规则。
- 不得使用贷款审批、授信、额度测算、金融产品销售话术。

## 失败注入备用分支（可选演示）

- 规则指纹错配：评估返回 assessment_failed，零报告。
- 资产指纹错配：解析前 fail closed，零解析、零索引、零报告。
- 引用越出授权快照：控制面保存报告前失败关闭。
- 上述分支以可复验基线检查清单的失败注入为准，不作为主故事。

## 边界声明

- 真实 LLM 接入（AnswerGenerator/ExplanationPort + BFF 桥接）：P0 在途，实施归 RAG 后台 + 控制面，执行总负责统筹验收与集成；演示期使用受控 demo LLM 凭证（脱敏），不落前端、不入库明文。
- 真实上传自动解析与索引：NOT_DONE。
- Dify 页面实机解释与截图：NOT_RUN。
- Qdrant、真实 PostgreSQL、OS 级 parser sandbox：NOT_DONE。
- Windows/SMB 独立服务账号、UNC 与 ACL 旁路写验证：NOT_RUN。
- 真实金融资料与规则、贷款、授信、额度、金融产品销售能力：禁止宣称。
