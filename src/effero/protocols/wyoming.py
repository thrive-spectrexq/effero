"""Wyoming protocol server and client for local streaming voice integration (Home Assistant compatible)."""
from __future__ import annotations

import asyncio
import io
import json
import logging
import struct
import wave
from dataclasses import dataclass, field
from typing import Any, Callable

logger = logging.getLogger(__name__)


@dataclass
class WyomingEvent:
    """A single Wyoming protocol event with JSON header and optional raw binary payload."""

    type: str
    data: dict[str, Any] = field(default_factory=dict)
    payload: bytes | None = None

    def to_bytes(self) -> bytes:
        """Serialize event to Wyoming wire format: JSON header + newline + optional payload."""
        header_dict: dict[str, Any] = {
            "type": self.type,
            "data": self.data,
            "payload_length": len(self.payload) if self.payload else 0,
        }
        header_bytes = (json.dumps(header_dict) + "\n").encode("utf-8")
        if self.payload:
            return header_bytes + self.payload
        return header_bytes

    @classmethod
    async def read_from_stream(cls, reader: asyncio.StreamReader) -> WyomingEvent | None:
        """Parse one Wyoming event from an asyncio stream reader."""
        line = await reader.readline()
        if not line:
            return None

        try:
            header_dict = json.loads(line.decode("utf-8"))
        except Exception as e:
            logger.error(f"Malformed Wyoming event header: {line!r} ({e})")
            return None

        event_type = header_dict.get("type", "")
        event_data = header_dict.get("data", {})
        payload_len = header_dict.get("payload_length", 0)

        payload: bytes | None = None
        if payload_len > 0:
            payload = await reader.readexactly(payload_len)

        return cls(type=event_type, data=event_data, payload=payload)


def pcm_to_wav(pcm_data: bytes, sample_rate: int = 16000, sample_width: int = 2, channels: int = 1) -> bytes:
    """Pack raw PCM audio samples into standard RIFF/WAV format."""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wav_file:
        wav_file.setnchannels(channels)
        wav_file.setsampwidth(sample_width)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(pcm_data)
    return buf.getvalue()


class WyomingServer:
    """Async TCP Server implementing the Wyoming voice protocol."""

    def __init__(
        self,
        host: str = "0.0.0.0",
        port: int = 10400,
        audio_pipeline=None,
        agent=None,
    ):
        self.host = host
        self.port = port
        self.audio_pipeline = audio_pipeline
        self.agent = agent
        self._server: asyncio.AbstractServer | None = None
        self._running = False

    async def start(self) -> None:
        """Start listening for incoming Wyoming satellite connections."""
        self._server = await asyncio.start_server(self._handle_client, self.host, self.port)
        self._running = True
        logger.info(f"Wyoming Voice Server running on {self.host}:{self.port}")

    async def stop(self) -> None:
        """Shutdown the Wyoming server."""
        if self._server:
            self._server.close()
            await self._server.wait_closed()
        self._running = False
        logger.info("Wyoming Voice Server stopped")

    async def _handle_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        """Handle communication with a connected voice satellite."""
        audio_buffer = bytearray()
        sample_rate = 16000
        sample_width = 2
        channels = 1

        try:
            while True:
                event = await WyomingEvent.read_from_stream(reader)
                if event is None:
                    break

                if event.type == "describe":
                    # Send satellite capabilities descriptor
                    info_event = WyomingEvent(
                        type="info",
                        data={
                            "asr": [{"name": "effero-asr", "installed": True}],
                            "tts": [{"name": "effero-tts", "installed": True}],
                            "handle": [{"name": "effero-agent", "installed": True}],
                        },
                    )
                    writer.write(info_event.to_bytes())
                    await writer.drain()

                elif event.type == "audio-start":
                    audio_buffer.clear()
                    sample_rate = event.data.get("rate", 16000)
                    sample_width = event.data.get("width", 2)
                    channels = event.data.get("channels", 1)

                elif event.type == "audio-chunk":
                    if event.payload:
                        audio_buffer.extend(event.payload)

                elif event.type == "audio-stop":
                    # Convert collected PCM buffer to WAV audio
                    wav_bytes = pcm_to_wav(bytes(audio_buffer), sample_rate, sample_width, channels)
                    transcript_text = ""

                    # Transcribe using AudioPipeline if available
                    if self.audio_pipeline:
                        transcript_text = await self.audio_pipeline.process_audio(wav_bytes)
                    else:
                        transcript_text = "Hello from Wyoming satellite"

                    # Send transcript back to client
                    tr_event = WyomingEvent(type="transcript", data={"text": transcript_text})
                    writer.write(tr_event.to_bytes())
                    await writer.drain()

                    # Process transcript through agent if attached
                    if self.agent and transcript_text.strip():
                        response_text = await self.agent.chat(transcript_text)

                        # Synthesize response audio
                        if self.audio_pipeline:
                            speech_wav = await self.audio_pipeline.speak(response_text)
                            # Send synthesized audio chunk back
                            synthesize_chunk = WyomingEvent(
                                type="audio-chunk",
                                data={"rate": sample_rate, "width": sample_width, "channels": channels},
                                payload=speech_wav,
                            )
                            writer.write(synthesize_chunk.to_bytes())
                            await writer.drain()

                elif event.type == "synthesize":
                    text_to_speak = event.data.get("text", "")
                    if self.audio_pipeline and text_to_speak:
                        speech_wav = await self.audio_pipeline.speak(text_to_speak)
                        speech_event = WyomingEvent(
                            type="audio-chunk",
                            data={"rate": 16000, "width": 2, "channels": 1},
                            payload=speech_wav,
                        )
                        writer.write(speech_event.to_bytes())
                        await writer.drain()

        except Exception as e:
            logger.error(f"Error handling Wyoming client: {e}")
        finally:
            writer.close()
            await writer.wait_closed()


class WyomingClient:
    """Client for connecting to remote Wyoming satellites or servers."""

    def __init__(self, host: str = "127.0.0.1", port: int = 10400):
        self.host = host
        self.port = port
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None

    async def connect(self) -> None:
        self._reader, self._writer = await asyncio.open_connection(self.host, self.port)

    async def describe(self) -> dict[str, Any]:
        """Send describe request and return remote capabilities."""
        if not self._writer or not self._reader:
            await self.connect()

        assert self._writer is not None
        assert self._reader is not None

        req = WyomingEvent(type="describe")
        self._writer.write(req.to_bytes())
        await self._writer.drain()

        resp = await WyomingEvent.read_from_stream(self._reader)
        return resp.data if resp else {}

    async def send_audio(self, pcm_bytes: bytes, rate: int = 16000) -> str:
        """Stream audio chunks and return the transcribed text."""
        if not self._writer or not self._reader:
            await self.connect()

        assert self._writer is not None
        assert self._reader is not None

        # 1. audio-start
        start_ev = WyomingEvent(type="audio-start", data={"rate": rate, "width": 2, "channels": 1})
        self._writer.write(start_ev.to_bytes())

        # 2. audio-chunk
        chunk_ev = WyomingEvent(
            type="audio-chunk",
            data={"rate": rate, "width": 2, "channels": 1},
            payload=pcm_bytes,
        )
        self._writer.write(chunk_ev.to_bytes())

        # 3. audio-stop
        stop_ev = WyomingEvent(type="audio-stop")
        self._writer.write(stop_ev.to_bytes())
        await self._writer.drain()

        # Read response events until transcript or timeout
        while True:
            resp = await WyomingEvent.read_from_stream(self._reader)
            if resp is None:
                return ""
            if resp.type == "transcript":
                return resp.data.get("text", "")

    async def close(self) -> None:
        if self._writer:
            self._writer.close()
            await self._writer.wait_closed()
        self._writer = None
        self._reader = None
