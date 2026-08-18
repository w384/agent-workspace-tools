from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from typing import Any, Mapping, Sequence

import httpx

from service.app.rag.contracts import (
    LLMConfigurationError,
    LLMUnavailableError,
    SearchHit,
)


@dataclass(frozen=True, slots=True)
class LLMConfig:
    base_url: str
    api_key: str
    model: str
    timeout_seconds: float = 30.0


def load_llm_config(
    environment: Mapping[str, str],
) -> LLMConfig:
    base_url = environment.get("RAG_LLM_BASE_URL", "").strip()
    api_key = environment.get("RAG_LLM_API_KEY", "").strip()
    model = environment.get("RAG_LLM_MODEL", "").strip()
    if not base_url or not model:
        raise LLMConfigurationError(
            "RAG_LLM_BASE_URL and RAG_LLM_MODEL must be injected; "
            "RAG_LLM_API_KEY is optional for local endpoints"
        )
    raw_timeout = environment.get(
        "RAG_LLM_TIMEOUT_SECONDS", ""
    ).strip()
    timeout_seconds = (
        float(raw_timeout) if raw_timeout else 30.0
    )
    if timeout_seconds <= 0:
        raise LLMConfigurationError(
            "RAG_LLM_TIMEOUT_SECONDS must be positive"
        )
    return LLMConfig(
        base_url=base_url,
        api_key=api_key,
        model=model,
        timeout_seconds=timeout_seconds,
    )


def build_llm_answer_generator(
    environment: Mapping[str, str],
) -> LLMAnswerGenerator:
    """Build a real answer generator from injected environment credentials."""
    return LLMAnswerGenerator(
        client=LLMClient(config=load_llm_config(environment))
    )


def build_llm_explanation_port(
    environment: Mapping[str, str],
) -> LLMExplanationPort:
    """Build a real explanation port from injected environment credentials."""
    return LLMExplanationPort(
        client=LLMClient(config=load_llm_config(environment))
    )


class LLMClient:
    """OpenAI-compatible chat completions client with injectable transport."""

    def __init__(
        self,
        *,
        config: LLMConfig,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._config = config
        self._transport = transport

    def complete(
        self,
        *,
        system: str,
        user: str,
    ) -> str:
        endpoint = (
            f"{self._config.base_url.rstrip('/')}/chat/completions"
        )
        payload = {
            "model": self._config.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": 0.0,
        }
        headers = {
            "Content-Type": "application/json",
        }
        if self._config.api_key:
            headers["Authorization"] = f"Bearer {self._config.api_key}"
        try:
            with httpx.Client(
                transport=self._transport,
                timeout=self._config.timeout_seconds,
            ) as client:
                response = client.post(
                    endpoint,
                    json=payload,
                    headers=headers,
                )
                response.raise_for_status()
                data = response.json()
        except (httpx.HTTPError, ValueError) as error:
            raise LLMUnavailableError(
                f"LLM request failed: {type(error).__name__}"
            ) from error

        try:
            content = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as error:
            raise LLMUnavailableError(
                "LLM response missing message content"
            ) from error
        if not isinstance(content, str) or not content.strip():
            raise LLMUnavailableError(
                "LLM response content is empty"
            )
        return content.strip()


class LLMAnswerGenerator:
    """Draft an answer from authorized evidence via a real LLM."""

    def __init__(self, *, client: LLMClient) -> None:
        self._client = client

    def generate(
        self,
        *,
        question: str,
        evidence: Sequence[SearchHit],
    ) -> str:
        system = (
            "你是企业资料知识库问答助手。你只依据用户提供的授权证据"
            "草拟回答；不得进行授权裁决，不得输出评分、贷款、授信、"
            "额度或金融产品推荐。证据不足时如实说明证据不足。"
        )
        evidence_blocks = [
            (
                f"[asset={hit.chunk.asset_id} "
                f"version={hit.chunk.asset_version_id} "
                f"chunk={hit.chunk.chunk_id} "
                f"page={hit.chunk.page_number} "
                f"paragraph={hit.chunk.paragraph_index}] "
                f"{hit.chunk.text}"
            )
            for hit in evidence
        ]
        user = (
            f"问题：{question}"
            "授权证据（仅以下内容可引用）："
            + " ".join(evidence_blocks)
        )
        return self._client.complete(
            system=system,
            user=user,
        )


class LLMExplanationPort:
    """Polish a deterministic structured match result via a real LLM."""

    def __init__(self, *, client: LLMClient) -> None:
        self._client = client

    def explain(
        self,
        structured_result: Any,
    ) -> str:
        system = (
            "你是资料匹配报告润色助手。将结构化匹配结果润色为"
            "人类可读的中文解释；不得改动确定性事实，不得输出授权"
            "结论、评分、贷款、授信、额度或金融产品推荐。"
        )
        snapshot = asdict(structured_result)
        user = (
            "结构化匹配结果（仅作为润色素材，不可改变数值与结论）："
            + json.dumps(snapshot, ensure_ascii=False, indent=2)
        )
        return self._client.complete(
            system=system,
            user=user,
        )
