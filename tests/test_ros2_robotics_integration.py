"""Tests for ROS 2 CDR Twist wire serialization and live robotics skill integration."""

from __future__ import annotations

import asyncio

import pytest

from effero.adapters.ros2.bridge import (
    ROS2Bridge,
    ROS2CDRSerializer,
    Twist,
    Vector3,
)
from effero.config import EfferoConfig, RoboticsConfig, ROS2Config
from effero.core.agent import Agent
from effero.skills.robotics.arm import ArmController, JointConfiguration
from effero.skills.robotics.navigate import NavigationController


def test_twist_cdr_roundtrip() -> None:
    """Verify OMG CDR serialization and deserialization of geometry_msgs/Twist."""
    original = Twist(
        linear=Vector3(x=0.45, y=-0.12, z=0.0),
        angular=Vector3(x=0.0, y=0.0, z=0.85),
    )
    cdr_data = ROS2CDRSerializer.serialize_twist(original)
    assert len(cdr_data) >= 48 + 4  # CDR header + 6 * 8-byte float64s

    decoded = ROS2CDRSerializer.deserialize_twist(cdr_data)
    assert pytest.approx(decoded.linear.x) == 0.45
    assert pytest.approx(decoded.linear.y) == -0.12
    assert pytest.approx(decoded.linear.z) == 0.0
    assert pytest.approx(decoded.angular.x) == 0.0
    assert pytest.approx(decoded.angular.y) == 0.0
    assert pytest.approx(decoded.angular.z) == 0.85


@pytest.mark.asyncio
async def test_ros2_bridge_publish_cmd_vel() -> None:
    """Verify ROS2Bridge publish_cmd_vel stores state and emits serialized CDR bytes."""
    bridge = ROS2Bridge(node_name="test_cmd_vel_node")
    twist = Twist(
        linear=Vector3(x=0.6, y=0.0, z=0.0),
        angular=Vector3(x=0.0, y=0.0, z=-0.3),
    )
    cdr_bytes = await bridge.publish_cmd_vel(twist)
    assert isinstance(cdr_bytes, bytes)
    assert len(cdr_bytes) > 0

    state = await bridge.read_state()
    assert state["latest_twist"] is not None
    assert pytest.approx(state["latest_twist"]["linear"]["x"]) == 0.6
    assert pytest.approx(state["latest_twist"]["angular"]["z"]) == -0.3


@pytest.mark.asyncio
async def test_ros2_bridge_execute_cmd_vel() -> None:
    """Verify execute command interface handles cmd_vel and publish_twist."""
    bridge = ROS2Bridge(node_name="test_exec_node")
    res = await bridge.execute(
        "cmd_vel",
        {
            "linear": {"x": 0.25, "y": 0.0, "z": 0.0},
            "angular": {"x": 0.0, "y": 0.0, "z": 0.5},
        },
    )
    assert res["status"] == "success"
    assert res["bytes_serialized"] > 0
    assert pytest.approx(res["linear"]["x"]) == 0.25
    assert pytest.approx(res["angular"]["z"]) == 0.5


@pytest.mark.asyncio
async def test_arm_controller_ros2_publishing() -> None:
    """Verify ArmController automatically publishes trajectories and actuator commands when bridge is attached."""
    bridge = ROS2Bridge(node_name="test_arm_bridge")
    arm = ArmController()
    arm.attach_ros2_bridge(bridge)

    # Move arm
    target = JointConfiguration(base=0.1, shoulder=0.5, elbow=-1.0, wrist=0.3)
    result = arm.move_to_joints(target, duration=0.5)
    assert result["status"] == "success"

    # Allow asyncio loop to execute the background publish task
    await asyncio.sleep(0.01)
    assert bridge._published_count >= 1

    # Actuate gripper
    gripper_res = arm.set_gripper(open_gripper=False)
    assert gripper_res["status"] == "success"
    await asyncio.sleep(0.01)
    assert bridge._published_count >= 2


@pytest.mark.asyncio
async def test_navigation_controller_ros2_publishing() -> None:
    """Verify NavigationController automatically publishes Twist cmd_vel when bridge is attached."""
    bridge = ROS2Bridge(node_name="test_nav_bridge")
    nav = NavigationController()
    nav.attach_ros2_bridge(bridge)

    # Set velocity
    res = nav.set_velocity(0.4, -0.2)
    assert res["status"] == "success"
    await asyncio.sleep(0.01)
    assert bridge._published_count >= 1
    assert bridge._latest_twist is not None
    assert pytest.approx(bridge._latest_twist["linear"]["x"]) == 0.4
    assert pytest.approx(bridge._latest_twist["angular"]["z"]) == -0.2

    # Stop mobile base
    stop_res = nav.stop()
    assert stop_res["status"] == "success"
    await asyncio.sleep(0.01)
    assert bridge._published_count >= 2
    assert pytest.approx(bridge._latest_twist["linear"]["x"]) == 0.0
    assert pytest.approx(bridge._latest_twist["angular"]["z"]) == 0.0


@pytest.mark.asyncio
async def test_agent_lifecycle_with_ros2_bridge() -> None:
    """Verify Agent initializes ROS2Bridge and attaches it to arm and nav controllers."""
    config = EfferoConfig(
        robotics=RoboticsConfig(
            ros2=ROS2Config(
                enabled=True,
                node_name="agent_ros2_bridge",
                transport_port=59123,  # unallocated port
            )
        )
    )
    agent = Agent(config)
    assert agent.ros2_bridge is None

    await agent.start()
    assert agent.ros2_bridge is not None
    assert agent.ros2_bridge.node_name == "agent_ros2_bridge"

    from effero.skills.robotics.arm import _arm_controller
    from effero.skills.robotics.navigate import _nav_controller

    assert _arm_controller.ros2_bridge is agent.ros2_bridge
    assert _nav_controller.ros2_bridge is agent.ros2_bridge

    await agent.stop()
    assert agent.ros2_bridge is None
    assert _arm_controller.ros2_bridge is None
    assert _nav_controller.ros2_bridge is None
