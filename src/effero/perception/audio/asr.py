"""ASR (Automatic Speech Recognition) backends."""

from __future__ import annotations

import asyncio
import io
import math
import struct
from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class TranscriptionResult:
    text: str
    language: str | None = None
    confidence: float | None = None
    segments: list[dict] = field(default_factory=list)


class ASRBackend(ABC):
    """Base class for ASR backends."""

    @abstractmethod
    async def transcribe(self, audio_data: bytes) -> TranscriptionResult:
        """Transcribe audio data into text."""
        ...


class OpenAIWhisperASR(ASRBackend):
    """Cloud ASR using OpenAI's Whisper model."""

    def __init__(self, api_key: str | None = None) -> None:
        try:
            from openai import AsyncOpenAI
        except ImportError as e:
            raise ImportError("Please install openai: pip install openai") from e

        self.client = AsyncOpenAI(api_key=api_key)

    async def transcribe(self, audio_data: bytes) -> TranscriptionResult:
        file_obj = io.BytesIO(audio_data)
        file_obj.name = "audio.wav"

        response = await self.client.audio.transcriptions.create(
            model="whisper-1", file=file_obj, response_format="verbose_json"
        )

        return TranscriptionResult(
            text=response.text,
            language=getattr(response, "language", None),
            confidence=None,
            segments=getattr(response, "segments", []),
        )


class FasterWhisperASR(ASRBackend):
    """Local ASR using faster-whisper."""

    def __init__(self, model_size: str = "small.en") -> None:
        try:
            import faster_whisper
        except ImportError as e:
            raise ImportError("Please install faster-whisper: pip install faster-whisper") from e

        self.model_size = model_size
        self._model = None
        self._faster_whisper = faster_whisper

    def _get_model(self):
        if self._model is None:
            self._model = self._faster_whisper.WhisperModel(self.model_size, device="cpu", compute_type="int8")
        return self._model

    async def transcribe(self, audio_data: bytes) -> TranscriptionResult:
        model = self._get_model()

        def _run_transcribe() -> TranscriptionResult:
            file_obj = io.BytesIO(audio_data)
            segments, info = model.transcribe(file_obj, beam_size=5)
            segments_list = list(segments)
            text = " ".join([seg.text for seg in segments_list]).strip()
            return TranscriptionResult(
                text=text,
                language=info.language,
                confidence=info.language_probability,
                segments=[{"start": s.start, "end": s.end, "text": s.text} for s in segments_list],
            )

        return await asyncio.to_thread(_run_transcribe)


class EnergyVADASR(ASRBackend):
    """Local acoustic energy Voice Activity Detection (VAD) and audio analysis ASR backend."""

    def __init__(self, energy_threshold: float = 0.01) -> None:
        self.energy_threshold = energy_threshold

    async def transcribe(self, audio_data: bytes) -> TranscriptionResult:
        def _analyze() -> TranscriptionResult:
            if not audio_data:
                return TranscriptionResult(text="", confidence=0.0)

            # Analyze 16-bit PCM samples
            sample_count = len(audio_data) // 2
            if sample_count == 0:
                return TranscriptionResult(text="", confidence=0.0)

            # Unpack signed 16-bit integers
            fmt = f"<{sample_count}h"
            try:
                samples = struct.unpack(fmt, audio_data[: sample_count * 2])
            except Exception:
                return TranscriptionResult(text="", confidence=0.0)

            # Compute normalized root-mean-square (RMS) energy
            sum_sq = sum((s / 32768.0) ** 2 for s in samples)
            rms = math.sqrt(sum_sq / sample_count)
            peak = max(abs(s) for s in samples) / 32768.0

            if rms > self.energy_threshold:
                # Active speech / acoustic event detected
                conf = min(0.99, max(0.6, rms * 10.0))
                return TranscriptionResult(
                    text=f"[speech_detected: rms={rms:.3f}, peak={peak:.3f}]",
                    language="en",
                    confidence=round(conf, 3),
                    segments=[{"start": 0.0, "end": sample_count / 16000.0, "rms": rms}],
                )
            else:
                return TranscriptionResult(
                    text="[silence]",
                    language="en",
                    confidence=0.95,
                    segments=[],
                )

        return await asyncio.to_thread(_analyze)
