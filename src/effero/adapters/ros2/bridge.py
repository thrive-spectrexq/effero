"""ROS 2 adapter and Common Data Representation (CDR) serializer."""

from __future__ import annotations

import asyncio
import logging
import struct
from dataclasses import dataclass, field
from typing import Any

from effero.adapters.base import DeviceAdapter

logger = logging.getLogger(__name__)


# =============================================================================
# ROS 2 Message Definitions
# =============================================================================


@dataclass
class Header:
    """Standard ROS 2 std_msgs/Header."""

    stamp_sec: int = 0
    stamp_nanosec: int = 0
    frame_id: str = ""


@dataclass
class JointState:
    """ROS 2 sensor_msgs/JointState."""

    header: Header = field(default_factory=Header)
    name: list[str] = field(default_factory=list)
    position: list[float] = field(default_factory=list)
    velocity: list[float] = field(default_factory=list)
    effort: list[float] = field(default_factory=list)


@dataclass
class JointTrajectoryPoint:
    """ROS 2 trajectory_msgs/JointTrajectoryPoint."""

    positions: list[float] = field(default_factory=list)
    velocities: list[float] = field(default_factory=list)
    accelerations: list[float] = field(default_factory=list)
    effort: list[float] = field(default_factory=list)
    time_from_start_sec: int = 0
    time_from_start_nanosec: int = 0


@dataclass
class JointTrajectory:
    """ROS 2 trajectory_msgs/JointTrajectory."""

    header: Header = field(default_factory=Header)
    joint_names: list[str] = field(default_factory=list)
    points: list[JointTrajectoryPoint] = field(default_factory=list)


@dataclass
class ActuatorCommand:
    """Effero custom ROS 2 actuator command message."""

    actuator_id: int = 1
    command_type: str = "position"
    target_position: float = 0.0
    target_velocity: float = 0.0
    max_torque: float = 1.0


# =============================================================================
# OMG CDR Serialization Engine
# =============================================================================


class CDREncoder:
    """Encodes ROS 2 messages to OMG Common Data Representation (CDR) little-endian wire format."""

    def __init__(self) -> None:
        # Standard CDR Encapsulation Header: [0x00, 0x01 (CDR_LE), 0x00, 0x00 (options)]
        self._buf = bytearray(b"\x00\x01\x00\x00")

    @property
    def payload_offset(self) -> int:
        return len(self._buf) - 4

    def pad(self, alignment: int) -> None:
        rem = self.payload_offset % alignment
        if rem != 0:
            self._buf.extend(b"\x00" * (alignment - rem))

    def write_int8(self, val: int) -> None:
        self._buf.extend(struct.pack("<b", val))

    def write_uint8(self, val: int) -> None:
        self._buf.extend(struct.pack("<B", val))

    def write_int32(self, val: int) -> None:
        self.pad(4)
        self._buf.extend(struct.pack("<i", val))

    def write_uint32(self, val: int) -> None:
        self.pad(4)
        self._buf.extend(struct.pack("<I", val))

    def write_float64(self, val: float) -> None:
        self.pad(8)
        self._buf.extend(struct.pack("<d", val))

    def write_string(self, s: str) -> None:
        raw = s.encode("utf-8") + b"\x00"
        self.pad(4)
        self._buf.extend(struct.pack("<I", len(raw)))
        self._buf.extend(raw)

    def write_sequence_string(self, strings: list[str]) -> None:
        self.pad(4)
        self._buf.extend(struct.pack("<I", len(strings)))
        for s in strings:
            self.write_string(s)

    def write_sequence_float64(self, floats: list[float]) -> None:
        self.pad(4)
        self._buf.extend(struct.pack("<I", len(floats)))
        for f in floats:
            self.write_float64(f)

    def to_bytes(self) -> bytes:
        return bytes(self._buf)


class CDRDecoder:
    """Decodes OMG Common Data Representation (CDR) little-endian wire format."""

    def __init__(self, data: bytes) -> None:
        if len(data) < 4:
            raise ValueError(f"CDR buffer too small: {len(data)} bytes")
        if data[:2] != b"\x00\x01":
            raise ValueError(f"Unsupported CDR encapsulation header: {data[:4].hex()}")

        self._data = data
        self._idx = 4  # Start after 4-byte encapsulation header

    @property
    def payload_offset(self) -> int:
        return self._idx - 4

    def align(self, alignment: int) -> None:
        rem = self.payload_offset % alignment
        if rem != 0:
            self._idx += alignment - rem

    def read_int8(self) -> int:
        val = struct.unpack_from("<b", self._data, self._idx)[0]
        self._idx += 1
        return val

    def read_uint8(self) -> int:
        val = struct.unpack_from("<B", self._data, self._idx)[0]
        self._idx += 1
        return val

    def read_int32(self) -> int:
        self.align(4)
        val = struct.unpack_from("<i", self._data, self._idx)[0]
        self._idx += 4
        return val

    def read_uint32(self) -> int:
        self.align(4)
        val = struct.unpack_from("<I", self._data, self._idx)[0]
        self._idx += 4
        return val

    def read_float64(self) -> float:
        self.align(8)
        val = struct.unpack_from("<d", self._data, self._idx)[0]
        self._idx += 8
        return val

    def read_string(self) -> str:
        length = self.read_uint32()
        raw = self._data[self._idx : self._idx + length]
        self._idx += length
        # Strip trailing null byte
        if raw.endswith(b"\x00"):
            raw = raw[:-1]
        return raw.decode("utf-8")

    def read_sequence_string(self) -> list[str]:
        count = self.read_uint32()
        return [self.read_string() for _ in range(count)]

    def read_sequence_float64(self) -> list[float]:
        count = self.read_uint32()
        return [self.read_float64() for _ in range(count)]


class ROS2CDRSerializer:
    """Serializer and deserializer for standard and custom ROS 2 messages using CDR wire format."""

    @classmethod
    def serialize_header(cls, enc: CDREncoder, header: Header) -> None:
        enc.write_int32(header.stamp_sec)
        enc.write_uint32(header.stamp_nanosec)
        enc.write_string(header.frame_id)

    @classmethod
    def deserialize_header(cls, dec: CDRDecoder) -> Header:
        sec = dec.read_int32()
        nsec = dec.read_uint32()
        frame = dec.read_string()
        return Header(stamp_sec=sec, stamp_nanosec=nsec, frame_id=frame)

    @classmethod
    def serialize_joint_state(cls, msg: JointState) -> bytes:
        enc = CDREncoder()
        cls.serialize_header(enc, msg.header)
        enc.write_sequence_string(msg.name)
        enc.write_sequence_float64(msg.position)
        enc.write_sequence_float64(msg.velocity)
        enc.write_sequence_float64(msg.effort)
        return enc.to_bytes()

    @classmethod
    def deserialize_joint_state(cls, data: bytes) -> JointState:
        dec = CDRDecoder(data)
        header = cls.deserialize_header(dec)
        names = dec.read_sequence_string()
        pos = dec.read_sequence_float64()
        vel = dec.read_sequence_float64()
        eff = dec.read_sequence_float64()
        return JointState(
            header=header,
            name=names,
            position=pos,
            velocity=vel,
            effort=eff,
        )

    @classmethod
    def serialize_joint_trajectory_point(cls, enc: CDREncoder, pt: JointTrajectoryPoint) -> None:
        enc.write_sequence_float64(pt.positions)
        enc.write_sequence_float64(pt.velocities)
        enc.write_sequence_float64(pt.accelerations)
        enc.write_sequence_float64(pt.effort)
        enc.write_int32(pt.time_from_start_sec)
        enc.write_uint32(pt.time_from_start_nanosec)

    @classmethod
    def deserialize_joint_trajectory_point(cls, dec: CDRDecoder) -> JointTrajectoryPoint:
        pos = dec.read_sequence_float64()
        vel = dec.read_sequence_float64()
        acc = dec.read_sequence_float64()
        eff = dec.read_sequence_float64()
        sec = dec.read_int32()
        nsec = dec.read_uint32()
        return JointTrajectoryPoint(
            positions=pos,
            velocities=vel,
            accelerations=acc,
            effort=eff,
            time_from_start_sec=sec,
            time_from_start_nanosec=nsec,
        )

    @classmethod
    def serialize_joint_trajectory(cls, msg: JointTrajectory) -> bytes:
        enc = CDREncoder()
        cls.serialize_header(enc, msg.header)
        enc.write_sequence_string(msg.joint_names)
        enc.pad(4)
        enc.write_uint32(len(msg.points))
        for pt in msg.points:
            cls.serialize_joint_trajectory_point(enc, pt)
        return enc.to_bytes()

    @classmethod
    def deserialize_joint_trajectory(cls, data: bytes) -> JointTrajectory:
        dec = CDRDecoder(data)
        header = cls.deserialize_header(dec)
        names = dec.read_sequence_string()
        num_pts = dec.read_uint32()
        pts = [cls.deserialize_joint_trajectory_point(dec) for _ in range(num_pts)]
        return JointTrajectory(
            header=header,
            joint_names=names,
            points=pts,
        )

    @classmethod
    def serialize_actuator_command(cls, msg: ActuatorCommand) -> bytes:
        enc = CDREncoder()
        enc.write_int32(msg.actuator_id)
        enc.write_string(msg.command_type)
        enc.write_float64(msg.target_position)
        enc.write_float64(msg.target_velocity)
        enc.write_float64(msg.max_torque)
        return enc.to_bytes()

    @classmethod
    def deserialize_actuator_command(cls, data: bytes) -> ActuatorCommand:
        dec = CDRDecoder(data)
        actuator_id = dec.read_int32()
        command_type = dec.read_string()
        target_pos = dec.read_float64()
        target_vel = dec.read_float64()
        max_torque = dec.read_float64()
        return ActuatorCommand(
            actuator_id=actuator_id,
            command_type=command_type,
            target_position=target_pos,
            target_velocity=target_vel,
            max_torque=max_torque,
        )


# =============================================================================
# Real ROS 2 Async Communication Bridge
# =============================================================================


class ROS2Bridge(DeviceAdapter):
    """Real communication bridge between Effero and ROS 2 nodes over socket or serial streams."""

    def __init__(
        self,
        node_name: str = "effero_bridge",
        reader: asyncio.StreamReader | None = None,
        writer: asyncio.StreamWriter | None = None,
    ) -> None:
        self.node_name = node_name
        self._reader: asyncio.StreamReader | None = reader
        self._writer: asyncio.StreamWriter | None = writer
        self._connected: bool = bool(reader and writer)
        self._actions: dict[str, str] = {}
        self._topics: dict[str, str] = {}
        self._published_count: int = 0
        self._latest_joint_state: dict[str, Any] | None = None

    @property
    def is_connected(self) -> bool:
        return self._connected and self._writer is not None

    async def connect(
        self,
        host: str = "127.0.0.1",
        port: int = 9090,
    ) -> None:
        """Connect to real ROS 2 bridge socket daemon or verify injected stream."""
        if self._reader is not None and self._writer is not None:
            self._connected = True
            logger.info(f"ROS 2 node '{self.node_name}' stream connected")
            return

        try:
            self._reader, self._writer = await asyncio.open_connection(host, port)
            self._connected = True
            logger.info(f"ROS 2 node '{self.node_name}' connected to {host}:{port}")
        except Exception as err:
            self._connected = False
            logger.warning(f"Could not connect to ROS 2 bridge at {host}:{port}: {err}")
            raise RuntimeError(f"ROS 2 bridge connection failed: {err}") from err

    async def disconnect(self) -> None:
        """Disconnect and close transport streams."""
        if self._writer:
            self._writer.close()
            try:
                await self._writer.wait_closed()
            except Exception:
                pass
            self._writer = None
            self._reader = None
        self._connected = False
        logger.info(f"ROS 2 node '{self.node_name}' disconnected")

    async def publish_joint_state(self, joint_state: JointState) -> bytes:
        """Serialize JointState to CDR format and send to ROS 2 transport."""
        data = ROS2CDRSerializer.serialize_joint_state(joint_state)
        if self.is_connected and self._writer:
            # Send length-prefixed frame: 4 bytes uint32 length + CDR data
            self._writer.write(struct.pack(">I", len(data)) + data)
            await self._writer.drain()

        self._published_count += 1
        self._latest_joint_state = {
            "names": joint_state.name,
            "positions": joint_state.position,
            "velocities": joint_state.velocity,
        }
        return data

    async def publish_trajectory(self, trajectory: JointTrajectory) -> bytes:
        """Serialize JointTrajectory to CDR format and send to ROS 2 transport."""
        data = ROS2CDRSerializer.serialize_joint_trajectory(trajectory)
        if self.is_connected and self._writer:
            self._writer.write(struct.pack(">I", len(data)) + data)
            await self._writer.drain()

        self._published_count += 1
        return data

    async def send_actuator_command(self, command: ActuatorCommand) -> bytes:
        """Serialize ActuatorCommand to CDR format and send to ROS 2 transport."""
        data = ROS2CDRSerializer.serialize_actuator_command(command)
        if self.is_connected and self._writer:
            self._writer.write(struct.pack(">I", len(data)) + data)
            await self._writer.drain()

        self._published_count += 1
        return data

    async def execute(self, command: str, params: dict[str, Any]) -> Any:
        """Execute ROS 2 action or command."""
        if command == "publish_joint_state":
            js = JointState(
                header=Header(frame_id=params.get("frame_id", "base_link")),
                name=params.get("names", []),
                position=params.get("positions", []),
                velocity=params.get("velocities", []),
                effort=params.get("effort", []),
            )
            raw_cdr = await self.publish_joint_state(js)
            return {
                "status": "success",
                "command": command,
                "bytes_serialized": len(raw_cdr),
                "joint_names": js.name,
            }

        elif command == "actuator_command":
            cmd = ActuatorCommand(
                actuator_id=params.get("actuator_id", 1),
                command_type=params.get("command_type", "position"),
                target_position=params.get("position", 0.0),
                target_velocity=params.get("velocity", 0.0),
                max_torque=params.get("max_torque", 1.0),
            )
            raw_cdr = await self.send_actuator_command(cmd)
            return {
                "status": "success",
                "command": command,
                "actuator_id": cmd.actuator_id,
                "bytes_serialized": len(raw_cdr),
            }

        elif command in self._actions:
            skill_target = self._actions[command]
            return {
                "status": "success",
                "action": command,
                "routed_skill": skill_target,
                "params": params,
            }

        else:
            raise ValueError(f"Unknown or unsupported ROS 2 command: '{command}'")

    async def read_state(self) -> dict[str, Any]:
        """Read state of ROS 2 node."""
        return {
            "node": self.node_name,
            "connected": self.is_connected,
            "published_count": self._published_count,
            "latest_joint_state": self._latest_joint_state,
            "exposed_actions": list(self._actions.keys()),
            "exposed_topics": list(self._topics.keys()),
        }

    def expose_action(self, action_name: str, skill_name: str) -> None:
        self._actions[action_name] = skill_name
        logger.info(f"Exposed ROS 2 action {action_name} as skill {skill_name}")

    def expose_topic(self, topic_name: str, event_name: str) -> None:
        self._topics[topic_name] = event_name
        logger.info(f"Exposed ROS 2 topic {topic_name} as event {event_name}")
