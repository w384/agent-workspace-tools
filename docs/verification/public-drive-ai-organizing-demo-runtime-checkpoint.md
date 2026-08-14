# 公共盘 AI 整理 DEMO：RAG 查询运行检查点

状态：本地受控样例检查点，不是生产发布或 Windows/SMB 环境验收。

## 已验证链路

样例源目录为 `work/demo/public-drive-ai-organizing/source`，只包含项目内生成的虚构资产。真实解析范围固定为 PDF/DOCX；JPG/AEP 仅用于展示非解析素材存在。

1. 认证后的 BFF 请求 `POST /api/retrieval/query` 必须提交 `question` 和已选择的 `asset_id`。
2. 浏览器自报 `user_id` 被忽略；请求身份只来自服务端 session。
3. `DemoRagPort` 用控制面同源 `PermissionGrant` 对目标 Asset 做查询授权，再以服务端过滤器把候选严格收窄到该 Asset 的 active AssetVersion。
4. PDF 使用 `pypdf` 按页切片，DOCX 使用 `python-docx` 按非空段落切片；切片写入可删除、可重建的 `InMemorySearchIndex`。
5. 结果包含 `asset_version_id`、`chunk_id`、页码或段落、`current_path`、`version_path`。A 指定敏感 Asset 时返回 `DENIED`，且评分器、重排器、回答生成器均不接触无权内容。

## 复验命令与结果

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
& '.\service\.venv\Scripts\python.exe' -B -m pytest `
  'control_plane\tests\test_demo_rag_query.py' `
  'control_plane\tests\test_demo_rag_http_integration.py' -q -p no:cacheprovider
```

结果：`3 passed in 0.21s`。

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
& '.\service\.venv\Scripts\python.exe' -B -m pytest `
  'service\tests' 'control_plane\tests' -q -p no:cacheprovider
& '.\plugin\.venv\Scripts\python.exe' -B -m pytest `
  'plugin\tests' -q -p no:cacheprovider
git diff --check
```

本次结果：服务端与控制面 `188 passed in 2.66s`；插件 `103 passed in 2.17s`，包含 2 个既有第三方弃用或 MonkeyPatch 警告。`git diff --check` 在本轮末尾复跑。

## 关键负向断言

- A 指定 `版权授权证明/内部法务评审意见.docx` 时：`status=DENIED`、`retrieved_count=0`、`llm_invoked=false`、`citations=[]`，评分器调用为零。
- B 查询 A 的验收 PDF 和 B 的法务 DOCX 分别成功，但均依赖各自显式 `PermissionGrant`；不是管理员默认绕过。
- 查询范围只允许目标 Asset 的当前 active AssetVersion；不存在模糊的“提问内容相似就返回其他已授权文件”回退。

## 演示操作补充

在黄金路径的每一次 RAG 查询前，演示者先从已显示的资产列表选择要引用的 Asset，再输入问题。这样 A 选择 B 的敏感 Asset 会直接展示检索前 DENY；B 选择 A 或 B 的已授权 Asset 才进入解析后的切片/索引查询。

## 仍未验证

- `DemoRagPort` 只接入项目内已准备的样例源文件；它不会接收任意真实上传文件。B 通过 FastAPI 对真实公共盘上传并自动解析/索引，仍需在专用环境和授权范围内接线验证。
- parser worker 的 OS 级无网络、超时、内存/CPU 隔离尚未实现；当前只验证固定格式、2 MiB 上限和受控源目录。
- 当前索引为内存副本，不是 Qdrant；控制面为内存仓储与静态 PostgreSQL DDL，不是生产部署。
- Windows/SMB 服务账号、普通成员账号、共享 UNC、专用目录 ACL 四项环境前提仍为 NOT_RUN；本检查点不能证明旁路写阻断。
