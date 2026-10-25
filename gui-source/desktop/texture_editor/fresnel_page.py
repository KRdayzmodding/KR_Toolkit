# -*- coding: utf-8 -*-
"""Вкладка «Подбор Френеля» в ``texture_editor``.

Обратная сторона фильтра TexView. Там вбивают N и K, ждут генерации и смотрят,
что вышло. Здесь наоборот: крутишь и сразу видишь, а когда понравилось —
забираешь готовую строку в шестой стейдж материала.

Три вида одного и того же, потому что по одному судить трудно:

* **таблица** — ровно то, что окажется в текстуре;
* **кривая** — по градиенту разницу между 0.10 и 0.14 на глаз не поймать, а
  тут видно сразу;
* **шар** — на плоской полосе не видно, где вспыхивает кромка, на изогнутой
  поверхности видно.

Шар нарисован одним только френелем: ни света, ни цвета материала, ни карты
нормалей. Это не движок и не притворяется им.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

import numpy as np

_HERE = Path(__file__).resolve().parent
_ROOT = _HERE.parents[1]
for _p in (str(_HERE), str(_ROOT), str(_HERE.parent)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from PySide6.QtCore import QPointF, QRect, QSettings, Qt               # noqa: E402
from PySide6.QtGui import (QColor, QFontMetrics, QGuiApplication,      # noqa: E402
                           QImage, QKeySequence, QPainter, QPainterPath,
                           QPalette, QPen, QPixmap, QShortcut)
from PySide6.QtWidgets import (                                        # noqa: E402
    QApplication, QFileDialog, QFormLayout, QHBoxLayout, QVBoxLayout, QWidget,
)
from qfluentwidgets import (                                           # noqa: E402
    BodyLabel, CaptionLabel, ComboBox, DoubleSpinBox, LineEdit, PrimaryPushButton,
    PushButton, SimpleCardWidget, Slider, SpinBox, StrongBodyLabel,
)

import look                                                            # noqa: E402
import remote as te                                                    # noqa: E402
from qts_ui import tokens                                              # noqa: E402

# --------------------------------------------------------------------------
# Текст — весь здесь
# --------------------------------------------------------------------------

TEXT = {
    "tab": "Подбор Френеля",

    "knobs": "Показатель преломления",
    "material": "Материал",
    "custom": "— свой —",
    "material_item": "%s — %d нм",
    "material_hint": ("Справочник движка. Все четырнадцать — металлы: у "
                      "диэлектрика поглощения нет, K равен нулю."),
    "n": "N — вещественная часть",
    "k": "K — мнимая часть, поглощение",
    "size": "Размер таблицы",
    "by": "×",

    "note": ("Горизонталь таблицы — косинус угла между нормалью и взглядом. "
             "Слева поверхность видна вскользь, справа — в упор. "
             "Вскользь отражает всё и всегда, материалы различаются правым концом."),

    "ramp": "Таблица",
    "curve": "Отражение по углу",
    "ball": "Шар",
    "body": "Деталь",
    "body_note": "тащить мышью, двойной клик — сброс",
    "body_hint": ("Освещение по формуле движка. Как френель умножается на "
                  "блик, документация не говорит — это наше допущение."),
    "material_group": "Материал",
    "level": "specular — сила блика",
    "power": "specularPower — резкость",
    "open": "Открыть rvmat…",
    "open_title": "Выберите материал",
    "open_filter": "Материалы (*.rvmat);;Все файлы (*)",
    "opened": "Взято из %s",
    "open_nofresnel": "В этом материале нет шестого стейджа с fresnel",
    "one": "1.0",
    "zero": "0.0",
    "grazing": "90°",
    "straight": "0°",
    "ball_note": "чистый френель, без света",

    "head_on": "В упор: %.3f",
    "lowest": "Минимум: %.3f при %.0f°",

    "line": "Строка для шестого стейджа",
    "copy": "Копировать",
    "copied": "Скопировано в буфер",
    "save": "Сохранить таблицу…",
    "save_title": "Сохранить таблицу",
    "save_filter": "PNG (*.png);;TGA (*.tga);;PAA (*.paa)",
    "saved": "Сохранено: %s",
    "save_failed": "Не сохранилось",

    "paste": "Взять из материала…",
    "paste_title": "Строка из материала",
    "paste_ask": "Вставьте строку из шестого стейджа:",
    "paste_failed": "В этой строке нет fresnel(N,K)",
}

#: пределы крутилок. Сняты с корпуса P:\DZ, 5794 записи: N от 0 до 10,
#: K от 0 до 10.26 — так что это не запас на всякий случай, а живой разброс
LIMIT = 10.0

#: на сколько долей делится ползунок: шаг выходит 0.01, как в материалах
STEPS = 1000

#: с чего начинаем — самая частая пара в корпусе
START = (1.0, 0.7)

#: размеры, которые ваниль ставит чаще всего
SIZES = ((64, 64), (32, 128))

MARGIN = 10
GAP = 8
BALL = 150

#: сколько радиан на пиксель при вращении мышью
TURN_PER_PIXEL = 0.012
CURVE = (260, 168)
RAMP_HEIGHT = 44


def _grid(painter: QPainter, box: QRect, ink: QColor) -> None:
    """Сетка под кривой: без неё по картинке ничего не измеришь."""
    pen = QPen(ink)
    pen.setWidth(1)
    painter.setPen(pen)
    for part in range(1, 4):
        y = box.top() + box.height() * part / 4
        painter.drawLine(QPointF(box.left(), y), QPointF(box.right(), y))
        x = box.left() + box.width() * part / 4
        painter.drawLine(QPointF(x, box.top()), QPointF(x, box.bottom()))


class Curve(QWidget):
    """Отражение по углу падения. Слева вскользь, справа в упор."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.values = np.zeros(2)
        self.setMinimumSize(*CURVE)

    def show_values(self, values: np.ndarray) -> None:
        self.values = values
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        palette = self.palette()
        box = self.rect().adjusted(1, 1, -2, -2)
        painter.fillRect(box, palette.base())

        faint = QColor(palette.text().color())
        faint.setAlpha(40)
        _grid(painter, box, faint)

        edge = QColor(palette.text().color())
        edge.setAlpha(90)
        painter.setPen(QPen(edge, 1))
        painter.drawRect(box)

        painter.setPen(QPen(QColor(palette.text().color()), 1))
        marks = QFontMetrics(painter.font())
        pad = 3
        painter.drawText(box.left() + pad, box.top() + marks.ascent() + pad, TEXT["one"])
        painter.drawText(box.left() + pad, box.bottom() - pad, TEXT["zero"])
        painter.drawText(box.left() + pad, box.bottom() - pad - marks.height(),
                         TEXT["grazing"])
        painter.drawText(box.right() - pad - marks.horizontalAdvance(TEXT["straight"]),
                         box.bottom() - pad - marks.height(), TEXT["straight"])

        if len(self.values) < 2:
            return
        path = QPainterPath()
        for index, value in enumerate(self.values):
            x = box.left() + box.width() * index / (len(self.values) - 1)
            y = box.bottom() - box.height() * float(value)
            point = QPointF(x, y)
            if index:
                path.lineTo(point)
            else:
                path.moveTo(point)
        painter.setPen(QPen(palette.highlight().color(), 2))
        painter.drawPath(path)


class Picture(QWidget):
    """Готовая картинка во всю отведённую ширину, без растягивания по высоте."""

    def __init__(self, height: int, smooth: bool = False, parent=None):
        super().__init__(parent)
        self.pixmap: Optional[QPixmap] = None
        self.smooth = smooth
        self.setMinimumHeight(height)
        self.setFixedHeight(height)

    def show_pixels(self, pixels: np.ndarray) -> None:
        data = np.ascontiguousarray(pixels)
        image = QImage(data.data, data.shape[1], data.shape[0],
                       data.shape[1] * 4, QImage.Format_RGBA8888).copy()
        self.pixmap = QPixmap.fromImage(image)
        self.update()

    def paintEvent(self, event) -> None:
        if self.pixmap is None:
            return
        painter = QPainter(self)
        if self.smooth:
            painter.setRenderHint(QPainter.SmoothPixmapTransform)
        painter.drawPixmap(self.rect(), self.pixmap)


class Body(QWidget):
    """Цилиндр, который можно покрутить мышью.

    Вращается само тело, а не свет: силуэт при повороте меняется, торец
    выходит из-за бока. Поворачивать одни нормали было бы дешевле, но тогда
    кажется, что ездит лампа, — а нам нужно посмотреть деталь с разных сторон.
    """

    def __init__(self, side: int, parent=None):
        super().__init__(parent)
        self.side = side
        self.turn = 0.5
        self.tilt = 0.35
        self.pixmap: Optional[QPixmap] = None
        self.material = None
        self.pair = None
        self._grab = None
        self.setFixedSize(side, side)
        self.setCursor(Qt.OpenHandCursor)
        self.setToolTip(TEXT["body_hint"])

    def show_material(self, material: dict, n=None, k=None) -> None:
        """material — {level, power, width, height}: из чего TextureEditor.exe соберёт материал."""
        self.material = material
        self.pair = (n, k)
        self._paint()

    def _paint(self) -> None:
        if self.material is None:
            return
        pixels = np.ascontiguousarray(te.fresnel_body(self.side, self.turn, self.tilt,
                                                      n=self.pair[0], k=self.pair[1], **self.material))
        image = QImage(pixels.data, pixels.shape[1], pixels.shape[0],
                       pixels.shape[1] * 4, QImage.Format_RGBA8888).copy()
        self.pixmap = QPixmap.fromImage(image)
        self.update()

    def paintEvent(self, event) -> None:
        if self.pixmap is not None:
            QPainter(self).drawPixmap(self.rect(), self.pixmap)

    # ---------- вращение ----------

    def mousePressEvent(self, event) -> None:
        self._grab = event.position()
        self.setCursor(Qt.ClosedHandCursor)

    def mouseMoveEvent(self, event) -> None:
        if self._grab is None:
            return
        shift = event.position() - self._grab
        self._grab = event.position()
        self.turn += shift.x() * TURN_PER_PIXEL
        self.tilt = max(-1.4, min(1.4, self.tilt + shift.y() * TURN_PER_PIXEL))
        self._paint()

    def mouseReleaseEvent(self, event) -> None:
        self._grab = None
        self.setCursor(Qt.OpenHandCursor)

    def mouseDoubleClickEvent(self, event) -> None:
        """Двойной клик возвращает исходный разворот: заблудиться легко."""
        self.turn, self.tilt = 0.5, 0.35
        self._paint()


class Knob(QWidget):
    """Ползунок и поле рядом: одним ведут, во втором читают и добивают точно."""

    def __init__(self, value: float, parent=None):
        super().__init__(parent)
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(GAP)

        self.slider = Slider(Qt.Horizontal)
        self.slider.setRange(0, STEPS)
        self.box = _SpinBox()
        self.box.setDecimals(3)
        self.box.setRange(0.0, LIMIT)
        self.box.setSingleStep(0.01)
        # число и встроенные кнопки поля: «10.000» целиком; ширина одна у всех
        # крутилок — поля встают в один столбец
        self.box.setFixedWidth(
            QFontMetrics(self.font()).horizontalAdvance("00.000") + 96)
        row.addWidget(self.slider, 1)
        row.addWidget(self.box)

        self._quiet = False
        self.slider.valueChanged.connect(self._from_slider)
        self.box.valueChanged.connect(self._from_box)
        self.set(value)

    def _from_slider(self, step: int) -> None:
        if self._quiet:
            return
        self._quiet = True
        self.box.setValue(step * LIMIT / STEPS)
        self._quiet = False
        self.changed()

    def _from_box(self, value: float) -> None:
        if self._quiet:
            return
        self._quiet = True
        self.slider.setValue(int(round(value * STEPS / LIMIT)))
        self._quiet = False
        self.changed()

    def changed(self) -> None:
        """Переопределяется окном."""

    def set(self, value: float) -> None:
        self._quiet = True
        self.box.setValue(value)
        self.slider.setValue(int(round(value * STEPS / LIMIT)))
        self._quiet = False

    def value(self) -> float:
        return self.box.value()


class _SpinBox(DoubleSpinBox):
    """Поле, которое не меняется от колеса под курсором: колесо листает окно,
    а не правит значение, на котором человек не стоял."""

    def wheelEvent(self, event):
        if self.hasFocus():
            super().wheelEvent(event)
        else:
            event.ignore()


class _SizeBox(SpinBox):

    def wheelEvent(self, event):
        if self.hasFocus():
            super().wheelEvent(event)
        else:
            event.ignore()


class FresnelPage(QWidget):

    def __init__(self, settings: Optional[QSettings] = None, parent=None):
        super().__init__(parent)
        self.settings = settings if settings is not None else QSettings("KR", "FresnelStudio")
        self._build()
        self._restore()
        self._redraw()

    # ---------- сборка ----------

    def _build(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, MARGIN, 0, MARGIN)
        outer.setSpacing(GAP)

        knobs = SimpleCardWidget()
        card = QVBoxLayout(knobs)
        card.setContentsMargins(tokens.SPACE_M, tokens.SPACE_S, tokens.SPACE_M, tokens.SPACE_S)
        card.setSpacing(GAP)
        card.addWidget(StrongBodyLabel(TEXT["knobs"]))
        form = QFormLayout()
        form.setSpacing(GAP)
        card.addLayout(form)
        self.material = ComboBox()
        self.material.addItem(TEXT["custom"], userData=None)
        for name, wavelength in te.info()["fresnel_materials"]:
            self.material.addItem(TEXT["material_item"] % (name, wavelength), userData=name)
        self.material.setToolTip(TEXT["material_hint"])
        self.material.activated.connect(self._material_picked)
        form.addRow(BodyLabel(TEXT["material"]), self.material)

        self.n = Knob(START[0])
        self.k = Knob(START[1])
        self.n.changed = self._redraw
        self.k.changed = self._redraw
        form.addRow(BodyLabel(TEXT["n"]), self.n)
        form.addRow(BodyLabel(TEXT["k"]), self.k)

        self.level = Knob(0.35)
        self.level.box.setRange(0.0, 1.0)
        self.level.box.setSingleStep(0.05)
        self.level.slider.setRange(0, 100)
        self.level.changed = self._redraw
        form.addRow(BodyLabel(TEXT["level"]), self.level)

        self.power = _SizeBox()
        self.power.setRange(1, 2000)
        self.power.setValue(50)
        self.power.valueChanged.connect(self._redraw)
        power_row = QHBoxLayout()
        power_row.setSpacing(GAP)
        power_row.addWidget(self.power)
        power_row.addStretch(1)
        form.addRow(BodyLabel(TEXT["power"]), power_row)

        self.width_box = _SizeBox()
        self.height_box = _SizeBox()
        for box, value in ((self.width_box, SIZES[0][0]), (self.height_box, SIZES[0][1])):
            box.setRange(1, 2048)
            box.setValue(value)
            box.valueChanged.connect(self._redraw)
        size_row = QHBoxLayout()
        size_row.setSpacing(GAP)
        size_row.addWidget(self.width_box)
        size_row.addWidget(BodyLabel(TEXT["by"]))
        size_row.addWidget(self.height_box)
        size_row.addStretch(1)
        form.addRow(BodyLabel(TEXT["size"]), size_row)
        outer.addWidget(knobs)

        note = CaptionLabel(TEXT["note"])
        note.setWordWrap(True)
        outer.addWidget(note)

        self.ramp = Picture(RAMP_HEIGHT)
        outer.addWidget(_titled(TEXT["ramp"], self.ramp))

        views = QHBoxLayout()
        views.setSpacing(GAP)
        self.curve = Curve()
        views.addWidget(_titled(TEXT["curve"], self.curve), 1)
        self.ball = Picture(BALL, smooth=True)
        self.ball.setFixedWidth(BALL)
        views.addWidget(_titled(TEXT["ball"], self.ball, TEXT["ball_note"]))
        self.body = Body(BALL)
        views.addWidget(_titled(TEXT["body"], self.body, TEXT["body_note"]))
        outer.addLayout(views)

        self.head_on = BodyLabel()
        self.lowest = BodyLabel()
        numbers = QHBoxLayout()
        numbers.setSpacing(GAP * 2)
        numbers.addWidget(self.head_on)
        numbers.addWidget(self.lowest)
        numbers.addStretch(1)
        outer.addLayout(numbers)

        self.line = LineEdit()
        self.line.setReadOnly(True)
        self.copy_btn = PrimaryPushButton(TEXT["copy"])
        self.copy_btn.setDefault(True)
        self.copy_btn.clicked.connect(self.copy)
        self.paste_btn = PushButton(TEXT["paste"])
        self.paste_btn.clicked.connect(self.take_from_material)
        self.save_btn = PushButton(TEXT["save"])
        self.save_btn.clicked.connect(self.save)

        bottom = QVBoxLayout()
        bottom.setSpacing(GAP)
        bottom.addWidget(BodyLabel(TEXT["line"]))
        row = QHBoxLayout()
        row.setSpacing(GAP)
        row.addWidget(self.line, 1)
        row.addWidget(self.copy_btn)
        bottom.addLayout(row)
        tools = QHBoxLayout()
        tools.setSpacing(GAP)
        self.open_btn = PushButton(TEXT["open"])
        self.open_btn.clicked.connect(self.open_material)
        tools.addWidget(self.open_btn)
        tools.addWidget(self.paste_btn)
        tools.addWidget(self.save_btn)
        tools.addStretch(1)
        # отклик действий — в свободном конце ряда кнопок, а не отдельной
        # строкой состояния: той не хватало места по высоте, и она уезжала
        # под прокрутку, где «Скопировано» уже никто не видит
        self._status_bar = _Note()
        tools.addWidget(self._status_bar)
        bottom.addLayout(tools)
        outer.addLayout(bottom)
        # Ctrl+C копирует строку, только пока открыта эта вкладка: на
        # соседних он должен копировать своё
        QShortcut(QKeySequence.Copy, self, self.copy,
                  context=Qt.WidgetWithChildrenShortcut)

    def statusBar(self) -> "_Note":
        return self._status_bar

    def activate(self) -> None:
        self.n.box.setFocus()

    # ---------- пересчёт ----------

    def values(self):
        return self.n.value(), self.k.value()

    def table_size(self):
        return self.width_box.value(), self.height_box.value()

    def _material_picked(self, index: int) -> None:
        name = self.material.itemData(index)
        if name is None:
            return
        n, k = te.fresnel_material(name)
        self.n.set(n)
        self.k.set(k)
        self._redraw()

    def _redraw(self) -> None:
        n, k = self.values()
        # список показывает справочное имя, только пока числа ровно на нём:
        # иначе он врал бы про материал, от которого человек уже ушёл
        width, height = self.table_size()
        # всё, что зависит от чисел, — одним запросом к TextureEditor.exe
        view = te.fresnel_view(n, k, width, height, max(1, RAMP_HEIGHT // 4), BALL)
        known = view["known"]
        self.material.setCurrentIndex(
            self.material.findData(known) if known else 0)
        # на экране показываем альфу серым: значение лежит именно в ней, а
        # белое полотно по светлому фону не видно вовсе. В файл при этом
        # уходит настоящая таблица, белая с альфой
        self.ramp.show_pixels(_alpha_as_grey(view["ramp"]))
        self.ball.show_pixels(view["ball"])

        line = view["curve"]
        self.curve.show_values(line)
        self.head_on.setText(TEXT["head_on"] % view["head_on"])
        at = int(np.argmin(line))
        angle = np.degrees(np.arccos(np.linspace(0.0, 1.0, 256)[at]))
        self.lowest.setText(TEXT["lowest"] % (line[at], angle))
        self.line.setText(view["stage_line"])
        self.file_stem = view["file_stem"]

        shown = {"level": self.level.value(), "power": float(self.power.value()),
                 "width": width, "height": height}
        self.body.show_material(shown, n, k)

    # ---------- действия ----------

    def copy(self) -> None:
        QGuiApplication.clipboard().setText(self.line.text())
        self.statusBar().showMessage(TEXT["copied"])

    def take_from_material(self) -> None:
        """Взять числа из уже написанного материала, а не набирать заново."""
        text, chosen = look.ask_text(self, TEXT["paste_title"], TEXT["paste_ask"])
        if not chosen:
            return
        found = te.fresnel_parse(text)
        if found is None:
            look.warn(self, TEXT["paste_title"], TEXT["paste_failed"])
            return
        n, k, width, height, _mips = found
        self.n.set(min(n, LIMIT))
        self.k.set(min(k, LIMIT))
        self.width_box.setValue(width)
        self.height_box.setValue(height)
        self._redraw()

    def open_material(self) -> None:
        """Взять числа прямо из rvmat: подбор чаще начинают от готового."""
        picked, _ = QFileDialog.getOpenFileName(
            self, TEXT["open_title"], "", TEXT["open_filter"])
        if not picked:
            return
        try:
            material = te.fresnel_read(picked)
        except (OSError, ValueError) as exc:
            look.warn(self, TEXT["open_title"], str(exc))
            return
        self.level.set(min(1.0, material["specular_level"]))
        self.power.setValue(int(round(max(1.0, material["power"]))))
        if material["fresnel"] is None:
            self.statusBar().showMessage(TEXT["open_nofresnel"])
        else:
            self.n.set(min(material["fresnel"][0], LIMIT))
            self.k.set(min(material["fresnel"][1], LIMIT))
            self.width_box.setValue(material["size"][0])
            self.height_box.setValue(material["size"][1])
            self.statusBar().showMessage(TEXT["opened"] % Path(picked).name)
        self._redraw()

    def save(self) -> None:
        n, k = self.values()
        width, height = self.table_size()
        stem = te.fresnel_view(n, k, width, height, 1, 16)["file_stem"]
        picked, _ = QFileDialog.getSaveFileName(
            self, TEXT["save_title"], stem, TEXT["save_filter"])
        if not picked:
            return
        target = Path(picked)
        if not target.suffix:
            target = target.with_suffix(".png")
        try:
            te.fresnel_save(n, k, width, height, target)
        except Exception as exc:
            look.warn(self, TEXT["save_failed"], str(exc))
            return
        self.statusBar().showMessage(TEXT["saved"] % target.name)

    # ---------- память ----------

    def _restore(self) -> None:
        try:
            self.n.set(float(self.settings.value("n", START[0])))
            self.k.set(float(self.settings.value("k", START[1])))
            self.width_box.setValue(int(self.settings.value("width", SIZES[0][0])))
            self.height_box.setValue(int(self.settings.value("height", SIZES[0][1])))
        except (TypeError, ValueError):
            pass

    def shutdown(self) -> None:
        """Запомнить крутилки. Зовёт главное окно при закрытии: вложенная
        вкладка своего closeEvent не получает."""
        self.settings.setValue("n", self.n.value())
        self.settings.setValue("k", self.k.value())
        self.settings.setValue("width", self.width_box.value())
        self.settings.setValue("height", self.height_box.value())
        # без этого значения остаются в памяти и пропадают, если процесс
        # закончится не своей смертью
        self.settings.sync()

    def closeEvent(self, event) -> None:
        self.shutdown()
        super().closeEvent(event)


class _Note(CaptionLabel):
    """Надпись с тем же обращением, что у строки состояния."""

    def showMessage(self, text: str) -> None:
        self.setText(text)

    def currentMessage(self) -> str:
        return self.text()


def _alpha_as_grey(pixels: np.ndarray) -> np.ndarray:
    """Альфу — в серый и непрозрачный, чтобы её было видно на экране."""
    out = np.empty_like(pixels)
    for channel in range(3):
        out[..., channel] = pixels[..., 3]
    out[..., 3] = 255
    return out


def _titled(title: str, widget: QWidget, note: str = "") -> QWidget:
    """Виджет с подписью сверху и пояснением снизу.

    Пояснение отдельной строкой, а не приписанное к заголовку через тире:
    склеенные, они растягивали колонку под самую длинную фразу, и окно
    разъезжалось вдвое шире нужного.
    """
    holder = QWidget()
    column = QVBoxLayout(holder)
    column.setContentsMargins(0, 0, 0, 0)
    column.setSpacing(2)
    column.addWidget(BodyLabel(title))
    column.addWidget(widget)
    if note:
        small = CaptionLabel(note)
        small.setWordWrap(True)
        small.setTextColor(tokens.color("text_dim"), tokens.color("text_dim"))
        column.addWidget(small)
    column.addStretch(1)
    if widget.maximumWidth() < 16777215:
        holder.setMaximumWidth(widget.maximumWidth())
    return holder

