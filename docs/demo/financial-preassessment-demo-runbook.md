# 资料预评估与银行规则匹配 DEMO 演示 Runbook（统一入口 /demo/ 双路径）

状态：受控金融样例的统一前端 /demo/ 双路径可复验演示脚本。当前为项目内受控证据，不是真实上传、生产知识库、真实公共盘或真实金融业务验证。

## 主话术

统一演示入口 /demo/（最小自研前端），员工登录后同一界面多条路径并存：路径 A「资料预评估报告」、路径 B「LLM 知识库问答」、路径 C「已建库文件管理」、路径 D「计划执行演示」。

- 路径 A：员工上传或选择模拟资料后，系统把资料版本化、结构化，再根据演示银行规则样例做资料匹配度预评估，输出可匹配的示例银行类型、缺失材料和引用依据。评估分「受控样例」（import-manifest 白名单）与「真实材料」（放宽白名单，自定类别）两种方式。
- 路径 B：同一登录态下，员工基于已授权资料提出知识库问答；系统先做权限前置召回，再由真实 LLM 依据授权证据生成回答草稿/润色，返回 answer 与版本化 citations。可勾选多个已上传文件跨文件一次提问（query-multi）。
- 路径 C：已建库真实材料文件管理：覆盖上传（同名替换）/ 删除，便于下次演示复用同名文件。
- 路径 D：计划 → 确认/审批 → 执行 → 独立读回验证闭环（carol 行动 + dave 审批，四眼原则）。
- 两路径结果仅供信息参考，不参与贷款申请、审批、授信、额度测算或金融产品销售。

## 演示前置条件

- 主项目根：D:\AI\dsh\Projects\agent-workspace-tools
- 统一演示入口：control_plane/static/** + /demo 挂载（最小自研前端）
- 受控样例：work/demo/financial-preassessment/source（虚构 PDF/DOCX）
- 导入清单：work/demo/financial-preassessment/import-manifest.json（仅 asset 到 material_key 映射）
- 规则夹具：work/demo/financial-preassessment/rules/demo-bank-rules-v1.json（demo_fixture 且带 content_fingerprint）
- 解释器：service/.venv/Scripts/python.exe
- 一键初始化：scripts/init_demo_financial_preassessment.py（E3 幂等种子脚本：登录态 alice/demo-a-password、bob/demo-b-password、carol/demo-c-password、dave/demo-d-password + 按 import-manifest 建受控资产 + demo_fixture 规则 + carol 三个行动授权 grant）
- 本地 LLM（路径 B 问答用）：llama.cpp llama-server 运行于 http://127.0.0.1:18080/v1，模型 qwen3.8-27b-local（/v1/models 可见）；llama-server 若启用了 --api-key 鉴权，启动演示服务前须注入 RAG_LLM_LOCAL_API_KEY，否则本地问答 fail-closed 为 REFUSED(llm_unavailable)；推理模型含思考过程耗时较长，代码默认 LLM 超时 120s，仍超时可注入 RAG_LLM_TIMEOUT_SECONDS 调大。
- 本轮演示以控制面 API 契约与测试驱动为准；Dify 页面实机与真实服务部署不在本演示范围。

## 演示步骤

### 步骤 0：一键初始化演示环境（E3）

- 展示内容：幂等可重复的初始化脚本一键建立「可演示」状态——登录态（alice/demo-a-password）、按 import-manifest 声明创建 Asset/AssetVersion（绑定真实文件 SHA-256、index_state=ready、active）、demo_fixture 规则版本（content_fingerprint 取自受控夹具）。
- 输入：运行 service/.venv/Scripts/python.exe scripts/init_demo_financial_preassessment.py（默认在 http://127.0.0.1:8891 提供 /demo/）；仅建状态不启动服务用 --seed-only。本地问答需在启动前注入环境变量：RAG_LLM_LOCAL_API_KEY（llama-server 开启 --api-key 鉴权时）、按需 RAG_LLM_TIMEOUT_SECONDS。
- 预期输出：打印 seed summary（asset_count=6、active_version_count=6、rule_version_count=1）；重复执行资产/规则数量不增长（assets_created/rule_versions_created=0）；初始化后路径 A 评估 MATCH 100。
- 留证点：seed summary 输出；重复执行前后数量对比。

### 步骤 1：统一入口 /demo/ 与演示定位

- 展示内容：主话术；登录态下统一入口 /demo/ 首页含「资料预评估」「知识库问答」「已建库文件」「计划执行演示」四 tab 与「免责声明」；受控样例目录结构与虚构 PDF/DOCX；导入清单；规则版本标签。
- 输入：浏览器打开 /demo/ 并完成受控身份登录。
- 预期输出：首页显示四 tab + 免责声明；登录面板展示四个演示账号提示（alice 有权限 / bob 越权负向 / carol 计划执行 / dave 审批者）；浏览器只调 BFF，不泄露 api_key/密钥/本地路径；样例文件集合与样例完整性测试固定集合一致；规则夹具显示 version_label=demo-2026-08-14 与 content_fingerprint。
- 留证点：首页四 tab 与免责声明截图；样例目录列表截图；规则 JSON 的版本标签与指纹截图。

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
- 演示期操作路径（P1 已落地）：前端只提交 import-manifest 白名单文件名，BFF 经 POST /api/controlled-sample/assess 自动解析为 asset_id 并复用 create_assessment_report（资产 ID 对演示隐藏，浏览器不再暴露 asset_ids）。
- 输入：POST /api/controlled-sample/assess（可信 session、scenario=finance_profile_matching、query_subject、file_names=白名单内文件名）。
- 预期输出：match_score=100、result_level=MATCH、missing_materials=[]、material/rule 两类引用、免责声明。
- 留证点：报告 JSON 截图；match_score 只称资料匹配度。

#### 步骤 4b：真实材料评估（放宽白名单，新增）

- 展示内容：Q 已明确「真实材料预评估放宽白名单」——评估页新增「真实材料评估」表单：上传自己的真实 PDF/DOCX（≤2MB），为每个文件选择对应材料类别（资料概览 / 收入情况 / 资金流 / 资产负债 / 经营情况 / 补充材料清单，与演示银行规则 requirements 的 material_key 对齐），提交后按同一套规则夹具做资料匹配度预评估。
- 安全边界：走显式端点 POST /api/real-material/assess（任何登录身份评估自己拖入的字节，无需 QUERY grant、不建资产、不入知识库、不产生授信/额度结论）；受控样例评估的 E5 白名单限制原样保留；`enqueue_version` 拒绝任意上传的约束不变。
- 输入：multipart（scenario、query_subject、files 多个 + material_keys 与文件对齐）。
- 预期输出：报告与受控路径同构（match_score / result_level / missing_materials / candidate_banks / citations，asset_versions=[]）；提供规则 A 全部三类材料 → MATCH 100 / missing=[]；部分材料 → 报告列出缺失类别。
- 留证点：报告 JSON 截图；缺失材料列表截图；bob（无 QUERY grant）评估自己文件成功 200。

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
- 输入：选择受控样例文件并输入问题，POST /api/controlled-sample/query（前端不暴露 asset_id，BFF 自动解析白名单文件）；或勾选多个已上传真实材料，POST /api/demo/knowledge/query-multi（跨文件一次检索，去重后 ≤6 文件；任一文件未授权 → 整单 DENIED 零召回零 LLM 调用，fail-closed）。
- 预期输出：权限前置召回先于 LLM 完成，返回授权证据（retrieved_count 等）；未授权资产在召回前 DENY，不进入 LLM。
- 留证点：问答请求与授权证据截图；LLM 调用点位于授权裁决之后。

#### 步骤 8：真实 LLM 生成回答

- 展示内容：真实 LLM 依据授权证据生成回答草稿/润色，非确定性 chunk 摘录占位。
- 输入：步骤 7 的授权证据进入 LLM。
- 预期输出：返回 answer + 版本化 citations（asset_id/asset_version_id/chunk_id/page/paragraph/path_kind）；LLM 不裁决（不产出授权结论、最终评分权威、贷款/授信/额度/产品推荐）；LLM 凭证（api_key/base_url/model）不落前端、BFF 响应与审计。本地模型需在启动演示服务时注入 RAG_LLM_LOCAL_API_KEY；未注入时 llama-server 401，问答 fail-closed 为 REFUSED(llm_unavailable)、llm_invoked=true、retrieved_count>0——可作为「凭证不落前端 + 失败闭环」的补充展示点。
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

### 步骤 11：控制面计划执行闭环（Agent Action Gateway 可验证执行，可选演示）

- 展示内容：演示服务已启用真实受控目录执行器 ControlledFileExecutor 与同根独立读回验证器 ControlledDirectoryVerifier（受控根 work/demo/financial-preassessment/controlled-actions/，已加入 .gitignore）。闭环行为（计划 → 确认 → 执行 → 读回 → VERIFIED；trash 走 APPROVAL_REQUIRED 审批；MISMATCH → recovery_task）由控制面测试覆盖（test_controlled_file_executor / test_recovery / test_verification，HTTP 层 test_recovery_approval_http、test_demo_carol_plan_flow）。
- 前端已提供「计划执行演示」tab（第四页，路径 D）：① carol 上传任意文件到受控目录 organized/（≤2MB，POST /api/demo/plan-demo/upload，不走 rag enqueue）；② 移动（SELF_CONFIRM，carol 确认后真实迁移文件、读回 VERIFIED）或删除（APPROVAL_REQUIRED，carol 建计划）；③ 切 dave 登录审批（四眼原则：carol 尝试自批 → 403 approval_forbidden）；④ 审批通过后执行删除并读回 VERIFIED；验证失败时「恢复任务」区出现 MISMATCH 的 Recovery Task，可标记 recovered / escalated。
- 实机负向（当前 /demo 默认可演示）：演示身份权限矩阵不授 bob 任何行动权限，故 bob 上传 / 建计划 → 403 upload_denied / plan_denied（实测 2026-09-18）——「行动零授权 fail-closed」的可演示负向。
- 正向实机演示前提：种子脚本已为 carol（user-c）注入 organized/ 上 UPLOAD / MOVE_RENAME / TRASH 三个行动授权 grant（幂等）；按测试用例走上传 → 建计划 → confirm（带 Idempotency-Key）→ 预期 confirm 响应 execution_job.state=verified、plan.state=verified、审计 execution_verified（verification_status=verified）、受控根内源文件消失且目标存在、内容指纹一致；trash 需 dave decide_approval 后执行并读回 VERIFIED。
- 留证点（负向）：403 plan_denied / upload_denied 响应截图；审计零执行事件截图。
- 负向分支（不必实机演示）：执行器层路径逃逸 fail-closed（create_plan 越界路径 → PermissionError）；验证失败 → HTTP 422 verification_failed + recovery_task（服务层 test_trash_verification / HTTP test_recovery_approval_http 已覆盖 MISMATCH→恢复/升级闭环）。

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

- 真实 LLM 接入（AnswerGenerator/ExplanationPort + BFF 桥接 + 越权负向 bob 演示身份）：已完成（提交 4d0c241）；演示期使用受控 demo LLM 凭证（脱敏），不落前端、不入库明文。
- 真实上传自动解析与索引：已完成（提交 5227ed3，真实材料上传→SHA-256 指纹→PDF/DOCX 解析→向量索引→授权绑定→权限感知检索闭环）。
- Dify 页面实机解释与截图：NOT_RUN。
- Qdrant、真实 PostgreSQL、OS 级 parser sandbox：NOT_DONE。
- Windows/SMB 独立服务账号、UNC 与 ACL 旁路写验证：NOT_RUN。
- 真实金融资料与规则、贷款、授信、额度、金融产品销售能力：禁止宣称。
