"""
Lip sync controller for Live2D avatar.
Analyzes audio amplitude to control mouth movements.
"""

import asyncio
import logging
import math
import struct
from collections import deque
from typing import Optional

logger = logging.getLogger(__name__)


class LipSyncController:
    def __init__(
        self,
        sample_rate: int = 24000,
        smoothing: float = 0.3,
        sensitivity: float = 1.5,
        threshold: float = 0.02
    ):
        self.sample_rate = sample_rate
        self.smoothing = smoothing
        self.sensitivity = sensitivity
        self.threshold = threshold

        self._current_value = 0.0
        self._target_value = 0.0
        self._amplitude_history: deque[float] = deque(maxlen=10)
        self._renderer = None

    def set_renderer(self, renderer):
        self._renderer = renderer

    def process_audio(self, audio_data: bytes):
        if len(audio_data) < 2:
            return

        try:
            samples = struct.unpack(f"<{len(audio_data) // 2}h", audio_data)

            if not samples:
                return

            rms = math.sqrt(sum(s * s for s in samples) / len(samples))
            normalized = rms / 32768.0

            self._amplitude_history.append(normalized)
            avg_amplitude = sum(self._amplitude_history) / len(self._amplitude_history)

            if avg_amplitude < self.threshold:
                self._target_value = 0.0
            else:
                self._target_value = min(1.0, avg_amplitude * self.sensitivity)

        except Exception as e:
            logger.error(f"Lip sync processing error: {e}")

    def update(self, delta_time: float):
        diff = self._target_value - self._current_value
        self._current_value += diff * min(1.0, self.smoothing * delta_time * 60)

        if self._renderer:
            self._renderer.set_mouth_open(self._current_value)

    def reset(self):
        self._current_value = 0.0
        self._target_value = 0.0
        self._amplitude_history.clear()

        if self._renderer:
            self._renderer.set_mouth_open(0.0)

    @property
    def mouth_value(self) -> float:
        return self._current_value

    @property
    def is_speaking(self) -> bool:
        return self._current_value > self.threshold
