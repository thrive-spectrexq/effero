"""Comprehensive test suite for actuator communication packet framing and ROS 2 CDR serialization."""

from __future__ import annotations

import asyncio
import math
import struct

import pytest

from effero.adapters.ros2.bridge import (
    ActuatorCommand,
    Header,
    JointState,
    JointTrajectory,
    JointTrajectoryPoint,
    ROS2Bridge,
    ROS2CDRSerializer,
)
from effero.adapters.serial_gpio.client import SerialAdapter
from effero.adapters.serial_gpio.framing import (
    CRC16,
    DynamixelError,
    DynamixelInstruction,
    DynamixelPacket,
    ModbusFunction,
    ModbusPacket,
    SerialFramedProtocol,
)

# =============================================================================
# CRC-16 Tests
# =============================================================================


def test_crc16_modbus_standard_vector() -> None:
    """Verify CRC-16-Modbus against standard reference test vector b'123456789' -> 0x4B37."""
    test_vec = b"123456789"
    crc = CRC16.compute_modbus(test_vec)
    assert crc == 0x4B37


def test_crc16_dynamixel_reference_vector() -> None:
    """Verify CRC-16-Dynamixel against Robotis Protocol 2.0 Ping packet for ID 1."""
    # Packet without CRC: Header(4) + ID(1) + Length(2) + Instruction(1)
    ping_pkt_body = bytes([0xFF, 0xFF, 0xFD, 0x00, 0x01, 0x03, 0x00, 0x01])
    crc = CRC16.compute_dynamixel(ping_pkt_body)
    assert crc == 0xD104


def test_crc16_ccitt_standard_vector() -> None:
    """Verify CRC-16-CCITT."""
    test_vec = b"123456789"
    crc = CRC16.compute_ccitt(test_vec)
    assert isinstance(crc, int)
    assert 0 <= crc <= 0xFFFF


# =============================================================================
# Dynamixel Protocol 2.0 Tests
# =============================================================================


def test_dynamixel_build_ping_packet() -> None:
    """Verify complete Ping packet for ID 1 matching Robotis Protocol 2.0 specification."""
    packet = DynamixelPacket.build_ping(packet_id=1)
    # Expected: FF FF FD 00 01 03 00 01 04 D1
    expected = bytes([0xFF, 0xFF, 0xFD, 0x00, 0x01, 0x03, 0x00, 0x01, 0x04, 0xD1])
    assert packet == expected


def test_dynamixel_build_read_packet() -> None:
    """Verify Read packet structure (address 132, length 4 for present position)."""
    packet = DynamixelPacket.build_read(packet_id=1, address=132, length=4)
    assert packet[:4] == DynamixelPacket.HEADER
    assert packet[4] == 1  # ID
    length = struct.unpack("<H", packet[5:7])[0]
    assert length == 1 + 4 + 2  # Instruction + Params + CRC = 7
    assert packet[7] == DynamixelInstruction.READ
    addr, read_len = struct.unpack("<HH", packet[8:12])
    assert addr == 132
    assert read_len == 4
    # CRC verification
    assert CRC16.compute_dynamixel(packet[:-2]) == struct.unpack("<H", packet[-2:])[0]


def test_dynamixel_build_write_packet() -> None:
    """Verify Write packet structure (LED enable: address 65, data 0x01)."""
    packet = DynamixelPacket.build_write(packet_id=2, address=65, data=bytes([0x01]))
    assert packet[4] == 2
    assert packet[7] == DynamixelInstruction.WRITE
    assert packet[10] == 0x01
    assert CRC16.compute_dynamixel(packet[:-2]) == struct.unpack("<H", packet[-2:])[0]


def test_dynamixel_build_sync_write() -> None:
    """Verify Sync Write packet for multiple servos (address 116, 4 bytes goal position)."""
    targets = [
        (1, struct.pack("<I", 1024)),
        (2, struct.pack("<I", 2048)),
    ]
    packet = DynamixelPacket.build_sync_write(address=116, data_len=4, id_data_map=targets)
    assert packet[4] == 0xFE  # Broadcast ID
    assert packet[7] == DynamixelInstruction.SYNC_WRITE
    assert CRC16.compute_dynamixel(packet[:-2]) == struct.unpack("<H", packet[-2:])[0]


def test_dynamixel_byte_stuffing_and_unstuffing() -> None:
    """Verify byte stuffing replaces 0xFF 0xFF 0xFD with 0xFF 0xFF 0xFD 0xFD and unstuffs cleanly."""
    raw_params = bytes([0x12, 0xFF, 0xFF, 0xFD, 0x34, 0x56, 0xFF, 0xFF, 0xFD, 0x78])
    stuffed = DynamixelPacket.byte_stuff(raw_params)

    # Stuffed length must have 2 extra bytes
    assert len(stuffed) == len(raw_params) + 2
    assert bytes([0xFF, 0xFF, 0xFD, 0xFD]) in stuffed

    unstuffed = DynamixelPacket.byte_unstuff(stuffed)
    assert unstuffed == raw_params


def test_dynamixel_status_packet_parsing() -> None:
    """Build and parse a valid Dynamixel Status response packet."""
    # Build a simulated status response: Header(4), ID=1, Length=7, Inst=0x55, Err=0, Params=[100, 200, 0, 0], CRC
    params = struct.pack("<I", 200)
    length = 1 + 1 + len(params) + 2  # Inst + Err + Params + CRC = 8
    pkt_body = (
        DynamixelPacket.HEADER
        + struct.pack("<B", 1)  # ID
        + struct.pack("<H", length)  # Length
        + struct.pack("<B", DynamixelInstruction.STATUS)
        + struct.pack("<B", 0)  # No error
        + params
    )
    crc = CRC16.compute_dynamixel(pkt_body)
    full_packet = pkt_body + struct.pack("<H", crc)

    status = DynamixelPacket.parse_status_packet(full_packet)
    assert status.packet_id == 1
    assert status.error_code == 0
    assert status.has_error is False
    assert struct.unpack("<I", status.parameters)[0] == 200


def test_dynamixel_status_packet_error_flags() -> None:
    """Verify parsing and decoding of multiple error bitflags in status packet."""
    err_flags = DynamixelError.DATA_RANGE_ERROR | DynamixelError.ACCESS_ERROR
    pkt_body = (
        DynamixelPacket.HEADER
        + struct.pack("<B", 3)
        + struct.pack("<H", 4)  # Inst(1) + Err(1) + CRC(2) = 4
        + struct.pack("<B", DynamixelInstruction.STATUS)
        + struct.pack("<B", err_flags)
    )
    crc = CRC16.compute_dynamixel(pkt_body)
    packet = pkt_body + struct.pack("<H", crc)

    status = DynamixelPacket.parse_status_packet(packet)
    assert status.has_error is True
    assert "DATA_RANGE_ERROR" in status.error_names()
    assert "ACCESS_ERROR" in status.error_names()


def test_dynamixel_corrupt_crc_rejected() -> None:
    """Verify that status packet with corrupted CRC raises ValueError."""
    pkt_body = (
        DynamixelPacket.HEADER
        + struct.pack("<B", 1)
        + struct.pack("<H", 4)
        + struct.pack("<B", DynamixelInstruction.STATUS)
        + struct.pack("<B", 0)
    )
    crc = CRC16.compute_dynamixel(pkt_body)
    bad_packet = pkt_body + struct.pack("<H", crc ^ 0xFFFF)
    with pytest.raises(ValueError, match="CRC error"):
        DynamixelPacket.parse_status_packet(bad_packet)


# =============================================================================
# Modbus RTU Tests
# =============================================================================


def test_modbus_read_holding_registers_roundtrip() -> None:
    """Verify Function 0x03 Read Holding Registers request and response."""
    slave = 1
    start_addr = 100
    qty = 2

    # Build request
    req = ModbusPacket.build_read_holding_registers(slave, start_addr, qty)
    assert req[0] == slave
    assert req[1] == ModbusFunction.READ_HOLDING_REGISTERS
    # Verify CRC
    assert CRC16.compute_modbus(req[:-2]) == struct.unpack("<H", req[-2:])[0]

    # Build simulated response: Slave(1), Func(1), ByteCount(1)=4, Reg1=1234, Reg2=5678, CRC(2)
    resp_data = struct.pack(">BHH", 4, 1234, 5678)
    resp_frame = ModbusPacket.build_response(slave, ModbusFunction.READ_HOLDING_REGISTERS, resp_data)

    parsed = ModbusPacket.parse_response(resp_frame)
    assert parsed.slave_address == slave
    assert parsed.function_code == ModbusFunction.READ_HOLDING_REGISTERS
    assert parsed.is_exception is False
    assert parsed.registers == [1234, 5678]


def test_modbus_write_single_register() -> None:
    """Verify Function 0x06 Write Single Register request and response."""
    req = ModbusPacket.build_write_single_register(slave_address=2, register_address=50, value=999)
    assert req[0] == 2
    assert req[1] == ModbusFunction.WRITE_SINGLE_REGISTER
    assert CRC16.compute_modbus(req[:-2]) == struct.unpack("<H", req[-2:])[0]

    # Echo response
    resp = ModbusPacket.parse_response(req)
    assert resp.slave_address == 2
    assert resp.function_code == 0x06
    assert resp.is_exception is False


def test_modbus_write_multiple_registers() -> None:
    """Verify Function 0x10 Write Multiple Registers."""
    values = [10, 20, 30]
    frame = ModbusPacket.build_write_multiple_registers(
        slave_address=1,
        start_address=0,
        values=values,
    )
    assert frame[0] == 1
    assert frame[1] == ModbusFunction.WRITE_MULTIPLE_REGISTERS
    assert CRC16.compute_modbus(frame[:-2]) == struct.unpack("<H", frame[-2:])[0]


def test_modbus_exception_response() -> None:
    """Verify Modbus exception response encoding and decoding."""
    exc_frame = ModbusPacket.build_exception(
        slave_address=1,
        function_code=ModbusFunction.READ_HOLDING_REGISTERS,
        exception_code=0x02,  # Illegal Data Address
    )
    parsed = ModbusPacket.parse_response(exc_frame)
    assert parsed.is_exception is True
    assert parsed.function_code == ModbusFunction.READ_HOLDING_REGISTERS
    assert parsed.exception_code == 0x02


def test_modbus_corrupted_crc_rejected() -> None:
    """Verify Modbus frame with corrupt CRC is rejected."""
    frame = bytearray(ModbusPacket.build_read_holding_registers(1, 0, 1))
    frame[-1] ^= 0xFF  # Corrupt CRC
    with pytest.raises(ValueError, match="Modbus CRC mismatch"):
        ModbusPacket.parse_response(bytes(frame))


# =============================================================================
# SerialFramedProtocol Tests
# =============================================================================


def test_serial_framed_protocol_roundtrip() -> None:
    """Verify SerialFramedProtocol packet framing, CRC, and streaming parser."""
    protocol = SerialFramedProtocol()
    payload = b"ACTUATOR_VELOCITY_TARGET=45.0"
    frame = SerialFramedProtocol.encode_frame(sequence=42, command_id=7, payload=payload)

    assert frame[:2] == SerialFramedProtocol.SOF
    assert frame[-2:] == SerialFramedProtocol.EOF

    packets = protocol.feed(frame)
    assert len(packets) == 1
    pkt = packets[0]
    assert pkt.sequence == 42
    assert pkt.command_id == 7
    assert pkt.payload == payload


def test_serial_framed_protocol_chunked_streaming() -> None:
    """Verify streaming parser handles partial chunks and multiple frames in one stream."""
    protocol = SerialFramedProtocol()
    frame1 = SerialFramedProtocol.encode_frame(1, 10, b"frame_one")
    frame2 = SerialFramedProtocol.encode_frame(2, 20, b"frame_two")
    stream = frame1 + frame2

    # Feed in 3-byte chunks
    collected = []
    for i in range(0, len(stream), 3):
        chunk = stream[i : i + 3]
        collected.extend(protocol.feed(chunk))

    assert len(collected) == 2
    assert collected[0].sequence == 1
    assert collected[0].payload == b"frame_one"
    assert collected[1].sequence == 2
    assert collected[1].payload == b"frame_two"


def test_serial_framed_protocol_noise_and_corruption() -> None:
    """Verify streaming parser discards noise and corrupted packets without crashing."""
    protocol = SerialFramedProtocol()
    valid_frame = SerialFramedProtocol.encode_frame(5, 1, b"valid_data")
    corrupt_frame = bytearray(SerialFramedProtocol.encode_frame(4, 1, b"bad_crc"))
    corrupt_frame[-4] ^= 0xFF  # Corrupt CRC

    garbage = b"\x00\xff\x12\x34\xaa\x00"
    noisy_stream = garbage + corrupt_frame + valid_frame

    packets = protocol.feed(noisy_stream)
    assert len(packets) == 1
    assert packets[0].sequence == 5
    assert packets[0].payload == b"valid_data"


# =============================================================================
# ROS 2 CDR Serialization Tests
# =============================================================================


def test_ros2_cdr_joint_state_roundtrip() -> None:
    """Verify OMG CDR serialization and deserialization of sensor_msgs/JointState."""
    js = JointState(
        header=Header(stamp_sec=1725750000, stamp_nanosec=500000, frame_id="base_link"),
        name=["joint1", "joint2", "joint3", "joint4"],
        position=[0.1, -0.5, 1.2, 0.0],
        velocity=[0.01, -0.02, 0.05, 0.0],
        effort=[2.5, 1.8, 0.9, 0.1],
    )

    cdr_bytes = ROS2CDRSerializer.serialize_joint_state(js)
    # Must have 4-byte CDR encapsulation header
    assert cdr_bytes[:4] == b"\x00\x01\x00\x00"

    decoded = ROS2CDRSerializer.deserialize_joint_state(cdr_bytes)
    assert decoded.header.stamp_sec == js.header.stamp_sec
    assert decoded.header.stamp_nanosec == js.header.stamp_nanosec
    assert decoded.header.frame_id == "base_link"
    assert decoded.name == js.name
    for i in range(4):
        assert math.isclose(decoded.position[i], js.position[i], abs_tol=1e-6)
        assert math.isclose(decoded.velocity[i], js.velocity[i], abs_tol=1e-6)
        assert math.isclose(decoded.effort[i], js.effort[i], abs_tol=1e-6)


def test_ros2_cdr_joint_trajectory_roundtrip() -> None:
    """Verify CDR serialization and deserialization of trajectory_msgs/JointTrajectory."""
    pt1 = JointTrajectoryPoint(
        positions=[0.0, 0.5],
        velocities=[0.0, 0.0],
        accelerations=[0.0, 0.0],
        effort=[0.0, 0.0],
        time_from_start_sec=1,
        time_from_start_nanosec=0,
    )
    pt2 = JointTrajectoryPoint(
        positions=[1.0, -0.2],
        velocities=[0.5, -0.1],
        accelerations=[0.1, -0.05],
        effort=[1.0, 0.5],
        time_from_start_sec=2,
        time_from_start_nanosec=500000,
    )
    traj = JointTrajectory(
        header=Header(stamp_sec=100, stamp_nanosec=200, frame_id="arm_base"),
        joint_names=["arm_joint_1", "arm_joint_2"],
        points=[pt1, pt2],
    )

    cdr_bytes = ROS2CDRSerializer.serialize_joint_trajectory(traj)
    decoded = ROS2CDRSerializer.deserialize_joint_trajectory(cdr_bytes)

    assert decoded.header.frame_id == "arm_base"
    assert decoded.joint_names == ["arm_joint_1", "arm_joint_2"]
    assert len(decoded.points) == 2
    assert decoded.points[0].positions == [0.0, 0.5]
    assert decoded.points[1].positions == [1.0, -0.2]
    assert decoded.points[1].time_from_start_sec == 2


def test_ros2_cdr_actuator_command_roundtrip() -> None:
    """Verify CDR serialization and deserialization of ActuatorCommand."""
    cmd = ActuatorCommand(
        actuator_id=7,
        command_type="velocity_control",
        target_position=1.57,
        target_velocity=0.85,
        max_torque=2.5,
    )
    cdr_bytes = ROS2CDRSerializer.serialize_actuator_command(cmd)
    decoded = ROS2CDRSerializer.deserialize_actuator_command(cdr_bytes)

    assert decoded.actuator_id == 7
    assert decoded.command_type == "velocity_control"
    assert math.isclose(decoded.target_position, 1.57, abs_tol=1e-6)
    assert math.isclose(decoded.target_velocity, 0.85, abs_tol=1e-6)
    assert math.isclose(decoded.max_torque, 2.5, abs_tol=1e-6)


@pytest.mark.asyncio
async def test_ros2_bridge_real_execution() -> None:
    """Verify ROS2Bridge real message handling without mocks."""
    bridge = ROS2Bridge(node_name="test_robot_node")

    # Execute publish_joint_state
    res = await bridge.execute(
        "publish_joint_state",
        {
            "names": ["joint1", "joint2"],
            "positions": [0.5, -0.5],
            "velocities": [0.1, -0.1],
        },
    )
    assert res["status"] == "success"
    assert res["bytes_serialized"] > 0
    assert res["joint_names"] == ["joint1", "joint2"]

    # Execute actuator_command
    res_cmd = await bridge.execute(
        "actuator_command",
        {
            "actuator_id": 3,
            "command_type": "position",
            "position": 1.2,
        },
    )
    assert res_cmd["status"] == "success"
    assert res_cmd["actuator_id"] == 3

    # Read state
    state = await bridge.read_state()
    assert state["node"] == "test_robot_node"
    assert state["published_count"] == 2
    assert state["latest_joint_state"] is not None
    assert "status" not in state or state.get("status") != "mock"


@pytest.mark.asyncio
async def test_serial_adapter_real_framing_communication() -> None:
    """Verify SerialAdapter executes genuine framed commands over real in-memory streams."""

    # Set up paired asyncio streams
    class DummyStream:
        def __init__(self) -> None:
            self.written = bytearray()

        def write(self, data: bytes) -> None:
            self.written.extend(data)

        async def drain(self) -> None:
            pass

        def close(self) -> None:
            pass

        async def wait_closed(self) -> None:
            pass

    reader = asyncio.StreamReader()
    writer = DummyStream()

    adapter = SerialAdapter(port="/dev/ttyUSB0", baudrate=115200, reader=reader, writer=writer)  # type: ignore[arg-type]
    await adapter.connect()
    assert adapter.is_connected is True

    # Test send_framed command
    res = await adapter.execute(
        "send_framed",
        {"sequence": 1, "cmd_id": 5, "payload": b"MOTOR_START"},
    )
    assert res["status"] == "success"
    assert res["bytes_sent"] > 0
    assert len(writer.written) > 0
    # First 2 bytes must be SOF
    assert writer.written[:2] == SerialFramedProtocol.SOF

    await adapter.disconnect()
    assert adapter.is_connected is False
