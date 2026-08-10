# 项目 README

本项目由项目集模板创建。

## 项目定位

待补充。

## 当前阶段

待补充。

## 主要资料

- `AGENTS.md`：项目级 AI 协作规则。
- `docs/agent/workflows.md`：复杂任务、计划、原型和交付复盘的分支规则。
- `docs/agent/memory-and-decisions.md`：主动沉淀、决策和错误/口径判断规则。
- `.learnings/LEARNINGS.md`：项目已确认经验。
- `.learnings/ERRORS.md`：项目已踩错误。

## 常用命令

```bash
# 待补充
```

## 推荐项目文档结构

推荐结构：

```text
/
├── AGENTS.md
├── README.md
├── docs/
│   ├── agent/
│   │   ├── workflows.md
│   │   └── memory-and-decisions.md
│   ├── implementation-plan.md
│   ├── implementation-notes.md
│   ├── unknowns-log.md
│   ├── decision-log.md
│   └── final-report.md
└── .learnings/
    ├── LEARNINGS.md
    └── ERRORS.md
```

不强制每个项目一次性建齐。`docs/agent/` 和 `.learnings/` 随模板创建；其他任务触发型文件需要时再创建。

## 本文件维护规则

项目 `AGENTS.md` 优先保持短入口和清楚路由。

适合写在项目 `AGENTS.md` 里的内容：

- 项目定位。
- 权威资料入口。
- 项目特有约束。
- 分支规则调用条件。
- 常用验证命令。
- 项目专属输出风格。

不适合写在项目 `AGENTS.md` 里的内容：

- 大段需求正文。
- 大段设计稿说明。
- 大段数据字典。
- 一次性任务计划。
- 频繁变化的中间结论。
- 复杂工作流全文。
- 沉淀和决策机制细则。

这些内容应放在 `docs/`、`docs/agent/` 或 `.learnings/`，并在项目 `AGENTS.md` 中给出清楚入口。
