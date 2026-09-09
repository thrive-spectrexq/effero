"""Tests for Live MQTT 3.1.1 protocol, wire codecs, loopback broker, and client."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from effero.adapters.mqtt_matter.client import MQTTAdapter, topic_matches
from effero.adapters.mqtt_matter.protocol import (
    ConnackPacket,
    ConnectPacket,
    DisconnectPacket,
    PacketType,
    PingreqPacket,
    PingrespPacket,
    PubackPacket,
    PubcompPacket,
    PublishPacket,
    PubrecPacket,
    PubrelPacket,
    SubackPacket,
    SubscribePacket,
    UnsubackPacket,
    UnsubscribePacket,
    decode_bytes,
    decode_packet,
    decode_string,
    decode_varint,
    encode_bytes,
    encode_packet,
    encode_string,
    encode_varint,
)

# ===========================================================================
# 1. Wire Codec Unit Tests
# ===========================================================================


def test_varint_encoding_decoding_boundaries():
    """Test variable-byte integer encoding/decoding across 1, 2, 3, 4 byte boundaries."""
    test_values = [
        (0, 1),
        (1, 1),
        (127, 1),
        (128, 2),
        (16383, 2),
        (16384, 3),
        (2097151, 3),
        (2097152, 4),
        (268435455, 4),
    ]
    for val, expected_len in test_values:
        encoded = encode_varint(val)
        assert len(encoded) == expected_len, f"Value {val} expected len {expected_len}, got {len(encoded)}"
        decoded, consumed = decode_varint(encoded)
        assert decoded == val
        assert consumed == expected_len

    # Test out of range
    with pytest.raises(ValueError, match="out of range"):
        encode_varint(-1)
    with pytest.raises(ValueError, match="out of range"):
        encode_varint(268435456)


def test_string_and_bytes_codecs():
    """Test length-prefixed UTF-8 string and binary byte codecs."""
    s = "effero/sensors/living_room"
    enc_s = encode_string(s)
    dec_s, consumed = decode_string(enc_s)
    assert dec_s == s
    assert consumed == len(enc_s)

    b = b"\x00\x01\xfe\xff\x42"
    enc_b = encode_bytes(b)
    dec_b, consumed_b = decode_bytes(enc_b)
    assert dec_b == b
    assert consumed_b == len(enc_b)


def test_packet_framing_all_types():
    """Verify round-trip encoding and decoding for all MQTT 3.1.1 packet types."""
    # CONNECT
    connect = ConnectPacket(
        client_id="effero_test_client",
        clean_session=True,
        keep_alive=120,
        username="user1",
        password="secret_password",
        will_topic="status/offline",
        will_message=b"node died",
        will_qos=1,
        will_retain=True,
    )
    raw = encode_packet(connect)
    decoded, consumed = decode_packet(raw)
    assert consumed == len(raw)
    assert isinstance(decoded, ConnectPacket)
    assert decoded.client_id == "effero_test_client"
    assert decoded.clean_session is True
    assert decoded.keep_alive == 120
    assert decoded.username == "user1"
    assert decoded.password == "secret_password"
    assert decoded.will_topic == "status/offline"
    assert decoded.will_message == b"node died"
    assert decoded.will_qos == 1
    assert decoded.will_retain is True

    # CONNACK
    connack = ConnackPacket(session_present=True, return_code=0)
    raw = encode_packet(connack)
    decoded, consumed = decode_packet(raw)
    assert consumed == len(raw)
    assert isinstance(decoded, ConnackPacket)
    assert decoded.session_present is True
    assert decoded.return_code == 0

    # PUBLISH QoS 0
    pub0 = PublishPacket(topic="home/garden/temp", payload=b"25.4", qos=0, retain=False)
    raw = encode_packet(pub0)
    decoded, consumed = decode_packet(raw)
    assert consumed == len(raw)
    assert isinstance(decoded, PublishPacket)
    assert decoded.topic == "home/garden/temp"
    assert decoded.payload == b"25.4"
    assert decoded.qos == 0
    assert decoded.packet_id is None

    # PUBLISH QoS 1 with DUP
    pub1 = PublishPacket(topic="home/garden/temp", payload=b"26.1", qos=1, packet_id=42, dup=True, retain=True)
    raw = encode_packet(pub1)
    decoded, consumed = decode_packet(raw)
    assert consumed == len(raw)
    assert isinstance(decoded, PublishPacket)
    assert decoded.topic == "home/garden/temp"
    assert decoded.qos == 1
    assert decoded.packet_id == 42
    assert decoded.dup is True
    assert decoded.retain is True

    # PUBLISH QoS 2
    pub2 = PublishPacket(topic="home/command", payload=b'{"action":"arm"}', qos=2, packet_id=101)
    raw = encode_packet(pub2)
    decoded, consumed = decode_packet(raw)
    assert consumed == len(raw)
    assert isinstance(decoded, PublishPacket)
    assert decoded.qos == 2
    assert decoded.packet_id == 101

    # PUBACK
    puback = PubackPacket(packet_id=42)
    raw = encode_packet(puback)
    decoded, consumed = decode_packet(raw)
    assert consumed == len(raw)
    assert isinstance(decoded, PubackPacket)
    assert decoded.packet_id == 42

    # PUBREC
    pubrec = PubrecPacket(packet_id=101)
    raw = encode_packet(pubrec)
    decoded, consumed = decode_packet(raw)
    assert consumed == len(raw)
    assert isinstance(decoded, PubrecPacket)
    assert decoded.packet_id == 101

    # PUBREL
    pubrel = PubrelPacket(packet_id=101)
    raw = encode_packet(pubrel)
    decoded, consumed = decode_packet(raw)
    assert consumed == len(raw)
    assert isinstance(decoded, PubrelPacket)
    assert decoded.packet_id == 101

    # PUBCOMP
    pubcomp = PubcompPacket(packet_id=101)
    raw = encode_packet(pubcomp)
    decoded, consumed = decode_packet(raw)
    assert consumed == len(raw)
    assert isinstance(decoded, PubcompPacket)
    assert decoded.packet_id == 101

    # SUBSCRIBE
    sub = SubscribePacket(packet_id=15, topics=[("home/+/temp", 1), ("sensors/#", 2)])
    raw = encode_packet(sub)
    decoded, consumed = decode_packet(raw)
    assert consumed == len(raw)
    assert isinstance(decoded, SubscribePacket)
    assert decoded.packet_id == 15
    assert decoded.topics == [("home/+/temp", 1), ("sensors/#", 2)]

    # SUBACK
    suback = SubackPacket(packet_id=15, return_codes=[1, 2])
    raw = encode_packet(suback)
    decoded, consumed = decode_packet(raw)
    assert consumed == len(raw)
    assert isinstance(decoded, SubackPacket)
    assert decoded.packet_id == 15
    assert decoded.return_codes == [1, 2]

    # UNSUBSCRIBE
    unsub = UnsubscribePacket(packet_id=16, topics=["home/+/temp", "sensors/#"])
    raw = encode_packet(unsub)
    decoded, consumed = decode_packet(raw)
    assert consumed == len(raw)
    assert isinstance(decoded, UnsubscribePacket)
    assert decoded.packet_id == 16
    assert decoded.topics == ["home/+/temp", "sensors/#"]

    # UNSUBACK
    unsuback = UnsubackPacket(packet_id=16)
    raw = encode_packet(unsuback)
    decoded, consumed = decode_packet(raw)
    assert consumed == len(raw)
    assert isinstance(decoded, UnsubackPacket)
    assert decoded.packet_id == 16

    # PINGREQ & PINGRESP
    pingreq = PingreqPacket()
    raw = encode_packet(pingreq)
    decoded, consumed = decode_packet(raw)
    assert consumed == 2
    assert isinstance(decoded, PingreqPacket)

    pingresp = PingrespPacket()
    raw = encode_packet(pingresp)
    decoded, consumed = decode_packet(raw)
    assert consumed == 2
    assert isinstance(decoded, PingrespPacket)

    # DISCONNECT
    disc = DisconnectPacket()
    raw = encode_packet(disc)
    decoded, consumed = decode_packet(raw)
    assert consumed == 2
    assert isinstance(decoded, DisconnectPacket)


def test_decode_partial_buffer():
    """Verify that decoder returns (None, 0) on partial buffers."""
    pub = PublishPacket(topic="a/b", payload=b"hello world", qos=0)
    raw = encode_packet(pub)
    for i in range(1, len(raw) - 1):
        decoded, consumed = decode_packet(raw[:i])
        assert decoded is None
        assert consumed == 0


# ===========================================================================
# 2. Topic Filter Wildcard Matching Unit Tests
# ===========================================================================


def test_topic_wildcard_matching():
    """Test standard MQTT 3.1.1 topic filter wildcard matching rules."""
    # Exact match
    assert topic_matches("home/living/temp", "home/living/temp") is True
    assert topic_matches("home/living/temp", "home/living/humidity") is False

    # Single-level wildcard '+'
    assert topic_matches("home/+/temp", "home/living/temp") is True
    assert topic_matches("home/+/temp", "home/kitchen/temp") is True
    assert topic_matches("home/+/temp", "home/living/bedroom/temp") is False
    assert topic_matches("home/+/temp", "home/temp") is False
    assert topic_matches("+/+", "home/living") is True
    assert topic_matches("+/+", "home") is False
    assert topic_matches("+", "home") is True

    # Multi-level wildcard '#'
    assert topic_matches("#", "home") is True
    assert topic_matches("#", "home/living/temp/sensor1") is True
    assert topic_matches("home/#", "home") is True
    assert topic_matches("home/#", "home/living") is True
    assert topic_matches("home/#", "home/living/temp") is True
    assert topic_matches("home/living/#", "home/living/temp") is True
    assert topic_matches("home/kitchen/#", "home/living/temp") is False

    # System topics starting with '$'
    assert topic_matches("#", "$SYS/broker/version") is False
    assert topic_matches("+/broker/version", "$SYS/broker/version") is False
    assert topic_matches("$SYS/#", "$SYS/broker/version") is True


# ===========================================================================
# 3. In-Memory Loopback TCP MQTT Broker & Live Client Tests
# ===========================================================================


class LoopbackMQTTBroker:
    """Minimal genuine TCP MQTT 3.1.1 broker for in-process network testing."""

    def __init__(self, host: str = "127.0.0.1"):
        self.host = host
        self.port = 0
        self.server: asyncio.Server | None = None
        self.clients: set[asyncio.StreamWriter] = set()
        self.subscriptions: dict[asyncio.StreamWriter, list[str]] = {}
        self.received_publishes: list[PublishPacket] = []

    async def handle_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        self.clients.add(writer)
        self.subscriptions[writer] = []
        buf = bytearray()
        try:
            while True:
                chunk = await reader.read(4096)
                if not chunk:
                    break
                buf.extend(chunk)
                while buf:
                    try:
                        packet, consumed = decode_packet(bytes(buf))
                    except ValueError:
                        buf.clear()
                        break
                    if packet is None or consumed == 0:
                        break
                    del buf[:consumed]

                    ptype = getattr(packet, "packet_type", None)
                    if ptype == PacketType.CONNECT:
                        connack = ConnackPacket(session_present=False, return_code=0)
                        writer.write(encode_packet(connack))
                        await writer.drain()

                    elif ptype == PacketType.SUBSCRIBE:
                        for top, _ in packet.topics or []:
                            self.subscriptions[writer].append(top)
                        suback = SubackPacket(packet_id=packet.packet_id, return_codes=[0] * len(packet.topics or []))
                        writer.write(encode_packet(suback))
                        await writer.drain()

                    elif ptype == PacketType.PUBLISH:
                        self.received_publishes.append(packet)
                        # Acknowledge QoS 1
                        if packet.qos == 1:
                            puback = PubackPacket(packet_id=packet.packet_id)
                            writer.write(encode_packet(puback))
                            await writer.drain()
                        elif packet.qos == 2:
                            # 4-way handshake step 1: send PUBREC
                            pubrec = PubrecPacket(packet_id=packet.packet_id)
                            writer.write(encode_packet(pubrec))
                            await writer.drain()

                        # Fan out to matching subscribers
                        for client_w, filters in list(self.subscriptions.items()):
                            if any(topic_matches(f, packet.topic) for f in filters):
                                # Forward message (QoS 0 for test broadcast)
                                fwd = PublishPacket(topic=packet.topic, payload=packet.payload, qos=0)
                                client_w.write(encode_packet(fwd))
                                await client_w.drain()

                    elif ptype == PacketType.PUBREL:
                        # 4-way handshake step 2: reply with PUBCOMP
                        pubcomp = PubcompPacket(packet_id=packet.packet_id)
                        writer.write(encode_packet(pubcomp))
                        await writer.drain()

                    elif ptype == PacketType.PINGREQ:
                        writer.write(encode_packet(PingrespPacket()))
                        await writer.drain()

                    elif ptype == PacketType.DISCONNECT:
                        break
        except Exception:
            pass
        finally:
            self.clients.discard(writer)
            self.subscriptions.pop(writer, None)
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:
                pass

    async def start(self) -> int:
        self.server = await asyncio.start_server(self.handle_client, self.host, 0)
        sock = self.server.sockets[0]
        self.port = sock.getsockname()[1]
        return self.port

    async def stop(self) -> None:
        if self.server:
            self.server.close()
            await self.server.wait_closed()
        for w in list(self.clients):
            w.close()
            try:
                await w.wait_closed()
            except Exception:
                pass
        self.clients.clear()
        self.subscriptions.clear()


@pytest.mark.asyncio
async def test_live_mqtt_loopback_pubsub_and_wildcards():
    """Test live MQTTAdapter connecting to TCP broker, subscribing with wildcards, and publishing."""
    broker = LoopbackMQTTBroker()
    port = await broker.start()

    client = MQTTAdapter(broker_host="127.0.0.1", broker_port=port, keep_alive=10)
    try:
        await client.connect()
        assert client.is_connected is True

        received_events: list[tuple[str, Any]] = []

        async def on_temp_event(topic: str, payload: Any) -> None:
            received_events.append((topic, payload))

        # Subscribe with single-level wildcard
        await client.subscribe("home/+/temperature", on_temp_event)

        # Publish matching topic
        await client.publish("home/living_room/temperature", {"val": 22.5})
        # Allow event loop dispatch
        await asyncio.sleep(0.1)

        assert len(received_events) == 1
        assert received_events[0][0] == "home/living_room/temperature"
        assert received_events[0][1] == {"val": 22.5}

        # Publish non-matching topic
        await client.publish("home/living_room/humidity", {"val": 55})
        await asyncio.sleep(0.05)
        assert len(received_events) == 1  # Unchanged

        # Test state cache
        state = await client.read_state()
        assert "home/living_room/temperature" in state

    finally:
        await client.disconnect()
        await broker.stop()


@pytest.mark.asyncio
async def test_live_mqtt_qos1_qos2_delivery_acknowledgment():
    """Test QoS 1 and QoS 2 delivery acknowledgment handshake over live loopback TCP."""
    broker = LoopbackMQTTBroker()
    port = await broker.start()

    client = MQTTAdapter(broker_host="127.0.0.1", broker_port=port)
    try:
        await client.connect()

        # QoS 1 publish (waits for PUBACK)
        await client.publish("alerts/fire", {"severity": "critical"}, qos=1, timeout=2.0)
        assert any(p.topic == "alerts/fire" and p.qos == 1 for p in broker.received_publishes)

        # QoS 2 publish (executes 4-way handshake: PUBLISH -> PUBREC -> PUBREL -> PUBCOMP)
        await client.publish("config/reboot", {"force": True}, qos=2, timeout=2.0)
        assert any(p.topic == "config/reboot" and p.qos == 2 for p in broker.received_publishes)

    finally:
        await client.disconnect()
        await broker.stop()


@pytest.mark.asyncio
async def test_live_mqtt_client_execute_adapter_interface():
    """Test standard DeviceAdapter execute() interface on MQTTAdapter."""
    broker = LoopbackMQTTBroker()
    port = await broker.start()

    client = MQTTAdapter(broker_host="127.0.0.1", broker_port=port)
    try:
        await client.connect()

        res = await client.execute("publish", {"topic": "cmd/test", "payload": {"status": "ok"}, "qos": 0})
        assert res["status"] == "success"
        assert res["topic"] == "cmd/test"

        res_sub = await client.execute("subscribe", {"topic": "cmd/test"})
        assert res_sub["status"] == "success"

        res_state = await client.execute("read_state", {})
        assert res_state["status"] == "success"
        assert "cmd/test" in res_state["state"]

    finally:
        await client.disconnect()
        await broker.stop()


@pytest.mark.asyncio
async def test_live_mqtt_auto_reconnect():
    """Test MQTTAdapter automatic reconnection watchdog when broker connection breaks and restarts."""
    broker = LoopbackMQTTBroker()
    port = await broker.start()

    client = MQTTAdapter(
        broker_host="127.0.0.1",
        broker_port=port,
        auto_reconnect=True,
        base_reconnect_delay=0.1,
        max_reconnect_delay=0.5,
        reconnect_jitter=0.05,
    )
    try:
        await client.connect()
        assert client.is_connected is True

        # Register subscription
        messages = []
        await client.subscribe("reconnect/topic", lambda t, p: messages.append(p))

        # Sever connection by closing active socket on broker
        for w in list(broker.clients):
            w.close()
            try:
                await w.wait_closed()
            except Exception:
                pass

        await asyncio.sleep(0.05)
        assert client.is_connected is False

        # Wait for client watchdog to reconnect
        for _ in range(50):
            if client.is_connected:
                break
            await asyncio.sleep(0.1)

        assert client.is_connected is True

        # Verify resubscription worked after reconnect
        await client.publish("reconnect/topic", {"reconnected": True})
        await asyncio.sleep(0.1)
        assert len(messages) >= 1

    finally:
        await client.disconnect()
        await broker.stop()
