"""Audio perception pipeline."""

from __future__ import annotations

import logging
import time
from typing import Any

from effero.core.event_bus import Event, EventBus
from effero.perception.audio.asr import ASRBackend, EnergyVADASR
from effero.perception.audio.tts import ToneSynthesizerTTS, TTSBackend
from effero.perception.base import PerceptionPipeline

logger = logging.getLogger(__name__)


class AudioPipeline(PerceptionPipeline):
    """Pipeline for processing audio (ASR) and generating speech (TTS)."""

    def __init__(
        self,
        event_bus: EventBus,
        asr_backend: ASRBackend | None = None,
        tts_backend: TTSBackend | None = None,
    ) -> None:
        super().__init__(event_bus)
        self.asr_backend: ASRBackend = asr_backend or EnergyVADASR()
        self.tts_backend: TTSBackend = tts_backend or ToneSynthesizerTTS()

    async def start(self) -> None:
        self._running = True
        logger.info("AudioPipeline started.")

    async def stop(self) -> None:
        self._running = False
        logger.info("AudioPipeline stopped.")

    async def process_audio(self, audio_data: bytes) -> str:
        """Process incoming audio, transcribe it, and publish an event."""
        result = await self.asr_backend.transcribe(audio_data)

        event = Event(
            topic="perception.audio.utterance",
            data={
                "text": result.text,
                "language": result.language,
                "confidence": result.confidence,
            },
            timestamp=time.time(),
            source="audio_pipeline",
        )
        self.event_bus.publish(event)

        return result.text

    async def speak(self, text: str) -> bytes:
        """Synthesize text into audio and publish an event."""
        audio_data = await self.tts_backend.synthesize(text)

        event = Event(
            topic="perception.audio.speech",
            data={"text": text},
            timestamp=time.time(),
            source="audio_pipeline",
        )
        self.event_bus.publish(event)

        return audio_data

    @classmethod
    def from_config(cls, config: dict[str, Any], event_bus: EventBus) -> AudioPipeline:
        """Create an AudioPipeline from configuration."""
        asr_config = config.get("asr", {})
        tts_config = config.get("tts", {})

        asr_type = asr_config.get("type", "vad")
        tts_type = tts_config.get("type", "tone")

        asr: ASRBackend
        if asr_type == "openai":
            from effero.perception.audio.asr import OpenAIWhisperASR

            asr = OpenAIWhisperASR(api_key=asr_config.get("api_key"))
        elif asr_type == "faster_whisper":
            from effero.perception.audio.asr import FasterWhisperASR

            asr = FasterWhisperASR(model_size=asr_config.get("model_size", "small.en"))
        else:
            asr = EnergyVADASR(energy_threshold=asr_config.get("energy_threshold", 0.01))

        tts: TTSBackend
        if tts_type == "openai":
            from effero.perception.audio.tts import OpenAITTS

            tts = OpenAITTS(
                model=tts_config.get("model", "tts-1"),
                voice=tts_config.get("voice", "alloy"),
                api_key=tts_config.get("api_key"),
            )
        else:
            tts = ToneSynthesizerTTS(
                sample_rate=tts_config.get("sample_rate", 16000),
                base_freq=tts_config.get("base_freq", 440.0),
            )

        return cls(event_bus=event_bus, asr_backend=asr, tts_backend=tts)
