"""Actuator communication packet framing protocols: Dynamixel Protocol 2.0, Modbus RTU, CRC-16, and Serial Stream."""

from __future__ import annotations

import struct
from dataclasses import dataclass, field
from enum import IntEnum


class CRC16:
    """Standard CRC-16 calculation engines for industrial and robotics protocols."""

    # Precomputed table for CRC-16-Modbus (polynomial 0xA001)
    _MODBUS_TABLE: list[int] = []
    # Precomputed table for CRC-16-Dynamixel (polynomial 0x1021 / Protocol 2.0 lookup table)
    _DYNAMIXEL_TABLE: list[int] = []
    # Precomputed table for CRC-16-CCITT (polynomial 0x1021)
    _CCITT_TABLE: list[int] = []

    @classmethod
    def _init_tables(cls) -> None:
        if cls._MODBUS_TABLE:
            return

        # Modbus table (reversed poly 0xA001)
        for i in range(256):
            curr = i
            for _ in range(8):
                if curr & 1:
                    curr = (curr >> 1) ^ 0xA001
                else:
                    curr >>= 1
            cls._MODBUS_TABLE.append(curr)

        # Dynamixel / CCITT table (poly 0x1021)
        poly = 0x1021
        for i in range(256):
            curr = i << 8
            for _ in range(8):
                if curr & 0x8000:
                    curr = ((curr << 1) ^ poly) & 0xFFFF
                else:
                    curr = (curr << 1) & 0xFFFF
            cls._DYNAMIXEL_TABLE.append(curr)
            cls._CCITT_TABLE.append(curr)

    @classmethod
    def compute_modbus(cls, data: bytes) -> int:
        """Compute CRC-16-Modbus (init=0xFFFF, poly=0xA001)."""
        cls._init_tables()
        crc = 0xFFFF
        for b in data:
            crc = (crc >> 8) ^ cls._MODBUS_TABLE[(crc ^ b) & 0xFF]
        return crc & 0xFFFF

    @classmethod
    def compute_dynamixel(cls, data: bytes) -> int:
        """Compute CRC-16-Dynamixel for Robotis Protocol 2.0 (init=0x0000, poly=0x1021)."""
        cls._init_tables()
        crc = 0x0000
        for b in data:
            i = ((crc >> 8) ^ b) & 0xFF
            crc = ((crc << 8) ^ cls._DYNAMIXEL_TABLE[i]) & 0xFFFF
        return crc & 0xFFFF

    @classmethod
    def compute_ccitt(cls, data: bytes, init: int = 0xFFFF) -> int:
        """Compute CRC-16-CCITT (poly=0x1021, default init=0xFFFF)."""
        cls._init_tables()
        crc = init
        for b in data:
            i = ((crc >> 8) ^ b) & 0xFF
            crc = ((crc << 8) ^ cls._CCITT_TABLE[i]) & 0xFFFF
        return crc & 0xFFFF


# Initialize lookup tables
CRC16._init_tables()


class DynamixelInstruction(IntEnum):
    """Robotis Dynamixel Protocol 2.0 Instruction Codes."""

    PING = 0x01
    READ = 0x02
    WRITE = 0x03
    REG_WRITE = 0x04
    ACTION = 0x05
    FACTORY_RESET = 0x06
    REBOOT = 0x08
    CLEAR = 0x10
    CONTROL_TABLE_BACKUP = 0x20
    STATUS = 0x55
    SYNC_READ = 0x82
    SYNC_WRITE = 0x83
    FAST_SYNC_READ = 0x8A
    BULK_READ = 0x92
    BULK_WRITE = 0x93
    FAST_BULK_READ = 0x9A


class DynamixelError(IntEnum):
    """Robotis Dynamixel Protocol 2.0 Error Bitflags."""

    NONE = 0x00
    RESULT_FAIL = 0x01
    INSTRUCTION_ERROR = 0x02
    CRC_ERROR = 0x04
    DATA_RANGE_ERROR = 0x08
    DATA_LENGTH_ERROR = 0x10
    DATA_LIMIT_ERROR = 0x20
    ACCESS_ERROR = 0x40


@dataclass
class DynamixelStatus:
    """Decoded Dynamixel Protocol 2.0 Status response packet."""

    packet_id: int
    error_code: int
    parameters: bytes
    has_error: bool

    def error_names(self) -> list[str]:
        names: list[str] = []
        for err in DynamixelError:
            if err.value != 0 and (self.error_code & err.value):
                names.append(err.name)
        return names


class DynamixelPacket:
    """Robotis Dynamixel Protocol 2.0 Packet Builder, Parser, and Byte Stuffer."""

    HEADER: bytes = bytes([0xFF, 0xFF, 0xFD, 0x00])

    @staticmethod
    def byte_stuff(data: bytes) -> bytes:
        """Insert 0xFD after sequence [0xFF, 0xFF, 0xFD] to avoid header false triggers."""
        stuffed = bytearray()
        i = 0
        n = len(data)
        while i < n:
            if i + 2 < n and data[i] == 0xFF and data[i + 1] == 0xFF and data[i + 2] == 0xFD:
                stuffed.extend([0xFF, 0xFF, 0xFD, 0xFD])
                i += 3
            else:
                stuffed.append(data[i])
                i += 1
        return bytes(stuffed)

    @staticmethod
    def byte_unstuff(data: bytes) -> bytes:
        """Remove stuffed 0xFD after sequence [0xFF, 0xFF, 0xFD, 0xFD]."""
        unstuffed = bytearray()
        i = 0
        n = len(data)
        while i < n:
            if i + 3 < n and data[i] == 0xFF and data[i + 1] == 0xFF and data[i + 2] == 0xFD and data[i + 3] == 0xFD:
                unstuffed.extend([0xFF, 0xFF, 0xFD])
                i += 4
            else:
                unstuffed.append(data[i])
                i += 1
        return bytes(unstuffed)

    @classmethod
    def build_instruction_packet(
        cls,
        packet_id: int,
        instruction: int,
        parameters: bytes = b"",
    ) -> bytes:
        """Build a complete Robotis Protocol 2.0 instruction packet."""
        stuffed_params = cls.byte_stuff(parameters)
        # Length = Instruction (1 byte) + Stuffed Parameters (N bytes) + CRC (2 bytes)
        length = 1 + len(stuffed_params) + 2

        packet_without_crc = (
            cls.HEADER
            + struct.pack("<B", packet_id)
            + struct.pack("<H", length)
            + struct.pack("<B", instruction)
            + stuffed_params
        )

        crc = CRC16.compute_dynamixel(packet_without_crc)
        return packet_without_crc + struct.pack("<H", crc)

    @classmethod
    def build_ping(cls, packet_id: int) -> bytes:
        """Build Ping packet (Instruction 0x01)."""
        return cls.build_instruction_packet(packet_id, DynamixelInstruction.PING)

    @classmethod
    def build_read(cls, packet_id: int, address: int, length: int) -> bytes:
        """Build Read packet (Instruction 0x02)."""
        params = struct.pack("<HH", address, length)
        return cls.build_instruction_packet(packet_id, DynamixelInstruction.READ, params)

    @classmethod
    def build_write(cls, packet_id: int, address: int, data: bytes) -> bytes:
        """Build Write packet (Instruction 0x03)."""
        params = struct.pack("<H", address) + data
        return cls.build_instruction_packet(packet_id, DynamixelInstruction.WRITE, params)

    @classmethod
    def build_sync_write(
        cls,
        address: int,
        data_len: int,
        id_data_map: list[tuple[int, bytes]],
    ) -> bytes:
        """Build Sync Write packet (Instruction 0x83) to broadcast ID 0xFE."""
        params = struct.pack("<HH", address, data_len)
        for dev_id, dev_data in id_data_map:
            params += struct.pack("<B", dev_id) + dev_data
        return cls.build_instruction_packet(0xFE, DynamixelInstruction.SYNC_WRITE, params)

    @classmethod
    def parse_status_packet(cls, packet: bytes) -> DynamixelStatus:
        """Parse, verify CRC, and unstuff a Robotis Protocol 2.0 Status packet."""
        if len(packet) < 11:
            raise ValueError(f"Packet too short for Dynamixel status: {len(packet)} bytes")

        if packet[:4] != cls.HEADER:
            raise ValueError(f"Invalid Dynamixel header: {packet[:4].hex()}")

        packet_id = packet[4]
        length = struct.unpack("<H", packet[5:7])[0]

        expected_total_len = 7 + length
        if len(packet) < expected_total_len:
            raise ValueError(f"Incomplete packet: expected {expected_total_len} bytes, got {len(packet)}")

        packet_body = packet[:expected_total_len]
        received_crc = struct.unpack("<H", packet_body[-2:])[0]
        calculated_crc = CRC16.compute_dynamixel(packet_body[:-2])

        if received_crc != calculated_crc:
            raise ValueError(f"CRC error: calculated 0x{calculated_crc:04X}, received 0x{received_crc:04X}")

        instruction = packet[7]
        if instruction != DynamixelInstruction.STATUS:
            raise ValueError(f"Expected status instruction 0x55, got 0x{instruction:02X}")

        error_code = packet[8]
        stuffed_params = packet[9:-2]
        parameters = cls.byte_unstuff(stuffed_params)

        return DynamixelStatus(
            packet_id=packet_id,
            error_code=error_code,
            parameters=parameters,
            has_error=(error_code != 0),
        )


class ModbusFunction(IntEnum):
    """Standard Modbus RTU Function Codes."""

    READ_HOLDING_REGISTERS = 0x03
    READ_INPUT_REGISTERS = 0x04
    WRITE_SINGLE_REGISTER = 0x06
    WRITE_MULTIPLE_REGISTERS = 0x10


@dataclass
class ModbusResponse:
    """Decoded Modbus RTU response frame."""

    slave_address: int
    function_code: int
    is_exception: bool
    exception_code: int | None = None
    data: bytes = b""
    registers: list[int] = field(default_factory=list)


class ModbusPacket:
    """Modbus RTU Frame Encoder, Decoder, and CRC-16 Engine."""

    @classmethod
    def build_request(
        cls,
        slave_address: int,
        function_code: int,
        data: bytes,
    ) -> bytes:
        """Encode a Modbus RTU request frame with CRC-16 (little-endian: low byte first)."""
        frame = struct.pack("<BB", slave_address, function_code) + data
        crc = CRC16.compute_modbus(frame)
        return frame + struct.pack("<H", crc)

    @classmethod
    def build_read_holding_registers(
        cls,
        slave_address: int,
        start_address: int,
        quantity: int,
    ) -> bytes:
        """Build Function 0x03 Read Holding Registers request."""
        data = struct.pack(">HH", start_address, quantity)
        return cls.build_request(slave_address, ModbusFunction.READ_HOLDING_REGISTERS, data)

    @classmethod
    def build_read_input_registers(
        cls,
        slave_address: int,
        start_address: int,
        quantity: int,
    ) -> bytes:
        """Build Function 0x04 Read Input Registers request."""
        data = struct.pack(">HH", start_address, quantity)
        return cls.build_request(slave_address, ModbusFunction.READ_INPUT_REGISTERS, data)

    @classmethod
    def build_write_single_register(
        cls,
        slave_address: int,
        register_address: int,
        value: int,
    ) -> bytes:
        """Build Function 0x06 Write Single Register request."""
        data = struct.pack(">HH", register_address, value)
        return cls.build_request(slave_address, ModbusFunction.WRITE_SINGLE_REGISTER, data)

    @classmethod
    def build_write_multiple_registers(
        cls,
        slave_address: int,
        start_address: int,
        values: list[int],
    ) -> bytes:
        """Build Function 0x10 Write Multiple Registers request."""
        qty = len(values)
        byte_count = qty * 2
        payload = struct.pack(">HHB", start_address, qty, byte_count)
        for val in values:
            payload += struct.pack(">H", val)
        return cls.build_request(slave_address, ModbusFunction.WRITE_MULTIPLE_REGISTERS, payload)

    @classmethod
    def build_response(
        cls,
        slave_address: int,
        function_code: int,
        data: bytes,
    ) -> bytes:
        """Build a Modbus RTU response frame."""
        return cls.build_request(slave_address, function_code, data)

    @classmethod
    def build_exception(
        cls,
        slave_address: int,
        function_code: int,
        exception_code: int,
    ) -> bytes:
        """Build Modbus exception response (function | 0x80)."""
        data = struct.pack("<B", exception_code)
        return cls.build_request(slave_address, function_code | 0x80, data)

    @classmethod
    def parse_response(cls, frame: bytes) -> ModbusResponse:
        """Decode and verify CRC of a Modbus RTU response frame."""
        if len(frame) < 4:
            raise ValueError(f"Frame too short for Modbus: {len(frame)} bytes")

        received_crc = struct.unpack("<H", frame[-2:])[0]
        calculated_crc = CRC16.compute_modbus(frame[:-2])
        if received_crc != calculated_crc:
            raise ValueError(f"Modbus CRC mismatch: calculated 0x{calculated_crc:04X}, received 0x{received_crc:04X}")

        slave_addr = frame[0]
        func_code = frame[1]
        payload = frame[2:-2]

        # Exception response
        if func_code & 0x80:
            exc_code = payload[0] if payload else 0
            return ModbusResponse(
                slave_address=slave_addr,
                function_code=func_code & 0x7F,
                is_exception=True,
                exception_code=exc_code,
            )

        regs: list[int] = []
        if func_code in (ModbusFunction.READ_HOLDING_REGISTERS, ModbusFunction.READ_INPUT_REGISTERS):
            byte_count = payload[0]
            reg_bytes = payload[1 : 1 + byte_count]
            num_regs = len(reg_bytes) // 2
            for i in range(num_regs):
                regs.append(struct.unpack(">H", reg_bytes[i * 2 : (i + 1) * 2])[0])

        return ModbusResponse(
            slave_address=slave_addr,
            function_code=func_code,
            is_exception=False,
            data=payload,
            registers=regs,
        )


@dataclass
class FramedPacket:
    """Decoded packet from SerialFramedProtocol."""

    sequence: int
    command_id: int
    payload: bytes


class SerialFramedProtocol:
    """Generic framed stream protocol with SOF, Sequence, Command ID, Length, Payload, CRC-16, and EOF.

    Frame format:
        [SOF: 0xAA 0x55] (2B)
        [Sequence: uint8] (1B)
        [Command ID: uint8] (1B)
        [Length: uint16 big-endian] (2B)
        [Payload: N bytes] (NB)
        [CRC-16 CCITT: uint16 big-endian] (2B)
        [EOF: 0x55 0xAA] (2B)
    """

    SOF: bytes = bytes([0xAA, 0x55])
    EOF: bytes = bytes([0x55, 0xAA])

    def __init__(self) -> None:
        self._buffer = bytearray()

    @classmethod
    def encode_frame(cls, sequence: int, command_id: int, payload: bytes) -> bytes:
        """Encode packet into framed byte sequence."""
        header = struct.pack(">BBH", sequence & 0xFF, command_id & 0xFF, len(payload))
        data_to_crc = header + payload
        crc = CRC16.compute_ccitt(data_to_crc)
        return cls.SOF + data_to_crc + struct.pack(">H", crc) + cls.EOF

    def feed(self, data: bytes) -> list[FramedPacket]:
        """Feed incoming streaming bytes and return list of all completely decoded packets."""
        self._buffer.extend(data)
        packets: list[FramedPacket] = []

        while len(self._buffer) >= 8:  # Minimum frame size: 2 SOF + 4 Header + 0 Payload + 2 CRC + 2 EOF = 10
            # Look for SOF
            sof_index = self._buffer.find(self.SOF)
            if sof_index == -1:
                # No SOF found, keep last byte in case it's 0xAA
                if len(self._buffer) > 0 and self._buffer[-1] == self.SOF[0]:
                    self._buffer = self._buffer[-1:]
                else:
                    self._buffer.clear()
                break

            # Discard any noise before SOF
            if sof_index > 0:
                del self._buffer[:sof_index]

            if len(self._buffer) < 8:
                break

            # Read sequence, command, length
            seq = self._buffer[2]
            cmd = self._buffer[3]
            length = struct.unpack(">H", self._buffer[4:6])[0]

            total_frame_len = 2 + 4 + length + 2 + 2
            if len(self._buffer) < total_frame_len:
                # Wait for more data
                break

            payload = bytes(self._buffer[6 : 6 + length])
            crc_offset = 6 + length
            received_crc = struct.unpack(">H", self._buffer[crc_offset : crc_offset + 2])[0]
            eof = bytes(self._buffer[crc_offset + 2 : crc_offset + 4])

            if eof != self.EOF:
                # Bad frame, skip past current SOF
                del self._buffer[:2]
                continue

            # Verify CRC
            data_to_crc = bytes(self._buffer[2:crc_offset])
            calculated_crc = CRC16.compute_ccitt(data_to_crc)
            if calculated_crc != received_crc:
                # Bad CRC, skip past current SOF
                del self._buffer[:2]
                continue

            # Valid packet decoded!
            packets.append(FramedPacket(sequence=seq, command_id=cmd, payload=payload))
            del self._buffer[:total_frame_len]

        return packets
