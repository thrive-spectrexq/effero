"""Tests for Wyoming Voice Protocol implementation."""
from __future__ import annotations

import asyncio
import pytest

from effero.protocols.wyoming import (
    WyomingClient,
    WyomingEvent,
    WyomingServer,
    pcm_to_wav,
)


def test_wyoming_event_serialization() -> None:
    event = WyomingEvent(
        type="audio-start",
        data={"rate": 16000, "width": 2, "channels": 1},
        payload=b"\x00\x01\x02\x03",
    )
    raw = event.to_bytes()
    assert b'"type": "audio-start"' in raw
    assert raw.endswith(b"\x00\x01\x02\x03")


def test_pcm_to_wav() -> None:
    pcm = b"\x00\x00" * 1600  # 0.1 second of 16kHz silence
    wav = pcm_to_wav(pcm, sample_rate=16000, sample_width=2, channels=1)
    assert wav.startswith(b"RIFF")
    assert b"WAVE" in wav


@pytest.mark.asyncio
async def test_wyoming_server_describe() -> None:
    port = 19500
    server = WyomingServer(host="127.0.0.1", port=port)
    await server.start()

    try:
        client = WyomingClient(host="127.0.0.1", port=port)
        await client.connect()
        info = await client.describe()
        assert "asr" in info
        assert "tts" in info
        await client.close()
    finally:
        await server.stop()


@pytest.mark.asyncio
async def test_wyoming_audio_exchange() -> None:
    port = 19501

    class MockAudioPipe:
        async def process_audio(self, audio_data: bytes) -> str:
            assert len(audio_data) > 0
            return "turn on the kitchen light"

    server = WyomingServer(host="127.0.0.1", port=port, audio_pipeline=MockAudioPipe())
    await server.start()

    try:
        client = WyomingClient(host="127.0.0.1", port=port)
        await client.connect()

        # Send raw 16-bit PCM bytes
        pcm_samples = b"\x10\x00" * 800
        transcript = await client.send_audio(pcm_samples, rate=16000)
        assert transcript == "turn on the kitchen light"

        await client.close()
    finally:
        await server.stop()
