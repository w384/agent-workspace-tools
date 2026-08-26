"""真实受控目录执行器（批次 C）。

实现 FileExecutorPort，让运行中的演示服务能真正走通
「计划→确认→执行→独立读回验证」闭环，而不是 init 脚本里的 file_executor=object()。

设计（fail-closed）：
  - 所有操作路径都必须 resolve 后仍位于受控根目录内；越界直接抛
    PermissionError（执行器层防御，不依赖 policy 层先拦截）；
  - upload       真实写盘 controlled_dir/<directory>/<file_name>，返回真实
                  SHA-256 的 UploadResult（重复目标抛 FileExistsError）；
  - create_plan  校验路径并按 executor_plan_id 记录规范化操作；executor_plan_hash
                  为占位摘要，真实计划哈希由控制面校验（PlanHashMismatchError）；
  - confirm_and_execute 重放已记录操作：
                    move_rename -> shutil.move(source -> target)
                    trash      -> 删除源文件
                    upload     -> 仅复验目标已存在
                  返回 ExecutionResult(status="completed")。
"""

from hashlib import sha256
from pathlib import Path
from uuid import uuid4

from .domain import Action, TrustedActorContext
from .ports import ExecutionResult, FilePlanPreview, UploadResult


def _fingerprint(content: bytes) -> str:
    return "sha256:" + sha256(content).hexdigest()


class ControlledFileExecutor:
    def __init__(self, controlled_dir: Path) -> None:
        self._controlled_dir = Path(controlled_dir)
        self._plans: dict[str, tuple[dict[str, object], ...]] = {}

    def _safe_path(self, *parts: str) -> Path:
        root = self._controlled_dir.resolve()
        candidate = root.joinpath(*parts).resolve()
        try:
            candidate.relative_to(root)
        except ValueError as error:
            raise PermissionError("operation path escapes controlled root") from error
        return candidate

    def _validate_operation_paths(self, operation: dict[str, object]) -> None:
        operation_type = str(operation["type"])
        self._safe_path(str(operation["source_path"]))
        if operation_type == Action.MOVE_RENAME.value:
            self._safe_path(str(operation["target_path"]))

    def upload(
        self,
        actor: TrustedActorContext,
        directory: str,
        file_name: str,
        content: bytes,
        request_id: str,
    ) -> UploadResult:
        del actor, request_id
        target = self._safe_path(directory, file_name)
        if target.exists():
            raise FileExistsError("upload target already exists")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
        return UploadResult(
            path=f"{directory.rstrip('/')}/{file_name}",
            name=file_name,
            size_bytes=len(content),
            content_fingerprint=_fingerprint(content),
        )

    def create_plan(
        self,
        actor: TrustedActorContext,
        normalized_operations: tuple[dict[str, object], ...],
        asset_snapshots: tuple[dict[str, str], ...],
        acl_snapshot: dict[str, object],
        policy_version: str,
        expires_at: str,
        idempotency_key: str,
    ) -> FilePlanPreview:
        del actor, asset_snapshots, acl_snapshot, policy_version, expires_at, idempotency_key
        for operation in normalized_operations:
            self._validate_operation_paths(operation)
        executor_plan_id = str(uuid4())
        self._plans[executor_plan_id] = tuple(normalized_operations)
        impact = "; ".join(
            (
                f"{operation['operation_id']}: {operation['type']} "
                f"{operation['source_path']}"
                + (
                    f" -> {operation['target_path']}"
                    if str(operation["type"]) == Action.MOVE_RENAME.value
                    else ""
                )
            )
            for operation in normalized_operations
        )
        return FilePlanPreview(
            impact_summary=impact or "no operations",
            executor_plan_id=executor_plan_id,
            executor_plan_hash="sha256:" + "e" * 64,
        )

    def confirm_and_execute(
        self,
        actor: TrustedActorContext,
        control_plan_id: str,
        executor_plan_id: str,
        executor_plan_hash: str,
        expected_plan_hash: str,
        asset_snapshots: tuple[dict[str, str], ...],
        acl_snapshot: dict[str, object],
        decision: dict[str, object],
        confirmation_evidence: dict[str, object],
        approval_evidence: dict[str, object] | None,
        idempotency_key: str,
    ) -> ExecutionResult:
        del (
            actor,
            control_plan_id,
            executor_plan_hash,
            expected_plan_hash,
            asset_snapshots,
            acl_snapshot,
            decision,
            confirmation_evidence,
            approval_evidence,
            idempotency_key,
        )
        operations = self._plans.get(executor_plan_id)
        if operations is None:
            raise RuntimeError(f"unknown executor plan: {executor_plan_id}")
        for operation in operations:
            self._validate_operation_paths(operation)
            operation_type = str(operation["type"])
            if operation_type == Action.MOVE_RENAME.value:
                source = self._safe_path(str(operation["source_path"]))
                target = self._safe_path(str(operation["target_path"]))
                if not source.exists():
                    raise FileNotFoundError(f"move source missing: {source}")
                target.parent.mkdir(parents=True, exist_ok=True)
                source.rename(target)
            elif operation_type == Action.TRASH.value:
                source = self._safe_path(str(operation["source_path"]))
                if source.exists():
                    source.unlink()
            elif operation_type == Action.UPLOAD.value:
                target = self._safe_path(str(operation["source_path"]))
                if not target.exists():
                    raise FileNotFoundError(f"upload target missing: {target}")
            else:
                raise RuntimeError(f"unsupported operation type: {operation_type}")
        return ExecutionResult(status="completed", operation_id="op-1")
