"""Serial and GPIO adapter implementation with genuine binary packet framing and streaming."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from effero.adapters.base import DeviceAdapter
from effero.adapters.serial_gpio.framing import (
    DynamixelPacket,
    DynamixelStatus,
    ModbusPacket,
    ModbusResponse,
    SerialFramedProtocol,
)

logger = logging.getLogger(__name__)

try:
    import serial_asyncio

    HAS_SERIAL = True
except ImportError:
    HAS_SERIAL = False


class SerialAdapter(DeviceAdapter):
    """Serial port adapter for communicating with microcontrollers, servos, and PLC devices.

    Supports genuine binary packet framing (Dynamixel Protocol 2.0, Modbus RTU, and framed streaming).
    """

    def __init__(
        self,
        port: str,
        baudrate: int = 9600,
        reader: asyncio.StreamReader | None = None,
        writer: asyncio.StreamWriter | None = None,
    ) -> None:
        self.port = port
        self.baudrate = baudrate
        self._reader: asyncio.StreamReader | None = reader
        self._writer: asyncio.StreamWriter | None = writer
        self._connected = bool(reader and writer)
        self._last_state: dict[str, Any] = {}
        self._protocol_parser = SerialFramedProtocol()

    @property
    def is_connected(self) -> bool:
        return self._connected and self._writer is not None

    async def connect(self) -> None:
        """Open physical serial connection or verify existing stream."""
        if self._reader is not None and self._writer is not None:
            self._connected = True
            logger.info(f"Using provided stream connection for {self.port}")
            return

        if not HAS_SERIAL:
            raise RuntimeError(f"pyserial-asyncio is required to open serial port {self.port}")

        self._reader, self._writer = await serial_asyncio.open_serial_connection(
            url=self.port,
            baudrate=self.baudrate,
        )
        self._connected = True
        logger.info(f"Connected to serial port {self.port} at {self.baudrate} baud")

    async def disconnect(self) -> None:
        """Close serial connection."""
        if self._writer:
            self._writer.close()
            try:
                await self._writer.wait_closed()
            except Exception:
                pass
            self._reader = None
            self._writer = None
            self._connected = False
            logger.info(f"Disconnected from serial port {self.port}")

    async def send_raw(self, data: bytes) -> None:
        """Send raw binary bytes to the serial transport."""
        if not self.is_connected or self._writer is None:
            raise RuntimeError(f"Serial port {self.port} is not connected")
        self._writer.write(data)
        await self._writer.drain()

    async def read_raw(self, nbytes: int, timeout: float = 2.0) -> bytes:
        """Read exactly nbytes from the serial transport."""
        if not self.is_connected or self._reader is None:
            raise RuntimeError(f"Serial port {self.port} is not connected")
        return await asyncio.wait_for(self._reader.readexactly(nbytes), timeout=timeout)

    async def send_dynamixel(
        self,
        packet_id: int,
        instruction: int,
        parameters: bytes = b"",
        response_timeout: float = 2.0,
    ) -> DynamixelStatus:
        """Send Dynamixel Protocol 2.0 instruction packet and await status response."""
        packet = DynamixelPacket.build_instruction_packet(packet_id, instruction, parameters)
        await self.send_raw(packet)

        # Read status response: Header(4) + ID(1) + Length(2)
        if self._reader is None:
            raise RuntimeError(f"Serial port {self.port} is not connected")

        header_bytes = await asyncio.wait_for(self._reader.readexactly(7), timeout=response_timeout)
        length = int.from_bytes(header_bytes[5:7], byteorder="little")
        body_bytes = await asyncio.wait_for(
            self._reader.readexactly(length),
            timeout=response_timeout,
        )
        full_status_pkt = header_bytes + body_bytes
        status = DynamixelPacket.parse_status_packet(full_status_pkt)
        self._last_state[f"dynamixel_{packet_id}"] = {
            "error_code": status.error_code,
            "has_error": status.has_error,
            "parameters_len": len(status.parameters),
        }
        return status

    async def send_modbus(
        self,
        slave_address: int,
        function_code: int,
        data: bytes,
        response_len: int,
        response_timeout: float = 2.0,
    ) -> ModbusResponse:
        """Send Modbus RTU frame and parse response frame."""
        frame = ModbusPacket.build_request(slave_address, function_code, data)
        await self.send_raw(frame)

        if self._reader is None:
            raise RuntimeError(f"Serial port {self.port} is not connected")

        resp_bytes = await asyncio.wait_for(
            self._reader.readexactly(response_len),
            timeout=response_timeout,
        )
        response = ModbusPacket.parse_response(resp_bytes)
        self._last_state[f"modbus_{slave_address}"] = {
            "function": response.function_code,
            "is_exception": response.is_exception,
            "registers": response.registers,
        }
        return response

    async def execute(self, command: str, params: dict[str, Any]) -> Any:
        """Execute a high-level actuator or protocol command over serial."""
        if not self.is_connected or self._writer is None or self._reader is None:
            raise RuntimeError(f"Serial port {self.port} is not connected")

        if command == "dynamixel_ping":
            servo_id = params.get("id", 1)
            status = await self.send_dynamixel(servo_id, 0x01)
            return {
                "status": "success",
                "servo_id": status.packet_id,
                "error_code": status.error_code,
                "has_error": status.has_error,
            }

        elif command == "modbus_read_holding":
            slave = params.get("slave", 1)
            start_addr = params.get("address", 0)
            qty = params.get("quantity", 1)
            req_data = ModbusPacket.build_read_holding_registers(slave, start_addr, qty)
            await self.send_raw(req_data)
            # Response length: Slave(1) + Func(1) + ByteCount(1) + qty*2 + CRC(2) = 5 + 2*qty
            expected_len = 5 + 2 * qty
            resp_bytes = await self.read_raw(expected_len)
            modbus_resp = ModbusPacket.parse_response(resp_bytes)
            return {
                "status": "success",
                "slave": modbus_resp.slave_address,
                "registers": modbus_resp.registers,
            }

        elif command == "send_framed":
            seq = params.get("sequence", 0)
            cmd_id = params.get("cmd_id", 1)
            payload = params.get("payload", b"")
            if isinstance(payload, str):
                payload = payload.encode("utf-8")
            frame = SerialFramedProtocol.encode_frame(seq, cmd_id, payload)
            await self.send_raw(frame)
            return {
                "status": "success",
                "sequence": seq,
                "cmd_id": cmd_id,
                "bytes_sent": len(frame),
            }

        else:
            # Standard framed JSON communication
            msg = {"command": command, "params": params}
            encoded = (json.dumps(msg) + "\n").encode()
            self._writer.write(encoded)
            await self._writer.drain()

            line = await self._reader.readline()
            try:
                response = json.loads(line.decode().strip())
                self._last_state.update(response)
                return response
            except json.JSONDecodeError:
                return {"status": "error", "raw": line.decode().strip()}

    async def read_state(self) -> dict[str, Any]:
        return dict(self._last_state)
