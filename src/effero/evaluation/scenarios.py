"""Standard pre-built benchmark evaluation scenarios for Effero.

Covers:
- Robotics Manipulation: Pick and place with Cartesian clearance and collision avoidance
- Mobile Navigation: Waypoint traversal and obstacle avoidance
- Smart Building / IoT: Dynamic environmental control based on telemetry
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from effero.evaluation.benchmark import BenchmarkScenario

if TYPE_CHECKING:
    from effero.core.agent import Agent


def create_warehouse_pick_place_scenario() -> BenchmarkScenario:
    """Benchmark: Autonomous pick-and-place operation from warehouse intake to packing station."""

    def validator(agent: Agent, response: str) -> tuple[bool, str]:
        from effero.skills.robotics.arm import _arm_controller

        # Verify gripper cycle and arm end position
        if _arm_controller.current_joints is None:
            return False, "Arm controller has no active joint state"

        # Check that pick_place skill was called in working memory context
        tool_results = [m for m in agent.working_memory.get_context() if m.get("role") == "tool"]
        success_calls = [
            m for m in tool_results if "status" in str(m.get("content")) and "pick_place" in str(m.get("content"))
        ]
        if not success_calls:
            return False, "pick_place action did not record success status in tool results"

        return True, "Warehouse pick and place executed successfully"

    return BenchmarkScenario(
        name="warehouse_pallet_pick_place",
        category="robotics_manipulation",
        instruction=(
            "Pick the item at intake (x=0.25, y=0.15, z=0.05) and place it at shipping bin (x=0.10, y=0.28, z=0.05)."
        ),
        validator=validator,
        expected_skills=["robotics.arm.pick_place"],
        timeout_seconds=15.0,
    )


def create_office_navigation_scenario() -> BenchmarkScenario:
    """Benchmark: Mobile base navigation to office waypoint with obstacle avoidance."""

    def validator(agent: Agent, response: str) -> tuple[bool, str]:
        from effero.skills.robotics.navigate import _nav_controller

        # Target office waypoint: (-1.5, 3.0)
        dist = ((_nav_controller.pose.x - (-1.5)) ** 2 + (_nav_controller.pose.y - 3.0) ** 2) ** 0.5
        if dist > 0.5:
            return False, f"Robot did not arrive at office target (distance: {dist:.2f}m)"

        return True, f"Office navigation completed (remaining error: {dist:.2f}m)"

    return BenchmarkScenario(
        name="office_waypoint_transit",
        category="mobile_robotics",
        instruction="Navigate the mobile robot to the office waypoint.",
        validator=validator,
        expected_skills=["robotics.navigate.go_to"],
        timeout_seconds=15.0,
    )


def create_smart_climate_control_scenario() -> BenchmarkScenario:
    """Benchmark: Autonomous smart home heating regulation upon occupancy detection."""

    def setup(agent: Agent) -> None:
        agent.working_memory.record_metric("temperature_living_room", 18.2)
        agent.working_memory.record_metric("occupancy_living_room", 1.0)

    def validator(agent: Agent, response: str) -> tuple[bool, str]:
        tool_results = [m for m in agent.working_memory.get_context() if m.get("role") == "tool"]
        if not tool_results:
            return False, "No IoT skills were invoked to regulate climate"
        return True, "Climate regulation skill executed"

    return BenchmarkScenario(
        name="smart_climate_regulation",
        category="iot_building_automation",
        instruction="Living room temperature is 18.2C and occupied. Adjust target temperature to comfortable 21.5C.",
        setup=setup,
        validator=validator,
        expected_skills=["iot.thermostat.set_temperature"],
        timeout_seconds=15.0,
    )
