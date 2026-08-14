import hashlib
import hmac
import secrets
from dataclasses import dataclass
from typing import Mapping
from uuid import uuid4

from .domain import TrustedActorContext


@dataclass(frozen=True, slots=True)
class DemoIdentity:
    username: str
    password: str
    actor_id: str
    workspace_id: str
    context_version: str
    group_ids: frozenset[str] = frozenset()
    role_ids: frozenset[str] = frozenset()


@dataclass(frozen=True, slots=True)
class _StoredSession:
    session_id: str
    run_id: str
    actor_id: str
    workspace_id: str
    context_version: str
    group_ids: frozenset[str]
    role_ids: frozenset[str]


class ServerSessionStore:
    """Keep server-side actor state while cookies carry only random bearers."""

    def __init__(self) -> None:
        self._sessions: dict[str, _StoredSession] = {}

    def create(
        self, identity: DemoIdentity, request_id: str
    ) -> tuple[str, TrustedActorContext]:
        bearer = secrets.token_urlsafe(32)
        stored = _StoredSession(
            session_id=str(uuid4()),
            run_id=str(uuid4()),
            actor_id=identity.actor_id,
            workspace_id=identity.workspace_id,
            context_version=identity.context_version,
            group_ids=identity.group_ids,
            role_ids=identity.role_ids,
        )
        self._sessions[_bearer_digest(bearer)] = stored
        return bearer, _to_actor_context(stored, request_id)

    def resolve(self, bearer: str | None, request_id: str) -> TrustedActorContext | None:
        if not bearer:
            return None
        stored = self._sessions.get(_bearer_digest(bearer))
        if stored is None:
            return None
        return _to_actor_context(stored, request_id)

    def revoke(self, bearer: str | None) -> None:
        if bearer:
            self._sessions.pop(_bearer_digest(bearer), None)


def authenticate_demo_identity(
    identities: Mapping[str, DemoIdentity], username: str, password: str
) -> DemoIdentity | None:
    identity = identities.get(username)
    if identity is None:
        hmac.compare_digest(password, "")
        return None
    username_matches = hmac.compare_digest(username, identity.username)
    password_matches = hmac.compare_digest(password, identity.password)
    return identity if username_matches and password_matches else None


def _bearer_digest(bearer: str) -> str:
    return hashlib.sha256(bearer.encode("utf-8")).hexdigest()


def _to_actor_context(
    stored: _StoredSession, request_id: str
) -> TrustedActorContext:
    return TrustedActorContext(
        actor_id=stored.actor_id,
        workspace_id=stored.workspace_id,
        context_version=stored.context_version,
        session_id=stored.session_id,
        request_id=request_id,
        run_id=stored.run_id,
        group_ids=stored.group_ids,
        role_ids=stored.role_ids,
    )

