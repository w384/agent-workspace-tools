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

  let cloudKeyConfigured = false;
  // 当前问答展示的模型名（回答卡片标注真实调用来源）
  let currentModelLabel = "本地模型（Ollama qwen3.5:9b）";
  // 会话内已上传的真实材料（自动建库），登出时清空
  let qaUploadedFiles = [];
  // 本会话真正上传成功的文件（409 时用于区分「本人上传」还是「可能其他账号」）
  let qaOwnUploaded = [];
  // 当前问答选中的文件：{ name, kind: "uploaded" | "controlled" }
  let qaSelectedFile = null;

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

  async function multipartRequest(path, formData) {
    const response = await fetch(path, {
      method: "POST",
      body: formData,
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
        ["缺失材料", missing.length ? missing.join("、") : "无"],
      ])
    );

    const candidates = report.candidate_banks || [];
    if (candidates.length) {
      const candidateSection = el("div", "report-section");
      candidateSection.appendChild(el("h3", null, "可匹配示例银行"));
      const list = el("ul", "candidate-banks");
      candidates.forEach((candidate) => {
        const item = el("li", "candidate-bank");
        item.appendChild(el("span", "candidate-bank-label", candidate.bank_label || "示例银行"));
        item.appendChild(
          renderKeyValue([
            ["匹配度", (candidate.match_score ?? "—") + " / 100"],
            ["结果级别", candidate.result_level || "—"],
            ["缺失材料", (candidate.missing_materials || []).length ? candidate.missing_materials.join("、") : "无"],
          ])
        );
        list.appendChild(item);
      });
      candidateSection.appendChild(list);
      card.appendChild(candidateSection);
    }
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
          ["模型", currentModelLabel],
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
      card.appendChild(el("h3", "denied-title", "你没有访问该文件的权限"));
      card.appendChild(
        el("p", "denied-hint", "该文件由其他账号上传，仅上传者有权检索；可改用受控样例文件体验问答。")
      );
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
      const username = String(form.get("username") || "");
      renderUserChip(username);
      // 重新登录后强制同步一次模型状态，避免上次会话的云端 Key 残留
      loadProviderStatus();
      loadKnowledgeFiles();
    } catch (error) {
      setStatus("登录失败：" + error.message);
    }
  }

  function renderUserChip(username) {
    const area = $("#user-area");
    if (!area) return;
    const avatar = $("#user-avatar");
    const nameEl = $("#user-name");
    const initial = username.charAt(0).toUpperCase();
    if (avatar) avatar.textContent = initial;
    if (nameEl) nameEl.textContent = username;
    area.classList.remove("hidden");
  }

  // 常驻指示条：任何时候都让用户看到「接下来提问谁」
  function updateQaCurrentTarget() {
    const target = $("#qa-current-target");
    if (!target) return;
    if (qaSelectedFile) {
      const source = qaSelectedFile.kind === "uploaded" ? "已上传材料" : "受控样例";
      target.className = "file-status file-status-ok";
      target.textContent =
        "当前将提问：" + qaSelectedFile.name + "（来源：" + source + "）";
    } else {
      target.className = "file-status";
      target.textContent = "尚未选择文件，请上传真实材料或选择受控样例。";
    }
  }

  // 登出时重置模型区：清空云端 Key（BFF 已同步清）、回退本地模型高亮
  function resetModelUi() {
    cloudKeyConfigured = false;
    currentModelLabel = "本地模型（Ollama qwen3.5:9b）";
    const keyPanel = $("#cloud-key-panel");
    if (keyPanel) keyPanel.classList.add("hidden");
    const keyInput = $("#cloud-api-key");
    if (keyInput) keyInput.value = "";
    document.querySelectorAll(".model-btn").forEach((btn) => {
      const active = btn.dataset.provider === "local";
      btn.classList.toggle("active", active);
      btn.setAttribute("aria-pressed", active ? "true" : "false");
    });
    const status = $("#model-status");
    if (status) status.textContent = "当前：" + currentModelLabel;
  }

  async function logout() {
    try {
      await jsonRequest("/api/session/logout", { method: "POST" });
    } catch (error) {
      // 登出失败也强制回登录页
    }
    $("#user-area").classList.add("hidden");
    $("#demo-panel").classList.add("hidden");
    $("#login-panel").classList.remove("hidden");
    const ar = $("#assessment-result");
    if (ar) ar.replaceChildren();
    const qr = $("#qa-result");
    if (qr) qr.replaceChildren();
    resetControlledFilePickers();
    resetUploadedMaterials();
    resetKnowledgeFiles();
    resetModelUi();
    activateTab("assessment");
    const status = $("#login-status");
    if (status) status.textContent = "已登出。";
    $("#login-form").reset();
  }

  function resetControlledFilePickers() {
    const pickers = ["#demo-file-picker", "#qa-file-picker"];
    pickers.forEach((selector) => {
      const picker = $(selector);
      if (picker) picker.value = "";
    });
    const statuses = ["#file-picker-status", "#qa-file-picker-status"];
    statuses.forEach((selector) => {
      const status = $(selector);
      if (status) {
        status.className = "file-status";
        status.textContent = "未选择文件。";
      }
    });
    const note = $("#file-picker-note");
    if (note) note.classList.add("hidden");
  }

  function resetUploadedMaterials() {
    qaUploadedFiles = [];
    qaOwnUploaded = [];
    qaSelectedFile = null;
    updateQaCurrentTarget();
    const wrap = $("#qa-uploaded-list");
    if (wrap) wrap.classList.add("hidden");
    const list = $("#qa-uploaded-items");
    if (list) list.replaceChildren();
    const picker = $("#qa-upload-picker");
    if (picker) picker.value = "";
    const status = $("#qa-upload-status");
    if (status) {
      status.className = "file-status";
      status.textContent = "未上传文件。";
    }
  }

  // 已建库文件管理：加载当前 workspace 已上传并建库的真实材料文件
  async function loadKnowledgeFiles() {
    try {
      const payload = await jsonRequest("/api/demo/knowledge/files", {
        method: "GET",
      });
      renderKnowledgeFiles(payload.files || []);
    } catch (error) {
      const list = $("#knowledge-file-list");
      if (list) {
        list.replaceChildren(
          el(
            "p",
            "file-status file-status-error",
            "加载已建库文件失败：" + error.message
          )
        );
      }
    }
  }

  function renderKnowledgeFiles(files) {
    const list = $("#knowledge-file-list");
    if (!list) return;
    list.replaceChildren();
    if (!files || files.length === 0) {
      list.appendChild(el("p", "file-status", "尚未上传任何真实材料文件。"));
      return;
    }
    const ul = el("ul", "knowledge-file-items");
    files.forEach((file) => {
      const li = el("li", "knowledge-file-item");
      const nameSpan = el("span", "knowledge-file-name", file.name);
      li.appendChild(nameSpan);
      if (file.can_delete) {
        const delBtn = el("button", "knowledge-file-del", "删除");
        delBtn.type = "button";
        delBtn.addEventListener("click", () => deleteKnowledgeFile(file.name));
        li.appendChild(delBtn);
      }
      ul.appendChild(li);
    });
    list.appendChild(ul);
  }

  async function deleteKnowledgeFile(name) {
    const list = $("#knowledge-file-list");
    if (!window.confirm("确认删除已建库文件「" + name + "」？删除后可重新上传。")) {
      return;
    }
    try {
      await jsonRequest("/api/demo/knowledge/files/delete", {
        body: { file_name: name },
      });
      // 若删除的正是当前选中的上传文件，清空选择
      if (
        qaSelectedFile &&
        qaSelectedFile.kind === "uploaded" &&
        qaSelectedFile.name === name
      ) {
        qaSelectedFile = null;
        updateQaCurrentTarget();
        const hiddenField = $('[name="file_name"]');
        if (hiddenField) hiddenField.value = "";
        const status = $("#qa-upload-status");
        if (status) {
          status.className = "file-status";
          status.textContent = "未上传文件。";
        }
      }
      qaUploadedFiles = qaUploadedFiles.filter((item) => item !== name);
      qaOwnUploaded = qaOwnUploaded.filter((item) => item !== name);
      renderUploadedFiles();
      await loadKnowledgeFiles();
    } catch (error) {
      if (list) {
        list.prepend(
          el("p", "file-status file-status-error", "删除失败：" + error.message)
        );
      }
    }
  }

  function resetKnowledgeFiles() {
    const list = $("#knowledge-file-list");
    if (list) list.replaceChildren();
  }

  function renderUploadedFiles() {
    const wrap = $("#qa-uploaded-list");
    const list = $("#qa-uploaded-items");
    if (!wrap || !list) return;
    list.replaceChildren();
    qaUploadedFiles.forEach((name) => {
      const item = el("li", "uploaded-file");
      const btn = el("button", "uploaded-file-btn", name);
      btn.type = "button";
      btn.addEventListener("click", () => selectUploadedFile(name));
      item.appendChild(btn);
      list.appendChild(item);
    });
    wrap.classList.toggle("hidden", qaUploadedFiles.length === 0);
  }

  function selectUploadedFile(name) {
    qaSelectedFile = { name: name, kind: "uploaded" };
    const hiddenField = $('[name="file_name"]');
    if (hiddenField) hiddenField.value = "";
    const status = $("#qa-upload-status");
    if (status) {
      status.className = "file-status file-status-ok";
      status.textContent = "已选择：" + name + "。点击「提问」开始检索。";
    }
    const qaStatus = $("#qa-file-picker-status");
    if (qaStatus) {
      qaStatus.className = "file-status";
      qaStatus.textContent = "未选择文件。";
    }
    document.querySelectorAll(".uploaded-file-btn").forEach((btn) => {
      btn.classList.toggle("active", btn.textContent === name);
    });
    updateQaCurrentTarget();
  }

  async function uploadRealMaterial() {
    const picker = $("#qa-upload-picker");
    const status = $("#qa-upload-status");
    const file = picker && picker.files && picker.files[0];
    if (!file) {
      if (status) {
        status.className = "file-status file-status-error";
        status.textContent = "请先选择要上传的真实材料（PDF/DOCX）。";
      }
      return;
    }
    const formData = new FormData();
    formData.append("file", file);
    if (status) {
      status.className = "file-status";
      status.textContent = "正在上传并建库…";
    }
    try {
      const payload = await multipartRequest("/api/demo/knowledge/upload", formData);
      if (!qaUploadedFiles.includes(payload.file_name)) {
        qaUploadedFiles.push(payload.file_name);
      }
      if (!qaOwnUploaded.includes(payload.file_name)) {
        qaOwnUploaded.push(payload.file_name);
      }
      renderUploadedFiles();
      selectUploadedFile(payload.file_name);
      if (picker) picker.value = "";
      if (status) {
        status.className = "file-status file-status-ok";
        status.textContent =
          "已上传并建库：" + payload.file_name + "（已自动选择，可直接提问）";
      }
    } catch (error) {
      if (status) {
        const dupCode =
          error.status === 409 &&
          error.payload &&
          error.payload.error &&
          error.payload.error.code === "upload_target_exists";
        if (dupCode && file) {
          const ownUpload = qaOwnUploaded.includes(file.name);
          if (!qaUploadedFiles.includes(file.name)) {
            qaUploadedFiles.push(file.name);
          }
          renderUploadedFiles();
          selectUploadedFile(file.name);
          status.className = "file-status file-status-ok";
          status.textContent = ownUpload
            ? "该文件本会话已上传过，已自动选中，可直接提问：" + file.name
            : "该文件已存在，可能是其他账号上传，你未必有访问权限。已为你选中，点「提问」验证：" + file.name;
        } else {
          status.className = "file-status file-status-error";
          status.textContent = "上传失败：" + error.message;
        }
      }
    }
  }

  function activateTab(target) {
    document.querySelectorAll(".tab").forEach((button) => {
      button.classList.toggle("active", button.dataset.tab === target);
    });
    document.querySelectorAll(".tab-panel").forEach((panel) => {
      panel.classList.toggle("hidden", panel.id !== target);
    });
  }

  function collectControlledFileNames(picker) {
    if (!picker || !picker.files || !picker.files.length) return [];
    return Array.from(picker.files)
      .filter((file) => CONTROLLED_FILE_NAMES.has(file.name))
      .map((file) => file.name);
  }

  function handleFileSelection(event) {
    const picker = event.currentTarget;
    const files = Array.from(picker.files || []);
    const isQa = picker.id === "qa-file-picker";
    const status = $(isQa ? "#qa-file-picker-status" : "#file-picker-status");
    const note = $("#file-picker-note");
    if (files.length === 0) {
      status.className = "file-status";
      status.textContent = "未选择文件。请从受控样例清单中选择 PDF 或 DOCX。";
      if (note) note.classList.add("hidden");
      return;
    }
    const unknown = files.filter((file) => !CONTROLLED_FILE_NAMES.has(file.name));
    if (unknown.length > 0) {
      status.className = "file-status file-status-error";
      status.textContent =
        "检测到非受控文件（" +
        unknown.map((file) => file.name).join("、") +
        "）：仅支持 import-manifest 受控样例，任意上传会被底层拒绝。";
      if (note) note.classList.add("hidden");
      picker.value = "";
      return;
    }
    const selected = files.map((file) => {
      const sample = CONTROLLED_SAMPLE_FILES.find((item) => item.name === file.name);
      return sample ? sample.material : file.name;
    });
    status.className = "file-status file-status-ok";
    status.textContent =
      "已识别 " + files.length + " 个受控样例：" + selected.join("、") +
      (isQa ? "。点击「提问」开始分析。" : "。点击「生成预评估报告」开始分析。");
    if (note) note.classList.remove("hidden");
    const names = files.map((file) => file.name);
    const hiddenField = isQa ? $('[name="file_name"]') : $('[name="file_names"]');
    if (hiddenField) hiddenField.value = names.join(",");
    if (isQa) {
      qaSelectedFile = { name: names[0], kind: "controlled" };
      const uploadStatus = $("#qa-upload-status");
      if (uploadStatus) {
        uploadStatus.className = "file-status";
        uploadStatus.textContent =
          "已选择受控样例：" + names[0] + "。点击「提问」开始分析。";
      }
      document.querySelectorAll(".uploaded-file-btn").forEach((btn) => {
        btn.classList.remove("active");
      });
      updateQaCurrentTarget();
    }
  }

  async function assess(event) {
    if (event && event.preventDefault) event.preventDefault();
    const form = event && event.currentTarget
      ? new FormData(event.currentTarget)
      : new FormData($("#assessment-form"));
    const result = $("#assessment-result");
    const hiddenNames = $('[name="file_names"]');
    const fileNames = hiddenNames && hiddenNames.value
      ? hiddenNames.value.split(",").filter(Boolean)
      : collectControlledFileNames($("#demo-file-picker"));
    if (!fileNames.length) {
      renderError("请先选择受控样例文件（资产 ID 已对演示隐藏）。");
      return;
    }
    result.replaceChildren(el("p", "report-empty", "正在生成预评估报告…"));
    try {
      const payload = await jsonRequest("/api/controlled-sample/assess", {
        body: {
          scenario: form.get("scenario"),
          query_subject: form.get("query_subject"),
          file_names: fileNames,
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
    if (event && event.preventDefault) event.preventDefault();
    const form = event && event.currentTarget
      ? new FormData(event.currentTarget)
      : new FormData($("#qa-form"));
    const result = $("#qa-result");
    const question = (form.get("question") || "").trim();
    if (!question) {
      result.replaceChildren(el("p", "report-error", "请先输入问题。"));
      return;
    }
    const hiddenFile = $('[name="file_name"]');
    const controlledNames = hiddenFile && hiddenFile.value
      ? hiddenFile.value.split(",").filter(Boolean)
      : collectControlledFileNames($("#qa-file-picker"));
    let targetFile = null;
    if (qaSelectedFile && qaSelectedFile.kind === "uploaded") {
      targetFile = qaSelectedFile.name;
    } else if (controlledNames.length) {
      targetFile = controlledNames[0];
      qaSelectedFile = { name: targetFile, kind: "controlled" };
    }
    if (!targetFile) {
      result.replaceChildren(
        el("p", "report-error", "请先选择受控样例或上传真实材料后再提问。")
      );
      return;
    }
    result.replaceChildren();
    result.appendChild(el("p", "report-empty", "正在检索并生成回答…"));
    const endpoint = qaSelectedFile.kind === "uploaded"
      ? "/api/demo/knowledge/query"
      : "/api/controlled-sample/query";
    try {
      const payload = await jsonRequest(endpoint, {
        body: { question: question, file_name: targetFile },
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
      cloudKeyConfigured = !!payload.cloud_key_configured;
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
      currentModelLabel = labelMap[current] || current;
      status.textContent = "当前：" + currentModelLabel;
      if (!cloudKeyConfigured && current === "cloud") {
        status.textContent += "（未配置 Key，重新选择联网模型时需填写）";
      }
    } catch (error) {
      status.textContent = "模型状态获取失败：" + error.message;
    }
  }

  async function switchProvider(event) {
    const button = event.currentTarget;
    const providerId = button.dataset.provider;
    const status = $("#model-status");
    const keyPanel = $("#cloud-key-panel");
    if (providerId === "cloud" && !cloudKeyConfigured) {
      if (keyPanel) {
        keyPanel.classList.remove("hidden");
        const input = $("#cloud-api-key");
        if (input) input.focus();
      }
      if (status) {
        status.textContent = "联网模型未配置 DeepSeek API Key，请先填写后确认切换。";
      }
      return;
    }
    if (status) status.textContent = "正在切换模型…";
    try {
      const payload = await jsonRequest("/api/llm/provider", {
        body: { provider: providerId },
      });
      cloudKeyConfigured = !!payload.cloud_key_configured;
      if (keyPanel) keyPanel.classList.add("hidden");
      const labelMap = {};
      (payload.providers || []).forEach((item) => {
        labelMap[item.id] = item.label;
      });
      document.querySelectorAll(".model-btn").forEach((btn) => {
        const active = btn.dataset.provider === payload.current;
        btn.classList.toggle("active", active);
        btn.setAttribute("aria-pressed", active ? "true" : "false");
      });
      currentModelLabel = labelMap[payload.current] || payload.current;
      if (status) status.textContent = "当前：" + currentModelLabel;
    } catch (error) {
      if (status) status.textContent = "切换失败：" + error.message;
    }
  }

  async function confirmCloudKey() {
    const input = $("#cloud-api-key");
    const key = input ? input.value.trim() : "";
    const status = $("#model-status");
    const keyPanel = $("#cloud-key-panel");
    if (!key) {
      if (status) status.textContent = "请先填写 DeepSeek API Key。";
      if (input) input.focus();
      return;
    }
    if (status) status.textContent = "正在切换模型…";
    try {
      const payload = await jsonRequest("/api/llm/provider", {
        body: { provider: "cloud", api_key: key },
      });
      cloudKeyConfigured = !!payload.cloud_key_configured;
      if (keyPanel) keyPanel.classList.add("hidden");
      if (input) input.value = "";
      const labelMap = {};
      (payload.providers || []).forEach((item) => {
        labelMap[item.id] = item.label;
      });
      document.querySelectorAll(".model-btn").forEach((btn) => {
        const active = btn.dataset.provider === payload.current;
        btn.classList.toggle("active", active);
        btn.setAttribute("aria-pressed", active ? "true" : "false");
      });
      currentModelLabel = labelMap[payload.current] || payload.current;
      if (status) status.textContent = "当前：" + currentModelLabel;
    } catch (error) {
      if (status) status.textContent = "切换失败：" + error.message;
    }
  }

  function cancelCloudKey() {
    const keyPanel = $("#cloud-key-panel");
    if (keyPanel) keyPanel.classList.add("hidden");
    const input = $("#cloud-api-key");
    if (input) input.value = "";
    const status = $("#model-status");
    if (status) status.textContent = "已取消；继续使用当前模型。";
  }

  function switchTab(event) {
    const target = event.currentTarget.dataset.tab;
    activateTab(target);
  }

  const logoutBtn = $("#logout-btn");
  if (logoutBtn) logoutBtn.addEventListener("click", logout);
  const userChip = $("#user-chip");
  const logoutTip = $("#logout-tip");
  if (userChip && logoutTip) {
    userChip.addEventListener("mouseenter", () => logoutTip.classList.remove("hidden"));
    userChip.addEventListener("mouseleave", () => logoutTip.classList.add("hidden"));
    logoutTip.addEventListener("mouseenter", () => logoutTip.classList.remove("hidden"));
    logoutTip.addEventListener("mouseleave", () => logoutTip.classList.add("hidden"));
  }
  const cloudKeyConfirm = $("#cloud-key-confirm");
  if (cloudKeyConfirm) cloudKeyConfirm.addEventListener("click", confirmCloudKey);
  const cloudKeyCancel = $("#cloud-key-cancel");
  if (cloudKeyCancel) cloudKeyCancel.addEventListener("click", cancelCloudKey);
  const cloudKeyInput = $("#cloud-api-key");
  if (cloudKeyInput) {
    cloudKeyInput.addEventListener("keydown", (event) => {
      if (event.key === "Enter") {
        event.preventDefault();
        confirmCloudKey();
      }
    });
  }
  $("#login-form").addEventListener("submit", login);
  $("#assessment-form").addEventListener("submit", assess);
  $("#qa-form").addEventListener("submit", ask);
  const filePicker = $("#demo-file-picker");
  if (filePicker) {
    filePicker.addEventListener("change", handleFileSelection);
  }
  const qaFilePicker = $("#qa-file-picker");
  if (qaFilePicker) {
    qaFilePicker.addEventListener("change", handleFileSelection);
  }
  const qaUploadBtn = $("#qa-upload-btn");
  if (qaUploadBtn) qaUploadBtn.addEventListener("click", uploadRealMaterial);
  document.querySelectorAll(".tab").forEach((button) => {
    button.addEventListener("click", switchTab);
  });
  document.querySelectorAll(".model-btn").forEach((button) => {
    button.addEventListener("click", switchProvider);
  });
})();
