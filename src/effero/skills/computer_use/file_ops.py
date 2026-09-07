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
async def read_file(path: str) -> dict:
    try:
        with open(path, encoding='utf-8') as f:
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
        with open(path, 'w', encoding='utf-8') as f:
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
