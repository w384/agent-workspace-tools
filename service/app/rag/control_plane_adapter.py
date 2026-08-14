"""Read-only bridge from the control-plane authority to RAG ports."""

from control_plane.app.domain import Action, DecisionState, TrustedActorContext
from control_plane.app.policy import evaluate_authorization
from control_plane.app.repository import ControlPlaneRepository

from service.app.rag.contracts import (
    ActiveAssetVersion,
    AssetReference,
    PermissionContext,
    RetrievalScope,
)


class ControlPlaneRetrievalAdapter:
    """Resolve RAG scope from one trusted BFF actor, never raw client identity."""

    def __init__(
        self,
        *,
        repository: ControlPlaneRepository,
        actor: TrustedActorContext,
    ) -> None:
        self._repository = repository
        self._actor = actor

    def resolve_retrieval_scope(
        self,
        context: PermissionContext,
    ) -> RetrievalScope:
        self._require_trusted_context(context)
        grants = self._repository.list_permission_grants(self._actor)
        allowed_active_versions: list[ActiveAssetVersion] = []
        denied_asset_ids: set[str] = set()

        for asset in self._repository.list_assets(self._actor.workspace_id):
            if asset.active_version_id is None:
                continue
            try:
                version = self._repository.get_asset_version(asset.active_version_id)
            except KeyError:
                continue
            if (
                version.asset_id != asset.asset_id
                or version.index_state != "ready"
            ):
                continue

            decision = evaluate_authorization(
                self._actor,
                grants,
                Action.QUERY,
                paths=(asset.path,),
            )
            if decision.state is DecisionState.DENY:
                denied_asset_ids.add(asset.asset_id)
                continue
            allowed_active_versions.append(
                ActiveAssetVersion(
                    asset_id=asset.asset_id,
                    asset_version_id=version.asset_version_id,
                )
            )

        return RetrievalScope(
            tenant_id=self._actor.workspace_id,
            allowed_active_versions=tuple(allowed_active_versions),
            denied_asset_ids=frozenset(denied_asset_ids),
        )

    def get_asset_reference(
        self,
        *,
        tenant_id: str,
        asset_id: str,
        asset_version_id: str,
    ) -> AssetReference:
        if tenant_id != self._actor.workspace_id:
            raise PermissionError("retrieval asset reference rejected")
        try:
            asset = self._repository.get_asset(asset_id)
            version = self._repository.get_asset_version(asset_version_id)
        except KeyError as error:
            raise PermissionError("retrieval asset reference rejected") from error
        if (
            asset.workspace_id != self._actor.workspace_id
            or asset.active_version_id != asset_version_id
            or version.asset_id != asset_id
            or version.index_state != "ready"
        ):
            raise PermissionError("retrieval asset reference rejected")
        return AssetReference(
            asset_id=asset.asset_id,
            asset_version_id=version.asset_version_id,
            current_path=asset.path,
            version_path=version.source_path,
        )

    def _require_trusted_context(self, context: PermissionContext) -> None:
        if (
            context.tenant_id != self._actor.workspace_id
            or context.principal_id != self._actor.actor_id
            or frozenset(context.group_ids) != self._actor.group_ids
            or context.session_id != self._actor.session_id
            or context.request_id != self._actor.request_id
        ):
            raise PermissionError("untrusted retrieval context")
