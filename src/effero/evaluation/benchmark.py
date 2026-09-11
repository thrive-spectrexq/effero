"""Effero Agentic Evaluation and Benchmarking Suite.

Provides formal scenario definitions, deterministic test execution, and comprehensive
metric reporting (accuracy, latencies, token consumption, cost USD, safety adherence)
to evaluate embodied agents across robotics, IoT, and desktop domains.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from typing import TYPE_CHECKING, Any

from effero.core.callbacks.telemetry import TelemetryCallback

if TYPE_CHECKING:
    from effero.core.agent import Agent

logger = logging.getLogger(__name__)


@dataclass
class EvaluationMetric:
    """Individual metric value captured during benchmark run."""

    name: str
    value: float
    unit: str
    target: float | None = None
    passed: bool = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ScenarioResult:
    """Result of running an individual evaluation scenario."""

    name: str
    category: str
    success: bool
    latency_seconds: float
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    cost_usd: float
    safety_violations: int
    metrics: dict[str, EvaluationMetric] = field(default_factory=dict)
    error: str | None = None
    transcript: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["metrics"] = {k: v.to_dict() for k, v in self.metrics.items()}
        return d


@dataclass
class BenchmarkReport:
    """Aggregated benchmark report across all executed scenarios."""

    suite_name: str
    total_scenarios: int
    passed_scenarios: int
    failed_scenarios: int
    success_rate: float
    total_latency_seconds: float
    average_latency_seconds: float
    total_tokens: int
    total_cost_usd: float
    total_safety_violations: int
    results: list[ScenarioResult] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "suite_name": self.suite_name,
            "total_scenarios": self.total_scenarios,
            "passed_scenarios": self.passed_scenarios,
            "failed_scenarios": self.failed_scenarios,
            "success_rate": round(self.success_rate, 4),
            "total_latency_seconds": round(self.total_latency_seconds, 3),
            "average_latency_seconds": round(self.average_latency_seconds, 3),
            "total_tokens": self.total_tokens,
            "total_cost_usd": round(self.total_cost_usd, 6),
            "total_safety_violations": self.total_safety_violations,
            "results": [r.to_dict() for r in self.results],
        }

    def summary(self) -> str:
        """Render a clean ASCII summary table of benchmark results."""
        lines = [
            f"=================== Benchmark Suite: {self.suite_name} ===================",
            f"Pass Rate: {self.passed_scenarios}/{self.total_scenarios} ({self.success_rate * 100:.1f}%)",
            f"Total Latency: {self.total_latency_seconds:.2f}s (Avg: {self.average_latency_seconds:.2f}s/task)",
            f"Total Tokens: {self.total_tokens} | Estimated Cost: ${self.total_cost_usd:.4f}",
            f"Safety Violations: {self.total_safety_violations}",
            "-------------------------------------------------------------------------",
            f"{'Scenario Name':<32} {'Status':<8} {'Time (s)':<10} {'Tokens':<8} {'Cost ($)':<10}",
            "-------------------------------------------------------------------------",
        ]
        for r in self.results:
            status = "PASS" if r.success else "FAIL"
            lines.append(
                f"{r.name:<32} {status:<8} {r.latency_seconds:<10.2f} {r.total_tokens:<8} ${r.cost_usd:<10.4f}"
            )
        lines.append("=========================================================================")
        return "\n".join(lines)


@dataclass
class BenchmarkScenario:
    """An executable evaluation scenario."""

    name: str
    category: str
    instruction: str
    validator: Callable[[Agent, str], bool | tuple[bool, str]]
    timeout_seconds: float = 30.0
    setup: Callable[[Agent], None] | None = None
    expected_skills: list[str] = field(default_factory=list)


class BenchmarkRunner:
    """Runs a collection of embodied AI benchmark scenarios and generates an executive report."""

    def __init__(self, suite_name: str = "Effero Embodied AI Benchmark") -> None:
        self.suite_name = suite_name
        self.scenarios: list[BenchmarkScenario] = []

    def add_scenario(self, scenario: BenchmarkScenario) -> None:
        self.scenarios.append(scenario)

    async def run(self, agent_factory: Callable[[], Agent]) -> BenchmarkReport:
        """Run all registered scenarios using a fresh agent instance for each run."""
        results: list[ScenarioResult] = []
        total_latency = 0.0
        total_tokens = 0
        total_cost = 0.0
        total_violations = 0
        passed = 0

        for sc in self.scenarios:
            logger.info(f"Running benchmark scenario: {sc.name} [{sc.category}]")
            agent = agent_factory()

            telemetry = TelemetryCallback(memory=agent.working_memory)
            agent.callbacks.add(telemetry)

            if sc.setup:
                sc.setup(agent)

            # In automated benchmarks, ensure approval handler does not block on interactive console
            from effero.safety.approval import AutoApprovalHandler, ConsoleApprovalHandler

            if isinstance(agent.approval_handler, ConsoleApprovalHandler):
                auto_approval = AutoApprovalHandler(approve_all=True)
                agent.approval_handler = auto_approval
                agent.planner.approval_handler = auto_approval

            t0 = time.perf_counter()
            err_msg: str | None = None
            is_success = False

            try:
                task = asyncio.create_task(agent.run(sc.instruction))
                response = await asyncio.wait_for(task, timeout=sc.timeout_seconds)
                val_res = sc.validator(agent, response)
                if isinstance(val_res, tuple):
                    is_success, err_msg = val_res[0], val_res[1] if not val_res[0] else None
                else:
                    is_success = bool(val_res)
                    err_msg = None if is_success else "Validation assertion returned False"
            except TimeoutError:
                is_success = False
                err_msg = f"Scenario exceeded timeout of {sc.timeout_seconds}s"
            except Exception as e:
                is_success = False
                err_msg = str(e)

            elapsed = time.perf_counter() - t0
            summary = telemetry.get_summary()

            # Check expected skill invocations
            metrics: dict[str, EvaluationMetric] = {}
            if sc.expected_skills:
                for expected_skill in sc.expected_skills:
                    count = summary["skill_counts"].get(expected_skill, 0)
                    metrics[f"invocations_{expected_skill}"] = EvaluationMetric(
                        name=f"invocations_{expected_skill}",
                        value=float(count),
                        unit="calls",
                        target=1.0,
                        passed=(count >= 1),
                    )
                    if count < 1 and is_success:
                        is_success = False
                        err_msg = f"Expected skill '{expected_skill}' was not called"

            violations = summary["safety_decisions"].get("denied", 0)

            if is_success:
                passed += 1

            total_latency += elapsed
            total_tokens += summary["total_tokens"]
            total_cost += summary["estimated_cost_usd"]
            total_violations += violations

            context = agent.working_memory.get_context()
            results.append(
                ScenarioResult(
                    name=sc.name,
                    category=sc.category,
                    success=is_success,
                    latency_seconds=round(elapsed, 3),
                    prompt_tokens=summary["total_prompt_tokens"],
                    completion_tokens=summary["total_completion_tokens"],
                    total_tokens=summary["total_tokens"],
                    cost_usd=summary["estimated_cost_usd"],
                    safety_violations=violations,
                    metrics=metrics,
                    error=err_msg,
                    transcript=context,
                )
            )

        total_scenarios = len(self.scenarios)
        success_rate = (passed / total_scenarios) if total_scenarios > 0 else 0.0
        avg_latency = (total_latency / total_scenarios) if total_scenarios > 0 else 0.0

        return BenchmarkReport(
            suite_name=self.suite_name,
            total_scenarios=total_scenarios,
            passed_scenarios=passed,
            failed_scenarios=total_scenarios - passed,
            success_rate=success_rate,
            total_latency_seconds=total_latency,
            average_latency_seconds=avg_latency,
            total_tokens=total_tokens,
            total_cost_usd=total_cost,
            total_safety_violations=total_violations,
            results=results,
        )
