# Effero

**One runtime for perceiving, reasoning, and acting — across computers, robots, and connected devices.**

*Latin: **effero** — "I carry out, I bring forth." From language to action.*

---

## What is Effero?

Effero is an open-source, modular runtime for building **agentic AI systems that operate in the physical and digital world** — not just chatbots that call APIs, but agents that *see*, *hear*, *speak*, *reason*, and *act*: driving a robot arm, flipping a smart switch, narrating what a camera sees, piloting a drone, or operating a desktop on your behalf.

It is designed from the ground up around three observations:

1. **Agent frameworks are excellent at software tool-calling but treat the physical world as an afterthought.** There's no first-class notion of a camera frame, a LiDAR scan, a servo limit, or an emergency stop.
2. **Robotics and IoT stacks are mature at device control but were never built around LLM-native reasoning, memory, or natural-language planning.**
3. **Safety guardrails built for text do not transfer to embodied action.** A model that refuses a harmful *sentence* will still happily execute a harmful *plan* unless there's a runtime layer checking actions against the physical world.

Effero sits in the middle: **one agent runtime, one skill/tool abstraction, one safety layer — many bodies.**

## Quick links

- [Quickstart](quickstart.md) — install and run your first agent in under 5 minutes
- [Architecture](architecture.md) — six-layer system design deep-dive
- [Skill Catalog](skills/catalog.md) — browse all available skills
- [Safety Model](safety/index.md) — how Effero keeps physical actions safe
- [Contributing](contributing.md) — how to add skills, adapters, and perception backends
- [GitHub Repository](https://github.com/thrive-spectrexq/effero)
