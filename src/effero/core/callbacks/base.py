"""Life-cycle callback interfaces for Agent execution and safety monitoring.

Inspired by Keras Callbacks and PyTorch lightning hooks.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


class AgentCallback:
    """Base class for observing agent execution lifecycle events with default no-op hooks."""

    def on_agent_start(self, prompt: str) -> None:
        """Called when an agent starts processing a new prompt/task."""
        pass

    def on_agent_finish(self, response: str, elapsed_seconds: float) -> None:
        """Called when an agent successfully finishes a run."""
        pass

    def on_agent_error(self, error: Exception) -> None:
        """Called when an unhandled exception occurs during execution."""
        pass

    def on_plan_generated(self, plan: Any) -> None:
        """Called after the cognitive planner produces execution steps or tool calls."""
        pass

    def on_skill_before_execute(self, skill_name: str, arguments: dict[str, Any]) -> None:
        """Called immediately before a skill function is executed."""
        pass

    def on_skill_after_execute(self, skill_name: str, result: Any, elapsed_seconds: float) -> None:
        """Called immediately after a skill execution completes."""
        pass

    def on_safety_check(
        self, skill_name: str, arguments: dict[str, Any], approved: bool, reason: str | None = None
    ) -> None:
        """Called when safety kernel or HITL evaluates an action."""
        pass


class CallbackList:
    """Manages a sequence of callbacks with exception isolation."""

    def __init__(self, callbacks: list[AgentCallback] | None = None) -> None:
        self.callbacks: list[AgentCallback] = callbacks or []

    def add(self, callback: AgentCallback) -> None:
        self.callbacks.append(callback)

    def on_agent_start(self, prompt: str) -> None:
        for cb in self.callbacks:
            try:
                cb.on_agent_start(prompt)
            except Exception as e:
                logger.warning(f"Callback {cb.__class__.__name__}.on_agent_start failed: {e}")

    def on_agent_finish(self, response: str, elapsed_seconds: float) -> None:
        for cb in self.callbacks:
            try:
                cb.on_agent_finish(response, elapsed_seconds)
            except Exception as e:
                logger.warning(f"Callback {cb.__class__.__name__}.on_agent_finish failed: {e}")

    def on_agent_error(self, error: Exception) -> None:
        for cb in self.callbacks:
            try:
                cb.on_agent_error(error)
            except Exception as e:
                logger.warning(f"Callback {cb.__class__.__name__}.on_agent_error failed: {e}")

    def on_plan_generated(self, plan: Any) -> None:
        for cb in self.callbacks:
            try:
                cb.on_plan_generated(plan)
            except Exception as e:
                logger.warning(f"Callback {cb.__class__.__name__}.on_plan_generated failed: {e}")

    def on_skill_before_execute(self, skill_name: str, arguments: dict[str, Any]) -> None:
        for cb in self.callbacks:
            try:
                cb.on_skill_before_execute(skill_name, arguments)
            except Exception as e:
                logger.warning(f"Callback {cb.__class__.__name__}.on_skill_before_execute failed: {e}")

    def on_skill_after_execute(self, skill_name: str, result: Any, elapsed_seconds: float) -> None:
        for cb in self.callbacks:
            try:
                cb.on_skill_after_execute(skill_name, result, elapsed_seconds)
            except Exception as e:
                logger.warning(f"Callback {cb.__class__.__name__}.on_skill_after_execute failed: {e}")

    def on_safety_check(
        self, skill_name: str, arguments: dict[str, Any], approved: bool, reason: str | None = None
    ) -> None:
        for cb in self.callbacks:
            try:
                cb.on_safety_check(skill_name, arguments, approved, reason)
            except Exception as e:
                logger.warning(f"Callback {cb.__class__.__name__}.on_safety_check failed: {e}")
