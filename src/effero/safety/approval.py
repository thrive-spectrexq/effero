"""Human-in-the-loop (HITL) safety approval system for Effero."""

from __future__ import annotations

import asyncio
import logging
import uuid
from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class ApprovalRequest:
    """A request for human approval before executing a sensitive action."""

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    skill_name: str = ""
    arguments: dict[str, Any] = field(default_factory=dict)
    reason: str = "Skill requires human authorization"
    safety_class: str = "act_with_approval"
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())


@dataclass
class ApprovalResponse:
    """The human decision for an approval request."""

    request_id: str
    approved: bool
    responder: str = "human"
    comment: str | None = None
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())


class ApprovalHandler(ABC):
    """Abstract interface for receiving and resolving HITL approval requests."""

    @abstractmethod
    async def request_approval(self, request: ApprovalRequest) -> ApprovalResponse:
        """Present the approval request to a human operator and await decision."""
        ...


class AutoApprovalHandler(ApprovalHandler):
    """Approval handler that resolves requests automatically.

    Supports:
    - All-or-nothing mode (default: `approve_all=True` or `approve_all=False`)
    - Graduated per-SafetyClass mode (`graduated=True`):
      - READ_ONLY / ACT_AUTONOMOUS: auto-approved (True)
      - ACT_RESTRICTED: auto-denied (False, simulation only)
      - ACT_WITH_APPROVAL: evaluates according to `approve_approval_gated` (default False)
    """

    def __init__(
        self,
        approve_all: bool = True,
        graduated: bool = False,
        approve_approval_gated: bool = False,
        responder_name: str = "auto",
    ) -> None:
        self.approve_all = approve_all
        self.graduated = graduated
        self.approve_approval_gated = approve_approval_gated
        self.responder_name = responder_name
        self.history: list[tuple[ApprovalRequest, ApprovalResponse]] = []

    async def request_approval(self, request: ApprovalRequest) -> ApprovalResponse:
        norm_class = (request.safety_class or "act_with_approval").lower()
        if self.graduated:
            if norm_class in ("read_only", "act_autonomous"):
                approved = True
                comment = f"Auto-approved graduated {norm_class}"
            elif norm_class == "act_restricted":
                approved = False
                comment = "Denied act_restricted in graduated auto mode"
            else:
                approved = self.approve_approval_gated
                comment = f"Graduated auto-decision for {norm_class}: {approved}"
        else:
            approved = self.approve_all
            comment = "Automatic decision by policy/simulation"

        decision = ApprovalResponse(
            request_id=request.id,
            approved=approved,
            responder=self.responder_name,
            comment=comment,
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
        except TimeoutError:
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
        except TimeoutError:
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


class GraduatedApprovalHandler(ApprovalHandler):
    """Graduated approval handler: auto-approves safe classes, gates ACT_WITH_APPROVAL via delegate.

    - READ_ONLY: auto-approved
    - ACT_AUTONOMOUS: auto-approved
    - ACT_WITH_APPROVAL: delegates to secondary handler (e.g. Console or Callback)
    - ACT_RESTRICTED: denied by default (simulation/sandbox only)
    """

    def __init__(self, delegate: ApprovalHandler | None = None):
        self.delegate = delegate or ConsoleApprovalHandler()

    async def request_approval(self, request: ApprovalRequest) -> ApprovalResponse:
        norm_class = request.safety_class.lower()

        if norm_class in ("read_only", "act_autonomous"):
            return ApprovalResponse(
                request_id=request.id,
                approved=True,
                responder="graduated_auto",
                comment=f"Auto-approved {norm_class} action",
            )
        elif norm_class == "act_restricted":
            return ApprovalResponse(
                request_id=request.id,
                approved=False,
                responder="graduated_auto",
                comment="Denied act_restricted action (simulation only)",
            )
        else:
            return await self.delegate.request_approval(request)
