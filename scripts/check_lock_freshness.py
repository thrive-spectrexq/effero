#!/usr/bin/env python3
"""Check that requirements-dev.lock is fresh and covers all dependencies in pyproject.toml.

Run: python scripts/check_lock_freshness.py
Exit code 0 if up to date, 1 if drift is detected.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

try:
    import tomllib  # Python 3.11+
except ImportError:
    import tomli as tomllib  # type: ignore[no-redef]

REPO_ROOT = Path(__file__).resolve().parents[1]
PYPROJECT_PATH = REPO_ROOT / "pyproject.toml"
LOCK_PATH = REPO_ROOT / "requirements-dev.lock"


def normalize_pkg_name(name: str) -> str:
    """Normalize package names according to PEP 503."""
    return re.sub(r"[-_.]+", "-", name.strip().lower()).split("[")[0].split(">")[0].split("<")[0].split("=")[0]


def check_lock_freshness() -> int:
    if not PYPROJECT_PATH.exists():
        print(f"[FAIL] pyproject.toml not found at {PYPROJECT_PATH}")
        return 1

    if not LOCK_PATH.exists():
        print(f"[FAIL] requirements-dev.lock not found at {LOCK_PATH}")
        return 1

    pyproject_data = tomllib.loads(PYPROJECT_PATH.read_text(encoding="utf-8"))
    project = pyproject_data.get("project", {})

    # Extract direct dependencies for base, dev, and llm extras
    declared_specs: list[str] = list(project.get("dependencies", []))
    opt_deps = project.get("optional-dependencies", {})
    declared_specs.extend(opt_deps.get("dev", []))
    declared_specs.extend(opt_deps.get("llm", []))

    declared_pkgs = {normalize_pkg_name(s) for s in declared_specs if s.strip()}

    # Extract packages pinned in requirements-dev.lock
    lock_content = LOCK_PATH.read_text(encoding="utf-8")
    locked_pkgs = set()
    for line in lock_content.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "==" in line:
            pkg = line.split("==")[0].strip()
            locked_pkgs.add(normalize_pkg_name(pkg))

    missing = declared_pkgs - locked_pkgs
    if missing:
        print(f"[FAIL] requirements-dev.lock is missing packages declared in pyproject.toml: {sorted(missing)}")
        print("Run: pip-compile --extra=dev --extra=llm --output-file=requirements-dev.lock pyproject.toml")
        return 1

    print(f"[PASS] requirements-dev.lock is up to date with pyproject.toml ({len(declared_pkgs)} root deps verified).")
    return 0


if __name__ == "__main__":
    sys.exit(check_lock_freshness())
