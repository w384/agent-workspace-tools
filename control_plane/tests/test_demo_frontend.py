from pathlib import Path


STATIC = Path(__file__).resolve().parents[1] / "static"


def _body(client, path: str) -> str:
    response = client.get(path)
    assert response.status_code == 200, path
    return response.content.decode("utf-8", errors="ignore")


def test_demo_index_served_at_demo_entry(client) -> None:
    body = _body(client, "/demo/")
    assert "资料预评估" in body
    assert "知识库问答" in body
    assert "免责声明" in body


def test_demo_assets_are_served(client) -> None:
    assert "/api/session/login" in _body(client, "/demo/app.js")
    assert "--accent" in _body(client, "/demo/style.css")


def test_demo_frontend_does_not_leak_credentials_or_keys(client) -> None:
    # The api_key request field name is intentional in app.js (the DeepSeek
    # key is typed at runtime and sent to the BFF); no other credential names
    # or secret values may appear anywhere in the static demo files.
    for path in ("/demo/", "/demo/app.js", "/demo/style.css"):
        body = _body(client, path).lower()
        assert "internal_service_key" not in body
        assert "authorization" not in body
        assert "secret" not in body
    for path in ("/demo/", "/demo/style.css"):
        body = _body(client, path).lower()
        assert "api_key" not in body


def test_demo_frontend_never_bakes_a_real_api_key(client) -> None:
    body = _body(client, "/demo/app.js")
    # app.js references the BFF request field name but never a concrete value.
    assert "api_key: key" in body
    assert "sk-" not in body


def test_demo_frontend_does_not_leak_llm_credential_names(client) -> None:
    for path in ("/demo/", "/demo/app.js", "/demo/style.css"):
        body = _body(client, path).lower()
        assert "llm_api_key" not in body
        assert "llm_base_url" not in body
        assert "llm_model" not in body
        assert "authorization: bearer" not in body


def test_demo_frontend_hides_local_filesystem_paths(client) -> None:
    for path in ("/demo/", "/demo/app.js", "/demo/style.css"):
        body = _body(client, path)
        assert "D:" not in body
        assert "C:" not in body
        assert str(STATIC).replace("\\", "/") not in body


def test_demo_frontend_does_not_hardcode_rule_fingerprint(client) -> None:
    body = _body(client, "/demo/app.js")
    assert "sha256:rule-demo-v1" not in body
