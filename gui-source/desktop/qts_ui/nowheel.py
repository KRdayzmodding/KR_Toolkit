# Скопировано из KR_ServerManager/ui/nowheel.py (рабочая копия на 22.10.2026, последний коммит QTS deba8ad) — общий визуальный язык с KR QTS.
# Править синхронно с оригиналом, а не молча здесь.
"""Правила колеса мыши: что листается и что не листается.

Первое: колесо листает страницу, а не правит числа под курсором.
Второе: список, докрутившийся до края, не передаёт колесо странице под собой.


Поля с числами по умолчанию перехватывают колесо и меняют значение. В длинных
окнах — настройках, редакторе пресета — это ловушка: человек листает список,
курсор проезжает над полем, и порт или интервал перезапуска тихо меняются. Тем
более что менялись бы они молча: ни подтверждения, ни следа.

Поэтому колесо у таких полей отбираем и отдаём наверх, тому, кто листает.
Фильтр ставится один раз на всё приложение: так под правило попадают и поля,
которые появятся позже, и не нужно помнить про него в каждом окне.

С клавиатуры значения по-прежнему меняются стрелками, и стрелочки самого поля
никуда не делись.
"""
from __future__ import annotations

import time

from PySide6.QtCore import QEvent, QObject, QPoint
from PySide6.QtWidgets import QAbstractScrollArea, QAbstractSpinBox, QApplication


class WheelGuard(QObject):
    """Съедает колесо у числовых полей и отдаёт его области прокрутки."""

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:
        if event.type() != QEvent.Type.Wheel or not isinstance(obj, QAbstractSpinBox):
            return False
        # Просто «не принять» событие мало: обычное всплытие к родителю
        # работает лишь на первой доставке, а мы её как раз и перехватили.
        # Поэтому ищем ближайшую прокручиваемую область и отдаём колесо ей
        # напрямую — в её viewport, потому что именно он листает содержимое.
        area = _scroll_area(obj)
        if area is not None:
            QApplication.sendEvent(area.viewport(), event)
        return True


# Насколько раньше упора список передаёт ход странице. Щелчок колеса: ждать
# самого упора — значит показать человеку остановку и новый старт. Последний
# щелчок при этом двигает обоих, и список всё же доезжает до конца.
_NEAR = 110

# Сколько страница не слушается колеса после того, как довела край карточки до
# экрана. Пока крутишь, курсор стоит на месте, а содержимое под ним уезжает —
# и там, где был список, оказывается страница. Следующий щелчок листал бы уже
# её, хотя рука делает то же самое движение. Треть секунды — пауза, за которую
# человек успевает увидеть, что докрутка кончилась.
_HOLD_MS = 350


class ChainGuard(QObject):
    """Колесо над списком: страница подхватывает движение, но не убегает.

    Правило одно на два случая.

    Список ещё не докручен, но до края ему осталось меньше щелчка — остаток
    отдаём списку, а хвост щелчка уже уходит странице. Без этого страница
    трогалась ровно в тот миг, когда список упёрся, и это читалось как рывок.

    Список докручен — страница едет дальше, но ровно до края карточки, в
    которой он лежит: вверх до шапки (там кнопка сворачивания), вниз до низа
    (там ручка размера и подсказка). Дошли — стоим: рука делает одно движение,
    и уносить её в другое место нечестно.
    """

    _busy = False           # сами же и отдали событие странице — не ловим его снова
    _hold_until = 0.0       # до какого момента страница не слушается колеса
    _hold_down = None       # в какую сторону молчит

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:
        if event.type() != QEvent.Type.Wheel or self._busy:
            return False
        area = _area_of_viewport(obj)
        if area is None:
            return False
        page = _outer_area(area)
        if page is not None:
            return self._hand_off(area, page, event)     # колесо пришло списку
        if not _is_page(area):
            return False        # не страница, а просто список — цеплять нечего
        if self._held(event):
            return True         # только что довели край — даём руке остановиться
        inner = _inner_area_under(event, area)
        if inner is None:
            return False        # курсор не над списком — страница едет как обычно
        return self._move_page(area, inner, event)

    # ----------------------------------------------------------------- шаги

    def _hand_off(self, inner, page, event) -> bool:
        """Список почти докручен — ход продолжает страница.

        Порог не нулевой: если ждать самого упора, страница трогается ровно в
        тот миг, когда список встал, и это читается как рывок. Полщелчка
        запаса — и движение переходит незаметно.
        """
        down = event.angleDelta().y() < 0
        bar = inner.verticalScrollBar()
        left = (bar.maximum() - bar.value()) if down else bar.value()
        if left > _NEAR:
            return False        # списку ещё есть куда ехать — не вмешиваемся
        moved = self._move_page(page, inner, event)
        # Последние пиксели списка отдаём ему же: если забрать щелчок целиком,
        # нижние строки станут недосягаемы колесом — только полосой прокрутки.
        return False if left else moved

    def _move_page(self, page, inner, event) -> bool:
        """Отдаёт колесо странице, пока нужный край карточки не показался.

        Именно отдаёт событие, а не двигает полосу сама: страница листается
        плавно, своей анимацией, а подкрутка значением шла рывками — то самое
        подёргивание, ради которого всё и затевалось.
        """
        down = event.angleDelta().y() < 0
        anchor = _anchor_of(inner, page)
        top = anchor.mapTo(page.viewport(), QPoint(0, 0)).y()
        hidden = (top + anchor.height() - page.viewport().height()) if down else -top
        if hidden <= 0:
            self._hold(down)    # докрутили — и на время замолкаем
            return True         # край виден — дальше страницу не трогаем
        self._busy = True
        try:
            QApplication.sendEvent(page.viewport(), event)
        finally:
            self._busy = False
        # Пока страница догоняла, содержимое под курсором уехало, и следующий
        # щелчок пришёл бы уже ей. Держим паузу в ту же сторону.
        self._hold(down)
        return True


    # ----------------------------------------------------------------- пауза

    def _hold(self, down: bool) -> None:
        self._hold_until = time.monotonic() + _HOLD_MS / 1000
        self._hold_down = down

    def _held(self, event) -> bool:
        """Идёт ли пауза для этого направления. Другая сторона — не пауза:
        передумал и крутишь обратно — значит, так и надо."""
        if self._hold_down is None or time.monotonic() >= self._hold_until:
            return False
        return (event.angleDelta().y() < 0) == self._hold_down


def _outer_area(area: QAbstractScrollArea):
    """Страница, внутри которой лежит эта область. None — страницы нет.

    Страницей считаем только настоящую прокручиваемую страницу — QScrollArea
    со своим содержимым. Список сам по себе тоже область прокрутки, и внутри
    его строк живут свои виджеты: без этой проверки дерево модов оказывалось
    «страницей» для собственного содержимого.
    """
    node = area.parentWidget()
    while node is not None:
        if isinstance(node, QAbstractScrollArea) and _is_page(node):
            return node
        node = node.parentWidget()
    return None


def _is_page(area) -> bool:
    getter = getattr(area, "widget", None)
    return callable(getter) and getter() is not None


def _anchor_of(widget, page: QAbstractScrollArea):
    """Карточка, в которой лежит список. Нет такой — сам список."""
    node = widget
    while node is not None and node is not page:
        if node.property("wheelAnchor"):
            return node
        node = node.parentWidget()
    return widget


def _area_of_viewport(obj: QObject) -> QAbstractScrollArea | None:
    """Область прокрутки, чей это viewport. None — это не viewport."""
    parent = obj.parentWidget() if hasattr(obj, "parentWidget") else None
    if isinstance(parent, QAbstractScrollArea) and parent.viewport() is obj:
        return parent
    return None


def _inner_area_under(event, page: QAbstractScrollArea) -> QAbstractScrollArea | None:
    """Вложенная в page область под курсором, которой есть что листать.

    Ищем по дереву виджетов, а не через widgetAt: тот смотрит на экран и
    порядок окон, то есть отвечает по-разному в зависимости от того, что
    сейчас поверх, а нам нужен ответ про содержимое страницы.
    """
    widget = page.viewport().childAt(event.position().toPoint())
    while widget is not None and widget is not page:
        if (isinstance(widget, QAbstractScrollArea)
                and widget.verticalScrollBar().maximum() > 0):
            return widget
        widget = widget.parentWidget()
    return None


def _scroll_area(widget: QObject) -> QAbstractScrollArea | None:
    """Ближайшая прокручиваемая область выше по дереву. None — её нет."""
    parent = widget.parentWidget() if hasattr(widget, "parentWidget") else None
    while parent is not None:
        if isinstance(parent, QAbstractScrollArea):
            return parent
        parent = parent.parentWidget()
    return None


_guard: WheelGuard | None = None
_chain: ChainGuard | None = None


def install(app: QApplication) -> WheelGuard:
    """Ставит правило на всё приложение. Возвращённый объект надо держать живым."""
    global _guard, _chain
    if _guard is None:
        _guard = WheelGuard()
        app.installEventFilter(_guard)
    if _chain is None:
        _chain = ChainGuard()
        app.installEventFilter(_chain)
    return _guard
