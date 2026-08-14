from collections.abc import Callable, Iterable, Sequence
from typing import Protocol

from service.app.rag.contracts import (
    ActiveAssetVersion,
    Chunk,
    RetrievalFilter,
    SearchHit,
)


class SearchIndex(Protocol):
    """Read-only port for a filtered, rebuildable search replica."""

    def search(
        self,
        *,
        question: str,
        retrieval_filter: RetrievalFilter,
        limit: int,
    ) -> Sequence[SearchHit]: ...


class InMemorySearchIndex:
    """Disposable demo replica; never an Asset or ACL authority."""

    def __init__(
        self,
        *,
        scorer: Callable[[str, Chunk], float],
    ) -> None:
        self._scorer = scorer
        self._chunks: tuple[Chunk, ...] = ()

    def rebuild(self, chunks: Iterable[Chunk]) -> None:
        """Replace the replica from an authoritative chunk snapshot."""
        self._chunks = tuple(chunks)

    def replace_version(
        self,
        *,
        tenant_id: str,
        active_version: ActiveAssetVersion,
        chunks: Iterable[Chunk],
    ) -> None:
        """Atomically replace one exact tenant/asset/version slice."""
        replacement = tuple(chunks)
        if any(
            not _matches_version(
                chunk,
                tenant_id=tenant_id,
                active_version=active_version,
            )
            for chunk in replacement
        ):
            raise ValueError(
                "replacement chunks do not match the target version"
            )

        retained = tuple(
            chunk
            for chunk in self._chunks
            if not _matches_version(
                chunk,
                tenant_id=tenant_id,
                active_version=active_version,
            )
        )
        self._chunks = retained + replacement

    def delete_version(
        self,
        *,
        tenant_id: str,
        active_version: ActiveAssetVersion,
    ) -> int:
        """Delete only one exact tenant/asset/version slice."""
        retained = tuple(
            chunk
            for chunk in self._chunks
            if not _matches_version(
                chunk,
                tenant_id=tenant_id,
                active_version=active_version,
            )
        )
        removed_count = len(self._chunks) - len(retained)
        self._chunks = retained
        return removed_count

    def search(
        self,
        *,
        question: str,
        retrieval_filter: RetrievalFilter,
        limit: int,
    ) -> tuple[SearchHit, ...]:
        if limit <= 0:
            return ()

        allowed_pairs = frozenset(
            (
                item.asset_id,
                item.asset_version_id,
            )
            for item in (
                retrieval_filter.allowed_active_versions
            )
        )
        denied_asset_ids = frozenset(
            retrieval_filter.denied_asset_ids
        )
        hits = (
            SearchHit(
                chunk=chunk,
                score=self._scorer(question, chunk),
            )
            for chunk in self._chunks
            if chunk.tenant_id == retrieval_filter.tenant_id
            and (
                chunk.asset_id,
                chunk.asset_version_id,
            ) in allowed_pairs
            and chunk.asset_id not in denied_asset_ids
        )
        return tuple(
            sorted(
                hits,
                key=lambda hit: (
                    -hit.score,
                    hit.chunk.chunk_id,
                ),
            )[: max(0, limit)]
        )


def _matches_version(
    chunk: Chunk,
    *,
    tenant_id: str,
    active_version: ActiveAssetVersion,
) -> bool:
    return (
        chunk.tenant_id == tenant_id
        and chunk.asset_id == active_version.asset_id
        and chunk.asset_version_id
        == active_version.asset_version_id
    )

