/* Minimal demo entry. The browser only talks to this BFF; RAG and Dify are not reachable directly. */
(function () {
  "use strict";

  const $ = (selector) => document.querySelector(selector);

  const BANK_LABEL_DISCLAIMER = "示例银行名为虚构脱敏，非真实银行推荐";
  const CONTROLLED_SAMPLE_FILES = [
    { name: "资料概览与授权说明.docx", material: "资料概览与授权说明" },
    { name: "收入情况说明.pdf", material: "收入情况说明" },
    { name: "资金流摘要.pdf", material: "资金流摘要" },
    { name: "资产负债说明.docx", material: "资产负债说明" },
    { name: "经营情况说明.docx", material: "经营情况说明" },
    { name: "补充材料清单.pdf", material: "补充材料清单" },
  ];
  const CONTROLLED_FILE_NAMES = new Set(
    CONTROLLED_SAMPLE_FILES.map((item) => item.name)
  );

  function setStatus(message) {
    $("#login-status").textContent = message;
  }

  function el(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined && text !== null) node.textContent = text;
    return node;
  }

  async function jsonRequest(path, options) {
    const response = await fetch(path, {
      method: options.method || "POST",
      headers: options.body ? { "Content-Type": "application/json" } : undefined,
      body: options.body ? JSON.stringify(options.body) : undefined,
      credentials: "same-origin",
    });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) {
      const detail = payload.error ? payload.error.code : "request_failed";
      const error = new Error(detail);
      error.status = response.status;
      error.payload = payload;
      throw error;
    }
    return payload;
  }

  function renderKeyValue(rows) {
    const dl = el("dl", "report-kv");
    rows.forEach(([label, value]) => {
      dl.appendChild(el("dt", null, label));
      dl.appendChild(el("dd", null, String(value)));
    });
    return dl;
  }

  function renderCitation(citation, index) {
    const kind = citation.citation_type || "material";
    const parts =
      kind === "rule"
        ? [
            "规则引用",
            citation.rule_id,
            citation.version_label
              ? "版本 " + citation.version_label
              : "",
            citation.source_type ? "来源 " + citation.source_type : "",
          ]
        : [
            "资料引用",
            citation.page ? "第 " + citation.page + " 页" : "",
            citation.paragraph ? "第 " + citation.paragraph + " 段" : "",
            citation.asset_version_id
              ? "资产版本 " + citation.asset_version_id.slice(0, 8)
              : "",
          ];
    const li = el("li", "citation-item", String(index + 1) + ". " + parts.filter(Boolean).join(" · "));
    return li;
  }

  function renderReport(report) {
    const area = $("#assessment-result");
    area.replaceChildren();
    const card = el("div", "report-card");
    const bankLabel = report.bank_label || "示例银行";
    card.appendChild(el("p", "bank-label", bankLabel));
    card.appendChild(el("p", "bank-disclaimer", BANK_LABEL_DISCLAIMER));

    const missing = report.missing_materials || [];
    card.appendChild(
      renderKeyValue([
        ["匹配度", (report.match_score ?? "—") + " / 100"],
        ["结果级别", report.result_level || "—"],
        ["查询主体", report.query_subject || "—"],
        ["缺失材料", missing.length ? missing.join("、") : "无"],
      ])
    );

    const evidence = report.rule_version_evidence || {};
    const evidenceSection = el("div", "report-section");
    evidenceSection.appendChild(el("h3", null, "规则版本证据"));
    evidenceSection.appendChild(
      el(
        "p",
        null,
        "版本 " +
          (evidence.version_label || "—") +
          " · 来源 " +
          (evidence.source_type || "—")
      )
    );
    card.appendChild(evidenceSection);

    const citations = report.citations || [];
    const citationSection = el("div", "report-section");
    citationSection.appendChild(el("h3", null, "引用"));
    if (citations.length) {
      const list = el("ul", "citations");
      citations.forEach((citation, index) => {
        list.appendChild(renderCitation(citation, index));
      });
      citationSection.appendChild(list);
    } else {
      citationSection.appendChild(el("p", "muted", "无引用"));
    }
    card.appendChild(citationSection);

    if (report.disclaimer) {
      card.appendChild(el("p", "disclaimer", "免责声明：" + report.disclaimer));
    }
    area.appendChild(card);
  }

  function renderDenied(payload) {
    const area = $("#assessment-result");
    area.replaceChildren();
    const card = el("div", "report-card denied");
    card.appendChild(el("h3", "denied-title", "评估被拒绝 · 零证据"));
    card.appendChild(
      renderKeyValue([
        ["状态", payload.status || "DENIED"],
        ["原因", payload.reason || "ACCESS_DENIED"],
        ["检索数量", String(payload.retrieved_count ?? 0)],
        [
          "LLM 调用",
          payload.llm_invoked ? "是" : "否（授权裁决后零调用）",
        ],
        ["引用", "无"],
      ])
    );
    card.appendChild(el("p", "disclaimer", BANK_LABEL_DISCLAIMER));
    area.appendChild(card);
  }

  function renderQaResult(payload) {
    const area = $("#qa-result");
    area.replaceChildren();
    const status = payload.status || "UNKNOWN";
    if (status === "ANSWERED") {
      const card = el("div", "report-card");
      card.appendChild(el("h3", "qa-title", "问答回答"));
      card.appendChild(
        renderKeyValue([
          ["LLM 调用", "已调用（真实模型生成）"],
          ["引用证据", String((payload.citations || []).length) + " 条"],
        ])
      );
      const answer = payload.answer || "（模型未返回回答文本）";
      card.appendChild(el("p", "qa-answer", answer));
      const citations = payload.citations || [];
      if (citations.length) {
        const list = el("ul", "citations");
        citations.forEach((citation, index) => {
          list.appendChild(renderCitation(citation, index));
        });
        card.appendChild(list);
      }
      card.appendChild(el("p", "disclaimer", BANK_LABEL_DISCLAIMER));
      area.appendChild(card);
      return;
    }
    if (status === "DENIED") {
      const card = el("div", "report-card denied");
      card.appendChild(el("h3", "denied-title", "访问受限（环境受限 / 无权访问）"));
      card.appendChild(
        renderKeyValue([
          ["状态", status],
          ["原因", payload.reason || "ACCESS_DENIED"],
          ["已检索资料", String(payload.retrieved_count ?? 0)],
          ["LLM 调用", "未调用（授权前置拦截）"],
          ["回答", "无"],
        ])
      );
      card.appendChild(el("p", "disclaimer", BANK_LABEL_DISCLAIMER));
      area.appendChild(card);
      return;
    }
    if (status === "REFUSED") {
      const card = el("div", "report-card denied");
      card.appendChild(el("h3", "denied-title", "模型暂不可用"));
      card.appendChild(
        renderKeyValue([
          ["状态", status],
          ["原因", payload.reason || "llm_unavailable"],
          ["LLM 调用", "未调用（模型未配置）"],
        ])
      );
      card.appendChild(el("p", "disclaimer", BANK_LABEL_DISCLAIMER));
      area.appendChild(card);
      return;
    }
    area.appendChild(el("p", "report-error", "未知状态：" + status));
  }

  function renderError(message) {
    const area = $("#assessment-result");
    area.replaceChildren(el("p", "report-error", message));
  }

  async function login(event) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    try {
      await jsonRequest("/api/session/login", {
        body: {
          username: form.get("username"),
          password: form.get("password"),
        },
      });
      setStatus("登录成功");
      $("#login-panel").classList.add("hidden");
      $("#demo-panel").classList.remove("hidden");
    } catch (error) {
      setStatus("登录失败：" + error.message);
    }
  }

  async function createRuleVersion(event) {
    event.preventDefault();
    const result = $("#assessment-result");
    result.replaceChildren(el("p", "report-empty", "正在创建演示规则版本…"));
    try {
      const payload = await jsonRequest("/api/rule-sets", {
        body: {
          scenario: "finance_profile_matching",
          name: "演示银行规则样例",
          status: "active",
          source_type: "demo_fixture",
          version_label: "demo-2026-08-14",
          redacted_rule_summary: "脱敏演示规则：收入证明、流水、身份证明",
        },
      });
      const ruleVersion = payload.rule_version;
      result.replaceChildren(
        el("p", "report-empty", "规则版本已创建：" + ruleVersion.rule_version_id)
      );
      $("input[name='rule_version_id']").value = ruleVersion.rule_version_id;
    } catch (error) {
      renderError("创建规则版本失败：" + error.message);
    }
  }

  function handleFileSelection(event) {
    const picker = event.currentTarget;
    const files = Array.from(picker.files || []);
    const status = $("#file-picker-status");
    const note = $("#file-picker-note");
    if (files.length === 0) {
      status.className = "file-status";
      status.textContent = "未选择文件。请从受控样例清单中选择 PDF 或 DOCX。";
      note.classList.add("hidden");
      return;
    }
    const unknown = files.filter((file) => !CONTROLLED_FILE_NAMES.has(file.name));
    if (unknown.length > 0) {
      status.className = "file-status file-status-error";
      status.textContent =
        "检测到非受控文件（" +
        unknown.map((file) => file.name).join("、") +
        "）：仅支持 import-manifest 受控样例，任意上传会被底层拒绝。";
      note.classList.add("hidden");
      picker.value = "";
      return;
    }
    const selected = files.map((file) => {
      const sample = CONTROLLED_SAMPLE_FILES.find((item) => item.name === file.name);
      return sample ? sample.material : file.name;
    });
    status.className = "file-status file-status-ok";
    status.textContent =
      "已识别 " + files.length + " 个受控样例：" + selected.join("、") + "。";
    note.classList.remove("hidden");
  }

  async function assess(event) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const result = $("#assessment-result");
    const assetIds = String(form.get("asset_ids") || "")
      .split(",")
      .map((item) => item.trim())
      .filter(Boolean);
    const picker = $("#demo-file-picker");
    const hasControlledFiles = picker && picker.files && picker.files.length > 0;
    if (!assetIds.length) {
      renderError(
        hasControlledFiles
          ? "已选择受控样例，请在“资产 ID”输入框中填写对应受控资产 ID（资产由演示环境初始化提供）后发起评估。"
          : "请先填写资产 ID（或使用下方受控样例文件选择器）。"
      );
      return;
    }
    result.replaceChildren(el("p", "report-empty", "正在生成预评估报告…"));
    try {
      const payload = await jsonRequest("/api/assessments", {
        body: {
          scenario: form.get("scenario"),
          query_subject: form.get("query_subject"),
          asset_ids: assetIds,
          rule_version_id: form.get("rule_version_id"),
        },
      });
      renderReport(payload.report);
    } catch (error) {
      if (error.status === 403) {
        renderDenied(error.payload || {});
      } else {
        renderError("预评估失败：" + error.message);
      }
    }
  }

  async function ask(event) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const result = $("#qa-result");
    result.replaceChildren();
    result.appendChild(el("p", "report-empty", "正在检索并生成回答…"));
    try {
      const payload = await jsonRequest("/api/retrieval/query", {
        body: {
          question: form.get("question"),
          asset_id: form.get("asset_id"),
        },
      });
      renderQaResult(payload);
    } catch (error) {
      result.replaceChildren(
        el("p", "report-error", "问答失败：" + error.message)
      );
    }
  }


  async function loadProviderStatus() {
    const status = $("#model-status");
    const buttons = document.querySelectorAll(".model-btn");
    if (!status) return;
    try {
      const payload = await jsonRequest("/api/llm/provider", { method: "GET" });
      const current = payload.current || "local";
      const labelMap = {};
      (payload.providers || []).forEach((item) => {
        labelMap[item.id] = item.label;
      });
      buttons.forEach((button) => {
        const active = button.dataset.provider === current;
        button.classList.toggle("active", active);
        button.setAttribute("aria-pressed", active ? "true" : "false");
      });
      status.textContent = "当前：本地模型（Ollama qwen3.5:9b）";
      if (labelMap[current]) {
        status.textContent = "当前：" + labelMap[current];
      }
    } catch (error) {
      status.textContent = "模型状态获取失败：" + error.message;
    }
  }

  async function switchProvider(event) {
    const button = event.currentTarget;
    const providerId = button.dataset.provider;
    const status = $("#model-status");
    if (status) status.textContent = "正在切换模型…";
    try {
      const payload = await jsonRequest("/api/llm/provider", {
        body: { provider: providerId },
      });
      const labelMap = {};
      (payload.providers || []).forEach((item) => {
        labelMap[item.id] = item.label;
      });
      document.querySelectorAll(".model-btn").forEach((btn) => {
        const active = btn.dataset.provider === payload.current;
        btn.classList.toggle("active", active);
        btn.setAttribute("aria-pressed", active ? "true" : "false");
      });
      if (status) status.textContent = "当前：" + (labelMap[payload.current] || payload.current);
    } catch (error) {
      if (status) status.textContent = "切换失败：" + error.message;
    }
  }

  function switchTab(event) {
    const target = event.currentTarget.dataset.tab;

  const modelButtons = document.querySelectorAll(".model-btn");
  modelButtons.forEach((button) => {
    button.addEventListener("click", switchProvider);
  });
  loadProviderStatus();

  document.querySelectorAll(".tab").forEach((button) => {
      button.classList.toggle("active", button.dataset.tab === target);
    });
    document.querySelectorAll(".tab-panel").forEach((panel) => {
      panel.classList.toggle("hidden", panel.id !== target);
    });
  }

  $("#login-form").addEventListener("submit", login);
  $("#create-rule").addEventListener("click", createRuleVersion);
  $("#assessment-form").addEventListener("submit", assess);
  $("#qa-form").addEventListener("submit", ask);
  const filePicker = $("#demo-file-picker");
  if (filePicker) {
    filePicker.addEventListener("change", handleFileSelection);
  }
  document.querySelectorAll(".tab").forEach((button) => {
    button.addEventListener("click", switchTab);
  });
})();
