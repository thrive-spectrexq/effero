"""Tests for EfferoConfig.from_env() behavior using real files and real environment variables."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

from effero.config import EfferoConfig


def test_from_env_openai_key() -> None:
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        f.write("agent:\n  model:\n    backend: openai\n")
        f_path = f.name

    old_key = os.environ.get("OPENAI_API_KEY")
    try:
        os.environ["OPENAI_API_KEY"] = "sk-live-test-key-openai"
        config = EfferoConfig.from_env(f_path)
        assert config.agent.model.backend == "openai"
        assert config.agent.model.api_key == "sk-live-test-key-openai"
    finally:
        if old_key is None:
            os.environ.pop("OPENAI_API_KEY", None)
        else:
            os.environ["OPENAI_API_KEY"] = old_key
        Path(f_path).unlink()


def test_from_env_anthropic_key_not_clobbered() -> None:
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        f.write("agent:\n  model:\n    backend: anthropic\n")
        f_path = f.name

    old_openai = os.environ.get("OPENAI_API_KEY")
    old_anthropic = os.environ.get("ANTHROPIC_API_KEY")
    try:
        os.environ["OPENAI_API_KEY"] = "sk-openai-clobber-attempt"
        os.environ["ANTHROPIC_API_KEY"] = "sk-anthropic-real-key"
        config = EfferoConfig.from_env(f_path)
        assert config.agent.model.backend == "anthropic"
        # Must select anthropic key, not openai key
        assert config.agent.model.api_key == "sk-anthropic-real-key"
    finally:
        if old_openai is None:
            os.environ.pop("OPENAI_API_KEY", None)
        else:
            os.environ["OPENAI_API_KEY"] = old_openai
        if old_anthropic is None:
            os.environ.pop("ANTHROPIC_API_KEY", None)
        else:
            os.environ["ANTHROPIC_API_KEY"] = old_anthropic
        Path(f_path).unlink()


def test_from_env_google_key() -> None:
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        f.write("agent:\n  model:\n    backend: google\n")
        f_path = f.name

    old_google = os.environ.get("GOOGLE_API_KEY")
    try:
        os.environ["GOOGLE_API_KEY"] = "sk-google-gemini-key"
        config = EfferoConfig.from_env(f_path)
        assert config.agent.model.backend == "google"
        assert config.agent.model.api_key == "sk-google-gemini-key"
    finally:
        if old_google is None:
            os.environ.pop("GOOGLE_API_KEY", None)
        else:
            os.environ["GOOGLE_API_KEY"] = old_google
        Path(f_path).unlink()


def test_fleet_config_defaults() -> None:
    config = EfferoConfig()
    assert config.fleet.enabled is False
    assert config.fleet.default_lease_duration == 30.0
