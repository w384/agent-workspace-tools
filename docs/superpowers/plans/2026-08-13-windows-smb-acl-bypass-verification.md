# Windows/SMB ACL 旁路写验证 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在不触碰真实业务文件的前提下，证明普通 Windows/SMB 用户不能绕过统一入口写入 DEMO 公共盘，而 FastAPI 执行器服务账号可以通过受控执行路径写入专用验证目录。

**阶段口径：** 这是冻结 v1 内的“Windows/SMB 旁路写环境实测阶段”，不是解冻架构、解除冻结 v1、生产闭环或整个企业公共盘安全结论。

**Architecture:** 使用一个隔离的 SMB 子目录和两个不同的 Windows 身份：`普通成员` 只具读取权限，`执行器服务账号` 具修改权限。先验证共享与 NTFS 的有效 ACL，再分别从成员身份做直接 SMB 写入负向测试、从执行器实际进程身份经 FastAPI 做正向执行测试；两组证据与哈希一同保留。

**Tech Stack:** Windows NTFS ACL、SMB share ACL、`icacls`、PowerShell、FastAPI 本地服务、现有 `/plans -> approval-token -> /execute` 受控路径。

## Global Constraints

- 不修改冻结纲要正文，不提交、不推送、不发布，不安装外部系统。
- 必须在专用验证子目录执行，绝不对 `D:\AI\AgentWorkspace` 根或真实业务文件做 ACL 重置、递归授权、删除或写入。
- 只有 Q 或获授权的 Windows 管理员执行账号创建、改 ACL、运行身份切换和清理；本计划本身不授予这些操作。
- FastAPI 是公共盘唯一写入边界；普通成员的直接 Windows/SMB 写成功即为失败结果，不得被确认或审批流程解释为可接受。
- 所有输出不得含 API Key、Windows 密码、SMB 凭据或一次性令牌；只记录账号 SID、ACL 摘要、命令退出码、错误类别和文件哈希。
- 若 FastAPI 当前不是独立的非交互服务账号运行，停止在基线核对，不宣称已证明旁路不可写。
- 未获得 Q 对四项前置条件的明确确认与管理员 ACL 操作授权前，只允许 Task 1 的只读核对；不得创建验证目录、修改 ACL、发起写测试或清理。

---

## 环境契约

本计划执行前由 Q 明确确认并授权以下四项；未确认任何一项即停止，不创建目录、不改 ACL、不做写测试或清理：

| 角色 | 必须满足的实际条件 |
| --- | --- |
| `执行器服务账号` | Windows 本地或域服务账号；运行 FastAPI 进程；不是 Q 的交互账号；具可审计 SID。 |
| `普通成员` | 与执行器服务账号不同的 Windows 本地或域账号；映射到 DEMO 的普通业务成员；不属于 Administrators。 |
| `管理员` | 仅用于创建隔离目录、设置 ACL、读取 SMB ACL、最终清理；不参与负向写入验证。 |
| `验证目录` | `D:\AI\AgentWorkspace\_acl-bypass-demo-20260813`；必须为空、专用、无业务文件。 |
| `SMB UNC` | 指向验证目录的实际 UNC，例如现有共享下的 `\\<服务器>\<共享名>\_acl-bypass-demo-20260813`；不得使用管理员隐藏共享。 |

四项授权分别是：独立执行器服务账号、普通成员测试账号、专用目录与对应 UNC、仅限专用目录的管理员 ACL 设置/验证/清理授权。共享根、公共盘根和真实业务目录始终不在授权范围内。

如果当前 FastAPI 由 Q 的交互 Windows 身份运行，下一阶段应先由 Q 决定是否创建独立服务账号和最小运行方式；在此之前只能保留“应用逻辑本地验收”结论。

### Task 1: 只读身份、共享和目录前置核对

**Files:**
- Create: `D:\AI\Codex\Documents\acl-bypass-evidence\2026-08-13\baseline.txt`（由 Q 在实测时保存输出）
- Read: 现有 FastAPI 进程、目标 SMB 共享、`D:\AI\AgentWorkspace`

**Interfaces:**
- Consumes: Q 提供的实际执行器 PID、普通成员用户名、目标共享名和 UNC。
- Produces: 服务进程账号、服务账号 SID、普通成员 SID、共享 ACL、验证目录不存在或为空的基线证据。

- [ ] **Step 1: 在管理员 PowerShell 核对 FastAPI 运行身份**

```powershell
$FastApiPid = <Q确认的FastAPI进程PID>
Get-Process -Id $FastApiPid -IncludeUserName | Select-Object Id, ProcessName, UserName
whoami /user
```

预期：`UserName` 是已确认的执行器服务账号，且不等于普通成员或 Q 的交互账号。若无法读取 UserName，停止并由 Q 以管理员身份获取同等进程身份证据。

- [ ] **Step 2: 只读核对 SMB 与 NTFS 当前有效 ACL**

```powershell
$DemoRoot = 'D:\AI\AgentWorkspace\_acl-bypass-demo-20260813'
Get-SmbShare | Select-Object Name, Path, Description
Get-SmbShareAccess -Name <Q确认的共享名>
if (Test-Path -LiteralPath $DemoRoot) { icacls $DemoRoot }
```

预期：可识别验证目录将映射的共享；记录共享级权限和目录 ACL，但此步不改变任何 ACL。

- [ ] **Step 3: 保存脱敏基线证据**

```powershell
$EvidenceRoot = 'D:\AI\Codex\Documents\acl-bypass-evidence\2026-08-13'
New-Item -ItemType Directory -Force -Path $EvidenceRoot | Out-Null
Get-Process -Id $FastApiPid -IncludeUserName | Select-Object Id, ProcessName, UserName |
  Out-File -LiteralPath "$EvidenceRoot\baseline.txt" -Encoding utf8
```

预期：只保存用户名、SID、ACL 和命令结果；不保存密码、API Key 或令牌。

### Task 2: 在隔离子目录配置最小 ACL

**Files:**
- Create: `D:\AI\AgentWorkspace\_acl-bypass-demo-20260813`（仅 Q/管理员创建）
- Create: `D:\AI\Codex\Documents\acl-bypass-evidence\2026-08-13\acl.txt`

**Interfaces:**
- Consumes: Task 1 已确认的执行器服务账号、普通成员、验证目录与共享 UNC。
- Produces: 继承关闭的 NTFS ACL：执行器 Modify、普通成员 Read & Execute、SYSTEM/Administrators Full Control。

- [ ] **Step 1: 创建空的专用验证目录，拒绝对根目录或递归路径操作**

```powershell
$DemoRoot = 'D:\AI\AgentWorkspace\_acl-bypass-demo-20260813'
if (Test-Path -LiteralPath $DemoRoot) { throw '验证目录已存在；先人工确认其为空且无业务文件。' }
New-Item -ItemType Directory -Path $DemoRoot -ErrorAction Stop | Out-Null
```

预期：只创建一个空目录；若路径已存在则停止，不覆盖或清理。

- [ ] **Step 2: 关闭继承并授予最小 NTFS 权限**

```powershell
$Executor = <Q确认的执行器服务账号>
$Member = <Q确认的普通成员账号>
icacls $DemoRoot /inheritance:r
icacls $DemoRoot /grant:r `
  "$Executor:(OI)(CI)M" `
  "$Member:(OI)(CI)RX" `
  'SYSTEM:(OI)(CI)F' `
  'BUILTIN\Administrators:(OI)(CI)F'
icacls $DemoRoot
```

预期：输出中普通成员只有 `RX`，执行器有 `M`；任何 inherited 或宽泛写入 ACE 都必须先由 Q 评估，不能自动删除共享根的 ACE。

- [ ] **Step 3: 核对 SMB 共享层不会额外授予普通成员写权限**

```powershell
Get-SmbShareAccess -Name <Q确认的共享名>
```

预期：即使共享层较宽，NTFS 的普通成员 `RX` 也必须令有效写入失败；若共享层单独授予普通成员或 Everyone Change/Full，记录为风险并由 Q 决定是否在专用共享上收紧，不能修改现有业务共享。

### Task 3: 普通成员直接 SMB 旁路写负向验证

**Files:**
- Create only if executor succeeds first: `D:\AI\AgentWorkspace\_acl-bypass-demo-20260813\seed.txt`
- Create: `D:\AI\Codex\Documents\acl-bypass-evidence\2026-08-13\member-negative.txt`

**Interfaces:**
- Consumes: Task 2 ACL、实际普通成员交互登录会话、实际 UNC。
- Produces: 创建、覆盖、重命名、删除四个动作均 Access Denied；seed 哈希不变。

- [ ] **Step 1: 由普通成员登录 Windows，确认身份并只通过 UNC 访问**

```powershell
whoami /user
$DemoUnc = <Q确认的验证目录UNC>
Get-ChildItem -LiteralPath $DemoUnc
```

预期：SID 对应 Task 1 的普通成员；不得在管理员或执行器窗口中运行此步。

- [ ] **Step 2: 依次执行四类直接写尝试，并保存每项退出码与错误类别**

```powershell
New-Item -ItemType File -Path "$DemoUnc\bypass-create.txt" -ErrorAction Stop
Set-Content -LiteralPath "$DemoUnc\seed.txt" -Value 'bypass-overwrite' -ErrorAction Stop
Rename-Item -LiteralPath "$DemoUnc\seed.txt" -NewName 'bypass-rename.txt' -ErrorAction Stop
Remove-Item -LiteralPath "$DemoUnc\seed.txt" -ErrorAction Stop
```

预期：四项均以 Access Denied 失败。任何一项成功均为旁路写失败证据：立即停止，不执行后续宣称，记录成功的动作和有效 ACL。

- [ ] **Step 3: 管理员核对 seed 哈希和目录内容未变化**

```powershell
$DemoRoot = 'D:\AI\AgentWorkspace\_acl-bypass-demo-20260813'
Get-FileHash -Algorithm SHA256 -LiteralPath "$DemoRoot\seed.txt"
Get-ChildItem -LiteralPath $DemoRoot -Force | Select-Object Name, Length, LastWriteTimeUtc
```

预期：只有执行器创建的 seed 和受控路径创建的文件存在；不存在 `bypass-*` 文件。

### Task 4: 执行器受控写正向验证

**Files:**
- Create: `D:\AI\AgentWorkspace\_acl-bypass-demo-20260813\seed.txt`（仅由 FastAPI 执行器创建）
- Create: `D:\AI\Codex\Documents\acl-bypass-evidence\2026-08-13\executor-positive.txt`

**Interfaces:**
- Consumes: Task 1 的独立 FastAPI 服务账号、当前本地服务、Q 手工注入但不输出的 API Key、受控 owner identity。
- Produces: 执行器通过 `create_plan -> approval-token -> execute` 创建或移动验证文件，操作日志和文件哈希可关联。

- [ ] **Step 1: 由 Q 在执行器服务实际运行期间确认其 PID 身份仍正确**

```powershell
Get-Process -Id $FastApiPid -IncludeUserName | Select-Object Id, ProcessName, UserName
```

预期：仍为 Task 1 已确认的执行器服务账号。

- [ ] **Step 2: 使用现有 Dify/服务受控路径创建并确认一个仅含验证目录文件的计划**

```text
在 Dify 中以已授权 owner 身份请求：将 _acl-bypass-demo-20260813/seed-source.txt 移动为 _acl-bypass-demo-20260813/seed.txt。
流程必须是：create_plan -> Human Input 确认 -> execute_confirmed_plan。
```

预期：服务返回 completed operation；不要在终端、截图或日志中打印 API Key、approval token 或 plan token。

- [ ] **Step 3: 管理员保存操作 ID、计划 ID、文件 SHA-256 与 ACL 快照**

```powershell
$DemoRoot = 'D:\AI\AgentWorkspace\_acl-bypass-demo-20260813'
Get-FileHash -Algorithm SHA256 -LiteralPath "$DemoRoot\seed.txt"
icacls $DemoRoot
```

预期：seed 只由受控执行路径产生；记录操作相关 ID 和哈希，不记录令牌或密钥。

### Task 5: 判定、保留证据与最小清理

**Files:**
- Create: `D:\AI\Codex\Documents\acl-bypass-evidence\2026-08-13\result.md`
- Remove only after Q review: `D:\AI\AgentWorkspace\_acl-bypass-demo-20260813`

**Interfaces:**
- Consumes: Tasks 1–4 的基线、ACL、普通成员负向和执行器正向证据。
- Produces: PASS/FAIL/NOT_RUN 三态结论；不改变业务目录。

- [ ] **Step 1: 使用固定判定规则写结果**

```text
PASS：独立执行器服务账号已确认；普通成员通过 SMB 的创建、覆盖、重命名、删除均 Access Denied；执行器经 FastAPI 受控路径成功；文件哈希与 ACL 证据完整。
FAIL：普通成员任意直接 SMB 写成功，或执行器身份与普通成员/Q 交互身份相同。
NOT_RUN：账号、共享、ACL 或手工 Dify 确认任一前置条件未完成。
```

- [ ] **Step 2: Q 审核证据后再清理专用目录**

```powershell
$DemoRoot = 'D:\AI\AgentWorkspace\_acl-bypass-demo-20260813'
if ((Resolve-Path -LiteralPath $DemoRoot).Path -ne $DemoRoot) { throw '拒绝非精确验证目录清理。' }
Get-ChildItem -LiteralPath $DemoRoot -Force
```

预期：Q 核对列表仅含验证文件后，才授权管理员删除该单一目录；未获授权不得执行删除。

## Self-Review

- 范围覆盖：计划包含身份基线、SMB/NTFS ACL、普通成员四类旁路写、执行器受控正向写、固定 PASS/FAIL/NOT_RUN 结论与人工清理。
- 安全边界：没有对公共盘根目录或业务文件提供递归 ACL/删除命令；任何账号或共享信息缺失都会停止。
- 未解决项：当前项目没有已验证的独立 Windows 服务账号、实际共享名或普通成员 Windows 身份映射，因此必须由 Q 手动确认并执行环境步骤。

## Execution Handoff

本计划完成并保存在 `docs/superpowers/plans/2026-08-13-windows-smb-acl-bypass-verification.md`。由于涉及 Windows 身份、SMB ACL 和真实目录，下一步只能由 Q 选择并手动执行 Task 1 的只读基线核对；在收到身份与共享证据前，不进入 ACL 修改或写入尝试。
