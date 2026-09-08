"""Telemetry and audit log callback implementations for Effero."""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING, Any

from effero.core.callbacks.base import AgentCallback

if TYPE_CHECKING:
    from effero.core.memory.working import WorkingMemory

logger = logging.getLogger(__name__)


class TelemetryCallback(AgentCallback):
    """Monitors performance, latencies, and execution counters across the agent lifecycle."""

    def __init__(self, memory: WorkingMemory | None = None) -> None:
        self.memory = memory
        self.total_agent_runs: int = 0
        self.total_agent_errors: int = 0
        self.total_skill_invocations: int = 0
        self.skill_counts: dict[str, int] = {}
        self.safety_decisions: dict[str, int] = {"approved": 0, "denied": 0}
        self.recent_latencies: list[float] = []

    def on_agent_start(self, prompt: str) -> None:
        self.total_agent_runs += 1
        if self.memory:
            self.memory.record_metric("agent_runs", self.total_agent_runs)

    def on_agent_finish(self, response: str, elapsed_seconds: float) -> None:
        self.recent_latencies.append(elapsed_seconds)
        if len(self.recent_latencies) > 1000:
            self.recent_latencies.pop(0)
        if self.memory:
            self.memory.record_metric("agent_latency_seconds", elapsed_seconds)

    def on_agent_error(self, error: Exception) -> None:
        self.total_agent_errors += 1
        if self.memory:
            self.memory.record_metric("agent_errors", self.total_agent_errors)

    def on_skill_before_execute(self, skill_name: str, arguments: dict[str, Any]) -> None:
        self.total_skill_invocations += 1
        self.skill_counts[skill_name] = self.skill_counts.get(skill_name, 0) + 1
        if self.memory:
            self.memory.record_metric(f"skill_calls_{skill_name}", self.skill_counts[skill_name])

    def on_skill_after_execute(self, skill_name: str, result: Any, elapsed_seconds: float) -> None:
        if self.memory:
            self.memory.record_metric(f"skill_latency_{skill_name}", elapsed_seconds)

    def on_safety_check(
        self, skill_name: str, arguments: dict[str, Any], approved: bool, reason: str | None = None
    ) -> None:
        key = "approved" if approved else "denied"
        self.safety_decisions[key] += 1
        if self.memory:
            self.memory.record_metric(f"safety_{key}", self.safety_decisions[key])

    def get_summary(self) -> dict[str, Any]:
        """Return aggregated telemetry metrics."""
        avg_lat = sum(self.recent_latencies) / len(self.recent_latencies) if self.recent_latencies else 0.0
        return {
            "total_agent_runs": self.total_agent_runs,
            "total_agent_errors": self.total_agent_errors,
            "total_skill_invocations": self.total_skill_invocations,
            "skill_counts": dict(self.skill_counts),
            "safety_decisions": dict(self.safety_decisions),
            "average_agent_latency_s": round(avg_lat, 4),
        }


class AuditLogCallback(AgentCallback):
    """Captures an append-only chronological log of all agent operations for compliance."""

    def __init__(self, log_to_logger: bool = True) -> None:
        self.log_to_logger = log_to_logger
        self.audit_records: list[dict[str, Any]] = []

    def _record(self, event_type: str, data: dict[str, Any]) -> None:
        record = {
            "timestamp": time.time(),
            "event_type": event_type,
            **data,
        }
        self.audit_records.append(record)
        if self.log_to_logger:
            logger.info(f"[AUDIT] {event_type}: {data}")

    def on_agent_start(self, prompt: str) -> None:
        self._record("agent_start", {"prompt": prompt})

    def on_agent_finish(self, response: str, elapsed_seconds: float) -> None:
        self._record(
            "agent_finish",
            {"response_len": len(response), "elapsed_seconds": round(elapsed_seconds, 4)},
        )

    def on_agent_error(self, error: Exception) -> None:
        self._record("agent_error", {"error": str(error), "error_type": error.__class__.__name__})

    def on_plan_generated(self, plan: Any) -> None:
        self._record("plan_generated", {"plan": str(plan)})

    def on_skill_before_execute(self, skill_name: str, arguments: dict[str, Any]) -> None:
        self._record("skill_call", {"skill_name": skill_name, "arguments": arguments})

    def on_skill_after_execute(self, skill_name: str, result: Any, elapsed_seconds: float) -> None:
        self._record(
            "skill_result",
            {"skill_name": skill_name, "elapsed_seconds": round(elapsed_seconds, 4)},
        )

    def on_safety_check(
        self, skill_name: str, arguments: dict[str, Any], approved: bool, reason: str | None = None
    ) -> None:
        self._record(
            "safety_check",
            {
                "skill_name": skill_name,
                "approved": approved,
                "reason": reason,
            },
        )
