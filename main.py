from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication, QMessageBox

from config.settings import SettingsStore
from ui.main_window import MainWindow


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("PalmShift")
    app.setQuitOnLastWindowClosed(False)

    try:
        settings = SettingsStore()
        window = MainWindow(settings)
        window.show()
        return app.exec()
    except Exception as exc:
        QMessageBox.critical(None, "PalmShift", f"PalmShift could not start:\n{exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
