# -*- coding: utf-8 -*-
"""Иконки тулз в окне и на панели задач — как у KR QTS (ui/theme.py).

Силуэт один (`desktop/icons/<имя>.png`, белый на прозрачном), а цвет — по
месту:

* в шапке окна фон наш и известен точно — силуэт под тему: светлый на тёмной,
  инвертированный на светлой;
* снаружи (панель задач, Alt+Tab, проводник) фон чужой — ровный серый 128,
  читается и на светлом, и на тёмном (замер QTS: контраст 3.6–4.1 к одному).

Уменьшение — половинками: билинейное сжатие 256 → 16 разом мылит картинку.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Dict, Tuple

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QIcon, QImage, QPainter, QPixmap

#: DevToolkit — знак и половина шестерёнки (юзер 24.10.2026); у каждой тулзы — знак и половина
#: значка её карточки, файл по имени exe без _GUI (юзер 25.10.2026); TOOL — шестерёнка про запас
DEV_TOOLKIT, TOOL = "dev_toolkit", "tool"
#: командные exe — окно консоли в цвете, как у CMD: не силуэт, не перекрашивается
CLI = "cli"
COLORED = {CLI}
#: размеры, которые реально запрашиваются: 16 — трей и системные места, 18 —
#: шапка FluentWidget, 32 — панель задач, 48/256 — проводник и Alt+Tab
SIZES = (16, 18, 20, 24, 32, 48, 64, 128, 256)
#: серый вне окна — тот же, что у QTS
OUTSIDE_GREY = 128

_cache: Dict[Tuple[str, str], QIcon] = {}


def icons_dir() -> Path:
    """Папка с силуэтами: в собранном exe — `runtime\\icons`, из исходников — рядом."""
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent)) / "icons"
    return Path(__file__).resolve().parent / "icons"


def _source(name: str) -> QPixmap:
    return QPixmap(str(icons_dir() / ("%s.png" % name)))


def _downscale(src: QPixmap, size: int) -> QPixmap:
    pm = src
    mode = Qt.TransformationMode.SmoothTransformation
    ratio = Qt.AspectRatioMode.KeepAspectRatio
    while pm.width() // 2 > size:
        pm = pm.scaled(pm.width() // 2, pm.height() // 2, ratio, mode)
    return pm.scaled(size, size, ratio, mode)


def _tinted(src: QPixmap, value: int) -> QPixmap:
    """Перекрасить силуэт в ровный серый; форма и полутона краёв — через альфу."""
    img = src.toImage().convertToFormat(QImage.Format.Format_ARGB32)
    p = QPainter(img)
    p.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceIn)
    p.fillRect(img.rect(), QColor(value, value, value))
    p.end()
    return QPixmap.fromImage(img)


def _build(src: QPixmap) -> QIcon:
    icon = QIcon()
    for size in SIZES:
        if size < src.width():
            icon.addPixmap(_downscale(src, size))
    icon.addPixmap(src)
    return icon


def available(name: str) -> bool:
    return (icons_dir() / ("%s.png" % name)).is_file()


def exe_icon(exe: str, windowed: bool) -> str:
    """Какая иконка у exe: командный — консоль, оконный — своя тулзы, DevToolkit — знак с шестерёнкой."""
    if not windowed:
        return CLI
    group = exe[:-4] if exe.endswith("_GUI") else exe
    if group == "DevToolkit":
        return DEV_TOOLKIT
    return group if available(group) else TOOL


def app_icon(name: str, dark: bool) -> QIcon:
    """Иконка для шапки окна под тему; пустая, если файла нет."""
    key = (name, "dark" if dark else "light")
    if key not in _cache:
        src = _source(name)
        if src.isNull():
            return QIcon()
        # силуэт монохромный: инверсия уровней серого = тот же знак тёмным
        _cache[key] = _build(src if dark or name in COLORED else _tinted(src, 0))
    return _cache[key]


def outside_icon(name: str) -> QIcon:
    """Иконка вне окна: панель задач, «Пуск», Alt+Tab — один серый на все фоны."""
    key = (name, "outside")
    if key not in _cache:
        src = _source(name)
        if src.isNull():
            return QIcon()
        _cache[key] = _build(src if name in COLORED else _tinted(src, OUTSIDE_GREY))
    return _cache[key]


def ico_file(name: str, target: Path) -> Path:
    """Многоразмерный .ico для exe — серым, как снаружи окна (проводник, ярлыки)."""
    from PIL import Image
    src = Image.open(icons_dir() / ("%s.png" % name)).convert("RGBA")
    if name in COLORED:
        grey = src
    else:
        grey = Image.new("RGBA", src.size, (OUTSIDE_GREY, OUTSIDE_GREY, OUTSIDE_GREY, 0))
        grey.putalpha(src.getchannel("A"))
    target.parent.mkdir(parents=True, exist_ok=True)
    grey.save(target, sizes=[(s, s) for s in (16, 20, 24, 32, 48, 64, 128, 256)])
    return target
