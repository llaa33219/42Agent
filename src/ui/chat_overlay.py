"""
Chat overlay widget for user-agent text communication.
Appears when user presses 'T' key.
"""

import logging
from typing import Callable, Optional

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QTextEdit,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QLabel,
    QFrame,
)

logger = logging.getLogger(__name__)


class MessageBubble(QFrame):
    def __init__(self, role: str, content: str, parent=None):
        super().__init__(parent)
        self.setFrameShape(QFrame.Shape.StyledPanel)

        is_user = role.lower() == "user"

        if is_user:
            self.setStyleSheet("""
                QFrame {
                    background-color: #007AFF;
                    border-radius: 12px;
                    padding: 8px;
                    margin: 4px;
                }
            """)
        else:
            self.setStyleSheet("""
                QFrame {
                    background-color: #3A3A3C;
                    border-radius: 12px;
                    padding: 8px;
                    margin: 4px;
                }
            """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)

        role_label = QLabel(role.capitalize())
        role_label.setStyleSheet("color: #8E8E93; font-size: 11px; font-weight: bold;")
        layout.addWidget(role_label)

        content_label = QLabel(content)
        content_label.setWordWrap(True)
        content_label.setStyleSheet("color: white; font-size: 14px;")
        layout.addWidget(content_label)


class ChatOverlay(QWidget):
    message_sent = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._send_callback: Optional[Callable[[str], None]] = None
        self._setup_ui()

    def _setup_ui(self):
        self.setStyleSheet("""
            QWidget {
                background-color: rgba(28, 28, 30, 0.95);
            }
        """)

        self.setFixedWidth(400)
        self.setMinimumHeight(300)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        header = QWidget()
        header.setStyleSheet("background-color: rgba(44, 44, 46, 1);")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(16, 12, 16, 12)

        title = QLabel("Chat with Agent42")
        title.setStyleSheet("color: white; font-size: 16px; font-weight: bold;")
        header_layout.addWidget(title)

        close_btn = QPushButton("×")
        close_btn.setFixedSize(24, 24)
        close_btn.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                color: #8E8E93;
                font-size: 20px;
                border: none;
            }
            QPushButton:hover {
                color: white;
            }
        """)
        close_btn.clicked.connect(self.hide)
        header_layout.addWidget(close_btn)

        layout.addWidget(header)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet("""
            QScrollArea {
                border: none;
                background-color: transparent;
            }
            QScrollBar:vertical {
                width: 8px;
                background: transparent;
            }
            QScrollBar::handle:vertical {
                background: #3A3A3C;
                border-radius: 4px;
            }
        """)

        self.messages_container = QWidget()
        self.messages_layout = QVBoxLayout(self.messages_container)
        self.messages_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.messages_layout.setSpacing(8)
        self.messages_layout.setContentsMargins(12, 12, 12, 12)

        scroll.setWidget(self.messages_container)
        layout.addWidget(scroll, 1)

        self.scroll_area = scroll

        input_container = QWidget()
        input_container.setStyleSheet("background-color: rgba(44, 44, 46, 1);")
        input_layout = QHBoxLayout(input_container)
        input_layout.setContentsMargins(12, 12, 12, 12)
        input_layout.setSpacing(8)

        self.input_field = QLineEdit()
        self.input_field.setPlaceholderText("Type a message...")
        self.input_field.setStyleSheet("""
            QLineEdit {
                background-color: #3A3A3C;
                border: none;
                border-radius: 18px;
                padding: 10px 16px;
                color: white;
                font-size: 14px;
            }
            QLineEdit:focus {
                background-color: #48484A;
            }
        """)
        self.input_field.returnPressed.connect(self._on_send)
        input_layout.addWidget(self.input_field, 1)

        send_btn = QPushButton("Send")
        send_btn.setStyleSheet("""
            QPushButton {
                background-color: #007AFF;
                color: white;
                border: none;
                border-radius: 18px;
                padding: 10px 20px;
                font-size: 14px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #0056CC;
            }
            QPushButton:pressed {
                background-color: #004099;
            }
        """)
        send_btn.clicked.connect(self._on_send)
        input_layout.addWidget(send_btn)

        layout.addWidget(input_container)

    def _on_send(self):
        text = self.input_field.text().strip()
        if not text:
            return

        self.add_message("user", text)
        self.input_field.clear()

        self.message_sent.emit(text)

        if self._send_callback:
            self._send_callback(text)

    def set_send_callback(self, callback: Callable[[str], None]):
        self._send_callback = callback

    def add_message(self, role: str, content: str):
        bubble = MessageBubble(role, content)
        self.messages_layout.addWidget(bubble)

        self.scroll_area.verticalScrollBar().setValue(
            self.scroll_area.verticalScrollBar().maximum()
        )

    def focus_input(self):
        self.input_field.setFocus()

    def clear_messages(self):
        while self.messages_layout.count():
            item = self.messages_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def showEvent(self, event):
        super().showEvent(event)
        if self.parent():
            parent = self.parent()
            x = parent.width() - self.width() - 20
            y = 20
            self.move(x, y)
            self.setFixedHeight(parent.height() - 40)
