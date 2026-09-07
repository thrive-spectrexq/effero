"""Comprehensive tests for IoT telemetry normalization, SenML (RFC 8428), and Pydantic models."""

from __future__ import annotations

import json
from datetime import UTC, datetime

from effero.adapters.mqtt_matter.telemetry import (
    NormalizedTelemetry,
    TelemetryNormalizer,
)


def test_normalized_telemetry_model_validation():
    """Verify NormalizedTelemetry Pydantic model initialization and JSON serialization."""
    now = datetime.now(UTC)
    tel = NormalizedTelemetry(
        device_id="sensor_node_1",
        timestamp=now,
        metrics={"temperature": 23.5, "humidity": 60},
        units={"temperature": "°C", "humidity": "%"},
        topic="home/sensors/node1",
        raw_payload={"temp": 23.5, "hum": 60},
        quality="good",
    )
    assert tel.device_id == "sensor_node_1"
    assert tel.metrics["temperature"] == 23.5
    assert tel.units["temperature"] == "°C"
    assert tel.quality == "good"

    # Pydantic dump
    dump = tel.model_dump()
    assert dump["device_id"] == "sensor_node_1"
    assert dump["metrics"]["temperature"] == 23.5

    # JSON export
    raw_json = tel.model_dump_json()
    assert "sensor_node_1" in raw_json


def test_normalize_flat_json_dictionary():
    """Test standard flat JSON dictionary normalization with unit inference."""
    raw = {"temperature": 22.4, "humidity": 58, "battery": 92}
    topic = "home/living_room/state"
    normalized = TelemetryNormalizer.normalize(topic, raw)

    assert normalized.device_id == "living_room"
    assert normalized.metrics["temperature"] == 22.4
    assert normalized.metrics["humidity"] == 58
    assert normalized.metrics["battery"] == 92
    assert normalized.units["temperature"] == "°C"
    assert normalized.units["humidity"] == "%"
    assert normalized.units["battery"] == "%"
    assert normalized.quality == "good"


def test_normalize_json_string_payload():
    """Test normalization when raw payload is an encoded JSON string."""
    raw_str = json.dumps({"power": 150.5, "voltage": 230.1})
    topic = "factory/machine1/power"
    normalized = TelemetryNormalizer.normalize(topic, raw_str)

    assert normalized.metrics["power"] == 150.5
    assert normalized.metrics["voltage"] == 230.1
    assert normalized.units["power"] == "W"
    assert normalized.units["voltage"] == "V"


def test_normalize_nested_tasmota_schema():
    """Test normalizing nested Tasmota telemetry structure."""
    raw = {
        "Time": "2026-09-07T22:30:00Z",
        "SENSOR": {
            "DS18B20": {
                "Temperature": 21.8,
            },
            "Humidity": 54.2,
        },
    }
    topic = "tele/tasmota_temp/SENSOR"
    normalized = TelemetryNormalizer.normalize(topic, raw)

    assert normalized.device_id == "tasmota_temp"
    assert normalized.timestamp == datetime(2026, 9, 7, 22, 30, 0, tzinfo=UTC)
    assert normalized.metrics["SENSOR_DS18B20_Temperature"] == 21.8
    assert normalized.metrics["SENSOR_Humidity"] == 54.2
    assert normalized.units["SENSOR_DS18B20_Temperature"] == "°C"
    assert normalized.units["SENSOR_Humidity"] == "%"


def test_normalize_homeassistant_state_attributes():
    """Test normalizing HomeAssistant state and attributes payload."""
    raw = {
        "entity_id": "sensor.kitchen_temperature",
        "state": 23.1,
        "attributes": {
            "unit_of_measurement": "°C",
            "battery_level": 88,
            "friendly_name": "Kitchen Temperature",
        },
    }
    topic = "homeassistant/sensor/kitchen_temperature/state"
    normalized = TelemetryNormalizer.normalize(topic, raw)

    assert normalized.metrics["state"] == 23.1
    assert normalized.units["state"] == "°C"
    assert normalized.metrics["battery_level"] == 88
    assert normalized.units["battery_level"] == "%"
    assert normalized.metrics["friendly_name"] == "Kitchen Temperature"


def test_normalize_senml_rfc8428():
    """Test SenML (RFC 8428) array format normalization."""
    raw_senml = [
        {"bn": "urn:dev:mac:0024e411:", "bt": 1276020076, "bu": "Cel"},
        {"n": "temp", "v": 23.5},
        {"n": "hum", "u": "%RH", "v": 62.0},
        {"n": "status", "vs": "nominal"},
        {"n": "active", "vb": True},
    ]
    topic = "senml/node01"
    normalized = TelemetryNormalizer.normalize(topic, raw_senml)

    assert normalized.device_id == "0024e411"
    assert normalized.metrics["temp"] == 23.5
    assert normalized.units["temp"] == "°C"
    assert normalized.metrics["hum"] == 62.0
    assert normalized.units["hum"] == "%"
    assert normalized.metrics["status"] == "nominal"
    assert normalized.metrics["active"] is True
    assert normalized.timestamp == datetime.fromtimestamp(1276020076, tz=UTC)


def test_normalize_raw_scalars():
    """Test normalizing raw scalar strings and numbers."""
    # Numeric string on topic
    norm1 = TelemetryNormalizer.normalize("home/greenhouse/temperature", "28.4")
    assert norm1.device_id == "greenhouse"
    assert norm1.metrics["temperature"] == 28.4
    assert norm1.units["temperature"] == "°C"
    assert norm1.quality == "good"

    # Boolean string on topic
    norm2 = TelemetryNormalizer.normalize("home/living_room/motion", "ON")
    assert norm2.metrics["motion"] is True
    assert norm2.quality == "good"

    # Plain text string
    norm3 = TelemetryNormalizer.normalize("device/diag/log", "system initialized")
    assert norm3.metrics["log"] == "system initialized"
    assert norm3.quality == "raw"


def test_timestamp_parsing_formats():
    """Verify parse_timestamp handles ISO, epoch seconds, epoch milliseconds, and now."""
    # ISO string
    dt_iso = TelemetryNormalizer.parse_timestamp("2026-09-07T12:00:00+00:00")
    assert dt_iso == datetime(2026, 9, 7, 12, 0, 0, tzinfo=UTC)

    # Epoch seconds
    dt_sec = TelemetryNormalizer.parse_timestamp(1700000000)
    assert dt_sec == datetime.fromtimestamp(1700000000, tz=UTC)

    # Epoch milliseconds (> 1e11)
    dt_ms = TelemetryNormalizer.parse_timestamp(1700000000000)
    assert dt_ms == datetime.fromtimestamp(1700000000, tz=UTC)

    # Invalid string defaults to now
    dt_invalid = TelemetryNormalizer.parse_timestamp("invalid_time_string")
    assert isinstance(dt_invalid, datetime)
    assert dt_invalid.tzinfo == UTC
