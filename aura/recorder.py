from __future__ import annotations

from datetime import datetime
from pathlib import Path
import time

import cv2

from utils.paths import recordings_dir


class VideoRecorder:
    def __init__(self, fps: int = 20) -> None:
        self.fps = fps
        self.writer = None
        self.path: Path | None = None
        self.paused = False
        self._last_write_at: float | None = None

    @property
    def is_recording(self) -> bool:
        return self.writer is not None

    def start(self, frame_shape) -> Path:
        self.stop()
        h, w = frame_shape[:2]
        self.path = recordings_dir() / f"PalmShift_{datetime.now():%Y%m%d_%H%M%S}.mp4"
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        self.writer = cv2.VideoWriter(str(self.path), fourcc, self.fps, (w, h))
        self.paused = False
        self._last_write_at = None
        return self.path

    def write(self, frame) -> None:
        if self.writer and not self.paused:
            now = time.monotonic()
            if self._last_write_at is None:
                copies = 1
            else:
                elapsed = max(0.0, now - self._last_write_at)
                copies = max(1, min(5, round(elapsed * self.fps)))
            for _ in range(copies):
                self.writer.write(frame)
            self._last_write_at = now

    def pause(self) -> None:
        self.paused = True

    def resume(self) -> None:
        self.paused = False

    def stop(self) -> Path | None:
        path = self.path
        if self.writer:
            self.writer.release()
        self.writer = None
        self.paused = False
        self._last_write_at = None
        return path
