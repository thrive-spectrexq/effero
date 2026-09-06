# Example: Local Smart Home

A fully offline, voice-controlled home-automation agent:

```
wake-word → faster-whisper (ASR) → local LLM (Ollama) → MQTT/Matter devices → Piper (TTS)
```

No cloud dependency required. See `effero.yaml` in this folder for the target config shape.

## Status

This example currently documents the **intended** config and wiring — the underlying
`effero run` command, the audio pipeline, and the MQTT/Matter adapter are not yet
implemented (see `ROADMAP` in the top-level README). It's included now so the shape of
a real deployment is concrete from the start, and so contributors building out
`perception/audio`, `adapters/mqtt_matter`, and `core/router` have a end-to-end target
to build toward.

## What it will do once implemented

1. Listen for the wake word ("hey effero") via an always-on local audio pipeline.
2. Transcribe the following utterance locally with `faster-whisper`.
3. Route the transcript to a local LLM (via Ollama) for intent + planning.
4. Call the relevant `iot.*` skill (e.g. `iot.lights.set_state`), which is checked
   against the safety policy in `src/effero/safety/policies/example.yaml` before
   it reaches the MQTT/Matter adapter.
5. Speak a confirmation back via Piper TTS.

## Try it today

Right now, you can exercise the parts that *are* implemented directly:

```python
from effero.sdk import skill, SafetyClass
from effero.core.agent import Agent

@skill(
    name="iot.lights.set_state",
    description="Turn a named light on or off.",
    safety_class=SafetyClass.ACT_AUTONOMOUS,
)
def set_light_state(light_id: str, on: bool) -> dict:
    # In a real deployment this calls into adapters.mqtt_matter.
    print(f"[demo] {light_id} -> {'ON' if on else 'OFF'}")
    return {"light_id": light_id, "on": on}

agent = Agent(name="home-and-desk-assistant")
print(agent.available_skills())
agent.invoke_skill("iot.lights.set_state", light_id="kitchen", on=True)
```
