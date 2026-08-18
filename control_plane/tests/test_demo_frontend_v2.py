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
    assert "rule_version_evidence" in body


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


def test_demo_frontend_p1_bff_endpoints_used(client) -> None:
    app_js = _body(client, "/demo/app.js")
    assert "/api/controlled-sample/assess" in app_js
    assert "/api/controlled-sample/query" in app_js
    # auto-trigger wording
    assert "选中即自动发起" in app_js
    # old hand-typed asset id flow is gone
    assert "asset_ids" not in app_js
    assert "rule_version_id" not in app_js


def test_demo_frontend_p1_no_rule_creation_ui(client) -> None:
    index = _body(client, "/demo/")
    assert 'id="create-rule"' not in index
    app_js = _body(client, "/demo/app.js")
    assert "createRuleVersion" not in app_js
    assert "rule-sets" not in app_js
