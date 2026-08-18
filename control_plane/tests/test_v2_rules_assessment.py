from control_plane.app.domain import Action, GrantEffect, PermissionGrant, PrincipalType


def _grant(action: Action, path_prefix: str, effect: GrantEffect = GrantEffect.ALLOW):
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


def _seed_ready_active_asset(repository, *, path="organized/customer-profile.pdf", fingerprint="sha256:customer-v1"):
    asset = repository.get_or_create_asset(
        "workspace-a", path, path.rsplit("/", 1)[-1], "user-a"
    )
    version = repository.create_asset_version(asset.asset_id, fingerprint, path)
    for state in ("parsing", "indexed", "ready"):
        version = repository.transition_asset_version(version.asset_version_id, state)
    repository.activate_asset_version(version.asset_version_id)
    return asset, version


def _create_demo_rule_version(client):
    response = client.post(
        "/api/rule-sets",
        json_body={
            "scenario": "finance_profile_matching",
            "name": "演示银行规则样例",
            "status": "active",
            "source_type": "demo_fixture",
            "version_label": "demo-2026-08-14",
            "redacted_rule_summary": "脱敏演示规则：收入证明、流水、身份证明",
        },
    )
    assert response.status_code == 200
    return response.json()["rule_version"]


def test_v2_rule_version_rejects_non_demo_or_manual_sources(client_as_a, repository) -> None:
    response = client_as_a.post(
        "/api/rule-sets",
        json_body={
            "scenario": "finance_profile_matching",
            "name": "真实银行规则",
            "status": "active",
            "source_type": "verified_external_source",
            "version_label": "external-2026-08-14",
            "content_fingerprint": "sha256:external",
            "redacted_rule_summary": "不可用于首轮演示的外部规则",
        },
    )

    assert response.status_code == 422
    assert response.json() == {
        "error": {
            "code": "rule_source_not_allowed",
            "message": "Rule source is not allowed for the demo",
        }
    }
    assert repository.rule_sets == {}
    assert repository.rule_versions == {}


def test_v2_assessment_uses_trusted_active_asset_version_and_audits_report(client_as_a, repository, rag_port) -> None:
    repository.add_permission_grant(_grant(Action.QUERY, "organized"))
    asset, active_version = _seed_ready_active_asset(repository)
    stale_version = repository.create_asset_version(
        asset.asset_id, "sha256:stale", "organized/customer-profile.pdf"
    )
    rule_version = _create_demo_rule_version(client_as_a)

    response = client_as_a.post(
        "/api/assessments",
        params={"user_id": "user-b"},
        headers={"X-User-Id": "user-b", "X-Request-Id": "forged-request"},
        json_body={
            "scenario": "finance_profile_matching",
            "query_subject": "customer-demo-001",
            "asset_ids": [asset.asset_id],
            "asset_version_ids": [stale_version.asset_version_id],
            "rule_version_id": rule_version["rule_version_id"],
            "llm_report": {"actor_id": "user-b", "match_score": 1, "result_level": "NOT_MATCH"},
        },
    )

    assert response.status_code == 200
    report = response.json()["report"]
    assert report["actor_id"] == "user-a"
    assert report["asset_versions"] == [active_version.asset_version_id]
    assert report["rule_version_id"] == rule_version["rule_version_id"]
    assert report["match_score"] == 82
    assert report["result_level"] == "MATCH"
    assert report["missing_materials"] == ["近六个月流水"]
    assert report["citations"] == [{
        "asset_version_id": active_version.asset_version_id,
        "chunk_id": "chunk-demo-1",
        "page": 1,
        "paragraph": 3,
    }]
    assert report["rule_version_evidence"] == {
        "rule_version_id": rule_version["rule_version_id"],
        "version_label": "demo-2026-08-14",
        "content_fingerprint": "sha256:4ec896850429e7d5edd3d8a943698a1eca0285e4c88c0720ae66e3a78a5e8b40",
        "source_type": "demo_fixture",
    }
    assert report["disclaimer"] == "仅供资料完整度与规则匹配演示参考"
    assert report["disclaimer_version"] == "disclaimer-demo-v1"
    for forbidden_key in ("credit_score", "loan_score", "loan_approval", "credit_decision", "授信结论", "贷款审批结论"):
        assert forbidden_key not in report

    assert len(rag_port.assessment_calls) == 1
    assessment_call = rag_port.assessment_calls[0]
    assert assessment_call.actor.actor_id == "user-a"
    assert assessment_call.asset_versions == (active_version,)
    assert assessment_call.rule_version.rule_version_id == rule_version["rule_version_id"]
    assert assessment_call.query_subject == "customer-demo-001"
    events = repository.list_audit_events()
    assert events[-1].event_type == "assessment_report_created"
    assert events[-1].actor_id == "user-a"
    assert events[-1].request_id != "forged-request"
    assert "forged" not in repr(events)


def test_v2_not_match_requires_explicit_fictional_conflict_evidence(client_as_a, repository, rag_port) -> None:
    repository.add_permission_grant(_grant(Action.QUERY, "organized"))
    asset, _active_version = _seed_ready_active_asset(repository)
    rule_version = _create_demo_rule_version(client_as_a)
    rag_port.assessment_result = rag_port.assessment_result.__class__(
        match_score=0,
        result_level="NOT_MATCH",
        missing_materials=("材料不足",),
        citations=({"asset_version_id": "", "chunk_id": "chunk-demo-1", "page": 1, "paragraph": 3},),
    )

    response = client_as_a.post(
        "/api/assessments",
        json_body={
            "scenario": "finance_profile_matching",
            "query_subject": "customer-demo-001",
            "asset_ids": [asset.asset_id],
            "rule_version_id": rule_version["rule_version_id"],
        },
    )
    assert response.status_code == 502
    assert response.json() == {"error": {"code": "assessment_failed", "message": "Assessment failed"}}
    assert repository.assessment_reports == {}
    assert repository.list_audit_events()[-1].event_type == "assessment_failed"
    assert repository.list_audit_events()[-1].details == {
        "scenario": "finance_profile_matching",
        "rule_version_id": rule_version["rule_version_id"],
        "reason": "invalid_assessment_result",
    }


def test_v2_assessment_deny_has_zero_rag_report_or_sensitive_audit(client_as_a, repository, rag_port) -> None:
    asset, _active_version = _seed_ready_active_asset(
        repository, path="private/customer-profile.pdf", fingerprint="sha256:private"
    )
    rule_version = _create_demo_rule_version(client_as_a)

    response = client_as_a.post(
        "/api/assessments",
        json_body={
            "scenario": "finance_profile_matching",
            "query_subject": "private-customer",
            "asset_ids": [asset.asset_id],
            "rule_version_id": rule_version["rule_version_id"],
        },
    )
    assert response.status_code == 403
    assert response.json() == {
        "status": "DENIED",
        "reason": "ACCESS_DENIED",
        "retrieved_count": 0,
        "llm_invoked": False,
        "citations": [],
        "error": {"code": "assessment_denied", "message": "Assessment is not authorized"},
    }
    assert rag_port.assessment_calls == []
    assert repository.assessment_reports == {}
    events = repository.list_audit_events()
    assert events[-1].event_type == "assessment_denied"
    assert events[-1].details == {
        "scenario": "finance_profile_matching",
        "decision": "DENY",
        "query_subject": "private-customer",
        "rule_version_id": rule_version["rule_version_id"],
        "requested_asset_ids": [asset.asset_id],
        "retrieved_count": 0,
        "llm_invoked": False,
        "citations": [],
    }
    assert "private/customer-profile.pdf" not in repr(events)


def test_v2_assessment_fails_closed_for_material_citation_outside_authorized_snapshot(
    client_as_a, repository, rag_port
) -> None:
    repository.add_permission_grant(_grant(Action.QUERY, "organized"))
    asset, active_version = _seed_ready_active_asset(repository)
    rule_version = _create_demo_rule_version(client_as_a)
    rag_port.assessment_result = rag_port.assessment_result.__class__(
        match_score=82,
        result_level="MATCH",
        missing_materials=(),
        citations=(
            {
                "citation_type": "material",
                "asset_id": asset.asset_id,
                "asset_version_id": "version-outside-authorized-snapshot",
                "chunk_id": "chunk-outside",
                "page": 1,
                "paragraph": 1,
            },
        ),
    )

    response = client_as_a.post(
        "/api/assessments",
        json_body={
            "scenario": "finance_profile_matching",
            "query_subject": "citation-scope-check",
            "asset_ids": [asset.asset_id],
            "rule_version_id": rule_version["rule_version_id"],
        },
    )

    assert response.status_code == 502
    assert response.json()["error"]["code"] == "assessment_failed"
    assert repository.assessment_reports == {}
    assert repository.list_audit_events()[-1].details["reason"] == "invalid_assessment_result"


def test_v2_assessment_fails_closed_for_rule_citation_outside_selected_version(
    client_as_a, repository, rag_port
) -> None:
    repository.add_permission_grant(_grant(Action.QUERY, "organized"))
    asset, active_version = _seed_ready_active_asset(repository)
    rule_version = _create_demo_rule_version(client_as_a)
    rag_port.assessment_result = rag_port.assessment_result.__class__(
        match_score=82,
        result_level="MATCH",
        missing_materials=(),
        citations=(
            {
                "citation_type": "material",
                "asset_id": asset.asset_id,
                "asset_version_id": active_version.asset_version_id,
                "chunk_id": "chunk-authorized",
                "page": 1,
                "paragraph": 1,
            },
            {
                "citation_type": "rule",
                "rule_id": "demo-rule-a",
                "rule_version_id": "rule-version-outside-selected-version",
                "version_label": "other-version",
                "content_fingerprint": "sha256:other-rule",
                "source_type": "demo_fixture",
            },
        ),
    )

    response = client_as_a.post(
        "/api/assessments",
        json_body={
            "scenario": "finance_profile_matching",
            "query_subject": "rule-citation-scope-check",
            "asset_ids": [asset.asset_id],
            "rule_version_id": rule_version["rule_version_id"],
        },
    )

    assert response.status_code == 502
    assert response.json()["error"]["code"] == "assessment_failed"
    assert repository.assessment_reports == {}
    assert repository.list_audit_events()[-1].details["reason"] == "invalid_assessment_result"
