# 协调者交接包 2026-08-15

> 用途：Q 的协调助手的交接依据。接替者（新 Codex 协调线程）开工前只读本文件 + 下述权威文件，禁止依赖旧对话记忆。
> 本角色不是 7 个业务线程之一，是第 8 个角色：多线程治理、git 基线管理、交接包维护、归档重开流程执行。

## 1. 角色与权威文件

- 角色：Q 的协调助手。负责：多线程归档重开协调、git 基线管理、交接包维护、阈值监控、跨线程流程推进。
- 权威文件（绝对路径）：
  - `D:\AI\Codex\Projects\dify-agent-workspace-tools\docs\contracts\frozen-v2-integration-contract.md`
  - `D:\AI\Codex\Projects\dify-agent-workspace-tools\docs\agent\v2-role-map.md`
  - `D:\AI\Codex\Projects\dify-agent-workspace-tools\docs\agent\thread-handoff-2026-08-14.md`
  - `D:\AI\Codex\Projects\dify-agent-workspace-tools\docs\agent\thread-archive-sop.md`

## 2. 当前状态（截至 2026-08-15）

### 2.1 git 基线（main 提交链，全部本地未推送）

```
5d7ba3d  docs: 执行端文档+脚本+受控样例（38 文件）
00a3f0f  feat(plugin): 上传工具 + plan_hash 令牌流程（15 文件）
7fca8ad  feat(service): 路径前缀访问控制（22 文件）
a4403fc  v1 纲要归档（superseded）
d9a2d7d  RAG 后端（fail-closed，42 passed）
49a796a  控制面（后端演进 + /demo 前端切片，86 passed）
1c2af05  治理文档基线（契约/role-map/交接包/SOP/guideline）
29a8b2c  ← origin/main 停留点
```

### 2.2 worktree 现状

- 主 checkout：`D:\AI\Codex\Projects\dify-agent-workspace-tools` @ main（a4403fc 之上 3 个提交）
- 唯一保留 worktree：`D:\AI\Codex\Worktree\dify-agent-workspace-tools-dify-integration`（feature 分支，标准位置）
- 已删除跑偏 worktree：a904、0328、12eb；已删过时 worktree：control-plane、rag

### 2.3 线程状态（7 个业务线程全部归档重开完成）

| 线程 | 状态 |
|---|---|
| 总集成 019ff955 | 已归档重开，正拆分执行线程 |
| 控制面 | 代码固化 49a796a，旧线程归档 |
| RAG | 代码固化 d9a2d7d，旧线程归档 |
| PO+PMO | 新线程 @ worktree 0bd2，定稿验收矩阵中 |
| 横纵分析 | 新线程复述通过，待命 |
| 独立审计 | 新线程复述通过，待命 |
| 战略专家 | 新线程复述通过，待命 |

## 3. 剩余待办（按优先级）

1. **执行线程拆分落地**：总集成已批准方案，待 create_thread 创建"执行线程（executor）"，B 类工作（跑测试/git 提交/合并/证据归档）下沉给它。
2. **RAG 侧 5 个文件提交**：`bank-rule-matching-demo.md`、`finance-demo-rag-bridge.md`、`finance-demo-rag-bridge-checkpoint.md`、`import-manifest.json`、`rules/demo-bank-rules-v1.json`——待 RAG 新线程确认归属后提交。
3. **交接文件提交**：`thread-handoff-2026-08-14.md`（M 状态）单独提交。
4. **`.audit-tmp-cp-f55f...` 残留目录**：权限受限，需清理（可能需重启 Codex 释放句柄）。
5. **旧分支指针清理**：`control-plane/main`、`rag/minimal-loop` 内容已进 main，可删分支。
6. **推送 origin**：待独立审计最终复核 + Q 授权。
7. **`work/demo/public-drive-ai-organizing/`**：二进制 fixture，待决策 git-lfs/体积管理。

## 4. 阈值与归档口径

- rollout > 5MB 或累计 input > 1000 万 tokens → 归档重开；4–5MB 临界。
- 归档触发采用**半自动**：监控线程检测超限 → 通知 Q → Q 确认后才归档重开（不自动归档）。
- 监控方式：新建监控线程 + heartbeat 自动化，定期扫 `C:\Users\tianh\.codex\sessions\` 下 rollout 文件大小。

## 5. 方法论与关键教训（接替者必读）

1. **归档前核验必须 git status 实况，不能信口头"无未提交"**：a904、0328、12eb 三个 worktree 都藏着未提交代码，口头确认全部失实。
2. **删除 worktree 前必须核验未跟踪文件**：`git worktree remove` 会因 untracked 文件被拦，`--force` 前必须确认代码已保全。
3. **交接包/契约必须进 git**：未提交文档在 worktree 线程里读不到（worktree 基于旧 commit 检出），导致多个线程报"找不到交接包"。
4. **create_thread 用 worktree 模式** = 能切模型 + 隔离 cwd；`spawn_agent` 无 cwd 参数，不能锁 worktree。
5. **开错目录的线程会在主 checkout 继续演进**：RAG/控制面都出现过"线程在主 checkout 做了比 worktree 分支更新的工作"，导致代码散落两处。合并时要以"主 checkout 最新版"为准，而非盲目从分支 merge。
6. **代码合并属代码级操作，交给懂代码的线程**（总集成），协调者不盲改代码。
7. **handoff_thread 存在**：用于 checkout ↔ 托管 worktree 之间迁移线程（不是创建线程）。
8. **automation 机制**：heartbeat（绑线程，可 minute 级）+ cron（绑 projectId，standalone）。之前战略专家用 heartbeat 建过 daily 扫描，可用作监控线程范本。

## 6. 协作方式

- 协调者只做：协调、归档重开流程、git 基线管理、交接包维护、阈值监控。
- 协调者不做：代码实现、测试、业务裁决（这些归各业务线程 + 执行线程）。
- 与线程通信：`send_message_to_thread` 派活，`wait_threads` 跟踪，`list_threads`/`read_thread` 查状态。
- 新建线程：`create_thread`（worktree 模式，默认模型），projectId = `24928e18-cf03-4909-a7e7-1ca81ddd6792`。

## 7. 首条开工指令（供 create_thread 的 prompt 使用）

```
你是 Q 的协调助手，接替已归档的协调者。旧对话不可用，禁止依赖旧记忆。
开工前只读本文件（docs/agent/coordinator-handoff-2026-08-15.md）+ 第 1 节列出的 4 份权威文件。
第一步：读完文件后，复述当前状态（git 基线、线程状态、剩余待办、阈值口径、关键教训），
等 Q 确认后再继续推进待办事项。
```
