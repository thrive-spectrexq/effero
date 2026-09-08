# Skills Overview

A **Skill** is Effero's atomic unit of capability. Every skill declares:

- An **MCP tool schema** — name, typed inputs/outputs, and a description the planner reasons over.
- A **safety class** — how much autonomy this skill is trusted with.
- An **adapter binding** — which piece of the Device Abstraction Layer carries it out.

## Safety classes

Every skill must declare one of four safety levels:

| Safety Class | Behavior | Example |
|---|---|---|
| `READ_ONLY` | Cannot change external state. Runs autonomously. | `get_temperature`, `take_screenshot` |
| `ACT_AUTONOMOUS` | May act without human approval. | `lights.turn_off`, `emergency_stop` |
| `ACT_WITH_APPROVAL` | Pauses for human confirmation before executing. | `arm.move_joints`, `shell.execute` |
| `ACT_RESTRICTED` | Simulation/dry-run only until explicitly promoted. | New community skills |

!!! warning "Default is safe"
    If you omit `safety_class` in a `@skill(...)` decorator, it defaults to `ACT_WITH_APPROVAL` — the conservative choice.

## Skill domains

| Domain | Example skills | Adapter |
|---|---|---|
| Robotics | navigate, pick_place, follow_person, e_stop | ROS 2 |
| Smart home / IoT | lights, thermostat, locks, sensors | MQTT · Matter · Zigbee |
| Microcontrollers | read_sensor, set_pin, drive_motor | Serial / GPIO |
| Computer use | open_app, click, type, read_screen, run_shell | OS-level adapter |
| Cloud / web | call_api, send_email, query_database | Generic REST adapter |

## Browse all skills

See the auto-generated [Skill Catalog](catalog.md) for a complete list of all registered skills.

## Add your own

See [Writing a Skill](writing-a-skill.md) for the step-by-step guide.
