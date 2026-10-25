# -*- coding: utf-8 -*-
"""Атлас с рамками спрайтов: просмотр, выбор и ручная правка рамки.

Текстура рисуется в системе координат RefSize, а не в своих пикселях: у @2x и у
`dayz_crosshairs` (RefSize 1024, атлас 512) это разные вещи, а рамки заданы в
RefSize. Колесо прокручивает, Ctrl+колесо — масштаб (свод правил, п. 48),
средняя кнопка — тащить атлас.

Правка рамки (юзер 23.10.2026). Одиночный щелчок — выбор (правка числами
в панели). Двойной — ручная правка выбранной рамки:
* за угол — тянутся две стороны этого угла, противоположный угол стоит;
* за середину — рамка двигается целиком;
* Shift — пропорционально (угол);
* Alt — шаг 32 пикселя;
* Ctrl — прилипание к краям соседних спрайтов и атласа, но только к соседу
  ближе 8 пикселей: прилипает то, к чему подтянули, а не ближайшее вообще.
  По X и по Y независимо — поэтому рамка встаёт и между четырьмя соседями.
  Отвели дальше 8 пикселей — прилипание отпускает.
Esc или двойной щелчок мимо — выйти из ручной правки. Весь жест — одна отмена.

Несколько спрайтов (юзер 23.10.2026): обвести мышью по пустому месту — выделить
все, кого рамка касается (с Ctrl — добавить). Выделено больше одного — тащить
любой из них сразу, без двойного щелчка: двигаются все вместе, Alt и Ctrl
работают для общей рамки группы. Щелчок по выделенному без движения — оставить
выделенным только его.
"""
from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from PySide6.QtCore import QLineF, QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QCursor, QPainter, QPen, QPixmap, QTransform
from PySide6.QtWidgets import QGraphicsPixmapItem, QGraphicsRectItem, QGraphicsScene, QGraphicsView

from qts_ui import tokens

#: шаг масштаба на щелчок колеса и пределы
ZOOM_STEP = 1.25
ZOOM_MIN, ZOOM_MAX = 0.05, 64.0
CHECKER = 8
#: ручки углов — в экранных пикселях
HANDLE = 9
#: шаг с Alt и порог прилипания с Ctrl — в пикселях атласа (RefSize).
#: Шаг 32 (юзер 23.10.2026; было 8), порог прилипания остался 8
STEP = 32
SNAP = 8

Rect = Tuple[int, int, int, int]
CORNERS = ("tl", "tr", "bl", "br")


def _checker() -> QBrush:
    """Шахматка под прозрачным — иначе прозрачное не отличить от чёрного."""
    dark = tokens.dark()
    a, b = (QColor(48, 48, 48), QColor(64, 64, 64)) if dark else (QColor(235, 235, 235), QColor(250, 250, 250))
    pix = QPixmap(CHECKER * 2, CHECKER * 2)
    pix.fill(a)
    p = QPainter(pix)
    p.fillRect(0, 0, CHECKER, CHECKER, b)
    p.fillRect(CHECKER, CHECKER, CHECKER, CHECKER, b)
    p.end()
    return QBrush(pix)


def _overlap(a0: float, a1: float, b0: float, b1: float) -> bool:
    return a0 <= b1 and b0 <= a1


def snap_axis(edges: List[float], targets: List[float]) -> Optional[float]:
    """Сдвиг, который ставит ближайший из своих краёв `edges` на чужой край `targets`,
    если между ними не больше SNAP; иначе None."""
    best = None
    for edge in edges:
        for target in targets:
            d = target - edge
            if abs(d) <= SNAP and (best is None or abs(d) < abs(best)):
                best = d
    return best


def drag_rect(start: Rect, mode: str, dx: float, dy: float, *, shift: bool = False,
              alt: bool = False, ctrl: bool = False, others: List[Rect] = (),
              bounds: Tuple[int, int] = (0, 0)) -> Tuple[Rect, List[Tuple[str, float]]]:
    """Новая рамка по жесту; второе — к каким линиям прилипло [("x"|"y", координата)].

    Чистая функция — её проверяет тест без окна.
    """
    x, y, w, h = start
    if alt:
        dx, dy = round(dx / STEP) * STEP, round(dy / STEP) * STEP
    dx, dy = int(round(dx)), int(round(dy))
    if mode == "move":
        left, top, right, bottom = x + dx, y + dy, x + w + dx, y + h + dy
    else:
        left, top, right, bottom = x, y, x + w, y + h
        if "l" in mode:
            left += dx
        else:
            right += dx
        if "t" in mode:
            top += dy
        else:
            bottom += dy
        if shift and w and h:
            # пропорционально: берём сторону, которую потянули сильнее, вторую — по ней
            nw, nh = abs(right - left), abs(bottom - top)
            scale = max(nw / w, nh / h)
            nw, nh = max(1, round(w * scale)), max(1, round(h * scale))
            if "l" in mode:
                left = right - nw
            else:
                right = left + nw
            if "t" in mode:
                top = bottom - nh
            else:
                bottom = top + nh
    lines: List[Tuple[str, float]] = []
    if ctrl:
        near_x = [r for r in others if _overlap(r[1], r[1] + r[3], top - SNAP, bottom + SNAP)]
        near_y = [r for r in others if _overlap(r[0], r[0] + r[2], left - SNAP, right + SNAP)]
        tx = [0.0, float(bounds[0])] + [e for r in near_x for e in (r[0], r[0] + r[2])]
        ty = [0.0, float(bounds[1])] + [e for r in near_y for e in (r[1], r[1] + r[3])]
        if mode == "move":
            sx = snap_axis([left, right], tx)
            sy = snap_axis([top, bottom], ty)
            if sx is not None:
                left, right = left + sx, right + sx
            if sy is not None:
                top, bottom = top + sy, bottom + sy
        else:
            moving_x = left if "l" in mode else right
            moving_y = top if "t" in mode else bottom
            sx, sy = snap_axis([moving_x], tx), snap_axis([moving_y], ty)
            if sx is not None:
                if "l" in mode:
                    left += sx
                else:
                    right += sx
            if sy is not None:
                if "t" in mode:
                    top += sy
                else:
                    bottom += sy
        if sx is not None:
            for edge in ([left, right] if mode == "move" else [left if "l" in mode else right]):
                if edge in tx:
                    lines.append(("x", edge))
        if sy is not None:
            for edge in ([top, bottom] if mode == "move" else [top if "t" in mode else bottom]):
                if edge in ty:
                    lines.append(("y", edge))
    if right < left:
        left, right = right, left
    if bottom < top:
        top, bottom = bottom, top
    rect = (int(left), int(top), max(1, int(right - left)), max(1, int(bottom - top)))
    return rect, lines


class AtlasCanvas(QGraphicsView):
    sprite_clicked = Signal(object, bool)    # id спрайта, Ctrl — добавить/снять из выделения
    edit_changed = Signal(object)            # id в ручной правке или None
    rect_live = Signal(object, object)       # id, рамка во время жеста
    rect_committed = Signal(object, object)  # id, рамка по окончании жеста
    band_selected = Signal(list, bool)       # id под обводкой, Ctrl — добавить к выделенным
    rects_committed = Signal(object)         # {id: рамка} — сдвинули группу (не dict: PySide не передаёт словарь с числовыми ключами)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setScene(QGraphicsScene(self))
        self.setRenderHint(QPainter.SmoothPixmapTransform, False)    # пиксели — пикселями
        self.setTransformationAnchor(QGraphicsView.NoAnchor)      # к курсору — сами, см. zoom
        self.setDragMode(QGraphicsView.NoDrag)
        # к левому верхнему углу, а не по центру: по центру по бокам оставались пустые
        # полосы, и окно занимало лишнее место (юзер 23.10.2026)
        self.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        self.setFocusPolicy(Qt.StrongFocus)          # Ctrl+C / Ctrl+V / Delete — на холсте
        self.setMouseTracking(True)
        self.setBackgroundBrush(_checker())
        self.rects: Dict[object, QGraphicsRectItem] = {}
        self.selected: Optional[object] = None
        #: все выделенные (как в дереве); `selected` — главный из них
        self.marked: set = set()
        self.editing: Optional[object] = None
        self.frame: Optional[QGraphicsRectItem] = None
        self.size_wh = (0, 0)
        self.readonly = False
        #: вписывать атлас при каждом изменении размера, пока человек сам не тронул масштаб
        self.auto_fit = True
        self._drag = None                    # (режим, рамка в начале, точка сцены в начале)
        self._group = None                   # сдвиг группы: (рамки в начале, общая рамка, точка, id под мышью)
        self._band = None                    # обводка: (точка сцены в начале, Ctrl, текущая точка)
        self._pan = None
        self._lines: List[Tuple[str, float]] = []

    # ------------------------------------------------------------------ содержимое
    def show_doc(self, doc) -> None:
        scene = self.scene()
        scene.clear()
        self.rects, self.selected, self.editing = {}, None, None
        self.readonly = doc.readonly
        w, h = doc.data.width, doc.data.height
        self.size_wh = (w, h)
        image = doc.image()
        if image is not None:
            item = QGraphicsPixmapItem(QPixmap.fromImage(image))
            item.setTransform(QTransform.fromScale(w / image.width(), h / image.height()))
            item.setTransformationMode(Qt.FastTransformation)
            scene.addItem(item)
        self.frame = scene.addRect(QRectF(0, 0, w, h), self._pen("divider"))
        for sid in doc.ids():
            s = doc.sprite(sid)
            self.rects[sid] = scene.addRect(QRectF(s.x, s.y, s.width, s.height), self._pen("info"))
        scene.setSceneRect(QRectF(-16, -16, w + 32, h + 32))
        self.auto_fit = True
        self.fit()

    def sync(self, doc) -> None:
        """Рамки по документу без сброса масштаба: новые добавить, удалённые убрать,
        остальные подвинуть. Вызывается при правке раскладки (вставка, удаление, отмена)."""
        scene = self.scene()
        for sid in [k for k in self.rects if k not in doc.items]:
            scene.removeItem(self.rects.pop(sid))
            self.marked.discard(sid)
            if self.selected == sid:
                self.selected = None
            if self.editing == sid:
                self.set_editing(None)
        for sid in doc.ids():
            s = doc.sprite(sid)
            if sid in self.rects:
                self.rects[sid].setRect(QRectF(s.x, s.y, s.width, s.height))
            else:
                self.rects[sid] = scene.addRect(QRectF(s.x, s.y, s.width, s.height), self._pen("info"))
        self.viewport().update()

    def cursor_scene_pos(self) -> QPointF:
        """Точка атласа под мышью; мышь вне холста — середина видимой части."""
        pos = self.viewport().mapFromGlobal(QCursor.pos())
        if not self.viewport().rect().contains(pos):
            pos = self.viewport().rect().center()
        return self.mapToScene(pos)

    def update_sprite(self, sid, sprite) -> None:
        item = self.rects.get(sid)
        if item is not None:
            item.setRect(QRectF(sprite.x, sprite.y, sprite.width, sprite.height))
            self.viewport().update()

    def select(self, sid, marked=None) -> None:
        """Главный выделенный `sid` и все выделенные `marked` (по умолчанию — только он).
        Подсвечены все: выделение на холсте то же, что в дереве (юзер 23.10.2026)."""
        if sid != self.editing:
            self.set_editing(None)
        self.selected = sid
        self.marked = set(marked) if marked is not None else ({sid} if sid is not None else set())
        if sid is not None:
            self.marked.add(sid)
        self._paint_marks()
        if sid in self.rects and not self.auto_fit:
            self.ensureVisible(self.rects[sid], 40, 40)

    def _paint_marks(self) -> None:
        for key, item in self.rects.items():
            on = key in self.marked
            item.setPen(self._pen("accent", 2) if on else self._pen("info"))
            item.setZValue(1 if on else 0)
        self.viewport().update()

    def set_editing(self, sid) -> None:
        if self.readonly:
            sid = None
        if sid == self.editing:
            return
        self.editing = sid
        self._drag, self._lines = None, []
        self.viewport().update()
        self.edit_changed.emit(sid)

    def repaint_theme(self) -> None:
        self.setBackgroundBrush(_checker())
        if self.frame is not None:
            self.frame.setPen(self._pen("divider"))
        self._paint_marks()

    @staticmethod
    def _pen(role: str, width: int = 1) -> QPen:
        color = QColor(tokens.ACCENT) if role == "accent" else QColor(tokens.color(role))
        pen = QPen(color, width)
        pen.setCosmetic(True)                  # толщина в экранных пикселях при любом масштабе
        return pen

    def _rect(self, sid) -> Rect:
        r = self.rects[sid].rect()
        return int(round(r.x())), int(round(r.y())), int(round(r.width())), int(round(r.height()))

    # ------------------------------------------------------------------ масштаб
    def _scrollbars(self, on: bool) -> None:
        policy = Qt.ScrollBarAsNeeded if on else Qt.ScrollBarAlwaysOff
        self.setHorizontalScrollBarPolicy(policy)
        self.setVerticalScrollBarPolicy(policy)

    def fit(self) -> None:
        # Вписанному атласу прокрутка не нужна — полос нет. С ними было зависание
        # (юзер 23.10.2026): вписывание добавляло полосу, полоса сужала холст, холст
        # вписывался заново — 25 тысяч resize за 3 с на квадратных dayz_gui и ccgui_enforce.
        self.auto_fit = True
        self._scrollbars(False)
        if self.frame is not None:
            self.fitInView(self.frame.rect().adjusted(-8, -8, 8, 8), Qt.KeepAspectRatio)
            self._fitted = self.viewport().size()

    def zoom(self, factor: float, view_pos=None) -> None:
        """Масштаб к точке `view_pos` (по умолчанию — центр): точка атласа под курсором
        остаётся под курсором. Своим счётом, а не AnchorUnderMouse: тот берёт позицию из
        стандартного обработчика движения мыши, а его заменяет ручная правка рамки —
        и масштаб уезжал в центр (юзер 23.10.2026)."""
        self.auto_fit = False
        self._scrollbars(True)                 # свой масштаб — атлас больше окна, нужна прокрутка
        current = self.transform().m11()
        factor = max(ZOOM_MIN / current, min(ZOOM_MAX / current, factor))
        if view_pos is None:
            view_pos = self.viewport().rect().center()
        anchor = self.mapToScene(view_pos)
        self.scale(factor, factor)
        moved = self.mapFromScene(anchor) - view_pos
        self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() + moved.x())
        self.verticalScrollBar().setValue(self.verticalScrollBar().value() + moved.y())

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        # повторно — только если холст правда стал другого размера
        if self.auto_fit and getattr(self, "_fitted", None) != self.viewport().size():
            self.fit()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        if self.auto_fit:
            self.fit()

    def wheelEvent(self, event) -> None:
        if event.modifiers() & Qt.ControlModifier:
            self.zoom(ZOOM_STEP if event.angleDelta().y() > 0 else 1 / ZOOM_STEP,
                      event.position().toPoint())
            event.accept()
            return
        super().wheelEvent(event)

    # ------------------------------------------------------------------ мышь
    def _hit_sprite(self, view_pos) -> Optional[object]:
        point = self.mapToScene(view_pos)
        # самый маленький из накрывших: крупная подложка не перехватывает мелкую иконку
        hits = [k for k, item in self.rects.items() if item.rect().contains(point)]
        if not hits:
            return None
        return min(hits, key=lambda k: self.rects[k].rect().width() * self.rects[k].rect().height())

    def _handle_at(self, view_pos) -> Optional[str]:
        """Что под курсором у рамки в ручной правке: угол, «move» или None."""
        if self.editing not in self.rects:
            return None
        r = self.rects[self.editing].rect()
        corners = {"tl": r.topLeft(), "tr": r.topRight(), "bl": r.bottomLeft(), "br": r.bottomRight()}
        for name, point in corners.items():
            v = self.mapFromScene(point)
            if abs(v.x() - view_pos.x()) <= HANDLE and abs(v.y() - view_pos.y()) <= HANDLE:
                return name
        return "move" if r.contains(self.mapToScene(view_pos)) else None

    def mouseDoubleClickEvent(self, event) -> None:
        if event.button() != Qt.LeftButton:
            return super().mouseDoubleClickEvent(event)
        sid = self._hit_sprite(event.position().toPoint())
        if sid is None:
            self.set_editing(None)
        else:
            self.sprite_clicked.emit(sid, False)
            self.set_editing(sid)
        event.accept()

    def mousePressEvent(self, event) -> None:
        self.setFocus()
        pos = event.position().toPoint()
        if event.button() == Qt.MiddleButton:
            self._pan = pos
            self.setCursor(Qt.ClosedHandCursor)
            event.accept()
            return
        if event.button() != Qt.LeftButton:
            return super().mousePressEvent(event)
        handle = self._handle_at(pos)
        if handle is not None:
            self._drag = (handle, self._rect(self.editing), self.mapToScene(pos))
            event.accept()
            return
        ctrl = bool(event.modifiers() & Qt.ControlModifier)
        sid = self._hit_sprite(pos)
        if sid is None:
            # пустое место — обводка
            point = self.mapToScene(pos)
            self._band = (point, ctrl, point)
            event.accept()
            return
        if not ctrl and not self.readonly and sid in self.marked and len(self.marked) > 1:
            # выделено несколько — тащим всех сразу, без двойного щелчка
            starts = {k: self._rect(k) for k in self.marked if k in self.rects}
            left = min(r[0] for r in starts.values())
            top = min(r[1] for r in starts.values())
            right = max(r[0] + r[2] for r in starts.values())
            bottom = max(r[1] + r[3] for r in starts.values())
            self._group = (starts, (left, top, right - left, bottom - top), self.mapToScene(pos), sid, False)
            event.accept()
            return
        self.sprite_clicked.emit(sid, ctrl)
        event.accept()

    def mouseMoveEvent(self, event) -> None:
        pos = event.position().toPoint()
        if self._pan is not None:
            delta = pos - self._pan
            self._pan = pos
            self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() - delta.x())
            self.verticalScrollBar().setValue(self.verticalScrollBar().value() - delta.y())
            return
        if self._band is not None:
            start, ctrl, _cur = self._band
            self._band = (start, ctrl, self.mapToScene(pos))
            self.viewport().update()
            return
        if self._group is not None:
            starts, box, origin, under, _moved = self._group
            here = self.mapToScene(pos)
            mods = event.modifiers()
            others = [self._rect(k) for k in self.rects if k not in starts]
            new_box, self._lines = drag_rect(box, "move", here.x() - origin.x(), here.y() - origin.y(),
                                             alt=bool(mods & Qt.AltModifier),
                                             ctrl=bool(mods & Qt.ControlModifier), others=others,
                                             bounds=self.size_wh)
            dx, dy = new_box[0] - box[0], new_box[1] - box[1]
            for k, (x, y, w, h) in starts.items():
                self.rects[k].setRect(QRectF(x + dx, y + dy, w, h))
            self._group = (starts, box, origin, under, bool(dx or dy))
            self.viewport().update()
            return
        if self._drag is None:
            handle = self._handle_at(pos)
            cursor = {"tl": Qt.SizeFDiagCursor, "br": Qt.SizeFDiagCursor, "tr": Qt.SizeBDiagCursor,
                      "bl": Qt.SizeBDiagCursor, "move": Qt.SizeAllCursor}.get(handle, Qt.ArrowCursor)
            self.viewport().setCursor(cursor)
            return
        mode, start, origin = self._drag
        here = self.mapToScene(pos)
        mods = event.modifiers()
        others = [self._rect(k) for k in self.rects if k != self.editing]
        rect, self._lines = drag_rect(start, mode, here.x() - origin.x(), here.y() - origin.y(),
                                      shift=bool(mods & Qt.ShiftModifier), alt=bool(mods & Qt.AltModifier),
                                      ctrl=bool(mods & Qt.ControlModifier), others=others,
                                      bounds=self.size_wh)
        self.rects[self.editing].setRect(QRectF(*rect))
        self.rect_live.emit(self.editing, rect)
        self.viewport().update()

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.MiddleButton and self._pan is not None:
            self._pan = None
            self.unsetCursor()
            return
        if event.button() == Qt.LeftButton and self._band is not None:
            start, ctrl, cur = self._band
            self._band = None
            band = QRectF(start, cur).normalized()
            hits = [k for k, item in self.rects.items() if band.intersects(item.rect())] if band.width() or band.height() else []
            self.band_selected.emit(hits, ctrl)
            self.viewport().update()
            return
        if event.button() == Qt.LeftButton and self._group is not None:
            starts, _box, _origin, under, moved = self._group
            self._group, self._lines = None, []
            if moved:
                self.rects_committed.emit({k: self._rect(k) for k in starts})
            else:
                self.sprite_clicked.emit(under, False)      # щелчок без движения — только он
            self.viewport().update()
            return
        if event.button() == Qt.LeftButton and self._drag is not None:
            _mode, start, _origin = self._drag
            self._drag, self._lines = None, []
            rect = self._rect(self.editing)
            if rect != start:
                self.rect_committed.emit(self.editing, rect)
            self.viewport().update()
            return
        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key_Escape and self.editing is not None:
            self.set_editing(None)
            return
        super().keyPressEvent(event)

    # ------------------------------------------------------------------ ручки и линии
    def drawForeground(self, painter: QPainter, rect: QRectF) -> None:
        super().drawForeground(painter, rect)
        accent = QColor(tokens.ACCENT)
        if self._band is not None:
            start, _ctrl, cur = self._band
            pen = QPen(accent, 1, Qt.DashLine)
            pen.setCosmetic(True)
            painter.setPen(pen)
            fill = QColor(accent)
            fill.setAlpha(28)
            painter.setBrush(fill)
            painter.drawRect(QRectF(start, cur).normalized())
        if self._lines and self._group is not None:
            pen = QPen(accent, 1)
            pen.setCosmetic(True)
            painter.setPen(pen)
            for axis, value in self._lines:
                painter.drawLine(QLineF(value, rect.top(), value, rect.bottom()) if axis == "x"
                                 else QLineF(rect.left(), value, rect.right(), value))
        if self.editing not in self.rects:
            return
        scale = self.transform().m11() or 1.0
        r = self.rects[self.editing].rect()
        accent = QColor(tokens.ACCENT)
        pen = QPen(accent, 1)
        pen.setCosmetic(True)
        painter.setPen(pen)
        # линии прилипания — на всю видимую область
        for axis, value in self._lines:
            line = QLineF(value, rect.top(), value, rect.bottom()) if axis == "x" \
                else QLineF(rect.left(), value, rect.right(), value)
            painter.drawLine(line)
        half = HANDLE / 2 / scale
        painter.setBrush(QColor(tokens.color("window")))
        for point in (r.topLeft(), r.topRight(), r.bottomLeft(), r.bottomRight()):
            painter.drawRect(QRectF(point.x() - half, point.y() - half, half * 2, half * 2))
