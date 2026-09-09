"""Tests for config loading and validation."""

from __future__ import annotations

import tempfile
from pathlib import Path

from effero.config import EfferoConfig


def test_default_config() -> None:
    config = EfferoConfig()
    assert config.agent.name == "effero-agent"
    assert config.agent.model.backend == "openai"
    assert config.agent.model.model == "gpt-4o"
    assert config.safety.enabled is True
    assert config.safety.kernel_port == 9400


def test_load_from_yaml() -> None:
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        f.write("""
agent:
  name: my-agent
  model:
    backend: anthropic
    model: claude-sonnet-4-20250514
skills:
  - iot.lights
  - iot.thermostat
""")
        f_path = f.name
    try:
        config = EfferoConfig.load(f_path)
        assert config.agent.name == "my-agent"
        assert config.agent.model.backend == "anthropic"
        assert config.skills == ["iot.lights", "iot.thermostat"]
    finally:
        Path(f_path).unlink()


def test_load_missing_file_returns_defaults() -> None:
    config = EfferoConfig.load("nonexistent_path_999.yaml")
    # Should return defaults, not raise
    assert config.agent.name == "effero-agent"


def test_nested_config_parsing() -> None:
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        f.write("""
agent:
  name: nested
  model:
    backend: google
    model: gemini-2.5-flash
    fallback:
      - openai:gpt-4o
perception:
  audio:
    enabled: true
    asr: faster-whisper:small.en
  vision:
    enabled: true
    backend: yolov9
safety:
  enabled: true
  kernel_port: 9500
  require_approval_for:
    - robotics.*
""")
        f_path = f.name
    try:
        config = EfferoConfig.load(f_path)
        assert config.agent.model.backend == "google"
        assert config.agent.model.fallback == ["openai:gpt-4o"]
        assert config.perception.audio.enabled is True
        assert config.perception.vision.backend == "yolov9"
        assert config.safety.kernel_port == 9500
        assert "robotics.*" in config.safety.require_approval_for
    finally:
        Path(f_path).unlink()


def test_security_audit_warnings() -> None:
    config = EfferoConfig()
    warnings = config.validate_security()
    assert any("server.api_key is not set" in w for w in warnings)

    # Secure server and TLS enabled
    config.server.api_key = "secret"
    config.iot.enabled = True
    config.iot.use_tls = False
    warnings = config.validate_security()
    assert not any("server.api_key is not set" in w for w in warnings)
    assert any("IoT MQTT is enabled without TLS" in w for w in warnings)
