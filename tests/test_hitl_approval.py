"""Tests for Human-in-the-loop (HITL) approval system."""

from __future__ import annotations

import asyncio
import inspect

import pytest

from effero.core.memory.working import WorkingMemory
from effero.core.planner.planner import Planner
from effero.core.router import ScriptedBackend
from effero.core.router.base import LLMResponse, ToolCall
from effero.safety.approval import (
    ApprovalRequest,
    AutoApprovalHandler,
    CallbackApprovalHandler,
    GraduatedApprovalHandler,
)
from effero.sdk.skill import SafetyClass, SkillRegistry, SkillSpec


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
    router = ScriptedBackend(
        [
            LLMResponse(
                content=None,
                tool_calls=[ToolCall(id="call-1", name="database.delete", arguments={"table": "users"})],
            ),
            LLMResponse(content="Table deleted successfully."),
        ]
    )
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
    router = ScriptedBackend(
        [
            LLMResponse(
                content=None,
                tool_calls=[ToolCall(id="call-1", name="database.delete", arguments={"table": "prod"})],
            ),
            LLMResponse(content="I could not delete the table due to operator refusal."),
        ]
    )
    planner = Planner(
        router=router,
        memory=WorkingMemory(),
        skills=approval_skill_registry,
        approval_handler=handler,
    )

    result = await planner.run("Delete prod table")
    assert result is not None
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


@pytest.mark.asyncio
async def test_graduated_approval_handler() -> None:
    """Verify GraduatedApprovalHandler auto-approves read_only/act_autonomous and delegates act_with_approval."""
    delegate = AutoApprovalHandler(approve_all=False)  # Delegate rejects
    handler = GraduatedApprovalHandler(delegate=delegate)

    # 1. READ_ONLY -> auto-approved
    req_ro = ApprovalRequest(skill_name="iot.sensors.read", safety_class="read_only")
    res_ro = await handler.request_approval(req_ro)
    assert res_ro.approved is True
    assert res_ro.responder == "graduated_auto"

    # 2. ACT_AUTONOMOUS -> auto-approved
    req_auto = ApprovalRequest(skill_name="robotics.arm.home", safety_class="act_autonomous")
    res_auto = await handler.request_approval(req_auto)
    assert res_auto.approved is True
    assert res_auto.responder == "graduated_auto"

    # 3. ACT_RESTRICTED -> auto-denied
    req_rest = ApprovalRequest(skill_name="untrusted.skill", safety_class="act_restricted")
    res_rest = await handler.request_approval(req_rest)
    assert res_rest.approved is False
    assert res_rest.responder == "graduated_auto"

    # 4. ACT_WITH_APPROVAL -> delegated to delegate handler (which rejects)
    req_with_app = ApprovalRequest(skill_name="robotics.arm.move_to", safety_class="act_with_approval")
    res_with_app = await handler.request_approval(req_with_app)
    assert res_with_app.approved is False
    assert res_with_app.responder == delegate.responder_name


@pytest.mark.asyncio
async def test_auto_approval_handler_graduated_mode() -> None:
    """Verify AutoApprovalHandler graduated mode auto-approves safe classes and gates approval-required actions."""
    handler = AutoApprovalHandler(graduated=True, approve_approval_gated=False)

    res_ro = await handler.request_approval(ApprovalRequest(skill_name="read", safety_class="read_only"))
    assert res_ro.approved is True

    res_auto = await handler.request_approval(ApprovalRequest(skill_name="auto", safety_class="act_autonomous"))
    assert res_auto.approved is True

    res_rest = await handler.request_approval(ApprovalRequest(skill_name="rest", safety_class="act_restricted"))
    assert res_rest.approved is False

    res_gated = await handler.request_approval(ApprovalRequest(skill_name="gated", safety_class="act_with_approval"))
    assert res_gated.approved is False

    # Now with approve_approval_gated=True
    handler_permissive = AutoApprovalHandler(graduated=True, approve_approval_gated=True)
    res_gated_ok = await handler_permissive.request_approval(
        ApprovalRequest(skill_name="gated", safety_class="act_with_approval")
    )
    assert res_gated_ok.approved is True
