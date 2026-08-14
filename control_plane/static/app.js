/* Minimal demo entry. The browser only talks to this BFF; RAG and Dify are not reachable directly. */
(function () {
  "use strict";

  const $ = (selector) => document.querySelector(selector);

  function setStatus(message) {
    $("#login-status").textContent = message;
  }

  async function jsonRequest(path, options) {
    const response = await fetch(path, {
      method: options.method || "POST",
      headers: options.json ? { "Content-Type": "application/json" } : undefined,
      body: options.body ? JSON.stringify(options.body) : undefined,
      credentials: "same-origin",
    });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) {
      const detail = payload.error ? payload.error.code : "request_failed";
      const error = new Error(detail);
      error.status = response.status;
      throw error;
    }
    return payload;
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
    result.textContent = "正在创建演示规则版本…";
    try {
      const payload = await jsonRequest("/api/rule-sets", {
        body: {
          scenario: "finance_profile_matching",
          name: "演示银行规则样例",
          status: "active",
          source_type: "demo_fixture",
          version_label: "demo-2026-08-14",
          content_fingerprint: "sha256:rule-demo-v1",
          redacted_rule_summary: "脱敏演示规则：收入证明、流水、身份证明",
        },
      });
      const ruleVersion = payload.rule_version;
      result.textContent = "规则版本已创建：" + ruleVersion.rule_version_id;
      $("input[name='rule_version_id']").value = ruleVersion.rule_version_id;
    } catch (error) {
      result.textContent = "创建规则版本失败：" + error.message;
    }
  }

  async function assess(event) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const result = $("#assessment-result");
    result.textContent = "正在生成预评估报告…";
    const assetIds = String(form.get("asset_ids") || "")
      .split(",")
      .map((item) => item.trim())
      .filter(Boolean);
    try {
      const payload = await jsonRequest("/api/assessments", {
        body: {
          scenario: form.get("scenario"),
          query_subject: form.get("query_subject"),
          asset_ids: assetIds,
          rule_version_id: form.get("rule_version_id"),
        },
      });
      result.textContent = JSON.stringify(payload.report, null, 2);
    } catch (error) {
      result.textContent = "预评估失败：" + error.message;
    }
  }

  async function ask(event) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const result = $("#qa-result");
    result.textContent = "正在检索…";
    try {
      const payload = await jsonRequest("/api/retrieval/query", {
        body: {
          question: form.get("question"),
          asset_id: form.get("asset_id"),
        },
      });
      result.textContent = JSON.stringify(payload, null, 2);
    } catch (error) {
      result.textContent = "问答失败：" + error.message;
    }
  }

  function switchTab(event) {
    const target = event.currentTarget.dataset.tab;
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
  document.querySelectorAll(".tab").forEach((button) => {
    button.addEventListener("click", switchTab);
  });
})();
