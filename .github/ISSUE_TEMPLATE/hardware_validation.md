---
name: Hardware validation report
about: Report real-world Effero testing results on physical boards, robots, or IoT gear
title: '[Hardware Validation] Device Name (OS / Board)'
labels: hardware-validation, documentation
assignees: ''
---

### Device Information
- **Hardware Platform / Model**: (e.g. Raspberry Pi 5 8GB, NVIDIA Jetson Orin Nano, Orange Pi 5 Plus, x86 N100 Mini-PC)
- **CPU / SoC**: (e.g. Broadcom BCM2712 Cortex-A76, NVIDIA Orin 6-core ARM Cortex-A78AE)
- **RAM**: (e.g. 4 GB, 8 GB, 16 GB)
- **OS & Kernel**: (e.g. Raspberry Pi OS Bookworm 64-bit, Ubuntu 24.04 LTS, JetPack 6.0)
- **Accelerator / NPU / GPU**: (e.g. Raspberry Pi AI HAT Hailo-8L, Jetson Ampere GPU, None / CPU-only)

### Effero Installation
- **Effero Version / Git Commit**: (e.g. effero 0.1.8)
- **Python Version**: (e.g. 3.11.8, 3.12.3, 3.13.0)
- **Installed Extras**: (e.g. effero[iot,voice], effero[litert])

### Measured Metrics
- **Cold Start Time**: (Time from running effero run or effero serve until first skill is ready, in seconds)
- **Idle RAM Consumption**: (Resident Set Size from htop / psutil when idle, e.g. ~75 MB)
- **CPU Load at Idle**: (e.g. < 1%)

### Tested Subsystems
Check the subsystems tested during this validation run:
- [ ] Core Planner (effero run CLI REPL)
- [ ] Safety Kernel Daemon (effero-safety-kerneld Rust process)
- [ ] Local REST / WebSocket Server (effero serve)
- [ ] MQTT / Matter Adapter (effero.adapters.mqtt_matter)
- [ ] Serial Sensor Streaming (effero.adapters.serial)
- [ ] Native Desktop Automation (effero.skills.computer_use.desktop)
- [ ] Browser Automation (effero.skills.computer_use.browser)
- [ ] LiteRT-LM Edge Model Inference
- [ ] Audio Pipeline (Microphone ASR / Speaker TTS)
- [ ] Camera Vision Pipeline

### Test Summary & Findings
What worked smoothly? Were there any bottlenecks, missing system libraries, or permission issues encountered?

``
paste test logs or benchmark output here
``

### Pull Request Link (Optional)
If you have also submitted a PR updating docs/compatibility.md, please link it here:
