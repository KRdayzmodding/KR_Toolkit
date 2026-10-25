# Скопировано из KR_ServerManager/ui/rows.py (рабочая копия на 22.10.2026, последний коммит QTS deba8ad) — общий визуальный язык с KR QTS.
# Править синхронно с оригиналом, а не молча здесь.
"""Строки настроек: название и пояснение слева, контрол справа.

Общий вид, к которому идут все формы программы, вместо «метка: поле».
Пояснение видно без наведения мыши — половина смысла программы жила во
всплывающих подсказках, и увидеть её можно было только случайно.

Выведено из прототипа (tools/mockup.py) после того, как форма устоялась.
Комментарии здесь — не пересказ кода, а следы ошибок: каждая мелочь вроде
`setMinimumWidth(1)` стоила отдельного разбора, почему окно требует полторы
тысячи пикселей ширины.
"""
from __future__ import annotations

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import (
    QGridLayout, QHBoxLayout, QSizePolicy, QVBoxLayout, QWidget,
)
from qfluentwidgets import CaptionLabel, StrongBodyLabel

from qts_ui import tokens

CONTROL_SLOT = 190      # ширина места под контрол: колонки выравниваются по нему
TEXT_MIN = 220          # ниже этого название с пояснением читать невозможно


def shrink(label):
    """Разрешает подписи ужиматься.

    Метка с переносом всё равно требует ширину всей строки целиком, пока ей не
    сказать, что её желаемая ширина никого не интересует. Из-за этого одна
    строка «Запаковывать изменённые моды перед запуском» требовала 602 px и
    растягивала окно до полутора тысяч.
    """
    label.setWordWrap(True)
    label.setMinimumWidth(1)
    # Preferred, а не Ignored: Ignored означает «желаемая ширина неинтересна», и
    # раскладка ужимает метку до минимума — текст встаёт столбиком по слову в
    # строке. Нужно другое: желаемую ширину учитывать, а требовать её — нет.
    label.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
    return label


def slot(control) -> QWidget:
    """Кладёт контрол в слот постоянной ширины, прижимая вправо.

    Без этого поле на 80 px и поле на 170 px дают разные колонки, и две сетки
    в одной карточке читаются как две разные таблицы.
    """
    box = QWidget()
    lay = QHBoxLayout(box)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.addStretch(1)
    lay.addWidget(control)
    # минимум, а не потолок: узкие контролы выстраиваются по одной вертикали,
    # широкие (поле ввода, список) не обрезаются
    box.setMinimumWidth(CONTROL_SLOT)
    return box


def setting_row(title: str, desc: str, control, prefix=None) -> QWidget:
    """Строка настройки: название и пояснение слева, контрол справа.

    prefix — виджет перед названием (галка «писать в файл» в редакторе
    конфига). Он часть строки, а не отдельная колонка: иначе при переносе в
    другую ширину галка уезжает от своего названия.
    """
    row = QWidget()
    lay = QHBoxLayout(row)
    lay.setContentsMargins(0, tokens.SPACE_XXS, 0, tokens.SPACE_XXS)
    lay.setSpacing(tokens.SPACE_M)
    if prefix is not None:
        lay.addWidget(prefix, 0, Qt.AlignmentFlag.AlignTop)
    text = QVBoxLayout()
    text.setSpacing(0)
    text.addWidget(shrink(StrongBodyLabel(title)))
    # Подпись создаём всегда, даже пустую: её текст меняется на ходу (список
    # подключённых модов, режим запаковки), и добавлять её потом значило бы
    # пересобирать строку.
    row.desc_label = shrink(CaptionLabel(desc))
    text.addWidget(row.desc_label)
    holder = QWidget()
    holder.setLayout(text)
    holder.setMinimumWidth(TEXT_MIN)
    lay.addWidget(holder, 1)
    lay.addWidget(slot(control), 0, Qt.AlignmentFlag.AlignVCenter)
    # Видимость — в самом конце, когда у подписи уже есть родитель. Виджет без
    # родителя, которому сказали показаться, — это окно верхнего уровня: оно
    # успевает мигнуть на экране и пропасть, когда его кладут в раскладку.
    row.desc_label.setVisible(bool(desc))
    return row


class Rule(QWidget):
    """Разделительная линия, которая рисует себя сама.

    Через таблицу стилей не годится: карточка при наведении мыши перекрашивает
    себя своим стилем, и линия внутри неё исчезала. Собственная отрисовка чужим
    стилем не перебивается.
    """

    def __init__(self, vertical: bool = False, parent=None):
        super().__init__(parent)
        self.vertical = vertical
        if vertical:
            self.setFixedWidth(1)
        else:
            self.setFixedHeight(1)

    def paintEvent(self, e):        # имя метода задаёт Qt
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(tokens.color("divider")))


def subheading(text: str, line: bool = False) -> QWidget:
    """Подзаголовок внутри карточки. С линией — когда отделяет блок от блока."""
    w = QWidget()
    box = QVBoxLayout(w)
    box.setContentsMargins(0, tokens.SPACE_S if line else 0, 0, tokens.SPACE_XXS)
    box.setSpacing(tokens.SPACE_XS)
    if line:
        box.addWidget(Rule())
    box.addWidget(StrongBodyLabel(text))
    return w


class Columns(QWidget):
    """Раскладывает строки настроек в несколько колонок по ширине.

    Строка настройки — это название, пояснение и контрол; в одну колонку такие
    строки занимают вдвое больше высоты, чем нужно, а справа остаётся пустое
    место. Колонок ровно столько, сколько помещается: узкое окно — одна, широкое
    — две или три. Порядок заполнения слева направо, как читают.
    """

    MIN_COL = 430           # ниже этого в колонке не помещаются название и контрол

    def __init__(self, rows, parent=None):
        super().__init__(parent)
        # какие строки показывать — храним явным списком. Опираться на
        # видимость виджетов нельзя: строка, которую ещё ни разу не показывали,
        # для Qt скрыта, и сетка получалась пустой.
        self.rows = list(rows)
        self.active = list(rows)
        self.grid = QGridLayout(self)
        self.grid.setContentsMargins(0, 0, 0, 0)
        # Жёлоб широкий и с линией: иначе контрол левой колонки оказывается
        # ближе к заголовку правой, чем к своему, и читается вместе с ним.
        self.grid.setHorizontalSpacing(tokens.SPACE_L)
        self.grid.setVerticalSpacing(0)
        self._cols = 0
        self._relayout(1)

    def _relayout(self, cols: int) -> None:
        if cols == self._cols:
            return
        self._cols = cols
        while self.grid.count():
            item = self.grid.takeAt(0)
            w = item.widget()
            if w is not None and w not in self.rows:
                # Сначала вынуть из иерархии, потом удалять: deleteLater
                # откладывает удаление до возврата в цикл событий, и до тех пор
                # старый разделитель продолжает рисоваться поверх новой сетки.
                w.setParent(None)
                w.deleteLater()
        # содержимое в чётных столбцах, разделители в нечётных
        for i, row in enumerate(self.active):
            self.grid.addWidget(row, i // cols, (i % cols) * 2)
        rows_count = (len(self.active) + cols - 1) // cols
        for c in range(cols):
            self.grid.setColumnStretch(c * 2, 1)
            # Разделитель нужен только там, где справа от него что-то есть:
            # при одной оставшейся строке линия висела в пустоте.
            if c and len(self.active) > c:
                self.grid.addWidget(Rule(vertical=True, parent=self),
                                    0, c * 2 - 1, max(rows_count, 1), 1)

    def set_active(self, rows) -> None:
        """Показать только эти строки — остальные убрать из сетки.

        Сначала перекладываем сетку, потом трогаем видимость: строку нам могли
        отдать списком, ни разу не положив в раскладку (так делает панель
        параметров), и тогда у неё нет родителя. Сказать такой строке
        «покажись» — значит завести окно верхнего уровня, которое мигнёт на
        экране и исчезнет. При тридцати строках это тридцать вспышек на старте.
        """
        self.active = [r for r in self.rows if r in rows]
        cols, self._cols = self._cols, 0
        self._relayout(cols or 1)
        for row in self.rows:
            if row.parentWidget() is not self:
                # не попала в сетку — всё равно наша, а не самостоятельное окно
                row.setParent(self)
            row.setVisible(row in rows)

    def minimumSizeHint(self):      # имя метода задаёт Qt
        """Минимум — одна колонка, а не столько, сколько показано сейчас.

        Иначе получается храповик: сетка из трёх колонок требует ширину трёх
        колонок, страница перестаёт сужаться, событие сужения до сетки не
        доходит — и она навсегда остаётся трёхколоночной. Окно при этом
        сужается, а содержимое уезжает за рамку.
        """
        base = super().minimumSizeHint()
        one = max((row.minimumSizeHint().width() for row in self.rows),
                  default=base.width())
        return QSize(min(one, base.width()), base.height())

    def resizeEvent(self, e):       # имя метода задаёт Qt
        super().resizeEvent(e)
        self._relayout(max(1, self.width() // self.MIN_COL))
