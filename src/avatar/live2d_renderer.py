"""
Live2D avatar renderer using live2d-py (Cubism 3 SDK).
Integrates with PyQt6 OpenGL for model rendering.
"""

import logging
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Callable

logger = logging.getLogger(__name__)

# Set environment variable for Qt OpenGL backend
os.environ["QSG_RHI_BACKEND"] = "opengl"

# Try to import live2d-py
try:
    import live2d.v3 as live2d
    from live2d.v3 import StandardParams
    LIVE2D_AVAILABLE = True
except ImportError:
    LIVE2D_AVAILABLE = False
    live2d = None
    StandardParams = None
    logger.warning("live2d-py not installed. Run: pip install live2d-py")


@dataclass
class AvatarConfig:
    model_path: str
    position_x: float = 0.7
    position_y: float = -0.5
    scale: float = 1.0
    idle_motion: str = "Idle"


class Live2DRenderer:
    """Live2D model renderer using live2d-py Cubism 3 SDK."""
    
    EXPRESSIONS = {
        "neutral": "Normal",
        "happy": "Happy",
        "sad": "Sad",
        "angry": "Angry",
        "surprised": "Surprised",
        "thinking": "Normal",
    }

    MOTIONS = {
        "idle": "Idle",
        "wave": "Tap",
        "nod": "Flick",
        "shake": "Flick",
        "talk": "Idle",
    }

    _global_initialized = False

    def __init__(self, config: AvatarConfig):
        self.config = config
        self._model: Optional["live2d.LAppModel"] = None
        self._initialized = False
        self._gl_initialized = False
        self._current_expression = "neutral"
        self._look_x = 0.0
        self._look_y = 0.0
        self._mouth_open = 0.0
        self._last_update = time.time()
        self._width = 800
        self._height = 600
        self._offset_x = 0.0
        self._offset_y = 0.0

    @classmethod
    def global_init(cls):
        """Initialize Live2D library globally (call once before creating any models)."""
        if not LIVE2D_AVAILABLE:
            logger.warning("live2d-py not available, skipping global init")
            return False
        
        if not cls._global_initialized:
            try:
                live2d.init()
                cls._global_initialized = True
                logger.info("Live2D library initialized globally")
                return True
            except Exception as e:
                logger.error(f"Failed to initialize Live2D library: {e}")
                return False
        return True

    @classmethod
    def global_dispose(cls):
        """Dispose Live2D library globally (call once at application shutdown)."""
        if LIVE2D_AVAILABLE and cls._global_initialized:
            try:
                live2d.dispose()
                cls._global_initialized = False
                logger.info("Live2D library disposed")
            except Exception as e:
                logger.error(f"Failed to dispose Live2D library: {e}")

    def init_gl(self):
        """Initialize OpenGL context for Live2D. Must be called from OpenGL context."""
        if not LIVE2D_AVAILABLE:
            return False
        
        if not self._gl_initialized:
            try:
                live2d.glInit()
                self._gl_initialized = True
                logger.info("Live2D OpenGL initialized")
                return True
            except Exception as e:
                logger.error(f"Failed to initialize Live2D OpenGL: {e}")
                return False
        return True

    async def initialize(self) -> bool:
        """Initialize the renderer and load the model."""
        if not LIVE2D_AVAILABLE:
            logger.warning("live2d-py not available, using placeholder renderer")
            self._initialized = True
            return True

        try:
            model_path = Path(self.config.model_path)
            if not model_path.exists():
                logger.error(f"Model not found: {model_path}")
                return False

            # Global init if not done
            if not Live2DRenderer._global_initialized:
                Live2DRenderer.global_init()

            self._initialized = True
            logger.info(f"Live2D renderer ready for model: {model_path}")
            return True

        except Exception as e:
            logger.error(f"Failed to initialize Live2D: {e}")
            return False

    def load_model(self) -> bool:
        """Load the Live2D model. Must be called from OpenGL context after init_gl()."""
        if not LIVE2D_AVAILABLE or not self._gl_initialized:
            return False

        try:
            model_path = Path(self.config.model_path)
            if not model_path.exists():
                logger.error(f"Model file not found: {model_path}")
                return False

            self._model = live2d.LAppModel()
            self._model.LoadModelJson(str(model_path))
            self._model.Resize(self._width, self._height)
            
            # Enable auto features
            self._model.SetAutoBlinkEnable(True)
            self._model.SetAutoBreathEnable(True)
            
            # Start idle motion
            self._start_idle_motion()
            
            logger.info(f"Live2D model loaded: {model_path}")
            return True

        except Exception as e:
            logger.error(f"Failed to load Live2D model: {e}")
            self._model = None
            return False

    def _start_idle_motion(self):
        """Start the idle motion loop."""
        if self._model:
            try:
                idle_group = self.MOTIONS.get(self.config.idle_motion.lower(), "Idle")
                self._model.StartRandomMotion(
                    group=idle_group,
                    priority=1,
                    onFinishMotionHandler=self._on_idle_motion_finished
                )
            except Exception as e:
                logger.debug(f"Could not start idle motion: {e}")

    def _on_idle_motion_finished(self):
        """Callback when idle motion finishes - restart it."""
        self._start_idle_motion()

    def update(self, delta_time: float):
        """Update internal state (called from timer, not OpenGL context)."""
        pass

    def render(self, width: int, height: int):
        """Render the model. Must be called from OpenGL context."""
        if not self._initialized:
            return

        if width != self._width or height != self._height:
            self._width = width
            self._height = height
            if self._model:
                self._model.Resize(width, height)

        if not LIVE2D_AVAILABLE or not self._model:
            return

        try:
            self._model.SetScale(self.config.scale)
            self._model.SetOffset(self._offset_x, self._offset_y)
            
            self._model.Update()
            self._model.Draw()
            
        except Exception as e:
            logger.error(f"Render error: {e}")

    async def set_expression(self, expression: str):
        """Set the model expression."""
        if expression in self.EXPRESSIONS:
            self._current_expression = expression
            if self._model and LIVE2D_AVAILABLE:
                try:
                    exp_name = self.EXPRESSIONS.get(expression, "Normal")
                    self._model.SetExpression(exp_name)
                    logger.debug(f"Expression set to: {expression} ({exp_name})")
                except Exception as e:
                    logger.debug(f"Could not set expression: {e}")

    async def play_motion(self, motion: str):
        """Play a motion animation."""
        if self._model and LIVE2D_AVAILABLE:
            try:
                motion_group = self.MOTIONS.get(motion.lower(), motion)
                self._model.StartRandomMotion(
                    group=motion_group,
                    priority=2,
                    onFinishMotionHandler=self._start_idle_motion
                )
                logger.debug(f"Playing motion: {motion} ({motion_group})")
            except Exception as e:
                logger.debug(f"Could not play motion: {e}")

    async def look_at(self, x: float, y: float):
        """Make the model look at a point (normalized 0-1 coordinates)."""
        self._look_x = max(-1.0, min(1.0, x * 2 - 1))
        self._look_y = max(-1.0, min(1.0, y * 2 - 1))
        
        if self._model and LIVE2D_AVAILABLE:
            try:
                # Convert to screen coordinates
                screen_x = x * self._width
                screen_y = y * self._height
                self._model.Drag(screen_x, screen_y)
            except Exception as e:
                logger.debug(f"Could not set look direction: {e}")

    def set_mouth_open(self, value: float):
        """Set mouth openness for lip sync (0.0 to 1.0)."""
        self._mouth_open = max(0.0, min(1.0, value))
        
        if self._model and LIVE2D_AVAILABLE and StandardParams:
            try:
                self._model.SetParameterValue(
                    StandardParams.ParamMouthOpenY,
                    self._mouth_open
                )
            except Exception as e:
                logger.debug(f"Could not set mouth parameter: {e}")

    def set_offset(self, x: float, y: float):
        """Set model position offset."""
        self._offset_x = x
        self._offset_y = y

    def resize(self, width: int, height: int):
        """Handle resize event."""
        self._width = width
        self._height = height
        if self._model:
            try:
                self._model.Resize(width, height)
            except Exception as e:
                logger.debug(f"Could not resize model: {e}")

    def get_render_position(self, window_width: int, window_height: int) -> tuple[int, int]:
        """Calculate render position based on config."""
        x = int(window_width * self.config.position_x)
        y = int(window_height * (1.0 - self.config.position_y) / 2)
        return x, y

    def get_render_size(self, window_height: int) -> int:
        """Calculate render size based on config."""
        return int(window_height * self.config.scale)

    @property
    def is_initialized(self) -> bool:
        return self._initialized

    @property
    def is_model_loaded(self) -> bool:
        return self._model is not None

    @property
    def current_expression(self) -> str:
        return self._current_expression

    @property
    def has_live2d(self) -> bool:
        """Check if live2d-py is available."""
        return LIVE2D_AVAILABLE
