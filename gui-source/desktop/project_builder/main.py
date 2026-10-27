# -*- coding: utf-8 -*-
"""Запуск окна [KR] Project Builder: `python desktop/project_builder/main.py`."""
from __future__ import annotations

import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_DESKTOP = _HERE.parent
_KITS = _HERE.parents[1] / "kits"
for path in (str(_HERE), str(_DESKTOP), str(_KITS)):
    if path not in sys.path:
        sys.path.insert(0, path)


def setup_theme(app, theme: str = "dark") -> None:
    """Тема как в KR QTS: выбранная (системная/светлая/тёмная), акцент DayZ, быстрые значки."""
    from qfluentwidgets import setThemeColor

    from dialogs import apply_theme
    from qts_ui import fasticons, nowheel, theme_sync, tokens

    apply_theme(theme)
    setThemeColor(tokens.ACCENT)
    # до первого окна: библиотека разбирает svg значков заново на каждый кадр
    fasticons.install()
    # колесо листает, а не правит числа под курсором
    nowheel.install(app)
    # тема — за общим выбором: сменили в DevToolkit — окно перекрашивается сразу
    theme_sync.follow(app)


def main() -> int:
    from PySide6.QtWidgets import QApplication

    from store import Store
    from window import MainWindow

    from dialogs import theme_name
    from worker import catalog, settings_path

    # первый вызов командной строки: она же переносит прежние имена файлов
    # настроек (24.10.2026) — до того, как окно их прочтёт
    catalog()
    app = QApplication(sys.argv)
    store = Store()
    setup_theme(app, theme_name(store))           # тема — до первого окна
    if "--settings" in sys.argv[1:]:
        # только окно настроек (заказ QTS 23.10.2026): QTS вешает его на свою кнопку,
        # а не рисует копию; правки — в тот же общий project_builder.json
        from dialogs import SettingsDialog
        SettingsDialog(settings_path(), store=store).exec()   # пишется на каждое изменение
        return 0
    window = MainWindow(store)
    window.show()
    # обновления: проверка в фоне, одно окно на все новые версии; устаревшая — предупреждение
    from qts_ui import updates_ui
    updates_ui.watch(window, "ProjectBuilder")
    return app.exec()


# пул процессов сборки на Windows перезапускает главный модуль в каждом
# процессе — окно должно подниматься только здесь
if __name__ == "__main__":
    raise SystemExit(main())
