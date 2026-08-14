from pathlib import Path


SCHEMA_PATH = Path(__file__).parents[1] / "migrations" / "001_control_plane.sql"


def test_schema_covers_every_control_plane_record_with_primary_keys() -> None:
    schema = SCHEMA_PATH.read_text(encoding="utf-8").lower()

    for table in (
        "users",
        "groups",
        "roles",
        "user_groups",
        "user_roles",
        "assets",
        "asset_versions",
        "permission_grants",
        "plans",
        "confirmations",
        "approvals",
        "execution_jobs",
        "rule_sets",
        "rule_versions",
        "assessment_reports",
        "audit_events",
        "chunk_metadata",
    ):
        assert f"create table {table}" in schema
        assert "id uuid primary key" in schema


def test_schema_links_authoritative_assets_versions_and_permissions_with_constraints() -> None:
    schema = SCHEMA_PATH.read_text(encoding="utf-8").lower()

    assert "asset_id uuid not null references assets(id)" in schema
    assert "asset_version_id uuid not null references asset_versions(id)" in schema
    assert "unique (asset_id, version_number)" in schema
    assert "unique (workspace_id, path)" in schema
    assert "check (effect in ('allow', 'deny'))" in schema
    assert "check (action in ('upload', 'create_folder', 'move_rename', 'trash', 'query'))" in schema
    assert "active_version_id uuid" in schema
    assert "path_history jsonb not null" in schema
    assert "source_path text not null" in schema
    assert "failure_code text" in schema
    assert "workspace_id text not null" in schema
    assert "context_version text not null check (context_version <> '')" in schema


def test_permission_grants_keep_their_user_group_or_role_subject_under_foreign_key() -> None:
    schema = SCHEMA_PATH.read_text(encoding="utf-8").lower()

    assert "user_id uuid references users(id)" in schema
    assert "group_id uuid references groups(id)" in schema
    assert "role_id text references roles(id)" in schema
    assert "check (" in schema


def test_schema_enforces_workflow_state_checks_and_approval_separation() -> None:
    schema = SCHEMA_PATH.read_text(encoding="utf-8").lower()

    assert "check (state in ('draft', 'pending_confirmation', 'pending_approval', 'approved', 'rejected', 'executing', 'completed', 'failed'))" in schema
    assert "check (decision in ('pending', 'approved', 'rejected'))" in schema
    assert "check (approver_id is null or approver_id <> requester_id)" in schema
    assert "check (index_state in ('queued', 'parsing', 'indexed', 'ready', 'failed'))" in schema
    assert "policy_version text not null check (policy_version <> '')" in schema
    assert "context_version text not null check (context_version <> '')" in schema
    assert "normalized_operations jsonb not null" in schema
    assert "asset_snapshots jsonb not null" in schema
    assert "executor_plan_id text not null check (executor_plan_id <> '')" in schema
    assert "executor_plan_hash text not null check (executor_plan_hash like 'sha256:%')" in schema
    assert "required_role_id text not null references roles(id)" in schema
    assert "check (state in ('queued', 'running', 'completed', 'failed', 'rolled_back'))" in schema
    assert "unique (plan_id, plan_hash, idempotency_key)" in schema
    assert "succeeded" not in schema


def test_schema_covers_v2_rule_versions_assessment_reports_and_audit_links() -> None:
    schema = SCHEMA_PATH.read_text(encoding="utf-8").lower()

    assert "scenario text not null check (scenario <> '')" in schema
    assert "name text not null check (name <> '')" in schema
    assert "status text not null check (status in ('active', 'archived'))" in schema
    assert "rule_set_id uuid not null references rule_sets(id)" in schema
    assert "source_type text not null check (source_type in ('demo_fixture', 'manual_entry'))" in schema
    assert "version_label text not null check (version_label <> '')" in schema
    assert "content_fingerprint text not null check (content_fingerprint like 'sha256:%')" in schema
    assert "redacted_rule_summary text not null check (redacted_rule_summary <> '')" in schema
    assert "asset_versions jsonb not null check (jsonb_typeof(asset_versions) = 'array')" in schema
    assert "rule_version_id uuid not null references rule_versions(id)" in schema
    assert "match_score integer not null check (match_score >= 0 and match_score <= 100)" in schema
    assert "result_level text not null check (result_level in ('match', 'possible', 'not_match', 'missing_info'))" in schema
    assert "missing_materials jsonb not null check (jsonb_typeof(missing_materials) = 'array')" in schema
    assert "citations jsonb not null check (jsonb_typeof(citations) = 'array')" in schema
    assert "rule_version_evidence jsonb not null check (jsonb_typeof(rule_version_evidence) = 'object')" in schema
    assert "disclaimer text not null check (disclaimer <> '')" in schema
    assert "disclaimer_version text not null check (disclaimer_version <> '')" in schema
    assert "query_subject text not null check (query_subject <> '')" in schema
    assert "audit_event_id uuid not null references audit_events(id)" in schema
