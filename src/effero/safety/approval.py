"""Human-in-the-loop (HITL) safety approval system for Effero."""
from __future__ import annotations

import asyncio
import logging
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable

logger = logging.getLogger(__name__)


@dataclass
class ApprovalRequest:
    """A request for human approval before executing a sensitive action."""

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    skill_name: str = ""
    arguments: dict[str, Any] = field(default_factory=dict)
    reason: str = "Skill requires human authorization"
    safety_class: str = "act_with_approval"
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


@dataclass
class ApprovalResponse:
    """The human decision for an approval request."""

    request_id: str
    approved: bool
    responder: str = "human"
    comment: str | None = None
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


class ApprovalHandler(ABC):
    """Abstract interface for receiving and resolving HITL approval requests."""

    @abstractmethod
    async def request_approval(self, request: ApprovalRequest) -> ApprovalResponse:
        """Present the approval request to a human operator and await decision."""
        ...


class AutoApprovalHandler(ApprovalHandler):
    """Approval handler that always approves or rejects (used for testing or simulations)."""

    def __init__(self, approve_all: bool = True, responder_name: str = "auto"):
        self.approve_all = approve_all
        self.responder_name = responder_name
        self.history: list[tuple[ApprovalRequest, ApprovalResponse]] = []

    async def request_approval(self, request: ApprovalRequest) -> ApprovalResponse:
        decision = ApprovalResponse(
            request_id=request.id,
            approved=self.approve_all,
            responder=self.responder_name,
            comment="Automatic decision by policy/simulation",
        )
        self.history.append((request, decision))
        return decision


class ConsoleApprovalHandler(ApprovalHandler):
    """Interactive CLI terminal approval prompt."""

    def __init__(self, timeout_seconds: float = 60.0):
        self.timeout_seconds = timeout_seconds

    async def request_approval(self, request: ApprovalRequest) -> ApprovalResponse:
        print("\n" + "=" * 60)
        print("🚨 EFFERO SAFETY KERNEL: APPROVAL REQUIRED")
        print("=" * 60)
        print(f"  Request ID:   {request.id}")
        print(f"  Skill:        {request.skill_name}")
        print(f"  Safety Class: {request.safety_class}")
        print(f"  Reason:       {request.reason}")
        print(f"  Arguments:    {request.arguments}")
        print("=" * 60)

        loop = asyncio.get_running_loop()
        try:
            # Prompt user without blocking async event loop
            user_input = await asyncio.wait_for(
                loop.run_in_executor(None, input, "Authorize this action? [y/N]: "),
                timeout=self.timeout_seconds,
            )
            approved = user_input.strip().lower() in ("y", "yes")
        except asyncio.TimeoutError:
            print("\n[Timeout waiting for authorization: Denied by default]")
            approved = False
        except (KeyboardInterrupt, EOFError):
            approved = False

        return ApprovalResponse(
            request_id=request.id,
            approved=approved,
            responder="console_operator",
            comment="Approved via console" if approved else "Denied via console",
        )


class CallbackApprovalHandler(ApprovalHandler):
    """Approval handler that dispatches to an async callback (e.g. Web UI, WebSocket, Telegram)."""

    def __init__(
        self,
        callback: Callable[[ApprovalRequest], Any],
        timeout_seconds: float = 120.0,
    ):
        self.callback = callback
        self.timeout_seconds = timeout_seconds
        self._pending: dict[str, asyncio.Future[ApprovalResponse]] = {}

    async def request_approval(self, request: ApprovalRequest) -> ApprovalResponse:
        future = asyncio.get_running_loop().create_future()
        self._pending[request.id] = future

        try:
            result = self.callback(request)
            if hasattr(result, "__await__"):
                asyncio.create_task(result)

            return await asyncio.wait_for(future, timeout=self.timeout_seconds)
        except asyncio.TimeoutError:
            logger.warning(f"Approval request {request.id} timed out; defaulting to deny.")
            return ApprovalResponse(
                request_id=request.id,
                approved=False,
                responder="system_timeout",
                comment="Approval timed out",
            )
        finally:
            self._pending.pop(request.id, None)

    def resolve(self, request_id: str, approved: bool, comment: str | None = None) -> bool:
        """Resolve a pending approval request externally."""
        if request_id in self._pending and not self._pending[request_id].done():
            self._pending[request_id].set_result(
                ApprovalResponse(
                    request_id=request_id,
                    approved=approved,
                    responder="remote_operator",
                    comment=comment,
                )
            )
            return True
        return False
