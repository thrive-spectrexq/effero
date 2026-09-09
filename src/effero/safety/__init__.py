"""Runtime guardrail engine: policy-as-code checks that run independently
of the LLM, between the skill layer and the Device Abstraction Layer.

Evaluates declarative policies against live telemetry and device facts via
the high-performance out-of-process Rust safety kernel daemon (TCP 127.0.0.1:9400).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from effero.safety.approval import (
    ApprovalHandler,
    ApprovalRequest,
    ApprovalResponse,
    AutoApprovalHandler,
    CallbackApprovalHandler,
    ConsoleApprovalHandler,
    GraduatedApprovalHandler,
)
from effero.safety.client import SafetyClient
from effero.safety.daemon import SafetyDaemonManager


class PolicyDecision(StrEnum):
    ALLOW = "allow"
    REQUIRE_APPROVAL = "require_approval"
    DENY = "deny"


@dataclass
class GuardrailResult:
    decision: PolicyDecision
    reason: str


__all__ = [
    "PolicyDecision",
    "GuardrailResult",
    "SafetyClient",
    "SafetyDaemonManager",
    "ApprovalRequest",
    "ApprovalResponse",
    "ApprovalHandler",
    "ConsoleApprovalHandler",
    "AutoApprovalHandler",
    "CallbackApprovalHandler",
    "GraduatedApprovalHandler",
]
