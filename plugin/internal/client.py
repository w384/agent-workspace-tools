from typing import Any

import requests

from .messages import (
    INVALID_SERVICE_RESPONSE_MESSAGE,
    SERVICE_CONNECTION_MESSAGE,
    SERVICE_TIMEOUT_MESSAGE,
    safe_service_message,
)


class WorkspaceServiceError(RuntimeError):
    def __init__(
        self,
        code: str,
        message: str,
        status_code: int | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.status_code = status_code


class WorkspaceTimeoutError(WorkspaceServiceError):
    pass


class WorkspaceClient:
    def __init__(
        self,
        base_url: str,
        api_key: str,
        *,
        timeout_seconds: float = 15.0,
        session: requests.Session | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout_seconds = timeout_seconds
        self.session = session or requests.Session()

    def request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        normalized_method = method.upper()
        attempts = 3 if normalized_method == "GET" else 1
        for attempt in range(attempts):
            try:
                response = self.session.request(
                    method=normalized_method,
                    url=f"{self.base_url}/{path.lstrip('/')}",
                    headers={"X-API-Key": self.api_key},
                    timeout=self.timeout_seconds,
                    **kwargs,
                )
            except requests.RequestException as error:
                if attempt + 1 < attempts:
                    continue
                if isinstance(error, requests.Timeout):
                    raise WorkspaceTimeoutError(
                        "service_timeout",
                        SERVICE_TIMEOUT_MESSAGE,
                    ) from None
                raise WorkspaceServiceError(
                    "service_unavailable",
                    SERVICE_CONNECTION_MESSAGE,
                ) from None

            try:
                payload = response.json()
            except ValueError:
                raise WorkspaceServiceError(
                    "invalid_service_response",
                    INVALID_SERVICE_RESPONSE_MESSAGE,
                    response.status_code,
                ) from None

            if not isinstance(payload, dict):
                raise WorkspaceServiceError(
                    "invalid_service_response",
                    INVALID_SERVICE_RESPONSE_MESSAGE,
                    response.status_code,
                )
            if response.status_code >= 400:
                detail = payload.get("error", {})
                if not isinstance(detail, dict):
                    detail = {}
                message = safe_service_message(
                    detail.get("message"),
                    api_key=self.api_key,
                )
                raise WorkspaceServiceError(
                    str(detail.get("code", "service_error")),
                    message,
                    response.status_code,
                )
            return payload
        raise AssertionError("request retry loop exited unexpectedly")
