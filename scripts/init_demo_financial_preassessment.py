"""One-click idempotent initializer for the financial pre-assessment demo state.

E3 (P0) of the v2 finance demo slice. The script:

- wires the demo login identity (alice / demo-a-password) when serving;
- creates controlled Asset/AssetVersion entries declared by the import
  manifest, bound to the real SHA-256 of the fictional source files;
- creates one demo_fixture RuleVersion bound to the controlled rules fixture
  fingerprint;
- is idempotent: re-running never duplicates assets, versions, rules or audits.
- prints the seeded asset IDs and rule version IDs for runbook reference; the
  "MATCH 100" /demo A assessment self-check is covered by
  control_plane/tests/test_init_demo_financial_preassessment.py.

Usage:
  python scripts/init_demo_financial_preassessment.py                # seed + serve /demo
  python scripts/init_demo_financial_preassessment.py --seed-only     # seed, print summary, exit
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from control_plane.app.domain import (
    Action,
    AuditEvent,
    GrantEffect,
    PermissionGrant,
    PrincipalType,
    RuleSet,
    RuleVersion,
    TrustedActorContext,
)
from control_plane.app.repository import InMemoryControlPlaneRepository

DEMO_ROOT = PROJECT_ROOT / "work" / "demo" / "financial-preassessment"
SOURCE_ROOT = DEMO_ROOT / "source"
IMPORT_MANIFEST_PATH = DEMO_ROOT / "import-manifest.json"
RULES_PATH = DEMO_ROOT / "rules" / "demo-bank-rules-v1.json"

SCENARIO = "finance_profile_matching"
SOURCE_TYPE = "demo_fixture"
VERSION_LABEL = "demo-2026-08-14"
QUERY_PATH_PREFIX = "客户模拟资料"
GRANT_ID = "finance-demo-query-seed"
WORKSPACE_ID = "workspace-a"
ACTOR_ID = "user-a"
CONTEXT_VERSION = "acl_2026_08_13"
RULE_SUMMARY = "受控虚构演示规则，不含真实银行规则。"
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8891


def seed_financial_preassessment_demo(
    repository: InMemoryControlPlaneRepository,
    *,
    source_root: Path = SOURCE_ROOT,
    import_manifest_path: Path = IMPORT_MANIFEST_PATH,
    rules_path: Path = RULES_PATH,
    workspace_id: str = WORKSPACE_ID,
    actor_id: str = ACTOR_ID,
    context_version: str = CONTEXT_VERSION,
) -> dict[str, object]:
    """Seed (or re-confirm) the demo state; idempotent by design."""
    manifest = _read_json(import_manifest_path)
    _require_keys(manifest, "source_type", "scenario", "assets")
    if manifest["source_type"] != SOURCE_TYPE or manifest["scenario"] != SCENARIO:
        raise ValueError("import manifest is not a controlled finance demo fixture")

    rules = _read_json(rules_path)
    _require_keys(rules, "source_type", "scenario", "version_label", "content_fingerprint")
    if (
        rules["source_type"] != SOURCE_TYPE
        or rules["scenario"] != SCENARIO
        or rules["version_label"] != VERSION_LABEL
    ):
        raise ValueError("rules fixture is not the controlled finance demo ruleset")
    fixture_fingerprint = rules["content_fingerprint"]
    _require_sha256_fingerprint(fixture_fingerprint)
    if fixture_fingerprint != _canonical_rules_fingerprint(rules):
        raise ValueError("rules fixture fingerprint does not match its content")

    actor = TrustedActorContext(
        actor_id=actor_id,
        workspace_id=workspace_id,
        context_version=context_version,
        session_id="seed-session",
        request_id="seed-request",
        run_id="seed-run",
        role_ids=frozenset({"role-member-demo"}),
    )
    created_assets = 0
    created_rule_versions = 0

    if GRANT_ID not in repository.permission_grants:
        repository.add_permission_grant(
            PermissionGrant(
                grant_id=GRANT_ID,
                workspace_id=workspace_id,
                context_version=context_version,
                principal_type=PrincipalType.USER,
                principal_id=actor_id,
                action=Action.QUERY,
                path_prefix=QUERY_PATH_PREFIX,
                effect=GrantEffect.ALLOW,
            )
        )

    for entry in manifest["assets"]:
        if not isinstance(entry, dict) or set(entry) != {"relative_path", "material_key"}:
            raise ValueError("import manifest asset declarations are invalid")
        relative_path = entry["relative_path"]
        existing = repository.find_asset_by_path(workspace_id, relative_path)
        if existing is not None and existing.active_version_id is not None:
            continue
        source_path = _declared_source_path(source_root, relative_path)
        fingerprint = "sha256:" + hashlib.sha256(source_path.read_bytes()).hexdigest()
        asset = repository.get_or_create_asset(
            workspace_id, relative_path, Path(relative_path).name, actor_id
        )
        version = repository.create_asset_version(
            asset.asset_id, fingerprint, relative_path
        )
        for state in ("parsing", "indexed", "ready"):
            repository.transition_asset_version(version.asset_version_id, state)
        repository.activate_asset_version(version.asset_version_id)
        repository.append_audit_event(
            _audit_event(
                event_type="asset_version_created",
                actor=actor,
                details={
                    "asset_id": asset.asset_id,
                    "asset_version_id": version.asset_version_id,
                    "version_number": version.version_number,
                },
            )
        )
        created_assets += 1

    if _find_fixture_rule_version(repository, fixture_fingerprint) is None:
        rule_set = repository.create_rule_set(
            RuleSet(str(uuid.uuid4()), SCENARIO, rules["rule_set_name"], "active")
        )
        rule_version = repository.create_rule_version(
            RuleVersion(
                rule_version_id=str(uuid.uuid4()),
                rule_set_id=rule_set.rule_set_id,
                source_type=SOURCE_TYPE,
                version_label=VERSION_LABEL,
                content_fingerprint=fixture_fingerprint,
                created_at=_utc_now(),
                redacted_rule_summary=RULE_SUMMARY,
            )
        )
        repository.append_audit_event(
            _audit_event(
                event_type="rule_version_created",
                actor=actor,
                details={
                    "scenario": SCENARIO,
                    "rule_set_id": rule_set.rule_set_id,
                    "rule_version_id": rule_version.rule_version_id,
                    "source_type": SOURCE_TYPE,
                    "version_label": VERSION_LABEL,
                },
            )
        )
        created_rule_versions += 1

    assets = repository.list_assets(workspace_id)
    rule_versions = [
        item
        for item in repository.rule_versions.values()
        if item.source_type == SOURCE_TYPE
    ]
    return {
        "asset_count": len(assets),
        "active_version_count": sum(
            1 for asset in assets if asset.active_version_id is not None
        ),
        "rule_version_count": len(rule_versions),
        "assets_created": created_assets,
        "rule_versions_created": created_rule_versions,
        "assets": [
            {
                "asset_id": asset.asset_id,
                "path": asset.path,
                "active_version_id": asset.active_version_id,
            }
            for asset in assets
        ],
        "rule_versions": [
            {
                "rule_version_id": item.rule_version_id,
                "rule_set_id": item.rule_set_id,
                "version_label": item.version_label,
                "content_fingerprint": item.content_fingerprint,
            }
            for item in rule_versions
        ],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--seed-only",
        action="store_true",
        help="seed the demo state, print a summary and exit without serving",
    )
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    args = parser.parse_args(argv)

    repository = InMemoryControlPlaneRepository()
    summary = seed_financial_preassessment_demo(repository)
    print("demo seed summary: " + json.dumps(summary, ensure_ascii=False))
    if args.seed_only:
        print("demo login: alice / demo-a-password (wired when serving /demo)")
        return 0

    import uvicorn

    from control_plane.app.finance_demo_llm_rag import FinanceDemoLlmRagPort
    from control_plane.app.main import create_app
    from control_plane.app.sessions import DemoIdentity

    rag_port = FinanceDemoLlmRagPort(
        repository=repository,
        source_root=SOURCE_ROOT,
        import_manifest_path=IMPORT_MANIFEST_PATH,
        rules_path=RULES_PATH,
        workspace_id=WORKSPACE_ID,
    )
    app = create_app(
        repository=repository,
        file_executor=object(),
        rag_port=rag_port,
        demo_identities={
            "alice": DemoIdentity(
                username="alice",
                password="demo-a-password",
                actor_id=ACTOR_ID,
                workspace_id=WORKSPACE_ID,
                context_version=CONTEXT_VERSION,
                group_ids=frozenset({"staff"}),
                role_ids=frozenset({"role-member-demo"}),
            ),
            "bob": DemoIdentity(
                username="bob",
                password="demo-b-password",
                actor_id="user-b",
                workspace_id=WORKSPACE_ID,
                context_version=CONTEXT_VERSION,
                group_ids=frozenset({"staff"}),
                role_ids=frozenset({"role-member-demo"}),
            ),
        },
        internal_service_key="demo-internal-key",
        approver_role_id="role-approver-demo",
        demo_rules_fixture_path=RULES_PATH,
    )
    print(
        "serving /demo at http://"
        f"{args.host}:{args.port}  (logins: alice / demo-a-password, "
        "bob / demo-b-password [no-query user])"
    )
    uvicorn.run(app, host=args.host, port=args.port)
    return 0


def _read_json(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("finance demo fixture must be a JSON object")
    return payload


def _require_keys(payload: dict[str, object], *keys: str) -> None:
    if not all(key in payload for key in keys):
        raise ValueError("finance demo fixture is missing required fields")


def _require_sha256_fingerprint(content_fingerprint: object) -> None:
    if not isinstance(content_fingerprint, str):
        raise ValueError("finance demo fingerprint must be a string")
    algorithm, separator, digest = content_fingerprint.partition(":")
    if (
        algorithm != "sha256"
        or separator != ":"
        or len(digest) != 64
        or any(character not in "0123456789abcdef" for character in digest)
    ):
        raise ValueError("finance demo fingerprint must be a sha256 digest")


def _canonical_rules_fingerprint(rules: dict[str, object]) -> str:
    canonical_payload = {
        key: value for key, value in rules.items() if key != "content_fingerprint"
    }
    return "sha256:" + hashlib.sha256(
        json.dumps(
            canonical_payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


def _declared_source_path(source_root: Path, relative_path: str) -> Path:
    source_path = (source_root / relative_path).resolve()
    try:
        source_path.relative_to(source_root.resolve())
    except ValueError as error:
        raise ValueError("finance demo source path escapes controlled root") from error
    if not source_path.is_file():
        raise ValueError("finance demo declared source does not exist")
    return source_path


def _find_fixture_rule_version(
    repository: InMemoryControlPlaneRepository, fixture_fingerprint: str
) -> RuleVersion | None:
    for rule_version in repository.rule_versions.values():
        if (
            rule_version.source_type == SOURCE_TYPE
            and rule_version.version_label == VERSION_LABEL
            and rule_version.content_fingerprint == fixture_fingerprint
        ):
            return rule_version
    return None


def _audit_event(
    *,
    event_type: str,
    actor: TrustedActorContext,
    details: dict[str, object],
) -> AuditEvent:
    return AuditEvent(
        event_id=str(uuid.uuid4()),
        event_type=event_type,
        actor_id=actor.actor_id,
        request_id=actor.request_id,
        run_id=actor.run_id,
        details=details,
    )


def _utc_now() -> str:
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


if __name__ == "__main__":
    raise SystemExit(main())
