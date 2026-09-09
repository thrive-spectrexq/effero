"""Pure-asyncio Live MQTT 3.1.1 client with auto-reconnect, wildcard matching, and QoS 1/2."""

from __future__ import annotations

import asyncio
import json
import logging
import random
import ssl
import time
import uuid
from collections.abc import Awaitable, Callable
from typing import Any

from effero.adapters.base import DeviceAdapter
from effero.adapters.mqtt_matter.protocol import (
    ConnackPacket,
    ConnectPacket,
    DisconnectPacket,
    MQTTPacket,
    PacketType,
    PingreqPacket,
    PubackPacket,
    PubcompPacket,
    PublishPacket,
    PubrecPacket,
    PubrelPacket,
    SubscribePacket,
    UnsubscribePacket,
    decode_packet,
    encode_packet,
)

logger = logging.getLogger(__name__)


def topic_matches(topic_filter: str, topic_name: str) -> bool:
    """Check if a published topic matches an MQTT topic subscription filter per MQTT 3.1.1.

    Supports exact match, '+' single-level wildcard, and '#' multi-level wildcard.
    """
    if topic_filter == topic_name:
        return True
    if topic_filter == "#":
        return not topic_name.startswith("$")

    # If topic starts with $ (system internal), filter must also start with $
    if topic_name.startswith("$") and not topic_filter.startswith("$"):
        return False

    filter_levels = topic_filter.split("/")
    topic_levels = topic_name.split("/")

    f_len = len(filter_levels)
    t_len = len(topic_levels)

    for i in range(f_len):
        f_level = filter_levels[i]
        if f_level == "#":
            # Multi-level wildcard matches everything from this point onwards
            return True
        if i >= t_len:
            # Topic ran out of levels before filter
            return False
        t_level = topic_levels[i]
        if f_level == "+":
            continue
        if f_level != t_level:
            return False

    return f_len == t_len


class MQTTAdapter(DeviceAdapter):
    """Pure-asyncio Live MQTT 3.1.1 client.

    Operates directly over asyncio TCP sockets with zero external dependencies.
    Supports auto-reconnection, exponential backoff, wildcard topic filters (+, #),
    and QoS 1 & QoS 2 delivery acknowledgment handshakes.
    """

    def __init__(
        self,
        broker_host: str = "localhost",
        broker_port: int = 1883,
        client_id: str | None = None,
        username: str | None = None,
        password: str | None = None,
        keep_alive: int = 60,
        clean_session: bool = True,
        auto_reconnect: bool = True,
        base_reconnect_delay: float = 0.5,
        max_reconnect_delay: float = 15.0,
        reconnect_jitter: float = 0.2,
        use_tls: bool = False,
        ssl_context: ssl.SSLContext | None = None,
        ca_certs: str | None = None,
        certfile: str | None = None,
        keyfile: str | None = None,
        tls_insecure: bool = False,
    ) -> None:
        self.broker_host = broker_host
        self.broker_port = broker_port
        self.client_id = client_id or f"effero_{uuid.uuid4().hex[:8]}"
        self.username = username
        self.password = password
        self.keep_alive = keep_alive
        self.clean_session = clean_session
        self.auto_reconnect = auto_reconnect
        self.base_reconnect_delay = base_reconnect_delay
        self.max_reconnect_delay = max_reconnect_delay
        self.reconnect_jitter = reconnect_jitter
        self.use_tls = use_tls
        self.ssl_context = ssl_context
        self.ca_certs = ca_certs
        self.certfile = certfile
        self.keyfile = keyfile
        self.tls_insecure = tls_insecure

        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._connected: bool = False
        self._manual_disconnect: bool = False

        self._reader_task: asyncio.Task[None] | None = None
        self._keepalive_task: asyncio.Task[None] | None = None
        self._reconnect_task: asyncio.Task[None] | None = None

        # Subscriptions: topic_filter -> list of callbacks
        self._subscriptions: dict[str, list[Callable[[str, Any], Awaitable[None] | None]]] = {}
        self._subscriptions_qos: dict[str, int] = {}

        # Local device state cache
        self._state: dict[str, Any] = {}

        # 16-bit packet identifier tracking
        self._next_packet_id: int = 1
        self._send_lock = asyncio.Lock()

        # Inflight tracking
        self._inflight_publishes: dict[int, asyncio.Future[None]] = {}
        self._inflight_packets: dict[int, PublishPacket] = {}
        self._inflight_subscribes: dict[int, asyncio.Future[list[int]]] = {}
        self._inflight_unsubscribes: dict[int, asyncio.Future[None]] = {}
        self._connack_future: asyncio.Future[ConnackPacket] | None = None

        # Incoming QoS 2 message state: packet_id -> (PublishPacket)
        self._incoming_qos2_packets: dict[int, PublishPacket] = {}

        # Last communication timestamp
        self._last_packet_sent: float = 0.0

    @property
    def is_connected(self) -> bool:
        """Return True if currently connected to MQTT broker."""
        return self._connected and self._writer is not None and not self._writer.is_closing()

    def _get_next_packet_id(self) -> int:
        """Generate the next available 16-bit packet identifier (1..65535)."""
        pid = self._next_packet_id
        self._next_packet_id = (self._next_packet_id % 65535) + 1
        return pid

    async def connect(self) -> None:
        """Establish connection to MQTT broker."""
        self._manual_disconnect = False
        await self._establish_connection()

    async def _establish_connection(self) -> None:
        """Perform socket connection and MQTT CONNECT / CONNACK handshake."""
        if self._writer and not self._writer.is_closing():
            try:
                self._writer.close()
                await self._writer.wait_closed()
            except Exception:
                pass
        self._reader = None
        self._writer = None

        ssl_ctx = self.ssl_context
        if (self.use_tls or self.broker_port == 8883) and ssl_ctx is None:
            if self.tls_insecure:
                ssl_ctx = ssl._create_unverified_context()
            else:
                ssl_ctx = ssl.create_default_context(cafile=self.ca_certs)
            if self.certfile:
                ssl_ctx.load_cert_chain(certfile=self.certfile, keyfile=self.keyfile)

        tls_note = " (TLS enabled)" if ssl_ctx is not None else ""
        logger.info(f"Connecting to MQTT broker at {self.broker_host}:{self.broker_port}{tls_note}...")
        self._reader, self._writer = await asyncio.open_connection(
            self.broker_host, self.broker_port, ssl=ssl_ctx
        )

        # Send CONNECT packet
        conn_packet = ConnectPacket(
            client_id=self.client_id,
            clean_session=self.clean_session,
            keep_alive=self.keep_alive,
            username=self.username,
            password=self.password,
        )

        loop = asyncio.get_running_loop()
        self._connack_future = loop.create_future()

        # Start reader loop
        if self._reader_task and not self._reader_task.done():
            self._reader_task.cancel()
        self._reader_task = asyncio.create_task(self._read_loop())

        await self._send_packet(conn_packet)

        # Await CONNACK
        try:
            connack = await asyncio.wait_for(self._connack_future, timeout=10.0)
            if connack.return_code != 0:
                raise ConnectionRefusedError(f"MQTT connection rejected by broker with code {connack.return_code}")
            self._connected = True
            logger.info(f"Successfully connected to MQTT broker {self.broker_host}:{self.broker_port}")
        except Exception:
            self._connected = False
            if self._writer and not self._writer.is_closing():
                self._writer.close()
            raise
        finally:
            self._connack_future = None

        # Start keepalive heartbeat
        if self.keep_alive > 0:
            if self._keepalive_task and not self._keepalive_task.done():
                self._keepalive_task.cancel()
            self._keepalive_task = asyncio.create_task(self._keepalive_loop())

        # Resubscribe existing subscriptions
        if self._subscriptions:
            for topic, qos in self._subscriptions_qos.items():
                pid = self._get_next_packet_id()
                sub_pkt = SubscribePacket(packet_id=pid, topics=[(topic, qos)])
                await self._send_packet(sub_pkt)

        # Retransmit unacknowledged QoS 1 / QoS 2 messages with DUP flag
        if self._inflight_packets:
            for pkt in list(self._inflight_packets.values()):
                pkt.dup = True
                await self._send_packet(pkt)

    async def disconnect(self) -> None:
        """Gracefully disconnect from MQTT broker."""
        self._manual_disconnect = True
        self._connected = False

        if self._keepalive_task and not self._keepalive_task.done():
            self._keepalive_task.cancel()
        if self._reconnect_task and not self._reconnect_task.done():
            self._reconnect_task.cancel()

        if self._writer and not self._writer.is_closing():
            try:
                await self._send_packet(DisconnectPacket())
            except Exception as e:
                logger.debug(f"Error sending DISCONNECT: {e}")
            try:
                self._writer.close()
                await self._writer.wait_closed()
            except Exception as e:
                logger.debug(f"Error closing writer: {e}")

        if self._reader_task and not self._reader_task.done():
            self._reader_task.cancel()

        self._reader = None
        self._writer = None
        logger.info("Disconnected from MQTT broker")

    async def _send_packet(self, packet: MQTTPacket) -> None:
        """Encode and transmit a packet through the active socket."""
        data = encode_packet(packet)
        async with self._send_lock:
            if self._writer is None or self._writer.is_closing():
                raise ConnectionResetError("Cannot send packet: MQTT client not connected")
            self._writer.write(data)
            await self._writer.drain()
            self._last_packet_sent = time.monotonic()

    async def _read_loop(self) -> None:
        """Continuous background loop reading and decoding binary MQTT packets."""
        buffer = bytearray()
        try:
            while not self._manual_disconnect:
                if self._reader is None:
                    break
                chunk = await self._reader.read(4096)
                if not chunk:
                    # Remote broker closed socket
                    logger.warning("MQTT broker connection closed (EOF received)")
                    break

                buffer.extend(chunk)
                while buffer:
                    try:
                        packet, consumed = decode_packet(bytes(buffer))
                    except ValueError as err:
                        logger.error(f"Malformed MQTT packet received: {err}")
                        buffer.clear()
                        break

                    if packet is None or consumed == 0:
                        # Wait for more bytes
                        break

                    del buffer[:consumed]
                    await self._handle_packet(packet)

        except asyncio.CancelledError:
            return
        except Exception as e:
            logger.warning(f"Error in MQTT reader loop: {e}")
        finally:
            self._connected = False
            if self._writer and not self._writer.is_closing():
                try:
                    self._writer.close()
                except Exception:
                    pass
            if not self._manual_disconnect and self.auto_reconnect:
                self._schedule_reconnect()

    def _schedule_reconnect(self) -> None:
        """Schedule automatic reconnection in the background."""
        if self._reconnect_task is None or self._reconnect_task.done():
            self._reconnect_task = asyncio.create_task(self._reconnect_loop())

    async def _reconnect_loop(self) -> None:
        """Exponential backoff reconnection watchdog."""
        retry_count = 0
        while not self._manual_disconnect and not self.is_connected:
            delay = min(
                self.max_reconnect_delay,
                self.base_reconnect_delay * (2**retry_count),
            )
            jitter = random.uniform(0, self.reconnect_jitter)
            wait_time = delay + jitter
            logger.info(f"Reconnecting to MQTT broker in {wait_time:.2f}s (attempt {retry_count + 1})...")
            try:
                await asyncio.sleep(wait_time)
                await self._establish_connection()
                logger.info("Successfully reconnected to MQTT broker")
                return
            except Exception as e:
                logger.warning(f"Reconnection attempt {retry_count + 1} failed: {e}")
                retry_count += 1

    async def _keepalive_loop(self) -> None:
        """Periodic keep-alive heartbeat loop."""
        interval = max(1.0, float(self.keep_alive) * 0.75)
        try:
            while self.is_connected:
                await asyncio.sleep(interval)
                elapsed = time.monotonic() - self._last_packet_sent
                if elapsed >= interval:
                    try:
                        await self._send_packet(PingreqPacket())
                    except Exception as e:
                        logger.warning(f"Failed to send PINGREQ: {e}")
                        break
        except asyncio.CancelledError:
            return

    async def _handle_packet(self, packet: Any) -> None:
        """Process a decoded MQTT packet according to protocol rules."""
        ptype = getattr(packet, "packet_type", None)

        if ptype == PacketType.CONNACK:
            if self._connack_future and not self._connack_future.done():
                self._connack_future.set_result(packet)

        elif ptype == PacketType.SUBACK:
            fut_sub = self._inflight_subscribes.pop(packet.packet_id, None)
            if fut_sub and not fut_sub.done():
                fut_sub.set_result(packet.return_codes or [])

        elif ptype == PacketType.UNSUBACK:
            fut_unsub = self._inflight_unsubscribes.pop(packet.packet_id, None)
            if fut_unsub and not fut_unsub.done():
                fut_unsub.set_result(None)

        elif ptype == PacketType.PUBACK:
            self._inflight_packets.pop(packet.packet_id, None)
            fut_pub = self._inflight_publishes.pop(packet.packet_id, None)
            if fut_pub and not fut_pub.done():
                fut_pub.set_result(None)

        elif ptype == PacketType.PUBREC:
            # QoS 2: Broker received message, send PUBREL
            pubrel = PubrelPacket(packet_id=packet.packet_id)
            await self._send_packet(pubrel)

        elif ptype == PacketType.PUBREL:
            # QoS 2: Broker released message, reply with PUBCOMP and dispatch
            pubcomp = PubcompPacket(packet_id=packet.packet_id)
            await self._send_packet(pubcomp)
            saved_packet = self._incoming_qos2_packets.pop(packet.packet_id, None)
            if saved_packet:
                await self._dispatch_publish(saved_packet)

        elif ptype == PacketType.PUBCOMP:
            # QoS 2: Transaction complete
            self._inflight_packets.pop(packet.packet_id, None)
            fut_pub2 = self._inflight_publishes.pop(packet.packet_id, None)
            if fut_pub2 and not fut_pub2.done():
                fut_pub2.set_result(None)

        elif ptype == PacketType.PUBLISH:
            if packet.qos == 0:
                await self._dispatch_publish(packet)
            elif packet.qos == 1:
                puback = PubackPacket(packet_id=packet.packet_id)
                await self._send_packet(puback)
                await self._dispatch_publish(packet)
            elif packet.qos == 2:
                # Store until PUBREL received
                self._incoming_qos2_packets[packet.packet_id] = packet
                pubrec = PubrecPacket(packet_id=packet.packet_id)
                await self._send_packet(pubrec)

        elif ptype == PacketType.PINGRESP:
            logger.debug("Received PINGRESP from broker")

    async def _dispatch_publish(self, packet: PublishPacket) -> None:
        """Dispatch an incoming PUBLISH packet to registered topic subscribers."""
        topic = packet.topic
        payload_bytes = packet.payload
        try:
            payload_str = payload_bytes.decode("utf-8")
            try:
                payload_val: Any = json.loads(payload_str)
            except Exception:
                payload_val = payload_str
        except Exception:
            payload_val = payload_bytes

        # Update local state cache
        self._state[topic] = payload_val

        # Dispatch to matching callbacks
        for filter_topic, callbacks in list(self._subscriptions.items()):
            if topic_matches(filter_topic, topic):
                for cb in callbacks:
                    try:
                        res = cb(topic, payload_val)
                        if asyncio.iscoroutine(res):
                            await res
                    except Exception as e:
                        logger.error(f"Error in MQTT subscription callback for topic {topic}: {e}")

    async def publish(
        self,
        topic: str,
        payload: Any,
        qos: int = 0,
        retain: bool = False,
        timeout: float = 10.0,
    ) -> None:
        """Publish a message to an MQTT topic with specified QoS (0, 1, or 2)."""
        if isinstance(payload, bytes):
            payload_bytes = payload
        elif isinstance(payload, (dict, list)):
            payload_bytes = json.dumps(payload).encode("utf-8")
        else:
            payload_bytes = str(payload).encode("utf-8")

        # Update local state
        try:
            self._state[topic] = json.loads(payload_bytes.decode("utf-8"))
        except Exception:
            self._state[topic] = payload

        if not self.is_connected:
            logger.debug(f"MQTT client not connected to broker; updated local state for {topic}")
            return

        if qos == 0:
            packet = PublishPacket(
                topic=topic,
                payload=payload_bytes,
                qos=0,
                retain=retain,
            )
            await self._send_packet(packet)
            return

        # QoS 1 or QoS 2 requires packet identifier and tracking
        pid = self._get_next_packet_id()
        packet = PublishPacket(
            topic=topic,
            payload=payload_bytes,
            qos=qos,
            packet_id=pid,
            retain=retain,
        )

        loop = asyncio.get_running_loop()
        ack_future: asyncio.Future[None] = loop.create_future()
        self._inflight_publishes[pid] = ack_future
        self._inflight_packets[pid] = packet

        await self._send_packet(packet)

        try:
            await asyncio.wait_for(ack_future, timeout=timeout)
        except TimeoutError:
            logger.warning(f"Publish QoS {qos} timed out for packet ID {pid} on topic {topic}")
            raise

    async def subscribe(
        self,
        topic: str,
        callback: Callable[[str, Any], Awaitable[None] | None],
        qos: int = 0,
        timeout: float = 10.0,
    ) -> None:
        """Subscribe to a topic filter with callback and requested QoS."""
        if topic not in self._subscriptions:
            self._subscriptions[topic] = []
        if callback not in self._subscriptions[topic]:
            self._subscriptions[topic].append(callback)
        self._subscriptions_qos[topic] = qos

        if self.is_connected:
            pid = self._get_next_packet_id()
            sub_pkt = SubscribePacket(packet_id=pid, topics=[(topic, qos)])
            loop = asyncio.get_running_loop()
            sub_fut: asyncio.Future[list[int]] = loop.create_future()
            self._inflight_subscribes[pid] = sub_fut

            await self._send_packet(sub_pkt)
            try:
                await asyncio.wait_for(sub_fut, timeout=timeout)
            except TimeoutError:
                logger.warning(f"Subscribe timed out for topic {topic}")
                raise

    async def unsubscribe(self, topic: str, timeout: float = 10.0) -> None:
        """Unsubscribe from a topic filter."""
        self._subscriptions.pop(topic, None)
        self._subscriptions_qos.pop(topic, None)

        if self.is_connected:
            pid = self._get_next_packet_id()
            unsub_pkt = UnsubscribePacket(packet_id=pid, topics=[topic])
            loop = asyncio.get_running_loop()
            unsub_fut: asyncio.Future[None] = loop.create_future()
            self._inflight_unsubscribes[pid] = unsub_fut

            await self._send_packet(unsub_pkt)
            try:
                await asyncio.wait_for(unsub_fut, timeout=timeout)
            except TimeoutError:
                logger.warning(f"Unsubscribe timed out for topic {topic}")
                raise

    async def execute(self, command: str, params: dict[str, Any]) -> Any:
        """Execute a device command against the MQTT adapter."""
        if command == "publish":
            topic = params.get("topic")
            if not topic:
                raise ValueError("execute 'publish' requires 'topic' in params")
            payload = params.get("payload", {})
            qos = params.get("qos", 0)
            retain = params.get("retain", False)
            await self.publish(topic, payload, qos=qos, retain=retain)
            return {"status": "success", "command": command, "topic": topic}

        elif command == "subscribe":
            topic = params.get("topic")
            if not topic:
                raise ValueError("execute 'subscribe' requires 'topic' in params")

            # Default state recorder callback
            def _cb(t: str, p: Any) -> None:
                self._state[t] = p

            await self.subscribe(topic, _cb)
            return {"status": "success", "command": command, "topic": topic}

        elif command == "read_state":
            state = await self.read_state()
            return {"status": "success", "command": command, "state": state}

        else:
            topic = params.get("topic")
            payload = params.get("payload", {})
            if topic:
                await self.publish(topic, payload)
                return {"status": "success", "command": command, "topic": topic}
            return {"status": "unknown_command", "command": command}

    async def read_state(self) -> dict[str, Any]:
        """Read currently recorded device state dictionary."""
        return dict(self._state)


_default_client: MQTTAdapter | None = None


def get_default_client(config: Any | None = None) -> MQTTAdapter:
    """Return the global default MQTT client instance, optionally configured from IoTConfig."""
    global _default_client
    if _default_client is None:
        if config is not None:
            _default_client = MQTTAdapter(
                broker_host=getattr(config, "broker_host", "localhost"),
                broker_port=getattr(config, "broker_port", 1883),
                username=getattr(config, "username", None),
                password=getattr(config, "password", None),
                client_id=getattr(config, "client_id", None),
                keep_alive=getattr(config, "keepalive", 60),
                use_tls=getattr(config, "use_tls", False),
                ca_certs=getattr(config, "ca_certs", None),
                certfile=getattr(config, "certfile", None),
                keyfile=getattr(config, "keyfile", None),
                tls_insecure=getattr(config, "tls_insecure", False),
            )
        else:
            _default_client = MQTTAdapter()
    return _default_client
