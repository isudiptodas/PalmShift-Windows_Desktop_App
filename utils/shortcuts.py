from __future__ import annotations

from PySide6.QtCore import QObject, Signal


class ShortcutManager(QObject):
    toggle_control_requested = Signal()
    toggle_aura_requested = Signal()
    aura_effect_requested = Signal(str)
    stop_requested = Signal()
    error = Signal(str)

    def __init__(self, shortcuts: dict[str, str]) -> None:
        super().__init__()
        self.shortcuts = shortcuts
        self._keyboard = None
        self._registered: list[str] = []

    def start(self) -> None:
        try:
            import keyboard

            self._keyboard = keyboard
            self._add("toggle_control", self.toggle_control_requested.emit)
            self._add("toggle_aura", self.toggle_aura_requested.emit)
            self._add("aura_water", lambda: self.aura_effect_requested.emit("Water"))
            self._add("aura_neon", lambda: self.aura_effect_requested.emit("Neon"))
            self._add("aura_ink", lambda: self.aura_effect_requested.emit("Ink"))
            self._add("aura_draw", lambda: self.aura_effect_requested.emit("Draw"))
            self._add("stop_active", self.stop_requested.emit)
        except Exception:
            self._keyboard = None
            self._start_pynput_fallback()

    def stop(self) -> None:
        if self._keyboard:
            for shortcut in self._registered:
                try:
                    self._keyboard.remove_hotkey(shortcut)
                except Exception:
                    pass
            self._registered.clear()
        if hasattr(self, "_listener") and self._listener:
            self._listener.stop()
            self._listener = None

    def _add(self, action: str, callback) -> None:
        shortcut = self.shortcuts.get(action)
        if not shortcut or not self._keyboard:
            return
        self._keyboard.add_hotkey(shortcut, callback)
        self._registered.append(shortcut)

    def _start_pynput_fallback(self) -> None:
        try:
            from pynput import keyboard as pynput_keyboard

            mapping = {
                self.shortcuts.get("toggle_control", "ctrl+alt+c"): self.toggle_control_requested.emit,
                self.shortcuts.get("toggle_aura", "ctrl+alt+a"): self.toggle_aura_requested.emit,
                self.shortcuts.get("aura_water", "ctrl+alt+w"): lambda: self.aura_effect_requested.emit("Water"),
                self.shortcuts.get("aura_neon", "ctrl+alt+n"): lambda: self.aura_effect_requested.emit("Neon"),
                self.shortcuts.get("aura_ink", "ctrl+alt+i"): lambda: self.aura_effect_requested.emit("Ink"),
                self.shortcuts.get("aura_draw", "ctrl+alt+d"): lambda: self.aura_effect_requested.emit("Draw"),
                self.shortcuts.get("stop_active", "ctrl+alt+x"): self.stop_requested.emit,
            }
            hotkeys = {
                self._pynput_combo(combo): callback
                for combo, callback in mapping.items()
                if combo
            }
            self._listener = pynput_keyboard.GlobalHotKeys(hotkeys)
            self._listener.start()
        except Exception:
            self.error.emit(
                "Global shortcuts could not be registered. You can still use PalmShift from the app window."
            )

    @staticmethod
    def _pynput_combo(combo: str) -> str:
        parts = []
        for part in combo.lower().split("+"):
            part = part.strip()
            if part in {"ctrl", "control"}:
                parts.append("<ctrl>")
            elif part == "alt":
                parts.append("<alt>")
            elif part == "shift":
                parts.append("<shift>")
            else:
                parts.append(part)
        return "+".join(parts)
