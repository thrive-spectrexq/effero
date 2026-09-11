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
        self.total_prompt_tokens: int = 0
        self.total_completion_tokens: int = 0
        self.total_tokens: int = 0
        self.estimated_cost_usd: float = 0.0

    @staticmethod
    def _estimate_cost(backend: str, model: str, prompt_tokens: int, completion_tokens: int) -> float:
        """Estimate USD cost based on model/backend and token count."""
        b_lower = backend.lower()
        m_lower = model.lower()
        if b_lower in ("ollama", "litert", "local") or "local" in m_lower:
            return 0.0

        rates: dict[str, tuple[float, float]] = {
            "gpt-4o-mini": (0.15, 0.60),
            "gpt-4o": (2.50, 10.00),
            "gpt-4.5": (75.00, 150.00),
            "o1-mini": (1.10, 4.40),
            "o3-mini": (1.10, 4.40),
            "claude-3-7-sonnet": (3.00, 15.00),
            "claude-3-5-sonnet": (3.00, 15.00),
            "claude-3-haiku": (0.25, 1.25),
            "gemini-2.0-flash": (0.10, 0.40),
            "gemini-1.5-pro": (3.50, 10.50),
            "gemini-1.5-flash": (0.075, 0.30),
        }
        for key, (p_rate, c_rate) in rates.items():
            if key in m_lower:
                return (prompt_tokens * p_rate + completion_tokens * c_rate) / 1_000_000.0

        if b_lower in ("openai", "anthropic", "google"):
            return (prompt_tokens * 1.50 + completion_tokens * 6.00) / 1_000_000.0

        return 0.0

    def on_llm_response(self, response: Any) -> None:
        usage = getattr(response, "usage", {}) or {}
        p_tokens = int(usage.get("prompt_tokens") or usage.get("input_tokens") or 0)
        c_tokens = int(usage.get("completion_tokens") or usage.get("output_tokens") or 0)
        t_tokens = int(usage.get("total_tokens") or (p_tokens + c_tokens))

        self.total_prompt_tokens += p_tokens
        self.total_completion_tokens += c_tokens
        self.total_tokens += t_tokens

        backend = str(getattr(response, "backend", "") or "")
        model = str(getattr(response, "model", "") or "")
        cost = self._estimate_cost(backend, model, p_tokens, c_tokens)
        self.estimated_cost_usd += cost

        if self.memory:
            self.memory.record_metric("tokens_prompt_total", self.total_prompt_tokens)
            self.memory.record_metric("tokens_completion_total", self.total_completion_tokens)
            self.memory.record_metric("tokens_total", self.total_tokens)
            self.memory.record_metric("estimated_cost_usd", self.estimated_cost_usd)

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
            "total_prompt_tokens": self.total_prompt_tokens,
            "total_completion_tokens": self.total_completion_tokens,
            "total_tokens": self.total_tokens,
            "estimated_cost_usd": round(self.estimated_cost_usd, 6),
        }

    def export_prometheus(self) -> str:
        """Export collected metrics in standard Prometheus text format."""
        lines = [
            "# HELP effero_agent_runs_total Total number of agent runs started.",
            "# TYPE effero_agent_runs_total counter",
            f"effero_agent_runs_total {self.total_agent_runs}",
            "# HELP effero_agent_errors_total Total number of unhandled agent errors.",
            "# TYPE effero_agent_errors_total counter",
            f"effero_agent_errors_total {self.total_agent_errors}",
            "# HELP effero_skill_invocations_total Total number of skill executions.",
            "# TYPE effero_skill_invocations_total counter",
            f"effero_skill_invocations_total {self.total_skill_invocations}",
        ]
        for skill_name, count in sorted(self.skill_counts.items()):
            lines.append(f'effero_skill_calls_total{{skill="{skill_name}"}} {count}')

        lines.extend(
            [
                "# HELP effero_safety_decisions_total Total safety check decisions by outcome.",
                "# TYPE effero_safety_decisions_total counter",
                f'effero_safety_decisions_total{{decision="approved"}} {self.safety_decisions.get("approved", 0)}',
                f'effero_safety_decisions_total{{decision="denied"}} {self.safety_decisions.get("denied", 0)}',
                "# HELP effero_tokens_total Total tokens processed across LLM interactions.",
                "# TYPE effero_tokens_total counter",
                f'effero_tokens_total{{type="prompt"}} {self.total_prompt_tokens}',
                f'effero_tokens_total{{type="completion"}} {self.total_completion_tokens}',
                f'effero_tokens_total{{type="total"}} {self.total_tokens}',
                "# HELP effero_cost_usd_total Estimated cost in USD.",
                "# TYPE effero_cost_usd_total counter",
                f"effero_cost_usd_total {self.estimated_cost_usd:.6f}",
            ]
        )
        return "\n".join(lines) + "\n"


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

    def on_llm_response(self, response: Any) -> None:
        usage = getattr(response, "usage", {}) or {}
        model = str(getattr(response, "model", "") or "")
        backend = str(getattr(response, "backend", "") or "")
        self._record("llm_response", {"backend": backend, "model": model, "usage": usage})
