import pytest

from control_plane.app.ports import UploadResult
from control_plane.app.service import ControlPlaneService


def _upload(client, directory: str = "organized", file_name: str = "report.txt"):
    return client.post(
        "/api/uploads",
        params={"user_id": "user-b"},
        headers={"X-User-Id": "user-b", "X-Request-Id": "forged-request"},
        data={"directory": directory, "user_id": "user-b"},
        files={"file": (file_name, b"payload", "text/plain")},
    )


def _set_index_state(client, version_id: str, state: str, failure_code: str | None = None):
    body = {"state": state}
    if failure_code is not None:
        body["failure_code"] = failure_code
    return client.post(
        f"/internal/asset-versions/{version_id}/index-status",
        headers={"X-Internal-Service-Key": "demo-internal-key"},
        json_body=body,
    )


def test_direct_upload_uses_trusted_actor_and_executor_fingerprint_without_rehashing(
    client_as_a, file_executor, rag_port, repository
) -> None:
    response = _upload(client_as_a)

    assert response.status_code == 200
    payload = response.json()
    assert payload["decision"] == {"state": "DIRECT", "reason": "authorized"}
    assert payload["asset"]["path"] == "organized/report.txt"
    assert payload["asset_version"]["index_state"] == "queued"
    assert payload["asset_version"]["content_fingerprint"] == "sha256:executor-digest"
    assert payload["asset"]["active_version_id"] is None

    assert len(file_executor.calls) == 1
    upload_call = file_executor.calls[0]
    assert upload_call.content == b"payload"
    assert upload_call.actor.actor_id == "user-a"
    assert upload_call.actor.role_ids == frozenset({"role-member-demo"})
    assert upload_call.actor.session_id
    assert upload_call.actor.run_id
    assert upload_call.actor.request_id == upload_call.request_id
    assert upload_call.request_id != "forged-request"

    assert len(rag_port.calls) == 1
    enqueue_call = rag_port.calls[0]
    assert enqueue_call.actor == upload_call.actor
    assert enqueue_call.request_id == upload_call.request_id
    assert enqueue_call.asset_version.asset_version_id == payload["asset_version"][
        "asset_version_id"
    ]

    events = repository.list_audit_events()
    assert [event.event_type for event in events] == [
        "upload_authorized",
        "asset_version_created",
    ]
    assert {event.request_id for event in events} == {upload_call.request_id}
    assert payload["audit_event_id"] == events[-1].event_id


def test_denied_upload_has_no_executor_rag_asset_or_version_side_effect(
    client_as_a, file_executor, rag_port, repository
) -> None:
    trusted_session = client_as_a.get("/api/session/me").json()
    response = _upload(client_as_a, directory="private")

    assert response.status_code == 403
    assert response.json() == {
        "error": {"code": "upload_denied", "message": "Upload is not authorized"}
    }
    assert file_executor.calls == []
    assert rag_port.calls == []
    assert repository._assets == {}
    assert repository._asset_versions == {}
    events = repository.list_audit_events()
    assert len(events) == 1
    denied_event = events[0]
    assert denied_event.event_type == "upload_denied"
    assert denied_event.actor_id == "user-a"
    assert denied_event.request_id
    assert denied_event.request_id != "forged-request"
    assert denied_event.run_id == trusted_session["run_id"]
    assert denied_event.details == {
        "action": "upload",
        "decision": "DENY",
        "reason": "unauthorized_path",
    }


def test_known_asset_path_is_denied_before_executor_without_a_new_version(
    client_as_a, file_executor, rag_port, repository
) -> None:
    existing_asset = repository.get_or_create_asset(
        "workspace-a",
        "organized/report.txt",
        "report.txt",
        "user-a",
    )

    response = _upload(client_as_a)

    assert response.status_code == 403
    assert response.json() == {
        "error": {"code": "upload_denied", "message": "Upload is not authorized"}
    }
    assert file_executor.calls == []
    assert rag_port.calls == []
    assert list(repository._assets.values()) == [existing_asset]
    assert repository._asset_versions == {}
    events = repository.list_audit_events()
    assert [event.event_type for event in events] == ["upload_denied"]
    assert events[0].details == {
        "action": "upload",
        "decision": "DENY",
        "reason": "overwrite_not_allowed",
    }


def test_executor_target_conflict_maps_to_stable_conflict_without_asset_version(
    client_as_a, file_executor, rag_port, repository
) -> None:
    file_executor.error = FileExistsError("executor target details")

    response = _upload(client_as_a)

    assert response.status_code == 409
    assert response.json() == {
        "error": {"code": "upload_target_exists", "message": "Upload target already exists"}
    }
    assert len(file_executor.calls) == 1
    assert rag_port.calls == []
    assert repository._assets == {}
    assert repository._asset_versions == {}
    events = repository.list_audit_events()
    assert [event.event_type for event in events] == ["upload_authorized", "upload_failed"]
    assert events[-1].details == {
        "action": "upload",
        "stage": "executor",
        "reason": "target_exists",
    }
    assert "executor target details" not in repr(events)


@pytest.mark.parametrize(
    ("executor_path", "executor_name"),
    (
        ("outside/report.txt", "report.txt"),
        ("organized/report.txt", "other.txt"),
    ),
)
def test_executor_cannot_bind_asset_to_a_target_other_than_the_authorized_final_path(
    client_as_a,
    file_executor,
    rag_port,
    repository,
    executor_path,
    executor_name,
) -> None:
    file_executor.result = UploadResult(
        path=executor_path,
        name=executor_name,
        size_bytes=7,
        content_fingerprint="sha256:executor-digest",
    )

    response = _upload(client_as_a)

    assert response.status_code == 502
    assert response.json() == {
        "error": {
            "code": "executor_result_mismatch",
            "message": "Executor result does not match the authorized upload target",
        }
    }
    assert len(file_executor.calls) == 1
    assert rag_port.calls == []
    assert repository._assets == {}
    assert repository._asset_versions == {}


def test_executor_exception_returns_safe_error_and_appends_sanitized_failure_audit(
    client_as_a, file_executor, rag_port, repository
) -> None:
    file_executor.error = RuntimeError("executor-secret payload")

    response = _upload(client_as_a)

    assert response.status_code == 502
    assert response.json() == {
        "error": {"code": "executor_upload_failed", "message": "File upload failed"}
    }
    assert len(file_executor.calls) == 1
    assert rag_port.calls == []
    assert repository._assets == {}
    assert repository._asset_versions == {}
    events = repository.list_audit_events()
    assert [event.event_type for event in events] == ["upload_authorized", "upload_failed"]
    assert events[-1].details == {
        "action": "upload",
        "stage": "executor",
        "reason": "executor_error",
    }
    assert len({event.request_id for event in events}) == 1
    assert len({event.run_id for event in events}) == 1
    assert "executor-secret" not in repr(events)


def test_rag_exception_fails_queued_version_and_returns_safe_correlated_error(
    client_as_a, file_executor, rag_port, repository
) -> None:
    rag_port.error = RuntimeError("rag-secret payload")

    response = _upload(client_as_a)

    assert response.status_code == 502
    assert response.json() == {
        "error": {"code": "rag_enqueue_failed", "message": "Index enqueue failed"}
    }
    assert len(file_executor.calls) == 1
    assert len(rag_port.calls) == 1
    assert len(repository._assets) == 1
    assert len(repository._asset_versions) == 1
    asset = next(iter(repository._assets.values()))
    version = next(iter(repository._asset_versions.values()))
    assert version.index_state == "failed"
    assert version.failure_code == "index_enqueue_failed"
    assert asset.active_version_id is None
    events = repository.list_audit_events()
    assert [event.event_type for event in events] == [
        "upload_authorized",
        "asset_version_created",
        "asset_version_state_changed",
        "rag_enqueue_failed",
    ]
    assert events[-1].details == {
        "action": "upload",
        "asset_version_id": version.asset_version_id,
        "stage": "rag",
        "reason": "enqueue_failed",
    }
    assert len({event.request_id for event in events}) == 1
    assert len({event.run_id for event in events}) == 1
    assert "rag-secret" not in repr(events)


def test_audit_events_do_not_retain_credentials_bearers_keys_or_upload_content(
    client_as_a, repository
) -> None:
    bearer = client_as_a.cookies["cp_session"]

    response = _upload(client_as_a)

    assert response.status_code == 200
    serialized_events = repr(repository.list_audit_events())
    for sensitive_value in (
        bearer,
        "demo-a-password",
        "demo-internal-key",
        "payload",
    ):
        assert sensitive_value not in serialized_events


def test_denied_upload_audit_never_retains_the_unauthorized_full_path(
    client_as_a, repository
) -> None:
    response = _upload(client_as_a, directory="outside")

    assert response.status_code == 403
    events = repository.list_audit_events()
    assert [event.event_type for event in events] == ["upload_denied"]
    serialized_events = repr(events)
    for sensitive_value in (
        "outside/report.txt",
        "payload",
        client_as_a.cookies["cp_session"],
        "demo-a-password",
        "demo-internal-key",
    ):
        assert sensitive_value not in serialized_events


def test_upload_result_requires_executor_sha256_fingerprint_format() -> None:
    try:
        UploadResult(
            path="organized/report.txt",
            name="report.txt",
            size_bytes=7,
            content_fingerprint="executor-digest",
        )
    except ValueError as error:
        assert str(error) == "content_fingerprint must use sha256:<digest> format"
    else:
        raise AssertionError("an unqualified executor fingerprint must be rejected")


def test_internal_index_callback_requires_service_key_even_with_user_cookie(
    client_as_a,
) -> None:
    uploaded = _upload(client_as_a).json()
    version_id = uploaded["asset_version"]["asset_version_id"]

    response = client_as_a.post(
        f"/internal/asset-versions/{version_id}/index-status",
        headers={"X-Internal-Service-Key": "wrong-key"},
        json_body={"state": "parsing"},
    )

    assert response.status_code == 401
    assert response.json() == {
        "error": {
            "code": "internal_service_unauthorized",
            "message": "Invalid internal service key",
        }
    }


def test_rebuilt_service_restores_callback_request_run_and_actor_from_persisted_audit(
    client_as_a, repository, file_executor, rag_port
) -> None:
    uploaded = _upload(client_as_a).json()
    version_id = uploaded["asset_version"]["asset_version_id"]
    creation_event = repository.find_asset_version_creation_event(version_id)
    assert creation_event is not None
    rebuilt_service = ControlPlaneService(
        repository,
        file_executor,
        rag_port,
        approver_role_id="role-approver-demo",
    )

    rebuilt_service.update_index_state(version_id, "parsing", None)

    state_event = repository.list_audit_events()[-1]
    assert state_event.event_type == "asset_version_state_changed"
    assert state_event.request_id == creation_event.request_id
    assert state_event.run_id == creation_event.run_id
    assert state_event.actor_id == creation_event.actor_id


def test_index_chain_records_correlated_audit_without_implicit_activation_and_failed_v2_keeps_v1(
    client_as_a, repository
) -> None:
    first_upload = _upload(client_as_a).json()
    asset_id = first_upload["asset"]["asset_id"]
    v1_id = first_upload["asset_version"]["asset_version_id"]

    for state in ("parsing", "indexed", "ready"):
        response = _set_index_state(client_as_a, v1_id, state)
        assert response.status_code == 200
        assert response.json()["asset_version"]["index_state"] == state

    assert repository.get_asset(asset_id).active_version_id is None
    repository.activate_asset_version(v1_id)

    v2 = repository.create_asset_version(
        asset_id=asset_id,
        content_fingerprint="sha256:v2",
        source_path="organized/report.txt",
    )
    failed_v2 = repository.transition_asset_version(
        v2.asset_version_id,
        "failed",
        "parse_error",
    )

    assert failed_v2.failure_code == "parse_error"
    assert repository.get_asset(asset_id).active_version_id == v1_id

    events = repository.list_audit_events()
    v1_request_ids = {
        event.request_id
        for event in events
        if event.details.get("asset_version_id") == v1_id
    }
    assert len(v1_request_ids) == 1
    assert sum(event.event_type == "asset_version_state_changed" for event in events) == 3


def test_illegal_index_state_jump_returns_structured_conflict(client_as_a) -> None:
    uploaded = _upload(client_as_a).json()
    version_id = uploaded["asset_version"]["asset_version_id"]

    response = _set_index_state(client_as_a, version_id, "ready")

    assert response.status_code == 409
    assert response.json() == {
        "error": {"code": "invalid_index_transition", "message": "Invalid index transition"}
    }

