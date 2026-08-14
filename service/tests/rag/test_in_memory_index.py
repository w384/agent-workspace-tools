import importlib

import pytest

from service.app.rag.contracts import (
    ActiveAssetVersion,
    Chunk,
    RetrievalFilter,
)


def _load_index_module():
    try:
        return importlib.import_module("service.app.rag.index")
    except ModuleNotFoundError as error:
        pytest.fail(
            f"In-memory RAG index replica is not implemented: {error}"
        )


def _chunk(
    *,
    tenant_id: str,
    asset_id: str,
    asset_version_id: str,
    chunk_id: str,
) -> Chunk:
    return Chunk(
        tenant_id=tenant_id,
        asset_id=asset_id,
        asset_version_id=asset_version_id,
        chunk_id=chunk_id,
        ordinal=0,
        text=f"text for {chunk_id}",
        page_number=1,
        paragraph_index=None,
        parser_version="parser-v1",
        embedding_version="embedding-v1",
        index_version="index-v1",
    )


def test_index_filters_tenant_deny_and_atomic_pairs_before_scoring():
    """Unauthorized points must never reach even the scoring callback."""
    index_module = _load_index_module()
    chunks = (
        _chunk(
            tenant_id="tenant-demo",
            asset_id="asset-a",
            asset_version_id="version-a-v1",
            chunk_id="allowed-a-v1",
        ),
        _chunk(
            tenant_id="tenant-demo",
            asset_id="asset-b",
            asset_version_id="version-b-v2",
            chunk_id="allowed-b-v2",
        ),
        _chunk(
            tenant_id="tenant-demo",
            asset_id="asset-a",
            asset_version_id="version-b-v2",
            chunk_id="CROSS-PAIR-SENTINEL",
        ),
        _chunk(
            tenant_id="tenant-demo",
            asset_id="asset-denied",
            asset_version_id="version-denied-v1",
            chunk_id="DENIED-SCORER-SENTINEL",
        ),
        _chunk(
            tenant_id="tenant-other",
            asset_id="asset-a",
            asset_version_id="version-a-v1",
            chunk_id="OTHER-TENANT-SENTINEL",
        ),
    )
    scored_chunk_ids = []

    def score(_question, chunk):
        scored_chunk_ids.append(chunk.chunk_id)
        return {
            "allowed-a-v1": 0.91,
            "allowed-b-v2": 0.82,
        }[chunk.chunk_id]

    replica = index_module.InMemorySearchIndex(scorer=score)
    replica.rebuild(chunks)
    hits = replica.search(
        question="approved evidence",
        retrieval_filter=RetrievalFilter(
            tenant_id="tenant-demo",
            allowed_active_versions=(
                ActiveAssetVersion(
                    asset_id="asset-a",
                    asset_version_id="version-a-v1",
                ),
                ActiveAssetVersion(
                    asset_id="asset-b",
                    asset_version_id="version-b-v2",
                ),
                ActiveAssetVersion(
                    asset_id="asset-denied",
                    asset_version_id="version-denied-v1",
                ),
            ),
            denied_asset_ids=("asset-denied",),
        ),
        limit=10,
    )

    assert scored_chunk_ids == ["allowed-a-v1", "allowed-b-v2"]
    assert [hit.chunk.chunk_id for hit in hits] == [
        "allowed-a-v1",
        "allowed-b-v2",
    ]
    serialized = repr((scored_chunk_ids, hits))
    assert "CROSS-PAIR-SENTINEL" not in serialized
    assert "DENIED-SCORER-SENTINEL" not in serialized
    assert "OTHER-TENANT-SENTINEL" not in serialized


def test_replace_delete_and_rebuild_exact_version_preserves_neighbors():
    """Writes must target tenant plus the atomic asset/version pair."""
    index_module = _load_index_module()
    target = ActiveAssetVersion(
        asset_id="asset-a",
        asset_version_id="shared-version-v2",
    )
    target_old = _chunk(
        tenant_id="tenant-demo",
        asset_id=target.asset_id,
        asset_version_id=target.asset_version_id,
        chunk_id="target-old",
    )
    target_replacement = _chunk(
        tenant_id="tenant-demo",
        asset_id=target.asset_id,
        asset_version_id=target.asset_version_id,
        chunk_id="target-replacement",
    )
    target_rebuilt = _chunk(
        tenant_id="tenant-demo",
        asset_id=target.asset_id,
        asset_version_id=target.asset_version_id,
        chunk_id="target-rebuilt",
    )
    same_asset_old_version = _chunk(
        tenant_id="tenant-demo",
        asset_id="asset-a",
        asset_version_id="version-a-v1",
        chunk_id="same-asset-old-version",
    )
    same_tenant_other_asset_same_version = _chunk(
        tenant_id="tenant-demo",
        asset_id="asset-b",
        asset_version_id="shared-version-v2",
        chunk_id="other-asset-same-version",
    )
    other_tenant_same_pair = _chunk(
        tenant_id="tenant-other",
        asset_id=target.asset_id,
        asset_version_id=target.asset_version_id,
        chunk_id="other-tenant-same-pair",
    )
    mismatched_chunk = _chunk(
        tenant_id="tenant-demo",
        asset_id="asset-b",
        asset_version_id=target.asset_version_id,
        chunk_id="mismatched-write",
    )
    scores = {
        "target-old": 0.99,
        "target-replacement": 0.98,
        "target-rebuilt": 0.97,
        "same-asset-old-version": 0.80,
        "other-asset-same-version": 0.70,
        "other-tenant-same-pair": 0.90,
    }
    replica = index_module.InMemorySearchIndex(
        scorer=lambda _question, chunk: scores[chunk.chunk_id]
    )
    replica.rebuild(
        (
            target_old,
            same_asset_old_version,
            same_tenant_other_asset_same_version,
            other_tenant_same_pair,
        )
    )
    tenant_filter = RetrievalFilter(
        tenant_id="tenant-demo",
        allowed_active_versions=(
            target,
            ActiveAssetVersion(
                asset_id="asset-a",
                asset_version_id="version-a-v1",
            ),
            ActiveAssetVersion(
                asset_id="asset-b",
                asset_version_id="shared-version-v2",
            ),
        ),
        denied_asset_ids=(),
    )
    other_tenant_filter = RetrievalFilter(
        tenant_id="tenant-other",
        allowed_active_versions=(target,),
        denied_asset_ids=(),
    )

    with pytest.raises(ValueError):
        replica.replace_version(
            tenant_id="tenant-demo",
            active_version=target,
            chunks=(target_replacement, mismatched_chunk),
        )
    after_invalid_replace = replica.search(
        question="evidence",
        retrieval_filter=tenant_filter,
        limit=10,
    )
    assert [
        hit.chunk.chunk_id for hit in after_invalid_replace
    ] == [
        "target-old",
        "same-asset-old-version",
        "other-asset-same-version",
    ]

    replica.replace_version(
        tenant_id="tenant-demo",
        active_version=target,
        chunks=(target_replacement,),
    )
    after_replace = replica.search(
        question="evidence",
        retrieval_filter=tenant_filter,
        limit=10,
    )
    assert [hit.chunk.chunk_id for hit in after_replace] == [
        "target-replacement",
        "same-asset-old-version",
        "other-asset-same-version",
    ]

    removed_count = replica.delete_version(
        tenant_id="tenant-demo",
        active_version=target,
    )
    after_delete = replica.search(
        question="evidence",
        retrieval_filter=tenant_filter,
        limit=10,
    )
    assert removed_count == 1
    assert [hit.chunk.chunk_id for hit in after_delete] == [
        "same-asset-old-version",
        "other-asset-same-version",
    ]
    other_tenant_after_delete = replica.search(
        question="evidence",
        retrieval_filter=other_tenant_filter,
        limit=10,
    )
    assert [
        hit.chunk.chunk_id for hit in other_tenant_after_delete
    ] == ["other-tenant-same-pair"]

    replica.replace_version(
        tenant_id="tenant-demo",
        active_version=target,
        chunks=(target_rebuilt,),
    )
    after_rebuild = replica.search(
        question="evidence",
        retrieval_filter=tenant_filter,
        limit=10,
    )
    assert [hit.chunk.chunk_id for hit in after_rebuild] == [
        "target-rebuilt",
        "same-asset-old-version",
        "other-asset-same-version",
    ]


@pytest.mark.parametrize("limit", [0, -1])
def test_non_positive_limit_returns_empty_without_scoring(limit):
    """A zero-result request must short-circuit before touching content."""
    index_module = _load_index_module()
    scored_chunk_ids = []

    def score(_question, chunk):
        scored_chunk_ids.append(chunk.chunk_id)
        return 1.0

    replica = index_module.InMemorySearchIndex(scorer=score)
    replica.rebuild(
        (
            _chunk(
                tenant_id="tenant-demo",
                asset_id="asset-a",
                asset_version_id="version-a-v1",
                chunk_id="must-not-be-scored",
            ),
        )
    )
    retrieval_filter = RetrievalFilter(
        tenant_id="tenant-demo",
        allowed_active_versions=(
            ActiveAssetVersion(
                asset_id="asset-a",
                asset_version_id="version-a-v1",
            ),
        ),
        denied_asset_ids=(),
    )

    hits = replica.search(
        question="evidence",
        retrieval_filter=retrieval_filter,
        limit=limit,
    )

    assert hits == ()
    assert scored_chunk_ids == []

