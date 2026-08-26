"""Independent read-back verification adapter.

Implements the "可验证执行" (verifiable execution) principle: never trust
the executor's self-report. After an executor claims completion, this
adapter independently reads back the real state of the controlled
directory (file existence + SHA-256) and compares it against the plan's
expected target state derived from asset snapshots.

File-level operations carry their own read-back semantics:
  - upload:      target file must exist with the expected SHA-256 fingerprint;
  - move_rename: source must be gone and target must carry the expected
                 fingerprint;
  - trash:       destructive op — source file must no longer exist (removed
                 from the controlled directory);
  - other op types (create_folder, ...) are reported as UNKNOWN because
    they cannot be independently read back here.
"""

from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path

from .domain import Action, Plan, TrustedActorContext
from .ports import ExecutionResult, VerificationResult, VerificationStatus


def _sha256_fingerprint(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def _read_file_state(path: Path) -> dict[str, object]:
    if not path.is_file():
        return {"exists": False, "content_fingerprint": None, "size_bytes": 0}
    return {
        "exists": True,
        "content_fingerprint": _sha256_fingerprint(path),
        "size_bytes": path.stat().st_size,
    }


def _entry_matches(entry: dict[str, object]) -> bool:
    """Whether a single read-back entry matches the plan's expected state."""
    op_type = entry.get("operation_type")
    if op_type == "upload":
        return entry.get("fingerprint_matches") is True
    if op_type == "move_rename":
        return (
            entry.get("fingerprint_matches") is True
            and entry.get("source_exists") is False
        )
    if op_type == "trash":
        return entry.get("file_removed") is True
    return False


@dataclass(frozen=True, slots=True)
class ControlledDirectoryVerifier:
    """Read-back verifier over a controlled local directory.

    Only verifies file-level operations (upload / move_rename / trash) that
    carry an asset snapshot; other operation types are reported as UNKNOWN
    because they cannot be independently read back here.
    """

    controlled_dir: Path

    def verify(
        self,
        actor: TrustedActorContext,
        plan: Plan,
        execution_result: ExecutionResult,
    ) -> VerificationResult:
        del actor  # read-back relies on disk state, not actor self-claims
        expected_entries: list[dict[str, object]] = []
        actual_entries: list[dict[str, object]] = []
        unverifiable: list[str] = []
        for operation, snapshot in zip(
            plan.normalized_operations, plan.asset_snapshots
        ):
            op_type = Action(str(operation["type"]))
            expected_fingerprint = str(snapshot.get("content_fingerprint", ""))
            if op_type is Action.UPLOAD:
                target = self.controlled_dir / str(operation["source_path"]).lstrip("/")
                expected_entries.append(
                    {
                        "operation_type": "upload",
                        "path": str(operation["source_path"]),
                        "expected_fingerprint": expected_fingerprint,
                    }
                )
                actual = _read_file_state(target)
                actual_entries.append(
                    {
                        "operation_type": "upload",
                        "path": str(operation["source_path"]),
                        **actual,
                        "fingerprint_matches": (
                            actual.get("content_fingerprint") == expected_fingerprint
                        ),
                    }
                )
            elif op_type is Action.MOVE_RENAME:
                source = self.controlled_dir / str(operation["source_path"]).lstrip("/")
                target = self.controlled_dir / str(operation["target_path"]).lstrip("/")
                expected_entries.append(
                    {
                        "operation_type": "move_rename",
                        "source_path": str(operation["source_path"]),
                        "target_path": str(operation["target_path"]),
                        "expected_fingerprint": expected_fingerprint,
                    }
                )
                source_exists = source.exists()
                target_state = _read_file_state(target)
                actual_entries.append(
                    {
                        "operation_type": "move_rename",
                        "source_path": str(operation["source_path"]),
                        "target_path": str(operation["target_path"]),
                        "source_exists": source_exists,
                        **target_state,
                        "fingerprint_matches": (
                            target_state.get("content_fingerprint") == expected_fingerprint
                        ),
                    }
                )
            elif op_type is Action.TRASH:
                source = self.controlled_dir / str(operation["source_path"]).lstrip("/")
                expected_entries.append(
                    {
                        "operation_type": "trash",
                        "path": str(operation["source_path"]),
                    }
                )
                source_exists = source.exists()
                actual_entries.append(
                    {
                        "operation_type": "trash",
                        "path": str(operation["source_path"]),
                        "source_exists": source_exists,
                        "file_removed": not source_exists,
                    }
                )
            else:
                unverifiable.append(str(operation.get("operation_id", "")))

        if unverifiable:
            return VerificationResult(
                status=VerificationStatus.UNKNOWN,
                operation_id=execution_result.operation_id,
                matched=False,
                expected_state={"entries": expected_entries},
                actual_state={"entries": actual_entries},
                evidence={"unverifiable_operation_ids": unverifiable},
                reason="independent_readback_unavailable",
            )

        if not actual_entries:
            return VerificationResult(
                status=VerificationStatus.UNKNOWN,
                operation_id=execution_result.operation_id,
                matched=False,
                expected_state={"entries": expected_entries},
                actual_state={"entries": actual_entries},
                evidence={},
                reason="no_file_level_operations_to_read_back",
            )

        all_match = all(_entry_matches(entry) for entry in actual_entries)
        if all_match:
            return VerificationResult(
                status=VerificationStatus.VERIFIED,
                operation_id=execution_result.operation_id,
                matched=True,
                expected_state={"entries": expected_entries},
                actual_state={"entries": actual_entries},
                evidence={
                    "read_back": "controlled_directory",
                    "entries_checked": len(actual_entries),
                },
                reason="",
            )
        mismatch_reason = (
            "trash_readback_failed"
            if any(
                entry.get("operation_type") == "trash"
                and entry.get("file_removed") is not True
                for entry in actual_entries
            )
            else "readback_fingerprint_mismatch"
        )
        return VerificationResult(
            status=VerificationStatus.MISMATCH,
            operation_id=execution_result.operation_id,
            matched=False,
            expected_state={"entries": expected_entries},
            actual_state={"entries": actual_entries},
            evidence={
                "read_back": "controlled_directory",
                "entries_checked": len(actual_entries),
                "mismatched_entries": sum(
                    1 for entry in actual_entries if not _entry_matches(entry)
                ),
            },
            reason=mismatch_reason,
        )