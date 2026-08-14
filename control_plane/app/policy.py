from pathlib import PurePosixPath
from typing import Iterable

from .domain import (
    Action,
    AuthorizationDecision,
    DecisionState,
    GrantEffect,
    PermissionGrant,
    PrincipalType,
    TrustedActorContext,
)


def evaluate_authorization(
    actor: TrustedActorContext,
    grants: Iterable[PermissionGrant],
    action: Action,
    paths: tuple[str, ...],
    overwrite: bool = False,
) -> AuthorizationDecision:
    """Apply the frozen v1 authorization and risk-state policy."""
    normalized_paths = tuple(_normalize_path(path) for path in paths)
    if not normalized_paths or any(path is None for path in normalized_paths):
        return AuthorizationDecision(DecisionState.DENY, "invalid_path")
    if action is Action.UPLOAD and overwrite:
        return AuthorizationDecision(DecisionState.DENY, "overwrite_not_allowed")

    applicable_grants = tuple(
        grant
        for grant in grants
        if _matches_principal(actor, grant)
        and grant.workspace_id == actor.workspace_id
        and grant.context_version == actor.context_version
    )
    grants_by_path = []
    for path in normalized_paths:
        path_grants = tuple(
            grant
            for grant in applicable_grants
            if grant.action is action and _path_is_within(path, grant.path_prefix)
        )
        grants_by_path.append(path_grants)
    if any(
        grant.effect is GrantEffect.DENY
        for path_grants in grants_by_path
        for grant in path_grants
    ):
        return AuthorizationDecision(DecisionState.DENY, "explicit_deny")
    if any(
        not any(grant.effect is GrantEffect.ALLOW for grant in path_grants)
        for path_grants in grants_by_path
    ):
        return AuthorizationDecision(DecisionState.DENY, "unauthorized_path")

    if action is Action.TRASH:
        return AuthorizationDecision(DecisionState.APPROVAL_REQUIRED, "high_risk_trash")
    if action in {Action.MOVE_RENAME, Action.CREATE_FOLDER}:
        return AuthorizationDecision(DecisionState.SELF_CONFIRM, "self_confirmation_required")
    return AuthorizationDecision(DecisionState.DIRECT, "authorized")


def _normalize_path(path: str) -> str | None:
    if not isinstance(path, str) or not path or "\\" in path:
        return None
    candidate = PurePosixPath(path)
    if candidate.is_absolute() or any(part in {"", ".", ".."} for part in candidate.parts):
        return None
    return candidate.as_posix()


def _matches_principal(actor: TrustedActorContext, grant: PermissionGrant) -> bool:
    if grant.principal_type is PrincipalType.USER:
        return grant.principal_id == actor.actor_id
    if grant.principal_type is PrincipalType.GROUP:
        return grant.principal_id in actor.group_ids
    return grant.principal_id in actor.role_ids


def _path_is_within(path: str, path_prefix: str) -> bool:
    prefix = _normalize_path(path_prefix)
    return prefix is not None and (path == prefix or path.startswith(f"{prefix}/"))

