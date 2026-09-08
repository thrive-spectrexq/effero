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
