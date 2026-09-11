"""Comprehensive automated unit tests for Effero Evaluation and Benchmark Suite."""

from __future__ import annotations

import pytest

from effero.config import EfferoConfig
from effero.core.agent import Agent
from effero.core.router.base import LLMResponse, ToolCall
from effero.core.router.scripted_backend import ScriptedBackend
from effero.evaluation import (
    BenchmarkReport,
    BenchmarkRunner,
    BenchmarkScenario,
    create_office_navigation_scenario,
    create_smart_climate_control_scenario,
    create_warehouse_pick_place_scenario,
)


@pytest.mark.asyncio
async def test_benchmark_runner_custom_scenario() -> None:
    """Verify BenchmarkRunner executes scenarios, aggregates metrics, and formats reports."""
    scenario = BenchmarkScenario(
        name="custom_math_eval",
        category="reasoning",
        instruction="Calculate sum of 10 and 20",
        validator=lambda agent, resp: "30" in resp,
        expected_skills=[],
        timeout_seconds=5.0,
    )

    runner = BenchmarkRunner(suite_name="Unit Eval")
    runner.add_scenario(scenario)

    def agent_factory() -> Agent:
        config = EfferoConfig()
        config.safety.enabled = False
        backend = ScriptedBackend(
            responses=[
                LLMResponse(
                    content="The calculated sum is 30.",
                    usage={"prompt_tokens": 15, "completion_tokens": 8, "total_tokens": 23},
                    model="gpt-4o-mini",
                    backend="openai",
                )
            ]
        )
        agent = Agent(config=config)
        agent.planner.router = backend
        return agent

    report: BenchmarkReport = await runner.run(agent_factory)
    assert report.total_scenarios == 1
    assert report.passed_scenarios == 1
    assert report.failed_scenarios == 0
    assert report.success_rate == 1.0
    assert report.total_tokens == 23
    assert report.total_cost_usd > 0.0

    summary_text = report.summary()
    assert "Benchmark Suite: Unit Eval" in summary_text
    assert "PASS" in summary_text
    assert "custom_math_eval" in summary_text


@pytest.mark.asyncio
async def test_warehouse_pick_place_scenario_execution() -> None:
    """Verify warehouse pick and place scenario passes when pick_place skill executes."""
    scenario = create_warehouse_pick_place_scenario()
    runner = BenchmarkRunner(suite_name="Warehouse Manipulation Benchmark")
    runner.add_scenario(scenario)

    def agent_factory() -> Agent:
        config = EfferoConfig()
        config.safety.enabled = False
        backend = ScriptedBackend(
            responses=[
                LLMResponse(
                    content=None,
                    tool_calls=[
                        ToolCall(
                            id="call-pick-1",
                            name="robotics.arm.pick_place",
                            arguments={
                                "pick_x": 0.25,
                                "pick_y": 0.15,
                                "pick_z": 0.05,
                                "place_x": 0.10,
                                "place_y": 0.28,
                                "place_z": 0.05,
                            },
                        )
                    ],
                    usage={"prompt_tokens": 40, "completion_tokens": 15, "total_tokens": 55},
                    model="gpt-4o-mini",
                    backend="openai",
                ),
                LLMResponse(
                    content="Pallet successfully transferred from intake to shipping bin.",
                    usage={"prompt_tokens": 60, "completion_tokens": 12, "total_tokens": 72},
                    model="gpt-4o-mini",
                    backend="openai",
                ),
            ]
        )
        agent = Agent(config=config)
        agent.planner.router = backend
        return agent

    report = await runner.run(agent_factory)
    assert report.total_scenarios == 1
    assert report.passed_scenarios == 1
    assert report.results[0].category == "robotics_manipulation"
    assert report.results[0].metrics["invocations_robotics.arm.pick_place"].passed is True


@pytest.mark.asyncio
async def test_office_navigation_scenario_execution() -> None:
    """Verify office navigation benchmark scenario updates mobile base coordinates."""
    scenario = create_office_navigation_scenario()
    runner = BenchmarkRunner(suite_name="Mobile Base Navigation Benchmark")
    runner.add_scenario(scenario)

    def agent_factory() -> Agent:
        config = EfferoConfig()
        config.safety.enabled = False
        backend = ScriptedBackend(
            responses=[
                LLMResponse(
                    content=None,
                    tool_calls=[
                        ToolCall(
                            id="call-nav-1",
                            name="robotics.navigate.go_to",
                            arguments={"waypoint": "office"},
                        )
                    ],
                    usage={"prompt_tokens": 30, "completion_tokens": 10, "total_tokens": 40},
                    model="gemini-2.0-flash",
                    backend="google",
                ),
                LLMResponse(
                    content="Robot has arrived at office waypoint.",
                    usage={"prompt_tokens": 45, "completion_tokens": 8, "total_tokens": 53},
                    model="gemini-2.0-flash",
                    backend="google",
                ),
            ]
        )
        agent = Agent(config=config)
        agent.planner.router = backend
        return agent

    report = await runner.run(agent_factory)
    assert report.total_scenarios == 1
    assert report.passed_scenarios == 1
    assert report.results[0].category == "mobile_robotics"
    assert report.results[0].metrics["invocations_robotics.navigate.go_to"].passed is True


@pytest.mark.asyncio
async def test_smart_climate_scenario_execution() -> None:
    """Verify climate regulation scenario validates telemetry-based thermostat adjustments."""
    scenario = create_smart_climate_control_scenario()
    runner = BenchmarkRunner(suite_name="Smart IoT Benchmark")
    runner.add_scenario(scenario)

    def agent_factory() -> Agent:
        config = EfferoConfig()
        config.safety.enabled = False
        backend = ScriptedBackend(
            responses=[
                LLMResponse(
                    content=None,
                    tool_calls=[
                        ToolCall(
                            id="call-iot-1",
                            name="iot.thermostat.set_temperature",
                            arguments={"device_id": "living_room", "temperature": 21.5},
                        )
                    ],
                    usage={"prompt_tokens": 35, "completion_tokens": 12, "total_tokens": 47},
                    model="claude-3-5-sonnet",
                    backend="anthropic",
                ),
                LLMResponse(
                    content="Living room temperature adjusted to 21.5C.",
                    usage={"prompt_tokens": 50, "completion_tokens": 10, "total_tokens": 60},
                    model="claude-3-5-sonnet",
                    backend="anthropic",
                ),
            ]
        )
        agent = Agent(config=config)
        agent.planner.router = backend
        return agent

    report = await runner.run(agent_factory)
    assert report.total_scenarios == 1
    assert report.passed_scenarios == 1
    assert report.results[0].category == "iot_building_automation"
