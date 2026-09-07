"""Tests for Human-in-the-loop (HITL) approval system."""
from __future__ import annotations

import asyncio
import inspect
import functools
import pytest

from effero.core.memory.working import WorkingMemory
from effero.core.planner.planner import Planner
from effero.core.router.base import LLMRequest, LLMResponse, ToolCall
from effero.safety.approval import (
    ApprovalRequest,
    ApprovalResponse,
    AutoApprovalHandler,
    CallbackApprovalHandler,
)
from effero.sdk.skill import SafetyClass, SkillRegistry, SkillSpec


class MockRouter:
    def __init__(self, responses: list[LLMResponse]):
        self.responses = list(responses)
        self.idx = 0

    async def complete(self, request: LLMRequest) -> LLMResponse:
        if self.idx < len(self.responses):
            resp = self.responses[self.idx]
            self.idx += 1
            return resp
        return LLMResponse(content="Done")


@pytest.fixture
def approval_skill_registry():
    reg = SkillRegistry()

    def delete_db_fn(table: str) -> dict:
        return {"status": "deleted", "table": table}

    spec = SkillSpec(
        name="database.delete",
        description="Drop a table",
        safety_class=SafetyClass.ACT_WITH_APPROVAL,
        func=delete_db_fn,
        signature=inspect.signature(delete_db_fn),
    )
    reg.register(spec)
    return reg


@pytest.mark.asyncio
async def test_auto_approval_accepts(approval_skill_registry) -> None:
    handler = AutoApprovalHandler(approve_all=True)
    router = MockRouter([
        LLMResponse(
            content=None,
            tool_calls=[ToolCall(id="call-1", name="database.delete", arguments={"table": "users"})],
        ),
        LLMResponse(content="Table deleted successfully."),
    ])
    planner = Planner(
        router=router,
        memory=WorkingMemory(),
        skills=approval_skill_registry,
        approval_handler=handler,
    )

    result = await planner.run("Delete users table")
    assert "deleted successfully" in result
    assert len(handler.history) == 1
    req, res = handler.history[0]
    assert req.skill_name == "database.delete"
    assert res.approved is True


@pytest.mark.asyncio
async def test_auto_approval_rejects_and_prevents_execution(approval_skill_registry) -> None:
    handler = AutoApprovalHandler(approve_all=False)
    router = MockRouter([
        LLMResponse(
            content=None,
            tool_calls=[ToolCall(id="call-1", name="database.delete", arguments={"table": "prod"})],
        ),
        LLMResponse(content="I could not delete the table due to operator refusal."),
    ])
    planner = Planner(
        router=router,
        memory=WorkingMemory(),
        skills=approval_skill_registry,
        approval_handler=handler,
    )

    result = await planner.run("Delete prod table")
    assert len(handler.history) == 1
    req, res = handler.history[0]
    assert res.approved is False
    # Verify the error was injected into working memory for the LLM to observe
    tool_msgs = [m for m in planner.memory.get_context() if m.get("role") == "tool"]
    assert len(tool_msgs) == 1
    assert "Action unauthorized by human operator" in str(tool_msgs[0].get("content"))


@pytest.mark.asyncio
async def test_callback_approval_handler() -> None:
    received_requests: list[ApprovalRequest] = []

    def on_request(req: ApprovalRequest):
        received_requests.append(req)
        # Asynchronously resolve in background after a tiny delay
        asyncio.create_task(_resolve_after_delay(handler, req.id, approved=True))

    async def _resolve_after_delay(h: CallbackApprovalHandler, rid: str, approved: bool):
        await asyncio.sleep(0.01)
        h.resolve(rid, approved, comment="Operator granted access")

    handler = CallbackApprovalHandler(callback=on_request)
    req = ApprovalRequest(skill_name="robotics.arm.move", arguments={"x": 10})
    res = await handler.request_approval(req)

    assert len(received_requests) == 1
    assert res.approved is True
    assert res.comment == "Operator granted access"
