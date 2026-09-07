"""Matter commissioning state machine, onboarding payload parser, and cluster implementations."""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import logging
import re
import secrets
import time
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

logger = logging.getLogger(__name__)

# Base38 character set defined in Matter specification section 5.1.3.1
BASE38_CHARS = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ-."
BASE38_MAP = {c: i for i, c in enumerate(BASE38_CHARS)}


def base38_decode(text: str) -> bytes:
    """Decode a Base-38 encoded string to raw bytes per Matter specification.

    Chunks:
    - 5 characters decode to 3 bytes
    - 4 characters decode to 2 bytes
    - 2 characters decode to 1 byte
    """
    out = bytearray()
    idx = 0
    n = len(text)
    while idx < n:
        rem = n - idx
        if rem >= 5:
            chunk_len = 5
            byte_count = 3
        elif rem == 4:
            chunk_len = 4
            byte_count = 2
        elif rem == 2:
            chunk_len = 2
            byte_count = 1
        else:
            raise ValueError(f"Invalid remaining Base38 chunk length: {rem}")

        chunk = text[idx : idx + chunk_len]
        idx += chunk_len

        val = 0
        weight = 1
        for c in chunk:
            if c not in BASE38_MAP:
                raise ValueError(f"Invalid Base38 character: {c}")
            val += BASE38_MAP[c] * weight
            weight *= 38

        for _ in range(byte_count):
            out.append(val & 0xFF)
            val >>= 8

    return bytes(out)


def base38_encode(data: bytes) -> str:
    """Encode raw bytes into a Base-38 string per Matter specification.

    Chunks:
    - 3 bytes encode to 5 characters
    - 2 bytes encode to 4 characters
    - 1 byte encodes to 2 characters
    """
    out = []
    idx = 0
    n = len(data)
    while idx < n:
        rem = n - idx
        if rem >= 3:
            chunk_len = 3
            char_count = 5
        elif rem == 2:
            chunk_len = 2
            char_count = 4
        else:
            chunk_len = 1
            char_count = 2

        chunk = data[idx : idx + chunk_len]
        idx += chunk_len

        val = 0
        for i, b in enumerate(chunk):
            val |= b << (i * 8)

        for _ in range(char_count):
            out.append(BASE38_CHARS[val % 38])
            val //= 38

    return "".join(out)


@dataclass
class OnboardingPayload:
    """Decoded onboarding payload for Matter device commissioning."""

    passcode: int  # 27-bit setup passcode (1..99999998)
    discriminator: int  # 12-bit discriminator (0..4095)
    vendor_id: int | None = None  # 16-bit Vendor ID (VID)
    product_id: int | None = None  # 16-bit Product ID (PID)
    discovery_capabilities: int = 4  # 8-bit discovery capabilities (default OnNetwork/IP)
    version: int = 0
    custom_flow: int = 0

    @classmethod
    def from_qr_code(cls, qr_string: str) -> OnboardingPayload:
        """Parse a Matter QR code string (starts with 'MT:').

        Bit layout (84 bits minimum = 11 bytes):
        - Version: 3 bits (bits 0..2)
        - Vendor ID: 16 bits (bits 3..18)
        - Product ID: 16 bits (bits 19..34)
        - Custom Flow: 2 bits (bits 35..36)
        - Discovery Capabilities: 8 bits (bits 37..44)
        - Discriminator: 12 bits (bits 45..56)
        - Setup Passcode: 27 bits (bits 57..83)
        """
        qr = qr_string.strip()
        if not qr.startswith("MT:"):
            raise ValueError("Matter QR code must start with 'MT:' prefix")

        payload_base38 = qr[3:]
        raw_bytes = base38_decode(payload_base38)
        if len(raw_bytes) < 11:
            raise ValueError(f"Decoded QR payload too short ({len(raw_bytes)} bytes < 11 bytes)")

        # Convert bytes to single integer (little-endian)
        val = int.from_bytes(raw_bytes, "little")

        version = val & 0x07
        val >>= 3

        vendor_id = val & 0xFFFF
        val >>= 16

        product_id = val & 0xFFFF
        val >>= 16

        custom_flow = val & 0x03
        val >>= 2

        discovery_cap = val & 0xFF
        val >>= 8

        discriminator = val & 0x0FFF
        val >>= 12

        passcode = val & 0x07FFFFFF

        return cls(
            version=version,
            vendor_id=vendor_id if vendor_id != 0 else None,
            product_id=product_id if product_id != 0 else None,
            custom_flow=custom_flow,
            discovery_capabilities=discovery_cap,
            discriminator=discriminator,
            passcode=passcode,
        )

    def to_qr_code(self) -> str:
        """Encode onboarding payload into standard Matter QR string ('MT:...')."""
        val = self.version & 0x07
        val |= ((self.vendor_id or 0) & 0xFFFF) << 3
        val |= ((self.product_id or 0) & 0xFFFF) << 19
        val |= (self.custom_flow & 0x03) << 35
        val |= (self.discovery_capabilities & 0xFF) << 37
        val |= (self.discriminator & 0x0FFF) << 45
        val |= (self.passcode & 0x07FFFFFF) << 57

        raw_bytes = val.to_bytes(11, "little")
        return "MT:" + base38_encode(raw_bytes)

    @classmethod
    def from_manual_code(cls, code: str) -> OnboardingPayload:
        """Parse a 11-digit or 21-digit manual pairing code.

        Hyphens and spaces are stripped automatically.
        """
        clean_code = re.sub(r"[\s\-]", "", code)
        if not clean_code.isdigit():
            raise ValueError(f"Manual pairing code contains non-digit characters: {code}")

        n_digits = len(clean_code)
        if n_digits == 11:
            d_high = int(clean_code[0]) & 0x03
            chunk1 = int(clean_code[1:6])
            chunk2 = int(clean_code[6:10])

            d_low = (chunk1 >> 14) & 0x03
            d_short = (d_high << 2) | d_low
            passcode_low = chunk1 & 0x3FFF
            passcode_high = chunk2 & 0x1FFF
            passcode = (passcode_high << 14) | passcode_low
            discriminator = d_short << 8

            return cls(
                passcode=passcode,
                discriminator=discriminator,
                vendor_id=None,
                product_id=None,
            )

        elif n_digits == 21:
            d_high = (int(clean_code[0]) - 4) & 0x03 if int(clean_code[0]) >= 4 else int(clean_code[0]) & 0x03
            chunk1 = int(clean_code[1:6])
            chunk2 = int(clean_code[6:10])
            vid = int(clean_code[10:15])
            pid = int(clean_code[15:20])

            d_low = (chunk1 >> 14) & 0x03
            d_short = (d_high << 2) | d_low
            passcode_low = chunk1 & 0x3FFF
            passcode_high = chunk2 & 0x1FFF
            passcode = (passcode_high << 14) | passcode_low
            discriminator = d_short << 8

            return cls(
                passcode=passcode,
                discriminator=discriminator,
                vendor_id=vid,
                product_id=pid,
            )

        else:
            raise ValueError(f"Invalid manual pairing code length: {n_digits} digits (must be 11 or 21)")

    def to_manual_code(self) -> str:
        """Encode onboarding payload to an 11-digit or 21-digit manual pairing code."""
        d_short = (self.discriminator >> 8) & 0x0F
        d_low = d_short & 0x03
        d_high = (d_short >> 2) & 0x03

        passcode_low = self.passcode & 0x3FFF
        passcode_high = (self.passcode >> 14) & 0x1FFF

        chunk1 = (d_low << 14) | passcode_low
        chunk2 = passcode_high

        if self.vendor_id is not None and self.product_id is not None:
            # 21-digit code
            digit0 = 4 + d_high
            s = f"{digit0}{chunk1:05d}{chunk2:04d}{self.vendor_id:05d}{self.product_id:05d}"
            chk = sum(int(c) for c in s) % 10
            return f"{s}{chk}"
        else:
            # 11-digit code
            digit0 = d_high
            s = f"{digit0}{chunk1:05d}{chunk2:04d}"
            chk = sum(int(c) for c in s) % 10
            return f"{s}{chk}"

    @classmethod
    def parse(cls, input_str: str) -> OnboardingPayload:
        """Parse either a QR code string ('MT:...') or a manual pairing code string."""
        s = input_str.strip()
        if s.startswith("MT:"):
            return cls.from_qr_code(s)
        return cls.from_manual_code(s)


class CommissioningState(StrEnum):
    """Matter commissioning lifecycle states."""

    UNCOMMISSIONED = "UNCOMMISSIONED"
    DISCOVERING = "DISCOVERING"
    PASE_SESSION = "PASE_SESSION"
    FAILSAFE_ARMED = "FAILSAFE_ARMED"
    CONFIGURING_NETWORK = "CONFIGURING_NETWORK"
    CASE_SESSION = "CASE_SESSION"
    COMMISSIONING_COMPLETE = "COMMISSIONING_COMPLETE"
    COMMISSIONED = "COMMISSIONED"
    FAILED = "FAILED"


# ---------------------------------------------------------------------------
# Matter Operational Clusters
# ---------------------------------------------------------------------------


class OnOffCluster:
    """Matter On/Off Cluster (Cluster ID 0x0006)."""

    def __init__(self, initial_state: bool = False) -> None:
        self._on_off: bool = initial_state

    @property
    def is_on(self) -> bool:
        """Return True if the switch is on."""
        return self._on_off

    async def on(self) -> None:
        """Turn device on."""
        self._on_off = True
        logger.info("Matter OnOffCluster: ON")

    async def off(self) -> None:
        """Turn device off."""
        self._on_off = False
        logger.info("Matter OnOffCluster: OFF")

    async def toggle(self) -> None:
        """Toggle device state."""
        self._on_off = not self._on_off
        logger.info(f"Matter OnOffCluster: TOGGLE -> {'ON' if self._on_off else 'OFF'}")


class LevelControlCluster:
    """Matter Level Control Cluster (Cluster ID 0x0008)."""

    def __init__(self, initial_level: int = 0, min_level: int = 0, max_level: int = 254) -> None:
        self.min_level = min_level
        self.max_level = max_level
        self._current_level: int = max(min_level, min(max_level, initial_level))

    @property
    def current_level(self) -> int:
        """Return current level (0..254)."""
        return self._current_level

    async def move_to_level(self, level: int, transition_time_ds: int = 0) -> None:
        """Move level to target value with transition time in tenths of a second."""
        clamped = max(self.min_level, min(self.max_level, level))
        self._current_level = clamped
        logger.info(
            f"Matter LevelControlCluster: moved to level {clamped} (transition_time={transition_time_ds * 0.1:.1f}s)"
        )


class TemperatureMeasurementCluster:
    """Matter Temperature Measurement Cluster (Cluster ID 0x0402)."""

    def __init__(self, initial_celsius: float = 21.5) -> None:
        # Per Matter spec: MeasuredValue is in 100ths of degrees Celsius
        self._measured_value: int = int(round(initial_celsius * 100))
        self.min_measured_value: int = -4000  # -40.0 C
        self.max_measured_value: int = 10000  # +100.0 C

    @property
    def measured_value(self) -> int:
        """Raw 100x Celsius integer value."""
        return self._measured_value

    def read_temperature(self) -> float:
        """Read temperature in degrees Celsius."""
        return self._measured_value / 100.0

    def set_temperature(self, temp_celsius: float) -> None:
        """Update measured temperature in degrees Celsius."""
        val = int(round(temp_celsius * 100))
        self._measured_value = max(self.min_measured_value, min(self.max_measured_value, val))


# ---------------------------------------------------------------------------
# Matter Commissioning State Machine
# ---------------------------------------------------------------------------


class MatterCommissioningStateMachine:
    """State machine executing the full Matter commissioning protocol.

    Follows Matter Specification:
    1. Parse onboarding payload (QR or manual code)
    2. SPAKE2+ Password-Authenticated Session Establishment (PASE)
    3. Arm fail-safe timer
    4. Network provisioning (Wi-Fi or Thread)
    5. Certificate-Authenticated Session Establishment (CASE) / Operational Credentials
    6. Complete commissioning and disarm fail-safe
    7. Expose operational clusters
    """

    def __init__(self, device_id: str = "matter_node_1") -> None:
        self.device_id = device_id
        self._state: CommissioningState = CommissioningState.UNCOMMISSIONED

        # Onboarding info
        self.payload: OnboardingPayload | None = None

        # SPAKE2+ / Session credentials
        self._salt: bytes = b""
        self._iterations: int = 1000
        self._session_encryption_key: bytes = b""
        self._session_auth_key: bytes = b""
        self.session_established: bool = False

        # Fail-safe management
        self._failsafe_armed: bool = False
        self._failsafe_deadline: float = 0.0
        self._failsafe_task: asyncio.Task[None] | None = None

        # Network configuration
        self.network_type: str | None = None
        self.network_credentials: dict[str, Any] = {}

        # Operational fabric
        self.fabric_index: int | None = None
        self.node_id: int | None = None
        self.noc: str | None = None
        self.rcac: str | None = None

        # Operational clusters
        self.on_off = OnOffCluster()
        self.level_control = LevelControlCluster()
        self.temperature_measurement = TemperatureMeasurementCluster()

    @property
    def state(self) -> CommissioningState:
        """Current commissioning state."""
        return self._state

    @property
    def is_commissioned(self) -> bool:
        """Return True if commissioning successfully completed."""
        return self._state == CommissioningState.COMMISSIONED

    def parse_payload(self, code_or_qr: str | OnboardingPayload) -> OnboardingPayload:
        """Parse and store the device onboarding payload."""
        if isinstance(code_or_qr, OnboardingPayload):
            self.payload = code_or_qr
        else:
            self.payload = OnboardingPayload.parse(code_or_qr)
        return self.payload

    async def start_discovery(self, code_or_qr: str | OnboardingPayload) -> None:
        """Begin discovery phase using device onboarding payload."""
        if self._state not in (CommissioningState.UNCOMMISSIONED, CommissioningState.FAILED):
            raise RuntimeError(f"Cannot start discovery from state {self._state}")

        payload = self.parse_payload(code_or_qr)
        self._state = CommissioningState.DISCOVERING
        logger.info(
            f"Matter discovery initiated for Passcode={payload.passcode}, Discriminator={payload.discriminator}"
        )

    async def establish_pase_session(self) -> dict[str, Any]:
        """Execute SPAKE2+ PASE handshake simulation with real cryptographic key derivation."""
        if self._state != CommissioningState.DISCOVERING or not self.payload:
            raise RuntimeError(f"Cannot establish PASE session from state {self._state}")

        # Step 1: PBKDF2 key derivation from passcode
        self._salt = secrets.token_bytes(16)
        self._iterations = 2000
        passcode_bytes = str(self.payload.passcode).encode("utf-8")

        w0_w1 = hashlib.pbkdf2_hmac("sha256", passcode_bytes, self._salt, self._iterations, dklen=64)
        w0 = w0_w1[:32]
        w1 = w0_w1[32:]

        # Step 2: SPAKE2+ ephemeral exchange simulation
        # Ephemeral random values for Commissioner (A) and Device (B)
        xa = secrets.token_bytes(32)
        xb = secrets.token_bytes(32)

        pa = hashlib.sha256(xa + w0).digest()
        pb = hashlib.sha256(xb + w0).digest()

        # Shared key material derived from ephemeral exchange and w1
        shared_secret = hashlib.sha256(xa + xb + pa + pb + w1).digest()

        # Confirmation tokens
        cb = hmac.new(shared_secret, b"MatterPASE_Confirmation_B" + pa + pb, hashlib.sha256).digest()
        ca = hmac.new(shared_secret, b"MatterPASE_Confirmation_A" + pb + pa, hashlib.sha256).digest()

        # Derive session keys: Encryption Key (Ke) and Authentication Key (Ka)
        self._session_encryption_key = hashlib.sha256(shared_secret + b"SessionEncryptionKey").digest()
        self._session_auth_key = hashlib.sha256(shared_secret + b"SessionAuthenticationKey").digest()
        self.session_established = True

        self._state = CommissioningState.PASE_SESSION
        logger.info(f"Matter PASE session established with node {self.device_id}")

        return {
            "status": "PASE_ESTABLISHED",
            "salt": self._salt.hex(),
            "iterations": self._iterations,
            "confirmation_a": ca.hex(),
            "confirmation_b": cb.hex(),
            "session_key_fingerprint": hashlib.sha256(self._session_encryption_key).hexdigest()[:16],
        }

    async def arm_failsafe(self, duration_seconds: float = 60.0) -> None:
        """Arm the fail-safe timer. If commissioning is not complete before deadline, rollback occurs."""
        if self._state not in (CommissioningState.PASE_SESSION, CommissioningState.FAILSAFE_ARMED):
            raise RuntimeError(f"Cannot arm fail-safe from state {self._state}")

        self._failsafe_armed = True
        self._failsafe_deadline = time.monotonic() + duration_seconds

        if self._failsafe_task and not self._failsafe_task.done():
            self._failsafe_task.cancel()

        self._failsafe_task = asyncio.create_task(self._failsafe_watcher(duration_seconds))
        self._state = CommissioningState.FAILSAFE_ARMED
        logger.info(f"Matter fail-safe armed for {duration_seconds}s")

    async def _failsafe_watcher(self, timeout: float) -> None:
        """Background task monitoring fail-safe expiry."""
        try:
            await asyncio.sleep(timeout)
            if self._failsafe_armed and self._state != CommissioningState.COMMISSIONED:
                logger.warning(f"Matter fail-safe expired after {timeout}s! Executing automatic rollback.")
                await self.rollback(reason="Fail-safe expired")
        except asyncio.CancelledError:
            return

    def disarm_failsafe(self) -> None:
        """Disarm active fail-safe timer."""
        self._failsafe_armed = False
        if self._failsafe_task and not self._failsafe_task.done():
            self._failsafe_task.cancel()
            self._failsafe_task = None
        logger.info("Matter fail-safe disarmed")

    async def configure_network(
        self,
        network_type: str = "wifi",
        ssid: str | None = None,
        password: str | None = None,
        thread_dataset: bytes | None = None,
    ) -> None:
        """Configure Wi-Fi or Thread network operational credentials."""
        if self._state not in (CommissioningState.FAILSAFE_ARMED, CommissioningState.CONFIGURING_NETWORK):
            raise RuntimeError(f"Cannot configure network from state {self._state}")

        self.network_type = network_type
        if network_type == "wifi":
            if not ssid:
                raise ValueError("Wi-Fi network configuration requires 'ssid'")
            self.network_credentials = {"ssid": ssid, "password": password or ""}
        elif network_type == "thread":
            if not thread_dataset:
                raise ValueError("Thread network configuration requires 'thread_dataset'")
            self.network_credentials = {"dataset": thread_dataset}
        else:
            raise ValueError(f"Unsupported network type: {network_type}")

        self._state = CommissioningState.CONFIGURING_NETWORK
        logger.info(f"Matter network configured: {network_type}")

    async def establish_case_session(
        self,
        fabric_index: int = 1,
        node_id: int | None = None,
        rcac_cert: str | None = None,
    ) -> None:
        """Perform Certificate-Authenticated Session Establishment (CASE) and assign fabric credentials."""
        if self._state != CommissioningState.CONFIGURING_NETWORK:
            raise RuntimeError(f"Cannot establish CASE session from state {self._state}")

        self.fabric_index = fabric_index
        self.node_id = node_id or secrets.randbits(64)
        self.rcac = rcac_cert or f"RCAC-ROOT-{secrets.token_hex(8)}"
        self.noc = f"NOC-NODE-{self.node_id:016X}-FABRIC-{self.fabric_index}"

        self._state = CommissioningState.CASE_SESSION
        logger.info(f"Matter CASE session established: NodeID=0x{self.node_id:016X}, FabricIndex={self.fabric_index}")

    async def complete_commissioning(self) -> None:
        """Finalize commissioning, disarm fail-safe, and transition to COMMISSIONED."""
        if self._state != CommissioningState.CASE_SESSION:
            raise RuntimeError(f"Cannot complete commissioning from state {self._state}")

        self.disarm_failsafe()
        self._state = CommissioningState.COMMISSIONING_COMPLETE
        await asyncio.sleep(0.01)  # Micro-tick
        self._state = CommissioningState.COMMISSIONED
        logger.info(f"Matter device {self.device_id} successfully commissioned!")

    async def rollback(self, reason: str = "Commissioning aborted") -> None:
        """Rollback commissioning progress and return to UNCOMMISSIONED state."""
        logger.warning(f"Rolling back Matter commissioning on {self.device_id}: {reason}")
        self.disarm_failsafe()

        # Clear ephemeral state
        self._salt = b""
        self._session_encryption_key = b""
        self._session_auth_key = b""
        self.session_established = False
        self.network_credentials.clear()
        self.fabric_index = None
        self.node_id = None
        self.noc = None
        self.rcac = None

        self._state = CommissioningState.UNCOMMISSIONED

    async def run_full_commissioning(
        self,
        code_or_qr: str | OnboardingPayload,
        wifi_ssid: str = "Effero_IoT",
        wifi_password: str = "SecretPass123",
        duration_seconds: float = 60.0,
    ) -> None:
        """Convenience method executing the complete end-to-end commissioning workflow."""
        await self.start_discovery(code_or_qr)
        await self.establish_pase_session()
        await self.arm_failsafe(duration_seconds=duration_seconds)
        await self.configure_network(network_type="wifi", ssid=wifi_ssid, password=wifi_password)
        await self.establish_case_session()
        await self.complete_commissioning()
