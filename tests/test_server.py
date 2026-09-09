"""Tests for FastAPI REST and WebSocket server."""

from __future__ import annotations

import pytest
from starlette.testclient import TestClient

from effero.core.agent import Agent
from effero.interfaces.server import create_app
from effero.safety.approval import AutoApprovalHandler


@pytest.fixture
def api_client():
    agent = Agent(approval_handler=AutoApprovalHandler(approve_all=True))
    app = create_app(agent=agent)
    with TestClient(app) as client:
        yield client, agent


def test_dashboard_endpoint(api_client) -> None:
    client, _ = api_client
    resp = client.get("/")
    assert resp.status_code == 200
    assert "Effero" in resp.text


def test_health_endpoint(api_client) -> None:
    client, _ = api_client
    resp = client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert "version" in data
    assert data["skills_count"] > 0


def test_agent_card_discovery(api_client) -> None:
    client, _ = api_client
    resp = client.get("/v1/agent-card")
    assert resp.status_code == 200
    card = resp.json()
    assert "name" in card
    assert "skills" in card
    assert len(card["skills"]) > 0


def test_list_skills(api_client) -> None:
    client, _ = api_client
    resp = client.get("/v1/skills")
    assert resp.status_code == 200
    skills = resp.json()["skills"]
    assert len(skills) > 0
    names = [s["name"] for s in skills]
    assert "robotics.arm.move_to" in names
    assert "robotics.navigate.go_to" in names


def test_invoke_skill(api_client) -> None:
    client, _ = api_client
    resp = client.post(
        "/v1/skills/invoke",
        json={"skill": "robotics.navigate.get_position", "arguments": {}},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["skill"] == "robotics.navigate.get_position"
    assert data["result"]["status"] == "success"


def test_semantic_memory_search(api_client) -> None:
    client, agent = api_client
    agent.semantic_memory.store("Safety: emergency shutdown procedures")

    resp = client.post(
        "/v1/memory/semantic/search",
        json={"query": "shutdown", "top_k": 1},
    )
    assert resp.status_code == 200
    results = resp.json()["results"]
    assert len(results) == 1
    assert "shutdown" in results[0]["text"]


def test_a2a_task_creation_and_polling(api_client) -> None:
    client, _ = api_client
    # Create task
    resp = client.post(
        "/v1/tasks",
        json={"sender": "peer-node-1", "instruction": "echo test", "context": {}},
    )
    assert resp.status_code == 200
    task_id = resp.json()["task_id"]

    # Poll task status
    poll_resp = client.get(f"/v1/tasks/{task_id}")
    assert poll_resp.status_code == 200
    assert poll_resp.json()["task_id"] == task_id


def test_server_authentication_enforcement() -> None:
    """Verify that when api_key is configured, requests without key or with invalid key are rejected."""
    from unittest.mock import AsyncMock

    agent = Agent(approval_handler=AutoApprovalHandler(approve_all=True))
    agent.config.server.api_key = "test-secret-key-12345"
    agent.chat = AsyncMock(return_value="hello back")  # type: ignore[method-assign]
    app = create_app(agent=agent)

    with TestClient(app) as client:
        # Public endpoints should work without auth
        assert client.get("/").status_code == 200
        assert client.get("/health").status_code == 200
        assert client.get("/v1/agent-card").status_code == 200
        assert client.get("/v1/skills").status_code == 200

        # Protected endpoint without auth -> 401
        res_no_auth = client.post("/v1/chat", json={"message": "hello"})
        assert res_no_auth.status_code == 401
        assert "Invalid or missing API key" in res_no_auth.json()["detail"]

        # Protected endpoint with bad auth -> 401
        res_bad_auth = client.post(
            "/v1/chat",
            json={"message": "hello"},
            headers={"Authorization": "Bearer wrong-token"},
        )
        assert res_bad_auth.status_code == 401

        # Protected endpoint with valid Bearer token -> 200
        res_bearer = client.post(
            "/v1/chat",
            json={"message": "hello"},
            headers={"Authorization": "Bearer test-secret-key-12345"},
        )
        assert res_bearer.status_code == 200

        # Protected endpoint with valid X-API-Key header -> 200
        res_header = client.post(
            "/v1/skills/invoke",
            json={"skill": "robotics.navigate.get_position", "arguments": {}},
            headers={"X-API-Key": "test-secret-key-12345"},
        )
        assert res_header.status_code == 200

        # Approvals endpoint protection
        res_approvals_unauth = client.get("/v1/approvals")
        assert res_approvals_unauth.status_code == 401

        res_approvals_auth = client.get(
            "/v1/approvals",
            headers={"X-API-Key": "test-secret-key-12345"},
        )
        assert res_approvals_auth.status_code == 200


def test_server_cors_configuration() -> None:
    """Verify CORS configuration adheres to spec."""
    # 1. Wildcard origin: allow_credentials must be False
    agent_wildcard = Agent()
    agent_wildcard.config.server.cors_origins = []
    app_wildcard = create_app(agent=agent_wildcard)

    cors_middleware = [m for m in app_wildcard.user_middleware if "CORSMiddleware" in str(m.cls)]
    assert len(cors_middleware) == 1
    assert cors_middleware[0].kwargs.get("allow_origins") == ["*"]
    assert cors_middleware[0].kwargs.get("allow_credentials") is False

    # 2. Specific origin: allow_credentials can be True
    agent_specific = Agent()
    agent_specific.config.server.cors_origins = ["https://dashboard.effero.io"]
    app_specific = create_app(agent=agent_specific)

    cors_middleware2 = [m for m in app_specific.user_middleware if "CORSMiddleware" in str(m.cls)]
    assert len(cors_middleware2) == 1
    assert cors_middleware2[0].kwargs.get("allow_origins") == ["https://dashboard.effero.io"]
    assert cors_middleware2[0].kwargs.get("allow_credentials") is True
