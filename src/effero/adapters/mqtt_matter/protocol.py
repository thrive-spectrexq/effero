"""MQTT 3.1.1 binary wire protocol framing and packet codecs."""

from __future__ import annotations

import struct
from dataclasses import dataclass
from enum import IntEnum
from typing import Any


class PacketType(IntEnum):
    """MQTT 3.1.1 Control Packet Types."""

    CONNECT = 1
    CONNACK = 2
    PUBLISH = 3
    PUBACK = 4
    PUBREC = 5
    PUBREL = 6
    PUBCOMP = 7
    SUBSCRIBE = 8
    SUBACK = 9
    UNSUBSCRIBE = 10
    UNSUBACK = 11
    PINGREQ = 12
    PINGRESP = 13
    DISCONNECT = 14


def encode_varint(value: int) -> bytes:
    """Encode an integer as an MQTT variable-byte integer (1 to 4 bytes)."""
    if value < 0 or value > 268435455:
        raise ValueError(f"Varint value out of range (0..268435455): {value}")
    encoded = bytearray()
    while True:
        digit = value % 128
        value //= 128
        if value > 0:
            digit |= 0x80
        encoded.append(digit)
        if value == 0:
            break
    return bytes(encoded)


def decode_varint(buf: bytes, offset: int = 0) -> tuple[int, int]:
    """Decode an MQTT variable-byte integer from buffer starting at offset.

    Returns (value, bytes_consumed).
    Raises ValueError if buffer is incomplete or invalid.
    """
    multiplier = 1
    value = 0
    bytes_read = 0
    idx = offset
    while True:
        if idx >= len(buf):
            raise ValueError("Incomplete variable-byte integer in buffer")
        encoded_byte = buf[idx]
        idx += 1
        bytes_read += 1
        value += (encoded_byte & 0x7F) * multiplier
        multiplier *= 128
        if (encoded_byte & 0x80) == 0:
            break
        if bytes_read >= 4:
            raise ValueError("Malformed variable-byte integer: exceeds 4 bytes")
    return value, bytes_read


def encode_string(s: str) -> bytes:
    """Encode a UTF-8 string with a 2-byte big-endian length prefix."""
    encoded = s.encode("utf-8")
    if len(encoded) > 65535:
        raise ValueError(f"String length exceeds 65535 bytes: {len(encoded)}")
    return struct.pack("!H", len(encoded)) + encoded


def decode_string(buf: bytes, offset: int = 0) -> tuple[str, int]:
    """Decode a length-prefixed UTF-8 string from buffer at offset.

    Returns (string, bytes_consumed).
    """
    if len(buf) < offset + 2:
        raise ValueError("Incomplete string length header")
    (length,) = struct.unpack_from("!H", buf, offset)
    if len(buf) < offset + 2 + length:
        raise ValueError(f"Incomplete string data: expected {length} bytes")
    s = buf[offset + 2 : offset + 2 + length].decode("utf-8")
    return s, 2 + length


def encode_bytes(data: bytes) -> bytes:
    """Encode binary data with a 2-byte big-endian length prefix."""
    if len(data) > 65535:
        raise ValueError(f"Binary length exceeds 65535 bytes: {len(data)}")
    return struct.pack("!H", len(data)) + data


def decode_bytes(buf: bytes, offset: int = 0) -> tuple[bytes, int]:
    """Decode length-prefixed binary data from buffer at offset.

    Returns (bytes, bytes_consumed).
    """
    if len(buf) < offset + 2:
        raise ValueError("Incomplete binary length header")
    (length,) = struct.unpack_from("!H", buf, offset)
    if len(buf) < offset + 2 + length:
        raise ValueError(f"Incomplete binary data: expected {length} bytes")
    b = buf[offset + 2 : offset + 2 + length]
    return b, 2 + length


# ---------------------------------------------------------------------------
# Packet Data Structures
# ---------------------------------------------------------------------------


class MQTTPacket:
    """Base class for all MQTT control packets."""

    packet_type: PacketType

    def encode(self) -> bytes:
        raise NotImplementedError


@dataclass
class ConnectPacket(MQTTPacket):
    """MQTT CONNECT packet."""

    packet_type: PacketType = PacketType.CONNECT
    client_id: str = "effero_client"
    clean_session: bool = True
    keep_alive: int = 60
    username: str | None = None
    password: str | None = None
    will_topic: str | None = None
    will_message: bytes | None = None
    will_qos: int = 0
    will_retain: bool = False
    protocol_name: str = "MQTT"
    protocol_level: int = 4  # 3.1.1

    def encode(self) -> bytes:
        # Variable Header
        vh = bytearray()
        vh.extend(encode_string(self.protocol_name))
        vh.append(self.protocol_level)

        # Connect Flags
        flags = 0
        if self.username is not None:
            flags |= 0x80
        if self.password is not None:
            flags |= 0x40
        if self.will_retain:
            flags |= 0x20
        flags |= (self.will_qos & 0x03) << 3
        if self.will_topic is not None:
            flags |= 0x04
        if self.clean_session:
            flags |= 0x02
        vh.append(flags)
        vh.extend(struct.pack("!H", self.keep_alive))

        # Payload
        payload = bytearray()
        payload.extend(encode_string(self.client_id))
        if self.will_topic is not None:
            payload.extend(encode_string(self.will_topic))
            msg = self.will_message if self.will_message is not None else b""
            payload.extend(encode_bytes(msg))
        if self.username is not None:
            payload.extend(encode_string(self.username))
        if self.password is not None:
            payload.extend(encode_string(self.password))

        remaining = bytes(vh) + bytes(payload)
        header = bytes([(PacketType.CONNECT << 4) | 0x00]) + encode_varint(len(remaining))
        return header + remaining


@dataclass
class ConnackPacket(MQTTPacket):
    """MQTT CONNACK packet."""

    packet_type: PacketType = PacketType.CONNACK
    session_present: bool = False
    return_code: int = 0

    def encode(self) -> bytes:
        vh = bytes([1 if self.session_present else 0, self.return_code & 0xFF])
        header = bytes([(PacketType.CONNACK << 4) | 0x00]) + encode_varint(len(vh))
        return header + vh


@dataclass
class PublishPacket(MQTTPacket):
    """MQTT PUBLISH packet."""

    packet_type: PacketType = PacketType.PUBLISH
    topic: str = ""
    payload: bytes = b""
    qos: int = 0
    packet_id: int | None = None
    dup: bool = False
    retain: bool = False

    def encode(self) -> bytes:
        flags = 0
        if self.dup:
            flags |= 0x08
        flags |= (self.qos & 0x03) << 1
        if self.retain:
            flags |= 0x01

        vh = bytearray()
        vh.extend(encode_string(self.topic))
        if self.qos > 0:
            if self.packet_id is None:
                raise ValueError("packet_id is required for QoS > 0")
            vh.extend(struct.pack("!H", self.packet_id))

        body = bytes(vh) + self.payload
        header = bytes([(PacketType.PUBLISH << 4) | flags]) + encode_varint(len(body))
        return header + body


@dataclass
class PubackPacket(MQTTPacket):
    """MQTT PUBACK packet (QoS 1 acknowledgment)."""

    packet_type: PacketType = PacketType.PUBACK
    packet_id: int = 0

    def encode(self) -> bytes:
        vh = struct.pack("!H", self.packet_id)
        header = bytes([(PacketType.PUBACK << 4) | 0x00]) + encode_varint(len(vh))
        return header + vh


@dataclass
class PubrecPacket(MQTTPacket):
    """MQTT PUBREC packet (QoS 2 publish received)."""

    packet_type: PacketType = PacketType.PUBREC
    packet_id: int = 0

    def encode(self) -> bytes:
        vh = struct.pack("!H", self.packet_id)
        header = bytes([(PacketType.PUBREC << 4) | 0x00]) + encode_varint(len(vh))
        return header + vh


@dataclass
class PubrelPacket(MQTTPacket):
    """MQTT PUBREL packet (QoS 2 publish release)."""

    packet_type: PacketType = PacketType.PUBREL
    packet_id: int = 0

    def encode(self) -> bytes:
        # bit 1 is reserved and must be 1 for PUBREL
        flags = 0x02
        vh = struct.pack("!H", self.packet_id)
        header = bytes([(PacketType.PUBREL << 4) | flags]) + encode_varint(len(vh))
        return header + vh


@dataclass
class PubcompPacket(MQTTPacket):
    """MQTT PUBCOMP packet (QoS 2 publish complete)."""

    packet_type: PacketType = PacketType.PUBCOMP
    packet_id: int = 0

    def encode(self) -> bytes:
        vh = struct.pack("!H", self.packet_id)
        header = bytes([(PacketType.PUBCOMP << 4) | 0x00]) + encode_varint(len(vh))
        return header + vh


@dataclass
class SubscribePacket(MQTTPacket):
    """MQTT SUBSCRIBE packet."""

    packet_type: PacketType = PacketType.SUBSCRIBE
    packet_id: int = 1
    topics: list[tuple[str, int]] | None = None  # [(topic_filter, requested_qos)]

    def encode(self) -> bytes:
        flags = 0x02  # bit 1 must be 1
        vh = bytearray(struct.pack("!H", self.packet_id))
        if self.topics:
            for topic, qos in self.topics:
                vh.extend(encode_string(topic))
                vh.append(qos & 0x03)
        header = bytes([(PacketType.SUBSCRIBE << 4) | flags]) + encode_varint(len(vh))
        return header + bytes(vh)


@dataclass
class SubackPacket(MQTTPacket):
    """MQTT SUBACK packet."""

    packet_type: PacketType = PacketType.SUBACK
    packet_id: int = 0
    return_codes: list[int] | None = None

    def encode(self) -> bytes:
        vh = bytearray(struct.pack("!H", self.packet_id))
        if self.return_codes:
            for code in self.return_codes:
                vh.append(code & 0xFF)
        header = bytes([(PacketType.SUBACK << 4) | 0x00]) + encode_varint(len(vh))
        return header + bytes(vh)


@dataclass
class UnsubscribePacket(MQTTPacket):
    """MQTT UNSUBSCRIBE packet."""

    packet_type: PacketType = PacketType.UNSUBSCRIBE
    packet_id: int = 1
    topics: list[str] | None = None

    def encode(self) -> bytes:
        flags = 0x02  # bit 1 must be 1
        vh = bytearray(struct.pack("!H", self.packet_id))
        if self.topics:
            for topic in self.topics:
                vh.extend(encode_string(topic))
        header = bytes([(PacketType.UNSUBSCRIBE << 4) | flags]) + encode_varint(len(vh))
        return header + bytes(vh)


@dataclass
class UnsubackPacket(MQTTPacket):
    """MQTT UNSUBACK packet."""

    packet_type: PacketType = PacketType.UNSUBACK
    packet_id: int = 0

    def encode(self) -> bytes:
        vh = struct.pack("!H", self.packet_id)
        header = bytes([(PacketType.UNSUBACK << 4) | 0x00]) + encode_varint(len(vh))
        return header + vh


@dataclass
class PingreqPacket(MQTTPacket):
    """MQTT PINGREQ packet."""

    packet_type: PacketType = PacketType.PINGREQ

    def encode(self) -> bytes:
        return bytes([(PacketType.PINGREQ << 4) | 0x00, 0x00])


@dataclass
class PingrespPacket(MQTTPacket):
    """MQTT PINGRESP packet."""

    packet_type: PacketType = PacketType.PINGRESP

    def encode(self) -> bytes:
        return bytes([(PacketType.PINGRESP << 4) | 0x00, 0x00])


@dataclass
class DisconnectPacket(MQTTPacket):
    """MQTT DISCONNECT packet."""

    packet_type: PacketType = PacketType.DISCONNECT

    def encode(self) -> bytes:
        return bytes([(PacketType.DISCONNECT << 4) | 0x00, 0x00])


# ---------------------------------------------------------------------------
# Packet Decoding
# ---------------------------------------------------------------------------


def encode_packet(packet: MQTTPacket) -> bytes:
    """Serialize an MQTT packet into binary bytes."""
    return packet.encode()


def decode_packet(buffer: bytes) -> tuple[Any | None, int]:
    """Decode a single MQTT packet from the buffer.

    Returns:
        (packet, bytes_consumed) if a complete packet was parsed.
        (None, 0) if the buffer does not yet contain a full packet.

    Raises:
        ValueError if data violates protocol framing.
    """
    if len(buffer) < 2:
        return None, 0

    byte1 = buffer[0]
    packet_type_int = (byte1 >> 4) & 0x0F
    flags = byte1 & 0x0F

    try:
        packet_type = PacketType(packet_type_int)
    except ValueError as err:
        raise ValueError(f"Invalid MQTT packet type: {packet_type_int}") from err

    try:
        rem_len, varint_len = decode_varint(buffer, offset=1)
    except ValueError:
        # Incomplete varint length
        return None, 0

    total_len = 1 + varint_len + rem_len
    if len(buffer) < total_len:
        return None, 0

    packet_body = buffer[1 + varint_len : total_len]

    # Decode specific packet types
    if packet_type == PacketType.CONNECT:
        offset = 0
        proto_name, n = decode_string(packet_body, offset)
        offset += n
        proto_level = packet_body[offset]
        offset += 1
        c_flags = packet_body[offset]
        offset += 1
        (keep_alive,) = struct.unpack_from("!H", packet_body, offset)
        offset += 2

        clean_session = bool(c_flags & 0x02)
        will_flag = bool(c_flags & 0x04)
        will_qos = (c_flags >> 3) & 0x03
        will_retain = bool(c_flags & 0x20)
        password_flag = bool(c_flags & 0x40)
        username_flag = bool(c_flags & 0x80)

        client_id, n = decode_string(packet_body, offset)
        offset += n

        will_topic: str | None = None
        will_msg: bytes | None = None
        if will_flag:
            will_topic, n = decode_string(packet_body, offset)
            offset += n
            will_msg, n = decode_bytes(packet_body, offset)
            offset += n

        username: str | None = None
        if username_flag:
            username, n = decode_string(packet_body, offset)
            offset += n

        password: str | None = None
        if password_flag:
            password, n = decode_string(packet_body, offset)
            offset += n

        return (
            ConnectPacket(
                client_id=client_id,
                clean_session=clean_session,
                keep_alive=keep_alive,
                username=username,
                password=password,
                will_topic=will_topic,
                will_message=will_msg,
                will_qos=will_qos,
                will_retain=will_retain,
                protocol_name=proto_name,
                protocol_level=proto_level,
            ),
            total_len,
        )

    elif packet_type == PacketType.CONNACK:
        if len(packet_body) < 2:
            raise ValueError("CONNACK variable header too short")
        session_present = bool(packet_body[0] & 0x01)
        return_code = packet_body[1]
        return ConnackPacket(session_present=session_present, return_code=return_code), total_len

    elif packet_type == PacketType.PUBLISH:
        dup = bool(flags & 0x08)
        qos = (flags >> 1) & 0x03
        retain = bool(flags & 0x01)

        offset = 0
        topic, n = decode_string(packet_body, offset)
        offset += n

        packet_id: int | None = None
        if qos > 0:
            if len(packet_body) < offset + 2:
                raise ValueError("PUBLISH variable header missing packet ID")
            (packet_id,) = struct.unpack_from("!H", packet_body, offset)
            offset += 2

        payload = packet_body[offset:]
        return (
            PublishPacket(
                topic=topic,
                payload=payload,
                qos=qos,
                packet_id=packet_id,
                dup=dup,
                retain=retain,
            ),
            total_len,
        )

    elif packet_type == PacketType.PUBACK:
        if len(packet_body) < 2:
            raise ValueError("PUBACK variable header too short")
        (packet_id,) = struct.unpack_from("!H", packet_body, 0)
        return PubackPacket(packet_id=packet_id), total_len

    elif packet_type == PacketType.PUBREC:
        if len(packet_body) < 2:
            raise ValueError("PUBREC variable header too short")
        (packet_id,) = struct.unpack_from("!H", packet_body, 0)
        return PubrecPacket(packet_id=packet_id), total_len

    elif packet_type == PacketType.PUBREL:
        if len(packet_body) < 2:
            raise ValueError("PUBREL variable header too short")
        (packet_id,) = struct.unpack_from("!H", packet_body, 0)
        return PubrelPacket(packet_id=packet_id), total_len

    elif packet_type == PacketType.PUBCOMP:
        if len(packet_body) < 2:
            raise ValueError("PUBCOMP variable header too short")
        (packet_id,) = struct.unpack_from("!H", packet_body, 0)
        return PubcompPacket(packet_id=packet_id), total_len

    elif packet_type == PacketType.SUBSCRIBE:
        if len(packet_body) < 2:
            raise ValueError("SUBSCRIBE variable header too short")
        (packet_id,) = struct.unpack_from("!H", packet_body, 0)
        offset = 2
        topics: list[tuple[str, int]] = []
        while offset < len(packet_body):
            t_filter, n = decode_string(packet_body, offset)
            offset += n
            if offset >= len(packet_body):
                raise ValueError("SUBSCRIBE missing requested QoS for topic")
            req_qos = packet_body[offset] & 0x03
            offset += 1
            topics.append((t_filter, req_qos))
        return SubscribePacket(packet_id=packet_id, topics=topics), total_len

    elif packet_type == PacketType.SUBACK:
        if len(packet_body) < 2:
            raise ValueError("SUBACK variable header too short")
        (packet_id,) = struct.unpack_from("!H", packet_body, 0)
        offset = 2
        return_codes = [b for b in packet_body[offset:]]
        return SubackPacket(packet_id=packet_id, return_codes=return_codes), total_len

    elif packet_type == PacketType.UNSUBSCRIBE:
        if len(packet_body) < 2:
            raise ValueError("UNSUBSCRIBE variable header too short")
        (packet_id,) = struct.unpack_from("!H", packet_body, 0)
        offset = 2
        unsub_topics: list[str] = []
        while offset < len(packet_body):
            t_filter, n = decode_string(packet_body, offset)
            offset += n
            unsub_topics.append(t_filter)
        return UnsubscribePacket(packet_id=packet_id, topics=unsub_topics), total_len

    elif packet_type == PacketType.UNSUBACK:
        if len(packet_body) < 2:
            raise ValueError("UNSUBACK variable header too short")
        (packet_id,) = struct.unpack_from("!H", packet_body, 0)
        return UnsubackPacket(packet_id=packet_id), total_len

    elif packet_type == PacketType.PINGREQ:
        return PingreqPacket(), total_len

    elif packet_type == PacketType.PINGRESP:
        return PingrespPacket(), total_len

    elif packet_type == PacketType.DISCONNECT:
        return DisconnectPacket(), total_len

    raise ValueError(f"Unsupported packet type: {packet_type}")
