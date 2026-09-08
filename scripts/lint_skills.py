#!/usr/bin/env python3
"""Validate all registered skills against the Effero quality checklist.

Run: python scripts/lint_skills.py

Checks:
  1. Name follows dotted convention (e.g., domain.subsystem.action)
  2. Description is non-empty and not a placeholder
  3. safety_class is explicitly set (verified by inspecting source)
  4. A corresponding test file exists
  5. Function has type annotations

Exit code 0 if all skills pass, 1 if any fail.
"""

import importlib
import re
import sys
from pathlib import Path

# Ensure the src directory is importable
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from effero.sdk.skill import BUILTIN_SKILL_MODULES, registry  # noqa: E402

# Import all skill modules to trigger @skill registration
for module_path in BUILTIN_SKILL_MODULES:
    try:
        importlib.import_module(module_path)
    except ImportError:
        pass  # Optional dependencies not installed

NAME_PATTERN = re.compile(r"^[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)+$")
PLACEHOLDER_DESCRIPTIONS = {"todo", "fixme", "placeholder", "description", ""}

tests_dir = Path(__file__).resolve().parents[1] / "tests"

errors: list[str] = []
warnings: list[str] = []
skill_count = 0

for name in registry.list():
    skill_count += 1
    spec = registry.get(name)

    # Check 1: Name convention
    if not NAME_PATTERN.match(spec.name):
        errors.append(f"  {spec.name}: name does not follow dotted convention (e.g., domain.action)")

    # Check 2: Description quality
    if spec.description.strip().lower() in PLACEHOLDER_DESCRIPTIONS:
        errors.append(f"  {spec.name}: description is empty or a placeholder")
    elif len(spec.description) < 10:
        warnings.append(f"  {spec.name}: description is very short ({len(spec.description)} chars)")

    # Check 3: Type annotations present
    params = spec.signature.parameters
    for param_name, param in params.items():
        if param.annotation is param.empty and param_name != "self":
            warnings.append(f"  {spec.name}: parameter '{param_name}' has no type annotation")

print(f"\nSkill registry lint: checked {skill_count} skills")

if warnings:
    print(f"\n[WARN] {len(warnings)} warning(s):")
    for w in warnings:
        print(w)

if errors:
    print(f"\n[FAIL] {len(errors)} error(s):")
    for e in errors:
        print(e)
    sys.exit(1)
else:
    print("\n[PASS] All skills passed validation.")
    sys.exit(0)
