"""Effero Agentic Evaluation and Benchmarking Suite.

Provides standard evaluation scenarios and benchmark suites for embodied AI:
- Scenario definitions (goals, initial states, validation assertions)
- Benchmark runners with metric capture (success rate, latency, token usage, cost USD, safety violations)
"""

from __future__ import annotations

from effero.evaluation.benchmark import (
    BenchmarkReport,
    BenchmarkRunner,
    BenchmarkScenario,
    EvaluationMetric,
    ScenarioResult,
)
from effero.evaluation.scenarios import (
    create_office_navigation_scenario,
    create_smart_climate_control_scenario,
    create_warehouse_pick_place_scenario,
)

__all__ = [
    "EvaluationMetric",
    "ScenarioResult",
    "BenchmarkScenario",
    "BenchmarkReport",
    "BenchmarkRunner",
    "create_warehouse_pick_place_scenario",
    "create_office_navigation_scenario",
    "create_smart_climate_control_scenario",
]
