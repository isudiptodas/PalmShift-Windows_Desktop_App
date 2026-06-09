from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from math import hypot

import cv2
import numpy as np


class TrackingMode(str, Enum):
    FINGER = "Finger Tracking"
    PALM = "Palm Tracking"


@dataclass
class GestureState:
    x: float = 0.5
    y: float = 0.5
    click: bool = False
    drag: bool = False
    scroll: float = 0.0
    swipe_x: float = 0.0
    zoom: float = 0.0
    pinch_distance: float = 1.0
    visible: bool = False
    label: str = ""


class HandTracker:
    def __init__(self, mode: TrackingMode) -> None:
        self.mode = mode
        self._hands = None
        try:
            import mediapipe as mp

            self._mp_hands = mp.solutions.hands
            self._hands = self._mp_hands.Hands(
                static_image_mode=False,
                max_num_hands=1,
                model_complexity=0,
                min_detection_confidence=0.58,
                min_tracking_confidence=0.62,
            )
        except Exception:
            self._hands = None
        self._last_scroll_y: float | None = None
        self._last_two_finger_x: float | None = None
        self._last_pinch_distance: float | None = None

    def close(self) -> None:
        if getattr(self, "_hands", None):
            self._hands.close()

    def process(self, frame) -> GestureState:
        if self._hands is None:
            return self._process_fallback(frame)

        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        result = self._hands.process(rgb)
        if not result.multi_hand_landmarks:
            self._last_scroll_y = None
            return GestureState(visible=False, label="No hand")

        landmarks = result.multi_hand_landmarks[0].landmark
        index_tip = landmarks[8]
        thumb_tip = landmarks[4]
        middle_tip = landmarks[12]
        wrist = landmarks[0]
        middle_mcp = landmarks[9]

        palm_x = (landmarks[0].x + landmarks[5].x + landmarks[9].x + landmarks[13].x + landmarks[17].x) / 5
        palm_y = (landmarks[0].y + landmarks[5].y + landmarks[9].y + landmarks[13].y + landmarks[17].y) / 5
        index_extended = index_tip.y < landmarks[6].y - 0.018
        if self.mode == TrackingMode.PALM and not index_extended:
            x, y = palm_x, palm_y
            label = "Palm"
        else:
            x, y = index_tip.x, index_tip.y
            label = "Pointer"

        pinch_distance = self._distance(index_tip, thumb_tip)
        pinch = pinch_distance < 0.052
        middle_pinch = self._distance(middle_tip, thumb_tip) < 0.058
        scroll = 0.0
        swipe_x = 0.0
        zoom = 0.0
        if pinch:
            if self._last_pinch_distance is not None:
                zoom = (self._last_pinch_distance - pinch_distance) * 28
            self._last_pinch_distance = pinch_distance
        else:
            self._last_pinch_distance = None
        if self._is_two_fingers_up(landmarks):
            if self._last_scroll_y is not None:
                scroll = (self._last_scroll_y - y) * 9
            if self._last_two_finger_x is not None:
                swipe_x = (x - self._last_two_finger_x) * 9
            self._last_scroll_y = y
            self._last_two_finger_x = x
        else:
            self._last_scroll_y = None
            self._last_two_finger_x = None

        return GestureState(
            x=max(0.0, min(1.0, x)),
            y=max(0.0, min(1.0, y)),
            click=pinch,
            drag=middle_pinch,
            scroll=scroll,
            swipe_x=swipe_x,
            zoom=zoom,
            pinch_distance=pinch_distance,
            visible=True,
            label=label,
        )

    @staticmethod
    def _distance(a, b) -> float:
        return hypot(a.x - b.x, a.y - b.y)

    @staticmethod
    def _is_two_fingers_up(landmarks) -> bool:
        return landmarks[8].y < landmarks[6].y and landmarks[12].y < landmarks[10].y

    def _process_fallback(self, frame) -> GestureState:
        """Basic camera fallback when the installed MediaPipe lacks the legacy solutions API."""
        flipped = cv2.flip(frame, 1)
        hsv = cv2.cvtColor(flipped, cv2.COLOR_BGR2HSV)
        lower = np.array([0, 25, 45], dtype=np.uint8)
        upper = np.array([25, 210, 255], dtype=np.uint8)
        mask1 = cv2.inRange(hsv, lower, upper)
        lower2 = np.array([160, 25, 45], dtype=np.uint8)
        upper2 = np.array([180, 210, 255], dtype=np.uint8)
        mask = cv2.bitwise_or(mask1, cv2.inRange(hsv, lower2, upper2))
        mask = cv2.medianBlur(mask, 7)
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if not contours:
            return GestureState(visible=False, label="No hand")
        contour = max(contours, key=cv2.contourArea)
        if cv2.contourArea(contour) < 1800:
            return GestureState(visible=False, label="No hand")
        x, y, w, h = cv2.boundingRect(contour)
        cx = x + w / 2
        cy = y + h / 2
        height, width = frame.shape[:2]
        return GestureState(
            x=max(0.0, min(1.0, cx / width)),
            y=max(0.0, min(1.0, cy / height)),
            click=w * h < 14000,
            drag=False,
            scroll=0.0,
            visible=True,
            label="Fallback",
        )
