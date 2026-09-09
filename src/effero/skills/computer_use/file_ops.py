"""File operation skills."""

from __future__ import annotations

import os
from pathlib import Path

from effero.sdk.skill import SafetyClass, skill


@skill(
    name="computer_use.file.read",
    description="Read a file",
    safety_class=SafetyClass.READ_ONLY,
)
async def read_file(path: str, max_bytes: int = 10_000_000) -> dict:
    try:
        p = Path(path)
        if p.exists() and p.stat().st_size > max_bytes:
            return {
                "status": "error",
                "path": path,
                "error": f"File size ({p.stat().st_size} bytes) exceeds safety limit of {max_bytes} bytes",
            }
        with open(path, encoding="utf-8", errors="replace") as f:
            content = f.read()
        return {"status": "success", "path": path, "content": content}
    except Exception as e:
        return {"status": "error", "path": path, "error": str(e)}


@skill(
    name="computer_use.file.write",
    description="Write to a file",
    safety_class=SafetyClass.ACT_WITH_APPROVAL,
)
async def write_file(path: str, content: str) -> dict:
    try:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        return {"status": "success", "path": path}
    except Exception as e:
        return {"status": "error", "path": path, "error": str(e)}


@skill(
    name="computer_use.file.list_dir",
    description="List directory contents",
    safety_class=SafetyClass.READ_ONLY,
)
async def list_dir(path: str) -> dict:
    try:
        items = os.listdir(path)
        return {"status": "success", "path": path, "items": items}
    except Exception as e:
        return {"status": "error", "path": path, "error": str(e)}


@skill(
    name="computer_use.file.delete",
    description="Delete a file or directory tree",
    safety_class=SafetyClass.ACT_WITH_APPROVAL,
)
async def delete_file(path: str, recursive: bool = False) -> dict:
    try:
        p = Path(path)
        if not p.exists():
            return {"status": "error", "path": path, "error": f"Path '{path}' does not exist"}
        if p.is_dir():
            if not recursive:
                return {
                    "status": "error",
                    "path": path,
                    "error": f"Path '{path}' is a directory. Set recursive=True to delete directory trees.",
                }
            import shutil

            shutil.rmtree(p)
        else:
            p.unlink()
        return {"status": "success", "path": path}
    except Exception as e:
        return {"status": "error", "path": path, "error": str(e)}
