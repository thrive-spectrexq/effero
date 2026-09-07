"""Audio perception module."""

from __future__ import annotations

from effero.perception.audio.asr import (
    ASRBackend,
    EnergyVADASR,
    FasterWhisperASR,
    OpenAIWhisperASR,
    TranscriptionResult,
)
from effero.perception.audio.pipeline import AudioPipeline
from effero.perception.audio.tts import OpenAITTS, ToneSynthesizerTTS, TTSBackend

__all__ = [
    "ASRBackend",
    "TranscriptionResult",
    "OpenAIWhisperASR",
    "FasterWhisperASR",
    "EnergyVADASR",
    "TTSBackend",
    "OpenAITTS",
    "ToneSynthesizerTTS",
    "AudioPipeline",
]
