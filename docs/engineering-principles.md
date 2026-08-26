# 工程指导思想（Engineering Principles）

本文档是 `agent-workspace-tools` 的权威工程锚点，用于统一后续所有方向修正、功能设计与验收口径。当出现方向性分歧时，以本文档为准。

## 一、工程定位

`agent-workspace-tools` 不是通用 Agent 平台，不是知识库产品，也不是 ERP/MES 的替代品。

它的定位是：

> **企业 Agent 行动安全网关（Agent Action Gateway）**
> 为任意 Agent、任意模型、任意业务系统之间的真实业务动作，提供统一的身份、策略、审批、执行验证、审计与恢复边界。

它不替换：

- Codex、Dify、企业微信、飞书、WorkBuddy 或自研 Agent；
- 企业的 ERP、MES、CRM、OA、文件库、数据库；
- 企业现有身份系统与审批流程。

它要控制的是：

```
Agent 想要执行真实动作的最后一公里
```

## 二、核心产品判断

企业真正担心的不是「Agent 能不能调用工具」，而是：

> 这个 Agent 代表谁？
> 它为什么有这个权限？
> 这个动作影响什么？
> 谁批准了？
> 它到底有没有真的执行成功？
> 失败后谁知道、谁处理、如何恢复？

因此，工程的核心价值不在「工具数量」，而在「行动证据链」：

```
任何 Agent
   ↓
Action Gateway
   ↓
Identity / User Context
   ↓
Policy Decision
   ↓
Plan Preview
   ↓
Confirmation / Approval
   ↓
Controlled Adapter Execution
   ↓
Independent Read-back Verification
   ↓
Audit / Recovery / Escalation
```

## 三、第一原则：不信任 Agent 的自我声明

Agent、模型、MCP 工具、执行器都可能：

- 误解任务；
- 使用错误参数；
- 越权调用；
- 声称执行成功但实际失败；
- 因网络、超时、重试导致重复执行；
- 被 Prompt Injection 诱导；
- 返回看似合理但不可验证的结果。

因此系统必须遵守：

> **Agent 说「我做完了」，不等于业务已经完成。**

只有当系统从目标业务系统独立读回状态，并确认实际结果符合批准计划时，才可以标记：

```
VERIFIED
```

否则必须明确进入：

```
MISMATCH
UNKNOWN
NEEDS_RECOVERY
ESCALATED
```

> 注：指导思想原文在「Agent 和执行器都说……」处中断，此处按语义补全为「Agent 和执行器都说执行成功了，但独立读回发现真实状态与批准计划不一致，系统拒绝标记 VERIFIED，并进入恢复/升级流程」，属转写补全。

## 四、工程唯一主线：从「受控执行」升级为「可验证执行」

当前工程中已实现并应继续保留的基础：

- 可信 Actor Context
- Policy
- 风险分级
- Plan + Plan Hash
- ACL / Context Snapshot
- Confirmation
- Approval
- Idempotency
- Execution Job
- Audit Event
- MCP 暴露
- 权限感知检索与资料版本化

下一阶段的核心不是再增加 Agent 功能，而是新增：

```
Verification Adapter
```

它必须能回答：

| 问题 | 系统应给出的证据 |
| --- | --- |
| 动作期望改变什么？ | 批准的目标状态与字段 |
| 实际写入了什么？ | 执行器返回的操作标识和摘要 |
| 业务系统当前真实状态是什么？ | 独立读回结果 |
| 是否与计划一致？ | 字段级或状态级比对 |
| 不一致时怎么办？ | 阻止伪成功、生成异常事件 |
| 是否可恢复？ | 补偿动作、人工处理或升级路径 |

工程后续最有价值的演示不是「Agent 成功调用了 ERP 工具」，而是：

> 「Agent 和执行器都说执行成功了，但独立读回发现状态不一致，系统拒绝标记 VERIFIED 并进入恢复流程。」

## 五、验证状态机与语义

| 状态 | 含义 | 系统行为 |
| --- | --- | --- |
| VERIFIED | 独立读回与批准计划一致 | 应用路径更新，job/plan → verified，审计 `execution_verified` |
| MISMATCH | 独立读回发现实际状态与预期不符 | 不应用路径更新，job/plan → mismatch，审计 `execution_verification_failed`，抛 `VerificationMismatchError`，阻止伪成功 |
| UNKNOWN | 无法独立读回 / 无法判定 | 不标记 verified，job/plan → unknown，审计 `execution_verification_failed` |
| NEEDS_RECOVERY | 动作未按预期落地，需要恢复 | 已实现：job/plan → needs_recovery，自动创建 RecoveryTask（strategy=auto_compensation，state=pending），审计 recovery_task_created |
| ESCALATED | 需人工 / 上级升级处理 | 已实现：job/plan → escalated，自动创建 RecoveryTask（strategy=escalate，state=pending），审计 recovery_task_created |

### 五.1 恢复 / 升级闭环（Recovery Task）

验证失败（MISMATCH / UNKNOWN / NEEDS_RECOVERY / ESCALATED）不再停留在静态
异常状态，而是进入可处理的恢复闭环：

- 自动创建 RecoveryTask（state=pending），strategy 按状态映射：
  MISMATCH → retry_compensation、UNKNOWN → manual_review、
  NEEDS_RECOVERY → auto_compensation、ESCALATED → escalate；
  审计事件 recovery_task_created。
- GET /api/recovery-tasks 按 workspace 隔离列出 pending 恢复任务。
- POST /api/recovery-tasks/{id}/resolve：decision=recovered → task/plan →
  recovered（审计 recovery_resolved）；decision=escalated → task/plan →
  escalated（审计 recovery_escalated）。任务已处理 / 非法 decision → 409，
  未知 id → 404。
- confirm_plan / decide_approval 触发验证失败时返回 422
  verification_failed，并在 error.details.recovery_task 附带最新 pending
  任务，供前端引导恢复 / 升级动作。

## 六、兼容与演进

- 现阶段 `verification_port` 为可选注入：未提供时保持既有 `completed` 行为（兼容现有测试与既有演示）；提供时执行后强制独立读回验证。
- 「强制验证」为后续演进项：验证成为必选，无验证适配器的执行一律不允许标记完成。
- 首个真实验证适配器：对受控本地目录做真实读回（文件存在 + SHA-256 指纹比对），支撑「执行器谎报 vs 实际未写入」负向演示。
- 文件级操作读回语义：upload 期望目标存在且指纹一致；move_rename 期望源消失且目标指纹一致；trash（破坏性操作）期望源文件已从受控目录消失——文件仍存在即 MISMATCH（reason=trash_readback_failed），阻断「伪删除」。
- 演示服务接线（init 脚本）：已从占位 file_executor=object() 切换为真实受控目录执行器（ControlledFileExecutor，受控根 work/demo/financial-preassessment/controlled-actions/，所有操作路径 resolve 后必须仍位于受控根内，越界抛 PermissionError fail-closed）+ 同根独立读回验证器（ControlledDirectoryVerifier）。被授权的计划在运行中的 /demo 服务上真实执行并可读回验证；无授权时仍由 policy 层先行拒绝，执行器层防御不替代策略层。
