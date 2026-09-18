# 企业 Agent 安全运行样板间 · 金融资料预评估演示

一个面向银行对公信贷 / 小微融资场景的**演示系统**，也是企业 Agent 安全运行样板间（Agent Control Plane 能力样板）的第一套可替换场景板块：企业上传或选择模拟资料后，系统将其版本化、结构化，完成「资料完整度与规则匹配」预评估，并提供基于本地知识库的自然语言问答。系统同时展示控制面 Policy / Audit / Context / Runtime / Skill 能力。全部结果仅供演示参考，不代表真实贷款、授信、额度测算或金融产品结论。

## 演示能力

- **登录与权限演示**：内置四个演示账号——`alice`（资料评估 / 知识库问答有权限）、`bob`（越权负向）、`carol`（计划执行：上传 / 移动 / 删除行动权限）、`dave`（独立审批者，四眼原则）。可演示「有权限用户正常执行」与「无权限用户越权访问被拒」两类行为。
- **知识库问答**：两种提问来源——
  - 上传真实材料：选择本地 PDF / DOCX 上传并自动建库（内存向量索引），随后对自建库提问；可**勾选多个文件跨文件一次提问**（`/api/demo/knowledge/query-multi`，任一文件无授权则整单 DENIED 零召回）；
  - 受控样例文件：从系统内置的 import-manifest 白名单中选择虚构样例，直接提问。
  - 问答模型可在「本地模型（llama）」与「联网模型（DeepSeek）」之间切换；联网模型支持在页面填写 API Key（登出即清空，不回写服务器）。
- **资料预评估**：两种评估方式——
  - 受控样例评估：选择 import-manifest 白名单内 6 个受控样例文件，按规则夹具匹配；
  - 真实材料评估（放宽白名单）：上传自己的真实 PDF / DOCX（≤2MB），为每个文件指定材料类别（资料概览 / 收入 / 资金流 / 资产负债 / 经营 / 补充材料清单），系统按同一套演示银行规则做资料匹配度预评估（`/api/real-material/assess`；该路径不建资产、不入知识库，任何登录身份可评估自己拖入的字节）。
  - 确定性规则引擎输出 match_score、结果等级（MATCH / POSSIBLE / NOT_MATCH）、已满足条件、缺失材料与版本化引用，并附固定免责声明。
- **已建库文件管理**：列出当前账号已上传并建库的真实材料文件；支持**覆盖上传（同名替换）**：先删旧文件再重新上传建库（仅上传者可覆盖）。上传者可在演示前手动删除，以便下次复用同名文件重新演示。受控样例文件不受影响。
- **计划执行与验证闭环**（第四页 UI）：carol 上传任意文件到受控目录 organized/ → 移动（自确认即执行）或删除（需 dave 审批，四眼原则：发起人不能自批）→ 执行后独立读回验证（VERIFIED / MISMATCH）；验证失败自动落 Recovery Task（recovered / escalated）。
- **登出重置**：Demo 阶段每次登出即清空本账号已上传 / 已建库文件与前端选中状态，重新登录从干净状态开始。
- **控制面能力样板（API 层）**：在演示 UI 之外，工程同时落地 Agent 安全运行样板能力——身份与授权策略（Policy / Actor Context）、计划与审批（Plan / Approval / 幂等 / 计划哈希）、独立读回验证（Verification Adapter：VERIFIED / MISMATCH / UNKNOWN）、失败后的恢复与升级（Recovery Task：recovered / escalated + 审计事件）、MCP 暴露层（Policy / Assess / Query / Audit 四工具，支持可选 agent_id 演示「Agent 代表用户执行」：Agent 继承所属用户授权、动作以 agent_action_executed 审计留痕、无 QUERY 授权用户的 Agent 同样被拒）。演示服务已接入**真实受控目录执行器**（不再使用占位 file_executor=object()）：被授权的计划在受控目录上真实执行（上传 / 移动重命名 / 删除），执行后由独立读回适配器校验真实磁盘状态（文件存在 + SHA-256 指纹；破坏性删除读回源文件是否消失），VERIFIED / MISMATCH 闭环在运行中的 /demo 服务上可用。完整闭环与验收口径见 docs/engineering-principles.md 与 docs/verification/。

## 快速开始（本地）

前置：Python 3.11+（依赖 fastapi / pydantic / pypdf / python-docx / httpx）。

    # 1. 创建虚拟环境并安装依赖
    python3 -m venv .venv
    source .venv/bin/activate            # Windows: .venv\Scripts\activate
    pip install -r service/requirements.txt

    # 2. 种子化演示数据并启动服务（幂等，可重复执行）
    python scripts/init_demo_financial_preassessment.py --host 127.0.0.1 --port 8891

    # 3. 浏览器打开演示页
    #    http://127.0.0.1:8891/demo/

只种子化数据不启动服务（打印资产 / 规则 ID 清单）：

    python scripts/init_demo_financial_preassessment.py --seed-only

## LLM 模型配置

「知识库问答」的生成模型可在**本地模型（llama.cpp / llama-server）**与**联网模型（DeepSeek）**之间切换，默认本地模型。**新用户首次运行请按自己的环境配置，不要直接依赖代码内置的默认值。**

本地模型（默认）：

- 默认端点 `http://127.0.0.1:18080/v1`（llama.cpp llama-server OpenAI 兼容端点）、默认模型 `qwen3.8-27b-local`（llama-server `/v1/models` 返回的实际模型 ID）。
- 若你的 llama-server 运行在不同地址 / 端口 / 模型，用环境变量覆盖：
  - `RAG_LLM_LOCAL_BASE_URL`：本地 llama 端点（默认 `http://127.0.0.1:18080/v1`）
  - `RAG_LLM_LOCAL_MODEL`：本地模型名（默认 `qwen3.8-27b-local`）
  - `RAG_LLM_LOCAL_API_KEY`：本地端点所需 Key（llama-server 启用 `--api-key` 鉴权时必填，否则留空）
  - `RAG_LLM_TIMEOUT_SECONDS`：LLM 请求超时（默认 120 秒）。本地推理模型含思考过程、耗时较长，若仍超时再调大

联网模型（DeepSeek）：

- 环境变量注入：`RAG_LLM_BASE_URL`（默认 `https://api.deepseek.com/v1`）、`RAG_LLM_MODEL`（默认 `deepseek-chat`）、`RAG_LLM_API_KEY`（必填）。
- 或页面填写：在「知识库问答」页切到联网模型并填入 API Key，Key 仅当前会话 BFF 内存持有，登出即清空。

安全约束：真实 Key / base_url / model 不落前端、不入审计。默认值源码位置：本地模型见 `control_plane/app/llm_providers.py`，RAG 注入见 `service/app/rag/llm.py`。云端部署（腾讯云国际站，无 GPU / 无本地模型服务）只配置 DeepSeek 三项环境变量即可，本地模型按钮会提示未配置。

## 云端部署（腾讯云国际站）

部署形态与完整步骤见 [docs/deployment/cloud-deploy-2026-08-20.md](docs/deployment/cloud-deploy-2026-08-20.md)，要点：

- 轻量应用服务器 / CVM，建议 2C4G 起步，Ubuntu 22.04 / Debian 12，Python 3.11+。
- **不装 GPU、不装本地模型服务（llama.cpp / Ollama）**；真实可用模型只有 DeepSeek API，本地模型按钮在云端会提示未配置。
- 启动时显式传 --host 0.0.0.0 才能从公网访问：

    python scripts/init_demo_financial_preassessment.py --host 0.0.0.0 --port 8891

- DeepSeek Key 用环境变量注入（RAG_LLM_API_KEY / RAG_LLM_MODEL / RAG_LLM_BASE_URL），不写入代码与仓库；前端填写的 Key 登出即清空。

## 演示账号

| 账号 | 密码 | 权限 |
| --- | --- | --- |
| alice | demo-a-password | 已授权：可检索「客户模拟资料」受控样例与本人上传材料 |
| bob | demo-b-password | 无 QUERY 授权：查询受控样例 / 他人材料返回 DENIED（越权演示） |

## 项目结构

    control_plane/          演示后端（BFF）：登录会话、权限评估、知识库上传/问答、资料预评估、模型切换
      static/               前端三页（资料预评估 / 知识库问答 / 已建库文件管理）
      app/                  FastAPI 应用、权限策略、RAG 桥接、LLM 提供方注册
      tests/                演示端到端测试（含越权负向控制断言）
    service/app/rag/        RAG 检索服务：文档解析、向量索引、权限感知检索、LLM 生成
    service/tests/rag/      RAG 单元测试
    scripts/                初始化脚本（幂等 seed + 起服务）、演示素材构建脚本
    work/demo/financial-preassessment/
      样例素材（PDF/DOCX，全部虚构）、规则 JSON、import-manifest 白名单
    docs/demo/              演示设计、runbook、演示指南
    docs/deployment/        云端部署清单
    docs/verification/      验证证据与检查清单

## 测试验证

    # 演示后端全量（含权限负向、前端交互、模型切换、知识库桥接）
    python -m pytest control_plane/tests -q

    # RAG 检索服务（LLM 生成 / 解释端口 / 文档解析 / 权限感知检索等）
    python -m pytest service/tests/rag -q

核心验收口径：RAG LLM 20 passed、控制面 170 passed、service/tests/rag 72 passed、git diff --check 通过。

## 免责声明

本系统的规则、样例资料、评分与示例银行名称均为虚构演示内容，仅表示资料与示例规则的匹配程度。**不参与、不代表贷款申请、授信审批、额度测算或金融产品销售**，也不构成任何真实金融机构的要求。
