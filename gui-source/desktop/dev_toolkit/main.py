# -*- coding: utf-8 -*-
"""Запуск лаунчера: `python desktop/dev_toolkit/main.py`."""
from __future__ import annotations

import json
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_DESKTOP = _HERE.parent
_KITS = _HERE.parents[1] / "kits"
for path in (str(_HERE), str(_DESKTOP), str(_KITS)):
    if path not in sys.path:
        sys.path.insert(0, path)

from kr_state import theme_name  # noqa: E402,F401  (тема одна на все тулзы)


def setup_theme(app, theme: str = "dark") -> None:
    """Тема как в KR QTS и [KR] Project Builder: выбранная, акцент DayZ, быстрые значки."""
    from qfluentwidgets import Theme, setTheme, setThemeColor

    from qts_ui import fasticons, nowheel, theme_sync, tokens

    setTheme({"auto": Theme.AUTO, "light": Theme.LIGHT, "dark": Theme.DARK}[theme])
    setThemeColor(tokens.ACCENT)
    # до первого окна: библиотека разбирает svg значков заново на каждый кадр
    fasticons.install()
    # колесо листает, а не правит значения под курсором
    nowheel.install(app)
    # тема — за общим выбором: сменили в DevToolkit — окно перекрашивается сразу
    theme_sync.follow(app)


def main() -> int:
    from PySide6.QtWidgets import QApplication

    from window import LauncherWindow

    app = QApplication(sys.argv)
    setup_theme(app, theme_name())
    window = LauncherWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
