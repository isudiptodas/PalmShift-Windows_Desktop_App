from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from math import hypot

import cv2


class TrackingMode(str, Enum):
    FINGER = "Finger Tracking"
    PALM = "Palm Tracking"


@dataclass
class HandSnapshot:
    label: str
    index: tuple[float, float]
    thumb: tuple[float, float]
    middle: tuple[float, float]
    ring: tuple[float, float]
    pinky: tuple[float, float]
    wrist: tuple[float, float]
    palm: tuple[float, float]
    span: float
    thumb_index: float
    thumb_middle: float
    extended: set[str] = field(default_factory=set)
    visible: bool = True


@dataclass
class GestureState:
    cursor_visible: bool = False
    action_visible: bool = False
    cursor_dx: float = 0.0
    cursor_dy: float = 0.0
    cursor_x: float = 0.5
    cursor_y: float = 0.5
    cursor_label: str = ""
    action_label: str = ""
    action: HandSnapshot | None = None
    label: str = ""

    @property
    def visible(self) -> bool:
        return self.cursor_visible


class HandTracker:
    def __init__(self, mode: TrackingMode) -> None:
        self.mode = mode
        self._hands = None
        try:
            import mediapipe as mp

            self._hands = mp.solutions.hands.Hands(
                static_image_mode=False,
                max_num_hands=2,
                model_complexity=0,
                min_detection_confidence=0.62,
                min_tracking_confidence=0.66,
            )
        except Exception:
            self._hands = None
        self._last_cursor_point: tuple[float, float] | None = None
        self._last_cursor_label: str | None = None

    def close(self) -> None:
        if self._hands:
            self._hands.close()

    def process(self, frame) -> GestureState:
        if self._hands is None:
            return GestureState(label="MediaPipe unavailable")

        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        result = self._hands.process(rgb)
        if not result.multi_hand_landmarks:
            self._last_cursor_point = None
            self._last_cursor_label = None
            return GestureState(label="Cursor hand lost")

        hands = self._snapshots(result)
        if not hands:
            self._last_cursor_point = None
            self._last_cursor_label = None
            return GestureState(label="Cursor hand lost")

        cursor = self._cursor_hand(hands)
        action = self._action_hand(hands, cursor)
        dx = dy = 0.0
        cursor_key = cursor.label
        if self._last_cursor_point is not None and self._last_cursor_label == cursor_key:
            dx = cursor.index[0] - self._last_cursor_point[0]
            dy = cursor.index[1] - self._last_cursor_point[1]
        self._last_cursor_point = cursor.index
        self._last_cursor_label = cursor_key

        return GestureState(
            cursor_visible=True,
            action_visible=action is not None,
            cursor_dx=dx,
            cursor_dy=dy,
            cursor_x=cursor.index[0],
            cursor_y=cursor.index[1],
            cursor_label=cursor.label,
            action_label=action.label if action else "",
            action=action,
            label=f"Cursor {cursor.label}" + (f" / Action {action.label}" if action else " / Action lost"),
        )

    def _snapshots(self, result) -> list[HandSnapshot]:
        handedness = result.multi_handedness or []
        snapshots = []
        for index, hand_landmarks in enumerate(result.multi_hand_landmarks or []):
            label = f"Hand{index}"
            if index < len(handedness) and handedness[index].classification:
                label = handedness[index].classification[0].label
            lm = hand_landmarks.landmark
            points = [(p.x, p.y) for p in lm]
            extended = self._extended(points)
            palm = (
                sum(points[i][0] for i in (0, 5, 9, 13, 17)) / 5,
                sum(points[i][1] for i in (0, 5, 9, 13, 17)) / 5,
            )
            span = max(
                self._distance_xy(points[4], points[20]),
                self._distance_xy(points[8], points[20]),
                self._distance_xy(points[4], points[12]),
            )
            snapshots.append(
                HandSnapshot(
                    label=label,
                    index=points[8],
                    thumb=points[4],
                    middle=points[12],
                    ring=points[16],
                    pinky=points[20],
                    wrist=points[0],
                    palm=palm,
                    span=span,
                    thumb_index=self._distance_xy(points[4], points[8]),
                    thumb_middle=self._distance_xy(points[4], points[12]),
                    extended=extended,
                )
            )
        return snapshots

    def _cursor_hand(self, hands: list[HandSnapshot]) -> HandSnapshot:
        for hand in hands:
            if hand.label.lower() == "right":
                return hand
        return hands[0]

    def _action_hand(self, hands: list[HandSnapshot], cursor: HandSnapshot) -> HandSnapshot | None:
        for hand in hands:
            if hand is not cursor:
                return hand
        return None

    def _extended(self, points: list[tuple[float, float]]) -> set[str]:
        extended = set()
        if abs(points[4][0] - points[3][0]) > 0.045:
            extended.add("thumb")
        for name, tip, pip, mcp in (
            ("index", 8, 6, 5),
            ("middle", 12, 10, 9),
            ("ring", 16, 14, 13),
            ("pinky", 20, 18, 17),
        ):
            if points[tip][1] < points[pip][1] - 0.025 and points[tip][1] < points[mcp][1] - 0.045:
                extended.add(name)
        return extended

    @staticmethod
    def _distance_xy(a: tuple[float, float], b: tuple[float, float]) -> float:
        return hypot(a[0] - b[0], a[1] - b[1])
