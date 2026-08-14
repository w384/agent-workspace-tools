CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE users (
    id UUID PRIMARY KEY,
    external_subject TEXT NOT NULL UNIQUE,
    display_name TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE groups (
    id UUID PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE roles (
    id TEXT PRIMARY KEY CHECK (id <> ''),
    name TEXT NOT NULL UNIQUE
);

CREATE TABLE user_groups (
    id UUID PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES users(id),
    group_id UUID NOT NULL REFERENCES groups(id),
    UNIQUE (user_id, group_id)
);

CREATE TABLE user_roles (
    id UUID PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES users(id),
    role_id TEXT NOT NULL REFERENCES roles(id),
    UNIQUE (user_id, role_id)
);

CREATE TABLE assets (
    id UUID PRIMARY KEY,
    workspace_id TEXT NOT NULL,
    path TEXT NOT NULL,
    name TEXT NOT NULL,
    created_by UUID NOT NULL REFERENCES users(id),
    active_version_id UUID,
    path_history JSONB NOT NULL DEFAULT '[]'::jsonb CHECK (jsonb_typeof(path_history) = 'array'),
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'archived')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (workspace_id, path)
);

CREATE TABLE asset_versions (
    id UUID PRIMARY KEY,
    asset_id UUID NOT NULL REFERENCES assets(id),
    version_number INTEGER NOT NULL CHECK (version_number > 0),
    content_fingerprint TEXT NOT NULL CHECK (content_fingerprint LIKE 'sha256:%'),
    source_path TEXT NOT NULL CHECK (source_path <> ''),
    index_state TEXT NOT NULL DEFAULT 'queued' CHECK (index_state IN ('queued', 'parsing', 'indexed', 'ready', 'failed')),
    failure_code TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (asset_id, version_number),
    UNIQUE (id, asset_id),
    CHECK (index_state <> 'failed' OR failure_code IS NOT NULL)
);

ALTER TABLE assets
    ADD CONSTRAINT assets_active_version_belongs_to_asset
    FOREIGN KEY (active_version_id, id) REFERENCES asset_versions(id, asset_id)
    DEFERRABLE INITIALLY DEFERRED;

CREATE TABLE permission_grants (
    id UUID PRIMARY KEY,
    workspace_id TEXT NOT NULL,
    context_version TEXT NOT NULL CHECK (context_version <> ''),
    principal_type TEXT NOT NULL CHECK (principal_type IN ('user', 'group', 'role')),
    user_id UUID REFERENCES users(id),
    group_id UUID REFERENCES groups(id),
    role_id TEXT REFERENCES roles(id),
    action TEXT NOT NULL CHECK (action IN ('upload', 'create_folder', 'move_rename', 'trash', 'query')),
    path_prefix TEXT NOT NULL CHECK (path_prefix <> '' AND path_prefix !~ '(^|/)\\.\\.(/|$)'),
    effect TEXT NOT NULL CHECK (effect IN ('allow', 'deny')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (
        (principal_type = 'user' AND user_id IS NOT NULL AND group_id IS NULL AND role_id IS NULL)
        OR (principal_type = 'group' AND user_id IS NULL AND group_id IS NOT NULL AND role_id IS NULL)
        OR (principal_type = 'role' AND user_id IS NULL AND group_id IS NULL AND role_id IS NOT NULL)
    )
);

CREATE UNIQUE INDEX permission_grants_user_scope_unique
    ON permission_grants (workspace_id, context_version, user_id, action, path_prefix) WHERE principal_type = 'user';
CREATE UNIQUE INDEX permission_grants_group_scope_unique
    ON permission_grants (workspace_id, context_version, group_id, action, path_prefix) WHERE principal_type = 'group';
CREATE UNIQUE INDEX permission_grants_role_scope_unique
    ON permission_grants (workspace_id, context_version, role_id, action, path_prefix) WHERE principal_type = 'role';

CREATE TABLE plans (
    id UUID PRIMARY KEY,
    workspace_id TEXT NOT NULL,
    created_by UUID NOT NULL REFERENCES users(id),
    decision_state TEXT NOT NULL CHECK (decision_state IN ('DIRECT', 'SELF_CONFIRM', 'APPROVAL_REQUIRED', 'DENY')),
    state TEXT NOT NULL CHECK (state IN ('draft', 'pending_confirmation', 'pending_approval', 'approved', 'rejected', 'executing', 'completed', 'failed')),
    decision_id UUID NOT NULL,
    policy_version TEXT NOT NULL CHECK (policy_version <> ''),
    context_version TEXT NOT NULL CHECK (context_version <> ''),
    normalized_operations JSONB NOT NULL CHECK (jsonb_typeof(normalized_operations) = 'array'),
    asset_snapshots JSONB NOT NULL CHECK (jsonb_typeof(asset_snapshots) = 'array'),
    plan_hash TEXT NOT NULL UNIQUE,
    executor_plan_id TEXT NOT NULL CHECK (executor_plan_id <> ''),
    executor_plan_hash TEXT NOT NULL CHECK (executor_plan_hash LIKE 'sha256:%'),
    acl_snapshot JSONB NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE confirmations (
    id UUID PRIMARY KEY,
    plan_id UUID NOT NULL REFERENCES plans(id),
    confirmed_by UUID NOT NULL REFERENCES users(id),
    decision TEXT NOT NULL CHECK (decision IN ('confirmed', 'cancelled')),
    expected_plan_hash TEXT NOT NULL CHECK (expected_plan_hash <> ''),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (plan_id)
);

CREATE TABLE approvals (
    id UUID PRIMARY KEY,
    plan_id UUID NOT NULL REFERENCES plans(id),
    requester_id UUID NOT NULL REFERENCES users(id),
    required_role_id TEXT NOT NULL REFERENCES roles(id),
    approver_id UUID REFERENCES users(id),
    decision TEXT NOT NULL DEFAULT 'pending' CHECK (decision IN ('pending', 'approved', 'rejected')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    decided_at TIMESTAMPTZ,
    CHECK (approver_id IS NULL OR approver_id <> requester_id),
    UNIQUE (plan_id)
);

CREATE TABLE execution_jobs (
    id UUID PRIMARY KEY,
    plan_id UUID NOT NULL REFERENCES plans(id),
    requested_by UUID NOT NULL REFERENCES users(id),
    plan_hash TEXT NOT NULL CHECK (plan_hash <> ''),
    state TEXT NOT NULL CHECK (state IN ('queued', 'running', 'completed', 'failed', 'rolled_back')),
    idempotency_key TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at TIMESTAMPTZ,
    UNIQUE (plan_id, plan_hash, idempotency_key)
);

CREATE TABLE rule_sets (
    id UUID PRIMARY KEY,
    scenario TEXT NOT NULL CHECK (scenario <> ''),
    name TEXT NOT NULL CHECK (name <> ''),
    status TEXT NOT NULL CHECK (status IN ('active', 'archived')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE rule_versions (
    id UUID PRIMARY KEY,
    rule_set_id UUID NOT NULL REFERENCES rule_sets(id),
    source_type TEXT NOT NULL CHECK (source_type IN ('demo_fixture', 'manual_entry')),
    version_label TEXT NOT NULL CHECK (version_label <> ''),
    content_fingerprint TEXT NOT NULL CHECK (content_fingerprint LIKE 'sha256:%'),
    redacted_rule_summary TEXT NOT NULL CHECK (redacted_rule_summary <> ''),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE audit_events (
    id UUID PRIMARY KEY,
    event_type TEXT NOT NULL,
    actor_id UUID NOT NULL REFERENCES users(id),
    request_id UUID NOT NULL,
    run_id UUID,
    plan_id UUID REFERENCES plans(id),
    job_id UUID REFERENCES execution_jobs(id),
    details JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE assessment_reports (
    id UUID PRIMARY KEY,
    scenario TEXT NOT NULL CHECK (scenario <> ''),
    actor_id UUID NOT NULL REFERENCES users(id),
    workspace_id TEXT NOT NULL,
    asset_versions JSONB NOT NULL CHECK (jsonb_typeof(asset_versions) = 'array'),
    rule_version_id UUID NOT NULL REFERENCES rule_versions(id),
    match_score INTEGER NOT NULL CHECK (match_score >= 0 AND match_score <= 100),
    result_level TEXT NOT NULL CHECK (result_level IN ('MATCH', 'POSSIBLE', 'NOT_MATCH', 'MISSING_INFO')),
    missing_materials JSONB NOT NULL CHECK (jsonb_typeof(missing_materials) = 'array'),
    citations JSONB NOT NULL CHECK (jsonb_typeof(citations) = 'array'),
    rule_version_evidence JSONB NOT NULL CHECK (jsonb_typeof(rule_version_evidence) = 'object'),
    disclaimer TEXT NOT NULL CHECK (disclaimer <> ''),
    disclaimer_version TEXT NOT NULL CHECK (disclaimer_version <> ''),
    query_subject TEXT NOT NULL CHECK (query_subject <> ''),
    audit_event_id UUID NOT NULL REFERENCES audit_events(id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE chunk_metadata (
    id UUID PRIMARY KEY,
    asset_version_id UUID NOT NULL REFERENCES asset_versions(id),
    chunk_index INTEGER NOT NULL CHECK (chunk_index >= 0),
    qdrant_point_id UUID NOT NULL UNIQUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (asset_version_id, chunk_index)
);
