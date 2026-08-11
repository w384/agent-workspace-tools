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
