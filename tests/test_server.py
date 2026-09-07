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
