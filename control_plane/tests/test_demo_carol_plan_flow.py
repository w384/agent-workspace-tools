"""演示身份 carol（计划执行闭环）HTTP 层测试。

覆盖：
- init 种子为 carol（user-c）授 UPLOAD/MOVE_RENAME/TRASH on organized/，且不改变 alice/bob 矩阵；
- carol 实机上传 → 建 move_rename 计划（SELF_CONFIRM）→ 确认 → 执行 VERIFIED（文件真实迁移）；
- carol 建 trash 计划（APPROVAL_REQUIRED）→ 确认 → carol 以审批者身份批准 → 执行 VERIFIED（文件真实删除）；
- 负向：bob 无行动授权 → upload 403 upload_denied、建计划 403 plan_denied。

使用真实 ControlledFileExecutor + ControlledDirectoryVerifier（tmp 目录），验证读回为真实文件系统状态。
"""

import importlib.util
from pathlib import Path

from control_plane.app.controlled_file_executor import ControlledFileExecutor
from control_plane.app.finance_demo_rag import FinanceDemoRagPort
from control_plane.app.main import create_app
from control_plane.app.repository import InMemoryControlPlaneRepository
from control_plane.app.sessions import DemoIdentity
from control_plane.app.verification import ControlledDirectoryVerifier

from conftest import AsgiClient

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEMO_ROOT = PROJECT_ROOT / "work" / "demo" / "financial-preassessment"
SOURCE_ROOT = DEMO_ROOT / "source"
IMPORT_MANIFEST_PATH = DEMO_ROOT / "import-manifest.json"
RULES_PATH = DEMO_ROOT / "rules" / "demo-bank-rules-v1.json"
SCRIPTS_PATH = PROJECT_ROOT / "scripts" / "init_demo_financial_preassessment.py"

EXPIRES_AT = "2099-12-31T23:59:59Z"


def _load_init():
    spec = importlib.util.spec_from_file_location(
        "init_demo_financial_preassessment", SCRIPTS_PATH
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _make_app(repository, controlled_dir: Path):
    controlled_dir.mkdir(parents=True, exist_ok=True)
    rag_port = FinanceDemoRagPort(
        repository=repository,
        source_root=SOURCE_ROOT,
        import_manifest_path=IMPORT_MANIFEST_PATH,
        rules_path=RULES_PATH,
    )
    identities = {
        "alice": DemoIdentity(
            username="alice",
            password="demo-a-password",
            actor_id="user-a",
            workspace_id="workspace-a",
            context_version="acl_2026_08_13",
            group_ids=frozenset({"staff"}),
            role_ids=frozenset({"role-member-demo"}),
        ),
        "bob": DemoIdentity(
            username="bob",
            password="demo-b-password",
            actor_id="user-b",
            workspace_id="workspace-a",
            context_version="acl_2026_08_13",
            group_ids=frozenset({"staff"}),
            role_ids=frozenset({"role-member-demo"}),
        ),
        "carol": DemoIdentity(
            username="carol",
            password="demo-c-password",
            actor_id="user-c",
            workspace_id="workspace-a",
            context_version="acl_2026_08_13",
            group_ids=frozenset({"staff"}),
            role_ids=frozenset({"role-member-demo", "role-approver-demo"}),
        ),
        "dave": DemoIdentity(
            username="dave",
            password="demo-d-password",
            actor_id="user-d",
            workspace_id="workspace-a",
            context_version="acl_2026_08_13",
            group_ids=frozenset({"staff"}),
            role_ids=frozenset({"role-approver-demo"}),
        ),
    }
    return create_app(
        repository=repository,
        file_executor=ControlledFileExecutor(controlled_dir),
        rag_port=rag_port,
        verification_port=ControlledDirectoryVerifier(controlled_dir),
        demo_identities=identities,
        internal_service_key="demo-internal-key",
        approver_role_id="role-approver-demo",
        demo_rules_fixture_path=RULES_PATH,
    )


def _login(client: AsgiClient, username: str, password: str) -> AsgiClient:
    response = client.post(
        "/api/session/login",
        json_body={"username": username, "password": password},
    )
    assert response.status_code == 200
    return client


def _assert_carol_grants(repository) -> None:
    grants = {
        grant.action: grant
        for grant in repository.permission_grants.values()
        if grant.principal_id == "user-c"
    }
    assert {action.name for action in grants} == {"UPLOAD", "MOVE_RENAME", "TRASH"}
    for grant in grants.values():
        assert grant.path_prefix == "organized"
        assert grant.effect.value == "allow"
    # alice/bob 矩阵不变：无任何行动授权（仅种子 QUERY for user-a on 客户模拟资料）
    for principal in ("user-a", "user-b"):
        action_grants = [
            grant
            for grant in repository.permission_grants.values()
            if grant.principal_id == principal
            and grant.action.name in {"UPLOAD", "MOVE_RENAME", "TRASH"}
        ]
        assert action_grants == []


def test_carol_plan_execution_closed_loop_and_bob_denied(tmp_path) -> None:
    init = _load_init()
    repository = InMemoryControlPlaneRepository()
    init.seed_financial_preassessment_demo(repository)
    _assert_carol_grants(repository)

    controlled_dir = tmp_path / "controlled-actions"
    app = _make_app(repository, controlled_dir)
    carol = _login(AsgiClient(app), "carol", "demo-c-password")

    # 1) 计划演示专用上传 organized/report.txt（UPLOAD 直接执行，不走 rag enqueue）
    upload = carol.post(
        "/api/demo/plan-demo/upload",
        files={"file": ("report.txt", b"carol plan flow content 2026", "text/plain")},
    )
    assert upload.status_code == 200
    assert upload.json()["decision"]["state"] == "DIRECT"
    assert (controlled_dir / "organized" / "report.txt").read_bytes() == (
        b"carol plan flow content 2026"
    )

    # 2) move_rename 计划 → SELF_CONFIRM → 确认 → VERIFIED（文件真实迁移）
    plan = carol.post(
        "/api/plans",
        json_body={
            "operations": [
                {
                    "operation_id": "op-move-1",
                    "type": "move_rename",
                    "source_path": "organized/report.txt",
                    "target_path": "organized/report-final.txt",
                }
            ],
            "expires_at": EXPIRES_AT,
        },
    )
    assert plan.status_code == 200
    plan_payload = plan.json()["plan"]
    assert plan_payload["decision_state"] == "SELF_CONFIRM"
    plan_hash = plan_payload["plan_hash"]

    confirmed = carol.post(
        f"/api/plans/{plan_payload['plan_id']}/confirm",
        json_body={"expected_plan_hash": plan_hash},
        headers={"Idempotency-Key": "idem-carol-move-1"},
    )
    assert confirmed.status_code == 200
    confirmed_payload = confirmed.json()
    assert confirmed_payload["execution_job"]["state"] == "verified"
    assert confirmed_payload["plan"]["state"] == "verified"
    assert (controlled_dir / "organized" / "report-final.txt").read_bytes() == (
        b"carol plan flow content 2026"
    )
    assert not (controlled_dir / "organized" / "report.txt").exists()

    # 3) trash 计划 → APPROVAL_REQUIRED → dave（独立审批者）批准 → VERIFIED（文件真实删除）
    trash = carol.post(
        "/api/plans",
        json_body={
            "operations": [
                {
                    "operation_id": "op-trash-1",
                    "type": "trash",
                    "source_path": "organized/report-final.txt",
                }
            ],
            "expires_at": EXPIRES_AT,
        },
    )
    assert trash.status_code == 200
    trash_payload = trash.json()["plan"]
    assert trash_payload["decision_state"] == "APPROVAL_REQUIRED"
    trash_hash = trash_payload["plan_hash"]

    trash_confirmed = carol.post(
        f"/api/plans/{trash_payload['plan_id']}/confirm",
        json_body={"expected_plan_hash": trash_hash},
        headers={"Idempotency-Key": "idem-carol-trash-1"},
    )
    assert trash_confirmed.status_code == 200
    approval_id = trash_confirmed.json()["approval"]["approval_id"]

    # 四眼原则：发起人（carol）不能审批自己的计划
    self_decide = carol.post(
        f"/api/approvals/{approval_id}/decide",
        json_body={"decision": "approved", "expected_plan_hash": trash_hash},
        headers={"Idempotency-Key": "idem-carol-self-approve-1"},
    )
    assert self_decide.status_code == 403
    assert self_decide.json()["error"]["code"] == "approval_forbidden"

    dave = _login(AsgiClient(app), "dave", "demo-d-password")
    pending = dave.get("/api/approvals/pending")
    assert pending.status_code == 200
    assert any(
        item["approval_id"] == approval_id
        for item in pending.json()["approvals"]
    )

    decided = dave.post(
        f"/api/approvals/{approval_id}/decide",
        json_body={"decision": "approved", "expected_plan_hash": trash_hash},
        headers={"Idempotency-Key": "idem-dave-approve-1"},
    )
    assert decided.status_code == 200
    decided_payload = decided.json()
    assert decided_payload["execution_job"]["state"] == "verified"
    assert not (controlled_dir / "organized" / "report-final.txt").exists()

    # 4) 负向：bob 无行动授权 → 403
    bob = _login(AsgiClient(app), "bob", "demo-b-password")
    denied_upload = bob.post(
        "/api/demo/plan-demo/upload",
        files={"file": ("bob-file.txt", b"bob must be denied", "text/plain")},
    )
    assert denied_upload.status_code == 403
    assert denied_upload.json()["error"]["code"] == "upload_denied"

    denied_plan = bob.post(
        "/api/plans",
        json_body={
            "operations": [
                {
                    "operation_id": "op-bob-move-1",
                    "type": "move_rename",
                    "source_path": "organized/anything.txt",
                    "target_path": "organized/elsewhere.txt",
                }
            ],
            "expires_at": EXPIRES_AT,
        },
    )
    assert denied_plan.status_code == 403
    assert denied_plan.json()["error"]["code"] == "plan_denied"
