"""Real LLM explanation port: polish contract and fail-closed behavior."""

from __future__ import annotations

import httpx
import pytest

from service.app.rag.contracts import (
    ActiveAssetVersion,
    Chunk,
    PermissionContext,
)


TENANT_ID = "tenant-demo"
ACTIVE_VERSION = ActiveAssetVersion(
    asset_id="asset-llm-demo",
    asset_version_id="version-llm-demo-v1",
)


def _chunk() -> Chunk:
    return Chunk(
        tenant_id=TENANT_ID,
        asset_id=ACTIVE_VERSION.asset_id,
        asset_version_id=ACTIVE_VERSION.asset_version_id,
        chunk_id="chunk-llm-1",
        ordinal=0,
        text="Authorized demo evidence.",
        page_number=3,
        paragraph_index=7,
        parser_version="parser-v1",
        embedding_version="embedding-v1",
        index_version="index-v1",
    )


def _context() -> PermissionContext:
    return PermissionContext(
        tenant_id=TENANT_ID,
        principal_id="principal-demo",
        group_ids=("group-demo",),
        session_id="authenticated-session",
        request_id="request-llm-explanation",
    )


def _llm_config():
    from service.app.rag.llm import LLMConfig

    return LLMConfig(
        base_url="https://llm.demo.example/v1",
        api_key="demo-secret-key-not-for-frontend",
        model="demo-llm-model",
        timeout_seconds=5.0,
    )


def _capturing_transport():
    captured = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        body = {
            "choices": [
                {"message": {"content": "LLM polished explanation"}}
            ]
        }
        return httpx.Response(200, json=body)

    return captured, httpx.MockTransport(handler)


def _rule_version():
    from service.app.rag.finance_matching import (
        MaterialRequirement,
        RuleSourceType,
        RuleVersionSnapshot,
    )

    return RuleVersionSnapshot(
        rule_set_id="ruleset-demo",
        rule_version_id="rule-version-demo-v1",
        version_label="demo-v1",
        source_type=RuleSourceType.DEMO_FIXTURE,
        content_fingerprint="sha256:demo-rules-v1",
        disclaimer="Demo fixture only; not a real bank rule.",
        requirements=(
            MaterialRequirement(
                rule_id="rule-balance-sheet",
                material_key="balance_sheet",
                label="Balance sheet",
            ),
        ),
    )


def _build_matching_service(
    *,
    explanation_port,
    control_plane=None,
    fact_index=None,
):
    from service.app.rag.finance_matching import (
        FinanceMaterialMatchingService,
        MaterialFact,
        MaterialFactHit,
        MaterialMatchingScope,
    )

    class DefaultControlPlane:
        def resolve_material_matching_scope(self, _context):
            return MaterialMatchingScope(
                tenant_id=TENANT_ID,
                allowed_active_versions=(ACTIVE_VERSION,),
                denied_asset_ids=frozenset(),
                rule_version=_rule_version(),
            )

    class DefaultFactIndex:
        def search(self, *, retrieval_filter, limit):
            return (
                MaterialFactHit(
                    fact=MaterialFact(
                        material_key="balance_sheet",
                        chunk=_chunk(),
                    ),
                    score=0.99,
                ),
            )

    return FinanceMaterialMatchingService(
        control_plane=control_plane or DefaultControlPlane(),
        fact_index=fact_index or DefaultFactIndex(),
        explanation_port=explanation_port,
    )


def test_explanation_comes_from_real_llm_when_requested():
    from service.app.rag.finance_matching import MaterialMatchStatus
    from service.app.rag.llm import LLMClient, LLMExplanationPort

    captured, transport = _capturing_transport()
    port = LLMExplanationPort(
        client=LLMClient(
            config=_llm_config(),
            transport=transport,
        )
    )
    result = _build_matching_service(explanation_port=port).match(
        context=_context(),
        include_explanation=True,
    )

    assert result.status == MaterialMatchStatus.MATCH
    assert result.explanation == "LLM polished explanation"
    assert result.llm_invoked is True
    assert len(captured) == 1
    assert result.match_score == 100


def test_explanation_request_contains_structured_result():
    from service.app.rag.llm import LLMClient, LLMExplanationPort

    captured, transport = _capturing_transport()
    port = LLMExplanationPort(
        client=LLMClient(
            config=_llm_config(),
            transport=transport,
        )
    )
    _build_matching_service(explanation_port=port).match(
        context=_context(),
        include_explanation=True,
    )

    request_body = captured[0].read().decode("utf-8")
    assert "MATCH" in request_body
    assert "match_score" in request_body
    assert "balance_sheet" in request_body


def test_explanation_not_requested_never_invokes_llm():
    from service.app.rag.llm import LLMClient, LLMExplanationPort

    captured, transport = _capturing_transport()
    port = LLMExplanationPort(
        client=LLMClient(
            config=_llm_config(),
            transport=transport,
        )
    )
    result = _build_matching_service(explanation_port=port).match(
        context=_context(),
        include_explanation=False,
    )

    assert result.llm_invoked is False
    assert result.explanation is None
    assert captured == []


def test_denied_scope_never_invokes_explanation_llm():
    from service.app.rag.finance_matching import MaterialMatchingScope
    from service.app.rag.llm import LLMClient, LLMExplanationPort

    class DeniedControlPlane:
        def resolve_material_matching_scope(self, _context):
            return MaterialMatchingScope(
                tenant_id=TENANT_ID,
                allowed_active_versions=(ACTIVE_VERSION,),
                denied_asset_ids=frozenset(
                    {ACTIVE_VERSION.asset_id}
                ),
                rule_version=_rule_version(),
            )

    class NeverFactIndex:
        def __init__(self):
            self.call_count = 0

        def search(self, **_kwargs):
            self.call_count += 1
            raise AssertionError(
                "DENIED fact must not be recalled"
            )

    captured, transport = _capturing_transport()
    port = LLMExplanationPort(
        client=LLMClient(
            config=_llm_config(),
            transport=transport,
        )
    )
    fact_index = NeverFactIndex()
    result = _build_matching_service(
        explanation_port=port,
        control_plane=DeniedControlPlane(),
        fact_index=fact_index,
    ).match(
        context=_context(),
        include_explanation=True,
    )

    assert fact_index.call_count == 0
    assert result.llm_invoked is False
    assert result.explanation is None
    assert captured == []


def test_explanation_failure_fails_closed_without_masking():
    from service.app.rag.finance_matching import MaterialMatchStatus
    from service.app.rag.llm import LLMClient, LLMExplanationPort

    def failing_handler(
        _request: httpx.Request,
    ) -> httpx.Response:
        return httpx.Response(500, text="upstream failure")

    port = LLMExplanationPort(
        client=LLMClient(
            config=_llm_config(),
            transport=httpx.MockTransport(failing_handler),
        )
    )
    result = _build_matching_service(explanation_port=port).match(
        context=_context(),
        include_explanation=True,
    )

    assert result.status == MaterialMatchStatus.MATCH
    assert result.explanation is None
    assert result.llm_invoked is True
    assert result.reason == "llm_unavailable"
    assert result.match_score == 100


def test_explanation_credentials_never_leak():
    from service.app.rag.llm import LLMClient, LLMExplanationPort

    captured, transport = _capturing_transport()
    port = LLMExplanationPort(
        client=LLMClient(
            config=_llm_config(),
            transport=transport,
        )
    )
    result = _build_matching_service(explanation_port=port).match(
        context=_context(),
        include_explanation=True,
    )

    assert (
        "demo-secret-key-not-for-frontend"
        not in result.explanation
    )
    assert "demo-secret-key-not-for-frontend" not in repr(result)


def test_explanation_config_requires_environment_injection():
    from service.app.rag.llm import (
        LLMConfigurationError,
        load_llm_config,
    )

    with pytest.raises(LLMConfigurationError):
        load_llm_config({})


def test_build_explanation_port_uses_injected_credentials():
    from service.app.rag.llm import (
        build_llm_explanation_port,
        load_llm_config,
    )

    environment = {
        "RAG_LLM_BASE_URL": "https://llm.demo.example/v1",
        "RAG_LLM_API_KEY": "injected-demo-key",
        "RAG_LLM_MODEL": "demo-model",
    }
    port = build_llm_explanation_port(environment)
    assert port is not None
    assert load_llm_config(environment).model == "demo-model"
