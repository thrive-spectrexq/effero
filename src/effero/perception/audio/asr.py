"""ASR (Automatic Speech Recognition) backends."""
from __future__ import annotations

import io
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
        except ImportError:
            raise ImportError("Please install openai: pip install openai")
            
        self.client = AsyncOpenAI(api_key=api_key)
        
    async def transcribe(self, audio_data: bytes) -> TranscriptionResult:
        file_obj = io.BytesIO(audio_data)
        file_obj.name = "audio.wav"
        
        response = await self.client.audio.transcriptions.create(
            model="whisper-1",
            file=file_obj,
            response_format="verbose_json"
        )
        
        return TranscriptionResult(
            text=response.text,
            language=getattr(response, "language", None),
            confidence=None,
            segments=getattr(response, "segments", [])
        )

class FasterWhisperASR(ASRBackend):
    """Local ASR using faster-whisper."""
    
    def __init__(self, model_size: str = "small.en") -> None:
        try:
            import faster_whisper
        except ImportError:
            raise ImportError("Please install faster-whisper: pip install faster-whisper")
            
        self.model_size = model_size
        self._model = None
        self._faster_whisper = faster_whisper
        
    def _get_model(self):
        if self._model is None:
            self._model = self._faster_whisper.WhisperModel(self.model_size, device="cpu", compute_type="int8")
        return self._model

    async def transcribe(self, audio_data: bytes) -> TranscriptionResult:
        import asyncio
        model = self._get_model()
        
        def _run_transcribe():
            file_obj = io.BytesIO(audio_data)
            segments, info = model.transcribe(file_obj, beam_size=5)
            segments_list = list(segments)
            text = " ".join([seg.text for seg in segments_list]).strip()
            return TranscriptionResult(
                text=text,
                language=info.language,
                confidence=info.language_probability,
                segments=[{"start": s.start, "end": s.end, "text": s.text} for s in segments_list]
            )
            
        return await asyncio.to_thread(_run_transcribe)

class MockASR(ASRBackend):
    """Mock ASR for testing."""
    
    def __init__(self, fixed_text: str = "This is a mock transcription.") -> None:
        self.fixed_text = fixed_text
        
    async def transcribe(self, audio_data: bytes) -> TranscriptionResult:
        return TranscriptionResult(text=self.fixed_text)
