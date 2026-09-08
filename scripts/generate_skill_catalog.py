"""Generate docs/skills/catalog.md from the @skill registry.

Run: python scripts/generate_skill_catalog.py
"""

import importlib
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

header = """# Skill Catalog

> Auto-generated from the `@skill` registry. Do not edit manually.
> Run `python scripts/generate_skill_catalog.py` to regenerate.

| Skill Name | Safety Class | Description |
|---|---|---|
"""

rows = []
for name in registry.list():
    spec = registry.get(name)
    rows.append(f"| `{spec.name}` | `{spec.safety_class.value}` | {spec.description} |")

output = header + "\n".join(rows) + "\n"
output_path = Path(__file__).resolve().parents[1] / "docs" / "skills" / "catalog.md"
output_path.parent.mkdir(parents=True, exist_ok=True)
output_path.write_text(output, encoding="utf-8")
print(f"Generated catalog with {len(rows)} skills.")
