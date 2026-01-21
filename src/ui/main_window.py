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
        self.setStyleSheet("background-color: black;")
        self.setMinimumSize(1920, 1080)

    def update_frame(self, frame_data: bytes):
        image = QImage.fromData(frame_data)
        if not image.isNull():
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

    def initializeGL(self):
        pass

    def paintGL(self):
        if self.renderer and self.renderer.is_initialized:
            self.renderer.render(self.width(), self.height())

    def resizeGL(self, w: int, h: int):
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
