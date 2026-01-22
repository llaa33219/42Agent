"""
Main application window with VM display and Live2D avatar overlay.
Uses PyQt6 for windowing and OpenGL for rendering.
"""

import asyncio
import logging
from typing import Optional

from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QImage, QPixmap, QKeyEvent
from PyQt6.QtWidgets import (
    QApplication,
    QMainWindow,
    QLabel,
    QWidget,
    QVBoxLayout,
    QStackedLayout,
)
from PyQt6.QtOpenGLWidgets import QOpenGLWidget

from ..avatar.live2d_renderer import Live2DRenderer
from ..avatar.lip_sync import LipSyncController

logger = logging.getLogger(__name__)


class VMDisplayWidget(QLabel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setStyleSheet("background-color: #1a1a2e; color: #9ca3af;")
        self.setMinimumSize(1920, 1080)
        self._has_frame = False
        self._show_connecting_message()

    def _show_connecting_message(self):
        """Show a message while waiting for VM connection."""
        self.setText("Connecting to VM...\n\nWaiting for VNC display")
        self.setStyleSheet("""
            background-color: #1a1a2e;
            color: #9ca3af;
            font-size: 24px;
            font-family: monospace;
        """)

    def update_frame(self, frame_data: bytes):
        if not frame_data:
            return
        image = QImage.fromData(frame_data)
        if not image.isNull():
            if not self._has_frame:
                self._has_frame = True
                self.setStyleSheet("background-color: black;")
            pixmap = QPixmap.fromImage(image)
            scaled = pixmap.scaled(
                self.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            )
            self.setPixmap(scaled)


class AvatarOverlayWidget(QOpenGLWidget):
    def __init__(self, renderer: Live2DRenderer, parent=None):
        super().__init__(parent)
        self.renderer = renderer
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setStyleSheet("background: transparent;")
        self._gl_initialized = False

    def initializeGL(self):
        try:
            from OpenGL import GL
            GL.glClearColor(0.0, 0.0, 0.0, 0.0)
            GL.glEnable(GL.GL_BLEND)
            GL.glBlendFunc(GL.GL_SRC_ALPHA, GL.GL_ONE_MINUS_SRC_ALPHA)
            self._gl_initialized = True
        except Exception as e:
            logger.error(f"OpenGL init failed: {e}")

    def paintGL(self):
        if not self._gl_initialized:
            return
        try:
            from OpenGL import GL
            import math
            
            GL.glClear(GL.GL_COLOR_BUFFER_BIT)
            
            # Setup orthographic projection
            GL.glMatrixMode(GL.GL_PROJECTION)
            GL.glLoadIdentity()
            GL.glOrtho(0, self.width(), self.height(), 0, -1, 1)
            GL.glMatrixMode(GL.GL_MODELVIEW)
            GL.glLoadIdentity()
            
            # Call renderer if available
            if self.renderer and self.renderer.is_initialized:
                self.renderer.render(self.width(), self.height())
            
            # Draw placeholder avatar (simple circle with face)
            self._draw_placeholder_avatar()
            
        except Exception as e:
            logger.error(f"OpenGL render error: {e}")

    def _draw_placeholder_avatar(self):
        """Draw a simple placeholder avatar when Live2D model isn't loaded."""
        from OpenGL import GL
        import math
        
        # Position in bottom-right corner
        center_x = self.width() * 0.85
        center_y = self.height() * 0.75
        radius = min(self.width(), self.height()) * 0.12
        
        # Draw filled circle (face)
        GL.glColor4f(0.9, 0.8, 0.7, 0.9)  # Skin tone
        GL.glBegin(GL.GL_TRIANGLE_FAN)
        GL.glVertex2f(center_x, center_y)
        for i in range(33):
            angle = 2.0 * math.pi * i / 32
            x = center_x + radius * math.cos(angle)
            y = center_y + radius * math.sin(angle)
            GL.glVertex2f(x, y)
        GL.glEnd()
        
        # Draw circle outline
        GL.glColor4f(0.6, 0.5, 0.4, 1.0)
        GL.glLineWidth(3.0)
        GL.glBegin(GL.GL_LINE_LOOP)
        for i in range(32):
            angle = 2.0 * math.pi * i / 32
            x = center_x + radius * math.cos(angle)
            y = center_y + radius * math.sin(angle)
            GL.glVertex2f(x, y)
        GL.glEnd()
        
        # Draw eyes
        eye_y = center_y - radius * 0.15
        eye_offset = radius * 0.3
        eye_radius = radius * 0.12
        
        GL.glColor4f(0.2, 0.2, 0.3, 1.0)
        for eye_x in [center_x - eye_offset, center_x + eye_offset]:
            GL.glBegin(GL.GL_TRIANGLE_FAN)
            GL.glVertex2f(eye_x, eye_y)
            for i in range(17):
                angle = 2.0 * math.pi * i / 16
                x = eye_x + eye_radius * math.cos(angle)
                y = eye_y + eye_radius * 0.8 * math.sin(angle)
                GL.glVertex2f(x, y)
            GL.glEnd()
        
        # Draw mouth (gets mouth_open from renderer)
        mouth_y = center_y + radius * 0.35
        mouth_width = radius * 0.4
        mouth_open = 0.0
        if self.renderer:
            mouth_open = getattr(self.renderer, '_mouth_open', 0.0)
        mouth_height = radius * 0.1 + radius * 0.15 * mouth_open
        
        GL.glColor4f(0.7, 0.3, 0.3, 1.0)
        GL.glBegin(GL.GL_TRIANGLE_FAN)
        GL.glVertex2f(center_x, mouth_y)
        for i in range(17):
            angle = math.pi * i / 16  # Half circle
            x = center_x + mouth_width * math.cos(angle)
            y = mouth_y + mouth_height * math.sin(angle)
            GL.glVertex2f(x, y)
        GL.glEnd()

    def resizeGL(self, w: int, h: int):
        if self._gl_initialized:
            try:
                from OpenGL import GL
                GL.glViewport(0, 0, w, h)
            except Exception:
                pass


class MainWindow(QMainWindow):
    frame_received = pyqtSignal(bytes)
    chat_toggled = pyqtSignal(bool)

    def __init__(
        self,
        avatar_renderer: Optional[Live2DRenderer] = None,
        lip_sync: Optional[LipSyncController] = None
    ):
        super().__init__()
        self.avatar_renderer = avatar_renderer
        self.lip_sync = lip_sync
        self._chat_visible = False
        self._chat_overlay = None

        self._setup_ui()
        self._setup_timers()
        self._connect_signals()

    def _setup_ui(self):
        self.setWindowTitle("42Agent")
        self.setMinimumSize(1920, 1080)

        central = QWidget()
        self.setCentralWidget(central)

        layout = QStackedLayout(central)
        layout.setStackingMode(QStackedLayout.StackingMode.StackAll)

        self.vm_display = VMDisplayWidget()
        layout.addWidget(self.vm_display)

        if self.avatar_renderer:
            self.avatar_widget = AvatarOverlayWidget(self.avatar_renderer)
            layout.addWidget(self.avatar_widget)

        from .chat_overlay import ChatOverlay
        self._chat_overlay = ChatOverlay(self)
        self._chat_overlay.hide()

    def _setup_timers(self):
        self.update_timer = QTimer(self)
        self.update_timer.timeout.connect(self._on_update)
        self.update_timer.start(16)

    def _connect_signals(self):
        self.frame_received.connect(self._on_frame_received)

    def _on_update(self):
        dt = 0.016

        if self.avatar_renderer:
            self.avatar_renderer.update(dt)

        if self.lip_sync:
            self.lip_sync.update(dt)

        if hasattr(self, 'avatar_widget'):
            self.avatar_widget.update()

    def _on_frame_received(self, frame_data: bytes):
        self.vm_display.update_frame(frame_data)

    def update_vm_frame(self, frame_data: bytes):
        self.frame_received.emit(frame_data)

    def process_audio(self, audio_data: bytes):
        if self.lip_sync:
            self.lip_sync.process_audio(audio_data)

    def keyPressEvent(self, event: QKeyEvent):
        if event.key() == Qt.Key.Key_T and not self._chat_visible:
            self._toggle_chat(True)
        elif event.key() == Qt.Key.Key_Escape and self._chat_visible:
            self._toggle_chat(False)
        else:
            super().keyPressEvent(event)

    def _toggle_chat(self, visible: bool):
        self._chat_visible = visible
        if self._chat_overlay:
            if visible:
                self._chat_overlay.show()
                self._chat_overlay.focus_input()
            else:
                self._chat_overlay.hide()
        self.chat_toggled.emit(visible)

    def set_message_callback(self, callback):
        if self._chat_overlay:
            self._chat_overlay.set_send_callback(callback)

    def add_chat_message(self, role: str, content: str):
        if self._chat_overlay:
            self._chat_overlay.add_message(role, content)

    @property
    def is_chat_visible(self) -> bool:
        return self._chat_visible
