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

预检先用 `rg --files service/app` 确认真实模块，再从 main.py 追踪环境变量；Docker 状态先检查进程和 `docker info`，只有引擎实际可连通后才进入 Dify UI 配置。

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

## [ERR-20260818-001] thread_tools_declared_missing_despite_existing

**Logged**: 2026-08-18
**Priority**: high
**Status**: open
**Area**: tooling

### Summary

多轮对话反复出现「线程投递 / 交接工具不存在」的错误结论，运行时实测线程工具族全部存在且可调用。

### Error

```text
（模型结论）当前环境没有线程投递 / 消息工具，send_message_to_thread 不可用
（运行时实测 2026-08-18）Object.keys(tools) = 166 项；codex_app__send_message_to_thread /
read_thread / wait_threads / list_threads / list_archived_threads / handoff_thread /
create_thread / fork_thread / set_thread_pinned / set_thread_archived / set_thread_title
均为 function；list_threads 调用成功
```

### Context

- 系统提示词外层工具契约写死「有效工具名恰好是 exec / wait / request_user_input / web_search」，与 exec 内嵌套工具事实冲突。
- exec 声明只列了少量嵌套工具，线程工具未列出；描述声称嵌套工具会列在 `ALL_TOOLS`，实测 `tools.ALL_TOOLS` 为空数组，该发现路径失效。
- 提示词 app 上下文用裸名（create_thread / send_message_to_thread）描述线程工具，运行时真实名字是 `codex_app__` 前缀；按提示词名字探测 `typeof tools.create_thread` = undefined，进一步误导。
- 唯一可靠发现路径是运行时 `Object.keys(tools)`，但提示词未告知模型。
- 次要放大：`docs/agent/thread-archive-sop.md` 已把错误结论「handoff_thread 在当前环境不存在」写入文档，后续会话读 SOP 直接复述，不再重新核查；与 `docs/agent/coordinator-handoff-2026-08-15.md`（handoff_thread 存在）互相矛盾。

### Suggested Fix

1. 任何「工具不存在 / 缺失」结论前，必须先运行时枚举：exec 内 `Object.keys(tools)` 或 `typeof tools.<候选名>`，只读探测后再下结论；「我找不到」≠「不存在」。
2. 线程工具真实名称为 `codex_app__` 前缀（例：`codex_app__send_message_to_thread`），不要用提示词里的裸名。
3. 修正 `thread-archive-sop.md` 第 4 节「handoff_thread 不存在」的错误断言。
4. 根因在系统提示词与运行时不一致（外层契约绝对化 + ALL_TOOLS 为空 + 命名前缀不一致），需向 Codex 产品侧反馈。

### Metadata

- Reproducible: yes
- Related Files: docs/agent/thread-archive-sop.md, docs/agent/coordinator-handoff-2026-08-15.md, C:\Users\tianh\.codex\AGENTS.md
