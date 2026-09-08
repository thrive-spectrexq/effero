# Governance

Effero is currently maintained by a single person
([@thrive-spectrexq](https://github.com/thrive-spectrexq)). This document
makes that reality explicit rather than implicit, because honest governance
is the first thing a potential adopter or contributor checks.

## Decision-making

All design decisions are currently made by the maintainer. For changes
touching `src/effero/safety/`, `crates/effero-safety-kernel/`, or the
`SafetyClass` enum, the bar is higher: the maintainer will document the
rationale in the PR description and wait at least 48 hours for community
feedback before merging.

## Path to co-maintainers

A contributor may be invited as a co-maintainer after demonstrating:

1. **Multiple non-trivial merged PRs** — not just typo fixes, but changes
   that required understanding the architecture.
2. **Thoughtful code review** on other contributors' PRs.
3. **Good judgment on safety-critical code** — the ability to say "this
   needs more scrutiny" on PRs touching the safety layer, adapters, or
   skills with physical-world consequences.

There is no formal application process — the maintainer will reach out
when the track record is there.

## Bus factor

With one active maintainer, the bus factor is 1. If you are building on
Effero and this concerns you (it should), the best mitigation is to
contribute: every merged PR brings the project closer to having multiple
people who understand the codebase deeply enough to maintain it.

## Changes to this document

Governance changes follow the same PR process as code changes, with the
same 48-hour feedback window used for safety-critical changes.
