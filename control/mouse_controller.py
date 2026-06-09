from __future__ import annotations

import time

from tracking.hand_tracker import GestureState


class MouseController:
    def __init__(self) -> None:
        self._backend = "pyautogui"
        self._click_down = False
        self._drag_down = False
        self._last_click_at = 0.0
        self._last_scroll_at = 0.0
        self._last_swipe_at = 0.0
        self._last_zoom_at = 0.0
        self._pinch_started_at = 0.0
        self._pinch_start_pos: tuple[int, int] | None = None
        self._smoothed_x: float | None = None
        self._smoothed_y: float | None = None
        self._mouse = None
        self._button = None

        try:
            import pyautogui

            pyautogui.FAILSAFE = False
            pyautogui.PAUSE = 0
            pyautogui.MINIMUM_DURATION = 0
            self._pyautogui = pyautogui
            self.screen_w, self.screen_h = pyautogui.size()
        except Exception:
            from pynput.mouse import Button, Controller

            self._backend = "pynput"
            self._mouse = Controller()
            self._button = Button.left
            self.screen_w, self.screen_h = 1920, 1080

    def apply(self, state: GestureState) -> tuple[int, int]:
        margin_x = 0.08
        margin_y = 0.08
        nx = min(1.0, max(0.0, (state.x - margin_x) / (1.0 - margin_x * 2)))
        ny = min(1.0, max(0.0, (state.y - margin_y) / (1.0 - margin_y * 2)))
        raw_x = int((1.0 - nx) * self.screen_w)
        raw_y = int(ny * self.screen_h)
        x, y = self._smooth(raw_x, raw_y)
        self._move(x, y)

        now = time.monotonic()
        pinch_active = state.click or state.drag
        if pinch_active and self._pinch_started_at == 0.0:
            self._pinch_started_at = now
            self._pinch_start_pos = (x, y)

        zoom = getattr(state, "zoom", 0.0)
        if abs(zoom) > 0.18 and not self._drag_down and now - self._last_zoom_at > 0.12:
            self._zoom(int(zoom * 5))
            self._last_zoom_at = now

        if pinch_active and abs(zoom) <= 0.22 and self._pinch_started_at and now - self._pinch_started_at > 0.18:
            if not self._drag_down and self._moved_from_pinch_start(x, y) > 14:
                self._down()
                self._drag_down = True

        if not pinch_active and self._pinch_started_at:
            duration = now - self._pinch_started_at
            movement = self._moved_from_pinch_start(x, y)
            if self._drag_down:
                self._up()
                self._drag_down = False
            elif duration < 0.32 and movement < 24 and now - self._last_click_at > 0.16:
                if now - self._last_click_at < 0.55:
                    self._double_click()
                else:
                    self._click()
                self._last_click_at = now
            self._pinch_started_at = 0.0
            self._pinch_start_pos = None

        if abs(state.scroll) > 0.18 and not self._drag_down and now - self._last_scroll_at > 0.035:
            self._scroll(int(state.scroll * 10))
            self._last_scroll_at = now
        if abs(getattr(state, "swipe_x", 0.0)) > 0.36 and not self._drag_down and now - self._last_swipe_at > 0.18:
            self._hscroll(int(state.swipe_x * 10))
            self._last_swipe_at = now

        return x, y

    def release(self) -> None:
        if self._drag_down:
            self._up()
        self._drag_down = False
        self._click_down = False
        self._pinch_started_at = 0.0

    def _move(self, x: int, y: int) -> None:
        if self._backend == "pyautogui":
            self._pyautogui.moveTo(x, y, duration=0)
        else:
            self._mouse.position = (x, y)

    def _click(self) -> None:
        if self._backend == "pyautogui":
            self._pyautogui.click()
        else:
            self._mouse.click(self._button)

    def _double_click(self) -> None:
        if self._backend == "pyautogui":
            self._pyautogui.doubleClick()
        else:
            self._mouse.click(self._button, 2)

    def _down(self) -> None:
        if self._backend == "pyautogui":
            self._pyautogui.mouseDown()
        else:
            self._mouse.press(self._button)

    def _up(self) -> None:
        if self._backend == "pyautogui":
            self._pyautogui.mouseUp()
        else:
            self._mouse.release(self._button)

    def _scroll(self, amount: int) -> None:
        if self._backend == "pyautogui":
            self._pyautogui.scroll(amount)
        else:
            self._mouse.scroll(0, amount)

    def _hscroll(self, amount: int) -> None:
        if self._backend == "pyautogui":
            try:
                self._pyautogui.hscroll(amount)
            except Exception:
                self._pyautogui.hotkey("alt", "right" if amount > 0 else "left")
        else:
            self._mouse.scroll(amount, 0)

    def _zoom(self, amount: int) -> None:
        if self._backend == "pyautogui":
            self._pyautogui.keyDown("ctrl")
            self._pyautogui.scroll(amount)
            self._pyautogui.keyUp("ctrl")

    def _smooth(self, x: int, y: int) -> tuple[int, int]:
        if self._smoothed_x is None or self._smoothed_y is None:
            self._smoothed_x = float(x)
            self._smoothed_y = float(y)
        distance = ((x - self._smoothed_x) ** 2 + (y - self._smoothed_y) ** 2) ** 0.5
        if distance < 3:
            return int(self._smoothed_x), int(self._smoothed_y)
        alpha = 0.34 if distance < 80 else 0.58
        self._smoothed_x = self._smoothed_x + (x - self._smoothed_x) * alpha
        self._smoothed_y = self._smoothed_y + (y - self._smoothed_y) * alpha
        return int(self._smoothed_x), int(self._smoothed_y)

    def _moved_from_pinch_start(self, x: int, y: int) -> float:
        if not self._pinch_start_pos:
            return 0.0
        sx, sy = self._pinch_start_pos
        return ((x - sx) ** 2 + (y - sy) ** 2) ** 0.5
