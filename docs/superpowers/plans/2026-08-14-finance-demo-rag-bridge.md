# Finance Demo RAG Bridge Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让项目内虚构金融 PDF/DOCX 样例经真实解析、切片和内存索引后，安全地进入 v2 确定性资料匹配。

**Architecture:** 新增受控导入清单，唯一声明 sample asset 与 `material_key` 的关系。`FinanceDemoRagPort` 仅接收控制面已授权的 active `AssetVersion` 与 `RuleVersion`，调用现有 parser/index 和 `FinanceMaterialMatchingService`；控制面继续负责 session、ACL、AssetVersion、RuleVersion、报告和审计。

**Tech Stack:** Python 3.12、FastAPI、pypdf、python-docx、现有 `InMemorySearchIndex` 与 RAG 值对象。

## Global Constraints

- 只读取 `work/demo/financial-preassessment/source` 中的虚构 PDF/DOCX；不接真实上传、公共盘或 SMB。
- `material_key` 只来自导入清单，不从文件名、自由文本或 LLM 推断。
- `MATCH=100`、`POSSIBLE=round(100*命中/要求)`、`MISSING_INFO=0`；`NOT_MATCH` 仅接受显式虚构冲突证据。
- DENY 必须发生在事实索引、评分、解释和引用前，返回零召回、零引用、零 LLM。
- Dify/LLM 仅能解释已完成的确定性报告，不得改变评分、等级、材料、权限、引用或规则版本。

---

### Task 1: 受控金融样例导入清单

**Files:**
- Create: `work/demo/financial-preassessment/import-manifest.json`
- Modify: `scripts/build_financial_preassessment_demo_assets.py`
- Modify: `service/tests/test_financial_preassessment_demo_assets.py`

**Interfaces:**
- Produces: `asset_relative_path -> material_key` 的静态映射和规则要求 `{rule_id, material_key, label}`。

- [ ] **Step 1: 写失败测试**

```python
assert manifest["assets"][0]["material_key"] == "income_statement"
assert "score" not in manifest["requirements"][0]
```

- [ ] **Step 2: 运行 RED**

Run: `service/.venv/Scripts/python.exe -m pytest service/tests/test_financial_preassessment_demo_assets.py -q -p no:cacheprovider`

Expected: FAIL，因为导入清单尚不存在。

- [ ] **Step 3: 最小实现**

```json
{"assets":[{"relative_path":"客户模拟资料/收入情况说明.pdf","material_key":"income_statement"}],"requirements":[{"rule_id":"demo-bank-a-income","material_key":"income_statement","label":"收入情况说明"}]}
```

- [ ] **Step 4: 运行 GREEN**

Run: `service/.venv/Scripts/python.exe -m pytest service/tests/test_financial_preassessment_demo_assets.py -q -p no:cacheprovider`

Expected: PASS，并确认清单不包含最终评分字段。

### Task 2: FinanceDemoRagPort 真实解析与确定性匹配

**Files:**
- Create: `control_plane/app/finance_demo_rag.py`
- Create: `control_plane/tests/test_finance_demo_rag_bridge.py`

**Interfaces:**
- Consumes: `RagPort.assess_versions(actor, asset_versions, rule_version, query_subject)`。
- Produces: `AssessmentResult(match_score, result_level, missing_materials, citations)`。

- [ ] **Step 1: 写失败测试**

```python
result = port.assess_versions(actor, (active_version,), rule_version, "demo")
assert result.match_score == 100
assert result.citations[0]["asset_version_id"] == active_version.asset_version_id
```

- [ ] **Step 2: 运行 RED**

Run: `service/.venv/Scripts/python.exe -m pytest control_plane/tests/test_finance_demo_rag_bridge.py -q -p no:cacheprovider`

Expected: FAIL，因为真实受控样例端口尚不存在。

- [ ] **Step 3: 最小实现**

```python
class FinanceDemoRagPort:
    def assess_versions(self, actor, asset_versions, rule_version, query_subject):
        scope = self._scope_for(actor, asset_versions, rule_version)
        facts = self._facts_from_manifest(scope.allowed_active_versions)
        return self._to_assessment_result(self._matching.match(scope, facts))
```

- [ ] **Step 4: 运行 GREEN**

Run: `service/.venv/Scripts/python.exe -m pytest control_plane/tests/test_finance_demo_rag_bridge.py -q -p no:cacheprovider`

Expected: PASS；PDF/DOCX 解析出的资料引用绑定 active AssetVersion 和 page/paragraph。

### Task 3: 权限拒绝与主项目 BFF 集成

**Files:**
- Modify: `control_plane/tests/test_v2_rules_assessment.py`
- Modify: `control_plane/tests/conftest.py`

**Interfaces:**
- Consumes: 控制面 `/api/assessments` 的可信 session 与 PermissionGrant。
- Produces: 授权时的 AssessmentReport；拒绝时 403 且 RAG 零调用。

- [ ] **Step 1: 写失败测试**

```python
assert response.status_code == 403
assert finance_demo_rag_port.fact_index_calls == 0
```

- [ ] **Step 2: 运行 RED**

Run: `service/.venv/Scripts/python.exe -m pytest control_plane/tests/test_v2_rules_assessment.py -q -p no:cacheprovider`

Expected: FAIL，因为 fixture 尚未接真实 FinanceDemoRagPort。

- [ ] **Step 3: 最小实现**

```python
app = create_app(..., rag_port=finance_demo_rag_port, ...)
```

- [ ] **Step 4: 运行 GREEN 与回归**

Run: `service/.venv/Scripts/python.exe -m pytest control_plane/tests service/tests -q -p no:cacheprovider`

Expected: PASS；DENY 不触达事实索引、评分、解释或引用。
