import importlib

import pytest

from service.app.rag.contracts import (
    ActiveAssetVersion,
    Chunk,
    PermissionContext,
    RetrievalFilter,
)


def _load_matching_module():
    try:
        return importlib.import_module(
            "service.app.rag.finance_matching"
        )
    except ModuleNotFoundError as error:
        pytest.fail(
            "RAG finance material matching boundary is not "
            f"implemented: {error}"
        )


def test_demo_rule_version_scores_material_match_with_versioned_refs():
    matching = _load_matching_module()
    active_version = ActiveAssetVersion(
        asset_id="asset-finance-demo",
        asset_version_id="version-finance-demo-v1",
    )
    rule_version = matching.RuleVersionSnapshot(
        rule_set_id="ruleset-demo-finance-materials",
        rule_version_id="rule-version-demo-v1",
        version_label="demo-v1",
        source_type=matching.RuleSourceType.DEMO_FIXTURE,
        content_fingerprint="sha256:demo-rules-v1",
        disclaimer="Demo fixture only; not a real bank rule or loan decision.",
        requirements=(
            matching.MaterialRequirement(
                rule_id="rule-balance-sheet",
                material_key="balance_sheet",
                label="Balance sheet",
            ),
            matching.MaterialRequirement(
                rule_id="rule-income-statement",
                material_key="income_statement",
                label="Income statement",
            ),
        ),
        bank_label="示例银行A",
    )
    chunk = Chunk(
        tenant_id="tenant-demo",
        asset_id=active_version.asset_id,
        asset_version_id=active_version.asset_version_id,
        chunk_id="chunk-finance-page-2",
        ordinal=1,
        text="Simulated demo facts: balance sheet and income statement",
        page_number=2,
        paragraph_index=4,
        parser_version="parser-v1",
        embedding_version="embedding-v1",
        index_version="index-v1",
    )

    class ControlPlaneStub:
        def resolve_material_matching_scope(self, context):
            assert context.principal_id == "principal-analyst"
            return matching.MaterialMatchingScope(
                tenant_id="tenant-demo",
                allowed_active_versions=(active_version,),
                denied_asset_ids=frozenset(),
                rule_version=rule_version,
            )

    class FactIndexStub:
        def search(self, *, retrieval_filter, limit):
            assert limit == 5
            assert retrieval_filter == RetrievalFilter(
                tenant_id="tenant-demo",
                allowed_active_versions=(active_version,),
                denied_asset_ids=(),
            )
            return (
                matching.MaterialFactHit(
                    fact=matching.MaterialFact(
                        material_key="balance_sheet", chunk=chunk
                    ),
                    score=0.99,
                ),
                matching.MaterialFactHit(
                    fact=matching.MaterialFact(
                        material_key="income_statement", chunk=chunk
                    ),
                    score=0.98,
                ),
            )

    class ExplanationPortStub:
        def __init__(self):
            self.calls = []

        def explain(self, structured_result):
            self.calls.append(structured_result)
            return "polished explanation"

    explanation_port = ExplanationPortStub()
    result = matching.FinanceMaterialMatchingService(
        control_plane=ControlPlaneStub(),
        fact_index=FactIndexStub(),
        explanation_port=explanation_port,
    ).match(
        context=PermissionContext(
            tenant_id="tenant-demo",
            principal_id="principal-analyst",
            group_ids=("finance-demo",),
            session_id="session-authenticated-by-bff",
            request_id="request-finance-match-001",
        ),
        limit=5,
        include_explanation=True,
    )

    assert result.status == matching.MaterialMatchStatus.MATCH
    assert result.match_score == 100
    assert result.missing_materials == ()
    assert result.bank_label == "示例银行A"
    assert result.retrieved_count == 2
    assert result.llm_invoked is True
    assert result.explanation == "polished explanation"
    assert result.material_citations == (
        matching.MaterialCitation(
            asset_id=active_version.asset_id,
            asset_version_id=active_version.asset_version_id,
            chunk_id="chunk-finance-page-2",
            page_number=2,
            paragraph_index=4,
        ),
    )
    assert result.rule_citations == (
        matching.RuleCitation(
            rule_set_id="ruleset-demo-finance-materials",
            rule_version_id="rule-version-demo-v1",
            rule_id="rule-balance-sheet",
            version_label="demo-v1",
            source_type=matching.RuleSourceType.DEMO_FIXTURE,
            content_fingerprint="sha256:demo-rules-v1",
            disclaimer=rule_version.disclaimer,
        ),
        matching.RuleCitation(
            rule_set_id="ruleset-demo-finance-materials",
            rule_version_id="rule-version-demo-v1",
            rule_id="rule-income-statement",
            version_label="demo-v1",
            source_type=matching.RuleSourceType.DEMO_FIXTURE,
            content_fingerprint="sha256:demo-rules-v1",
            disclaimer=rule_version.disclaimer,
        ),
    )
    assert result.rule_citations[0].source_type.value == "demo_fixture"
    assert len(explanation_port.calls) == 1
    assert explanation_port.calls[0].match_score == 100
    assert explanation_port.calls[0].status == matching.MaterialMatchStatus.MATCH


def test_denied_scope_short_circuits_before_fact_recall_and_explanation():
    matching = _load_matching_module()
    denied_version = ActiveAssetVersion(
        asset_id="asset-denied-finance",
        asset_version_id="version-denied-finance-v1",
    )
    rule_version = matching.RuleVersionSnapshot(
        rule_set_id="ruleset-demo-finance-materials",
        rule_version_id="rule-version-demo-v1",
        version_label="demo-v1",
        source_type=matching.RuleSourceType.DEMO_FIXTURE,
        content_fingerprint="sha256:demo-rules-v1",
        disclaimer="Demo fixture only; no real bank rule.",
        requirements=(
            matching.MaterialRequirement(
                rule_id="rule-balance-sheet",
                material_key="balance_sheet",
                label="Balance sheet",
            ),
        ),
    )

    class ControlPlaneStub:
        def resolve_material_matching_scope(self, _context):
            return matching.MaterialMatchingScope(
                tenant_id="tenant-demo",
                allowed_active_versions=(denied_version,),
                denied_asset_ids=frozenset({"asset-denied-finance"}),
                rule_version=rule_version,
            )

    class FactIndexStub:
        def __init__(self):
            self.call_count = 0

        def search(self, **_kwargs):
            self.call_count += 1
            raise AssertionError("DENIED-CHUNK-SENTINEL must not be recalled")

    class ExplanationPortStub:
        def __init__(self):
            self.call_count = 0

        def explain(self, _structured_result):
            self.call_count += 1
            return "must not be invoked"

    fact_index = FactIndexStub()
    explanation_port = ExplanationPortStub()
    result = matching.FinanceMaterialMatchingService(
        control_plane=ControlPlaneStub(),
        fact_index=fact_index,
        explanation_port=explanation_port,
    ).match(
        context=PermissionContext(
            tenant_id="tenant-demo",
            principal_id="principal-analyst",
            group_ids=("finance-demo",),
            session_id="session-authenticated-by-bff",
            request_id="request-finance-deny-001",
        ),
        limit=5,
        include_explanation=True,
    )

    assert fact_index.call_count == 0
    assert explanation_port.call_count == 0
    assert result.retrieved_count == 0
    assert result.llm_invoked is False
    assert result.material_citations == ()
    assert result.rule_citations == ()
    assert result.match_score == 0
    assert result.explanation is None
    assert result.bank_label is None


@pytest.mark.parametrize(
    ("case_name", "tenant_id", "active_version", "denied_asset_ids"),
    [
        ("cross tenant", "tenant-other", ActiveAssetVersion("asset-finance-demo", "version-finance-demo-v1"), frozenset()),
        ("inactive pair", "tenant-demo", ActiveAssetVersion("asset-finance-demo", "version-finance-demo-old"), frozenset()),
        ("explicit deny", "tenant-demo", ActiveAssetVersion("asset-denied-finance", "version-denied-finance-v1"), frozenset({"asset-denied-finance"})),
    ],
)
def test_fact_index_scope_violations_fail_closed_before_scoring(
    monkeypatch, case_name, tenant_id, active_version, denied_asset_ids
):
    matching = _load_matching_module()
    allowed_version = ActiveAssetVersion("asset-finance-demo", "version-finance-demo-v1")
    denied_version = ActiveAssetVersion("asset-denied-finance", "version-denied-finance-v1")
    rule_version = matching.RuleVersionSnapshot(
        rule_set_id="ruleset-demo-finance-materials",
        rule_version_id="rule-version-demo-v1",
        version_label="demo-v1",
        source_type=matching.RuleSourceType.DEMO_FIXTURE,
        content_fingerprint="sha256:demo-rules-v1",
        disclaimer="Demo fixture only; no real bank rule.",
        requirements=(matching.MaterialRequirement("rule-balance-sheet", "balance_sheet", "Balance sheet"),),
    )
    violating_chunk = Chunk(
        tenant_id=tenant_id,
        asset_id=active_version.asset_id,
        asset_version_id=active_version.asset_version_id,
        chunk_id=f"DENIED-CHUNK-SENTINEL-{case_name}",
        ordinal=0,
        text=f"DENIED-TEXT-SENTINEL-{case_name}",
        page_number=9,
        paragraph_index=7,
        parser_version="parser-v1",
        embedding_version="embedding-v1",
        index_version="index-v1",
    )

    class ControlPlaneStub:
        def resolve_material_matching_scope(self, _context):
            return matching.MaterialMatchingScope(
                tenant_id="tenant-demo",
                allowed_active_versions=(allowed_version, denied_version),
                denied_asset_ids=denied_asset_ids,
                rule_version=rule_version,
            )

    class FactIndexStub:
        def search(self, *, retrieval_filter, limit):
            assert limit == 5
            assert retrieval_filter.allowed_active_versions
            return (matching.MaterialFactHit(matching.MaterialFact("balance_sheet", violating_chunk), 0.99),)

    class ExplanationPortStub:
        def __init__(self):
            self.call_count = 0

        def explain(self, _structured_result):
            self.call_count += 1
            return "must not be invoked"

    score_calls = []
    original_score_matches = matching._score_matches

    def score_spy(*args, **kwargs):
        score_calls.append((args, kwargs))
        return original_score_matches(*args, **kwargs)

    monkeypatch.setattr(matching, "_score_matches", score_spy)
    explanation_port = ExplanationPortStub()
    result = matching.FinanceMaterialMatchingService(
        control_plane=ControlPlaneStub(),
        fact_index=FactIndexStub(),
        explanation_port=explanation_port,
    ).match(
        context=PermissionContext(
            tenant_id="tenant-demo",
            principal_id="principal-analyst",
            group_ids=("finance-demo",),
            session_id="session-authenticated-by-bff",
            request_id=f"request-finance-scope-{case_name}",
        ),
        limit=5,
        include_explanation=True,
    )

    assert score_calls == []
    assert explanation_port.call_count == 0
    assert result.status is None
    assert result.reason == "ACCESS_DENIED"
    assert result.retrieved_count == 0
    assert result.llm_invoked is False
    assert result.material_citations == ()
    assert result.rule_citations == ()
    assert result.match_score == 0
    assert result.bank_label is None
    safe_output = repr((result, explanation_port.call_count))
    assert "DENIED-CHUNK-SENTINEL" not in safe_output
    assert "DENIED-TEXT-SENTINEL" not in safe_output

def test_score_multi_rule_matches_returns_one_result_per_candidate_rule():
    matching = _load_matching_module()
    active_version = ActiveAssetVersion(
        asset_id="asset-finance-demo",
        asset_version_id="version-finance-demo-v1",
    )
    chunk = Chunk(
        tenant_id="tenant-demo",
        asset_id=active_version.asset_id,
        asset_version_id=active_version.asset_version_id,
        chunk_id="chunk-finance-page-2",
        ordinal=1,
        text="Simulated demo facts: balance sheet and income statement",
        page_number=2,
        paragraph_index=4,
        parser_version="parser-v1",
        embedding_version="embedding-v1",
        index_version="index-v1",
    )
    hits = (
        matching.MaterialFactHit(
            matching.MaterialFact("balance_sheet", chunk), 0.99
        ),
        matching.MaterialFactHit(
            matching.MaterialFact("income_statement", chunk), 0.98
        ),
    )
    rules = (
        matching.RuleVersionSnapshot(
            rule_set_id="ruleset-demo-finance-materials",
            rule_version_id="rule-version-demo-v1",
            version_label="demo-v1",
            source_type=matching.RuleSourceType.DEMO_FIXTURE,
            content_fingerprint="sha256:demo-rules-v1",
            disclaimer="Demo fixture only; not a real bank rule.",
            requirements=(
                matching.MaterialRequirement("rule-balance-sheet", "balance_sheet", "Balance sheet"),
                matching.MaterialRequirement("rule-income-statement", "income_statement", "Income statement"),
            ),
            bank_label="示例银行A",
        ),
        matching.RuleVersionSnapshot(
            rule_set_id="ruleset-demo-finance-materials",
            rule_version_id="rule-version-demo-v1",
            version_label="demo-v1",
            source_type=matching.RuleSourceType.DEMO_FIXTURE,
            content_fingerprint="sha256:demo-rules-v1",
            disclaimer="Demo fixture only; not a real bank rule.",
            requirements=(
                matching.MaterialRequirement("rule-cashflow", "cashflow_summary", "Cashflow summary"),
                matching.MaterialRequirement("rule-business", "business_profile", "Business profile"),
            ),
            bank_label="示例银行B",
        ),
    )
    results = matching.score_multi_rule_matches(rule_versions=rules, hits=hits)
    assert len(results) == 2
    assert results[0].bank_label == "示例银行A"
    assert results[0].match_score == 100
    assert results[0].status == matching.MaterialMatchStatus.MATCH
    assert results[0].missing_materials == ()
    assert results[1].bank_label == "示例银行B"
    assert results[1].match_score == 0
    assert results[1].status == matching.MaterialMatchStatus.MISSING_INFO
    assert len(results[1].missing_materials) == 2
    assert results[1].reason is None
