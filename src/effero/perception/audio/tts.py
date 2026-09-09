"""TTS (Text-to-Speech) backends."""

from __future__ import annotations

import asyncio
import io
import math
import struct
import wave
from abc import ABC, abstractmethod


class TTSBackend(ABC):
    """Base class for TTS backends."""

    @abstractmethod
    async def synthesize(self, text: str) -> bytes:
        """Synthesize text into audio bytes."""
        ...


class OpenAITTS(TTSBackend):
    """Cloud TTS using OpenAI."""

    def __init__(self, model: str = "tts-1", voice: str = "alloy", api_key: str | None = None) -> None:
        try:
            from openai import AsyncOpenAI
        except ImportError as e:
            raise ImportError("Please install openai: pip install openai") from e

        self.client = AsyncOpenAI(api_key=api_key)
        self.model = model
        self.voice = voice

    async def synthesize(self, text: str) -> bytes:
        response = await self.client.audio.speech.create(model=self.model, voice=self.voice, input=text)
        return response.read()


class ToneSynthesizerTTS(TTSBackend):
    """Synthesizes real acoustic PCM WAV audio for speech responses."""

    def __init__(self, sample_rate: int = 16000, base_freq: float = 440.0) -> None:
        self.sample_rate = sample_rate
        self.base_freq = base_freq

    async def synthesize(self, text: str) -> bytes:
        def _generate_wav() -> bytes:
            if not text.strip():
                # Produce a brief 50ms silence WAV
                duration = 0.05
                num_samples = int(self.sample_rate * duration)
                buf = io.BytesIO()
                with wave.open(buf, "wb") as wf:
                    wf.setnchannels(1)
                    wf.setsampwidth(2)
                    wf.setframerate(self.sample_rate)
                    wf.writeframes(b"\x00\x00" * num_samples)
                return buf.getvalue()

            # Duration proportional to text length (approx 40ms per char, min 200ms, max 3.0s)
            duration = min(3.0, max(0.2, len(text) * 0.04))
            num_samples = int(self.sample_rate * duration)

            # Modulate frequency based on text characters
            char_sum = sum(ord(c) for c in text)
            freq = self.base_freq + (char_sum % 150)

            # Generate smooth harmonic audio samples with attack and decay envelope
            samples = bytearray()
            for i in range(num_samples):
                t = i / self.sample_rate
                # Envelope: 20ms attack, 50ms release
                env = 1.0
                attack_len = int(0.02 * self.sample_rate)
                release_len = int(0.05 * self.sample_rate)
                if i < attack_len:
                    env = i / attack_len
                elif i > num_samples - release_len:
                    env = max(0.0, (num_samples - i) / release_len)

                # Fundamental + second harmonic
                val = env * (0.8 * math.sin(2 * math.pi * freq * t) + 0.2 * math.sin(4 * math.pi * freq * t))
                s16 = int(max(-32767, min(32767, val * 16384)))
                samples.extend(struct.pack("<h", s16))

            buf = io.BytesIO()
            with wave.open(buf, "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(self.sample_rate)
                wf.writeframes(bytes(samples))

            return buf.getvalue()

        return await asyncio.to_thread(_generate_wav)
