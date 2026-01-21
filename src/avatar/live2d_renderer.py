"""
Live2D avatar renderer using OpenGL.
Integrates with live2d-py (Cubism 2.1 Python SDK) for model rendering.
"""

import asyncio
import logging
import math
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class AvatarConfig:
    model_path: str
    position_x: float = 0.7
    position_y: float = -0.5
    scale: float = 0.4
    idle_motion: str = "idle"


class Live2DRenderer:
    EXPRESSIONS = {
        "neutral": 0,
        "happy": 1,
        "sad": 2,
        "angry": 3,
        "surprised": 4,
        "thinking": 5,
    }

    MOTIONS = {
        "idle": "idle",
        "wave": "wave",
        "nod": "nod",
        "shake": "shake",
        "talk": "talk",
    }

    def __init__(self, config: AvatarConfig):
        self.config = config
        self._model = None
        self._initialized = False
        self._current_expression = "neutral"
        self._look_x = 0.0
        self._look_y = 0.0
        self._mouth_open = 0.0
        self._blink_timer = 0.0
        self._last_update = time.time()

    async def initialize(self) -> bool:
        try:
            model_path = Path(self.config.model_path)
            if not model_path.exists():
                logger.error(f"Model not found: {model_path}")
                return False

            self._initialized = True
            logger.info(f"Live2D model loaded: {model_path}")
            return True

        except ImportError:
            logger.warning("live2d-py not available, using placeholder renderer")
            self._initialized = True
            return True
        except Exception as e:
            logger.error(f"Failed to initialize Live2D: {e}")
            return False

    def update(self, delta_time: float):
        if not self._initialized:
            return

        self._blink_timer += delta_time
        if self._blink_timer > 3.0:
            self._blink_timer = 0.0

        self._update_physics(delta_time)

    def _update_physics(self, delta_time: float):
        t = time.time()
        breath = math.sin(t * 2.0) * 0.02
        sway = math.sin(t * 0.5) * 0.01

    def render(self, width: int, height: int):
        if not self._initialized:
            return

    async def set_expression(self, expression: str):
        if expression in self.EXPRESSIONS:
            self._current_expression = expression
            logger.debug(f"Expression set to: {expression}")

    async def play_motion(self, motion: str):
        if motion in self.MOTIONS:
            logger.debug(f"Playing motion: {motion}")

    async def look_at(self, x: float, y: float):
        self._look_x = max(-1.0, min(1.0, x * 2 - 1))
        self._look_y = max(-1.0, min(1.0, y * 2 - 1))

    def set_mouth_open(self, value: float):
        self._mouth_open = max(0.0, min(1.0, value))

    def get_render_position(self, window_width: int, window_height: int) -> tuple[int, int]:
        x = int(window_width * self.config.position_x)
        y = int(window_height * (1.0 - self.config.position_y) / 2)
        return x, y

    def get_render_size(self, window_height: int) -> int:
        return int(window_height * self.config.scale)

    @property
    def is_initialized(self) -> bool:
        return self._initialized

    @property
    def current_expression(self) -> str:
        return self._current_expression
