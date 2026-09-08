"""Tests for VoiceLoop voice interface and speech coordination."""

import pytest

from effero.core.agent import Agent
from effero.core.event_bus import EventBus
from effero.interfaces.voice import VoiceLoop
from effero.perception.audio.asr import EnergyVADASR
from effero.perception.audio.pipeline import AudioPipeline
from effero.perception.audio.tts import ToneSynthesizerTTS


@pytest.mark.asyncio
async def test_voice_loop_text_interaction():
    """Test VoiceLoop single interaction with plain string prompt."""
    bus = EventBus()
    pipeline = AudioPipeline(
        event_bus=bus,
        asr_backend=EnergyVADASR(),
        tts_backend=ToneSynthesizerTTS(),
    )

    spoken_chunks = []

    def on_speak(audio_bytes: bytes):
        spoken_chunks.append(audio_bytes)

    agent = Agent()

    # Mock agent.run to simulate real agent response without needing external cloud LLM API key
    async def _mock_run(instruction: str) -> str:
        return f"Processed: {instruction}"

    agent.run = _mock_run  # type: ignore[method-assign]

    voice_loop = VoiceLoop(
        agent=agent,
        audio_pipeline=pipeline,
        wake_word="effero",
        audio_output_callback=on_speak,
    )

    # Utterance without wake word should be ignored
    ignored_reply = await voice_loop.run_single_interaction("hello computer")
    assert ignored_reply == ""
    assert len(spoken_chunks) == 0

    # Utterance with wake word should process and synthesize audio
    reply = await voice_loop.run_single_interaction("effero what time is it")
    assert reply != ""
    assert len(spoken_chunks) == 1
    # Check that output is valid WAV header
    assert spoken_chunks[0][:4] == b"RIFF"
