from __future__ import annotations

import time

import cv2
from PySide6.QtCore import QThread, Signal

from control.mouse_controller import MouseController
from tracking.hand_tracker import HandTracker, TrackingMode


class ControlWorker(QThread):
    pointer_moved = Signal(int, int, bool)
    status = Signal(str)
    error = Signal(str)

    def __init__(self, mode: TrackingMode, camera_index: int = 0) -> None:
        super().__init__()
        self.mode = mode
        self.camera_index = camera_index
        self._running = False

    def run(self) -> None:
        tracker = None
        mouse = None
        cap = None
        try:
            tracker = HandTracker(self.mode)
            mouse = MouseController()
            cap = cv2.VideoCapture(self.camera_index, cv2.CAP_DSHOW)
            if not cap.isOpened():
                cap.release()
                cap = cv2.VideoCapture(self.camera_index)
            if not cap.isOpened():
                self.error.emit("PalmShift could not open your webcam. Please check camera permissions and try again.")
                return

            cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 360)
            cap.set(cv2.CAP_PROP_FPS, 60)
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            self._running = True
            self.status.emit(f"{self.mode.value} active")

            while self._running:
                ok, frame = cap.read()
                if not ok:
                    self.error.emit("PalmShift lost access to the webcam.")
                    break
                frame = cv2.resize(frame, (640, 360), interpolation=cv2.INTER_AREA)
                state = tracker.process(frame)
                if state.visible:
                    x, y = mouse.apply(state)
                    self.pointer_moved.emit(x, y, True)
                else:
                    self.pointer_moved.emit(0, 0, False)
                time.sleep(0.001)
        except Exception as exc:
            self.error.emit(str(exc))
        finally:
            if mouse:
                mouse.release()
            if tracker:
                tracker.close()
            if cap:
                cap.release()
            self.status.emit("Control mode stopped")

    def stop(self) -> None:
        self._running = False
        self.wait(1800)
