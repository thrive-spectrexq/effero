"""Community contributed system inspection and diagnostic skills."""

from __future__ import annotations

import platform
import sys
import time
from typing import Any

import psutil

from effero.sdk.skill import SafetyClass, skill


@skill(
    name="community.system_info.get_overview",
    description="Retrieve comprehensive hardware, host operating system, and runtime telemetry.",
    safety_class=SafetyClass.READ_ONLY,
)
def get_system_overview() -> dict[str, Any]:
    """Inspect and return current host system platform, hardware resource usage, and process stats."""
    cpu_percent = psutil.cpu_percent(interval=0.1)
    cpu_count_logical = psutil.cpu_count(logical=True)
    cpu_count_physical = psutil.cpu_count(logical=False)

    mem = psutil.virtual_memory()
    disk = psutil.disk_usage("/")

    boot_time = psutil.boot_time()
    uptime_seconds = round(time.time() - boot_time, 2)

    return {
        "os": {
            "system": platform.system(),
            "release": platform.release(),
            "version": platform.version(),
            "architecture": platform.machine(),
            "python_version": sys.version.split()[0],
        },
        "cpu": {
            "usage_percent": cpu_percent,
            "logical_cores": cpu_count_logical,
            "physical_cores": cpu_count_physical,
        },
        "memory": {
            "total_gb": round(mem.total / (1024**3), 2),
            "available_gb": round(mem.available / (1024**3), 2),
            "used_gb": round(mem.used / (1024**3), 2),
            "percent_used": mem.percent,
        },
        "disk": {
            "total_gb": round(disk.total / (1024**3), 2),
            "free_gb": round(disk.free / (1024**3), 2),
            "used_gb": round(disk.used / (1024**3), 2),
            "percent_used": disk.percent,
        },
        "uptime": {
            "boot_timestamp": boot_time,
            "uptime_seconds": uptime_seconds,
        },
    }
