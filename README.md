# 企业资料预评估与知识库问答演示系统

一个面向银行对公信贷 / 小微融资场景的**演示系统**：企业上传或选择模拟资料后，系统将其版本化、结构化，完成「资料完整度与规则匹配」预评估，并提供基于本地知识库的自然语言问答。全部结果仅供演示参考，不代表真实贷款、授信、额度测算或金融产品结论。

## 演示能力

- **登录与权限演示**：内置两个演示账号，可演示「有权限用户正常检索」与「无权限用户越权访问被拒」两类行为。
- **知识库问答**：两种提问来源——
  - 上传真实材料：选择本地 PDF / DOCX 上传并自动建库（内存向量索引），随后对自建库提问；
  - 受控样例文件：从系统内置的 import-manifest 白名单中选择虚构样例，直接提问。
  - 问答模型可在「本地模型（Ollama）」与「联网模型（DeepSeek）」之间切换；联网模型支持在页面填写 API Key（登出即清空，不回写服务器）。
- **资料预评估**：确定性规则引擎按演示银行规则做资料匹配度预评估，输出 match_score、结果等级（MATCH / POSSIBLE / NOT_MATCH）、已满足条件、缺失材料与版本化引用，并附固定免责声明。
- **已建库文件管理**：列出当前账号已上传并建库的真实材料文件；上传者可在演示前手动删除，以便下次复用同名文件重新演示。受控样例文件不受影响。
- **登出重置**：Demo 阶段每次登出即清空本账号已上传 / 已建库文件与前端选中状态，重新登录从干净状态开始。

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

## 云端部署（腾讯云国际站）

部署形态与完整步骤见 [docs/deployment/cloud-deploy-2026-08-20.md](docs/deployment/cloud-deploy-2026-08-20.md)，要点：

- 轻量应用服务器 / CVM，建议 2C4G 起步，Ubuntu 22.04 / Debian 12，Python 3.11+。
- **不装 GPU、不装 Ollama**；真实可用模型只有 DeepSeek API，本地模型按钮在云端会提示未配置。
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

核心验收口径：RAG LLM 20 passed、控制面 112 passed、service/tests/rag 72 passed、git diff --check 通过。

## 免责声明

本系统的规则、样例资料、评分与示例银行名称均为虚构演示内容，仅表示资料与示例规则的匹配程度。**不参与、不代表贷款申请、授信审批、额度测算或金融产品销售**，也不构成任何真实金融机构的要求。
