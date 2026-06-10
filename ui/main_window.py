from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QDateTime, QSize, QTimer, Slot
from PySide6.QtGui import QAction, QIcon
from PySide6.QtWidgets import (
    QApplication,
    QMainWindow,
    QMessageBox,
    QStackedWidget,
    QSystemTrayIcon,
)

from aura.aura_worker import AuraWorker
from aura.recorder import VideoRecorder
from config.settings import SettingsStore
from control.control_worker import ControlWorker
from tracking.hand_tracker import TrackingMode
from ui.indicator import TrackingIndicator
from ui.screens import AuraScreen, CommandsScreen, ControlActiveScreen, IntroScreen, SelectionScreen
from utils.paths import resource_path
from utils.shortcuts import ShortcutManager


class MainWindow(QMainWindow):
    def __init__(self, settings_store: SettingsStore) -> None:
        super().__init__()
        self.settings_store = settings_store
        self.settings = settings_store.settings
        self.icon_path = str(resource_path("assets/app_icon.png"))
        self.setWindowTitle("PalmShift")
        self.setWindowIcon(QIcon(self.icon_path))
        available = QApplication.primaryScreen().availableGeometry()
        self.normal_size = QSize(max(760, available.width() // 2), max(520, available.height() // 2))
        self.resize(self.normal_size)
        self.setMinimumSize(760, 520)

        self.stack = QStackedWidget()
        self.setCentralWidget(self.stack)
        self.indicator = TrackingIndicator()
        self.control_worker: ControlWorker | None = None
        self.camera_worker: AuraWorker | None = None
        self.recorder = VideoRecorder()
        self.aura_screen: AuraScreen | None = None
        self.current_effect = self.settings.last_aura_effect
        self._last_aura_frame = None
        self._recording_paused = False
        self._was_maximized_before_hide = False
        self._exiting = False
        self.control_active_screen: ControlActiveScreen | None = None
        self.control_started_at: QDateTime | None = None
        self.control_timer = QTimer(self)
        self.control_timer.timeout.connect(self._update_control_timer)

        self._build_tray()
        self._build_shortcuts()
        self._apply_styles()
        self._show_intro_or_selection()

    def _show_intro_or_selection(self) -> None:
        if self.settings.skip_intro:
            self.show_selection()
        else:
            intro = IntroScreen(self.icon_path)
            intro.start_clicked.connect(self._finish_intro)
            self._set_screen(intro)

    def _finish_intro(self, skip_intro: bool) -> None:
        self.settings_store.set_skip_intro(skip_intro)
        self.show_selection()

    def show_selection(self) -> None:
        self.stop_aura()
        screen = SelectionScreen()
        screen.control_clicked.connect(lambda: self.start_control_mode(TrackingMode.PALM.value))
        screen.aura_clicked.connect(self.show_aura)
        screen.commands_clicked.connect(self.show_commands)
        self._set_screen(screen)
        self._bring_forward()

    def show_commands(self) -> None:
        screen = CommandsScreen(self.settings.shortcuts)
        screen.back_clicked.connect(self.show_selection)
        self._set_screen(screen)

    def show_aura(self) -> None:
        self.stop_control_mode()
        self.aura_screen = AuraScreen(self.current_effect)
        self.aura_screen.back_clicked.connect(self.show_selection)
        self.aura_screen.effect_changed.connect(self._set_effect)
        self.aura_screen.draw_color_changed.connect(self._set_draw_color)
        self.aura_screen.draw_action_clicked.connect(self._queue_draw_action)
        self.aura_screen.record_clicked.connect(self._start_recording)
        self.aura_screen.pause_clicked.connect(self._toggle_recording_pause)
        self.aura_screen.stop_clicked.connect(self._stop_recording)
        self._set_screen(self.aura_screen)
        self.start_aura_camera()
        self._bring_forward()

    @Slot(str)
    def start_control_mode(self, mode_name: str) -> None:
        self.stop_aura()
        self.stop_control_mode()
        mode = TrackingMode.FINGER if "Finger" in mode_name else TrackingMode.PALM
        self.control_worker = ControlWorker(mode)
        self.control_worker.pointer_moved.connect(self.indicator.update_position)
        self.control_worker.error.connect(self._show_error)
        self.control_worker.start()
        self.control_active_screen = ControlActiveScreen(mode.value)
        self.control_active_screen.stop_clicked.connect(self.stop_active_mode)
        self._set_screen(self.control_active_screen)
        self.control_started_at = QDateTime.currentDateTime()
        self.control_timer.start(1000)
        self._update_control_timer()
        self._was_maximized_before_hide = self.isMaximized()
        self.showMinimized()

    def stop_control_mode(self) -> None:
        if self.control_worker:
            self.control_worker.stop()
            self.control_worker = None
        self.control_timer.stop()
        self.control_started_at = None
        self.indicator.hide()

    def toggle_control_mode(self) -> None:
        if self.control_worker:
            self.stop_control_mode()
            self.show_selection()
        else:
            self.start_control_mode(TrackingMode.PALM.value)

    def start_aura_camera(self) -> None:
        self.stop_aura()
        self.camera_worker = AuraWorker(self.current_effect)
        self.camera_worker.frame_ready.connect(self._on_camera_frame)
        self.camera_worker.error.connect(self._show_error)
        self.camera_worker.start()

    def stop_aura(self) -> None:
        self._stop_recording(show_message=False)
        if self.camera_worker:
            self.camera_worker.stop()
            self.camera_worker = None
        self._last_aura_frame = None

    def toggle_aura_mode(self) -> None:
        if self.camera_worker:
            self.stop_aura()
            self.show_selection()
        else:
            self.show_aura()

    @Slot(object)
    def _on_camera_frame(self, frame) -> None:
        self._last_aura_frame = frame
        if self.recorder.is_recording:
            self.recorder.write(frame)
        if self.aura_screen:
            self.aura_screen.set_frame(frame)

    @Slot(str)
    def _set_effect(self, effect: str) -> None:
        self.current_effect = effect
        self.settings_store.set_last_aura_effect(effect)
        if self.camera_worker:
            self.camera_worker.set_effect(effect)

    @Slot(tuple)
    def _set_draw_color(self, color: tuple[int, int, int]) -> None:
        if self.camera_worker:
            self.camera_worker.set_draw_color(color)

    @Slot(str)
    def _queue_draw_action(self, action: str) -> None:
        if self.camera_worker:
            self.camera_worker.queue_draw_action(action)

    def _start_recording(self) -> None:
        if not self.aura_screen:
            return
        if self._last_aura_frame is None:
            self._show_error("Recording can start after the first camera frame appears.")
            return
        path = self.recorder.start(self._last_aura_frame.shape)
        self._recording_paused = False
        self.aura_screen.set_recording_state(True, False)
        self.tray.showMessage("PalmShift", f"Recording started: {path.name}")

    def _toggle_recording_pause(self) -> None:
        self._recording_paused = not self._recording_paused
        if self._recording_paused:
            self.recorder.pause()
        else:
            self.recorder.resume()
        if self.aura_screen:
            self.aura_screen.set_recording_state(True, self._recording_paused)

    def _stop_recording(self, show_message: bool = True) -> None:
        was_recording = self.recorder.is_recording
        path = self.recorder.stop()
        if self.aura_screen:
            self.aura_screen.set_recording_state(False, False)
        self._recording_paused = False
        if show_message and was_recording and path:
            QMessageBox.information(self, "Recording saved", f"Saved to:\n{path}")

    def _build_tray(self) -> None:
        self.tray = QSystemTrayIcon(QIcon(self.icon_path), self)
        self.tray.setToolTip("PalmShift")
        menu = self.tray.contextMenu()
        if menu is None:
            from PySide6.QtWidgets import QMenu

            menu = QMenu()
        restore = QAction("Restore", self)
        restore.triggered.connect(self._restore_from_tray)
        stop = QAction("Stop Active Mode", self)
        stop.triggered.connect(self.stop_active_mode)
        exit_action = QAction("Exit", self)
        exit_action.triggered.connect(self.exit_app)
        menu.addAction(restore)
        menu.addAction(stop)
        menu.addSeparator()
        menu.addAction(exit_action)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(lambda reason: self._restore_from_tray() if reason == QSystemTrayIcon.ActivationReason.DoubleClick else None)
        self.tray.show()

    def _build_shortcuts(self) -> None:
        self.shortcuts = ShortcutManager(self.settings.shortcuts)
        self.shortcuts.toggle_control_requested.connect(self.toggle_control_mode)
        self.shortcuts.toggle_aura_requested.connect(self.toggle_aura_mode)
        self.shortcuts.aura_effect_requested.connect(self.open_aura_effect)
        self.shortcuts.stop_requested.connect(self.stop_active_mode)
        self.shortcuts.error.connect(self._show_error)
        self.shortcuts.start()

    def stop_active_mode(self) -> None:
        self.stop_control_mode()
        self.stop_aura()
        self.show_selection()

    def open_aura_effect(self, effect: str) -> None:
        self.current_effect = effect
        self.settings_store.set_last_aura_effect(effect)
        if self.aura_screen:
            self.aura_screen.select_effect(effect)
        if self.camera_worker:
            self.camera_worker.set_effect(effect)
        if not self.camera_worker:
            self.show_aura()

    def _restore_from_tray(self) -> None:
        if self._was_maximized_before_hide:
            self.showMaximized()
        else:
            self.show()
        self.activateWindow()

    def _update_control_timer(self) -> None:
        if not self.control_active_screen or not self.control_started_at:
            return
        elapsed = self.control_started_at.secsTo(QDateTime.currentDateTime())
        self.control_active_screen.set_elapsed(max(0, elapsed))

    def _bring_forward(self) -> None:
        if not self.isVisible():
            if self._was_maximized_before_hide:
                self.showMaximized()
            else:
                self.show()
        self.activateWindow()

    def exit_app(self) -> None:
        self._exiting = True
        self.stop_control_mode()
        self.stop_aura()
        self.shortcuts.stop()
        self.tray.hide()
        QApplication.quit()

    def closeEvent(self, event) -> None:
        event.accept()
        if not self._exiting:
            self.exit_app()

    def _set_screen(self, widget) -> None:
        self.stack.addWidget(widget)
        self.stack.setCurrentWidget(widget)

    def _show_error(self, message: str) -> None:
        QMessageBox.warning(self, "PalmShift", message)

    def _apply_styles(self) -> None:
        self.setStyleSheet(
            """
            QMainWindow, QWidget {
                background: #ffffff;
                color: #000000;
                font-family: Segoe UI, Arial;
                font-size: 16px;
            }
            QPushButton {
                border: none;
                background: transparent;
                color: #000000;
            }
            QPushButton:pressed {
                opacity: 0.72;
            }
            QFrame[pressed="true"] {
                background: #f3f3f3;
            }
            QLabel#brandTitle {
                background: transparent;
            }
            QWidget#brandTitle {
                background: transparent;
            }
            QLabel#brandPalm {
                background: transparent;
                color: #1b0011;
            }
            QLabel#brandShift {
                background: transparent;
                color: #b40070;
            }
            QFrame#introIconFrame {
                background: #ffffff;
                border-radius: 30px;
            }
            QLabel#welcomeText {
                font-size: 24px;
                color: #111111;
            }
            QLabel#tagline {
                font-size: 17px;
                color: #6c6c6c;
            }
            QPushButton#startButton {
                border-radius: 27px;
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #080006, stop:1 #CD007B);
                color: #ffffff;
                font-size: 24px;
                font-weight: 800;
            }
            QCheckBox#introCheck {
                color: #686868;
                font-size: 14px;
            }
            QCheckBox#introCheck::indicator {
                width: 14px;
                height: 14px;
                border-radius: 3px;
                border: 1px solid #9c9c9c;
                background: #d8d8d8;
            }
            QCheckBox#introCheck::indicator:checked {
                background: #315CFF;
                border-color: #315CFF;
                image: url(assets/checkmark.svg);
            }
            QFrame#modeCard {
                background: #ffffff;
                border-radius: 30px;
            }
            QLabel#modeIconBox {
                background: #ffffff;
                border-radius: 24px;
            }
            QLabel#modeTitle {
                background: transparent;
                font-size: 24px;
                font-weight: 900;
            }
            QLabel#modeBody {
                background: transparent;
                font-size: 15px;
                color: #666666;
            }
            QLabel#modeShortcut {
                background: transparent;
                font-size: 13px;
                font-weight: 900;
                color: #666666;
            }
            QPushButton#commandsLink {
                font-size: 21px;
                font-weight: 800;
                color: #666666;
            }
            QLabel#selectTitle {
                font-size: 34px;
                font-weight: 900;
                color: #222222;
            }
            QLabel#activeMode {
                font-size: 30px;
                font-weight: 900;
                color: #222222;
            }
            QLabel#controlTimer {
                font-size: 58px;
                font-weight: 900;
                color: #b40070;
            }
            QPushButton#stopControlButton {
                background: #d71920;
                color: #ffffff;
                border-radius: 12px;
                font-size: 20px;
                font-weight: 800;
            }
            QFrame#trackingChoice {
                background: transparent;
            }
            QLabel#trackingTile {
                background: #ffffff;
                border-radius: 28px;
                color: #000000;
            }
            QLabel#trackingLabel {
                background: transparent;
                font-size: 21px;
                color: #111111;
            }
            QPushButton#backButton {
                background: #dddddd;
                border-radius: 24px;
                color: #000000;
                padding-bottom: 5px;
            }
            QFrame#cameraBox {
                background: #1a1a1a;
                border-radius: 34px;
            }
            QLabel#cameraPreview {
                background: transparent;
                border-radius: 34px;
                color: #ffffff;
            }
            QFrame#auraControls {
                background: transparent;
                margin-bottom: 24px;
            }
            QFrame#auraOverlayControls {
                background: transparent;
            }
            QFrame#drawTools {
                background: transparent;
                border-radius: 12px;
                padding: 8px;
            }
            QPushButton#colorSwatch {
                border: 2px solid rgba(255, 255, 255, 0.55);
                border-radius: 15px;
            }
            QPushButton#colorSwatch:checked {
                border: 3px solid #ffffff;
            }
            QPushButton#drawActionButton {
                background: rgba(0, 0, 0, 0.28);
                border: 1px solid rgba(255, 255, 255, 0.72);
                border-radius: 9px;
                color: #ffffff;
                font-size: 13px;
                font-weight: 800;
                padding-left: 12px;
                padding-right: 12px;
            }
            QPushButton#effectButton {
                background: rgba(105, 105, 116, 0.78);
                border-radius: 9px;
                color: #ffffff;
                font-size: 17px;
            }
            QPushButton#effectButton:checked {
                background: #111020;
            }
            QPushButton#recordButton {
                background: #ffffff;
                border-radius: 9px;
                color: #000000;
                font-size: 16px;
                font-weight: 700;
            }
            QPushButton#roundAction, QPushButton#stopAction {
                background: #ffffff;
                border-radius: 24px;
                color: #000000;
                font-weight: 900;
            }
            QPushButton#stopAction {
                color: #ff0000;
            }
            QFrame#commandCard {
                background: #e9e9e9;
                border-radius: 18px;
            }
            QLabel#commandsHeading {
                background: transparent;
                color: #222222;
                font-size: 28px;
                font-weight: 900;
            }
            QLabel#commandKey {
                background: transparent;
                color: #5e5e5e;
                font-size: 24px;
                font-weight: 900;
            }
            QLabel#commandBody {
                background: transparent;
                color: #000000;
                font-size: 15px;
            }
            """
        )
