from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel


class TrackingIndicator(QLabel):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(24, 24)
        self.setStyleSheet(
            "background: #CD007B; border: 3px solid white; border-radius: 12px;"
        )

    def update_position(self, x: int, y: int, visible: bool) -> None:
        if visible:
            self.move(x - 12, y - 12)
            if not self.isVisible():
                self.show()
        else:
            self.hide()
