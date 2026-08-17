# Task 3 implementation report - Gate2 plans, approvals, execution audit

## Status

`GREEN_CANDIDATE_AFTER_FIX_ROUND_3`

Task 3 implements the minimum control-plane slice for Gate2: canonical plan hash, SELF_CONFIRM, APPROVAL_REQUIRED A-to-B timing, configured opaque approver role ID, workspace-scoped approval isolation, compound execution idempotency, requester-owned execution actor reconstruction, pre-execution revalidation, BFF DENY zero downstream, executor final DENY mapping, executor failure handling, and one-time credential boundary by omission.

Scope stayed under `control_plane/**`. No `service/**`, `plugin/**`, frozen guideline, external deployment, remote push, dependency install, or real public-drive data access.

## Changed files

Production and contract files:

- `control_plane/app/plan_hash.py`
- `control_plane/app/domain.py`
- `control_plane/app/ports.py`
- `control_plane/app/repository.py`
- `control_plane/app/service.py`
- `control_plane/app/main.py`
- `control_plane/migrations/001_control_plane.sql`
- `control_plane/docs/implementation-plan.md`

Tests and work records:

- `control_plane/tests/test_gate2_plans.py`
- `control_plane/tests/test_approval.py`
- `control_plane/tests/test_policy.py`
- `control_plane/tests/test_schema.py`
- `control_plane/tests/test_gate1_upload.py`
- `control_plane/tests/test_session_boundary.py`
- `control_plane/tests/conftest.py`
- `control_plane/work/sdd/control-plane-demo/progress.md`
- `control_plane/work/sdd/control-plane-demo/task-3-report.md`

## RED evidence

Initial Task3 RED:

```powershell
& 'D:\AI\Codex\Projects\agent-workspace-tools\service\.venv\Scripts\python.exe' -B -m pytest control_plane\tests\test_gate2_plans.py control_plane\tests\test_approval.py -q -p no:cacheprovider
```

Result:

```text
ERROR control_plane/tests/test_gate2_plans.py
ModuleNotFoundError: No module named 'control_plane.app.plan_hash'
1 error in 0.10s
exit 1
```

The failure was expected because the canonical hash value object did not exist yet.

## GREEN evidence

Task3 slice:

```powershell
& 'D:\AI\Codex\Projects\agent-workspace-tools\service\.venv\Scripts\python.exe' -B -m pytest control_plane\tests\test_gate2_plans.py control_plane\tests\test_approval.py -q -p no:cacheprovider
```

Result:

```text
10 passed in 0.15s
exit 0
```

Scoped full control-plane regression:

```powershell
& 'D:\AI\Codex\Projects\agent-workspace-tools\service\.venv\Scripts\python.exe' -B -m pytest control_plane\tests -q -p no:cacheprovider
```

Result:

```text
54 passed in 0.38s
exit 0
```

## Fix round 1 evidence

Review RED:

```powershell
& 'D:\AI\Codex\Projects\agent-workspace-tools\service\.venv\Scripts\python.exe' -B -m pytest control_plane\tests\test_gate2_plans.py::test_confirm_revalidates_expiry_context_acl_and_active_snapshot_before_execution control_plane\tests\test_gate2_plans.py::test_executor_exception_or_non_completed_result_fails_job_without_false_completion control_plane\tests\test_gate2_plans.py::test_confirm_fails_closed_for_non_creator_session control_plane\tests\test_approval.py::test_high_risk_creates_pending_approval_only_after_creator_confirms -q -p no:cacheprovider
```

Result:

```text
3 failed, 1 passed in 0.16s
exit 1
```

Failure causes were expected: expired plans still executed, executor exceptions returned framework 500, and repeated high-risk confirmation returned 409 instead of the same pending approval.

Additional RED:

```powershell
& 'D:\AI\Codex\Projects\agent-workspace-tools\service\.venv\Scripts\python.exe' -B -m pytest control_plane\tests\test_gate2_plans.py::test_service_uses_repository_protocol_methods_for_confirmation_and_approval_state control_plane\tests\test_approval.py::test_approver_role_id_is_injected_configuration -q -p no:cacheprovider
```

Result:

```text
2 failed in 0.10s
exit 1
```

Failure causes were expected: `ControlPlaneRepository` lacked explicit confirmation/approval query methods and `create_app` could not inject `approver_role_id`.

Fix round GREEN:

```powershell
& 'D:\AI\Codex\Projects\agent-workspace-tools\service\.venv\Scripts\python.exe' -B -m pytest control_plane\tests\test_gate2_plans.py::test_confirm_revalidates_expiry_context_acl_and_active_snapshot_before_execution control_plane\tests\test_gate2_plans.py::test_executor_exception_or_non_completed_result_fails_job_without_false_completion control_plane\tests\test_gate2_plans.py::test_confirm_fails_closed_for_non_creator_session control_plane\tests\test_gate2_plans.py::test_service_uses_repository_protocol_methods_for_confirmation_and_approval_state control_plane\tests\test_approval.py::test_high_risk_creates_pending_approval_only_after_creator_confirms control_plane\tests\test_approval.py::test_approver_role_id_is_injected_configuration -q -p no:cacheprovider
```

Result:

```text
6 passed in 0.12s
exit 0
```

Latest Task3 slice:

```powershell
& 'D:\AI\Codex\Projects\agent-workspace-tools\service\.venv\Scripts\python.exe' -B -m pytest control_plane\tests\test_gate2_plans.py control_plane\tests\test_approval.py -q -p no:cacheprovider
```

Result:

```text
15 passed in 0.23s
exit 0
```

Latest scoped full control-plane regression:

```powershell
& 'D:\AI\Codex\Projects\agent-workspace-tools\service\.venv\Scripts\python.exe' -B -m pytest control_plane\tests -q -p no:cacheprovider
```

Result:

```text
60 passed in 0.48s
exit 0
```

## Fix round 2 evidence

Review RED:

```powershell
& 'D:\AI\Codex\Projects\agent-workspace-tools\service\.venv\Scripts\python.exe' -B -m pytest control_plane\tests\test_approval.py::test_configured_non_initiator_approver_executes_after_approval control_plane\tests\test_approval.py::test_approver_role_grant_cannot_replace_requester_file_grant control_plane\tests\test_gate2_plans.py::test_missing_active_snapshot_fails_closed_instead_of_500 -q -p no:cacheprovider
```

Result:

```text
3 failed in 0.15s
exit 1
```

Failure causes were expected: approval execution sent B to the executor, B approver-role grants could satisfy A's file authorization after A's grant was revoked, and a missing active snapshot returned framework 500.

Fix round GREEN:

```powershell
& 'D:\AI\Codex\Projects\agent-workspace-tools\service\.venv\Scripts\python.exe' -B -m pytest control_plane\tests\test_approval.py::test_configured_non_initiator_approver_executes_after_approval control_plane\tests\test_approval.py::test_approver_role_grant_cannot_replace_requester_file_grant control_plane\tests\test_gate2_plans.py::test_missing_active_snapshot_fails_closed_instead_of_500 -q -p no:cacheprovider
```

Result:

```text
3 passed in 0.10s
exit 0
```

Latest Task3 slice:

```powershell
& 'D:\AI\Codex\Projects\agent-workspace-tools\service\.venv\Scripts\python.exe' -B -m pytest control_plane\tests\test_gate2_plans.py control_plane\tests\test_approval.py -q -p no:cacheprovider
```

Result:

```text
17 passed in 0.26s
exit 0
```

Latest scoped full control-plane regression:

```powershell
& 'D:\AI\Codex\Projects\agent-workspace-tools\service\.venv\Scripts\python.exe' -B -m pytest control_plane\tests -q -p no:cacheprovider
```

Result:

```text
62 passed in 0.48s
exit 0
```

## Fix round 3 evidence

Review RED:

```powershell
& 'D:\AI\Codex\Projects\agent-workspace-tools\service\.venv\Scripts\python.exe' -B -m pytest control_plane\tests\test_approval.py::test_same_role_approver_from_another_workspace_cannot_list_or_decide_approval -q -p no:cacheprovider
```

Result:

```text
1 failed in 0.09s
exit 1
```

The failure was expected: a `workspace-b` actor with the same opaque approver role could list a `workspace-a` pending approval.

Fix round GREEN:

```powershell
& 'D:\AI\Codex\Projects\agent-workspace-tools\service\.venv\Scripts\python.exe' -B -m pytest control_plane\tests\test_approval.py::test_same_role_approver_from_another_workspace_cannot_list_or_decide_approval -q -p no:cacheprovider
```

Result:

```text
1 passed in 0.06s
exit 0
```

Latest Task3 slice:

```powershell
& 'D:\AI\Codex\Projects\agent-workspace-tools\service\.venv\Scripts\python.exe' -B -m pytest control_plane\tests\test_gate2_plans.py control_plane\tests\test_approval.py -q -p no:cacheprovider
```

Result:

```text
18 passed in 0.26s
exit 0
```

Latest scoped full control-plane regression:

```powershell
& 'D:\AI\Codex\Projects\agent-workspace-tools\service\.venv\Scripts\python.exe' -B -m pytest control_plane\tests -q -p no:cacheprovider
```

Result:

```text
63 passed in 0.49s
exit 0
```

## Self review

- `compute_canonical_plan_hash` uses canonical JSON with sorted keys, compact separators and UTF-8; `asset_snapshots` are sorted by `asset_id`; `idempotency_key` is not part of the hash.
- Plan hash binds `contract_version`, `plan_id`, `workspace_id`, `actor_id`, `decision_state`, `decision_id`, `policy_version`, `context_version`, normalized operations, asset snapshots and `expires_at`.
- `plan_hash_matches` uses constant-time comparison.
- `SELF_CONFIRM` plans persist as `pending_confirmation`; only the creator can confirm; B has no pending approval.
- `APPROVAL_REQUIRED` creates no approval at plan creation. A confirmation creates exactly one pending approval requiring `role-approver-demo`.
- A cannot self-approve even if the request body forges roles. Only trusted session `role_ids` are used.
- `approver_role_id` is injected through `create_app`/`ControlPlaneService`; fixture uses `role-approver-demo`, but the service no longer hardcodes it as authority.
- Confirmation and approval state are retrieved through `ControlPlaneRepository` protocol methods, not by reading repository internals from the service.
- Before execution, the BFF revalidates `expires_at`, actor context version, current ACL and active asset/version/fingerprint snapshots. Expiry, context drift, ACL DENY, missing snapshot or snapshot drift fail closed before executor calls and write redacted `plan_revalidation_failed` audit.
- Approval execution reconstructs the requester actor from trusted Plan `acl_snapshot` (`created_by`, workspace, context version, creator group IDs and creator role IDs). B's approver role/group never become A's file authorization input. The executor receives A as `actor`; approval evidence carries B as `approver_id`.
- Approval decision audit records B (`approval_approved`), while execution audit records A and links the approval ID/approver evidence.
- Pending approval listing filters through approval -> plan and requires `actor.workspace_id == plan.workspace_id`. Direct approval decision also rejects workspace mismatch before hash/state/execution, leaving approval pending and executor untouched.
- Execution jobs use `(plan_id, plan_hash, idempotency_key)` semantics and state `queued|running|completed|failed|rolled_back`; no `succeeded` state remains in DDL.
- BFF DENY writes only redacted audit and creates no Plan, Confirmation, Approval, ExecutionJob, executor preview, executor execution, or RAG call.
- Executor final `PermissionError` maps to structured `executor_acl_denied`, marks the job failed, writes redacted audit, and cannot be approval-bypassed. Other executor exceptions or non-completed/mismatched results map to structured `executor_execution_failed`, mark the job failed and avoid false `completed`.
- One-time executor credential is not represented in entities, requests, responses, tests, audit details, or repository records.

## Residual risks

1. PostgreSQL repository and migrations remain statically checked only; no real PostgreSQL migration was executed in this task.
2. The file executor and RAG integrations are still contract stubs from the BFF side; no real executor Gate2 adapter was modified or end-to-end tested.
3. The demo service keeps in-memory repository semantics; cross-process locking and race handling for concurrent confirmations/approvals remains a PostgreSQL implementation concern.

