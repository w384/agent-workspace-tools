import pytest
from typing import get_type_hints

from control_plane.app.domain import (
    Action,
    AssetVersion,
    AuditEvent,
    DecisionState,
    GrantEffect,
    PermissionGrant,
    PrincipalType,
    TrustedActorContext,
)
from control_plane.app.policy import evaluate_authorization
from control_plane.app.repository import InMemoryControlPlaneRepository


def _actor() -> TrustedActorContext:
    return TrustedActorContext(
        actor_id="user-a",
        workspace_id="workspace-a",
        context_version="acl_2026_08_13",
        session_id="session-a",
        request_id="request-a",
        run_id="run-a",
        role_ids=frozenset({"role-member-demo"}),
    )


def _grant(
    action: Action,
    path_prefix: str = "organized",
    effect: GrantEffect = GrantEffect.ALLOW,
) -> PermissionGrant:
    return PermissionGrant(
        grant_id=f"{effect.value}-{action.value}-{path_prefix}",
        workspace_id="workspace-a",
        context_version="acl_2026_08_13",
        principal_type=PrincipalType.USER,
        principal_id="user-a",
        action=action,
        path_prefix=path_prefix,
        effect=effect,
    )


def test_explicit_deny_wins_before_high_risk_escalation() -> None:
    decision = evaluate_authorization(
        actor=_actor(),
        grants=[
            _grant(Action.TRASH),
            _grant(Action.TRASH, "organized/restricted", GrantEffect.DENY),
        ],
        action=Action.TRASH,
        paths=("organized/restricted/payroll.pdf",),
    )

    assert decision.state is DecisionState.DENY
    assert decision.reason == "explicit_deny"


def test_explicit_deny_wins_over_an_earlier_unauthorized_path_in_a_batch() -> None:
    decision = evaluate_authorization(
        actor=_actor(),
        grants=[
            _grant(Action.QUERY),
            _grant(Action.QUERY, "organized/restricted", GrantEffect.DENY),
        ],
        action=Action.QUERY,
        paths=("outside/report.txt", "organized/restricted/payroll.pdf"),
    )

    assert decision.state is DecisionState.DENY
    assert decision.reason == "explicit_deny"


def test_low_risk_upload_is_direct_and_move_is_self_confirm() -> None:
    actor = _actor()
    upload_decision = evaluate_authorization(
        actor, [_grant(Action.UPLOAD)], Action.UPLOAD, ("organized/report.txt",)
    )
    move_decision = evaluate_authorization(
        actor, [_grant(Action.MOVE_RENAME)], Action.MOVE_RENAME, ("organized/report.txt",)
    )

    assert upload_decision.state is DecisionState.DIRECT
    assert move_decision.state is DecisionState.SELF_CONFIRM


def test_authorized_trash_requires_approval_and_folder_creation_requires_self_confirmation() -> None:
    actor = _actor()

    trash_decision = evaluate_authorization(
        actor, [_grant(Action.TRASH)], Action.TRASH, ("organized/report.txt",)
    )
    folder_decision = evaluate_authorization(
        actor, [_grant(Action.CREATE_FOLDER)], Action.CREATE_FOLDER, ("organized/new",)
    )

    assert trash_decision.state is DecisionState.APPROVAL_REQUIRED
    assert folder_decision.state is DecisionState.SELF_CONFIRM


def test_authorized_query_is_direct_but_overwrite_upload_is_denied() -> None:
    actor = _actor()
    query_decision = evaluate_authorization(
        actor, [_grant(Action.QUERY)], Action.QUERY, ("organized/report.txt",)
    )
    overwrite_decision = evaluate_authorization(
        actor, [_grant(Action.UPLOAD)], Action.UPLOAD, ("organized/report.txt",), overwrite=True
    )

    assert query_decision.state is DecisionState.DIRECT
    assert overwrite_decision.state is DecisionState.DENY
    assert overwrite_decision.reason == "overwrite_not_allowed"


def test_unauthorized_or_invalid_path_is_denied() -> None:
    actor = _actor()
    unauthorized = evaluate_authorization(
        actor, [_grant(Action.QUERY)], Action.QUERY, ("outside/report.txt",)
    )
    invalid = evaluate_authorization(
        actor, [_grant(Action.QUERY)], Action.QUERY, ("organized/../secret.txt",)
    )

    assert unauthorized.state is DecisionState.DENY
    assert unauthorized.reason == "unauthorized_path"
    assert invalid.state is DecisionState.DENY
    assert invalid.reason == "invalid_path"


def test_group_and_role_grants_apply_to_the_trusted_actor() -> None:
    actor = TrustedActorContext(
        actor_id="user-a",
        workspace_id="workspace-a",
        context_version="acl_2026_08_13",
        session_id="session-a",
        request_id="request-a",
        run_id="run-a",
        group_ids=frozenset({"finance"}),
        role_ids=frozenset({"role-approver-demo"}),
    )
    group_decision = evaluate_authorization(
        actor,
        [
            PermissionGrant(
                grant_id="finance-query",
                workspace_id="workspace-a",
                context_version="acl_2026_08_13",
                principal_type=PrincipalType.GROUP,
                principal_id="finance",
                action=Action.QUERY,
                path_prefix="finance",
            )
        ],
        Action.QUERY,
        ("finance/budget.xlsx",),
    )

    assert group_decision.state is DecisionState.DIRECT


def test_authorization_rejects_a_grant_from_another_workspace_or_context_version() -> None:
    actor = _actor()
    other_workspace = PermissionGrant(
        grant_id="other-workspace",
        workspace_id="workspace-b",
        context_version="acl_2026_08_13",
        principal_type=PrincipalType.USER,
        principal_id="user-a",
        action=Action.QUERY,
        path_prefix="organized",
    )
    stale_context = PermissionGrant(
        grant_id="stale-context",
        workspace_id="workspace-a",
        context_version="acl_stale",
        principal_type=PrincipalType.USER,
        principal_id="user-a",
        action=Action.QUERY,
        path_prefix="organized",
    )

    for grant in (other_workspace, stale_context):
        decision = evaluate_authorization(actor, [grant], Action.QUERY, ("organized/report.txt",))
        assert decision.state is DecisionState.DENY
        assert decision.reason == "unauthorized_path"


def test_in_memory_repository_preserves_domain_records_for_later_api_tests() -> None:
    repo = InMemoryControlPlaneRepository()
    grant = _grant(Action.QUERY)

    repo.add_permission_grant(grant)

    assert repo.list_permission_grants(_actor()) == [grant]


def test_in_memory_repository_keeps_explicitly_active_v1_when_v2_fails() -> None:
    repo = InMemoryControlPlaneRepository()
    asset = repo.get_or_create_asset(
        workspace_id="workspace-a",
        path="organized/report.txt",
        name="report.txt",
        created_by="user-a",
    )
    v1 = repo.create_asset_version(
        asset_id=asset.asset_id,
        content_fingerprint="sha256:v1",
        source_path="organized/report.txt",
    )
    repo.transition_asset_version(v1.asset_version_id, "parsing")
    repo.transition_asset_version(v1.asset_version_id, "indexed")
    repo.transition_asset_version(v1.asset_version_id, "ready")
    repo.activate_asset_version(v1.asset_version_id)
    v2 = repo.create_asset_version(
        asset_id=asset.asset_id,
        content_fingerprint="sha256:v2",
        source_path="organized/report.txt",
    )
    failed_v2 = repo.transition_asset_version(v2.asset_version_id, "failed", "parse_error")

    assert failed_v2.failure_code == "parse_error"
    assert repo.get_asset(asset.asset_id).active_version_id == v1.asset_version_id


def test_in_memory_repository_only_activates_a_ready_version_and_appends_audit_events() -> None:
    repo = InMemoryControlPlaneRepository()
    asset = repo.get_or_create_asset("workspace-a", "organized/report.txt", "report.txt", "user-a")
    version = repo.create_asset_version(asset.asset_id, "sha256:v1", "organized/report.txt")

    assert repo.activate_asset_version(version.asset_version_id) is None
    repo.transition_asset_version(version.asset_version_id, "parsing")
    repo.transition_asset_version(version.asset_version_id, "indexed")
    repo.transition_asset_version(version.asset_version_id, "ready")
    assert repo.get_asset(asset.asset_id).active_version_id is None
    assert repo.activate_asset_version(version.asset_version_id) is not None
    assert repo.get_asset(asset.asset_id).active_version_id == version.asset_version_id

    event = AuditEvent("event-1", "asset.created", "user-a", "request-1", "run-1")
    repo.append_audit_event(event)
    assert repo.list_audit_events() == [event]


def test_ready_v2_does_not_replace_explicitly_active_v1_until_activated() -> None:
    repo = InMemoryControlPlaneRepository()
    asset = repo.get_or_create_asset("workspace-a", "organized/report.txt", "report.txt", "user-a")
    v1 = repo.create_asset_version(asset.asset_id, "sha256:v1", "organized/report.txt")
    for state in ("parsing", "indexed", "ready"):
        repo.transition_asset_version(v1.asset_version_id, state)
    repo.activate_asset_version(v1.asset_version_id)
    v2 = repo.create_asset_version(asset.asset_id, "sha256:v2", "organized/report.txt")
    for state in ("parsing", "indexed", "ready"):
        repo.transition_asset_version(v2.asset_version_id, state)

    assert repo.get_asset(asset.asset_id).active_version_id == v1.asset_version_id
    repo.activate_asset_version(v2.asset_version_id)
    assert repo.get_asset(asset.asset_id).active_version_id == v2.asset_version_id


def test_context_version_is_an_opaque_string() -> None:
    actor = _actor()

    assert actor.context_version == "acl_2026_08_13"
    assert isinstance(actor.context_version, str)
    assert get_type_hints(TrustedActorContext)["context_version"] is str
    assert get_type_hints(PermissionGrant)["context_version"] is str


@pytest.mark.parametrize("field_name", ("session_id", "request_id", "run_id"))
def test_trusted_actor_rejects_empty_correlation_fields(field_name: str) -> None:
    values = {
        "actor_id": "user-a",
        "workspace_id": "workspace-a",
        "context_version": "acl_2026_08_13",
        "session_id": "session-a",
        "request_id": "request-a",
        "run_id": "run-a",
        "role_ids": frozenset({"role-member-demo"}),
    }
    values[field_name] = ""

    with pytest.raises(ValueError, match=f"{field_name} must be non-empty"):
        TrustedActorContext(**values)


def test_trusted_actor_rejects_empty_role_ids() -> None:
    with pytest.raises(ValueError, match="role_ids must be non-empty"):
        TrustedActorContext(
            actor_id="user-a",
            workspace_id="workspace-a",
            context_version="acl_2026_08_13",
            session_id="session-a",
            request_id="request-a",
            run_id="run-a",
            role_ids=frozenset(),
        )


def test_asset_version_rejects_skips_backwards_moves_and_terminal_transitions() -> None:
    repo = InMemoryControlPlaneRepository()
    asset = repo.get_or_create_asset("workspace-a", "organized/report.txt", "report.txt", "user-a")
    version = repo.create_asset_version(asset.asset_id, "sha256:v1", "organized/report.txt")

    for state in ("ready", "indexed"):
        try:
            repo.transition_asset_version(version.asset_version_id, state)
        except ValueError:
            pass
        else:
            raise AssertionError(f"queued -> {state} must be rejected")

    repo.transition_asset_version(version.asset_version_id, "parsing")
    repo.transition_asset_version(version.asset_version_id, "indexed")
    repo.transition_asset_version(version.asset_version_id, "ready")

    for state in ("failed", "indexed"):
        try:
            repo.transition_asset_version(version.asset_version_id, state, "late" if state == "failed" else None)
        except ValueError:
            pass
        else:
            raise AssertionError(f"ready -> {state} must be rejected")


def test_non_ready_version_can_fail_only_with_a_failure_code_and_failed_is_terminal() -> None:
    repo = InMemoryControlPlaneRepository()
    asset = repo.get_or_create_asset("workspace-a", "organized/report.txt", "report.txt", "user-a")
    version = repo.create_asset_version(asset.asset_id, "sha256:v1", "organized/report.txt")

    try:
        repo.transition_asset_version(version.asset_version_id, "failed")
    except ValueError:
        pass
    else:
        raise AssertionError("failed state requires a failure code")

    failed = repo.transition_asset_version(version.asset_version_id, "failed", "parse_error")
    assert failed.failure_code == "parse_error"
    try:
        repo.transition_asset_version(version.asset_version_id, "parsing")
    except ValueError:
        pass
    else:
        raise AssertionError("failed is terminal")

