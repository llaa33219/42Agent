"""
Main application window with VM display and Live2D avatar overlay.
Single OpenGL context renders both VM frame (as texture) and Live2D model.
"""

import logging
from typing import Optional

from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QImage, QKeyEvent
from PyQt6.QtWidgets import QApplication, QMainWindow, QWidget, QVBoxLayout
from PyQt6.QtOpenGLWidgets import QOpenGLWidget

from ..avatar.live2d_renderer import Live2DRenderer
from ..avatar.lip_sync import LipSyncController

logger = logging.getLogger(__name__)


class CombinedGLWidget(QOpenGLWidget):
    """Single OpenGL widget that renders VM frame as texture + Live2D overlay."""
    
    def __init__(self, avatar_renderer: Optional[Live2DRenderer] = None, parent=None):
        super().__init__(parent)
        self.avatar_renderer = avatar_renderer
        self._gl_initialized = False
        self._model_loaded = False
        
        self._vm_texture_id = None
        self._vm_frame_data: Optional[bytes] = None
        self._vm_frame_width = 0
        self._vm_frame_height = 0
        self._vm_frame_updated = False
        
        self._avatar_size = (400, 500)
        self._avatar_margin = 20

    def initializeGL(self):
        try:
            from OpenGL import GL
            
            GL.glClearColor(0.1, 0.1, 0.12, 1.0)
            GL.glEnable(GL.GL_BLEND)
            GL.glBlendFunc(GL.GL_SRC_ALPHA, GL.GL_ONE_MINUS_SRC_ALPHA)
            GL.glEnable(GL.GL_TEXTURE_2D)
            
            self._vm_texture_id = GL.glGenTextures(1)
            GL.glBindTexture(GL.GL_TEXTURE_2D, self._vm_texture_id)
            GL.glTexParameteri(GL.GL_TEXTURE_2D, GL.GL_TEXTURE_MIN_FILTER, GL.GL_LINEAR)
            GL.glTexParameteri(GL.GL_TEXTURE_2D, GL.GL_TEXTURE_MAG_FILTER, GL.GL_LINEAR)
            GL.glBindTexture(GL.GL_TEXTURE_2D, 0)
            
            self._gl_initialized = True
            
            if self.avatar_renderer and self.avatar_renderer.has_live2d:
                self.avatar_renderer.init_gl()
                if self.avatar_renderer.load_model():
                    self._model_loaded = True
                    logger.info("Live2D model loaded successfully")
                else:
                    logger.warning("Failed to load Live2D model")
            
        except Exception as e:
            logger.error(f"OpenGL init failed: {e}")

    def update_vm_frame(self, frame_data: bytes):
        if not frame_data:
            return
        self._vm_frame_data = frame_data
        self._vm_frame_updated = True

    def _upload_vm_texture(self):
        if not self._vm_frame_data or not self._vm_frame_updated:
            return
        
        from OpenGL import GL
        
        image = QImage.fromData(self._vm_frame_data)
        if image.isNull():
            return
        
        image = image.convertToFormat(QImage.Format.Format_RGBA8888)
        self._vm_frame_width = image.width()
        self._vm_frame_height = image.height()
        
        ptr = image.bits()
        ptr.setsize(image.sizeInBytes())
        
        GL.glBindTexture(GL.GL_TEXTURE_2D, self._vm_texture_id)
        GL.glTexImage2D(
            GL.GL_TEXTURE_2D, 0, GL.GL_RGBA,
            self._vm_frame_width, self._vm_frame_height,
            0, GL.GL_RGBA, GL.GL_UNSIGNED_BYTE, bytes(ptr)
        )
        GL.glBindTexture(GL.GL_TEXTURE_2D, 0)
        
        self._vm_frame_updated = False

    def _render_vm_frame(self):
        from OpenGL import GL
        
        if not self._vm_texture_id or self._vm_frame_width == 0:
            self._draw_connecting_message()
            return
        
        GL.glMatrixMode(GL.GL_PROJECTION)
        GL.glLoadIdentity()
        GL.glOrtho(0, self.width(), self.height(), 0, -1, 1)
        GL.glMatrixMode(GL.GL_MODELVIEW)
        GL.glLoadIdentity()
        
        widget_w, widget_h = self.width(), self.height()
        frame_w, frame_h = self._vm_frame_width, self._vm_frame_height
        
        scale = min(widget_w / frame_w, widget_h / frame_h)
        scaled_w = int(frame_w * scale)
        scaled_h = int(frame_h * scale)
        
        x = (widget_w - scaled_w) // 2
        y = (widget_h - scaled_h) // 2
        
        GL.glEnable(GL.GL_TEXTURE_2D)
        GL.glBindTexture(GL.GL_TEXTURE_2D, self._vm_texture_id)
        GL.glColor4f(1.0, 1.0, 1.0, 1.0)
        
        GL.glBegin(GL.GL_QUADS)
        GL.glTexCoord2f(0, 0); GL.glVertex2f(x, y)
        GL.glTexCoord2f(1, 0); GL.glVertex2f(x + scaled_w, y)
        GL.glTexCoord2f(1, 1); GL.glVertex2f(x + scaled_w, y + scaled_h)
        GL.glTexCoord2f(0, 1); GL.glVertex2f(x, y + scaled_h)
        GL.glEnd()
        
        GL.glBindTexture(GL.GL_TEXTURE_2D, 0)
        GL.glDisable(GL.GL_TEXTURE_2D)

    def _draw_connecting_message(self):
        pass

    def _render_avatar(self):
        if not self._model_loaded or not self.avatar_renderer:
            return
        
        from OpenGL import GL
        
        avatar_w, avatar_h = self._avatar_size
        avatar_x = self.width() - avatar_w - self._avatar_margin
        avatar_y = self._avatar_margin
        
        GL.glPushAttrib(GL.GL_ALL_ATTRIB_BITS)
        GL.glPushMatrix()
        
        GL.glViewport(avatar_x, avatar_y, avatar_w, avatar_h)
        GL.glEnable(GL.GL_SCISSOR_TEST)
        GL.glScissor(avatar_x, avatar_y, avatar_w, avatar_h)
        
        self.avatar_renderer.render(avatar_w, avatar_h)
        
        GL.glDisable(GL.GL_SCISSOR_TEST)
        GL.glPopMatrix()
        GL.glPopAttrib()
        GL.glViewport(0, 0, self.width(), self.height())

    def paintGL(self):
        if not self._gl_initialized:
            return
        
        from OpenGL import GL
        
        try:
            GL.glClear(GL.GL_COLOR_BUFFER_BIT)
            
            self._upload_vm_texture()
            self._render_vm_frame()
            self._render_avatar()
            
        except Exception as e:
            logger.error(f"Render error: {e}")

    def resizeGL(self, w: int, h: int):
        if self._gl_initialized:
            from OpenGL import GL
            GL.glViewport(0, 0, w, h)


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
        self.setMinimumSize(800, 600)
        self.resize(1280, 720)

        central = QWidget()
        self.setCentralWidget(central)

        layout = QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)

        self.gl_widget = CombinedGLWidget(self.avatar_renderer, self)
        layout.addWidget(self.gl_widget)

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
        if self.lip_sync:
            self.lip_sync.update(0.016)
        self.gl_widget.update()

    def _on_frame_received(self, frame_data: bytes):
        self.gl_widget.update_vm_frame(frame_data)

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
