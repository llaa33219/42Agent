"""
QMP (QEMU Machine Protocol) controller for keyboard/mouse input and screenshots.
"""

import asyncio
import json
import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)

KEY_MAP = {
    "enter": "ret",
    "return": "ret",
    "esc": "esc",
    "escape": "esc",
    "tab": "tab",
    "space": "spc",
    "backspace": "backspace",
    "delete": "delete",
    "insert": "insert",
    "home": "home",
    "end": "end",
    "pageup": "pgup",
    "pagedown": "pgdn",
    "up": "up",
    "down": "down",
    "left": "left",
    "right": "right",
    "f1": "f1", "f2": "f2", "f3": "f3", "f4": "f4",
    "f5": "f5", "f6": "f6", "f7": "f7", "f8": "f8",
    "f9": "f9", "f10": "f10", "f11": "f11", "f12": "f12",
    "ctrl": "ctrl", "alt": "alt", "shift": "shift",
    "super": "meta_l", "win": "meta_l", "meta": "meta_l",
    "capslock": "caps_lock",
}


class QMPController:
    def __init__(self, host: str = "localhost", port: int = 4444):
        self.host = host
        self.port = port
        self._reader: Optional[asyncio.StreamReader] = None
        self._writer: Optional[asyncio.StreamWriter] = None
        self._connected = False
        self._lock = asyncio.Lock()

    async def connect(self, max_retries: int = 5, retry_delay: float = 1.0) -> bool:
        for attempt in range(max_retries):
            try:
                self._reader, self._writer = await asyncio.open_connection(
                    self.host, self.port
                )

                greeting = await self._reader.readline()
                logger.debug(f"QMP greeting: {greeting.decode()}")

                await self._send({"execute": "qmp_capabilities"})
                response = await self._receive()

                if "return" in response:
                    self._connected = True
                    logger.info("QMP connected successfully")
                    return True

            except ConnectionRefusedError:
                if attempt < max_retries - 1:
                    await asyncio.sleep(retry_delay)
                continue
            except Exception as e:
                logger.error(f"QMP connection error: {e}")
                break

        return False

    async def disconnect(self):
        if self._writer:
            self._writer.close()
            await self._writer.wait_closed()
        self._connected = False
        logger.info("QMP disconnected")

    async def _send(self, data: dict):
        if not self._writer:
            raise RuntimeError("Not connected")
        message = json.dumps(data) + "\n"
        self._writer.write(message.encode())
        await self._writer.drain()

    async def _receive(self) -> dict:
        if not self._reader:
            raise RuntimeError("Not connected")
        line = await self._reader.readline()
        return json.loads(line.decode())

    async def execute(self, command: str, arguments: Optional[dict] = None) -> Any:
        async with self._lock:
            request = {"execute": command}
            if arguments:
                request["arguments"] = arguments

            await self._send(request)
            response = await self._receive()

            while "event" in response:
                response = await self._receive()

            if "error" in response:
                raise RuntimeError(f"QMP error: {response['error']}")

            return response.get("return")

    def _normalize_key(self, key: str) -> str:
        key_lower = key.lower()
        if key_lower in KEY_MAP:
            return KEY_MAP[key_lower]
        if len(key) == 1:
            return key.lower()
        return key_lower

    async def key_press(self, key: str, hold_time: float = 0.05):
        qcode = self._normalize_key(key)
        await self.execute("send-key", {
            "keys": [{"type": "qcode", "data": qcode}],
            "hold-time": int(hold_time * 1000)
        })

    async def key_combo(self, keys: str, hold_time: float = 0.1):
        key_list = [k.strip() for k in keys.split("+")]
        qcodes = [{"type": "qcode", "data": self._normalize_key(k)} for k in key_list]
        await self.execute("send-key", {
            "keys": qcodes,
            "hold-time": int(hold_time * 1000)
        })

    async def type_text(self, text: str, delay: float = 0.02):
        for char in text:
            if char == " ":
                await self.key_press("space")
            elif char == "\n":
                await self.key_press("enter")
            elif char == "\t":
                await self.key_press("tab")
            elif char.isupper():
                await self.key_combo(f"shift+{char.lower()}")
            else:
                await self.key_press(char)
            await asyncio.sleep(delay)

    async def mouse_move(self, x: int, y: int):
        await self.execute("input-send-event", {
            "events": [
                {"type": "abs", "data": {"axis": "x", "value": x}},
                {"type": "abs", "data": {"axis": "y", "value": y}}
            ]
        })

    async def mouse_click(self, button: str = "left"):
        btn_map = {"left": 0, "middle": 1, "right": 2}
        btn_code = btn_map.get(button, 0)

        await self.execute("input-send-event", {
            "events": [{"type": "btn", "data": {"down": True, "button": btn_code}}]
        })
        await asyncio.sleep(0.05)
        await self.execute("input-send-event", {
            "events": [{"type": "btn", "data": {"down": False, "button": btn_code}}]
        })

    async def mouse_double_click(self, button: str = "left"):
        await self.mouse_click(button)
        await asyncio.sleep(0.1)
        await self.mouse_click(button)

    async def mouse_drag(self, start_x: int, start_y: int, end_x: int, end_y: int):
        await self.mouse_move(start_x, start_y)
        await asyncio.sleep(0.05)

        await self.execute("input-send-event", {
            "events": [{"type": "btn", "data": {"down": True, "button": 0}}]
        })

        steps = 20
        for i in range(1, steps + 1):
            x = start_x + (end_x - start_x) * i // steps
            y = start_y + (end_y - start_y) * i // steps
            await self.mouse_move(x, y)
            await asyncio.sleep(0.01)

        await self.execute("input-send-event", {
            "events": [{"type": "btn", "data": {"down": False, "button": 0}}]
        })

    async def screenshot(self, filename: str = "/tmp/screenshot.ppm") -> str:
        await self.execute("screendump", {"filename": filename})
        return filename

    @property
    def is_connected(self) -> bool:
        return self._connected
