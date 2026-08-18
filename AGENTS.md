# 项目级 AGENTS.md

本文件叠加 Q 的全局 `C:\Users\tianh\.codex\AGENTS.md`。

若与全局规则冲突，以本项目更具体规则为准。

本文件是项目级主入口，目标是短、清楚、可路由：只保留当前项目每次都可能需要的结果、权威来源、约束、工具路由、验证标准、输出与沉淀规则。

## 1. 项目结果

一句话定位：

> 待补充。

目标用户：

- 待补充。

当前阶段：

- 待补充。

最重要的成功标准：

- 待补充。

当前不做：

- 待补充。

## 2. 项目权威来源

按以下优先级判断项目事实：

1. 用户当前明确指定的版本、材料、数值、字段、范围和口径。
2. 本项目标记为权威的 PRD、设计规范、数据口径、接口文档和测试说明。
3. 当前代码、接口、测试、运行结果和真实数据。
4. 历史文档与 `.learnings/`，仅用于补充背景，不覆盖较新的事实。

本项目核心资料入口：

- `README.md`：项目总入口。没有时先忽略。
- `docs/`：需求、设计、测试、数据口径和交付说明。没有时先忽略。
- `docs/agent/workflows.md`：复杂任务、需求澄清、原型、实施计划和交付复盘的工作流说明。
- `docs/agent/memory-and-decisions.md`：主动沉淀、决策记录、明确错误与待确认口径的处理规则。
- `.learnings/LEARNINGS.md`：项目已确认经验。只有涉及项目延续、历史规则或沉淀候选时读取。
- `.learnings/ERRORS.md`：项目已踩错误。只有排查失败、重复错误或环境问题时读取。

如本项目有更具体的权威文档，在这里补充：

- 待补充。

## 3. 项目约束

本项目必须保留：

- 待补充。

本项目禁止改变：

- 待补充。

本项目需要先确认的动作：

- 待补充。

只填写本项目特有的限制，不重复全局风险边界。

## 4. 工具与工作流路由

只在命中场景时读取分支文件。

读取 `docs/agent/workflows.md` 的场景：

- 需求模糊、陌生模块、新功能或影响范围较大。
- 需要 Blind Spot Pass、Reverse Interview、Prototype First、Implementation Plan、Implementation Notes、Delivery Review 或 Final Exam。
- 涉及架构、数据、权限、核心流程、重要体验路径或多文件正式改动。

读取 `docs/agent/memory-and-decisions.md` 的场景：

- 用户表达后续要遵守的项目规则、术语、字段、流程、偏好或边界。
- 对话中出现可复用经验、重复错误、稳定验证方式或明确项目裁定。
- 需要判断内容应写入项目 `AGENTS.md`、`.learnings/`、`docs/decision-log.md` 还是全局规则。
- 需要区分明确错误与待确认口径。

本项目特有工具、Skill 或外部系统：

- 工具核查铁律（Codex 桌面端，「工具不存在 / 缺失」结论前必须执行）：
  - 先运行时枚举，不得仅凭外层工具目录或系统提示词清单下结论：exec 内 `Object.keys(tools)` 全量枚举（本环境实测 166 项），或 `typeof tools.<候选名>` 定向探测；「我找不到」≠「不存在」。
  - 线程工具真实名称为 `codex_app__` 前缀：`codex_app__send_message_to_thread`（给线程派活 / 投递）、`codex_app__wait_threads`（跟踪）、`codex_app__list_threads` / `codex_app__read_thread`（查状态）、`codex_app__create_thread` / `codex_app__fork_thread`（新建）、`codex_app__handoff_thread`（迁移）、`codex_app__set_thread_pinned` / `codex_app__set_thread_archived` / `codex_app__set_thread_title`。提示词 / 文档里的裸名（如 create_thread）不是可调用名。
  - 证据：`.learnings/ERRORS.md` ERR-20260818-001。

## 5. 验证与完成标准

本项目常用验证命令：

```bash
# 待补充
```

必测状态：

- 待补充。

无法运行验证时，说明原因、风险和替代检查。

交付时必须说明：

- 改了什么。
- 为什么这样改。
- 怎么验证。
- 哪些风险仍存在。

## 6. 输出与沉淀

本项目专属输出要求：

- 无。若需要固定结束语、术语、章节命名或交付格式，在这里填写。

如果本次改动改变了需求、字段、状态、接口、权限、页面行为、数据口径或验证方式，应同步更新对应文档。

主动识别可沉淀内容，但区分“候选”和“写入”：

- 只有当前任务包含文档同步、规则维护或经验沉淀授权时才写入。
- 未获得写入授权时，在最终回复中列为沉淀候选。
- 用户可以随时要求本轮暂停沉淀、只列候选、不写入文件。

默认写入位置：

- 项目固定执行规则、固定验证命令、输出风格：写入项目 `AGENTS.md`。
- 项目经验、业务口径、命名和后续复用事实：写入 `.learnings/LEARNINGS.md`。
- 已踩错误、失败原因和避免方式：写入 `.learnings/ERRORS.md`。
- 重要长期决策：按需写入 `docs/decision-log.md`。
- 跨项目规则：先提示用户确认，再考虑更新全局 `C:\Users\tianh\.codex\AGENTS.md`。

