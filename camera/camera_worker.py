from __future__ import annotations

import time

import cv2
from PySide6.QtCore import QThread, Signal


class CameraWorker(QThread):
    frame_ready = Signal(object)
    error = Signal(str)

    def __init__(self, camera_index: int = 0, target_fps: int = 30) -> None:
        super().__init__()
        self.camera_index = camera_index
        self.target_fps = target_fps
        self._running = False

    def run(self) -> None:
        self._running = True
        cap = cv2.VideoCapture(self.camera_index, cv2.CAP_DSHOW)
        if not cap.isOpened():
            cap.release()
            cap = cv2.VideoCapture(self.camera_index)
        if not cap.isOpened():
            self.error.emit("PalmShift could not open your webcam. Please check camera permissions and try again.")
            return

        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
        cap.set(cv2.CAP_PROP_FPS, self.target_fps)
        delay = 1.0 / max(1, self.target_fps)

        while self._running:
            ok, frame = cap.read()
            if not ok:
                self.error.emit("PalmShift lost access to the webcam.")
                break
            self.frame_ready.emit(frame)
            time.sleep(delay)

        cap.release()

    def stop(self) -> None:
        self._running = False
        self.wait(1500)
