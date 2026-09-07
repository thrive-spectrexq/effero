"""Structured IoT telemetry normalization supporting JSON, SenML (RFC 8428), and HomeAssistant schemas."""

from __future__ import annotations

import json
import logging
import re
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

logger = logging.getLogger(__name__)

# Standard unit lookup by metric name
KNOWN_METRIC_UNITS: dict[str, str] = {
    "temperature": "°C",
    "temp": "°C",
    "degc": "°C",
    "humidity": "%",
    "hum": "%",
    "relative_humidity": "%",
    "pressure": "hPa",
    "barometer": "hPa",
    "battery": "%",
    "battery_level": "%",
    "voltage": "V",
    "volt": "V",
    "current": "A",
    "ampere": "A",
    "power": "W",
    "watt": "W",
    "energy": "kWh",
    "co2": "ppm",
    "pm25": "µg/m³",
    "pm10": "µg/m³",
    "illuminance": "lx",
    "lux": "lx",
    "light": "lx",
    "rssi": "dBm",
    "linkquality": "lqi",
    "frequency": "Hz",
    "speed": "m/s",
    "wind_speed": "m/s",
}

# SenML RFC 8428 unit symbol normalization
SENML_UNIT_MAP: dict[str, str] = {
    "Cel": "°C",
    "%RH": "%",
    "/": "%",
    "V": "V",
    "A": "A",
    "W": "W",
    "J": "J",
    "kWh": "kWh",
    "Pa": "Pa",
    "hPa": "hPa",
    "bar": "bar",
    "m": "m",
    "m/s": "m/s",
    "s": "s",
    "ms": "ms",
    "lx": "lx",
    "ppm": "ppm",
    "dBm": "dBm",
    "Hz": "Hz",
}


class NormalizedTelemetry(BaseModel):
    """Standard normalized IoT telemetry model."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    device_id: str = Field(..., description="Unique device identifier")
    timestamp: datetime = Field(..., description="UTC timestamp of the telemetry reading")
    metrics: dict[str, float | int | str | bool] = Field(
        default_factory=dict, description="Key-value metric observations"
    )
    units: dict[str, str] = Field(default_factory=dict, description="Standard physical units for metrics")
    topic: str = Field(..., description="Source MQTT topic or Matter endpoint")
    raw_payload: Any = Field(..., description="Original raw payload for audit and traceability")
    quality: str = Field("good", description="Quality rating: 'good', 'degraded', or 'raw'")


class TelemetryNormalizer:
    """Normalizes heterogeneous IoT payloads into standard NormalizedTelemetry models."""

    @staticmethod
    def parse_timestamp(val: Any) -> datetime:
        """Parse diverse timestamp formats (ISO strings, unix seconds/ms) to UTC datetime."""
        if isinstance(val, datetime):
            if val.tzinfo is None:
                return val.replace(tzinfo=UTC)
            return val.astimezone(UTC)

        if isinstance(val, (int, float)):
            # Distinguish milliseconds vs seconds: > 10^11 is ms
            if val > 1e11:
                return datetime.fromtimestamp(val / 1000.0, tz=UTC)
            return datetime.fromtimestamp(val, tz=UTC)

        if isinstance(val, str):
            val_clean = val.strip()
            # Try ISO format
            try:
                dt = datetime.fromisoformat(val_clean.replace("Z", "+00:00"))
                if dt.tzinfo is None:
                    return dt.replace(tzinfo=UTC)
                return dt.astimezone(UTC)
            except Exception:
                pass

            # Try float string
            try:
                fval = float(val_clean)
                return TelemetryNormalizer.parse_timestamp(fval)
            except Exception:
                pass

        return datetime.now(UTC)

    @staticmethod
    def _infer_device_and_metric(topic: str) -> tuple[str, str]:
        """Infer device_id and metric name from topic segments."""
        parts = [p for p in topic.strip("/").split("/") if p]
        if not parts:
            return "unknown_device", "state"

        # Trailing command subtopics like 'set', 'get', 'cmd'
        if len(parts) >= 3 and parts[-1].lower() in ("set", "get", "cmd"):
            return parts[-3], parts[-2]

        # Common status/state subtopics: device is the preceding element
        if len(parts) >= 2 and parts[-1].lower() in (
            "state",
            "status",
            "telemetry",
            "tele",
            "sensor",
            "sensors",
            "data",
        ):
            return parts[-2], "state"

        if len(parts) >= 2:
            return parts[-2], parts[-1]

        return parts[0], "state"

    @classmethod
    def normalize(
        cls,
        topic: str,
        raw_payload: Any,
        device_id: str | None = None,
    ) -> NormalizedTelemetry:
        """Normalize an incoming payload (JSON dict, SenML array, HomeAssistant, or scalar)."""
        inferred_device, inferred_metric = cls._infer_device_and_metric(topic)
        final_device = device_id or inferred_device

        # If payload is raw bytes, decode to string
        parsed_obj = raw_payload
        if isinstance(raw_payload, bytes):
            try:
                parsed_obj = raw_payload.decode("utf-8")
            except Exception:
                parsed_obj = raw_payload

        # If payload is a string, attempt JSON parsing
        if isinstance(parsed_obj, str):
            str_val = parsed_obj.strip()
            if (str_val.startswith("{") and str_val.endswith("}")) or (
                str_val.startswith("[") and str_val.endswith("]")
            ):
                try:
                    parsed_obj = json.loads(str_val)
                except Exception:
                    pass

        # Branch 1: SenML array format (RFC 8428)
        if isinstance(parsed_obj, list) and (len(parsed_obj) == 0 or isinstance(parsed_obj[0], dict)):
            return cls._normalize_senml(topic, parsed_obj, final_device, raw_payload, user_device_id=device_id)

        # Branch 2: Dictionary format (JSON, HomeAssistant, Tasmota)
        if isinstance(parsed_obj, dict):
            return cls._normalize_dict(topic, parsed_obj, final_device, raw_payload)

        # Branch 3: Scalar format (numeric, boolean, or plain text)
        return cls._normalize_scalar(topic, parsed_obj, final_device, inferred_metric, raw_payload)

    @classmethod
    def _normalize_senml(
        cls,
        topic: str,
        records: list[dict[str, Any]],
        device_id: str,
        raw_payload: Any,
        user_device_id: str | None = None,
    ) -> NormalizedTelemetry:
        """Normalize SenML (RFC 8428) record array."""
        base_name = ""
        base_time = 0.0
        base_unit = ""
        metrics: dict[str, float | int | str | bool] = {}
        units: dict[str, str] = {}
        latest_time: float | None = None

        for rec in records:
            if "bn" in rec:
                base_name = str(rec["bn"])
            if "bt" in rec:
                base_time = float(rec["bt"])
            if "bu" in rec:
                base_unit = str(rec["bu"])

            metric_name = rec.get("n", "")
            if metric_name:
                name_to_clean = metric_name
            elif base_name:
                name_to_clean = base_name.strip(":").split(":")[-1] or "value"
            else:
                name_to_clean = "value"

            # Determine value (v, vs, vb, vd, s)
            val: float | int | str | bool | None = None
            if "v" in rec:
                val = rec["v"]
            elif "vs" in rec:
                val = rec["vs"]
            elif "vb" in rec:
                val = rec["vb"]
            elif "s" in rec:
                val = rec["s"]

            if val is not None:
                # Clean metric name
                clean_name = re.sub(r"[^\w\-]", "_", name_to_clean).strip("_")
                metrics[clean_name] = val

                # Determine unit
                raw_u = rec.get("u", base_unit)
                if raw_u:
                    units[clean_name] = SENML_UNIT_MAP.get(raw_u, raw_u)
                elif clean_name.lower() in KNOWN_METRIC_UNITS:
                    units[clean_name] = KNOWN_METRIC_UNITS[clean_name.lower()]

            # Determine timestamp
            rec_t = rec.get("t", 0.0)
            t_total = base_time + float(rec_t)
            if t_total > 0 and (latest_time is None or t_total > latest_time):
                latest_time = t_total

        timestamp = cls.parse_timestamp(latest_time) if latest_time else datetime.now(UTC)
        final_device = device_id
        if user_device_id is None and base_name:
            bn_clean = base_name.rstrip(":").split(":")[-1]
            if bn_clean:
                final_device = bn_clean

        return NormalizedTelemetry(
            device_id=final_device,
            timestamp=timestamp,
            metrics=metrics,
            units=units,
            topic=topic,
            raw_payload=raw_payload,
            quality="good" if metrics else "degraded",
        )

    @classmethod
    def _normalize_dict(
        cls,
        topic: str,
        data: dict[str, Any],
        device_id: str,
        raw_payload: Any,
    ) -> NormalizedTelemetry:
        """Normalize JSON dictionary (supports flat and nested structures, Tasmota, HomeAssistant)."""
        metrics: dict[str, float | int | str | bool] = {}
        units: dict[str, str] = {}
        timestamp: datetime = datetime.now(UTC)
        found_explicit_timestamp = False

        # Check for explicit device_id in data
        for dev_key in ("device_id", "device", "id", "deviceId", "node_id"):
            if dev_key in data and isinstance(data[dev_key], (str, int)):
                device_id = str(data[dev_key])
                break

        # Check for explicit timestamp in data
        for ts_key in ("timestamp", "time", "Time", "ts", "datetime", "date"):
            if ts_key in data:
                timestamp = cls.parse_timestamp(data[ts_key])
                found_explicit_timestamp = True
                break

        # Flatten nested structures (e.g. Tasmota SENSOR: {DS18B20: {Temperature: 21.5}})
        flat_items: list[tuple[str, Any]] = []

        def _flatten(prefix: str, sub: Any) -> None:
            if isinstance(sub, dict):
                # Check for {value: X, unit: Y} pattern
                if "value" in sub and len(sub) <= 3:
                    flat_items.append((prefix, sub["value"]))
                    unit_val = sub.get("unit") or sub.get("unit_of_measurement")
                    if unit_val:
                        units[prefix] = str(unit_val)
                    return

                for k, v in sub.items():
                    # Skip metadata keys in flatten
                    if k.lower() in ("timestamp", "time", "date", "device_id", "device"):
                        continue
                    new_prefix = f"{prefix}_{k}" if prefix else str(k)
                    _flatten(new_prefix, v)
            else:
                flat_items.append((prefix, sub))

        # Check HomeAssistant attributes wrapper
        if "attributes" in data and isinstance(data["attributes"], dict):
            _flatten("", data["attributes"])
            if "state" in data:
                _flatten("state", data["state"])
            if "unit_of_measurement" in data["attributes"]:
                # Default unit for main state
                units["state"] = str(data["attributes"]["unit_of_measurement"])
        else:
            _flatten("", data)

        for key, val in flat_items:
            # Skip non-primitive types
            if isinstance(val, (int, float, str, bool)):
                clean_key = re.sub(r"[^\w\-]", "_", key).strip("_")
                metrics[clean_key] = val

                # Check unit
                if clean_key not in units:
                    k_full = clean_key.lower()
                    if k_full in KNOWN_METRIC_UNITS:
                        units[clean_key] = KNOWN_METRIC_UNITS[k_full]
                    else:
                        for token in k_full.split("_"):
                            if token in KNOWN_METRIC_UNITS:
                                units[clean_key] = KNOWN_METRIC_UNITS[token]
                                break

        quality = "good" if metrics and found_explicit_timestamp else ("good" if metrics else "degraded")

        return NormalizedTelemetry(
            device_id=device_id,
            timestamp=timestamp,
            metrics=metrics,
            units=units,
            topic=topic,
            raw_payload=raw_payload,
            quality=quality,
        )

    @classmethod
    def _normalize_scalar(
        cls,
        topic: str,
        val: Any,
        device_id: str,
        metric_name: str,
        raw_payload: Any,
    ) -> NormalizedTelemetry:
        """Normalize raw scalar values (numbers, booleans, plain strings)."""
        metrics: dict[str, float | int | str | bool] = {}
        units: dict[str, str] = {}
        quality = "good"

        # Try converting string numbers
        if isinstance(val, str):
            val_clean = val.strip()
            if val_clean.lower() in ("true", "on", "active", "online"):
                metrics[metric_name] = True
            elif val_clean.lower() in ("false", "off", "inactive", "offline"):
                metrics[metric_name] = False
            else:
                try:
                    metrics[metric_name] = int(val_clean)
                except ValueError:
                    try:
                        metrics[metric_name] = float(val_clean)
                    except ValueError:
                        metrics[metric_name] = val_clean
                        quality = "raw"
        elif isinstance(val, (int, float, bool)):
            metrics[metric_name] = val
        else:
            metrics[metric_name] = str(val)
            quality = "raw"

        # Infer unit
        m_lower = metric_name.lower()
        if m_lower in KNOWN_METRIC_UNITS:
            units[metric_name] = KNOWN_METRIC_UNITS[m_lower]

        return NormalizedTelemetry(
            device_id=device_id,
            timestamp=datetime.now(UTC),
            metrics=metrics,
            units=units,
            topic=topic,
            raw_payload=raw_payload,
            quality=quality,
        )
