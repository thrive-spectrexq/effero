"""Minimal placeholder for the Effero plan -> act -> observe -> replan loop.

This is intentionally small: it exists so the package imports cleanly
and so early contributors have a concrete seam to build the real
orchestrator described in the top-level README's Architecture section
(graph-based planning, memory reads/writes, guardrail checks before
every skill call). See ROADMAP for sequencing.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from effero.sdk.skill import SkillRegistry
from effero.sdk.skill import registry as default_registry


@dataclass
class AgentStep:
    """A single recorded step in the agent's history."""

    thought: str
    skill_name: str | None = None
    result: Any = None


@dataclass
class Agent:
    """A placeholder orchestrator.

    Real planning logic (LLM calls, replanning on failure, memory
    integration, guardrail enforcement) lands in a later milestone --
    this class only wires together the pieces that already exist
    (the skill registry) so it's usable and testable today.
    """

    name: str
    skills: SkillRegistry = field(default_factory=lambda: default_registry)
    history: list[AgentStep] = field(default_factory=list)

    def available_skills(self) -> list[str]:
        """List the names of every skill this agent can currently invoke."""
        return self.skills.list()

    def invoke_skill(self, name: str, /, **kwargs: Any) -> Any:
        """Directly invoke a registered skill by name and record the step.

        This bypasses planning and guardrail enforcement entirely -- it
        exists as a low-level building block for tests and early
        experimentation, not as the intended production call path.
        """
        spec = self.skills.get(name)
        result = spec(**kwargs)
        self.history.append(AgentStep(thought=f"invoke {name}", skill_name=name, result=result))
        return result
