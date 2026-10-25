# -*- coding: utf-8 -*-
"""Подложка блока окна: своя, не из QTS.

Замечание юзера 25.10.2026 по массовым конвертерам: «нет чёткого разделения
между областями, всё слито воедино». Список источников, настройки и таблица
лежали на одном фоне. Карточка — сплошная (настройки) или пунктирная (место,
куда перетаскивают, как «Что паковать» у Project Builder).

Рисует себя сама: стиль родителя перебивает стиль ребёнка, а цвета из
tokens берутся на каждой отрисовке — смена темы подхватывается без подписки.
"""
from __future__ import annotations

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QVBoxLayout, QWidget

from qts_ui import tokens


class Card(QWidget):
    def __init__(self, parent=None, dashed: bool = False, padding: int = tokens.SPACE_S):
        super().__init__(parent)
        self.dashed = dashed
        self.box = QVBoxLayout(self)
        self.box.setContentsMargins(padding, padding, padding, padding)
        self.box.setSpacing(0)

    def paintEvent(self, e):        # имя метода задаёт Qt
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        if self.dashed:
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(QPen(QColor(tokens.color("divider")), 1, Qt.PenStyle.DashLine))
        else:
            painter.setBrush(QColor(tokens.color("card")))
            painter.setPen(QPen(QColor(tokens.color("border")), 1))
        painter.drawRoundedRect(rect, tokens.RADIUS_CARD, tokens.RADIUS_CARD)
