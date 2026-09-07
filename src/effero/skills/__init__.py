"""Effero Skills package.

This package contains built-in skills for IoT, computer use, and robotics.
"""
from __future__ import annotations

import effero.skills.community
import effero.skills.computer_use
import effero.skills.iot
import effero.skills.robotics

__all__ = [
    "iot", "computer_use", "robotics", "community"
]
