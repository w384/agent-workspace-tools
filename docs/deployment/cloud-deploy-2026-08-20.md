# 云端部署清单 · 腾讯云国际站（2026-08-20）

> 用途：将演示系统部署到腾讯云国际站。本文是总集成起草的部署需求清单，供 Q 审阅与执行线程落地。

## 0. 部署形态（Q 已定）

- 云端：腾讯云国际站，直接通过 GitHub 仓库部署。
- 不装 GPU、不装本地模型服务（llama.cpp / Ollama）；真实可用的模型只有 DeepSeek API。
- 前端保留「本地模型 / 联网模型」两个按钮，本地按钮在云端无本地模型服务时不可用。
- 来源仓库：<https://github.com/w384/agent-workspace-tools>（main，HEAD=52b9338，已推送同步）。

## 1. 服务器最低要求

- 轻量应用服务器或 CVM，建议 2C4G 起步（单进程、内存态，无 GPU）。
- 操作系统：Ubuntu 22.04 / Debian 12（推荐）。
- Python 3.11+（requirements 依赖 fastapi 0.141 / pydantic 2.13）。
- 公网放行端口：8891（演示服务）。

## 2. 部署步骤

1. 安装 Python、pip、git。
2. 拉取代码：
   ```bash
   git clone https://github.com/w384/agent-workspace-tools.git
   cd agent-workspace-tools
   ```
3. 建虚拟环境并装依赖（control_plane 与 service 共用 service/requirements.txt）：
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -r service/requirements.txt
   ```
4. 配置环境变量（见第 3 节）。
5. 启动（seed 幂等 + 起服务）：
   ```bash
   python scripts/init_demo_financial_preassessment.py --host 0.0.0.0 --port 8891
   ```
   说明：默认 host 127.0.0.1，云端必须显式传 `--host 0.0.0.0` 才能从公网访问。
6. 验证：浏览器访问 `http://<服务器IP>:8891/demo/`，用 alice 登录发起一次问答。

## 3. 环境变量

| 变量 | 说明 | 云端建议 |
| --- | --- | --- |
| `RAG_LLM_MODEL` | DeepSeek 模型名 | 默认 `deepseek-chat`，可不设 |
| `RAG_LLM_API_KEY` | DeepSeek API Key | 推荐用环境变量注入；不设则前端登录后填写（登出即清空） |
| `RAG_LLM_BASE_URL` | DeepSeek 端点 | 默认 `https://api.deepseek.com/v1`，可不设 |
| `RAG_LLM_LOCAL_*` | 本地模型配置（llama.cpp / Ollama） | 云端不设（无本地模型服务） |

Key 通过环境变量 / 密钥管理注入，不写入代码与仓库。

## 4. 已知行为（按 Q 口径）

- 两个模型按钮保留：点「本地模型」在云端会提示 LLM 未配置（REFUSED llm_not_configured）；真实可用仅「联网模型（DeepSeek）」。
- DeepSeek Key：环境变量预置或前端填写；前端填写的不回写服务器、登出即清空。
- 演示身份：alice / demo-a-password（有权限）、bob / demo-b-password（无权限，越权演示）。
- 内存态：服务重启会清空已上传 / 已建库文件（Demo 口径，未来真实使用时再接持久化）。
- 演示素材：样例 PDF/DOCX、import-manifest、规则 JSON 已随仓库跟踪，clone 即可用，无需额外上传。

## 5. 安全提醒

- 演示身份是固定口令，公网暴露前建议：安全组仅放行可信 IP，或前置认证（属后续阶段）。
- DeepSeek Key 不落入代码与仓库；必要时用环境变量注入。
- 生产化（真实用户、持久化存储、真实模型）不在本次范围，单独立项。

## 6. 回滚与备份

- 本地完整备份：`D:\AI\Codex\Backups\agent-workspace-tools-2026-08-20`（工作树快照 + `agent-workspace-tools.bundle` 完整 git 历史）。
- GitHub origin/main 与本地 main 一致（52b9338），可随时 `git reset --hard origin/main` 回滚。

## 7. 实际部署记录（2026-09-18）

- 服务器：106.53.200.115（内网 10.1.0.4），Ubuntu 24.04.4 LTS（x86_64），2C2G / 40G 盘（低于 4G 建议值但内存态演示可跑）。
- 部署位置：`/opt/agent-workspace-tools`（git clone 自 GitHub origin/main，部署时 HEAD=0adcb44）。
- 运行方式：systemd 单元 `agent-demo.service`（WorkingDirectory=/opt/agent-workspace-tools，`ExecStart=.venv/bin/python scripts/init_demo_financial_preassessment.py --host 0.0.0.0 --port 8891`，Restart=on-failure，开机自启）。单元文件已 scp 至 `/etc/systemd/system/agent-demo.service`。
- 环境：Python 3.12.3（apt 装 python3-venv/python3-pip）+ venv + `service/requirements.txt`（pip 走 `mirrors.cloud.tencent.com/pypi/simple` 腾讯内网镜像）。
- 安全组：公网放行 22（部署期临时 0.0.0.0/0，建议收紧）+ 8891（0.0.0.0/0，演示端口）。SSH 为 ed25519 私钥登录（C:\Users\tianh\.ssh\id_rsa_demo）。
- DeepSeek Key：未注入环境变量，按 Q 选择「页面填写」（登录后切联网模型填 Key，登出即清空）。
- 验证（公网冒烟 2026-09-18）：/demo/ 200；alice 登录 200；预评估 MATCH 100 / missing=0；本地问答 REFUSED(llm_unavailable)（云端无本地模型，符合第 4 节口径）；bob 越权 DENIED / retrieved=0 / LLM 零调用。
- 备注：本地 HEAD 多出的文档提交 098cbc6（runbook 同步）当时未推送，未进入部署 clone（仅文档差异，不影响运行）。

