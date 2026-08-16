# Project Learnings

记录项目推进中已经被证据支持、后续应继续遵循的项目经验。

适合记录：

- 项目特定规则。
- 已确认业务口径。
- 固定命名、字段、状态、流程。
- 后续任务需要继续遵守的用户偏好。

不要记录：

- 临时猜测。
- 一次性中间过程。
- 未经确认的偏好。
- 敏感信息。

建议格式：

```md
## 规则或经验标题

- 类型：业务口径 / 命名规则 / 验证方式 / 体验偏好 / 技术约束
- 证据：来自用户确认 / 代码事实 / 测试结果 / 数据结果
- 内容：
- 适用范围：
- 记录时间：
```

---

## [LRN-20260816-001] correction

**Logged**: 2026-08-16
**Priority**: high
**Status**: resolved
**Area**: process

### Summary

总集成拆出"执行线程（executor）"承接 B 类机械执行，Q 授权其可做执行端域内写操作；"不得实现控制面/RAG 重叠功能、不得跨线程决策"仍保留。

### Details

此前 LRN-20260813-001 要求子智能体仅只读验证。Q 于 2026-08-16 放宽：执行线程可做 git 提交/合并、证据落盘、runbook/checklist 起草等 B 类写操作，但仍是总集成下属；不得触碰控制面/RAG 模块所有权，不得裁决集成顺序/Gate/范围/契约，不得 push，不得自行扩大提交范围，不得跨线程协调。归属冲突、测试失败根因不明、清单外需求一律回总集成裁决。

### Suggested Action

给执行线程派活使用固定结构（目标 + 可验证产出 + 文件/命令清单 + 提交信息 + 范围边界 + 回报格式）；执行线程只报事实与原始证据，不做判定。

### Metadata

- Source: user_feedback
- Related Files: docs/agent/thread-handoff-2026-08-14.md, docs/agent/v2-role-map.md, docs/contracts/frozen-v2-integration-contract.md
- Tags: executor, subagent, ownership, write-scope, integration
- Pattern-Key: execution.executor-thread-b-class-writes
- Recurrence-Count: 1
- First-Seen: 2026-08-16
- Last-Seen: 2026-08-16

---

## [LRN-20260813-001] correction

**Logged**: 2026-08-13
**Priority**: high
**Status**: resolved
**Area**: tests

### Summary

执行总负责可以创建子智能体协助验证，但不得让其实现与中台控制面或 RAG 后台重叠的功能。

### Details

用户补充授权：主线程继续承担安全文件执行、共同契约和集成；新建子智能体仅用于只读测试、代码审查或证据核验。中台控制面与 RAG 后台已有固定任务和模块所有权，验证子智能体不得修改或复制这些功能。

### Suggested Action

需要独立证据时可派发边界明确的只读审查，并指定文件范围、禁止写入和禁止跨域实现；功能开发仍由既定三个执行端口按所有权完成。

### Metadata

- Source: user_feedback
- Related Files: docs/contracts/frozen-v1-integration-contract.md
- Tags: subagent, validation, ownership, integration
- Pattern-Key: execution.validation-subagents-only
- Recurrence-Count: 1
- First-Seen: 2026-08-13
- Last-Seen: 2026-08-13

---

## [LRN-20260811-002] correction

**Logged**: 2026-08-11
**Priority**: high
**Status**: resolved
**Area**: infra

### Summary

用户明确授权会话内自动批准后，控制器与子代理必须统一复用批准范围，不能继续逐条弹出同类命令确认。

### Details

子代理继续使用带有不同命令前缀的逐条提权请求，导致测试、日志和报告更新反复要求用户确认。正确做法是把新的批准策略同步给所有后续代理，合并同类非破坏性操作，并使用已经保存的受限命令前缀。

### Suggested Action

本次实施中，读取、测试、项目日志和 Git 检查在既有授权范围内自动执行；删除、重启、Windows 服务安装、防火墙修改和真实工作区写入仍单独确认。

### Metadata

- Source: user_feedback
- Related Files: .superpowers/sdd/2026-08-11-dify-workspace-integration/progress.md
- Tags: approval, powershell, subagent, user-experience
- Pattern-Key: execution.propagate-approval-policy
- Recurrence-Count: 1
- First-Seen: 2026-08-11
- Last-Seen: 2026-08-11

---

## [LRN-20260811-001] best_practice

**Logged**: 2026-08-11
**Priority**: high
**Status**: resolved
**Area**: backend

### Summary

Windows 上使用临时文件原子替换持久化计划时，读和写必须共享同一把计划锁。

### Details

只锁一次性令牌的“检查并消费”不足以保护计划文件。执行完成、失败回滚、恢复流程和并发状态读取都会访问同一个 JSON；任一写回未纳入同一把锁，都可能与读取形成文件占用竞态。

### Suggested Action

新增计划状态或持久化路径时，继续调用统一的 `_read_plan`、`_write_plan`，不要绕过它们直接读取或替换计划 JSON。

### Metadata

- Source: error
- Related Files: service/app/plans.py, service/app/execution.py, service/app/restore.py
- Tags: windows, concurrency, rlock, atomic-replace
- Pattern-Key: windows.atomic-plan-file-lock
- Recurrence-Count: 1
- First-Seen: 2026-08-11
- Last-Seen: 2026-08-11

---
