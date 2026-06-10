from __future__ import annotations

import cv2
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QFont, QFontMetrics, QImage, QPainter, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QCheckBox,
    QFrame,
    QGraphicsDropShadowEffect,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QStyle,
    QSizePolicy,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from aura.effects import EFFECTS
from utils.paths import resource_path


MAX_CONTENT_WIDTH = 1120


class ClickButton(QPushButton):
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.setCursor(Qt.CursorShape.PointingHandCursor)


class ClickFrame(QFrame):
    clicked = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def mousePressEvent(self, event) -> None:
        self.setProperty("pressed", True)
        self.style().unpolish(self)
        self.style().polish(self)
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        self.setProperty("pressed", False)
        self.style().unpolish(self)
        self.style().polish(self)
        if self.rect().contains(event.position().toPoint()):
            self.clicked.emit()
        super().mouseReleaseEvent(event)


class BrandTitle(QWidget):
    def __init__(self, size: int = 60, large_size: int | None = None) -> None:
        super().__init__()
        self.base_size = size
        self.large_size = large_size or int(size * 1.16)
        self.current_size = size
        self.setObjectName("brandTitle")
        self._apply_font(size)

    def resizeEvent(self, event) -> None:
        width = self.window().width() if self.window() else self.width()
        self._apply_font(self.large_size if width >= 1100 else self.base_size)
        super().resizeEvent(event)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        font = QFont("Segoe UI", self.current_size)
        font.setWeight(QFont.Weight.Black)
        painter.setFont(font)
        metrics = QFontMetrics(font)
        palm = "Palm"
        shift = "Shift"
        gap = max(8, self.current_size // 7)
        total = metrics.horizontalAdvance(palm) + gap + metrics.horizontalAdvance(shift)
        x = max(0, (self.width() - total) // 2)
        baseline = (self.height() + metrics.ascent() - metrics.descent()) // 2
        painter.setPen(QColor("#1b0011"))
        painter.drawText(x, baseline, palm)
        x += metrics.horizontalAdvance(palm) + gap
        painter.setPen(QColor("#b40070"))
        painter.drawText(x, baseline, shift)

    def _apply_font(self, size: int) -> None:
        self.current_size = size
        font = QFont("Segoe UI", size)
        font.setWeight(QFont.Weight.Black)
        metrics = QFontMetrics(font)
        total_width = metrics.horizontalAdvance("Palm") + metrics.horizontalAdvance("Shift") + max(8, size // 7)
        self.setFixedWidth(total_width)
        self.setFixedHeight(int(size * 1.28))
        self.update()


class IntroScreen(QWidget):
    start_clicked = Signal(bool)

    def __init__(self, icon_path: str) -> None:
        super().__init__()
        self.skip_checkbox = QCheckBox("Don't show start page from next time")
        self.skip_checkbox.setObjectName("introCheck")
        self.skip_checkbox.setChecked(False)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(0)
        layout.addStretch(1)

        icon_host = QFrame()
        icon_host.setObjectName("introIconHost")
        icon_host.setFixedSize(210, 174)
        icon_host_layout = QVBoxLayout(icon_host)
        icon_host_layout.setContentsMargins(38, 18, 38, 24)
        icon_host_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        icon_frame = QFrame()
        icon_frame.setObjectName("introIconFrame")
        icon_frame.setFixedSize(132, 132)
        add_shadow(icon_frame, blur=30, y=12, alpha=78)
        icon_layout = QVBoxLayout(icon_frame)
        icon_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        logo = QLabel()
        logo.setPixmap(QPixmap(icon_path).scaled(92, 92, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_layout.addWidget(logo)
        icon_host_layout.addWidget(icon_frame)

        welcome = QLabel("Welcome to")
        welcome.setObjectName("welcomeText")
        welcome.setAlignment(Qt.AlignmentFlag.AlignCenter)

        title = BrandTitle(72, 90)

        tagline = QLabel("Control reality, touch the invisible")
        tagline.setObjectName("tagline")
        tagline.setAlignment(Qt.AlignmentFlag.AlignCenter)

        start = ClickButton("Start")
        start.setObjectName("startButton")
        start.setFixedSize(250, 54)
        start.clicked.connect(lambda checked=False: self.start_clicked.emit(self.skip_checkbox.isChecked()))

        layout.addWidget(icon_host, alignment=Qt.AlignmentFlag.AlignCenter)
        layout.addSpacing(10)
        layout.addWidget(welcome)
        layout.addWidget(title, alignment=Qt.AlignmentFlag.AlignCenter)
        layout.addSpacing(34)
        layout.addWidget(tagline)
        layout.addSpacing(10)
        layout.addWidget(start, alignment=Qt.AlignmentFlag.AlignCenter)
        layout.addSpacing(10)
        layout.addWidget(self.skip_checkbox, alignment=Qt.AlignmentFlag.AlignCenter)
        layout.addStretch(1)


class SelectionScreen(QWidget):
    control_clicked = Signal()
    aura_clicked = Signal()
    commands_clicked = Signal()

    def __init__(self) -> None:
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 22, 28, 20)
        layout.setSpacing(0)
        layout.addWidget(BrandTitle(58), alignment=Qt.AlignmentFlag.AlignCenter)
        layout.addStretch(1)

        content = QFrame()
        content.setObjectName("contentWrap")
        content.setMinimumWidth(680)
        content.setMaximumWidth(MAX_CONTENT_WIDTH)
        cards = QVBoxLayout(content)
        cards.setContentsMargins(34, 24, 34, 24)
        cards.setSpacing(22)

        control = ModeCard(
            "control-icon.png",
            "Control Mode",
            "Make your system visually interactive, no need to physical mouse / trackpad movements anymore",
            "CTRL + alt + C",
        )
        aura = ModeCard(
            "aura-icon.png",
            "Aura Mode",
            "Experience smooth invisible surface textures such as glass, water, energy in free air",
            "CTRL + alt + A",
        )
        control.clicked.connect(lambda checked=False: self.control_clicked.emit())
        aura.clicked.connect(lambda checked=False: self.aura_clicked.emit())
        cards.addWidget(control)
        cards.addWidget(aura)
        layout.addWidget(content, alignment=Qt.AlignmentFlag.AlignCenter)
        layout.addSpacing(18)

        commands = ClickButton("Commands")
        commands.setObjectName("commandsLink")
        commands.clicked.connect(lambda checked=False: self.commands_clicked.emit())
        layout.addWidget(commands, alignment=Qt.AlignmentFlag.AlignCenter)
        layout.addStretch(1)


class ModeCard(ClickFrame):
    def __init__(self, icon_name: str, title: str, body: str, shortcut: str) -> None:
        super().__init__()
        self.setObjectName("modeCard")
        self.setMinimumHeight(118)
        self.setMaximumHeight(132)
        self.setMinimumWidth(600)
        self.setMaximumWidth(MAX_CONTENT_WIDTH)
        add_shadow(self, blur=28, y=12, alpha=68)
        row = QHBoxLayout(self)
        row.setContentsMargins(9, 9, 22, 9)
        row.setSpacing(18)

        icon_box = QLabel()
        icon_box.setObjectName("modeIconBox")
        icon_box.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_box.setFixedSize(96, 96)
        icon_box.setPixmap(icon_pixmap(icon_name, 58))
        icon_box.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        row.addWidget(icon_box)

        text_col = QVBoxLayout()
        text_col.setSpacing(5)
        title_label = QLabel(title)
        title_label.setObjectName("modeTitle")
        body_label = QLabel(body)
        body_label.setObjectName("modeBody")
        body_label.setWordWrap(True)
        text_col.addStretch()
        text_col.addWidget(title_label)
        text_col.addWidget(body_label)
        text_col.addStretch()
        row.addLayout(text_col, 1)

        key = QLabel(shortcut)
        key.setObjectName("modeShortcut")
        key.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignBottom)
        key.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        row.addWidget(key, 0, Qt.AlignmentFlag.AlignBottom)


class ControlActiveScreen(QWidget):
    stop_clicked = Signal()

    def __init__(self, mode_name: str) -> None:
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 22, 28, 22)
        layout.setSpacing(0)
        layout.addWidget(BrandTitle(56), alignment=Qt.AlignmentFlag.AlignCenter)
        layout.addStretch(1)

        mode = QLabel(mode_name)
        mode.setObjectName("activeMode")
        mode.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.timer_label = QLabel("00:00:00")
        self.timer_label.setObjectName("controlTimer")
        self.timer_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        stop = ClickButton("Stop Control Mode")
        stop.setObjectName("stopControlButton")
        stop.setFixedSize(270, 54)
        stop.clicked.connect(lambda checked=False: self.stop_clicked.emit())

        layout.addWidget(mode)
        layout.addSpacing(12)
        layout.addWidget(self.timer_label)
        layout.addSpacing(24)
        layout.addWidget(stop, alignment=Qt.AlignmentFlag.AlignCenter)
        layout.addStretch(2)

    def set_elapsed(self, seconds: int) -> None:
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        secs = seconds % 60
        self.timer_label.setText(f"{hours:02d}:{minutes:02d}:{secs:02d}")

class AuraScreen(QWidget):
    back_clicked = Signal()
    effect_changed = Signal(str)
    draw_color_changed = Signal(tuple)
    draw_action_clicked = Signal(str)
    record_clicked = Signal()
    pause_clicked = Signal()
    stop_clicked = Signal()

    def __init__(self, selected_effect: str) -> None:
        super().__init__()
        self.selected_effect = selected_effect if selected_effect in EFFECTS else "Water"
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 22, 28, 20)
        layout.setSpacing(0)
        layout.addLayout(page_header(self.back_clicked))
        layout.addSpacing(12)

        self.camera_box = QFrame()
        self.camera_box.setObjectName("cameraBox")
        self.camera_box.setMaximumWidth(1680)
        self.camera_box.setMinimumHeight(350)
        self.camera_box.setMaximumHeight(980)
        self.camera_box.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        camera_layout = QGridLayout(self.camera_box)
        camera_layout.setContentsMargins(0, 0, 0, 0)
        self.preview = QLabel("Starting camera...")
        self.preview.setObjectName("cameraPreview")
        self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        camera_layout.addWidget(self.preview, 0, 0)

        overlay_controls = QFrame()
        overlay_controls.setObjectName("auraOverlayControls")
        overlay_controls.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        overlay_layout = QVBoxLayout(overlay_controls)
        overlay_layout.setContentsMargins(0, 0, 0, 0)
        overlay_layout.setSpacing(10)

        self.draw_tools = QFrame()
        self.draw_tools.setObjectName("drawTools")
        draw_row = QHBoxLayout(self.draw_tools)
        draw_row.setContentsMargins(0, 0, 0, 0)
        draw_row.setSpacing(10)
        self.color_buttons = []
        colors = [
            ("White", "#ffffff", (255, 255, 255)),
            ("Black", "#050505", (5, 5, 5)),
            ("Red", "#ff2b35", (53, 43, 255)),
            ("Green", "#22c55e", (94, 197, 34)),
            ("Blue", "#2563eb", (235, 99, 37)),
            ("Yellow", "#facc15", (21, 204, 250)),
            ("Purple", "#a855f7", (247, 85, 168)),
            ("Pink", "#ec4899", (153, 72, 236)),
            ("Orange", "#f97316", (22, 115, 249)),
        ]
        for index, (name, css_color, bgr) in enumerate(colors):
            button = ClickButton()
            button.setObjectName("colorSwatch")
            button.setToolTip(name)
            button.setCheckable(True)
            button.setFixedSize(30, 30)
            button.setStyleSheet(
                f"""
                QPushButton {{
                    background: {css_color};
                    border: 1px solid rgba(0, 0, 0, 0.28);
                    border-radius: 15px;
                }}
                QPushButton:checked {{
                    border: 3px solid #315CFF;
                }}
                """
            )
            button.clicked.connect(lambda checked=False, c=bgr, b=button: self._select_draw_color(c, b))
            self.color_buttons.append(button)
            draw_row.addWidget(button)
            if index == 0:
                button.setChecked(True)
        draw_row.addSpacing(8)
        for label, action in (("Undo", "undo"), ("Redo", "redo"), ("Clear Canvas", "clear")):
            action_button = ClickButton(label)
            action_button.setObjectName("drawActionButton")
            action_button.setFixedHeight(34)
            action_button.clicked.connect(lambda checked=False, a=action: self.draw_action_clicked.emit(a))
            draw_row.addWidget(action_button)
        overlay_layout.addWidget(self.draw_tools, alignment=Qt.AlignmentFlag.AlignCenter)

        controls = QFrame()
        controls.setObjectName("auraControls")
        control_row = QHBoxLayout(controls)
        control_row.setContentsMargins(0, 0, 0, 0)
        control_row.setSpacing(12)
        self.effect_group = QButtonGroup(self)
        self.effect_group.setExclusive(True)
        for effect in EFFECTS:
            button = ClickButton(effect)
            button.setCheckable(True)
            button.setObjectName("effectButton")
            button.setFixedSize(116, 42)
            button.setChecked(effect == self.selected_effect)
            button.clicked.connect(lambda checked=False, e=effect: self._select_effect(e))
            self.effect_group.addButton(button)
            control_row.addWidget(button)

        self.record_button = ClickButton("Start Recording")
        self.record_button.setObjectName("recordButton")
        self.record_button.setFixedSize(212, 42)
        self.record_button.clicked.connect(lambda checked=False: self.record_clicked.emit())
        control_row.addSpacing(16)
        control_row.addWidget(self.record_button)

        self.stop_button = IconActionButton(QStyle.StandardPixmap.SP_MediaStop)
        self.stop_button.setObjectName("stopAction")
        self.stop_button.clicked.connect(lambda checked=False: self.stop_clicked.emit())
        self.pause_button = IconActionButton(QStyle.StandardPixmap.SP_MediaPause)
        self.pause_button.setObjectName("roundAction")
        self.pause_button.clicked.connect(lambda checked=False: self.pause_clicked.emit())
        control_row.addWidget(self.stop_button)
        control_row.addWidget(self.pause_button)

        overlay_layout.addWidget(controls, alignment=Qt.AlignmentFlag.AlignCenter)
        camera_layout.addWidget(overlay_controls, 0, 0, Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignBottom)
        layout.addWidget(self.camera_box, 1)
        self.set_recording_state(False, False)
        self._update_draw_tools()

    def _select_effect(self, effect: str) -> None:
        self.selected_effect = effect
        self._update_draw_tools()
        self.effect_changed.emit(effect)

    def select_effect(self, effect: str) -> None:
        self.selected_effect = effect
        for button in self.effect_group.buttons():
            button.setChecked(button.text() == effect)
        self._update_draw_tools()

    def _select_draw_color(self, color: tuple[int, int, int], active_button: ClickButton) -> None:
        for button in self.color_buttons:
            button.setChecked(button is active_button)
        self.draw_color_changed.emit(color)

    def _update_draw_tools(self) -> None:
        self.draw_tools.setVisible(self.selected_effect == "Draw")

    def set_frame(self, frame) -> None:
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        h, w, ch = rgb.shape
        image = QImage(rgb.data, w, h, ch * w, QImage.Format.Format_RGB888).copy()
        pixmap = QPixmap.fromImage(image).scaled(
            self.preview.size(),
            Qt.AspectRatioMode.KeepAspectRatioByExpanding,
            Qt.TransformationMode.SmoothTransformation,
        )
        self.preview.setPixmap(pixmap)

    def set_recording_state(self, recording: bool, paused: bool = False) -> None:
        self.record_button.setVisible(not recording)
        self.stop_button.setVisible(recording)
        self.pause_button.setVisible(recording)
        icon = QStyle.StandardPixmap.SP_MediaPlay if paused else QStyle.StandardPixmap.SP_MediaPause
        self.pause_button.setIcon(QApplication.style().standardIcon(icon))


class CommandsScreen(QWidget):
    back_clicked = Signal()

    def __init__(self, shortcuts: dict[str, str]) -> None:
        super().__init__()
        outer = QVBoxLayout(self)
        outer.setContentsMargins(28, 22, 28, 20)
        outer.setSpacing(0)
        outer.addLayout(page_header(self.back_clicked))
        heading = QLabel("Commands")
        heading.setObjectName("commandsHeading")
        heading.setAlignment(Qt.AlignmentFlag.AlignCenter)
        outer.addSpacing(6)
        outer.addWidget(heading)
        outer.addSpacing(14)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setObjectName("commandsScroll")
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        grid_wrap = QFrame()
        grid_wrap.setMaximumWidth(980)
        grid = QGridLayout(grid_wrap)
        grid.setContentsMargins(8, 8, 8, 8)
        grid.setHorizontalSpacing(18)
        grid.setVerticalSpacing(18)
        rows = [
            ("CTRL + alt + C", "Open Palm Shift in control mode"),
            ("CTRL + alt + W", "Open Palm Shift aura mode (Water effect)"),
            ("CTRL + alt + A", "Open Palm Shift in aura mode"),
            ("CTRL + alt + X", "Close Palm Shift controls"),
            ("CTRL + alt + N", "Open Palm Shift aura mode (Neon effect)"),
            ("CTRL + alt + I", "Open Palm Shift aura mode (Ink effect)"),
            ("CTRL + alt + D", "Open Palm Shift aura mode (Draw effect)"),
        ]
        for index, (key, body) in enumerate(rows):
            grid.addWidget(CommandCard(key, body), index // 2, index % 2)
        layout.addWidget(grid_wrap, alignment=Qt.AlignmentFlag.AlignHCenter)
        layout.addStretch()
        scroll.setWidget(content)
        outer.addWidget(scroll, 1)


class CommandCard(QFrame):
    def __init__(self, key: str, body: str) -> None:
        super().__init__()
        self.setObjectName("commandCard")
        self.setMinimumSize(280, 132)
        col = QVBoxLayout(self)
        col.setContentsMargins(20, 16, 20, 16)
        col.setSpacing(7)
        key_label = QLabel(key)
        key_label.setObjectName("commandKey")
        body_label = QLabel(body)
        body_label.setObjectName("commandBody")
        body_label.setWordWrap(True)
        col.addWidget(key_label)
        col.addWidget(body_label)
        col.addStretch()


class IconActionButton(ClickButton):
    def __init__(self, icon: QStyle.StandardPixmap) -> None:
        super().__init__()
        self.setFixedSize(48, 48)
        self.setIcon(QApplication.style().standardIcon(icon))
        self.setIconSize(self.size() * 0.48)


def page_header(back_signal: Signal) -> QHBoxLayout:
    row = QHBoxLayout()
    row.setContentsMargins(0, 0, 0, 0)
    back = ClickButton()
    back.setObjectName("backButton")
    back.setFixedSize(48, 48)
    back.setText("<")
    font = QFont("Segoe UI", 34)
    font.setWeight(QFont.Weight.Bold)
    back.setFont(font)
    back.clicked.connect(lambda checked=False: back_signal.emit())
    row.addWidget(back)
    row.addStretch()
    row.addWidget(BrandTitle(52))
    row.addStretch()
    row.addSpacing(48)
    return row


def icon_pixmap(icon_name: str, size: int) -> QPixmap:
    return QPixmap(str(resource_path(f"assets/{icon_name}"))).scaled(
        size,
        size,
        Qt.AspectRatioMode.KeepAspectRatio,
        Qt.TransformationMode.SmoothTransformation,
    )


def add_shadow(widget: QWidget, blur: int, y: int, alpha: int) -> None:
    effect = QGraphicsDropShadowEffect(widget)
    effect.setBlurRadius(blur)
    effect.setOffset(0, y)
    color = Qt.GlobalColor.black
    effect.setColor(color)
    qcolor = effect.color()
    qcolor.setAlpha(alpha)
    effect.setColor(qcolor)
    widget.setGraphicsEffect(effect)
