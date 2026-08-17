import importlib

import pytest
from fastapi.testclient import TestClient


def test_health_endpoint_returns_service_status():
    """服务必须通过 /health 返回固定的健康状态。"""
    try:
        main_module = importlib.import_module("service.app.main")
    except ModuleNotFoundError:
        pytest.fail("service.app.main 尚未实现")

    client = TestClient(main_module.app)
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "agent-workspace-tools",
    }