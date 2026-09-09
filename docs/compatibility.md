# Hardware Compatibility

Effero is designed to run on hardware ranging from a Raspberry Pi to a
rack-mounted server. This table tracks what has been tested.

> **Help wanted**: if you run Effero on hardware not listed here, please
> open a PR adding your measurements.

## Tested Platforms

| Device | CPU | RAM | OS | Effero Version | Status | Cold Start | Idle RAM | Notes |
|---|---|---|---|---|---|---|---|---|
| x86-64 desktop | i7-12700 | 32 GB | Ubuntu 24.04 | 0.1.4 | ✅ Tested | — | — | Primary development target |
| *Raspberry Pi 5* | *Cortex-A76* | *8 GB* | *Bookworm* | — | 🔲 Untested | — | — | *Target platform, needs validation* |
| *Jetson Orin Nano* | *Cortex-A78AE* | *8 GB* | *JetPack 6* | — | 🔲 Untested | — | — | *GPU acceleration for vision/VLA* |
| *Generic x86 mini-PC* | *N100* | *16 GB* | *Ubuntu 24.04* | — | 🔲 Untested | — | — | *Budget always-on home server* |

## What we measure

- **Cold Start**: Time from `effero run` to first skill invocation ready (no model loading).
- **Idle RAM**: Resident set size with the agent running, no active skills, no model loaded.
- **Model loading**: Separate — depends entirely on the model backend (Ollama, llama.cpp, cloud).

## Minimum requirements (estimated)

- Python 3.11+
- 512 MB RAM (core runtime only, no models)
- ARM64 or x86-64
- Linux, macOS, or Windows (WSL2)

## On-Device Inference Engine (Cactus) Footprint

When using Effero with on-device LLM inference via the [Cactus](https://github.com/cactus-compute/cactus) runtime (`backend: cactus`), quantized models run locally with sub-100ms first-token latencies:

| Model Architecture | Quantization | RAM Footprint | Device Target | Latency (First Token) |
|---|---|---|---|---|
| 1B-3B Edge SLM | INT4 | ~1.2 GB - 2.1 GB | Raspberry Pi 5 / Mobile / Jetson Nano | < 60 ms |
| 7B-8B Compact LM | INT4 | ~4.2 GB - 4.8 GB | Jetson Orin Nano / N100 Mini-PC | < 120 ms |
| 7B-8B Compact LM | INT8 | ~7.8 GB - 8.5 GB | x86 Desktop / Jetson AGX | < 90 ms |

### Confidence-Based Hybrid Cloud Handoff

Effero supports hybrid routing with Cactus:
1. The on-device SLM produces local reasoning and an action plan with an evaluated confidence score.
2. If confidence meets or exceeds `model.min_confidence` (default `0.70`), the action is dispatched locally with zero external API latency or cost.
3. If the model encounters ambiguity or confidence falls below the threshold, Effero automatically escalates the context to the configured cloud fallback backend (e.g. `openai:gpt-4o`, `anthropic:claude-sonnet-4-5`).

## Google AI Edge LiteRT-LM (In-Process NPU & Edge Engine)

For single-board computers (Raspberry Pi 5 with AI HAT), robotics controllers, and edge Linux boards, Effero supports [Google LiteRT-LM](https://github.com/google-ai-edge/LiteRT-LM) (`backend: litert`).

Unlike background HTTP server daemons, LiteRT-LM runs **in-process** via native Python bindings, directly accessing device NPUs and GPUs:

| Hardware Target | Accelerator Backend | Model Format | Recommended SLM |
|---|---|---|---|
| Raspberry Pi 5 + AI HAT | NPU / Hailo-8 / Coral | `.litertlm` | Gemma 3 1B / SmolLM 1.7B |
| Jetson Orin Nano / AGX | GPU (Vulkan/OpenCL) | `.litertlm` | Gemma 3 4B / Qwen 2.5 7B |
| Android Robotics Tablets | NNAPI / Hexagon NPU | `.litertlm` | Gemma 3 1B / MobileLM |
| Standard Edge x86/ARM | Multi-threaded CPU | `.litertlm` | Compact SLMs |


