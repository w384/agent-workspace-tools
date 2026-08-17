# 协调者交接包 2026-08-15

> 用途：Q 的协调助手的交接依据。接替者（新 Codex 协调线程）开工前只读本文件 + 下述权威文件，禁止依赖旧对话记忆。
> 本角色不是 7 个业务线程之一，是第 8 个角色：多线程治理、git 基线管理、交接包维护、归档重开流程执行。
> 最后更新：2026-08-18（本线程归档重开时据实更新，未提交、未推送）。

## 1. 角色与权威文件

- 角色：Q 的协调助手。负责：多线程归档重开协调、git 基线管理、交接包维护、阈值监控、跨线程流程推进。
- 权威文件（绝对路径）：
  - `D:\AI\Codex\Projects\agent-workspace-tools\docs\contracts\frozen-v2-integration-contract.md`
  - `D:\AI\Codex\Projects\agent-workspace-tools\docs\agent\v2-role-map.md`
  - `D:\AI\Codex\Projects\agent-workspace-tools\docs\agent\thread-handoff-2026-08-14.md`
  - `D:\AI\Codex\Projects\agent-workspace-tools\docs\agent\thread-archive-sop.md`

## 2. 当前状态（截至 2026-08-18 归档）

### 2.1 git 基线（main 提交链，全部本地未推送）

```
51cdc75  docs: 执行端 runbook/checklist 对齐统一 /demo/ 双路径故事线
eaaf8ec  feat(control_plane): BFF 桥接注入 RAG 真实 LLM + 桥接/前端测试
4720891  feat(rag): 接入真实 LLM（AnswerGenerator/ExplanationPort + 检索流调用点与测试）
4b045cf  docs: add coordinator handoff and executor split (LRN-20260816-001)
5d7ba3d  docs: 执行端文档+脚本+受控样例（38 文件）
00a3f0f  feat(plugin): 上传工具 + plan_hash 令牌流程（15 文件）
7fca8ad  feat(service): 路径前缀访问控制（22 文件）
a4403fc  v1 纲要归档（superseded）
29a8b2c  ← origin/main 停留点（origin 远端 URL 已丢失，remote -v 为空，需 Q 提供）
```

- 独立仓库（非主项目）：thread-archive-restart skill @ `C:\Users\tianh\.codex\skills\thread-archive-restart`，aac8e97 + tag v0.1.0，已推送 https://github.com/w384/thread-archive-restart。

### 2.2 worktree 现状

- 主 checkout：`D:\AI\Codex\Projects\agent-workspace-tools` @ main（HEAD=51cdc75；工作区 22 M + 7 未跟踪，未提交）。
- 协调者 worktree：`D:\AI\Codex\Worktree\af25\agent-workspace-tools` @ main（新协调者线程沿用）。
- 其他 worktree：0bd2（PO+PMO 定稿）、9c51、9f9b、ceb0（执行线程）、4c0b（RAG v2）、79e8（控制面 v2）。
- 已删除：dify-integration worktree（feature 已并入 main，演示包备份至 D:\AI\Codex\Documents\2026-08-16-dify-integration-worktree-backup）；跑偏 worktree a904、0328、12eb；过时 worktree control-plane、rag。

### 2.3 线程状态（业务线程均已归档重开过一轮）

| 线程 | 状态 |
|---|---|
| 总集成 019ff955 | 已归档重开（当前 01a000d2），负责派单 |
| 控制面 | 代码固化（v2 合入 eaaf8ec），旧线程归档 |
| RAG | 代码固化（v2 合入 4720891），旧线程归档 |
| PO+PMO | 新线程 @ worktree 0bd2，3.6 定稿已同步回主 checkout（未 commit） |
| 横纵分析 | 已归档重开 |
| 独立审计 | 已归档重开 |
| 战略专家 | 已归档重开 |
| 协调者（本角色） | 2026-08-18 归档重开中（ARCHIVE 命中：累计 input 2950 万 ≥ 1000 万），新线程待 Q 客户端归档后重开 |

## 3. 剩余待办（按优先级，2026-08-18 更新）

1. **恢复 origin 并推送 main**：origin 远端 URL 丢失（remote -v 为空），需 Q 提供仓库 URL；推送前待独立审计最终复核 + Q 授权。main 领先 origin（29a8b2c）共 9 个提交（至 51cdc75）。
2. **改名未提交改动**：主 checkout 22 个 M + 7 个未跟踪（含 uncommitted 3.6 定稿、`work/demo/public-drive-ai-organizing/` 二进制 fixture），需按归属提交 / 决策（git-lfs / 体积管理）。
3. **BFF 集成联调 + Gate V2-5 验收**：归总集成（01a000d2）派单，执行线程实施；RAG/控制面已合入，测试基线 RAG 62 passed、control_plane 93 passed（合入时实测）。
4. **RAG 侧 5 个文件提交**：`bank-rule-matching-demo.md`、`finance-demo-rag-bridge.md`、`finance-demo-rag-bridge-checkpoint.md`、`import-manifest.json`、`rules/demo-bank-rules-v1.json`——待 RAG 新线程确认归属后提交。
5. **交接文件提交**：`thread-handoff-2026-08-14.md`（M 状态）单独提交。
6. **`.audit-tmp-cp-f55f...` 残留目录**：权限受限，需清理（可能需重启 Codex 释放句柄）。
7. **旧分支指针清理**：`control-plane/main`、`rag/minimal-loop` 内容已进 main，可删分支。

## 4. 阈值与归档口径

- rollout > 5MB 或累计 input > 1000 万 tokens → 归档重开；4–5MB 临界。
- 归档触发采用**半自动**：检测超限 → 通知 Q → Q 确认后才归档重开（不自动归档）。
- 判定/监控执行：thread-archive-restart 技能（v0.1.0，已开源）`scripts/measure_thread_context.py`，`--check` 退出码 0=无、1=TRIGGER、2=WARN、3=ARCHIVE、4=ROLLOUT；阈值可调。
- 2026-08-18 全机扫描（近 5 天）：56 线程，7 个命中信号（见 thread-handoff 3.7 归档记录与当次扫描输出）。

## 5. 方法论与关键教训（接替者必读）

1. **归档前核验必须 git status 实况，不能信口头"无未提交"**：a904、0328、12eb 三个 worktree 都藏着未提交代码，口头确认全部失实。
2. **删除 worktree 前必须核验未跟踪文件**：`git worktree remove` 会因 untracked 文件被拦，`--force` 前必须确认代码已保全。
3. **交接包/契约必须进 git**：未提交文档在 worktree 线程里读不到（worktree 基于旧 commit 检出），导致多个线程报"找不到交接包"。
4. **create_thread 用 worktree 模式** = 能切模型 + 隔离 cwd；`spawn_agent` 无 cwd 参数，不能锁 worktree。
5. **开错目录的线程会在主 checkout 继续演进**：RAG/控制面都出现过"线程在主 checkout 做了比 worktree 分支更新的工作"，导致代码散落两处。合并时要以"主 checkout 最新版"为准，而非盲目从分支 merge。
6. **代码合并属代码级操作，交给懂代码的线程**（总集成），协调者不盲改代码。
7. **handoff_thread 存在**：用于 checkout ↔ 托管 worktree 之间迁移线程（不是创建线程）。
8. **automation 机制**：heartbeat（绑线程，可 minute 级）+ cron（绑 projectId，standalone）。之前战略专家用 heartbeat 建过 daily 扫描，可用作监控线程范本。
9. **归档流程用技能本身执行**：thread-archive-restart skill 已开源（v0.1.0），含测量脚本与 6 步交接包优先流程，协调者归档重开按技能执行。

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