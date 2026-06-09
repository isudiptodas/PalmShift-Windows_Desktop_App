from __future__ import annotations

import threading
import time

import cv2
from PySide6.QtCore import QThread, Signal

from aura.effects import AuraEffectRenderer


class AuraWorker(QThread):
    frame_ready = Signal(object)
    error = Signal(str)

    def __init__(self, effect: str, camera_index: int = 0, target_fps: int = 60) -> None:
        super().__init__()
        self.camera_index = camera_index
        self.target_fps = target_fps
        self._effect = effect
        self._effect_lock = threading.Lock()
        self._running = False

    def set_effect(self, effect: str) -> None:
        with self._effect_lock:
            self._effect = effect

    def run(self) -> None:
        renderer = AuraEffectRenderer()
        cap = cv2.VideoCapture(self.camera_index, cv2.CAP_DSHOW)
        if not cap.isOpened():
            cap.release()
            cap = cv2.VideoCapture(self.camera_index)
        if not cap.isOpened():
            renderer.close()
            self.error.emit("PalmShift could not open your webcam. Please check camera permissions and try again.")
            return

        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 360)
        cap.set(cv2.CAP_PROP_FPS, self.target_fps)
        delay = 1.0 / max(1, self.target_fps)
        self._running = True

        try:
            while self._running:
                ok, frame = cap.read()
                if not ok:
                    self.error.emit("PalmShift lost access to the webcam.")
                    break
                frame = cv2.resize(frame, (640, 360), interpolation=cv2.INTER_AREA)
                with self._effect_lock:
                    effect = self._effect
                processed = renderer.render(frame, effect)
                self.frame_ready.emit(processed)
                time.sleep(delay)
        except Exception as exc:
            self.error.emit(str(exc))
        finally:
            cap.release()
            renderer.close()

    def stop(self) -> None:
        self._running = False
        self.wait(1800)
