"""Runtime guardrail engine: policy-as-code checks that run independently
of the LLM, between the skill layer and the Device Abstraction Layer.

See safety/policies/example.yaml for the intended policy shape and the
"Safety & Governance" section of the top-level README for the design
rationale. The verification/grounding logic itself is not implemented in
this scaffold -- see ROADMAP.md in the repo root.
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
]
