import hashlib

import pytest

from control_plane.app.main import create_app


def test_login_sets_hardened_bearer_cookie_but_stores_only_its_digest(client, app) -> None:
    response = client.post(
        "/api/session/login",
        json_body={"username": "alice", "password": "demo-a-password"},
    )

    assert response.status_code == 200
    bearer = client.cookies["cp_session"]
    set_cookie = response.headers["set-cookie"].lower()
    assert "httponly" in set_cookie
    assert "samesite=strict" in set_cookie
    assert bearer not in response.content.decode("utf-8")
    digest = hashlib.sha256(bearer.encode("utf-8")).hexdigest()
    assert set(app.state.session_store._sessions) == {digest}
    assert bearer not in app.state.session_store._sessions


def test_me_uses_only_cookie_actor_and_adds_trusted_correlation_fields(client) -> None:
    login = client.post(
        "/api/session/login",
        headers={"X-User-Id": "user-b", "X-Request-Id": "forged-request"},
        json_body={
            "username": "alice",
            "password": "demo-a-password",
            "user_id": "user-b",
        },
    )
    login_context = login.json()

    response = client.get(
        "/api/session/me",
        params={"user_id": "user-b"},
        headers={"X-User-Id": "user-b", "X-Request-Id": "forged-request"},
        json_body={"user_id": "user-b"},
    )

    assert response.status_code == 200
    context = response.json()
    assert context["actor_id"] == "user-a"
    assert context["workspace_id"] == "workspace-a"
    assert context["context_version"] == "acl_2026_08_13"
    assert context["group_ids"] == ["staff"]
    assert context["role_ids"] == ["role-member-demo"]
    assert context["session_id"] == login_context["session_id"]
    assert context["run_id"] == login_context["run_id"]
    assert context["request_id"] != login_context["request_id"]
    assert context["request_id"] != "forged-request"


def test_protected_route_requires_cookie_and_logout_revokes_server_session(client) -> None:
    unauthenticated = client.get("/api/session/me")
    assert unauthenticated.status_code == 401
    assert unauthenticated.json() == {
        "error": {"code": "authentication_required", "message": "Authentication required"}
    }

    client.post(
        "/api/session/login",
        json_body={"username": "alice", "password": "demo-a-password"},
    )
    bearer = client.cookies["cp_session"]
    logout = client.post("/api/session/logout")
    assert logout.status_code == 204

    after_logout = client.get(
        "/api/session/me", headers={"Cookie": f"cp_session={bearer}"}
    )
    assert after_logout.status_code == 401
    assert after_logout.json()["error"]["code"] == "authentication_required"


def test_demo_login_rejects_bad_credentials_with_structured_error(client) -> None:
    response = client.post(
        "/api/session/login",
        json_body={"username": "alice", "password": "wrong"},
    )

    assert response.status_code == 401
    assert response.json() == {
        "error": {"code": "invalid_credentials", "message": "Invalid credentials"}
    }
    assert "cp_session" not in client.cookies


def test_request_validation_uses_the_common_error_envelope(client) -> None:
    response = client.post(
        "/api/session/login",
        json_body={"username": "alice"},
    )

    assert response.status_code == 422
    assert response.json() == {
        "error": {"code": "request_validation_error", "message": "Invalid request"}
    }


def test_internal_service_key_must_be_injected_non_empty(
    repository, file_executor, rag_port, demo_identities
) -> None:
    with pytest.raises(ValueError, match="internal service key"):
        create_app(
            repository=repository,
            file_executor=file_executor,
            rag_port=rag_port,
            demo_identities=demo_identities,
            internal_service_key="",
            approver_role_id="role-approver-demo",
        )


def test_approver_role_id_must_be_injected_non_empty(
    repository, file_executor, rag_port, demo_identities
) -> None:
    with pytest.raises(ValueError, match="approver_role_id"):
        create_app(
            repository=repository,
            file_executor=file_executor,
            rag_port=rag_port,
            demo_identities=demo_identities,
            internal_service_key="demo-internal-key",
            approver_role_id="",
        )

