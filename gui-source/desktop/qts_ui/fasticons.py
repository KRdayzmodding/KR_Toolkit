# Скопировано из KR_ServerManager/ui/fasticons.py (рабочая копия на 22.10.2026, последний коммит QTS deba8ad) — общий визуальный язык с KR QTS.
# Править синхронно с оригиналом, а не молча здесь.
"""Кэш разбора SVG у иконок библиотеки — по одному разбору на иконку, а не на кадр.

qfluentwidgets рисует каждую иконку так: берёт svg-файл, разбирает его XML,
подставляет цвет темы, собирает строку обратно и скармливает её новому
QSvgRenderer. Всё это — на каждый paintEvent каждой кнопки, вкладки и
выпадающего списка. В окне их два десятка, и на один кадр приходилось около
340 разборов svg.

Замерено на главном окне 1400×900 с раскрытым списком модов: 17,8 мс на кадр
против 13,8 мс с кэшем — почти четверть. На мониторе 165 Гц бюджет кадра
6 мс, так что эти миллисекунды и есть разница между «тянется плавно» и
«подёргивается».

Кэшировать можно, потому что обе функции чистые: из одного пути и одних
атрибутов получается одна и та же разметка, из одной разметки — один и тот
же рисовальщик. Файлы иконок внутри сборки не меняются, а смена темы меняет
атрибуты, то есть и ключ.

Подмена чужих функций — вещь неприятная, но здесь она точечная: обе функции
публичные, их поведение задокументировано, а своего способа кэшировать
отрисовку библиотека не даёт.
"""
from __future__ import annotations

import sys
from functools import lru_cache

from PySide6.QtCore import QByteArray, QRectF
from PySide6.QtSvg import QSvgRenderer

_installed = False


def install() -> None:
    """Ставит кэш. Второй вызов ничего не делает."""
    global _installed
    if _installed:
        return
    from qfluentwidgets.common import icon as lib

    original_write = lib.writeSvg

    @lru_cache(maxsize=1024)
    def _write(path: str, indexes: tuple | None, items: tuple) -> str:
        return original_write(path, list(indexes) if indexes else None, **dict(items))

    def write_svg(iconPath, indexes=None, **attributes):   # имя задаёт библиотека
        try:
            return _write(iconPath, tuple(indexes) if indexes else None,
                          tuple(sorted(attributes.items())))
        except TypeError:
            # нехешируемый аргумент — отвечаем как раньше, без кэша
            return original_write(iconPath, indexes, **attributes)

    @lru_cache(maxsize=1024)
    def _renderer(key):
        return QSvgRenderer(QByteArray(key) if isinstance(key, bytes) else key)

    def draw_svg_icon(icon, painter, rect):                # имя задаёт библиотека
        key = bytes(icon.data()) if isinstance(icon, QByteArray) else icon
        if not isinstance(key, (bytes, str)):
            lib_draw(icon, painter, rect)                  # что-то незнакомое
            return
        _renderer(key).render(painter, QRectF(rect))

    lib_draw = lib.drawSvgIcon
    lib.writeSvg = write_svg
    lib.drawSvgIcon = draw_svg_icon
    # модули библиотеки импортировали эти функции по имени — подменяем и у них,
    # иначе половина виджетов продолжит звать старые
    for module in list(sys.modules.values()):
        if not getattr(module, "__name__", "").startswith("qfluentwidgets"):
            continue
        if getattr(module, "drawSvgIcon", None) is lib_draw:
            module.drawSvgIcon = draw_svg_icon
        if getattr(module, "writeSvg", None) is original_write:
            module.writeSvg = write_svg
    _installed = True
