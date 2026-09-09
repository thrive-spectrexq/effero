"""Skill for running learned neural policies (Isaac Lab / Isaac Sim RL / imitation learning)."""

from __future__ import annotations

from typing import Any

from effero.robotics.policy_runner import IsaacLabPolicyRunner
from effero.sdk.skill import SafetyClass, skill

_active_runner: IsaacLabPolicyRunner | None = None


def get_or_create_policy_runner(
    observation_dim: int = 48,
    action_dim: int = 12,
    history_len: int = 5,
    delay_steps: int = 1,
    action_scale: float = 0.25,
) -> IsaacLabPolicyRunner:
    global _active_runner
    if _active_runner is None:
        _active_runner = IsaacLabPolicyRunner(
            observation_dim=observation_dim,
            action_dim=action_dim,
            history_len=history_len,
            delay_steps=delay_steps,
            action_scale=action_scale,
        )
    return _active_runner


@skill(
    name="robotics.policy.step",
    description="Feed sensor observation vector to active neural policy and return joint targets.",
    safety_class=SafetyClass.ACT_AUTONOMOUS,
)
def step_policy(observation: list[float]) -> dict[str, Any]:
    """Execute a single control step through the learned policy runner.

    Args:
        observation: State vector (joint positions, velocities, commands, IMU)

    Returns:
        Dictionary with status and commanded target positions.
    """
    runner = get_or_create_policy_runner(observation_dim=len(observation))
    targets = runner.step(observation)
    return {
        "status": "ok",
        "action_dim": len(targets),
        "target_joint_positions": [round(t, 4) for t in targets],
    }


@skill(
    name="robotics.policy.reset",
    description="Reset the temporal observation buffer and actuator latency queue for the active neural policy.",
    safety_class=SafetyClass.ACT_AUTONOMOUS,
)
def reset_policy() -> dict[str, Any]:
    """Reset policy runner history buffer and actuator latency pipeline."""
    global _active_runner
    if _active_runner is not None:
        _active_runner.reset()
    return {"status": "ok", "message": "Policy history and actuator buffers reset"}
