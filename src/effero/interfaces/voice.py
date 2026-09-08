"""End-to-End Voice loop interface — listens for speech, executes via Agent, and speaks response."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from effero.core.agent import Agent
    from effero.perception.audio.pipeline import AudioPipeline

logger = logging.getLogger(__name__)


class VoiceLoop:
    """Manages continuous or push-to-talk voice interactions with an Effero agent."""

    def __init__(
        self,
        agent: Agent,
        audio_pipeline: AudioPipeline | None = None,
        wake_word: str | None = None,
        audio_output_callback: Callable[[bytes], Any] | None = None,
    ) -> None:
        self.agent = agent
        self.audio_pipeline = audio_pipeline
        self.wake_word = wake_word
        self.audio_output_callback = audio_output_callback
        self._running = False

    async def run_single_interaction(self, input_text_or_audio: str | bytes) -> str:
        """Process one voice turn: transcribe (if audio), plan/act via Agent, synthesize speech."""
        user_prompt: str

        if isinstance(input_text_or_audio, bytes):
            if not self.audio_pipeline:
                raise RuntimeError("AudioPipeline required to transcribe audio bytes")
            logger.info("Transcribing audio input...")
            user_prompt = await self.audio_pipeline.process_audio(input_text_or_audio)
        else:
            user_prompt = str(input_text_or_audio)

        if not user_prompt.strip():
            return ""

        # Check wake-word filter if configured
        if self.wake_word:
            lower = user_prompt.lower()
            if self.wake_word.lower() not in lower:
                logger.debug(f"Wake word '{self.wake_word}' not detected in utterance: {user_prompt}")
                return ""
            # Strip out wake word from beginning
            idx = lower.find(self.wake_word.lower())
            user_prompt = user_prompt[idx + len(self.wake_word) :].strip()

        logger.info(f"Voice query: {user_prompt}")
        agent_reply = await self.agent.run(user_prompt)
        logger.info(f"Agent response: {agent_reply}")

        # Synthesize audio speech feedback if pipeline is active
        if self.audio_pipeline:
            audio_response = await self.audio_pipeline.speak(agent_reply)
            if self.audio_output_callback:
                try:
                    res = self.audio_output_callback(audio_response)
                    if asyncio.iscoroutine(res):
                        await res
                except Exception as e:
                    logger.warning(f"Audio output callback error: {e}")

        return agent_reply

    async def run_interactive(self) -> None:
        """Run continuous voice conversation loop via terminal / microphone prompt."""
        self._running = True
        print("Effero Voice Loop started. Type message to speak (or press Ctrl+C to stop):")

        loop = asyncio.get_running_loop()
        while self._running:
            try:
                line = await loop.run_in_executor(None, lambda: input("Voice input >> "))
                if line.strip().lower() in ("exit", "quit"):
                    break
                if not line.strip():
                    continue

                reply = await self.run_single_interaction(line)
                print(f"Effero: {reply}\n")
            except (EOFError, KeyboardInterrupt):
                break
        self._running = False
        print("\nVoice Loop exited.")
