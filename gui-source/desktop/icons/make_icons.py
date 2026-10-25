# -*- coding: utf-8 -*-
r"""Иконки тулз: `python desktop/icons/make_icons.py` → dev_toolkit.png, tool.png, <Тулза>.png, cli.png.

Заказ юзера 24.10.2026: иконки как у KR QTS. У QTS `icon.tga` — белый плоский
силуэт 256x256: слева наш знак, справа стойка сервера. Здесь так же:

* DevToolkit — слева тот же знак, справа половина шестерёнки (кит, а не сервер);
* остальные тулзы — шестерёнка.

Знак (`kr_emblem.png`) вырезан из `icon.tga` QTS: он занимает столбцы 7–113,
стойка — 118–239, между ними пустая полоса, так что разрез чистый. Шестерёнка
рисуется здесь, со сверхвыборкой, чтобы края были гладкими.

Своя иконка у каждого окна (юзер 25.10.2026, вариант D2: на панели задач
отличался только лаунчер): слева та же морда, справа — правая половина значка
карточки тулзы в лаунчере (SVG qfluentwidgets), разрезанного по центру, с тем
же зазором от морды, что у шестерёнки DevToolkit. Командным exe — одна иконка
консоли в цвете, как у CMD (cli.png, kr_icons её не перекрашивает).

Цвет силуэта — белый 255, как у QTS (97% пикселей знака — ровно белые); под тему (шапка окна) и в серый для
панели задач и проводника его перекрашивает kr_icons при запуске и сборщик
.ico, так что здесь лежит только форма.
"""
from __future__ import annotations

import math
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

HERE = Path(__file__).resolve().parent
SIZE = 256
#: сверхвыборка шестерёнки
SUPER = 8
INK = 255
#: где кончается знак (по icon.tga QTS)
EMBLEM_RIGHT = 114


def gear(cx: float, cy: float, r_out: float, r_root: float, r_hole: float, teeth: int,
         half: bool = False) -> np.ndarray:
    """Маска шестерёнки 256x256 (0..255). ``half`` — только правая половина."""
    k = SUPER
    big = Image.new("L", (SIZE * k, SIZE * k), 0)
    draw = ImageDraw.Draw(big)
    points = []
    steps = teeth * 4
    for i in range(steps):
        angle = 2 * math.pi * i / steps - math.pi / 2
        phase = i % 4
        radius = r_out if phase in (1, 2) else r_root
        # вершина зуба уже основания — зуб трапецией, а не прямоугольником
        skew = (2 * math.pi / steps) * (0.18 if phase == 1 else -0.18 if phase == 2 else 0.0)
        points.append(((cx + radius * math.cos(angle + skew)) * k,
                       (cy + radius * math.sin(angle + skew)) * k))
    draw.polygon(points, fill=255)
    draw.ellipse([(cx - r_hole) * k, (cy - r_hole) * k, (cx + r_hole) * k, (cy + r_hole) * k], fill=0)
    if half:
        draw.rectangle([0, 0, cx * k, SIZE * k], fill=0)
    return np.array(big.resize((SIZE, SIZE), Image.LANCZOS))


def silhouette(mask: np.ndarray) -> Image.Image:
    out = np.zeros((SIZE, SIZE, 4), np.uint8)
    out[..., :3] = INK
    out[..., 3] = mask
    return Image.fromarray(out)


#: тулза (имя exe без _GUI) → значок её карточки в лаунчере (dev_toolkit/tools.py)
GLYPHS = {"ProjectBuilder": "SEND", "TextureEditor": "PALETTE", "ImagesetEditor": "TILES",
          "TextureConverter": "PHOTO", "ModelConverter": "IOT", "DeBinarizer": "CODE",
          "PboUnpacker": "ZIP_FOLDER", "AnmConverter": "MOVIE", "SoundConverter": "MUSIC",
          "AddonSigner": "CERTIFICATE"}
#: откуда начинается половина значка: зазор от морды ~12 px, как у шестерёнки DevToolkit
HALF_X = 126
#: поле вокруг значка карточки при отрисовке 256x256
GLYPH_PAD = 16


def _qt():
    import os
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


def _qimage_alpha(img) -> np.ndarray:
    from PySide6.QtGui import QImage
    img = img.convertToFormat(QImage.Format.Format_RGBA8888)
    data = np.frombuffer(bytes(img.constBits()), np.uint8).reshape(img.height(), img.width(), 4)
    return data[..., 3].copy()


def glyph_mask(name: str) -> np.ndarray:
    """Значок карточки (SVG qfluentwidgets) белым силуэтом 256x256 — альфа."""
    from PySide6.QtCore import QRectF, Qt
    from PySide6.QtGui import QImage, QPainter
    from PySide6.QtSvg import QSvgRenderer
    from qfluentwidgets import FluentIcon, Theme
    img = QImage(SIZE, SIZE, QImage.Format.Format_ARGB32_Premultiplied)
    img.fill(Qt.GlobalColor.transparent)
    painter = QPainter(img)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    QSvgRenderer(getattr(FluentIcon, name).path(Theme.DARK)).render(
        painter, QRectF(GLYPH_PAD, GLYPH_PAD, SIZE - 2 * GLYPH_PAD, SIZE - 2 * GLYPH_PAD))
    painter.end()
    return _qimage_alpha(img)


def tool_mask(emblem: np.ndarray, name: str) -> np.ndarray:
    """Морда слева, правая половина значка справа."""
    out = emblem.copy()
    half = glyph_mask(name)[:, SIZE // 2:]
    out[:, HALF_X:HALF_X + half.shape[1]] = np.maximum(out[:, HALF_X:HALF_X + half.shape[1]],
                                                     half[:, :SIZE - HALF_X])
    return out


def cli_icon() -> Image.Image:
    """Командные exe: окно консоли в цвете, как у CMD — чёрное окно, светлая полоса, «>_»."""
    k = SUPER
    big = Image.new("RGBA", (SIZE * k, SIZE * k), (0, 0, 0, 0))
    d = ImageDraw.Draw(big)
    d.rounded_rectangle([12 * k, 28 * k, (SIZE - 12) * k, (SIZE - 28) * k], radius=22 * k,
                        fill=(12, 12, 12, 255), outline=(150, 150, 150, 255), width=6 * k)
    d.rounded_rectangle([15 * k, 31 * k, (SIZE - 15) * k, 71 * k], radius=18 * k, fill=(200, 200, 200, 255))
    d.rectangle([15 * k, 55 * k, (SIZE - 15) * k, 71 * k], fill=(200, 200, 200, 255))
    ink = (235, 235, 235, 255)
    d.line([(56 * k, 110 * k), (100 * k, 145 * k), (56 * k, 180 * k)], fill=ink, width=18 * k, joint="curve")
    for x, y in ((56, 110), (100, 145), (56, 180)):
        d.ellipse([(x - 9) * k, (y - 9) * k, (x + 9) * k, (y + 9) * k], fill=ink)
    d.line([(120 * k, 185 * k), (190 * k, 185 * k)], fill=ink, width=18 * k)
    for x in (120, 190):
        d.ellipse([(x - 9) * k, 176 * k, (x + 9) * k, 194 * k], fill=ink)
    return big.resize((SIZE, SIZE), Image.LANCZOS)


def main() -> None:
    emblem = np.array(Image.open(HERE / "kr_emblem.png").convert("RGBA"))[..., 3]
    half = gear(124, 128, 118, 96, 44, 10, half=True)
    silhouette(np.maximum(emblem, half)).save(HERE / "dev_toolkit.png")
    silhouette(gear(128, 128, 120, 98, 46, 10)).save(HERE / "tool.png")
    _qt()
    for name, glyph in GLYPHS.items():
        silhouette(tool_mask(emblem, glyph)).save(HERE / ("%s.png" % name))
    cli_icon().save(HERE / "cli.png")
    print("готово:", ", ".join(["dev_toolkit.png", "tool.png", "cli.png"] + ["%s.png" % n for n in GLYPHS]))


if __name__ == "__main__":
    main()
