from pathlib import Path


STATIC = Path(__file__).resolve().parents[1] / "static"


def _body(client, path: str) -> str:
    response = client.get(path)
    assert response.status_code == 200, path
    return response.content.decode("utf-8", errors="ignore")


def test_demo_frontend_renders_structured_report(client) -> None:
    body = _body(client, "/demo/app.js")
    assert "示例银行名为虚构脱敏，非真实银行推荐" in body
    assert "bank_label" in body
    assert "missing_materials" in body
    assert "report-kv" in body
    assert "citation-item" in body
    assert "查询主体" not in body


def test_demo_frontend_renders_zero_evidence_denied_summary(client) -> None:
    body = _body(client, "/demo/app.js")
    assert "评估被拒绝" in body
    assert "llm_invoked" in body
    assert "零调用" in body
    assert "retrieved_count" in body


def test_demo_frontend_controlled_file_picker(client) -> None:
    index = _body(client, "/demo/")
    assert 'id="demo-file-picker"' in index
    assert "受控文件选择" in index
    assert "import-manifest 受控样例" in index
    app_js = _body(client, "/demo/app.js")
    assert "CONTROLLED_SAMPLE_FILES" in app_js
    assert "收入情况说明.pdf" in app_js
    assert "任意上传会被底层拒绝" in app_js


def test_demo_frontend_green_theme(client) -> None:
    css = _body(client, "/demo/style.css")
    assert "--accent: #16a34a" in css
    assert "--accent-soft" in css
    assert "report-card" in css
    assert "denied-title" in css


def test_demo_frontend_p1_auto_trigger_hides_asset_ids(client) -> None:
    index = _body(client, "/demo/")
    # asset id / rule version id inputs are removed for the P1 auto-trigger flow
    assert 'name="asset_ids"' not in index
    assert 'name="asset_id"' not in index
    assert 'name="rule_version_id"' not in index
    # hidden fields carry the controlled file names to the BFF
    assert 'name="file_names"' in index
    assert 'name="file_name"' in index
    # qa panel has its own controlled file picker
    assert 'id="qa-file-picker"' in index


def test_demo_frontend_logout_clears_previous_report(client) -> None:
    # 登出后切换身份登录时，不应残留上一用户生成的评估报告/问答结果。
    # 修复合入后，logout 必须清空两个结果区、重置文件选择器并切回默认 tab，
    # 避免跨身份看到旧报告/已选文件/停留页面（纯前端残留）。
    app_js = _body(client, "/demo/app.js")
    # logout 中应存在对两个结果区的清空调用
    assert 'if (ar) ar.replaceChildren()' in app_js
    assert 'if (qr) qr.replaceChildren()' in app_js
    # logout 中应重置两个受控文件选择器（待上传状态，而非已选文件说明）
    assert "resetControlledFilePickers()" in app_js
    assert '$("#demo-file-picker")' in app_js
    assert '$("#qa-file-picker")' in app_js
    assert '"未选择文件。"' in app_js
    # logout 中应切回默认「资料预评估」tab
    assert 'activateTab("assessment")' in app_js


def test_demo_frontend_p1_bff_endpoints_used(client) -> None:
    app_js = _body(client, "/demo/app.js")
    assert "/api/controlled-sample/assess" in app_js
    assert "/api/controlled-sample/query" in app_js
    # button-trigger wording（评估与问答都改为点按钮发起）
    assert "点击「提问」开始分析" in app_js
    assert "点击「生成预评估报告」开始分析" in app_js
    # old hand-typed asset id flow is gone
    assert "asset_ids" not in app_js
    assert "rule_version_id" not in app_js


def test_demo_frontend_p1_no_rule_creation_ui(client) -> None:
    index = _body(client, "/demo/")
    assert 'id="create-rule"' not in index
    app_js = _body(client, "/demo/app.js")
    assert "createRuleVersion" not in app_js
    assert "rule-sets" not in app_js

def test_demo_frontend_p1_scenario_hidden(client) -> None:
    index = _body(client, "/demo/")
    # scenario / query_subject are fixed for the demo; visible inputs removed
    assert '<input type="hidden" name="scenario"' in index
    assert '<input type="hidden" name="query_subject"' in index
    assert 'name="asset_ids"' not in index


def test_demo_frontend_user_area_and_logout(client) -> None:
    index = _body(client, "/demo/")
    assert 'id="user-area"' in index
    assert 'id="user-avatar"' in index
    assert 'id="user-chip"' in index
    assert 'id="logout-btn"' in index
    assert 'id="logout-tip"' in index
    app_js = _body(client, "/demo/app.js")
    assert "renderUserChip" in app_js
    assert "charAt(0).toUpperCase" in app_js
    assert "/api/session/logout" in app_js


def test_demo_frontend_assess_button_below_picker(client) -> None:
    index = _body(client, "/demo/")
    # 提交按钮在文件选择器之后
    picker_pos = index.find('id="demo-file-picker"')
    btn_pos = index.find('type="submit"', picker_pos)
    assert picker_pos != -1
    assert btn_pos != -1
    assert btn_pos > picker_pos
    assert "生成预评估报告" in index


def test_demo_frontend_report_trimmed(client) -> None:
    app_js = _body(client, "/demo/app.js")
    # 精简展示：去掉查询主体/规则版本证据，保留匹配度/结果级别/缺失材料
    assert "rule_version_evidence" not in app_js
    assert "查询主体" not in app_js
    assert "匹配度" in app_js
    assert "缺失材料" in app_js


def test_demo_frontend_login_panel_centered(client) -> None:
    css = _body(client, "/demo/style.css")
    assert "#login-panel" in css
    assert "max-width: 640px" in css


def test_demo_frontend_candidate_banks_rendering(client) -> None:
    app_js = _body(client, "/demo/app.js")
    assert "candidate_banks" in app_js
    assert "可匹配示例银行" in app_js
    assert "candidate-bank-label" in app_js
    assert "candidate-bank" in app_js
    assert "candidate.match_score" in app_js
    assert "candidate.result_level" in app_js
    assert "candidate.missing_materials" in app_js


def test_demo_static_assets_are_not_cached(client) -> None:
    """Demo static assets must not be browser-cached, or frontend updates stay
    invisible (stale app.js via ETag/304) in the in-app browser."""
    response = client.get("/demo/app.js")
    assert response.status_code == 200
    headers = response.headers
    assert headers.get("cache-control", "").startswith("no-store")
    assert "no-cache" in headers.get("cache-control", "")
    assert headers.get("pragma") == "no-cache"


def test_demo_frontend_qa_model_name_and_target_bar(client) -> None:
    # 常驻指示条：告诉用户「接下来提问谁」，杜绝两区选择困惑
    index = _body(client, "/demo/")
    assert 'id="qa-current-target"' in index
    assert "尚未选择文件，请上传真实材料或选择受控样例" in index
    app_js = _body(client, "/demo/app.js")
    assert "updateQaCurrentTarget" in app_js
    assert "当前将提问：" in app_js
    # 登出清空云端 Key 并回退本地模型
    assert "resetModelUi" in app_js
    # 问答回答卡片展示真实调用模型名
    assert "currentModelLabel" in app_js
    assert '["模型", currentModelLabel]' in app_js
    # 409 文案拆分：本人上传 vs 可能其他账号（不再无条件承诺「可直接提问」）
    assert "该文件本会话已上传过，已自动选中，可直接提问" in app_js
    assert "可能是其他账号上传，你未必有访问权限" in app_js
    # DENIED 卡片文案：主文案给结论，副文案给下一步
    assert "你没有访问该文件的权限" in app_js
    assert "该文件由其他账号上传，仅上传者有权检索" in app_js
    assert "可改用受控样例文件体验问答" in app_js
