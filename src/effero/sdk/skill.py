"""Effero SDK: skill registration decorator and safety classification.

A "skill" is the atomic unit of capability in Effero: a robot joint, a
smart plug, a shell command, and a browser click are all exposed through
this same interface. In a full deployment each registered skill is also
exposed as an MCP tool, so Effero's own planner -- and any other
MCP-compatible client -- can call it without extra glue code.

This module is deliberately dependency-free and self-contained so it can
be imported (and unit-tested) without the rest of the runtime.
"""

from __future__ import annotations

import functools
import inspect
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class SafetyClass(StrEnum):
    """Declares how much autonomy a skill is trusted with.

    READ_ONLY          -- cannot change any external state.
    ACT_AUTONOMOUS      -- may act without human approval.
    ACT_WITH_APPROVAL   -- requires human-in-the-loop confirmation before executing.
    ACT_RESTRICTED       -- simulation/dry-run only until explicitly promoted.
    """

    READ_ONLY = "read_only"
    ACT_AUTONOMOUS = "act_autonomous"
    ACT_WITH_APPROVAL = "act_with_approval"
    ACT_RESTRICTED = "act_restricted"


@dataclass
class SkillSpec:
    """The registered form of a skill: metadata plus the callable itself."""

    name: str
    description: str
    safety_class: SafetyClass
    func: Callable[..., Any]
    signature: inspect.Signature = field(repr=False)

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        return self.func(*args, **kwargs)


class SkillRegistry:
    """Process-wide registry of every skill Effero knows about.

    A later milestone will project this registry out as MCP tool
    schemas; for now it's a plain in-memory lookup so the rest of the
    runtime (and tests) have something concrete to build against.
    """

    def __init__(self) -> None:
        self._skills: dict[str, SkillSpec] = {}

    def register(self, spec: SkillSpec) -> None:
        if spec.name in self._skills:
            raise ValueError(f"Skill '{spec.name}' is already registered.")
        self._skills[spec.name] = spec

    def get(self, name: str) -> SkillSpec:
        try:
            return self._skills[name]
        except KeyError as exc:
            raise KeyError(f"No skill registered under '{name}'.") from exc

    def list(self) -> list[str]:
        return sorted(self._skills)

    def clear(self) -> None:
        """Reset the registry. Mainly useful in tests."""
        self._skills.clear()


#: The default, process-wide registry. Most code should use this rather
#: than constructing its own SkillRegistry.
registry = SkillRegistry()


def skill(
    name: str,
    description: str,
    safety_class: SafetyClass = SafetyClass.ACT_WITH_APPROVAL,
) -> Callable[[Callable[..., Any]], SkillSpec]:
    """Decorator that turns a plain function into a registered Effero skill.

    Example:
        >>> from effero.sdk import skill, SafetyClass
        >>>
        >>> @skill(
        ...     name="iot.thermostat.set_temperature",
        ...     description="Set the target temperature of a named thermostat.",
        ...     safety_class=SafetyClass.ACT_AUTONOMOUS,
        ... )
        ... def set_temperature(thermostat_id: str, celsius: float) -> dict:
        ...     return {"status": "ok", "device": thermostat_id, "target_temperature": celsius}
        >>> set_temperature("kitchen", 21.5)
        {'status': 'ok', 'device': 'kitchen', 'target_temperature': 21.5}
    """

    def decorator(func: Callable[..., Any]) -> SkillSpec:
        spec = SkillSpec(
            name=name,
            description=description,
            safety_class=safety_class,
            func=func,
            signature=inspect.signature(func),
        )
        functools.update_wrapper(spec, func)
        registry.register(spec)
        return spec

    return decorator


BUILTIN_SKILL_MODULES: list[str] = [
    "effero.skills.iot.lights",
    "effero.skills.iot.thermostat",
    "effero.skills.iot.sensors",
    "effero.skills.computer_use.shell",
    "effero.skills.computer_use.browser",
    "effero.skills.computer_use.file_ops",
    "effero.skills.robotics.arm",
    "effero.skills.robotics.navigate",
]
