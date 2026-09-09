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


@pytest.mark.asyncio
async def test_voice_loop_audio_bytes_and_empty():
    bus = EventBus()
    pipeline = AudioPipeline(
        event_bus=bus,
        asr_backend=EnergyVADASR(),
        tts_backend=ToneSynthesizerTTS(),
    )
    agent = Agent()

    async def _mock_run(instruction: str) -> str:
        return f"Echo: {instruction}"

    agent.run = _mock_run  # type: ignore[method-assign]

    voice_loop = VoiceLoop(agent=agent, audio_pipeline=pipeline)

    # 1. Empty input returns ""
    assert await voice_loop.run_single_interaction("   ") == ""

    # 2. Audio bytes input processed via pipeline
    fake_wav = await pipeline.speak("hello world")
    result = await voice_loop.run_single_interaction(fake_wav)
    assert "Echo:" in result

    # 3. Audio bytes without pipeline raises RuntimeError
    no_pipe_loop = VoiceLoop(agent=agent, audio_pipeline=None)
    with pytest.raises(RuntimeError, match="AudioPipeline required"):
        await no_pipe_loop.run_single_interaction(fake_wav)


@pytest.mark.asyncio
async def test_voice_loop_async_callback_and_error():
    bus = EventBus()
    pipeline = AudioPipeline(event_bus=bus, tts_backend=ToneSynthesizerTTS())
    agent = Agent()

    async def _mock_run(instruction: str) -> str:
        return "Answer"

    agent.run = _mock_run  # type: ignore[method-assign]

    async_calls = []

    async def async_cb(data: bytes):
        async_calls.append(len(data))

    # Async callback works
    loop_async = VoiceLoop(agent=agent, audio_pipeline=pipeline, audio_output_callback=async_cb)
    await loop_async.run_single_interaction("test")
    assert len(async_calls) == 1

    # Faulty callback does not crash
    def crashing_cb(data: bytes):
        raise ValueError("Audio device disconnected")

    loop_crash = VoiceLoop(agent=agent, audio_pipeline=pipeline, audio_output_callback=crashing_cb)
    # Should not raise exception
    res = await loop_crash.run_single_interaction("test")
    assert res == "Answer"


@pytest.mark.asyncio
async def test_voice_loop_interactive():
    from unittest.mock import patch

    agent = Agent()

    async def _mock_run(instruction: str) -> str:
        return f"Ok: {instruction}"

    agent.run = _mock_run  # type: ignore[method-assign]

    voice_loop = VoiceLoop(agent=agent)

    # Simulate typing "hi", empty line, then "exit"
    inputs = iter(["hi", "", "exit"])
    with patch("builtins.input", side_effect=lambda *args: next(inputs)):
        await voice_loop.run_interactive()
        assert not voice_loop._running
