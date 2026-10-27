# -*- coding: utf-8 -*-
"""Колонки таблицы делят её ширину по долям.

Заказ юзера 27.10.2026 (Project Builder, список PBO): ширину колонок можно
менять мышью, при изменении размера окна колонки меняются пропорционально,
а выставленное человеком помнится между запусками.

Граница между колонками работает как разделитель: что одна колонка взяла,
то соседняя отдала. Сумма ширин всегда равна ширине таблицы — горизонтальной
прокрутки нет, и последняя колонка не уезжает за край.
"""
from __future__ import annotations

from typing import List, Optional, Sequence

from PySide6.QtCore import QEvent, QObject, Signal
from PySide6.QtWidgets import QHeaderView, QTableView

#: уже нельзя: заголовок перестаёт читаться
MIN_W = 56


def _shares(values: Optional[Sequence[float]], count: int) -> Optional[List[float]]:
    """Доли, приведённые к сумме 1, или None, если сохранённое не подходит таблице."""
    if not values or len(values) != count:
        return None
    try:
        nums = [float(v) for v in values]
    except (TypeError, ValueError):
        return None
    total = sum(nums)
    if total <= 0 or any(v <= 0 for v in nums):
        return None
    return [v / total for v in nums]


class ProportionalColumns(QObject):
    #: доли после правки человеком — сохранить
    changed = Signal(list)

    def __init__(self, table: QTableView, defaults: Sequence[float],
                 saved: Optional[Sequence[float]] = None):
        super().__init__(table)
        self.table = table
        self.header = table.horizontalHeader()
        count = self.header.count()
        self.shares = _shares(saved, count) or _shares(defaults, count)
        self.header.setStretchLastSection(False)
        self.header.setMinimumSectionSize(MIN_W)
        for index in range(count):
            self.header.setSectionResizeMode(index, QHeaderView.Interactive)
        self._applying = False
        self.header.sectionResized.connect(self._on_resized)
        table.viewport().installEventFilter(self)
        self.apply()

    def eventFilter(self, obj, event):            # имя метода задаёт Qt
        if obj is self.table.viewport() and event.type() == QEvent.Resize:
            self.apply()
        return False

    def widths(self) -> List[int]:
        return [self.header.sectionSize(i) for i in range(self.header.count())]

    def apply(self) -> None:
        """Ширины по долям под текущую ширину таблицы; остаток округления — последней."""
        total = self.table.viewport().width()
        if total <= 0:
            return
        widths = [max(MIN_W, int(total * share)) for share in self.shares]
        widths[-1] = max(MIN_W, total - sum(widths[:-1]))
        self._set(widths)

    def _set(self, widths: Sequence[int]) -> None:
        self._applying = True
        try:
            for index, width in enumerate(widths):
                if self.header.sectionSize(index) != width:
                    self.header.resizeSection(index, width)
        finally:
            self._applying = False

    def _on_resized(self, index: int, old: int, new: int) -> None:
        if self._applying:
            return
        widths = self.widths()
        # соседняя справа отдаёт или забирает разницу; у последней колонки — левая
        other = index + 1 if index + 1 < len(widths) else index - 1
        if other < 0:
            return
        widths[other] -= new - old
        if widths[other] < MIN_W:
            widths[index] -= MIN_W - widths[other]          # дальше соседа не ужать
            widths[other] = MIN_W
        self._set(widths)
        total = sum(widths)
        self.shares = [w / total for w in widths]
        self.changed.emit(list(self.shares))
