# -*- coding: utf-8 -*-
"""Запуск окна массовой тулзы: `python desktop/batch_tools/main.py textures|models|debin [ПУТЬ…]`.

Пути после имени тулзы добавляются во входы окна — так её зовёт проводник и
«Отправить».
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import List, Optional

_HERE = Path(__file__).resolve().parent
_DESKTOP = _HERE.parent
_KITS = _HERE.parents[1] / "kits"
for path in (str(_HERE), str(_DESKTOP), str(_KITS)):
    if path not in sys.path:
        sys.path.insert(0, path)

from kr_state import theme_name  # noqa: E402  (тема одна на все тулзы)

#: подкоманда → ключ описания
BY_CLI = {"textures": "texture_converter", "models": "model_converter", "debin": "debinarizer",
          "pbo": "pbo_unpacker", "anm": "anm_converter"}


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


def main(cli: str, paths: Optional[List[str]] = None) -> int:
    from PySide6.QtWidgets import QApplication

    # явно, а не по имени из описания: сборщик exe видит только явные импорты,
    # а киты целиком окну не нужны — работу делает командная строка
    from batch_kit import anm_version, debin_version, model_version, pbo_version, texture_version
    from spec import SPECS
    from store import Store
    from window import BatchWindow

    spec = SPECS[BY_CLI[cli]]
    version = {"textures": texture_version, "models": model_version, "debin": debin_version,
               "pbo": pbo_version, "anm": anm_version}[cli]
    app = QApplication(sys.argv[:1])
    setup_theme(app, theme_name())
    window = BatchWindow(spec, Store(spec.key, spec.defaults()), version.NAME, version.VERSION)
    if paths:
        window.add_inputs(paths)
    window.show()
    # обновления: проверка в фоне, одно окно на все новые версии; устаревшая — предупреждение
    from qts_ui import updates_ui
    updates_ui.watch(window, spec.exe)
    return app.exec()


if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] not in BY_CLI:
        sys.exit("какая тулза: %s" % ", ".join(BY_CLI))
    raise SystemExit(main(sys.argv[1], sys.argv[2:]))
