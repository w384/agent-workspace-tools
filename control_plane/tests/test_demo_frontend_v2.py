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
