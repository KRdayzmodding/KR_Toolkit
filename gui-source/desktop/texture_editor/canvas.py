# -*- coding: utf-8 -*-
"""Холст: показ текстуры с зумом, панорамой и отсчётом под курсором.

Отдельно от окна, потому что это единственное место со своей отрисовкой, и
смешивать его с раскладкой и меню незачем.

Выше стопроцентного увеличения тексели рисуются квадратами, без сглаживания:
во вьюере текстур смотрят на конкретный тексель, и интерполяция скрыла бы
ровно то, ради чего открыли файл. Ниже ста процентов, наоборот, сглаживаем —
иначе мелкие детали мерцают при перетаскивании.
"""
from __future__ import annotations

from typing import Optional

import numpy as np
from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import (QBrush, QColor, QImage, QPainter, QPalette,
                           QPen, QPixmap)
from PySide6.QtWidgets import QWidget

#: пределы увеличения
MIN_ZOOM, MAX_ZOOM = 0.05, 64.0

#: во сколько раз меняется увеличение за один щелчок колеса
ZOOM_STEP = 1.25

#: клетка шахматки под полупрозрачным, в пикселях экрана
CHECKER = 8

#: с какого увеличения есть смысл рисовать сетку блоков DXT
GRID_FROM = 3.0

#: сторона блока DXT
BLOCK = 4


class Canvas(QWidget):
    """Показывает готовый RGBA-массив и сообщает, что под курсором."""

    hovered = Signal(int, int)      #: тексель под курсором, (-1, -1) если мимо
    scaled = Signal(float)          #: увеличение изменилось

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.StrongFocus)
        self._pixels: Optional[np.ndarray] = None
        self._image: Optional[QImage] = None
        self._zoom = 1.0
        self._origin = QPointF(0.0, 0.0)
        self._grab: Optional[QPointF] = None
        self._checker: Optional[QPixmap] = None
        self.checker = False        #: подкладывать ли шахматку вместо серого
        self.magnify = 1.0          #: во сколько раз растянуть уровень мипа
        self.show_grid = False      #: рисовать ли сетку блоков
        self.placeholder = ""

    # ---------- содержимое ----------

    def set_pixels(self, pixels: Optional[np.ndarray], keep_view: bool = False) -> None:
        self._pixels = pixels
        if pixels is None:
            self._image = None
        else:
            height, width = pixels.shape[:2]
            # QImage не копирует буфер, поэтому держим массив у себя
            self._pixels = np.ascontiguousarray(pixels)
            self._image = QImage(self._pixels.data, width, height,
                                 4 * width, QImage.Format_RGBA8888)
        if keep_view:
            self._clamp()
        else:
            self.fit()
        self.update()

    def _scale(self) -> float:
        """Во сколько раз картинка рисуется крупнее своих пикселей.

        Мелкий мип показывается растянутым до размера полной текстуры: так же
        делает TexView, и это верно для глаза — переключая уровни, смотрят,
        что стало с деталями, а не как съехала рамка.
        """
        return self._zoom * self.magnify

    def texel(self, position: QPointF) -> tuple:
        """Какой тексель под этой точкой окна."""
        if self._image is None or self._scale() <= 0:
            return (-1, -1)
        x = int((position.x() - self._origin.x()) / self._scale())
        y = int((position.y() - self._origin.y()) / self._scale())
        if 0 <= x < self._image.width() and 0 <= y < self._image.height():
            return (x, y)
        return (-1, -1)

    # ---------- увеличение ----------

    def zoom(self) -> float:
        return self._zoom

    def set_zoom(self, value: float, anchor: Optional[QPointF] = None) -> None:
        value = max(MIN_ZOOM, min(MAX_ZOOM, value))
        if self._image is None or abs(value - self._zoom) < 1e-9:
            return
        # опорная точка — верхний левый угол окна, как в TexView
        anchor = anchor if anchor is not None else QPointF(0.0, 0.0)
        before = (anchor - self._origin) / self._scale()
        self._zoom = value
        self._origin = anchor - before * self._scale()
        self._clamp()
        self.scaled.emit(self._zoom)
        self.update()

    def fit(self) -> None:
        """Вписать целиком. Больше ста процентов не растягиваем: маленькая
        текстура во весь экран выглядит обманчиво чёткой."""
        if self._image is None:
            return
        full_width = self._image.width() * self.magnify
        full_height = self._image.height() * self.magnify
        wide = self.width() / max(full_width, 1)
        tall = self.height() / max(full_height, 1)
        self._zoom = max(MIN_ZOOM, min(1.0, min(wide, tall)))
        self._corner()
        self._clamp()
        self.scaled.emit(self._zoom)
        self.update()

    def actual(self) -> None:
        self._zoom = 1.0
        self._corner()
        self._clamp()
        self.scaled.emit(self._zoom)
        self.update()

    def _corner(self) -> None:
        """Картинка прижата к верхнему левому углу, а не по центру: так же в
        TexView, и при смене увеличения ничего не разъезжается."""
        self._origin = QPointF(0.0, 0.0)

    def _clamp(self) -> None:
        """Не дать утащить картинку за край.

        Помещается в окно — приколота к левому верхнему углу и не двигается
        вовсе. Не помещается — таскать можно, но пустоты за краями не бывает:
        картинка всегда закрывает окно целиком.
        """
        if self._image is None:
            return
        scale = self._scale()
        self._origin = QPointF(
            self._limit(self._origin.x(), self._image.width() * scale, self.width()),
            self._limit(self._origin.y(), self._image.height() * scale, self.height()))

    @staticmethod
    def _limit(value: float, span: float, room: float) -> float:
        if span <= room:
            return 0.0
        return min(0.0, max(room - span, value))

    # ---------- события ----------

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self._image is None:
            return
        if event.oldSize().width() <= 0:
            self.fit()
        else:
            # окно растянули — картинка могла перестать его закрывать
            self._clamp()

    def wheelEvent(self, event):
        if self._image is None:
            return
        steps = event.angleDelta().y() / 120.0
        if steps:
            self.set_zoom(self._zoom * (ZOOM_STEP ** steps))

    def mousePressEvent(self, event):
        if event.button() == Qt.RightButton and self._image is not None:
            self._grab = QPointF(event.position()) - self._origin
            self.setCursor(Qt.ClosedHandCursor)

    def mouseMoveEvent(self, event):
        position = QPointF(event.position())
        if self._grab is not None:
            self._origin = position - self._grab
            self._clamp()
            self.update()
        self.hovered.emit(*self.texel(position))

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.RightButton:
            self._grab = None
            self.unsetCursor()

    def leaveEvent(self, event):
        super().leaveEvent(event)
        self.hovered.emit(-1, -1)

    def mouseDoubleClickEvent(self, event):
        self.actual() if self._zoom < 1.0 else self.fit()

    # ---------- отрисовка ----------

    def _visible(self, target: QRectF) -> QRectF:
        """Та часть картинки, что попадает в окно.

        На большом увеличении прямоугольник картинки в сотни раз больше окна,
        и рисовать по нему целиком нельзя: шахматка из клеток по восемь
        пикселей давала на 64-кратном увеличении десятки миллионов заливок, и
        окно намертво вставало. Считаем только видимое.
        """
        return target.intersected(QRectF(self.rect()))

    def paintEvent(self, _event):
        painter = QPainter(self)
        palette = self.palette()
        painter.fillRect(self.rect(), palette.color(QPalette.Dark))

        if self._image is None:
            painter.setPen(palette.color(QPalette.Disabled, QPalette.WindowText))
            painter.drawText(self.rect(), Qt.AlignCenter | Qt.TextWordWrap,
                             self.placeholder)
            return

        scale = self._scale()
        target = QRectF(self._origin,
                        QPointF(self._origin.x() + self._image.width() * scale,
                                self._origin.y() + self._image.height() * scale))
        visible = self._visible(target)
        if visible.isEmpty():
            return
        if self.checker:
            self._checkerboard(painter, visible)
        else:
            # под прозрачным — тот же серый, что и вокруг: по умолчанию так
            # спокойнее, а шахматка включается, когда нужна именно она
            painter.fillRect(visible, palette.color(QPalette.Dark))

        painter.setRenderHint(QPainter.SmoothPixmapTransform, self._zoom < 1.0)
        # рисуем только видимый кусок исходника, а не всю картинку в огромный
        # прямоугольник: на большом увеличении это разница в сотни раз
        source = QRectF((visible.left() - target.left()) / scale,
                        (visible.top() - target.top()) / scale,
                        visible.width() / scale,
                        visible.height() / scale)
        painter.drawImage(visible, self._image, source)

        if self.show_grid and self._zoom >= GRID_FROM:
            self._grid(painter, target, visible)

        painter.setRenderHint(QPainter.SmoothPixmapTransform, False)
        painter.setPen(QPen(palette.color(QPalette.Mid), 1))
        painter.setBrush(Qt.NoBrush)
        painter.drawRect(target)

    def _checkerboard(self, painter: QPainter, area: QRectF) -> None:
        """Шахматка под прозрачным: иначе не отличить дыру от чёрного.

        Рисуется кистью с плиткой — одной заливкой, сколько бы ни было клеток.
        """
        if self._checker is None:
            self._checker = QPixmap(CHECKER * 2, CHECKER * 2)
            self._checker.fill(QColor(120, 120, 120))
            tile = QPainter(self._checker)
            dark = QColor(90, 90, 90)
            tile.fillRect(0, 0, CHECKER, CHECKER, dark)
            tile.fillRect(CHECKER, CHECKER, CHECKER, CHECKER, dark)
            tile.end()
        painter.fillRect(area, QBrush(self._checker))

    def _grid(self, painter: QPainter, target: QRectF, area: QRectF) -> None:
        """Границы блоков DXT: по ним видно, где сжатие сломало картинку.

        Линии ставятся от начала картинки, но рисуются только по видимому
        куску — иначе на большом увеличении их были бы десятки тысяч.
        """
        painter.save()
        painter.setClipRect(area)
        painter.setPen(QPen(QColor(0, 0, 0, 90), 1))
        step = BLOCK * self._scale()
        first = int((area.left() - target.left()) / step)
        x = target.left() + first * step
        while x <= area.right():
            painter.drawLine(QPointF(x, area.top()), QPointF(x, area.bottom()))
            x += step
        first = int((area.top() - target.top()) / step)
        y = target.top() + first * step
        while y <= area.bottom():
            painter.drawLine(QPointF(area.left(), y), QPointF(area.right(), y))
            y += step
        painter.restore()
