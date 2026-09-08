# Effero Technical Architecture Deep-Dive

Effero is an open-source, production-grade agent runtime designed for physical and digital agency. It provides unified orchestration across local computers, robotics hardware, and IoT devices.

---

## 1. Six-Layer Subsystem Architecture

The Effero runtime is structured into six strictly separated, modular layers:

```
┌────────────────────────────────────────────────────────┐
│                   Layer 6: Interfaces                  │
│       CLI (REPL / Chat) · FastAPI REST · WebSockets    │
└───────────────────────────┬────────────────────────────┘
                            │
┌───────────────────────────▼────────────────────────────┐
│                    Layer 5: Protocols                  │
│         MCP (Stdio) · Wyoming Voice · A2A Mesh         │
└───────────────────────────┬────────────────────────────┘
                            │
┌───────────────────────────▼────────────────────────────┐
│                 Layer 4: Agent Core Engine             │
│   Planner Loop · Memory (Working/Episodic/Semantic)    │
│            Model Router · Fleet Coordinator            │
└─────────────┬───────────────────────────┬──────────────┘
              │                           │
┌─────────────▼───────────────┐ ┌─────────▼──────────────┐
│  Layer 3: Safety & Defense  │ │   Layer 2: Perception  │
│ Rust Policy Kernel (TCP RPC)│ │ Audio (ASR/TTS/VAD)    │
│  Human-in-the-Loop Approval │ │ Vision (YOLO/ONNX VLA) │
│       Bounds Clamping       │ │ Sensors (Hardware/Sys) │
└─────────────┬───────────────┘ └─────────┬──────────────┘
              │                           │
┌─────────────▼───────────────────────────▼──────────────┐
│             Layer 1: Skills & Hardware Adapters        │
│  Computer Use (OS / Playwright) · Robotics Kinematics  │
│  Serial / Dynamixel / Modbus · ROS 2 CDR · MQTT/Matter │
└────────────────────────────────────────────────────────┘
```

---

## 2. Core Execution Engine: The Planner Loop

The central reasoning engine is implemented in `effero.core.planner.Planner`:
- **System Grounding**: Injects a unified prompt anchoring the agent's digital and physical actions.
- **Dynamic Schema Synthesis**: Generates OpenAI-compliant tool schemas at runtime directly from registered skills in `SkillRegistry`.
- **Iterative Reasoning Loop**: Evaluates user input against the prioritized fallback chain in `ModelRouter` (supporting local Ollama, cloud OpenAI, Anthropic Claude, and Google Gemini).
- **Safety Interception**: Before dispatching any tool call, the action is verified with the Rust Safety Kernel (`effero-safety-kernel`) and routed through `ApprovalHandler` if classified as `ACT_WITH_APPROVAL`.
- **Context Preservation**: Execution observations are appended to `WorkingMemory` while session histories are persisted to append-only JSONL files via `EpisodicMemory`.

---

## 3. Tiered Memory Hierarchy

1. **Working Memory (`effero.core.memory.working`)**:
   - In-memory sliding window message buffer.
   - Retains system instructions while truncating older dialogue turns to preserve LLM token context limits.
2. **Episodic Memory (`effero.core.memory.episodic`)**:
   - Disk-persisted append-only interaction log (`sessions/session_<timestamp>.jsonl`).
   - Stores timestamps, roles, raw model responses, and tool call traces for replay and post-hoc auditing.
3. **Semantic Memory (`effero.core.memory.semantic`)**:
   - Zero-dependency local TF-IDF vector recall engine with subword trigram hashing and cosine similarity.
   - Provides instant semantic retrieval of long-term preferences, user habits, and device states without external vector databases.

---

## 4. Hardware Safety & Policy Guardrails

Effero incorporates defense-in-depth for physical safety:
- **Rust Safety Kernel (`crates/effero-safety-kernel`)**: A deterministic engine evaluating mathematical and boolean conditions (`time.hour >= 23`, `distance < 1.0m`, `speed > limit`) over high-throughput TCP RPC (`127.0.0.1:9400`).
- **Safety Classifications (`effero.sdk.SafetyClass`)**:
  - `READ_ONLY`: Passive telemetry and sensing. Autonomous execution allowed.
  - `ACT_AUTONOMOUS`: Idempotent, low-risk local actions (e.g. homing joints, stopping motors).
  - `ACT_WITH_APPROVAL`: High-risk or physical actions requiring operator authorization.
  - `ACT_RESTRICTED`: High-consequence actions strictly gated by safety policies.
- **OS Destructive Filter**: Native Windows automation (`desktop.py`) intercepts dangerous hotkey combinations (e.g. `Alt+F4`, `Ctrl+Alt+Del`) and enforces cursor bounding limits.

---

## 5. Protocols & Distributed Fleet Coordination

- **MCP Protocol (`effero.protocols.mcp_server`)**: Standard Model Context Protocol implementation over stdio, exposing Effero skills as tools to external agents (Claude Desktop, IDE agents).
- **Wyoming Voice (`effero.protocols.wyoming`)**: Wire-compatible with Home Assistant voice satellites for local wake-word, binary PCM audio streaming, speech-to-text, and text-to-speech synthesis.
- **A2A Mesh Protocol (`effero.protocols.a2a`)**: Agent-to-Agent REST API for multi-agent capability discovery (`AgentCard`) and remote task delegation (`TaskMessage`).
- **Fleet Consensus (`effero.core.fleet`)**: Decentralized multi-node task bidding via sealed-bid commit-reveal auctions (`SealedBidAuction`) and lease renewals (`TaskLease`).
