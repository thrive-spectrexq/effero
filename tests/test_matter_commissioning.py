"""Comprehensive tests for Matter commissioning state machine, onboarding parser, SPAKE2+, and clusters."""

from __future__ import annotations

import asyncio

import pytest

from effero.adapters.mqtt_matter.matter import (
    CommissioningState,
    LevelControlCluster,
    MatterCommissioningStateMachine,
    OnboardingPayload,
    OnOffCluster,
    TemperatureMeasurementCluster,
    base38_decode,
    base38_encode,
)

# ===========================================================================
# 1. Base38 Codec & Onboarding Payload Tests
# ===========================================================================


def test_base38_roundtrip_various_lengths():
    """Verify Base38 encoding and decoding across 1, 2, 3, and arbitrary byte lengths."""
    for raw in [b"\x42", b"\x12\x34", b"\x01\x02\x03", b"MatterTestPayload11B"]:
        encoded = base38_encode(raw)
        decoded = base38_decode(encoded)
        assert decoded == raw, f"Mismatch for raw={raw!r}, encoded={encoded!r}, decoded={decoded!r}"


def test_base38_invalid_inputs():
    """Test Base38 error handling for invalid characters and malformed chunks."""
    with pytest.raises(ValueError, match="Invalid Base38 character"):
        base38_decode("MT_INVALID!*")

    with pytest.raises(ValueError, match="chunk length"):
        base38_decode("A")  # Single character is invalid chunk length


def test_onboarding_qr_code_roundtrip():
    """Verify Matter QR code (MT:...) parsing and serialization roundtrip."""
    payload = OnboardingPayload(
        version=0,
        vendor_id=0xFFF1,
        product_id=0x8001,
        custom_flow=0,
        discovery_capabilities=4,  # OnNetwork/IP
        discriminator=3840,
        passcode=20202021,
    )
    qr = payload.to_qr_code()
    assert qr.startswith("MT:")

    parsed = OnboardingPayload.from_qr_code(qr)
    assert parsed.vendor_id == 0xFFF1
    assert parsed.product_id == 0x8001
    assert parsed.discriminator == 3840
    assert parsed.passcode == 20202021
    assert parsed.discovery_capabilities == 4
    assert parsed.version == 0


def test_onboarding_qr_code_invalid():
    """Test invalid QR code inputs."""
    with pytest.raises(ValueError, match="prefix"):
        OnboardingPayload.from_qr_code("NOT_A_MATTER_CODE")

    with pytest.raises(ValueError, match="too short"):
        OnboardingPayload.from_qr_code("MT:00")


def test_onboarding_manual_code_roundtrip_11_digit():
    """Verify 11-digit manual pairing code parsing and generation."""
    payload = OnboardingPayload(
        passcode=1234567,
        discriminator=0x0F00,  # Short discriminator = 0x0F
        vendor_id=None,
        product_id=None,
    )
    code = payload.to_manual_code()
    assert len(code) == 11
    assert code.isdigit()

    parsed = OnboardingPayload.from_manual_code(code)
    assert parsed.passcode == 1234567
    assert (parsed.discriminator >> 8) == (payload.discriminator >> 8)


def test_onboarding_manual_code_roundtrip_21_digit():
    """Verify 21-digit manual pairing code parsing with VID and PID."""
    payload = OnboardingPayload(
        passcode=7654321,
        discriminator=0x0A00,
        vendor_id=12345,
        product_id=54321,
    )
    code = payload.to_manual_code()
    assert len(code) == 21
    assert code.isdigit()

    parsed = OnboardingPayload.from_manual_code(code)
    assert parsed.passcode == 7654321
    assert parsed.vendor_id == 12345
    assert parsed.product_id == 54321


def test_onboarding_payload_auto_parse():
    """Verify unified OnboardingPayload.parse() dispatches correctly."""
    # Test QR
    payload = OnboardingPayload(passcode=20202021, discriminator=1234)
    qr = payload.to_qr_code()
    parsed_qr = OnboardingPayload.parse(qr)
    assert parsed_qr.passcode == 20202021

    # Test manual code with hyphens
    manual = "3497-011-2332"
    parsed_man = OnboardingPayload.parse(manual)
    assert parsed_man.passcode > 0


# ===========================================================================
# 2. Commissioning State Machine Tests
# ===========================================================================


@pytest.mark.asyncio
async def test_full_commissioning_lifecycle():
    """Verify standard end-to-end commissioning progression from UNCOMMISSIONED to COMMISSIONED."""
    sm = MatterCommissioningStateMachine(device_id="matter_bulb_01")
    assert sm.state == CommissioningState.UNCOMMISSIONED
    assert sm.is_commissioned is False

    qr = OnboardingPayload(passcode=20202021, discriminator=3840, vendor_id=0xFFF1, product_id=0x8001).to_qr_code()

    # 1. Discovery
    await sm.start_discovery(qr)
    assert sm.state == CommissioningState.DISCOVERING

    # 2. SPAKE2+ PASE Session
    pase_res = await sm.establish_pase_session()
    assert sm.state == CommissioningState.PASE_SESSION
    assert sm.session_established is True
    assert "session_key_fingerprint" in pase_res
    assert len(pase_res["confirmation_a"]) > 0
    assert len(pase_res["confirmation_b"]) > 0

    # 3. Arm Fail-Safe
    await sm.arm_failsafe(duration_seconds=30.0)
    assert sm.state == CommissioningState.FAILSAFE_ARMED

    # 4. Configure Network
    await sm.configure_network(network_type="wifi", ssid="HomeMesh", password="SecretWifiPassword")
    assert sm.state == CommissioningState.CONFIGURING_NETWORK
    assert sm.network_credentials["ssid"] == "HomeMesh"

    # 5. Establish CASE Session
    await sm.establish_case_session(fabric_index=1, node_id=0xCAFE1234BEEF5678)
    assert sm.state == CommissioningState.CASE_SESSION
    assert sm.fabric_index == 1
    assert sm.node_id == 0xCAFE1234BEEF5678
    assert sm.noc is not None

    # 6. Complete Commissioning
    await sm.complete_commissioning()
    assert sm.state == CommissioningState.COMMISSIONED
    assert sm.is_commissioned is True


@pytest.mark.asyncio
async def test_convenience_run_full_commissioning():
    """Test one-line execution of full commissioning."""
    sm = MatterCommissioningStateMachine(device_id="smart_plug_01")
    qr = OnboardingPayload(passcode=12345678, discriminator=1234).to_qr_code()
    await sm.run_full_commissioning(qr, wifi_ssid="IoT_Net", wifi_password="secure")
    assert sm.is_commissioned is True


@pytest.mark.asyncio
async def test_failsafe_timeout_automatic_rollback():
    """Verify that fail-safe timer expiry automatically rolls state back to UNCOMMISSIONED."""
    sm = MatterCommissioningStateMachine(device_id="unreliable_device")
    qr = OnboardingPayload(passcode=20202021, discriminator=1234).to_qr_code()

    await sm.start_discovery(qr)
    await sm.establish_pase_session()

    # Arm with ultra-short timeout (0.05 seconds)
    await sm.arm_failsafe(duration_seconds=0.05)
    assert sm.state == CommissioningState.FAILSAFE_ARMED

    # Wait for timeout to expire
    await asyncio.sleep(0.1)

    # Must have automatically rolled back to UNCOMMISSIONED
    assert sm.state == CommissioningState.UNCOMMISSIONED
    assert sm.session_established is False
    assert sm.is_commissioned is False


@pytest.mark.asyncio
async def test_explicit_rollback():
    """Test calling rollback() resets state and cleans keys."""
    sm = MatterCommissioningStateMachine(device_id="test_rollback_node")
    qr = OnboardingPayload(passcode=20202021, discriminator=1234).to_qr_code()

    await sm.start_discovery(qr)
    await sm.establish_pase_session()
    await sm.arm_failsafe(duration_seconds=10.0)

    # Abort
    await sm.rollback(reason="Commissioning user cancelled")
    assert sm.state == CommissioningState.UNCOMMISSIONED
    assert sm.session_established is False


@pytest.mark.asyncio
async def test_invalid_state_transitions():
    """Verify that state machine rejects invalid operational transitions."""
    sm = MatterCommissioningStateMachine(device_id="invalid_node")

    with pytest.raises(RuntimeError, match="Cannot establish PASE session"):
        await sm.establish_pase_session()

    with pytest.raises(RuntimeError, match="Cannot arm fail-safe"):
        await sm.arm_failsafe()

    with pytest.raises(RuntimeError, match="Cannot configure network"):
        await sm.configure_network(ssid="foo", password="bar")

    with pytest.raises(RuntimeError, match="Cannot complete commissioning"):
        await sm.complete_commissioning()


# ===========================================================================
# 3. Matter Operational Clusters Tests
# ===========================================================================


@pytest.mark.asyncio
async def test_on_off_cluster():
    """Test OnOffCluster operations."""
    cluster = OnOffCluster(initial_state=False)
    assert cluster.is_on is False

    await cluster.on()
    assert cluster.is_on is True

    await cluster.off()
    assert cluster.is_on is False

    await cluster.toggle()
    assert cluster.is_on is True

    await cluster.toggle()
    assert cluster.is_on is False


@pytest.mark.asyncio
async def test_level_control_cluster():
    """Test LevelControlCluster level transitions and bounds clamping."""
    cluster = LevelControlCluster(initial_level=0, min_level=0, max_level=254)
    assert cluster.current_level == 0

    await cluster.move_to_level(128, transition_time_ds=10)
    assert cluster.current_level == 128

    # Clamp below min
    await cluster.move_to_level(-10)
    assert cluster.current_level == 0

    # Clamp above max
    await cluster.move_to_level(300)
    assert cluster.current_level == 254


def test_temperature_measurement_cluster():
    """Test TemperatureMeasurementCluster read/set and 100x Celsius scaling."""
    cluster = TemperatureMeasurementCluster(initial_celsius=21.5)
    assert cluster.measured_value == 2150
    assert cluster.read_temperature() == 21.5

    cluster.set_temperature(23.75)
    assert cluster.measured_value == 2375
    assert cluster.read_temperature() == 23.75

    # Bounds check
    cluster.set_temperature(-50.0)
    assert cluster.measured_value == cluster.min_measured_value
