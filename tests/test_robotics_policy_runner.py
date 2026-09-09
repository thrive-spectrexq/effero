"""Tests for Isaac Lab policy runner, observation buffer, and actuator delay."""

import pytest

from effero.robotics.policy_runner import DelayedActuatorQueue, IsaacLabPolicyRunner, ObservationBuffer
from effero.skills.robotics.policy import reset_policy, step_policy


def test_delayed_actuator_queue() -> None:
    # 2-step delay
    queue = DelayedActuatorQueue(delay_steps=2)

    # Step 0: action a0 -> holds initial action (a0)
    out0 = queue.step([1.0, 2.0])
    assert out0 == [1.0, 2.0]

    # Step 1: action a1 -> holds initial action (a0)
    out1 = queue.step([3.0, 4.0])
    assert out1 == [1.0, 2.0]

    # Step 2: action a2 -> returns action from 2 steps ago (a0)
    out2 = queue.step([5.0, 6.0])
    assert out2 == [1.0, 2.0]

    # Step 3: action a3 -> returns a1
    out3 = queue.step([7.0, 8.0])
    assert out3 == [3.0, 4.0]

    # Zero delay test
    zero_q = DelayedActuatorQueue(delay_steps=0)
    assert zero_q.step([10.0]) == [10.0]


def test_observation_buffer() -> None:
    buf = ObservationBuffer(observation_dim=2, history_len=3)
    buf.reset([0.5, 0.5])

    flat = buf.get_flattened()
    assert len(flat) == 6  # 2 * 3
    assert flat == [0.5, 0.5, 0.5, 0.5, 0.5, 0.5]

    buf.append([1.0, 2.0])
    flat = buf.get_flattened()
    # Newest is [1.0, 2.0], then two [0.5, 0.5]
    assert flat[:2] == [1.0, 2.0]
    assert flat[2:] == [0.5, 0.5, 0.5, 0.5]

    with pytest.raises(ValueError):
        buf.append([1.0])  # dimension mismatch


def test_isaac_lab_policy_runner_step() -> None:
    runner = IsaacLabPolicyRunner(
        observation_dim=4,
        action_dim=2,
        history_len=2,
        action_scale=0.5,
        default_joint_pos=[0.1, -0.1],
        delay_steps=1,
    )
    runner.reset()

    # Step without model session uses zero action fallback: target = default_joint_pos
    targets = runner.step([0.0, 1.0, 2.0, 3.0])
    assert len(targets) == 2
    assert targets == [0.1, -0.1]


def test_robotics_policy_skill() -> None:
    reset_res = reset_policy()
    assert reset_res["status"] == "ok"

    step_res = step_policy([0.1] * 48)
    assert step_res["status"] == "ok"
    assert step_res["action_dim"] == 12
    assert len(step_res["target_joint_positions"]) == 12
