"""
Main entry point for 42Agent application.
Integrates all components: Agent, VM, Avatar, UI.
"""

import asyncio
import logging
import os
import sys
from pathlib import Path
from typing import Optional

import pyaudio
from PyQt6.QtWidgets import QApplication

from .agent.core import Agent42
from .memory.rag import RAGMemory
from .memory.conversation import ConversationManager
from .vm.qemu_manager import QEMUManager, VMConfig
from .vm.qmp_controller import QMPController
from .vm.vnc_capture import VNCCapture
from .avatar.live2d_renderer import Live2DRenderer, AvatarConfig
from .avatar.lip_sync import LipSyncController
from .ui.main_window import MainWindow

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger(__name__)


class Agent42Application:
    def __init__(
        self,
        iso_path: str,
        avatar_model_path: str,
        api_key: Optional[str] = None,
        data_dir: str = "./data"
    ):
        self.iso_path = iso_path
        self.avatar_model_path = avatar_model_path
        self.api_key = api_key or os.getenv("DASHSCOPE_API_KEY")
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)

        self.qt_app: Optional[QApplication] = None
        self.window: Optional[MainWindow] = None
        self.agent: Optional[Agent42] = None
        self.vm_manager: Optional[QEMUManager] = None
        self.qmp: Optional[QMPController] = None
        self.vnc: Optional[VNCCapture] = None
        self.avatar: Optional[Live2DRenderer] = None
        self.lip_sync: Optional[LipSyncController] = None
        self.memory: Optional[RAGMemory] = None
        self.conversation: Optional[ConversationManager] = None

        self._audio_stream = None
        self._audio_interface = None
        self._running = False

    async def initialize(self) -> bool:
        logger.info("Initializing 42Agent...")

        self.memory = RAGMemory(persist_dir=str(self.data_dir / "memory"))
        self.conversation = ConversationManager(self.memory)

        vm_config = VMConfig(
            iso_path=self.iso_path,
            disk_path=str(self.data_dir / "vm" / "disk.qcow2"),
            memory="4096",
            cpus=2,
            vnc_port=5900,
            qmp_port=4444
        )
        self.vm_manager = QEMUManager(vm_config, str(self.data_dir / "vm"))

        self.qmp = QMPController(port=vm_config.qmp_port)
        self.vnc = VNCCapture(port=vm_config.vnc_port, fps=30)

        avatar_config = AvatarConfig(model_path=self.avatar_model_path)
        self.avatar = Live2DRenderer(avatar_config)
        self.lip_sync = LipSyncController()
        self.lip_sync.set_renderer(self.avatar)

        self.agent = Agent42(api_key=self.api_key)
        self.agent.set_vm_controller(self.qmp)
        self.agent.set_avatar_controller(self.avatar)
        self.agent.set_memory_manager(self.memory)

        self.agent.on_speech_output = self._on_agent_speech
        self.agent.on_text_output = self._on_agent_text

        return True

    async def start(self):
        logger.info("Starting 42Agent...")

        logger.info("Starting VM...")
        if not await self.vm_manager.start():
            raise RuntimeError("Failed to start VM")

        await asyncio.sleep(3)

        logger.info("Connecting to VM control...")
        if not await self.qmp.connect():
            raise RuntimeError("Failed to connect to QMP")

        if not await self.vnc.connect():
            raise RuntimeError("Failed to connect to VNC")

        logger.info("Initializing avatar...")
        await self.avatar.initialize()

        logger.info("Starting agent...")
        await self.agent.start()

        self._setup_audio()

        self._running = True
        asyncio.create_task(self._run_streams())

        logger.info("42Agent is ready!")

    def _setup_audio(self):
        self._audio_interface = pyaudio.PyAudio()

        self._mic_stream = self._audio_interface.open(
            format=pyaudio.paInt16,
            channels=1,
            rate=16000,
            input=True,
            frames_per_buffer=3200
        )

        self._speaker_stream = self._audio_interface.open(
            format=pyaudio.paInt16,
            channels=1,
            rate=24000,
            output=True
        )

    async def _run_streams(self):
        video_task = asyncio.create_task(self._video_stream_loop())
        audio_task = asyncio.create_task(self._audio_stream_loop())

        await asyncio.gather(video_task, audio_task)

    async def _video_stream_loop(self):
        while self._running:
            try:
                frame = await self.vnc.capture_frame()
                if frame:
                    await self.agent.send_frame(frame)
                    if self.window:
                        self.window.update_vm_frame(frame)
                await asyncio.sleep(1 / 30)
            except Exception as e:
                logger.error(f"Video stream error: {e}")
                await asyncio.sleep(0.1)

    async def _audio_stream_loop(self):
        while self._running:
            try:
                audio_data = await asyncio.to_thread(
                    self._mic_stream.read,
                    3200,
                    exception_on_overflow=False
                )
                await self.agent.send_audio(audio_data)
                await asyncio.sleep(0.01)
            except Exception as e:
                logger.error(f"Audio stream error: {e}")
                await asyncio.sleep(0.1)

    def _on_agent_speech(self, audio_data: bytes):
        if self._speaker_stream:
            self._speaker_stream.write(audio_data)

        self.lip_sync.process_audio(audio_data)

        if self.window:
            self.window.process_audio(audio_data)

    def _on_agent_text(self, text: str):
        if self.window:
            self.window.add_chat_message("agent42", text)

        asyncio.create_task(
            self.conversation.add_message("assistant", text)
        )

    async def _on_user_message(self, text: str):
        await self.conversation.add_message("user", text)

    def run_ui(self):
        self.qt_app = QApplication(sys.argv)

        self.window = MainWindow(
            avatar_renderer=self.avatar,
            lip_sync=self.lip_sync
        )

        self.window.set_message_callback(
            lambda msg: asyncio.create_task(self._on_user_message(msg))
        )

        self.vnc.set_frame_callback(self.window.update_vm_frame)

        self.window.show()

        return self.qt_app.exec()

    async def stop(self):
        logger.info("Stopping 42Agent...")
        self._running = False

        if self.agent:
            await self.agent.stop()

        if self.vnc:
            await self.vnc.disconnect()

        if self.qmp:
            await self.qmp.disconnect()

        if self.vm_manager:
            await self.vm_manager.stop()

        if self._mic_stream:
            self._mic_stream.stop_stream()
            self._mic_stream.close()

        if self._speaker_stream:
            self._speaker_stream.stop_stream()
            self._speaker_stream.close()

        if self._audio_interface:
            self._audio_interface.terminate()

        if self.conversation:
            await self.conversation.summarize_and_archive_all()

        logger.info("42Agent stopped")


async def main(iso_path: str, avatar_path: str):
    app = Agent42Application(
        iso_path=iso_path,
        avatar_model_path=avatar_path
    )

    await app.initialize()

    loop = asyncio.get_event_loop()
    loop.create_task(app.start())

    exit_code = app.run_ui()

    await app.stop()

    return exit_code


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="42Agent - Autonomous AI Agent")
    parser.add_argument("--iso", required=True, help="Path to VM ISO file")
    parser.add_argument("--avatar", required=True, help="Path to Live2D model")
    args = parser.parse_args()

    asyncio.run(main(args.iso, args.avatar))
