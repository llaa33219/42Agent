"""
Core Agent42 implementation - the main autonomous agent controller.
"""

import asyncio
import logging
from typing import Optional

from .omni_client import OmniRealtimeClient, SessionConfig
from .system_prompt import SYSTEM_PROMPT, VOICE_CONFIG
from .tools import ToolExecutor

logger = logging.getLogger(__name__)


class Agent42:
    def __init__(
        self,
        api_key: Optional[str] = None,
        region: str = "intl"
    ):
        config = SessionConfig(
            voice=VOICE_CONFIG["voice"],
            instructions=SYSTEM_PROMPT,
            modalities=["text", "audio"]
        )

        self.client = OmniRealtimeClient(
            api_key=api_key,
            region=region,
            config=config
        )
        self.tools = ToolExecutor()

        self._running = False
        self._audio_queue: asyncio.Queue[bytes] = asyncio.Queue()
        self._frame_queue: asyncio.Queue[bytes] = asyncio.Queue()

        self.on_speech_output: Optional[callable] = None
        self.on_text_output: Optional[callable] = None

        self._setup_callbacks()

    def _setup_callbacks(self):
        self.client.on_text_done = self._on_text_received
        self.client.on_audio_delta = self._on_audio_received
        self.client.on_input_transcript = self._on_user_speech
        self.client.on_speech_started = self._on_speech_started
        self.client.on_speech_stopped = self._on_speech_stopped

    def _on_text_received(self, text: str):
        logger.debug(f"Agent text: {text}")
        asyncio.create_task(self._process_text(text))

    async def _process_text(self, text: str):
        results = await self.tools.execute_all(text)
        for tool, result in results:
            logger.info(f"Tool {tool.name} result: {result}")

        clean_text = self.tools.strip_tools(text)
        if clean_text and self.on_text_output:
            self.on_text_output(clean_text)

    def _on_audio_received(self, audio: bytes):
        if self.on_speech_output:
            self.on_speech_output(audio)

    def _on_user_speech(self, transcript: str):
        logger.info(f"User said: {transcript}")

    def _on_speech_started(self):
        logger.debug("User started speaking")

    def _on_speech_stopped(self):
        logger.debug("User stopped speaking")

    def set_vm_controller(self, controller):
        self.tools.set_vm_controller(controller)

    def set_avatar_controller(self, controller):
        self.tools.set_avatar_controller(controller)

    def set_memory_manager(self, manager):
        self.tools.set_memory_manager(manager)

    async def start(self):
        logger.info("Starting Agent42...")
        success = await self.client.connect()
        if not success:
            raise RuntimeError("Failed to connect to Qwen API")

        self._running = True
        logger.info("Agent42 is now active")

    async def stop(self):
        logger.info("Stopping Agent42...")
        self._running = False
        await self.client.disconnect()
        logger.info("Agent42 stopped")

    async def send_audio(self, audio_data: bytes):
        if self.client.is_connected:
            await self.client.send_audio(audio_data)

    async def send_frame(self, frame_data: bytes):
        if self.client.is_connected:
            await self.client.send_image(frame_data)

    async def run_audio_stream(self, audio_source):
        while self._running:
            try:
                audio_chunk = await asyncio.wait_for(
                    audio_source.read(),
                    timeout=0.1
                )
                if audio_chunk:
                    await self.send_audio(audio_chunk)
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                logger.error(f"Audio stream error: {e}")
                break

    async def run_video_stream(self, frame_source, fps: int = 30):
        frame_interval = 1.0 / fps
        while self._running:
            try:
                frame = await asyncio.wait_for(
                    frame_source.read(),
                    timeout=frame_interval
                )
                if frame:
                    await self.send_frame(frame)
                await asyncio.sleep(frame_interval)
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                logger.error(f"Video stream error: {e}")
                break

    @property
    def is_running(self) -> bool:
        return self._running
