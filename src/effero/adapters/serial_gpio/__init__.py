"""Serial adapter and actuator framing module."""

from __future__ import annotations

from effero.adapters.serial_gpio.client import SerialAdapter
from effero.adapters.serial_gpio.framing import (
    CRC16,
    DynamixelError,
    DynamixelInstruction,
    DynamixelPacket,
    DynamixelStatus,
    FramedPacket,
    ModbusFunction,
    ModbusPacket,
    ModbusResponse,
    SerialFramedProtocol,
)

__all__ = [
    "SerialAdapter",
    "CRC16",
    "DynamixelPacket",
    "DynamixelStatus",
    "DynamixelInstruction",
    "DynamixelError",
    "ModbusPacket",
    "ModbusResponse",
    "ModbusFunction",
    "SerialFramedProtocol",
    "FramedPacket",
]
