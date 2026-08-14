# Dify 插件发布检查清单

每次项目测试完成、需要生成可安装插件包时，按以下顺序执行：

1. 确认服务端和插件全量测试通过，并记录测试数量与异常警告。
2. 按语义化版本迭代插件版本号；本次版本从 `0.0.5` 升级为 `0.0.6`。
3. 同步更新以下版本字段：
   - `plugin/manifest.yaml` 的顶层 `version`。
   - `plugin/manifest.yaml` 的 `meta.version`。
   - `plugin/pyproject.toml` 的项目版本。
   - `plugin/README.md` 的显示版本。
4. 更新 `plugin/README.md`，确保内容已替换模板占位说明，并包含实际 Provider 配置、`service_url`、Human Input 确认流程、权限边界和安全限制。
5. 使用 Dify CLI 在项目根目录打包：

   ```powershell
   D:\AI\Dify\dify\tools\dify.exe plugin package .\plugin
   ```

6. 将产物复制到既有 E2E 安装包目录：
   `D:\AI\Codex\Worktree\dify-agent-workspace-tools-dify-integration\work\e2e`
7. 文件名必须包含插件版本，并沿用历史命名规范：
   `local-workspace-tools-permission-demo-<version>.difypkg`
8. 对最终安装包复核：manifest 两处版本一致、README 版本一致、无真实 API Key、无 `.env`（允许 `.env.example`）、无无关敏感文件。
9. 运行 `git diff --check`，并把源码、文档、测试、打包产物和复制动作记录到当天的 `project-changes.log`。
10. 在 Dify 页面通过本地文件安装新版本，确认页面显示新版本和最新 README；旧版本保留用于回滚对照。

当前标准产物示例：

`D:\AI\Codex\Worktree\dify-agent-workspace-tools-dify-integration\work\e2e\local-workspace-tools-permission-demo-0.0.6.difypkg`
