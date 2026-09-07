"""TTS (Text-to-Speech) backends."""
from __future__ import annotations

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
        except ImportError:
            raise ImportError("Please install openai: pip install openai")
            
        self.client = AsyncOpenAI(api_key=api_key)
        self.model = model
        self.voice = voice
        
    async def synthesize(self, text: str) -> bytes:
        response = await self.client.audio.speech.create(
            model=self.model,
            voice=self.voice,
            input=text
        )
        return response.read()

class MockTTS(TTSBackend):
    """Mock TTS for testing."""
    
    async def synthesize(self, text: str) -> bytes:
        return b""
