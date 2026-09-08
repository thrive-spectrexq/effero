# Configuration

Effero is configured via an `effero.yaml` file in your project root.

## Top-level structure

```yaml
agent:
  name: my-agent
  model:
    backend: ollama          # ollama | openai | anthropic | google
    model: qwen3:8b
    fallback: []             # ordered list of fallback backends

perception:
  audio:
    wake_word: "hey effero"
    asr: faster-whisper:small.en
    tts: piper:en_US-amy-medium
  vision:
    enabled: false
    backend: yolov9

skills:
  - iot.lights
  - iot.thermostat
  - computer_use.shell

safety:
  policy: safety/policies/home.yaml
  require_approval_for: []
```

## CLI configuration

You can modify config from the terminal without editing YAML manually:

```bash
effero config set model.backend ollama --model qwen3:8b
effero config get model.backend
```

## Environment variables

API keys for cloud LLM backends are loaded from environment variables:

| Variable | Backend |
|---|---|
| `OPENAI_API_KEY` | OpenAI |
| `ANTHROPIC_API_KEY` | Anthropic (Claude) |
| `GOOGLE_API_KEY` | Google (Gemini) |

## Optional extras

Effero's `pip install effero` is deliberately lightweight. Enable additional capabilities with extras:

```bash
pip install effero[voice]    # ASR/TTS (faster-whisper, piper-tts)
pip install effero[vision]   # Detection (ultralytics/YOLO)
pip install effero[iot]      # MQTT/Matter protocols
pip install effero[llm]      # Cloud LLM SDKs (OpenAI, Anthropic, Google)
pip install effero[all]      # Everything above
```
