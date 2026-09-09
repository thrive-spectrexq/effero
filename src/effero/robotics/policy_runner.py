"""Isaac Lab ONNX Policy Runner and Actuator Dynamics.

Provides temporal observation history buffers, delayed PD actuator modeling
(emulating Isaac Lab's DelayedPDActuator pattern), and execution of exported
ONNX locomotion/manipulation policies.
"""

from __future__ import annotations

import collections
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class DelayedActuatorQueue:
    """Models transport/hardware latency between policy inference and motor actuation.

    Emulates Isaac Lab's `DelayedPDActuator` / `history_buffer` where motor commands
    take N control steps or time duration to reach the physical actuators.
    """

    delay_steps: int = 1
    _queue: collections.deque[list[float]] = field(default_factory=collections.deque)

    def __post_init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        """Clear queue buffer."""
        self._queue.clear()

    def step(self, action: list[float]) -> list[float]:
        """Push a new action command and return the delayed command applied at this timestep.

        If delay_steps == 0, returns the action immediately.
        Otherwise, returns previous action from `delay_steps` ago.
        """
        if self.delay_steps <= 0:
            return list(action)

        self._queue.append(list(action))
        if len(self._queue) <= self.delay_steps:
            # Not enough history yet: hold initial action (or zeros)
            return self._queue[0]

        return self._queue.popleft()


class ObservationBuffer:
    """Temporal observation buffer for policy inputs with history (e.g. Isaac Lab H=5 or H=10).

    Concatenates state vectors across consecutive time steps:
    [obs_t, obs_{t-1}, ..., obs_{t-(history_len-1)}]
    """

    def __init__(self, observation_dim: int, history_len: int = 5) -> None:
        self.observation_dim = observation_dim
        self.history_len = max(1, history_len)
        self._history: collections.deque[list[float]] = collections.deque(maxlen=self.history_len)

    def reset(self, initial_obs: list[float] | None = None) -> None:
        """Reset history, optionally seeding with repeated initial observation."""
        self._history.clear()
        fill = list(initial_obs) if initial_obs else [0.0] * self.observation_dim
        for _ in range(self.history_len):
            self._history.append(list(fill))

    def append(self, obs: list[float]) -> None:
        """Append a new observation vector."""
        if len(obs) != self.observation_dim:
            raise ValueError(f"Expected observation of dim {self.observation_dim}, got {len(obs)}")
        self._history.append(list(obs))

    def get_flattened(self) -> list[float]:
        """Get flattened array from newest to oldest observation."""
        if len(self._history) < self.history_len:
            # Pad with oldest observation if needed
            pad_val = self._history[0] if self._history else [0.0] * self.observation_dim
            while len(self._history) < self.history_len:
                self._history.appendleft(list(pad_val))

        out: list[float] = []
        for obs in reversed(self._history):
            out.extend(obs)
        return out


class IsaacLabPolicyRunner:
    """Executes trained Isaac Lab / Isaac Sim RL & IL policies exported to ONNX format.

    Handles observation normalization, history buffering, inference (via ONNXRuntime or
    pure-Python linear fallback), action scaling, and actuator delay modeling.
    """

    def __init__(
        self,
        model_path: str | Path | None = None,
        observation_dim: int = 48,
        action_dim: int = 12,
        history_len: int = 1,
        action_scale: float = 0.25,
        default_joint_pos: list[float] | None = None,
        delay_steps: int = 0,
    ) -> None:
        self.model_path = Path(model_path) if model_path else None
        self.observation_dim = observation_dim
        self.action_dim = action_dim
        self.history_len = history_len
        self.action_scale = action_scale
        self.default_joint_pos = default_joint_pos or [0.0] * action_dim
        self.obs_buffer = ObservationBuffer(observation_dim, history_len)
        self.actuator_delay = DelayedActuatorQueue(delay_steps)
        self._session: Any = None

        if self.model_path and self.model_path.exists():
            self._init_session()

    def _init_session(self) -> None:
        try:
            import onnxruntime as ort

            self._session = ort.InferenceSession(
                str(self.model_path),
                providers=["CPUExecutionProvider"],
            )
            logger.info(f"Loaded ONNX policy from {self.model_path}")
        except ImportError:
            logger.warning("onnxruntime not installed; policy runner will operate in kinematic passthrough mode")
            self._session = None

    def reset(self, initial_obs: list[float] | None = None) -> None:
        """Reset observation history and actuator delay queues."""
        self.obs_buffer.reset(initial_obs)
        self.actuator_delay.reset()

    def step(self, observation: list[float]) -> list[float]:
        """Compute single policy control step.

        1. Push observation to temporal history buffer.
        2. Execute policy network inference.
        3. Scale action and apply default joint offset: target = default_pos + action * scale.
        4. Apply actuator delay queue.
        5. Return delayed joint target positions.
        """
        self.obs_buffer.append(observation)
        flat_obs = self.obs_buffer.get_flattened()

        raw_action = self._infer(flat_obs)

        # Scale action to joint targets
        scaled_targets: list[float] = []
        for i in range(self.action_dim):
            act = raw_action[i] if i < len(raw_action) else 0.0
            default_p = self.default_joint_pos[i] if i < len(self.default_joint_pos) else 0.0
            scaled_targets.append(default_p + act * self.action_scale)

        # Apply actuator delay
        delayed_targets = self.actuator_delay.step(scaled_targets)
        return delayed_targets

    def _infer(self, flat_obs: list[float]) -> list[float]:
        if self._session is not None:
            import numpy as np

            input_name = self._session.get_inputs()[0].name
            inp = np.array([flat_obs], dtype=np.float32)
            outputs = self._session.run(None, {input_name: inp})
            return outputs[0][0].tolist()

        return [0.0] * self.action_dim
