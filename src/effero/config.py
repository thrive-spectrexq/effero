"""Effero configuration system — parses effero.yaml into typed models."""

from __future__ import annotations

import os
from pathlib import Path

import yaml
from pydantic import BaseModel, Field


class ModelConfig(BaseModel):
    backend: str = "openai"
    model: str = "gpt-4o"
    fallback: list[str] = Field(default_factory=list)
    api_key: str | None = None
    base_url: str | None = None


class AudioConfig(BaseModel):
    enabled: bool = False
    wake_word: str | None = None
    asr: str = "openai:whisper-1"
    tts: str = "openai:tts-1"
    vad_enabled: bool = True


class VisionConfig(BaseModel):
    enabled: bool = False
    backend: str = "yolov9"
    camera_index: int = 0
    frame_rate: float = 1.0


class SensorConfig(BaseModel):
    enabled: bool = False
    poll_interval: float = 1.0


class PerceptionConfig(BaseModel):
    audio: AudioConfig = Field(default_factory=AudioConfig)
    vision: VisionConfig = Field(default_factory=VisionConfig)
    sensors: SensorConfig = Field(default_factory=SensorConfig)


class SafetyConfig(BaseModel):
    enabled: bool = True
    kernel_host: str = "127.0.0.1"
    kernel_port: int = 9400
    policy: str | None = None
    require_approval_for: list[str] = Field(default_factory=list)
    approval_mode: str = "console"


class FleetConfig(BaseModel):
    enabled: bool = False
    default_lease_duration: float = 30.0


class AgentConfig(BaseModel):
    name: str = "effero-agent"
    model: ModelConfig = Field(default_factory=ModelConfig)


class EfferoConfig(BaseModel):
    agent: AgentConfig = Field(default_factory=AgentConfig)
    perception: PerceptionConfig = Field(default_factory=PerceptionConfig)
    skills: list[str] = Field(default_factory=list)
    safety: SafetyConfig = Field(default_factory=SafetyConfig)
    fleet: FleetConfig = Field(default_factory=FleetConfig)

    @classmethod
    def load(cls, path: Path | str | None = None) -> EfferoConfig:
        """Load config from YAML file, falling back to defaults."""
        if path is None:
            path = Path.cwd() / "effero.yaml"
        path = Path(path)
        if path.exists():
            with open(path) as f:
                data = yaml.safe_load(f) or {}
            return cls.model_validate(data)
        return cls()

    @classmethod
    def from_env(cls, path: Path | str | None = None) -> EfferoConfig:
        """Build config with environment variable overrides."""
        config = cls.load(path)
        backend = config.agent.model.backend
        env_map = {
            "openai": "OPENAI_API_KEY",
            "anthropic": "ANTHROPIC_API_KEY",
            "google": "GOOGLE_API_KEY",
        }
        env_var = env_map.get(backend)
        if env_var and (key := os.environ.get(env_var)):
            config.agent.model.api_key = key
        return config
