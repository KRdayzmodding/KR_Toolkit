# -*- coding: utf-8 -*-
"""Общий вид Texture Editor — как у остальных тулз (KR QTS, Project Builder).

Заказ юзера 24.10.2026: «UI TextureEditor нужно привести к общему визуалу».
Здесь то, что нужно всем вкладкам сразу:

* тема qfluentwidgets из общего выбора (`kr_state.theme_name`, тёмная по
  умолчанию) и палитра Qt из тех же токенов — свои отрисовки (холст, кривая
  Френеля, сегмент) берут цвета из палитры и иначе остались бы светлыми;
* строка состояния вкладки (`StatusLine`) — вместо QStatusBar, с тем же
  `showMessage` / `addPermanentWidget`;
* окна вопросов и сообщений в цвет темы — вместо QMessageBox,
  QInputDialog и QProgressDialog, которые в тёмной теме оставались белыми;
* кнопка с выпадающим меню из готовых QAction — вместо строки меню, которой у
  окна со своей шапкой нет.
"""
from __future__ import annotations

from typing import Iterable, List, Optional, Sequence

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QAction, QColor, QPalette
from PySide6.QtWidgets import QHBoxLayout, QVBoxLayout, QWidget
from qfluentwidgets import (BodyLabel, CaptionLabel, LineEdit, PrimaryPushButton, ProgressBar,
                            PushButton, RoundMenu, SpinBox, SubtitleLabel,
                            TransparentDropDownPushButton, qconfig)

from qts_ui import tokens
from qts_ui.theme import ThemedDialog


# --------------------------------------------------------------------------
# тема
# --------------------------------------------------------------------------

def setup_theme(app, theme: str = "dark") -> None:
    """Тема как в KR QTS и [KR] Project Builder: выбранная, акцент DayZ, быстрые значки."""
    from qfluentwidgets import Theme, setTheme, setThemeColor

    from qts_ui import fasticons, nowheel, theme_sync

    setTheme({"auto": Theme.AUTO, "light": Theme.LIGHT, "dark": Theme.DARK}[theme])
    setThemeColor(tokens.ACCENT)
    # до первого окна: библиотека разбирает svg значков заново на каждый кадр
    fasticons.install()
    # колесо листает, а не правит значения под курсором
    nowheel.install(app)
    # тема — за общим выбором: сменили в DevToolkit — окно перекрашивается сразу
    theme_sync.follow(app)
    apply_palette(app)
    qconfig.themeChanged.connect(lambda *_: apply_palette(app))


def apply_palette(app) -> None:
    """Палитра Qt из токенов темы: по ней рисуют холст, кривая и сегмент."""
    c = lambda role: QColor(tokens.color(role))                    # noqa: E731
    pal = QPalette()
    for group in (QPalette.Active, QPalette.Inactive):
        pal.setColor(group, QPalette.Window, c("window"))
        pal.setColor(group, QPalette.WindowText, c("text"))
        pal.setColor(group, QPalette.Base, c("card"))
        pal.setColor(group, QPalette.AlternateBase, c("raised"))
        pal.setColor(group, QPalette.Text, c("text"))
        pal.setColor(group, QPalette.Button, c("raised"))
        pal.setColor(group, QPalette.ButtonText, c("text"))
        pal.setColor(group, QPalette.PlaceholderText, c("text_dim"))
        pal.setColor(group, QPalette.Highlight, QColor(tokens.ACCENT))
        pal.setColor(group, QPalette.HighlightedText, QColor("#ffffff"))
        pal.setColor(group, QPalette.ToolTipBase, c("card"))
        pal.setColor(group, QPalette.ToolTipText, c("text"))
        # подложка холста и линии на нём
        pal.setColor(group, QPalette.Dark, c("console_bg"))
        pal.setColor(group, QPalette.Mid, c("divider"))
        pal.setColor(group, QPalette.Light, c("raised"))
    for role in (QPalette.WindowText, QPalette.Text, QPalette.ButtonText):
        pal.setColor(QPalette.Disabled, role, c("muted"))
    for role, name in ((QPalette.Window, "window"), (QPalette.Base, "card"), (QPalette.Button, "raised"),
                       (QPalette.Dark, "console_bg"), (QPalette.Mid, "divider"),
                       (QPalette.Highlight, "border")):
        pal.setColor(QPalette.Disabled, role, c(name))
    app.setPalette(pal)


# --------------------------------------------------------------------------
# строка состояния вкладки
# --------------------------------------------------------------------------

class StatusLine(QWidget):
    """Строка под вкладкой: сообщение слева, постоянные сведения справа.

    Повторяет нужное от QStatusBar (`showMessage`, `currentMessage`,
    `addPermanentWidget`), но рисуется в цвет темы.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._row = QHBoxLayout(self)
        self._row.setContentsMargins(0, tokens.SPACE_XXS, 0, tokens.SPACE_XXS)
        self._row.setSpacing(tokens.SPACE_M)
        self._message = CaptionLabel("", self)
        self._message.setTextColor(tokens.color("text_dim"), tokens.color("text_dim"))
        self._row.addWidget(self._message, 1)

    def showMessage(self, text: str, _timeout: int = 0) -> None:      # noqa: N802 — как у QStatusBar
        self._message.setText(text)

    def currentMessage(self) -> str:                                   # noqa: N802
        return self._message.text()

    def addPermanentWidget(self, widget: QWidget, stretch: int = 0) -> None:   # noqa: N802
        self._row.addWidget(widget, stretch)


# --------------------------------------------------------------------------
# окна вопросов и сообщений
# --------------------------------------------------------------------------

class Box(ThemedDialog):
    """Окно с заголовком, текстом и своими кнопками — в цвет темы (как диалоги QTS).

    `exec()` возвращает номер нажатой кнопки из `buttons` (0 — первая), либо -1,
    если окно закрыли Esc. Кнопка `default` — по Enter. Содержимое добавляется
    в `viewLayout`.
    """

    def __init__(self, parent, title: str, text: str = "", buttons: Sequence[str] = (),
                 default: int = 0):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.chosen = -1
        outer = QVBoxLayout(self)
        outer.setContentsMargins(tokens.SPACE_L, tokens.SPACE_L, tokens.SPACE_L, tokens.SPACE_M)
        outer.setSpacing(tokens.SPACE_S)
        self.viewLayout = QVBoxLayout()
        self.viewLayout.setSpacing(tokens.SPACE_S)
        self.viewLayout.addWidget(SubtitleLabel(title, self))
        if text:
            note = BodyLabel(text, self)
            note.setWordWrap(True)
            self.viewLayout.addWidget(note)
        outer.addLayout(self.viewLayout)
        outer.addSpacing(tokens.SPACE_XS)
        self.buttonLayout = QHBoxLayout()
        self.buttonLayout.setSpacing(tokens.SPACE_XS)
        self.buttonLayout.addStretch(1)
        outer.addLayout(self.buttonLayout)
        self._buttons: List[PushButton] = []
        for index, label in enumerate(buttons):
            button = (PrimaryPushButton if index == default else PushButton)(label, self)
            button.setAutoDefault(False)
            button.clicked.connect(lambda _c=False, i=index: self._pick(i))
            self.buttonLayout.addWidget(button)
            self._buttons.append(button)
        if self._buttons:
            self._buttons[default].setDefault(True)          # Enter (п. 46)
        self.setMinimumWidth(400)

    def _pick(self, index: int) -> None:
        self.chosen = index
        self.accept()

    def exec(self) -> int:                                             # noqa: A003
        super().exec()
        return self.chosen


def button_row(dialog, accept_text: str, cancel_text: str = "Отмена"):
    """Кнопки внизу своего окна: действие (первичное, по Enter) и «Отмена» —
    в том же порядке, что у остальных окон тулзы (п. 20). Вернуть (ряд, кнопку)."""
    row = QHBoxLayout()
    row.setSpacing(tokens.SPACE_XS)
    row.addStretch(1)
    go = PrimaryPushButton(accept_text, dialog)
    go.setDefault(True)
    go.clicked.connect(dialog.accept)
    cancel = PushButton(cancel_text, dialog)
    cancel.setAutoDefault(False)
    cancel.clicked.connect(dialog.reject)
    row.addWidget(go)
    row.addWidget(cancel)
    return row, go


def warn(parent, title: str, text: str) -> None:
    """Сообщение с одной кнопкой «Понятно» — вместо QMessageBox.warning."""
    Box(parent, title, text, ("Понятно",)).exec()


YES, NO, CANCEL = 0, 1, 2


def ask(parent, title: str, text: str, default: int = YES) -> int:
    """Да / Нет / Отмена — вместо QMessageBox.question. Esc — отмена."""
    answer = Box(parent, title, text, ("Да", "Нет", "Отмена"), default).exec()
    return CANCEL if answer < 0 else answer


class _ValueBox(Box):
    def __init__(self, parent, title: str, label: str, field: QWidget):
        super().__init__(parent, title, label, ("OK", "Отмена"))
        self.field = field
        self.viewLayout.addWidget(field)
        QTimer.singleShot(0, field.setFocus)


def ask_int(parent, title: str, label: str, value: int, low: int, high: int):
    """Целое число — вместо QInputDialog.getInt. Возвращает (число, выбрано)."""
    box = SpinBox()
    box.setRange(low, high)
    box.setValue(value)
    dialog = _ValueBox(parent, title, label, box)
    return box.value(), dialog.exec() == 0


def ask_text(parent, title: str, label: str, text: str = ""):
    """Строка — вместо QInputDialog.getText. Возвращает (текст, выбрано)."""
    edit = LineEdit()
    edit.setText(text)
    dialog = _ValueBox(parent, title, label, edit)
    return edit.text(), dialog.exec() == 0


class Progress(Box):
    """Ход долгой операции с отменой — вместо QProgressDialog.

    Появляется, только если операция длится дольше `delay` мс: быстрая
    обходится без мелькающего окна.
    """

    def __init__(self, parent, text: str, cancel: str, delay: int = 400):
        super().__init__(parent, text, "", (cancel,))
        self.bar = ProgressBar(self)
        self.bar.setRange(0, 100)
        self.viewLayout.addWidget(self.bar)
        self.cancelled = False
        self._buttons[0].clicked.disconnect()
        self._buttons[0].clicked.connect(self._cancel)
        self._delay = delay
        self._started: Optional[float] = None

    def _cancel(self) -> None:
        self.cancelled = True

    def setValue(self, percent: int) -> None:                          # noqa: N802 — как у QProgressDialog
        import time
        now = time.monotonic()
        if self._started is None:
            self._started = now
        if not self.isVisible() and percent < 100 and (now - self._started) * 1000 >= self._delay:
            self.setWindowModality(Qt.WindowModal)
            self.show()
        self.bar.setValue(percent)
        if percent >= 100 and self.isVisible():
            self.hide()

    def wasCanceled(self) -> bool:                                     # noqa: N802
        return self.cancelled


# --------------------------------------------------------------------------
# меню
# --------------------------------------------------------------------------

class Submenu:
    """Вложенное меню, которое собирается в момент открытия (недавние файлы)."""

    def __init__(self, title: str, empty: str, actions):
        self.title = title
        self.empty = empty            #: надпись пункта, когда вложить нечего
        self.actions = actions        #: функция → список QAction
        self.visible = True           #: как у QAction: невидимое в меню не попадает


class MenuButton(TransparentDropDownPushButton):
    """Кнопка-меню из готовых действий: None — разделитель, Submenu — вложенное.

    Меню собирается заново при каждом открытии: так в нём ровно видимые сейчас
    пункты и свежий список недавних, а сочетания клавиш остаются на самих
    действиях и от меню не зависят.
    """

    #: пункты меню; ставит menu_button() — свой __init__ библиотека не терпит
    #: (её перегрузки зовут self.__init__(parent=...) заново)
    items: list = []

    def _build(self) -> RoundMenu:
        menu = RoundMenu(parent=self)
        pending_separator = False
        for item in self.items:
            if item is None:
                pending_separator = bool(menu.actions())
                continue
            if isinstance(item, QAction) and not item.isVisible():
                continue
            if isinstance(item, Submenu) and not item.visible:
                continue
            if pending_separator:
                menu.addSeparator()
                pending_separator = False
            if isinstance(item, Submenu):
                actions = item.actions()
                if actions:
                    sub = RoundMenu(item.title, menu)
                    sub.addActions(actions)
                    menu.addMenu(sub)
                else:
                    stub = QAction(item.empty, menu)
                    stub.setEnabled(False)
                    menu.addAction(stub)
            else:
                menu.addAction(item)
        return menu

    def _showMenu(self) -> None:                                       # noqa: N802 — метод библиотеки
        self.setMenu(self._build())
        super()._showMenu()

    def actions_in(self) -> List[QAction]:
        return [i for i in self.items if isinstance(i, QAction)]


def menu_button(text: str, items: Iterable, parent=None) -> MenuButton:
    """Кнопка-меню с этими пунктами."""
    button = MenuButton(text, parent)
    button.items = list(items)
    button.setMenu(button._build())
    return button
