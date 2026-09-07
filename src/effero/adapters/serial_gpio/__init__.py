"""Serial adapter module."""

from __future__ import annotations

from effero.adapters.serial_gpio.client import MockSerialAdapter, SerialAdapter

__all__ = ["SerialAdapter", "MockSerialAdapter"]
