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
from qasync import QEventLoop, asyncSlot, asyncClose

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

        self._mic_stream = None
        self._speaker_stream = None
        self._audio_interface = None
        self._running = False
        self._has_microphone = False

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

        # Audio setup is optional - continue even if it fails
        try:
            self._setup_audio()
            self._has_microphone = True
            logger.info("Audio initialized")
        except Exception as e:
            self._has_microphone = False
            logger.warning(f"Audio setup failed (continuing without audio): {e}")

        # Start video stream (VM display should always work)
        self._running = True
        asyncio.create_task(self._run_streams())
        logger.info("Video stream started")

        # Agent connection is optional - continue even if it fails
        logger.info("Starting agent...")
        try:
            await self.agent.start()
            logger.info("42Agent is ready!")
        except Exception as e:
            logger.warning(f"Agent API connection failed: {e}")
            logger.info("42Agent running in offline mode (VM display only)")

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
        # Qwen3-Omni API requires audio to be sent before/with images
        # When no microphone, send silent audio periodically to satisfy this requirement
        silent_audio = b'\x00' * 3200  # 100ms of silence at 16kHz mono 16-bit
        
        while self._running:
            try:
                frame = await self.vnc.capture_frame()
                if frame:
                    # Update UI first (always works)
                    if self.window:
                        self.window.update_vm_frame(frame)
                    # Send to agent (may fail if not connected)
                    try:
                        if self.agent and self.agent.client.is_connected:
                            # API requires audio before/with image - send silent audio if no mic
                            if not self._has_microphone:
                                await self.agent.send_audio(silent_audio)
                            await self.agent.send_frame(frame)
                    except Exception as e:
                        # Agent not connected, but continue showing VM
                        pass
                await asyncio.sleep(1 / 30)
            except Exception as e:
                logger.error(f"Video stream error: {e}")
                await asyncio.sleep(0.1)

    async def _audio_stream_loop(self):
        if not self._mic_stream:
            logger.info("Audio stream disabled (no microphone)")
            return
        
        while self._running:
            try:
                audio_data = await asyncio.to_thread(
                    self._mic_stream.read,
                    3200,
                    exception_on_overflow=False
                )
                if self.agent:
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
        """Deprecated: UI is now initialized in main() with proper event loop integration."""
        pass

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


def main(iso_path: str, avatar_path: str):
    """Main entry with proper asyncio + Qt event loop integration."""
    qt_app = QApplication(sys.argv)
    
    # Initialize Live2D library globally (must be before any model creation)
    Live2DRenderer.global_init()
    
    # Create qasync event loop that integrates asyncio with Qt
    loop = QEventLoop(qt_app)
    asyncio.set_event_loop(loop)
    
    app = Agent42Application(
        iso_path=iso_path,
        avatar_model_path=avatar_path
    )
    
    async def run():
        await app.initialize()
        
        # Setup UI before starting backend services
        app.qt_app = qt_app
        app.window = MainWindow(
            avatar_renderer=app.avatar,
            lip_sync=app.lip_sync
        )
        app.window.set_message_callback(
            lambda msg: asyncio.create_task(app._on_user_message(msg))
        )
        app.vnc.set_frame_callback(app.window.update_vm_frame)
        app.window.show()
        
        # Start backend services (VM, VNC, etc.) after UI is visible
        try:
            await app.start()
        except Exception as e:
            logger.error(f"Failed to start backend: {e}")
            # UI remains visible even if backend fails
    
    # Stop event loop when window is closed
    qt_app.aboutToQuit.connect(lambda: loop.stop())
    
    # Schedule the async startup
    loop.create_task(run())
    
    # Run the combined Qt + asyncio event loop
    with loop:
        try:
            loop.run_forever()
        except KeyboardInterrupt:
            pass
        finally:
            loop.run_until_complete(app.stop())
            # Dispose Live2D library on shutdown
            Live2DRenderer.global_dispose()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="42Agent - Autonomous AI Agent")
    parser.add_argument("--iso", required=True, help="Path to VM ISO file")
    parser.add_argument("--avatar", required=True, help="Path to Live2D model")
    args = parser.parse_args()

    main(args.iso, args.avatar)
