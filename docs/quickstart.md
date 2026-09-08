# Quickstart

> Effero targets Python 3.11+ and runs on Linux, macOS, Windows (WSL2), and edge boards (Raspberry Pi 5, Jetson Orin).

## Install

```bash
pip install effero
```

For development:

```bash
git clone https://github.com/thrive-spectrexq/effero.git
cd effero
python -m venv .venv
source .venv/bin/activate      # .venv\Scripts\activate on Windows
pip install -e ".[dev]"
```

## Scaffold a new project

```bash
effero init my-agent
cd my-agent
```

## Point it at a model

```bash
# Local (default)
effero config set model.backend ollama --model qwen3:8b

# Or use a cloud model
effero config set model.backend anthropic --model claude-sonnet-5
```

## Run it

```bash
effero run
```

## Minimal agent definition

```yaml
# effero.yaml
agent:
  name: home-and-desk-assistant
  model:
    backend: ollama
    model: qwen3:8b
    fallback: [anthropic:claude-sonnet-5]

perception:
  audio:
    wake_word: "hey effero"
    asr: faster-whisper:small.en
    tts: piper:en_US-amy-medium
  vision:
    enabled: true
    backend: yolov9

skills:
  - iot.lights
  - iot.thermostat
  - robotics.arm_pick_place
  - computer_use.browser

safety:
  policy: safety/policies/home.yaml
  require_approval_for: [robotics.*, computer_use.file_delete]
```

## Define a custom skill

```python
from effero.sdk import skill, SafetyClass

@skill(
    name="iot.thermostat.set_temperature",
    description="Set the target temperature of a named thermostat.",
    safety_class=SafetyClass.ACT_AUTONOMOUS,
)
def set_temperature(thermostat_id: str, celsius: float) -> dict:
    device = mqtt_matter.get_device(thermostat_id)
    device.set_attribute("target_temperature", celsius)
    return {"status": "ok", "device": thermostat_id, "target_temperature": celsius}
```

Because this is registered as an MCP tool under the hood, it is immediately callable by Effero's own planner *and* by any other MCP-compatible client.

## Next steps

- Browse the [Skill Catalog](skills/catalog.md) to see what's available
- Read [Writing a Skill](skills/writing-a-skill.md) to contribute your own
- Understand the [Safety Model](safety/index.md) before deploying to hardware
