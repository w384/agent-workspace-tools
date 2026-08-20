"""BFF-side LLM provider registry for the finance demo path-B query.

The demo exposes two runtime-switchable answer providers:

- "local" (default): Ollama served via its OpenAI-compatible endpoint,
  model qwen3.5:9b, no API key required.
- "cloud": DeepSeek OpenAI-compatible endpoint. The API key is never
  exposed to the frontend, the BFF response, or the audit trail; it is
  injected only through the environment.

The registry is owned by the control plane (BFF). Switching only rebuilds
the answer generator used by the RAG query path; the authorization gate
(DENY-before-scoring) and the deterministic path-A assessment are unchanged.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Mapping

from service.app.rag.contracts import LLMConfigurationError
from service.app.rag.llm import build_llm_answer_generator


LOCAL_PROVIDER_ID = "local"
CLOUD_PROVIDER_ID = "cloud"


@dataclass(frozen=True, slots=True)
class ProviderDescriptor:
    id: str
    label: str
    model: str


@dataclass(frozen=True, slots=True)
class ProviderSecrets:
    base_url: str
    api_key: str
    model: str


def _local_secrets(environment: Mapping[str, str]) -> ProviderSecrets:
    return ProviderSecrets(
        base_url=environment.get(
            "RAG_LLM_LOCAL_BASE_URL", "http://localhost:11434/v1"
        ).strip(),
        api_key=environment.get("RAG_LLM_LOCAL_API_KEY", "").strip(),
        model=environment.get("RAG_LLM_LOCAL_MODEL", "qwen3.5:9b").strip(),
    )


def _cloud_secrets(environment: Mapping[str, str]) -> ProviderSecrets:
    return ProviderSecrets(
        base_url=environment.get(
            "RAG_LLM_BASE_URL", "https://api.deepseek.com/v1"
        ).strip(),
        api_key=environment.get("RAG_LLM_API_KEY", "").strip(),
        model=environment.get("RAG_LLM_MODEL", "deepseek-chat").strip(),
    )


class LLMProviderRegistry:
    """Owns the current provider and rebuilds answer generators on switch.

    The registry only exposes non-secret descriptors to the BFF/frontend.
    Credentials are read from the environment at switch time and never
    leave this class.
    """

    def __init__(self, *, environment: Mapping[str, str] | None = None) -> None:
        self._environment = os.environ if environment is None else environment
        self._current = LOCAL_PROVIDER_ID
        self._cloud_api_key_override: str | None = None
        self._answer_generator: object | None = self._build(LOCAL_PROVIDER_ID)

    @property
    def current(self) -> str:
        return self._current

    @property
    def answer_generator(self) -> object | None:
        return self._answer_generator

    def descriptors(self) -> list[ProviderDescriptor]:
        return [
            ProviderDescriptor(
                id=LOCAL_PROVIDER_ID,
                label="本地模型（Ollama qwen3.5:9b）",
                model="qwen3.5:9b",
            ),
            ProviderDescriptor(
                id=CLOUD_PROVIDER_ID,
                label="联网模型（DeepSeek）",
                model=_cloud_secrets(self._environment).model,
            ),
        ]

    @property
    def cloud_key_configured(self) -> bool:
        """True when a cloud (DeepSeek) API key is available in memory/env.

        Only the boolean is surfaced to the BFF/frontend; the key itself is
        never exposed in responses or audits.
        """
        if self._cloud_api_key_override:
            return True
        return bool(_cloud_secrets(self._environment).api_key)

    def switch(self, provider_id: str, api_key: str | None = None) -> bool:
        if provider_id not in (LOCAL_PROVIDER_ID, CLOUD_PROVIDER_ID):
            raise ValueError(f"unknown LLM provider: {provider_id}")
        if api_key and api_key.strip():
            # Runtime-injected key (typed into the demo UI). Held in memory
            # only; never persisted, never echoed in responses or audits.
            self._cloud_api_key_override = api_key.strip()
        self._answer_generator = self._build(provider_id)
        self._current = provider_id
        return True
    def clear_cloud_key(self) -> None:
        """Drop any runtime-typed cloud API key and fall back to local when
        the cloud provider can no longer be used (called on logout).
        Only the runtime override is session-scoped; an environment-provided
        key (if any) is left untouched.
        """
        self._cloud_api_key_override = None
        if self._current == CLOUD_PROVIDER_ID and not self.cloud_key_configured:
            self._current = LOCAL_PROVIDER_ID
            self._answer_generator = self._build(LOCAL_PROVIDER_ID)
    def _build(self, provider_id: str) -> object | None:
        secrets = (
            _local_secrets(self._environment)
            if provider_id == LOCAL_PROVIDER_ID
            else _cloud_secrets(self._environment)
        )
        environment = dict(self._environment)
        environment["RAG_LLM_BASE_URL"] = secrets.base_url
        if provider_id == CLOUD_PROVIDER_ID:
            environment["RAG_LLM_API_KEY"] = (
                self._cloud_api_key_override or secrets.api_key
            )
        else:
            environment["RAG_LLM_API_KEY"] = secrets.api_key
        environment["RAG_LLM_MODEL"] = secrets.model
        try:
            return build_llm_answer_generator(environment)
        except LLMConfigurationError:
            return None
