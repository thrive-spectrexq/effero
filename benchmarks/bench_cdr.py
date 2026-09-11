"""Benchmark for OMG CDR serialization and deserialization throughput."""

from __future__ import annotations

from typing import Any

import pytest

from effero.adapters.ros2.bridge import (
    Header,
    JointTrajectory,
    JointTrajectoryPoint,
    ROS2CDRSerializer,
    Twist,
    Vector3,
)


@pytest.fixture
def complex_joint_trajectory() -> JointTrajectory:
    points = [
        JointTrajectoryPoint(
            positions=[0.1 * i, -0.2 * i, 0.3 * i, -0.05 * i],
            velocities=[0.05, -0.05, 0.1, -0.02],
            accelerations=[0.01, -0.01, 0.02, -0.005],
            effort=[],
            time_from_start_sec=i // 10,
            time_from_start_nanosec=(i % 10) * 100_000_000,
        )
        for i in range(50)
    ]
    return JointTrajectory(
        header=Header(frame_id="arm_base_link"),
        joint_names=["base", "shoulder", "elbow", "wrist"],
        points=points,
    )


@pytest.fixture
def twist_command() -> Twist:
    return Twist(
        linear=Vector3(x=0.8, y=0.0, z=0.0),
        angular=Vector3(x=0.0, y=0.0, z=-0.35),
    )


def test_bench_cdr_serialize_trajectory(benchmark: Any, complex_joint_trajectory: JointTrajectory) -> None:
    """Benchmark OMG CDR serialization of a 50-point 4-DOF JointTrajectory."""
    raw = benchmark(ROS2CDRSerializer.serialize_joint_trajectory, complex_joint_trajectory)
    assert len(raw) > 0


def test_bench_cdr_deserialize_trajectory(benchmark: Any, complex_joint_trajectory: JointTrajectory) -> None:
    """Benchmark OMG CDR deserialization of a 50-point 4-DOF JointTrajectory."""
    raw = ROS2CDRSerializer.serialize_joint_trajectory(complex_joint_trajectory)
    msg = benchmark(ROS2CDRSerializer.deserialize_joint_trajectory, raw)
    assert len(msg.points) == 50


def test_bench_cdr_serialize_twist(benchmark: Any, twist_command: Twist) -> None:
    """Benchmark OMG CDR serialization of a Twist cmd_vel packet."""
    raw = benchmark(ROS2CDRSerializer.serialize_twist, twist_command)
    assert len(raw) >= 52


def test_bench_cdr_deserialize_twist(benchmark: Any, twist_command: Twist) -> None:
    """Benchmark OMG CDR deserialization of a Twist cmd_vel packet."""
    raw = ROS2CDRSerializer.serialize_twist(twist_command)
    msg = benchmark(ROS2CDRSerializer.deserialize_twist, raw)
    assert pytest.approx(msg.linear.x) == 0.8
