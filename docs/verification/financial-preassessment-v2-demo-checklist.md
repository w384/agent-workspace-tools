# 资料预评估与银行规则匹配 DEMO 可复验基线检查清单

状态：v2 受控金融样例演示可复验基线。仅代表本地受控证据；未提交、未推送、未发布。

## 复验命令

专项（受控桥接、规则版本、样例完整性）：

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
& '.\service\.venv\Scripts\python.exe' -B -m pytest 'control_plane\tests\test_finance_demo_rag_bridge.py' 'control_plane\tests\test_v2_rules_assessment.py' 'service\tests\rag\test_finance_material_matching.py' 'service\tests\test_financial_preassessment_demo_assets.py' -q -p no:cacheprovider
```

控制面全量、服务端全量与插件全量：

```powershell
& '.\service\.venv\Scripts\python.exe' -B -m pytest control_plane\tests -q -p no:cacheprovider
& '.\service\.venv\Scripts\python.exe' -B -m pytest service\tests -q -p no:cacheprovider
& '.\plugin\.venv\Scripts\python.exe' -B -m pytest plugin\tests -q -p no:cacheprovider
```

提交前检查：

```powershell
git diff --check
```

## 实际结果（2026-08-14 实测）

- 专项：20 passed in 0.40s。
- 控制面：85 passed in 1.31s。
- 服务端：126 passed in 2.12s。
- 插件：103 passed in 2.09s（2 条既有第三方 warning：gevent MonkeyPatch、Pydantic 弃用）。
- git diff --check：exit 0，仅有既有 LF 转 CRLF warning。

## 演示自检/重置验证记录（2026-08-14 执行）

按本清单执行样例完整性、失败注入与重置复跑，日志证据位于 work/demo/financial-preassessment/verification/：

- checklist-step1-sample-integrity.log：8 个 PDF/DOCX 样例文件集合与魔数校验通过；样例完整性测试 2 passed in 0.02s。
- checklist-step2-failure-injection.log：规则指纹错配、资产指纹错配、未声明源、DENY 零召回、越权/错配 material 与 rule 引用共 7 项全部 fail closed，7 passed in 0.24s。
- checklist-step3-reset-regression.log：重置后完整专项复跑 20 passed in 0.40s，证明内存仓储与测试夹具可从干净状态自动重建并全绿。

## 关键断言

正向：

- match_score 为 0-100 整数，不来自规则 JSON 静态展示分数。
- result_level 仅允许 MATCH、POSSIBLE、NOT_MATCH、MISSING_INFO。
- 报告引用区分 material 与 rule：资料引用含 asset_id、asset_version_id、chunk_id、page 或 paragraph；规则引用含 rule_id、rule_version_id、version_label、content_fingerprint、source_type。
- rule_version_evidence 含 rule_version_id、version_label、content_fingerprint、source_type。
- 免责声明或免责声明版本存在，且不含贷款审批、授信、额度测算话术。
- 缺材料返回 POSSIBLE 或 MISSING_INFO，不推断 NOT_MATCH；NOT_MATCH 仅接受显式 fictional_conflict 证据。

负向：

- 越权评估返回 403 与 status=DENIED、reason=ACCESS_DENIED、retrieved_count=0、llm_invoked=false、citations=[]。
- DENY 发生在解析、索引、评分、LLM 与报告前；解析/索引/评分/LLM 零调用，不创建 AssessmentReport。
- 规则指纹错配：502 assessment_failed，零报告。
- 资产内容指纹与受控源文件不一致：解析前 fail closed，零解析、零索引、零报告。
- RAG 返回越出授权快照的 material 或 rule 引用：保存报告前失败关闭。
- 未在导入清单声明的资料：502 assessment_failed，零报告。
- 审计只记录安全计数与关联 ID，不包含未授权路径、正文或 chunk。

## 失败注入

1. RuleVersion 指纹错配。
2. AssetVersion content_fingerprint 与受控源文件 SHA-256 不一致。
3. RAG 返回越权 material 引用或错配 rule 引用。
4. 无权限请求敏感资料导致 DENY 零召回。
5. 导入清单未声明的 source 被请求。

## 重置步骤

- 样例完整性校验：重跑专项测试（固定 8 个 PDF/DOCX 文件集合、rules 版本标签与指纹）。
- 若样例文件被改动：在具备 python-docx 与 reportlab 依赖的解释器运行 scripts/build_financial_preassessment_demo_assets.py 重建（主项目 service venv 当前未含 reportlab，重建命令未在本机验证，作为边界说明）。
- 应用状态重置：重启 control_plane 进程或重新创建内存仓储；测试夹具每次自动重建 asset、version、rule、report 状态。
- 复跑专项与全量命令确认全绿。

## 残余风险

- 真实上传自动解析与索引：NOT_DONE。
- Dify 页面实机解释与 Workflow 追踪：NOT_RUN。
- Qdrant、真实 PostgreSQL、OS 级无网络/资源隔离 parser sandbox：NOT_DONE。
- Windows/SMB 独立服务账号、UNC 与 ACL 旁路写验证：NOT_RUN。
- 真实银行规则、真实金融资料、金融业务上线许可：NOT_DONE。
- 贷款审批、授信、额度测算、金融产品销售能力：禁止宣称。

## 未提交状态

- 全部变更未提交、未推送、未发布。
- git status 含大量既有未提交变更（service、plugin、docs、control_plane、work 等），本轮仅新增上述文档；未触碰 Dify、公共盘或 ACL。
