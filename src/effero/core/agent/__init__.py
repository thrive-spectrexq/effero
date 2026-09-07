"""The Agent — wires together all Effero subsystems."""

from __future__ import annotations

import logging

from effero.config import EfferoConfig
from effero.core.event_bus import EventBus
from effero.core.memory.episodic import EpisodicMemory
from effero.core.memory.semantic import SemanticMemory
from effero.core.memory.working import WorkingMemory
from effero.core.planner.planner import Planner
from effero.core.router.router import ModelRouter
from effero.safety.client import SafetyClient
from effero.sdk.skill import SkillRegistry
from effero.sdk.skill import registry as global_registry

logger = logging.getLogger(__name__)


class Agent:
    """The top-level Effero agent.

    Wires together: config, event bus, skills, memory, model router,
    safety client, planner, and perception pipelines.
    """

    def __init__(
        self,
        config: EfferoConfig | None = None,
        skills: SkillRegistry | None = None,
        approval_handler=None,
    ) -> None:
        self.config = config or EfferoConfig.load()
        self.event_bus = EventBus()
        self.skills = skills or global_registry
        self.working_memory = WorkingMemory()
        self.episodic_memory = EpisodicMemory()
        self.semantic_memory = SemanticMemory()
        self.router = ModelRouter(self.config.agent.model)
        self.safety: SafetyClient | None = None
        if self.config.safety.enabled:
            self.safety = SafetyClient(
                host=self.config.safety.kernel_host,
                port=self.config.safety.kernel_port,
            )

        if approval_handler is not None:
            self.approval_handler = approval_handler
        elif self.config.safety.approval_mode == "auto":
            from effero.safety.approval import AutoApprovalHandler

            self.approval_handler = AutoApprovalHandler(approve_all=True)
        else:
            from effero.safety.approval import ConsoleApprovalHandler

            self.approval_handler = ConsoleApprovalHandler()

        self.planner = Planner(
            router=self.router,
            memory=self.working_memory,
            skills=self.skills,
            safety_client=self.safety,
            approval_handler=self.approval_handler,
        )

    async def run(self, instruction: str) -> str:
        """Execute an instruction through the planner loop."""
        logger.info(f"Agent '{self.config.agent.name}' processing: {instruction}")
        result = await self.planner.run(instruction)
        # Record to episodic memory
        self.episodic_memory.record(
            "interaction",
            {
                "instruction": instruction,
                "response": result,
            },
        )
        return result

    async def chat(self, message: str) -> str:
        """Single-turn chat interface."""
        return await self.run(message)

    async def start(self) -> None:
        """Start background services."""
        if self.safety:
            try:
                await self.safety.connect()
                logger.info("Connected to safety kernel")
            except (ConnectionRefusedError, OSError) as e:
                logger.warning(f"Safety kernel not running ({e}) — operating without guardrails")
                self.safety = None
                self.planner.safety = None

        # Load built-in skills
        self._load_builtin_skills()

        logger.info(f"Agent '{self.config.agent.name}' started with {len(self.skills.list())} skills")

    async def stop(self) -> None:
        """Graceful shutdown."""
        if self.safety:
            await self.safety.close()
        logger.info(f"Agent '{self.config.agent.name}' stopped")

    def _load_builtin_skills(self) -> None:
        """Import built-in skill modules to trigger @skill registration."""
        skill_modules = [
            "effero.skills.iot.lights",
            "effero.skills.iot.thermostat",
            "effero.skills.iot.sensors",
            "effero.skills.computer_use.shell",
            "effero.skills.computer_use.browser",
            "effero.skills.computer_use.file_ops",
            "effero.skills.robotics.arm",
            "effero.skills.robotics.navigate",
        ]
        import importlib

        for mod_name in skill_modules:
            try:
                importlib.import_module(mod_name)
            except ImportError as e:
                logger.debug(f"Could not load skill module {mod_name}: {e}")

    def available_skills(self) -> list[str]:
        """List names of all registered skills."""
        return list(self.skills.list())
