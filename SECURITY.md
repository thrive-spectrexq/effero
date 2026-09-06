# Security Policy

Effero is designed to control physical devices — robots, actuators, and smart-home hardware. A security or safety vulnerability here can have real-world consequences, not just data-confidentiality ones. Please treat that with extra care when reporting.

## Reporting a vulnerability

**Please do not open a public GitHub issue for security or physical-safety vulnerabilities.**

Instead, use GitHub's private vulnerability reporting for this repository (**Security** tab → **Report a vulnerability**), if enabled, or contact the maintainers directly through a private channel listed on the repository's GitHub profile.

When reporting, please include:

- A description of the vulnerability and its potential impact (data exposure, unauthorized device control, unsafe physical action, etc.).
- Steps to reproduce, or a minimal proof-of-concept if possible.
- The affected version/commit and your environment (OS, Python version, relevant adapters/extras installed).
- Whether the issue requires physical access to hardware to exploit, or is remotely triggerable.

## Scope

Particularly high-priority categories for this project:

- Any path by which a remote actor could invoke an `ACT_AUTONOMOUS` or `ACT_WITH_APPROVAL` skill without going through the intended guardrail/approval flow.
- Any way to bypass, disable, or spoof the safety/guardrail engine (`src/effero/safety/`) once implemented.
- Any way to defeat a hardware e-stop hook.
- Credential or secret handling in adapters (`src/effero/adapters/`) that connect to cloud APIs or local networks.
- Prompt-injection paths that could cause a skill call the operator did not intend.

## Response

We aim to acknowledge reports within a few business days and will work with you on a coordinated disclosure timeline before any public write-up. Please give us reasonable time to ship a fix before public disclosure.

Thank you for helping keep Effero — and the physical devices it controls — safe.
