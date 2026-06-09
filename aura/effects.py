from __future__ import annotations

import math
import time

import cv2
import numpy as np

EFFECTS = ("Water", "Neon", "Ink")
HAND_CONNECTIONS = (
    (0, 1), (1, 2), (2, 3), (3, 4),
    (0, 5), (5, 6), (6, 7), (7, 8),
    (0, 9), (9, 10), (10, 11), (11, 12),
    (0, 13), (13, 14), (14, 15), (15, 16),
    (0, 17), (17, 18), (18, 19), (19, 20),
    (5, 9), (9, 13), (13, 17),
)
FINGER_TIPS = (4, 8, 12, 16, 20)
FINGER_IDS = {
    4: "thumb",
    8: "index",
    12: "middle",
    16: "ring",
    20: "pinky",
}


class AuraEffectRenderer:
    def __init__(self) -> None:
        self._hands = None
        try:
            import mediapipe as mp

            self._hands = mp.solutions.hands.Hands(
                static_image_mode=False,
                max_num_hands=2,
                model_complexity=0,
                min_detection_confidence=0.6,
                min_tracking_confidence=0.55,
            )
        except Exception:
            self._hands = None
        self._tick = 0
        self._grid_shape = None
        self._map_x = None
        self._map_y = None
        self._neon_trails = []
        self._last_neon_points = {}
        self._water_surface = None
        self._water_velocity = None
        self._water_mask = None
        self._last_water_points = {}
        self._ink_density = None
        self._ink_velocity = None
        self._ink_drips = []
        self._last_ink_points = {}

    def close(self) -> None:
        if self._hands:
            self._hands.close()

    def render(self, frame, effect: str):
        self._tick += 1
        effect = effect if effect in EFFECTS else "Water"
        frame = cv2.flip(frame, 1)
        landmarks = self._landmark_points(frame)
        if not landmarks:
            if effect == "Neon":
                return self._neon_contact(frame, [])
            if effect == "Ink":
                return self._ink_contact(frame, [])
            return self._water_contact(frame, [])
        if effect == "Neon":
            return self._neon_contact(frame, landmarks)
        if effect == "Ink":
            return self._ink_contact(frame, landmarks)
        return self._water_contact(frame, landmarks)

    def _landmark_points(self, frame) -> list[dict]:
        if self._hands is None:
            return self._fallback_points(frame)
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        result = self._hands.process(rgb)
        if not result.multi_hand_landmarks:
            return []
        h, w = frame.shape[:2]
        hands = []
        handedness = result.multi_handedness or []
        for hand_index, hand_landmarks in enumerate(result.multi_hand_landmarks):
            landmarks = hand_landmarks.landmark
            label = f"hand{hand_index}"
            if hand_index < len(handedness) and handedness[hand_index].classification:
                label = handedness[hand_index].classification[0].label.lower()

            palm_open = self._is_open_hand(landmarks)
            pixel_landmarks = [(int(point.x * w), int(point.y * h)) for point in landmarks]
            contacts = []

            for tip, pip in ((8, 6), (12, 10), (16, 14), (20, 18)):
                if palm_open and self._finger_is_extended(landmarks, tip, pip):
                    point = landmarks[tip]
                    contacts.append((f"{label}:{FINGER_IDS[tip]}", int(point.x * w), int(point.y * h)))
            thumb_tip = landmarks[4]
            if palm_open and self._thumb_is_extended(landmarks):
                contacts.append((f"{label}:thumb", int(thumb_tip.x * w), int(thumb_tip.y * h)))
            if contacts:
                palm_ids = (0, 5, 9, 13, 17)
                palm_x = int(sum(pixel_landmarks[index][0] for index in palm_ids) / len(palm_ids))
                palm_y = int(sum(pixel_landmarks[index][1] for index in palm_ids) / len(palm_ids))
                contour_ids = (0, 1, 2, 4, 8, 12, 16, 20, 18, 17)
                contour = [pixel_landmarks[index] for index in contour_ids]
                hands.append(
                    {
                        "id": label,
                        "contacts": contacts,
                        "landmarks": pixel_landmarks,
                        "palm": (palm_x, palm_y),
                        "contour": contour,
                    }
                )
        return hands

    def _is_open_hand(self, landmarks) -> bool:
        extended = 0
        for tip, pip in ((8, 6), (12, 10), (16, 14), (20, 18)):
            if self._finger_is_extended(landmarks, tip, pip):
                extended += 1
        if self._thumb_is_extended(landmarks):
            extended += 1
        return extended >= 1

    def _finger_is_extended(self, landmarks, tip: int, pip: int) -> bool:
        tip_point = landmarks[tip]
        pip_point = landmarks[pip]
        mcp_point = landmarks[tip - 3]
        # The fingertip must be clearly above the knuckle chain. This avoids knuckles
        # becoming neon/water contacts when the palm is folded.
        return tip_point.y < pip_point.y - 0.018 and tip_point.y < mcp_point.y - 0.035

    def _thumb_is_extended(self, landmarks) -> bool:
        tip = landmarks[4]
        ip = landmarks[3]
        mcp = landmarks[2]
        wrist = landmarks[0]
        horizontal_open = abs(tip.x - ip.x) > 0.055 and abs(tip.x - mcp.x) > 0.075
        away_from_palm = math.hypot(tip.x - wrist.x, tip.y - wrist.y) > math.hypot(ip.x - wrist.x, ip.y - wrist.y)
        return horizontal_open and away_from_palm

    def _fallback_points(self, frame) -> list[dict]:
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        mask1 = cv2.inRange(hsv, np.array([0, 25, 45], dtype=np.uint8), np.array([25, 210, 255], dtype=np.uint8))
        mask2 = cv2.inRange(hsv, np.array([160, 25, 45], dtype=np.uint8), np.array([180, 210, 255], dtype=np.uint8))
        mask = cv2.bitwise_or(mask1, mask2)
        mask = cv2.medianBlur(mask, 7)
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if not contours:
            return []
        contour = max(contours, key=cv2.contourArea)
        if cv2.contourArea(contour) < 1800:
            return []
        x, y, w, h = cv2.boundingRect(contour)
        if h < 75:
            return []
        point = (x + w // 2, y + 8)
        return [{"id": "fallback", "contacts": [("fallback:index", *point)], "landmarks": [], "palm": point, "contour": []}]

    def _water_contact(self, frame, points):
        h, w = frame.shape[:2]
        map_x, map_y = self._grid(h, w)
        if self._water_surface is None or self._water_surface.shape != (h, w):
            self._water_surface = np.zeros((h, w), dtype=np.float32)
            self._water_velocity = np.zeros((h, w, 2), dtype=np.float32)
            self._water_mask = np.zeros((h, w), dtype=np.float32)

        impulse = np.zeros((h, w), dtype=np.float32)
        velocity_x = np.zeros((h, w), dtype=np.float32)
        velocity_y = np.zeros((h, w), dtype=np.float32)
        contour_pressure = np.zeros((h, w), dtype=np.float32)
        contacts = self._contact_points(points)
        for contact_id, x, y in contacts:
            point = (x, y)
            previous = self._last_water_points.get(contact_id)
            if previous is not None:
                px, py = previous
                distance = math.hypot(x - px, y - py)
                if distance < 130:
                    strength = min(1.0, 0.22 + distance / 85.0)
                    cv2.line(impulse, previous, point, strength, 7, cv2.LINE_AA)
                    cv2.line(velocity_x, previous, point, (x - px) * 0.035, 9, cv2.LINE_AA)
                    cv2.line(velocity_y, previous, point, (y - py) * 0.035, 9, cv2.LINE_AA)
            cv2.circle(impulse, point, 3, 0.72, -1, cv2.LINE_AA)
            self._last_water_points[contact_id] = point

        for hand in points:
            palm = hand.get("palm")
            contour = hand.get("contour") or []
            if palm:
                cv2.circle(contour_pressure, palm, 18, 0.08, -1, cv2.LINE_AA)
            if len(contour) >= 4:
                contour_array = np.array(contour, dtype=np.int32)
                cv2.polylines(contour_pressure, [contour_array], True, 0.18, 5, cv2.LINE_AA)
        if not contacts:
            self._last_water_points = {}

        impulse = cv2.GaussianBlur(impulse, (0, 0), 7)
        contour_pressure = cv2.GaussianBlur(contour_pressure, (0, 0), 12)
        velocity = np.dstack((velocity_x, velocity_y)).astype(np.float32)
        self._water_velocity = cv2.GaussianBlur(self._water_velocity * 0.86 + velocity, (0, 0), 5)
        self._water_mask = cv2.GaussianBlur(self._water_mask * 0.9 + contour_pressure, (0, 0), 6)
        self._water_surface = cv2.GaussianBlur(self._water_surface * 0.88 + impulse * 0.55 + self._water_mask * 0.28, (0, 0), 3.5)
        self._water_surface = np.clip(self._water_surface, 0.0, 1.0)
        self._water_mask = np.clip(self._water_mask, 0.0, 1.0)

        grad_x = cv2.Sobel(self._water_surface, cv2.CV_32F, 1, 0, ksize=5)
        grad_y = cv2.Sobel(self._water_surface, cv2.CV_32F, 0, 1, ksize=5)
        surface = self._water_surface
        liquid_flow_x = np.sin((map_y * 0.071) + (map_x * 0.014) + self._tick * 0.24) * surface * 1.25
        liquid_flow_y = np.cos((map_x * 0.068) - (map_y * 0.012) + self._tick * 0.2) * surface * 1.1
        disp_x = (grad_x * 64.0) + self._water_velocity[:, :, 0] + liquid_flow_x
        disp_y = (grad_y * 64.0) + self._water_velocity[:, :, 1] + liquid_flow_y

        warped = cv2.remap(
            frame,
            map_x + disp_x,
            map_y + disp_y,
            cv2.INTER_LINEAR,
            borderMode=cv2.BORDER_REFLECT,
        )
        chroma_x = np.clip(disp_x * 0.42, -2.2, 2.2)
        chroma_y = np.clip(disp_y * 0.42, -2.2, 2.2)
        red = cv2.remap(frame[:, :, 2], map_x + disp_x + chroma_x, map_y + disp_y, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)
        blue = cv2.remap(frame[:, :, 0], map_x + disp_x - chroma_x, map_y + disp_y - chroma_y, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)
        warped[:, :, 2] = cv2.addWeighted(warped[:, :, 2], 0.78, red, 0.22, 0)
        warped[:, :, 0] = cv2.addWeighted(warped[:, :, 0], 0.8, blue, 0.2, 0)

        edge = cv2.GaussianBlur(np.abs(grad_x) + np.abs(grad_y), (0, 0), 2)
        edge = np.clip(edge * 255.0, 0, 255).astype(np.uint8)
        shimmer = (np.sin((map_x * 0.05 + map_y * 0.04) + self._tick * 0.32) * 16 + 22).astype(np.uint8)
        highlight_mask = cv2.multiply(edge, shimmer, scale=1 / 255.0)
        highlight = cv2.merge((highlight_mask // 3, highlight_mask, highlight_mask))
        touched = cv2.addWeighted(warped, 0.98, highlight, 0.18, 0)
        alpha = np.clip(surface * 1.3 + self._water_mask * 0.18, 0.0, 0.86)[..., None]
        return (touched * alpha + frame * (1.0 - alpha)).astype(np.uint8)

    def _neon_contact(self, frame, points):
        now = time.monotonic()
        colors = ((255, 20, 190), (80, 230, 255), (120, 255, 160), (255, 210, 90), (220, 110, 255))
        contacts = self._contact_points(points)
        for contact_id, x, y in contacts:
            point = (x, y)
            previous = self._last_neon_points.get(contact_id)
            if previous is not None:
                px, py = previous
                if math.hypot(x - px, y - py) < 95:
                    color_index = abs(hash(contact_id)) % len(colors)
                    self._neon_trails.append((previous, point, colors[color_index], now))
            self._last_neon_points[contact_id] = point
        if not contacts:
            self._last_neon_points = {}

        self._neon_trails = [trail for trail in self._neon_trails if now - trail[3] <= 2.0]
        glow = np.zeros_like(frame)
        core = np.zeros_like(frame)
        for start, end, color, born in self._neon_trails:
            age = now - born
            alpha = max(0.0, 1.0 - age / 2.0)
            thickness = max(1, int(7 * alpha))
            dim = tuple(int(c * alpha) for c in color)
            cv2.line(glow, start, end, dim, thickness + 9, cv2.LINE_AA)
            cv2.line(core, start, end, dim, max(1, thickness), cv2.LINE_AA)

        glow = cv2.GaussianBlur(glow, (35, 35), 0)
        lit = cv2.addWeighted(frame, 0.94, glow, 1.25, 0)
        return cv2.addWeighted(lit, 1.0, core, 0.7, 0)

    def _ink_contact(self, frame, points):
        h, w = frame.shape[:2]
        map_x, map_y = self._grid(h, w)
        if self._ink_density is None or self._ink_density.shape != (h, w):
            self._ink_density = np.zeros((h, w), dtype=np.float32)
            self._ink_velocity = np.zeros((h, w, 2), dtype=np.float32)

        source = np.zeros((h, w), dtype=np.float32)
        velocity_x = np.zeros((h, w), dtype=np.float32)
        velocity_y = np.zeros((h, w), dtype=np.float32)
        now_points = {}
        now = time.monotonic()
        for hand in points:
            index_point = self._index_point(hand)
            if not index_point:
                continue
            contact_id, x, y = index_point
            point = (x, y)
            previous = self._last_ink_points.get(contact_id)
            speed = 0.0
            if previous is not None:
                px, py = previous
                speed = math.hypot(x - px, y - py)
                if speed < 120:
                    thickness = max(3, int(11 - min(speed, 50) * 0.13))
                    cv2.line(source, previous, point, 0.64 if speed < 10 else 0.34, thickness, cv2.LINE_AA)
                    cv2.line(velocity_x, previous, point, (x - px) * 0.012, thickness + 4, cv2.LINE_AA)
                    cv2.line(velocity_y, previous, point, max(1.5, (y - py) * 0.014 + 1.8), thickness + 4, cv2.LINE_AA)
                    if speed < 16 and now - self._last_ink_points.get(f"{contact_id}:born", (0, 0, 0))[2] > 0.16:
                        self._ink_drips.append(
                            {
                                "x": float(x + np.random.uniform(-4, 4)),
                                "y": float(y),
                                "length": float(np.random.uniform(24, 48)),
                                "speed": float(np.random.uniform(3.6, 6.2)),
                                "width": float(np.random.uniform(4.5, 8.0)),
                                "born": now,
                            }
                        )
            radius = 8 if speed < 10 else 4
            amount = 0.78 if speed < 10 else 0.38
            cv2.circle(source, point, radius, amount, -1, cv2.LINE_AA)
            now_points[contact_id] = point
            now_points[f"{contact_id}:born"] = (x, y, now)
        self._last_ink_points = now_points

        self._draw_ink_drips(source, h, w, now)
        fall = 5.4
        horizontal_flow = self._ink_velocity[:, :, 0] * 0.4 + np.sin((map_y * 0.035) + self._tick * 0.18) * self._ink_density * 0.55
        vertical_flow = fall + self._ink_velocity[:, :, 1] * 0.36 + self._ink_density * 3.2
        advected = cv2.remap(
            self._ink_density,
            map_x - horizontal_flow,
            map_y - vertical_flow,
            cv2.INTER_LINEAR,
            borderMode=cv2.BORDER_CONSTANT,
            borderValue=0,
        )
        velocity = np.dstack((velocity_x, velocity_y)).astype(np.float32)
        self._ink_velocity = cv2.GaussianBlur(self._ink_velocity * 0.82 + velocity, (0, 0), 3)
        source = cv2.GaussianBlur(source, (0, 0), 1.8)
        density = advected * 0.996 + source
        density = cv2.dilate(density, np.ones((2, 1), dtype=np.uint8), iterations=1)
        density = cv2.GaussianBlur(density, (0, 0), 0.9)
        self._ink_density = np.clip(density, 0.0, 1.0)

        thin = np.clip(self._ink_density * 1.5, 0.0, 1.0)
        ink_color = np.zeros_like(frame, dtype=np.float32)
        ink_color[:, :, 0] = 120
        ink_color[:, :, 1] = 32
        ink_color[:, :, 2] = 4
        edge = cv2.GaussianBlur(np.abs(cv2.Sobel(thin, cv2.CV_32F, 1, 0)) + np.abs(cv2.Sobel(thin, cv2.CV_32F, 0, 1)), (0, 0), 2)
        highlight = np.clip(edge * 180, 0, 255).astype(np.uint8)
        shine = cv2.merge((highlight, highlight // 2, highlight // 5)).astype(np.float32)
        alpha = np.clip(thin * 0.92, 0.0, 0.94)[..., None]
        composed = frame.astype(np.float32) * (1.0 - alpha) + ink_color * alpha
        composed = cv2.addWeighted(composed.astype(np.uint8), 1.0, shine.astype(np.uint8), 0.14, 0)
        return composed

    def _contact_points(self, points):
        if points and isinstance(points[0], dict):
            contacts = []
            for hand in points:
                contacts.extend(hand.get("contacts", []))
            return contacts
        return points

    def _index_point(self, hand):
        landmarks = hand.get("landmarks") or []
        if len(landmarks) > 8:
            x, y = landmarks[8]
            return (f"{hand.get('id', 'hand')}:index", int(x), int(y))
        for contact in hand.get("contacts", []):
            if ":index" in contact[0]:
                return contact
        return None

    def _draw_ink_drips(self, source, h: int, w: int, now: float) -> None:
        alive = []
        for drip in self._ink_drips:
            age = now - drip["born"]
            drip["y"] += drip["speed"] * (1.0 + min(age, 2.0) * 0.56)
            drip["length"] += drip["speed"] * 1.05
            if drip["y"] - drip["length"] > h or age > 7.0:
                continue
            x = int(max(0, min(w - 1, drip["x"] + math.sin(age * 3.1) * 2.2)))
            y = int(max(0, min(h - 1, drip["y"])))
            top = int(max(0, y - drip["length"]))
            width = max(2, int(drip["width"] * (1.0 - min(age, 6.0) * 0.035)))
            cv2.line(source, (x, top), (x, y), 0.48, width, cv2.LINE_AA)
            cv2.circle(source, (x, y), max(width + 2, int(width * 1.8)), 0.76, -1, cv2.LINE_AA)
            if age > 0.9 and int(age * 10) % 7 == 0:
                side_x = int(max(0, min(w - 1, x + np.random.uniform(-10, 10))))
                side_y = int(max(0, min(h - 1, y - np.random.uniform(8, 28))))
                cv2.circle(source, (side_x, side_y), max(2, width // 2), 0.25, -1, cv2.LINE_AA)
            alive.append(drip)
        self._ink_drips = alive[-80:]

    def _grid(self, h: int, w: int):
        if self._grid_shape != (h, w):
            map_y, map_x = np.indices((h, w), dtype=np.float32)
            self._map_x = map_x
            self._map_y = map_y
            self._grid_shape = (h, w)
        return self._map_x, self._map_y


def apply_effect(frame, effect: str):
    """Compatibility helper for simple one-off use."""
    renderer = AuraEffectRenderer()
    try:
        return renderer.render(frame, effect)
    finally:
        renderer.close()
