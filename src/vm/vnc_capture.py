"""
VNC screen capture for streaming VM display at 30fps.
Uses the vncdotool library for VNC protocol handling.
"""

import asyncio
import io
import logging
from typing import Callable, Optional

from PIL import Image

logger = logging.getLogger(__name__)


class VNCCapture:
    def __init__(
        self,
        host: str = "localhost",
        port: int = 5900,
        width: int = 1920,
        height: int = 1080,
        fps: int = 30
    ):
        self.host = host
        self.port = port
        self.width = width
        self.height = height
        self.fps = fps

        self._client = None
        self._running = False
        self._capture_task: Optional[asyncio.Task] = None
        self._frame_callback: Optional[Callable[[bytes], None]] = None

    async def connect(self, max_retries: int = 10, retry_delay: float = 1.0) -> bool:
        try:
            from vncdotool import api as vnc_api
        except ImportError:
            logger.error("vncdotool not installed. Run: pip install vncdotool")
            return False

        for attempt in range(max_retries):
            try:
                self._client = await asyncio.to_thread(
                    vnc_api.connect,
                    f"{self.host}::{self.port}"
                )
                logger.info(f"VNC connected to {self.host}:{self.port}")
                return True
            except Exception as e:
                if attempt < max_retries - 1:
                    logger.debug(f"VNC connection attempt {attempt + 1} failed: {e}")
                    await asyncio.sleep(retry_delay)
                else:
                    logger.error(f"VNC connection failed after {max_retries} attempts")
        return False

    async def disconnect(self):
        self._running = False
        if self._capture_task:
            self._capture_task.cancel()
            try:
                await self._capture_task
            except asyncio.CancelledError:
                pass

        if self._client:
            try:
                await asyncio.to_thread(self._client.disconnect)
            except Exception:
                pass
            self._client = None
        logger.info("VNC disconnected")

    async def capture_frame(self) -> Optional[bytes]:
        if not self._client:
            return None

        try:
            screenshot = await asyncio.to_thread(self._client.screen)

            if screenshot.size != (self.width, self.height):
                screenshot = screenshot.resize(
                    (self.width, self.height),
                    Image.Resampling.LANCZOS
                )

            buffer = io.BytesIO()
            screenshot.save(buffer, format="JPEG", quality=80)
            return buffer.getvalue()

        except Exception as e:
            logger.error(f"Frame capture error: {e}")
            return None

    async def capture_frame_raw(self) -> Optional[bytes]:
        if not self._client:
            return None

        try:
            screenshot = await asyncio.to_thread(self._client.screen)

            if screenshot.size != (self.width, self.height):
                screenshot = screenshot.resize(
                    (self.width, self.height),
                    Image.Resampling.LANCZOS
                )

            return screenshot.tobytes()

        except Exception as e:
            logger.error(f"Raw frame capture error: {e}")
            return None

    def set_frame_callback(self, callback: Callable[[bytes], None]):
        self._frame_callback = callback

    async def start_streaming(self):
        self._running = True
        self._capture_task = asyncio.create_task(self._stream_loop())

    async def _stream_loop(self):
        frame_interval = 1.0 / self.fps
        last_frame_time = 0.0

        while self._running:
            try:
                current_time = asyncio.get_event_loop().time()
                elapsed = current_time - last_frame_time

                if elapsed < frame_interval:
                    await asyncio.sleep(frame_interval - elapsed)

                frame = await self.capture_frame()
                if frame and self._frame_callback:
                    self._frame_callback(frame)

                last_frame_time = asyncio.get_event_loop().time()

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Stream error: {e}")
                await asyncio.sleep(0.1)

    async def stop_streaming(self):
        self._running = False
        if self._capture_task:
            self._capture_task.cancel()
            try:
                await self._capture_task
            except asyncio.CancelledError:
                pass

    async def read(self) -> Optional[bytes]:
        return await self.capture_frame()

    @property
    def is_connected(self) -> bool:
        return self._client is not None

    @property
    def is_streaming(self) -> bool:
        return self._running
