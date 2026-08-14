# Project Errors

记录项目中已经踩过、后续应避免重复的错误。

建议格式：

```md
## 错误标题

- 现象：
- 原因：
- 修复：
- 下次避免方式：
- 证据：
- 记录时间：
```

只记录有证据支持的错误，不记录临时猜测。

---

## [ERR-20260813-002] restore_snapshot_used_public_path_resolver

**Logged**: 2026-08-13
**Priority**: high
**Status**: resolved
**Area**: backend

### Summary

为所有计划增加源文件指纹时，恢复计划的合法 `.trash` 源被面向公共工作区的路径解析器拒绝。

### Error

```text
ProtectedManagementPathError: 不能访问服务内部管理目录
```

### Context

- 普通计划必须禁止 `.trash` 与 `.file-manager`，但恢复计划的受信 undo action 必须读取 `.trash/<operation_id>/...`。
- 初次兼容修复让 restore 保存空快照，随后完整修复又错误复用了公共路径解析器。
- scoped restore 回归准确暴露了该边界冲突。

### Suggested Fix

不要全局放宽管理目录。恢复源只能使用专用解析：规范化后的绝对路径必须仍位于当前工作区 `.trash` 根内；普通计划继续使用公共工作区解析器。

### Metadata

- Reproducible: yes
- Related Files: service/app/plans.py, service/app/restore.py, service/tests/test_restore.py

### Resolution

- **Resolved**: 2026-08-13
- **Notes**: 源快照函数新增仅供 restore 使用的受控 `.trash` 解析分支；plans/execution/restore scoped 17 passed，主项目 service 111 passed，plugin 103 passed，diff check 通过。

---

## [ERR-20260813-001] mutable_plan_type_integrity_bypass

**Logged**: 2026-08-13
**Priority**: critical
**Status**: resolved
**Area**: backend

### Summary

不能依据计划文件内可变的 `plan_type` 决定是否执行完整性校验。

### Error

```text
普通计划同时被改写为 plan_type=restore 和新目标路径后，原确认令牌仍可执行篡改后的移动。
```

### Context

- 首版 `plan_hash` 只覆盖 `plan_id + operations`，并对 `plan_type=restore` 跳过校验。
- 只读验证子智能体通过临时工作区实际复现了业务文件写入，不是静态推断。
- 该分支可在令牌消费前绕过确认时看到的计划内容。

### Suggested Fix

所有可写计划统一校验；摘要至少绑定计划类型、关联操作编号和规范化操作。恢复计划也必须生成摘要。跨服务 Gate 2 还需由 BFF 保存并回传受信 `expected_plan_hash`，不能只依赖与载荷同存的无密钥摘要。

### Metadata

- Reproducible: yes
- Related Files: service/app/plans.py, service/app/restore.py, service/tests/test_execution.py

### Resolution

- **Resolved**: 2026-08-13
- **Notes**: 已新增绕过回归测试；常规与恢复计划统一计算和校验包含 plan_type、operation_id、operations 的摘要。主项目服务全量 76 passed，插件全量 97 passed，diff check 通过。

---

## [ERR-20260811-002] local_dify_preflight_assumptions

**Logged**: 2026-08-11
**Priority**: low
**Status**: resolved
**Area**: infra

### Summary

本机 Dify 联调预检不应猜测配置模块文件名，也不能仅凭 Docker Desktop 窗口曾启动就假定 Linux Engine 当前可用。

### Error

```text
Get-Content: service/app/configuration.py 不存在
docker ps: 找不到 dockerDesktopLinuxEngine 命名管道
```

### Context

- 进入最小闭环端到端配置前，尝试读取一个未由 `rg --files` 证实的配置文件名。
- 同一只读命令尝试连接 Docker API，但 Docker Linux Engine 当时未提供命名管道。
- 命令没有修改产品文件或真实工作区。

### Suggested Fix

预检先用 `rg --files service/app` 确认真实模块，再从 `main.py` 追踪环境变量；Docker 状态先检查进程和 `docker info`，只有引擎实际可连通后才进入 Dify UI 配置。

### Metadata

- Reproducible: yes
- Related Files: service/app/main.py

### Resolution

- **Resolved**: 2026-08-11
- **Notes**: 已切换为文件清单与进程状态驱动的预检，不再重复猜测路径或假定 Docker 引擎在线。

---

## [ERR-20260811-001] concurrent_plan_file_replace

**Logged**: 2026-08-11
**Priority**: high
**Status**: resolved
**Area**: backend

### Summary

并发执行同一计划时，令牌锁只覆盖消费阶段，执行结果写回可能在 Windows 上因并发读取而触发 `WinError 5`。

### Error

```text
PermissionError: [WinError 5] 计划 JSON 临时文件替换目标文件时被拒绝访问
```

### Context

- API 并发测试同时提交 6 个使用同一令牌的执行请求。
- 令牌消费已经使用每计划 `RLock`，但执行完成后的 `_write_plan` 位于锁外。
- 其他请求读取计划状态时，Windows 可能阻止临时 JSON 替换目标 JSON。

### Suggested Fix

所有计划读写都必须通过同一计划编号对应的可重入锁，而不只是令牌消费阶段加锁。

### Metadata

- Reproducible: yes
- Related Files: service/app/plans.py, service/tests/test_api_execution.py

### Resolution

- **Resolved**: 2026-08-11
- **Notes**: `_read_plan` 和 `_write_plan` 统一复用每计划 `RLock`；并发 API 测试连续多次通过。

---
