"""Tests for FastAPI server WebSocket connection lifecycle, approvals, and memory endpoints using real Agent."""

from __future__ import annotations

from starlette.testclient import TestClient

from effero.core.agent import Agent
from effero.interfaces.server import create_app
from effero.safety.approval import ApprovalRequest, CallbackApprovalHandler


def test_websocket_events_connect_and_ping() -> None:
    agent = Agent()
    app = create_app(agent=agent)

    with TestClient(app) as client:
        with client.websocket_connect("/ws/events") as websocket:
            websocket.send_text("ping")


def test_approvals_api_endpoints() -> None:
    agent = Agent()
    app = create_app(agent=agent)

    with TestClient(app) as client:
        # Initially empty
        resp = client.get("/v1/approvals")
        assert resp.status_code == 200
        assert resp.json() == []

        # Trigger an approval request directly on the agent's configured callback handler
        req = ApprovalRequest(
            id="req-test-123",
            skill_name="robotics.arm.move",
            arguments={"x": 0.5, "y": 0.2},
            reason="Safety bounding check requires operator confirmation",
            safety_class="act_with_approval",
        )
        assert isinstance(agent.approval_handler, CallbackApprovalHandler)
        agent.approval_handler.callback(req)

        # Verify listed in GET /v1/approvals
        list_resp = client.get("/v1/approvals")
        assert list_resp.status_code == 200
        approvals = list_resp.json()
        assert len(approvals) == 1
        assert approvals[0]["id"] == "req-test-123"
        assert approvals[0]["skill_name"] == "robotics.arm.move"

        # Resolve approval via POST /v1/approvals/{request_id}
        dec_resp = client.post(
            "/v1/approvals/req-test-123",
            json={"approved": True, "comment": "Authorized by operator"},
        )
        assert dec_resp.status_code == 200
        assert dec_resp.json()["approved"] is True

        # Now approvals list should be cleared
        final_list = client.get("/v1/approvals")
        assert len(final_list.json()) == 0


def test_working_and_episodic_memory_endpoints() -> None:
    agent = Agent()
    app = create_app(agent=agent)

    with TestClient(app) as client:
        agent.working_memory.add_message("user", "Hello world memory test")
        resp_working = client.get("/v1/memory/working")
        assert resp_working.status_code == 200
        messages = resp_working.json()["messages"]
        assert any(m.get("content") == "Hello world memory test" for m in messages)

        agent.episodic_memory.record("event", {"action": "grasp", "success": True})
        resp_episodic = client.get("/v1/memory/episodic?limit=10")
        assert resp_episodic.status_code == 200
        history = resp_episodic.json()["history"]
        assert len(history) >= 1
        assert history[-1]["data"]["action"] == "grasp"


def test_websocket_authentication() -> None:
    from starlette.websockets import WebSocketDisconnect

    agent = Agent()
    agent.config.server.api_key = "secure-ws-key"
    app = create_app(agent=agent)

    with TestClient(app) as client:
        # Connect without auth should fail / disconnect
        try:
            with client.websocket_connect("/ws/events") as ws:
                ws.send_text("ping")
                raise AssertionError("Should have been rejected")
        except WebSocketDisconnect:
            pass

        # Connect with valid query param ?api_key=secure-ws-key should succeed
        with client.websocket_connect("/ws/events?api_key=secure-ws-key") as ws:
            ws.send_text("ping")

