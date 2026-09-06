"""Cognition core: orchestrator/planner, memory, and model router.

This is the "brain" layer described in the project README's Architecture
section. Submodules:

- agent    -- the plan -> act -> observe -> replan loop
- memory   -- working / episodic / semantic memory
- planner  -- task decomposition and replanning
- router   -- routes LLM calls to a local or cloud backend
"""
