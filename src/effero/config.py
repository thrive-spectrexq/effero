"""Effero configuration system — parses effero.yaml into typed models."""

from __future__ import annotations

import logging
import os
from pathlib import Path

import yaml
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class ModelConfig(BaseModel):
    backend: str = "openai"
    model: str = "gpt-4o"
    fallback: list[str] = Field(default_factory=list)
    api_key: str | None = None
    base_url: str | None = None
    min_confidence: float = 0.7
    hybrid_cloud_fallback: bool = True
    device: str = "auto"


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
    auto_spawn: bool = True
    heartbeat_enabled: bool = True
    heartbeat_interval: float = 0.2


class FleetConfig(BaseModel):
    enabled: bool = False
    default_lease_duration: float = 30.0


class ServerConfig(BaseModel):
    host: str = "0.0.0.0"
    port: int = 8000
    api_key: str | None = None
    no_auth: bool = False
    cors_origins: list[str] = Field(default_factory=list)


class IoTConfig(BaseModel):
    enabled: bool = False
    broker_host: str = "127.0.0.1"
    broker_port: int = 1883
    username: str | None = None
    password: str | None = None
    client_id: str | None = None
    keepalive: int = 60
    auto_connect: bool = True
    use_tls: bool = False
    ca_certs: str | None = None
    certfile: str | None = None
    keyfile: str | None = None
    tls_insecure: bool = False


class ROS2Config(BaseModel):
    enabled: bool = False
    node_name: str = "effero_bridge"
    transport_host: str = "127.0.0.1"
    transport_port: int = 9090
    joint_trajectory_topic: str = "/joint_trajectory_controller/joint_trajectory"
    joint_states_topic: str = "/joint_states"
    cmd_vel_topic: str = "/cmd_vel"
    auto_publish_arm_trajectory: bool = True
    auto_publish_nav_cmd_vel: bool = True


class RoboticsConfig(BaseModel):
    enabled: bool = True
    ros2: ROS2Config = Field(default_factory=ROS2Config)


class MCPServerConfig(BaseModel):
    name: str
    command: str | None = None
    args: list[str] = Field(default_factory=list)
    env: dict[str, str] = Field(default_factory=dict)
    url: str | None = None
    default_safety_class: str = "act_with_approval"


class AgentConfig(BaseModel):
    name: str = "effero-agent"
    model: ModelConfig = Field(default_factory=ModelConfig)


class EfferoConfig(BaseModel):
    agent: AgentConfig = Field(default_factory=AgentConfig)
    server: ServerConfig = Field(default_factory=ServerConfig)
    perception: PerceptionConfig = Field(default_factory=PerceptionConfig)
    skills: list[str] = Field(default_factory=list)
    safety: SafetyConfig = Field(default_factory=SafetyConfig)
    fleet: FleetConfig = Field(default_factory=FleetConfig)
    iot: IoTConfig = Field(default_factory=IoTConfig)
    robotics: RoboticsConfig = Field(default_factory=RoboticsConfig)
    mcp_servers: list[MCPServerConfig] = Field(default_factory=list)

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

        # Server API key override from environment
        if server_key := os.environ.get("EFFERO_API_KEY"):
            config.server.api_key = server_key

        # IoT MQTT credential overrides from environment
        if mqtt_pwd := os.environ.get("EFFERO_MQTT_PASSWORD") or os.environ.get("MQTT_PASSWORD"):
            config.iot.password = mqtt_pwd
        if mqtt_user := os.environ.get("EFFERO_MQTT_USERNAME") or os.environ.get("MQTT_USERNAME"):
            config.iot.username = mqtt_user

        for warning in config.validate_security():
            logger.warning(warning)

        return config

    def validate_security(self) -> list[str]:
        """Audit configuration for insecure defaults and return a list of warnings."""
        warnings: list[str] = []
        if not self.server.api_key:
            warnings.append(
                "Insecure configuration: server.api_key is not set. "
                "REST and WebSocket endpoints are open without authentication."
            )
        if self.iot.enabled and not self.iot.use_tls:
            warnings.append(
                "Insecure configuration: IoT MQTT is enabled without TLS. "
                "Sensor telemetry and motor commands are sent in plaintext."
            )
        if self.iot.tls_insecure:
            warnings.append(
                "Insecure configuration: iot.tls_insecure is True. "
                "Broker certificates will not be validated, allowing MITM attacks."
            )
        return warnings

    def save(self, path: Path | str | None = None) -> Path:
        """Serialize configuration model to YAML file with restrictive file permissions."""
        if path is None:
            path = Path.cwd() / "effero.yaml"
        target_path = Path(path)
        data = self.model_dump(mode="python", exclude_none=True)
        target_path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
        try:
            target_path.chmod(0o600)
        except OSError:
            pass
        return target_path
