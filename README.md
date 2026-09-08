<div align="center">

# Effero

**One runtime for perceiving, reasoning, and acting — across computers, robots, and connected devices.**

*Latin: **effero** — "I carry out, I bring forth." From language to action.*

[![License: Apache 2.0](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue)](https://www.python.org/)
[![CI](https://github.com/thrive-spectrexq/effero/actions/workflows/ci.yml/badge.svg)](https://github.com/thrive-spectrexq/effero/actions/workflows/ci.yml)
[![codecov](https://codecov.io/gh/thrive-spectrexq/effero/graph/badge.svg)](https://codecov.io/gh/thrive-spectrexq/effero)
[![PyPI version](https://img.shields.io/pypi/v/effero)](https://pypi.org/project/effero/)
[![PyPI downloads](https://img.shields.io/pypi/dm/effero)](https://pypi.org/project/effero/)
[![MCP Native](https://img.shields.io/badge/protocol-MCP%20%2B%20A2A-6E56CF)](https://modelcontextprotocol.io)
[![Status: Alpha](https://img.shields.io/badge/status-alpha-orange)]()
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](CONTRIBUTING.md)

[Why Effero](#why-effero) • [Architecture](#architecture) • [Quickstart](#quickstart) • [Skills](#skills--the-device-abstraction-layer) • [Safety](#safety--governance) • [Contributing](#contributing)

</div>

---

## What is Effero?

Effero is an open-source, modular runtime for building **agentic AI systems that operate in the physical and digital world** — not just chatbots that call APIs, but agents that *see*, *hear*, *speak*, *reason*, and *act*: driving a robot arm, flipping a smart switch, narrating what a camera sees, piloting a drone, or operating a desktop on your behalf.

It is designed from the ground up around three observations from the current state of the field:

1. **Agent frameworks (LangGraph, CrewAI, AutoGen, OpenAI/Google Agent SDKs) are excellent at software tool-calling but treat the physical world as an afterthought.** There's no first-class notion of a camera frame, a LiDAR scan, a servo limit, or an emergency stop.
2. **Robotics and IoT stacks (ROS 2, Home Assistant, Matter/Thread, MQTT) are mature at *device control* but were never built around LLM-native reasoning, memory, or natural-language planning.**
3. **Safety guardrails built for text ("don't say harmful things") do not transfer to embodied action ("don't do harmful things").** Research on LLM-controlled robots has repeatedly shown that a model that refuses a harmful *sentence* will still happily execute a harmful *plan* unless there's a runtime layer, independent of the model, checking actions against the physical world before they execute.

Effero's job is to sit in the middle: **one agent runtime, one skill/tool abstraction, one safety layer — many bodies.** The same agent that debugs your code over chat can, with the right skills installed, water your plants, greet a visitor at the door, or guide a manipulator arm through a pick-and-place task — through the same planner, the same memory, and the same guardrail engine.

---

## Why Effero

Effero doesn't try to replace ROS 2, Home Assistant, or your favorite agent SDK — it **speaks their protocols** and gives you one coherent reasoning layer on top of all of them.

---

## Core Principles

1. **Protocol-native, not protocol-adjacent.** [MCP](https://modelcontextprotocol.io) is how skills are exposed, and [A2A](https://a2aproject.github.io/A2A/) is how agents talk to each other. These aren't plugins bolted onto a proprietary tool format — they *are* the tool format.
2. **Everything is a Skill.** A robot joint, a smart plug, a shell command, a browser click, and a REST API call are all exposed through the same `Skill` interface: a name, an input schema, a safety class, and an execution scope. The planner never needs to know *how* a skill is implemented.
3. **Modality-agnostic perception.** Speech, vision, and sensor telemetry are pluggable pipelines with a common event bus. Swap Whisper for Moonshine, or a cloud vision API for a local YOLO model, without touching agent logic.
4. **Local-first, cloud-optional.** Effero runs end-to-end on a Raspberry Pi / Jetson / mini-PC with local models (llama.cpp, Ollama, faster-whisper, Piper) and no internet connection. Cloud LLMs and APIs are opt-in accelerants, not requirements. See the [Hardware Compatibility](docs/compatibility.md) table for tested platforms.
5. **Safety is architecture, not a system prompt.** A runtime guardrail engine — independent of the LLM — grounds every proposed action against the robot/device's actual state and a declarative policy before it is allowed to execute.
6. **Bring your own model.** LLM, ASR, TTS, and vision backends are all adapters behind stable interfaces, matched to your hardware budget: from a 27 MB edge speech model to a frontier cloud LLM.
7. **Polyglot by design, not by default.** Everything defaults to Python — that's where the ecosystem and the contributors are. Rust shows up only where the architecture specifically calls for it: the safety kernel (an independently-auditable, LLM-free guardrail process) and constrained-device MCP servers (`crates/`) that a Python runtime can't run on. It's never a blanket rewrite of the core.

---

## Architecture

Effero is organized in six layers. Data flows up from perception, through cognition, back down through skills into the physical/digital world — with the safety layer able to intercept at every boundary.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                             INTERFACES                                      │
│   CLI / SDK          Chat & Web Dashboard       Voice Loop       Mobile     │
└──────────┬──────────────────┬──────────────────────┬──────────────┬─────────┘
           │                  │                      │              │
           ▼                  ▼                      ▼              ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                          PERCEPTION BUS                                     │
│                                                                             │
│  ┌──────────────────┐  ┌──────────────────┐  ┌────────────────────────┐     │
│  │  Vision Pipeline │  │  Audio Pipeline  │  │     Sensor Fusion      │     │
│  │  detection · seg │  │  wake-word · VAD │  │  IMU · LiDAR · telem   │     │
│  │  VLA · OCR       │  │  ASR · TTS       │  │  odometry · env        │     │
│  └──────────────────┘  └──────────────────┘  └────────────────────────┘     │
└──────────────────────────────┬──────────────────────────────────────────────┘
                               │ events
                               ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                    COGNITION CORE  (Effero Runtime)                         │
│                                                                             │
│  ┌────────────────────┐  ┌──────────────┐  ┌────────────────────────────┐   │
│  │   Orchestrator /   │  │    Memory    │  │       Model Router         │   │
│  │      Planner       │  │              │  │                            │   │
│  │  plan → act →      │  │  working     │  │  local llama.cpp / Ollama  │   │
│  │  observe → replan  │  │  episodic    │  │         ⇅                  │   │
│  │                    │  │  semantic    │  │  cloud  OpenAI / Anthropic │   │
│  └────────────────────┘  └──────────────┘  │         / Google           │   │
│                                            └────────────────────────────┘   │
│                               ◄── A2A ──►                                   │
└──────────────────────────────┬──────────────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                      SKILL LAYER  (MCP-native)                              │
│                                                                             │
│  ┌──────────┐  ┌──────────┐  ┌──────────────┐  ┌────────────────────────┐   │
│  │ Robotics │  │   IoT    │  │ Computer Use │  │  Custom / Community    │   │
│  │  Skills  │  │  Skills  │  │    Skills    │  │       Skills           │   │
│  └──────────┘  └──────────┘  └──────────────┘  └────────────────────────┘   │
│                        ▲  Skill Registry  ▲                                 │
└────────────────────────┼──────────────────┼─────────────────────────────────┘
                         │                  │
      ┌──────────────────┘                  └──────────────────┐
      ▼                                                        ▼
┌───────────────────────────────────────┐  ┌──────────────────────────────────┐
│      DEVICE ABSTRACTION LAYER         │  │      SAFETY & GOVERNANCE         │
│                                       │  │                                  │
│  ROS 2 Adapter                        │  │  Runtime Guardrail Engine        │
│  MQTT / Matter / Zigbee / Thread      │◄─┤  (policy-as-code, Rust kernel)   │
│  Serial / GPIO / Arduino / ESP32      │  │                                  │
│  Generic REST / Cloud APIs            │  │  Human-in-the-loop Approval      │
│  OS Control (files · browser · input) │  │  Hardware E-Stop Hook            │
│                                       │  │  Audit Log                       │
└───────────────────────────────────────┘  └──────────────────────────────────┘
```

### Layer breakdown

**1. Interfaces** — CLI (`effero`), a chat/web dashboard, a voice wake-word loop, and a thin mobile client. All talk to the same runtime over a local gRPC/WebSocket API.

**2. Perception Bus** — Independent, always-on pipelines that publish structured events (`ObjectDetected`, `Utterance`, `SensorReading`) onto a shared bus. The planner subscribes to what it needs instead of polling hardware directly.

**3. Cognition Core** — The actual "brain": a graph-based orchestrator (plan → act → observe → replan), a three-tier memory (working context, episodic transcript, semantic vector recall), and a **model router** that lets every LLM call declare its needs (latency, tool-calling reliability, multimodality) and get routed to a local or cloud backend accordingly.

**4. Skill Layer** — Every capability the agent can invoke — moving a servo, toggling a light, reading a file, clicking a browser element — is registered as an MCP tool with a declared **safety class** (see [Safety](#safety--governance)). This is also the layer where the community contributes: a new skill is a new MCP server, full stop.

**5. Device Abstraction Layer (DAL)** — Where skills actually touch hardware: a ROS 2 bridge for robots, an MQTT/Matter/Zigbee/Thread bridge for IoT, a serial/GPIO bridge for microcontrollers (Arduino, ESP32), a generic REST adapter for cloud-connected appliances, and an OS-control adapter for desktop/browser automation.

**6. Safety & Governance** — A runtime guardrail engine that sits *between* the skill layer and the DAL, independent of the LLM, checking every proposed action against declarative policy and the device's live state before it's allowed to reach hardware.

---

## Repository Layout

The Python core lives under `src/effero/` (a standard `src`-layout
package, so the repo root and the importable package don't collide);
`crates/` holds the two Rust components described under Core Principles
above.

```
effero/
├── src/effero/
│   ├── core/                  # Orchestrator, planner, memory, model router
│   │   ├── agent/             #   plan/act/observe loop, task graph
│   │   ├── memory/            #   working, episodic, semantic (vector) memory
│   │   ├── planner/           #   task decomposition, replanning
│   │   └── router/            #   LLM backend routing & fallback
│   ├── perception/
│   │   ├── vision/            #   detection, segmentation, VLA, OCR adapters
│   │   ├── audio/              #   wake-word, VAD, ASR, TTS adapters
│   │   └── sensors/            #   IMU, LiDAR, generic telemetry fusion
│   ├── skills/                 # MCP-native skill definitions
│   │   ├── robotics/
│   │   ├── iot/
│   │   ├── computer_use/
│   │   └── community/
│   ├── adapters/                # Device Abstraction Layer
│   │   ├── ros2/
│   │   ├── mqtt_matter/
│   │   ├── serial_gpio/
│   │   └── cloud_api/
│   ├── safety/                   # Guardrail types, policy examples (Python side)
│   ├── protocols/                # MCP server/client, A2A, Wyoming voice protocol
│   ├── interfaces/                # CLI, web dashboard, mobile shell, voice loop
│   └── sdk/                       # The @skill decorator and skill registry
├── crates/                        # Rust: safety kernel + edge-device MCP server
│   ├── effero-safety-kernel/      #   the independent, LLM-free guardrail engine
│   └── effero-edge-mcp/           #   MCP server template for constrained devices
├── examples/                      # Reference builds (see below)
├── docs/
└── tests/
```

---

## Quickstart

> Effero targets Python 3.11+ and runs on Linux, macOS, Windows (WSL2), and edge boards (Raspberry Pi 5, Jetson Orin).

```bash
# 1. Install
pip install effero

# 2. Scaffold a new project
effero init my-agent
cd my-agent

# 3. Point it at a model (local by default)
effero config set model.backend ollama --model qwen3:8b
# or, to use a cloud model instead:
# effero config set model.backend anthropic --model claude-sonnet-5

# 4. Run it
effero run
```

### Minimal agent definition

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
  - iot.lights           # via MQTT/Matter
  - iot.thermostat
  - robotics.arm_pick_place   # via ROS 2
  - computer_use.browser

safety:
  policy: safety/policies/home.yaml
  require_approval_for: [robotics.*, computer_use.file_delete]
```

### Defining a custom skill (Python SDK)

```python
from effero.sdk import skill, SafetyClass

@skill(
    name="iot.thermostat.set_temperature",
    description="Set the target temperature of a named thermostat.",
    safety_class=SafetyClass.ACT_AUTONOMOUS,  # no approval needed
)
def set_temperature(thermostat_id: str, celsius: float) -> dict:
    device = mqtt_matter.get_device(thermostat_id)
    device.set_attribute("target_temperature", celsius)
    return {"status": "ok", "device": thermostat_id, "target_temperature": celsius}
```

Because this is registered as an MCP tool under the hood, it is immediately callable by Effero's own planner *and* by any other MCP-compatible client (Claude, an IDE agent, etc.) — no extra glue code.

### Connecting a robot over ROS 2

```python
from effero.adapters.ros2 import ROS2Bridge

bridge = ROS2Bridge(node_name="effero_bridge")
bridge.expose_action("/arm/pick_place", skill_name="robotics.arm_pick_place")
bridge.expose_topic("/scan", event_name="lidar.scan")  # feeds the perception bus
bridge.spin()
```

---

## Perception: Pluggable Backends

Effero ships adapters for today's strongest open building blocks and lets you swap any of them per deployment:

| Modality | Edge / low-power | Balanced | High-accuracy / cloud |
|---|---|---|---|
| **ASR (speech-to-text)** | Moonshine (down to ~27 MB) | faster-whisper (CTranslate2 Whisper, ~4x realtime) | NVIDIA Canary-Qwen, Parakeet-TDT, cloud APIs |
| **TTS (text-to-speech)** | Piper (on-device, Wyoming-compatible) | Piper (higher-quality voices) | Cloud neural TTS |
| **Wake-word** | openWakeWord / microWakeWord | — | — |
| **Vision – detection** | YOLO-family (ONNX/TensorRT) | YOLO-family + tracking | Cloud vision APIs |
| **Vision – grounding** | CLIP/SigLIP (quantized) | CLIP/SigLIP | Frontier multimodal LLM |
| **Embodied action (VLA)** | SmolVLA | OpenVLA / Octo | GR00T-class foundation policies |
| **LLM reasoning** | small local model via llama.cpp/Ollama | mid-size local model | Frontier cloud LLM |

Speech pipelines speak the **Wyoming protocol**, the same lightweight streaming standard used by Home Assistant's local voice stack, so Effero can plug directly into an existing Wyoming satellite/microphone setup instead of reinventing audio transport.

---

## Skills & the Device Abstraction Layer

A **Skill** is Effero's only unit of capability. Every skill declares:

- an **MCP tool schema** (name, typed inputs/outputs, description the planner reasons over),
- a **safety class** — `READ_ONLY`, `ACT_AUTONOMOUS`, `ACT_WITH_APPROVAL`, or `ACT_RESTRICTED` (simulation-only until explicitly promoted),
- and an **adapter binding** — which piece of the Device Abstraction Layer actually carries it out.

| Domain | Example skills | Adapter |
|---|---|---|
| Robotics | navigate, pick_place, follow_person, e_stop | ROS 2 |
| Smart home / IoT | lights, thermostat, locks, sensors | MQTT · Matter · Zigbee · Thread |
| Microcontrollers | read_sensor, set_pin, drive_motor | Serial / GPIO / Arduino / ESP32 |
| Computer use | open_app, click, type, read_screen, run_shell | OS-level adapter |
| Cloud / web | call_api, send_email, query_database | Generic REST adapter |

Multiple robots or Effero instances coordinate over **A2A** (Agent-to-Agent protocol), so a fleet of agents — a mobile robot, a stationary arm, and a home-automation instance — can negotiate and delegate subtasks instead of each acting blindly.

---

## Safety & Governance

Text-alignment guardrails do not protect against unsafe *physical* actions — a model that refuses to describe something harmful in words has been repeatedly shown to still execute an unsafe robot plan unless something *outside the model* stops it. Effero's guardrail engine is built around that finding:

- **Policy-as-code**: declarative rules ("never exceed 0.5 m/s within 1 m of a person", "never unlock an exterior door between 11pm–6am without approval") are grounded against the *live* world model at runtime, not just the prompt.
- **Independent runtime check**: every action from the skill layer is validated against policy and current device/robot state *before* it reaches the Device Abstraction Layer — this check does not go through the LLM and cannot be prompt-injected away.
- **Human-in-the-loop approval**: skills marked `ACT_WITH_APPROVAL` pause for explicit confirmation (CLI, chat, or push notification) before executing.
- **Simulation-first promotion**: new or community-contributed skills default to `ACT_RESTRICTED` (dry-run/simulated) until a maintainer or operator promotes them.
- **Hardware e-stop hook**: a dedicated, LLM-independent kill switch that adapters must implement — pulling it halts actuation regardless of what the agent is "thinking."
- **Full audit log**: every plan, tool call, guardrail decision, and approval is logged for post-hoc review.

This mirrors the direction of current robot-safety research: **safety guarantees need to live at the level of grounded, verifiable actions — not at the level of text.**

**Status:** the independent runtime check above is implemented as [`crates/effero-safety-kernel`](crates/effero-safety-kernel/) — a small, dependency-minimal Rust process (deliberately *not* embedded in the Python runtime, for the reason stated above) that loads a declarative policy and serves allow/require-approval/deny/limit decisions over a local Unix socket. It's built, unit-tested, and wired into `src/effero/safety/` with full end-to-end client verification.

---

## Example Builds (`examples/`)

- **`local-smart-home/`** ✅ — voice-controlled home automation: wake-word → ASR → LLM → Matter/MQTT devices → TTS. Runs as an interactive REPL.
- **`desktop-copilot/`** ✅ — a computer-use agent that operates shell, files, and browser on the user's behalf, gated behind `ACT_WITH_APPROVAL` for destructive actions.
- **`mobile-manipulator/`** *(planned)* — natural-language task planning over a ROS 2-connected mobile robot with a VLA-driven manipulation skill for pick-and-place.
- **`industrial-monitor/`** *(planned)* — sensor-fusion anomaly detection across a fleet of IoT sensors, with agentic triage and human-approved actuation.
- **`multi-robot-swarm/`** *(planned)* — two or more Effero instances coordinating over A2A to split a shared task.

---

## Contributing


Effero is community-built from day one. Good places to start:

- **New skills** are the easiest contribution — a skill is a small, testable MCP server. See `sdk/` and `CONTRIBUTING.md`.
- **New adapters** (a new IoT protocol, a new robot middleware, a new microcontroller board) live in `adapters/`.
- **New perception backends** (an ASR/TTS/vision model you want supported) live in `perception/`.
- Please read `CODE_OF_CONDUCT.md` before opening issues or PRs. Look for issues tagged `good-first-issue`.

## License

Released under the **Apache License 2.0** (see `LICENSE`) — chosen deliberately over MIT for its explicit patent grant, which matters for a framework that touches physical hardware. Feel free to revisit this choice for your own fork if your governance needs differ.

## Acknowledgments

Effero interoperates with, and draws design lessons from, a number of independent open ecosystems it is **not affiliated with**: the [Model Context Protocol](https://modelcontextprotocol.io) and A2A protocol for agent/tool interoperability, [ROS 2](https://www.ros.org/) for robotics middleware, [Home Assistant](https://www.home-assistant.io/) and the Wyoming protocol for local-first voice and smart-home patterns, the open Vision-Language-Action research line (OpenVLA, Octo, and related generalist robot policies), and the broader open ASR/TTS ecosystem (Whisper and its faster-whisper/Moonshine/Parakeet derivatives, Piper). Effero exists to connect these worlds, not replace them.

---

<div align="center">

*Effero is an independent open-source project. Contributions, forks, and disagreement with the design choices above are all welcome — open an issue.*

</div>
