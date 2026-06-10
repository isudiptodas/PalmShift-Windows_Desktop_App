from __future__ import annotations

import time
from enum import Enum

from tracking.hand_tracker import GestureState, HandSnapshot


class ActionState(str, Enum):
    IDLE = "Idle"
    CLICK_PENDING = "Click pending"
    CLICKED = "Click"
    RIGHT_CLICK_PENDING = "Right click pending"
    DRAGGING = "Dragging"
    SCROLLING = "Scrolling"
    ZOOMING = "Zooming"
    ACTION_HAND_LOST = "Action hand lost"


class MouseController:
    def __init__(self) -> None:
        self._backend = "pyautogui"
        self._state = ActionState.IDLE
        self._last_feedback = ""
        self._left_pinch_started = 0.0
        self._right_pinch_started = 0.0
        self._left_click_fired = False
        self._right_click_fired = False
        self._last_click_release = 0.0
        self._click_count = 0
        self._scroll_anchor: tuple[float, float] | None = None
        self._scroll_cooldown = 0.0
        self._zoom_span: float | None = None
        self._zoom_cooldown = 0.0
        self._drag_down = False
        self._cursor_ready = False
        self._smoothed_dx = 0.0
        self._smoothed_dy = 0.0

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
            self._left_button = Button.left
            self._right_button = Button.right
            self.screen_w, self.screen_h = 1920, 1080

    def apply(self, state: GestureState) -> tuple[int, int, bool, str]:
        if state.cursor_visible:
            self._move_relative(state.cursor_dx, state.cursor_dy)
        else:
            self._cursor_ready = False
            self._smoothed_dx = 0.0
            self._smoothed_dy = 0.0

        if state.action:
            feedback = self._apply_action(state.action)
        else:
            feedback = "Action hand lost"
            self._reset_action_state(release_drag=False)

        x, y = self._position()
        visible = state.cursor_visible
        self._last_feedback = feedback
        return x, y, visible, feedback

    def release(self) -> None:
        if self._drag_down:
            self._up()
        self._drag_down = False
        self._reset_action_state(release_drag=False)

    def _move_relative(self, dx: float, dy: float) -> None:
        if not self._cursor_ready:
            self._cursor_ready = True
            self._smoothed_dx = 0.0
            self._smoothed_dy = 0.0
            return
        distance = (dx * dx + dy * dy) ** 0.5
        if distance < 0.0038:
            self._smoothed_dx *= 0.55
            self._smoothed_dy *= 0.55
            return
        alpha = 0.22 if distance < 0.012 else 0.46
        self._smoothed_dx = self._smoothed_dx + (dx - self._smoothed_dx) * alpha
        self._smoothed_dy = self._smoothed_dy + (dy - self._smoothed_dy) * alpha
        gain = 1050 if distance < 0.016 else 1500
        move_x = int(self._smoothed_dx * gain)
        move_y = int(self._smoothed_dy * gain)
        if abs(move_x) < 1 and abs(move_y) < 1:
            return
        if self._backend == "pyautogui":
            self._pyautogui.moveRel(move_x, move_y, duration=0)
        else:
            x, y = self._mouse.position
            self._mouse.position = (x + move_x, y + move_y)

    def _apply_action(self, hand: HandSnapshot) -> str:
        now = time.monotonic()
        left_pinched = hand.thumb_index < 0.045
        right_pinched = hand.thumb_middle < 0.052
        two_fingers = hand.extended == {"index", "middle"}
        full_hand = len(hand.extended) >= 4

        if self._drag_down:
            if not left_pinched:
                self._up()
                self._drag_down = False
                self._reset_action_state(release_drag=False)
                return "Drag released"
            self._state = ActionState.DRAGGING
            return "Dragging"

        if left_pinched:
            self._scroll_anchor = None
            self._zoom_span = None
            if self._left_pinch_started == 0.0:
                self._left_pinch_started = now
                self._left_click_fired = False
                self._state = ActionState.CLICK_PENDING
            held = now - self._left_pinch_started
            if held >= 0.38:
                self._down()
                self._drag_down = True
                self._left_click_fired = True
                self._state = ActionState.DRAGGING
                return "Dragging"
            if held >= 0.12 and not self._left_click_fired:
                if now - self._last_click_release <= 0.38 and self._click_count == 1:
                    self._double_click()
                    self._click_count = 0
                    self._left_click_fired = True
                    self._state = ActionState.CLICKED
                    return "Double Click"
                self._click()
                self._click_count = 1
                self._left_click_fired = True
                self._state = ActionState.CLICKED
                return "Click"
            return "Click pending"

        if self._left_pinch_started:
            self._last_click_release = now
            self._left_pinch_started = 0.0
            self._left_click_fired = False

        if right_pinched:
            self._scroll_anchor = None
            self._zoom_span = None
            if self._right_pinch_started == 0.0:
                self._right_pinch_started = now
                self._right_click_fired = False
                self._state = ActionState.RIGHT_CLICK_PENDING
            if now - self._right_pinch_started >= 0.15 and not self._right_click_fired:
                self._right_click()
                self._right_click_fired = True
                return "Right Click"
            return "Right click pending"

        if self._right_pinch_started:
            self._right_pinch_started = 0.0
            self._right_click_fired = False

        if full_hand:
            if self._zoom_span is None:
                self._zoom_span = hand.span
                return "Zoom ready"
            delta = hand.span - self._zoom_span
            if abs(delta) > 0.035 and now - self._zoom_cooldown > 0.22:
                self._zoom(1 if delta > 0 else -1)
                self._zoom_span = hand.span
                self._zoom_cooldown = now
                self._state = ActionState.ZOOMING
                return "Zooming"
            return "Zoom ready"
        self._zoom_span = None

        if two_fingers:
            if self._scroll_anchor is None:
                self._scroll_anchor = hand.palm
                return "Scrolling ready"
            dx = hand.palm[0] - self._scroll_anchor[0]
            dy = hand.palm[1] - self._scroll_anchor[1]
            if now - self._scroll_cooldown > 0.32:
                if abs(dy) > 0.075 and abs(dy) > abs(dx) * 1.25:
                    self._scroll(-5 if dy < 0 else 5)
                    self._scroll_cooldown = now
                    self._scroll_anchor = hand.palm
                    self._state = ActionState.SCROLLING
                    return "Scroll"
                if abs(dx) > 0.085 and abs(dx) > abs(dy) * 1.15:
                    self._browser_nav("forward" if dx > 0 else "back")
                    self._scroll_cooldown = now
                    self._scroll_anchor = hand.palm
                    self._state = ActionState.SCROLLING
                    return "Navigation"
            return "Scrolling ready"
        self._scroll_anchor = None
        self._state = ActionState.IDLE
        return "Cursor Active"

    def _reset_action_state(self, release_drag: bool = True) -> None:
        if release_drag and self._drag_down:
            self._up()
            self._drag_down = False
        self._left_pinch_started = 0.0
        self._right_pinch_started = 0.0
        self._left_click_fired = False
        self._right_click_fired = False
        self._scroll_anchor = None
        self._zoom_span = None
        self._state = ActionState.IDLE

    def _position(self) -> tuple[int, int]:
        if self._backend == "pyautogui":
            pos = self._pyautogui.position()
            return int(pos.x), int(pos.y)
        x, y = self._mouse.position
        return int(x), int(y)

    def _click(self) -> None:
        if self._backend == "pyautogui":
            self._pyautogui.click()
        else:
            self._mouse.click(self._left_button)

    def _double_click(self) -> None:
        if self._backend == "pyautogui":
            self._pyautogui.doubleClick()
        else:
            self._mouse.click(self._left_button, 2)

    def _right_click(self) -> None:
        if self._backend == "pyautogui":
            self._pyautogui.rightClick()
        else:
            self._mouse.click(self._right_button)

    def _down(self) -> None:
        if self._backend == "pyautogui":
            self._pyautogui.mouseDown()
        else:
            self._mouse.press(self._left_button)

    def _up(self) -> None:
        if self._backend == "pyautogui":
            self._pyautogui.mouseUp()
        else:
            self._mouse.release(self._left_button)

    def _scroll(self, amount: int) -> None:
        if self._backend == "pyautogui":
            self._pyautogui.scroll(amount)
        else:
            self._mouse.scroll(0, amount)

    def _zoom(self, amount: int) -> None:
        if self._backend == "pyautogui":
            self._pyautogui.keyDown("ctrl")
            self._pyautogui.scroll(amount * 4)
            self._pyautogui.keyUp("ctrl")

    def _browser_nav(self, direction: str) -> None:
        if self._backend == "pyautogui":
            self._pyautogui.hotkey("alt", "right" if direction == "forward" else "left")
