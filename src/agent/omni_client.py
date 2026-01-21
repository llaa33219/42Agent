"""
Qwen3-Omni-Flash Realtime WebSocket Client for real-time omnimodal interaction.
"""

import asyncio
import base64
import json
import logging
import os
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Optional

import websockets
from websockets.client import WebSocketClientProtocol

logger = logging.getLogger(__name__)


class ConnectionState(Enum):
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    ERROR = "error"


@dataclass
class SessionConfig:
    voice: str = "Chelsie"
    input_audio_format: str = "pcm16"
    output_audio_format: str = "pcm24"
    modalities: list = field(default_factory=lambda: ["text", "audio"])
    instructions: str = ""
    turn_detection: Optional[dict] = field(default_factory=lambda: {
        "type": "server_vad",
        "threshold": 0.5,
        "silence_duration_ms": 800
    })


class OmniRealtimeClient:
    API_URL_INTL = "wss://dashscope-intl.aliyuncs.com/api-ws/v1/realtime"
    API_URL_CN = "wss://dashscope.aliyuncs.com/api-ws/v1/realtime"
    MODEL = "qwen3-omni-flash-realtime"

    def __init__(
        self,
        api_key: Optional[str] = None,
        region: str = "intl",
        config: Optional[SessionConfig] = None
    ):
        self.api_key = api_key or os.getenv("DASHSCOPE_API_KEY")
        if not self.api_key:
            raise ValueError("DASHSCOPE_API_KEY is required")

        self.base_url = self.API_URL_INTL if region == "intl" else self.API_URL_CN
        self.config = config or SessionConfig()
        self.state = ConnectionState.DISCONNECTED
        self.ws: Optional[WebSocketClientProtocol] = None
        self._event_id_counter = 0

        self.on_text_delta: Optional[Callable[[str], None]] = None
        self.on_text_done: Optional[Callable[[str], None]] = None
        self.on_audio_delta: Optional[Callable[[bytes], None]] = None
        self.on_audio_done: Optional[Callable[[], None]] = None
        self.on_transcript_delta: Optional[Callable[[str], None]] = None
        self.on_input_transcript: Optional[Callable[[str], None]] = None
        self.on_speech_started: Optional[Callable[[], None]] = None
        self.on_speech_stopped: Optional[Callable[[], None]] = None
        self.on_error: Optional[Callable[[str], None]] = None

        self._receive_task: Optional[asyncio.Task] = None
        self._text_buffer = ""
        self._audio_buffer = b""

    def _generate_event_id(self) -> str:
        self._event_id_counter += 1
        return f"evt_{self._event_id_counter:08d}"

    async def connect(self) -> bool:
        if self.state == ConnectionState.CONNECTED:
            return True

        self.state = ConnectionState.CONNECTING
        url = f"{self.base_url}?model={self.MODEL}"

        try:
            self.ws = await websockets.connect(
                url,
                additional_headers={"Authorization": f"Bearer {self.api_key}"},
                ping_interval=20,
                ping_timeout=60,
                max_size=10 * 1024 * 1024
            )
            self.state = ConnectionState.CONNECTED
            logger.info(f"Connected to {self.MODEL}")

            self._receive_task = asyncio.create_task(self._receive_loop())
            await self._update_session()
            return True

        except Exception as e:
            self.state = ConnectionState.ERROR
            logger.error(f"Connection failed: {e}")
            if self.on_error:
                self.on_error(str(e))
            return False

    async def disconnect(self):
        if self._receive_task:
            self._receive_task.cancel()
            try:
                await self._receive_task
            except asyncio.CancelledError:
                pass

        if self.ws:
            await self.ws.close()
            self.ws = None

        self.state = ConnectionState.DISCONNECTED
        logger.info("Disconnected")

    async def _update_session(self):
        session_update = {
            "event_id": self._generate_event_id(),
            "type": "session.update",
            "session": {
                "modalities": self.config.modalities,
                "voice": self.config.voice,
                "input_audio_format": self.config.input_audio_format,
                "output_audio_format": self.config.output_audio_format,
                "instructions": self.config.instructions,
                "turn_detection": self.config.turn_detection
            }
        }
        await self._send(session_update)

    async def _send(self, data: dict):
        if self.ws and self.state == ConnectionState.CONNECTED:
            await self.ws.send(json.dumps(data))

    async def _receive_loop(self):
        try:
            if self.ws is None:
                return
            async for message in self.ws:
                await self._handle_message(json.loads(message))
        except websockets.ConnectionClosed:
            logger.info("Connection closed")
            self.state = ConnectionState.DISCONNECTED
        except Exception as e:
            logger.error(f"Receive error: {e}")
            self.state = ConnectionState.ERROR

    async def _handle_message(self, data: dict):
        event_type = data.get("type", "")

        if event_type == "response.text.delta":
            delta = data.get("delta", "")
            self._text_buffer += delta
            if self.on_text_delta:
                self.on_text_delta(delta)

        elif event_type == "response.text.done":
            if self.on_text_done:
                self.on_text_done(self._text_buffer)
            self._text_buffer = ""

        elif event_type == "response.audio.delta":
            audio_b64 = data.get("delta", "")
            if audio_b64:
                audio_bytes = base64.b64decode(audio_b64)
                self._audio_buffer += audio_bytes
                if self.on_audio_delta:
                    self.on_audio_delta(audio_bytes)

        elif event_type == "response.audio.done":
            if self.on_audio_done:
                self.on_audio_done()
            self._audio_buffer = b""

        elif event_type == "response.audio_transcript.delta":
            delta = data.get("delta", "")
            if self.on_transcript_delta:
                self.on_transcript_delta(delta)

        elif event_type == "conversation.item.input_audio_transcription.completed":
            transcript = data.get("transcript", "")
            if self.on_input_transcript:
                self.on_input_transcript(transcript)

        elif event_type == "input_audio_buffer.speech_started":
            if self.on_speech_started:
                self.on_speech_started()

        elif event_type == "input_audio_buffer.speech_stopped":
            if self.on_speech_stopped:
                self.on_speech_stopped()

        elif event_type == "error":
            error_msg = data.get("error", {}).get("message", "Unknown error")
            logger.error(f"API Error: {error_msg}")
            if self.on_error:
                self.on_error(error_msg)

    async def send_audio(self, audio_data: bytes):
        audio_b64 = base64.b64encode(audio_data).decode("ascii")
        await self._send({
            "event_id": self._generate_event_id(),
            "type": "input_audio_buffer.append",
            "audio": audio_b64
        })

    async def send_image(self, image_data: bytes):
        image_b64 = base64.b64encode(image_data).decode("ascii")
        await self._send({
            "event_id": self._generate_event_id(),
            "type": "input_image_buffer.append",
            "image": image_b64
        })

    async def commit_audio(self):
        await self._send({
            "event_id": self._generate_event_id(),
            "type": "input_audio_buffer.commit"
        })

    async def create_response(self):
        await self._send({
            "event_id": self._generate_event_id(),
            "type": "response.create"
        })

    async def cancel_response(self):
        await self._send({
            "event_id": self._generate_event_id(),
            "type": "response.cancel"
        })

    @property
    def is_connected(self) -> bool:
        return self.state == ConnectionState.CONNECTED
