# -*- coding: utf-8 -*-
"""Находки со ссылкой на файл: «[ERROR] модель.p3d: LOD 1.000. …», имя — ссылка.

Клик по имени открывает проводник с выделенным исходником (решение юзера
22.10.2026): находку правят в Object Builder, и первое, что нужно, — сам файл.
"""
from __future__ import annotations

import html
import os
import subprocess
from pathlib import Path
from urllib.parse import quote, unquote

from PySide6.QtCore import QEvent, QUrl, Qt, Signal
from PySide6.QtGui import QColor, QTextCursor
from PySide6.QtWidgets import QHBoxLayout, QTextEdit, QWidget
from qfluentwidgets import CaptionLabel, FluentIcon, PlainTextEdit, SearchLineEdit, TransparentToolButton

from qts_ui import tokens
from qts_ui.packing_log import PackingLog
from qts_ui.theme import link_html

TAG = {"error": "[ERROR]", "warning": "[WARNING]", "info": "[INFO]"}

#: Ссылка на окно логов: «kr-log:<уровень>/<имя PBO>».
LOG_SCHEME = "kr-log:"
#: Ссылка-действие окна: «kr-act:<действие>».
ACT_SCHEME = "kr-act:"


def act_link(action: str, text: str) -> str:
    from qts_ui.theme import link_color
    return '<a href="%s%s" style="color:%s;">%s</a>' % (ACT_SCHEME, action, link_color(),
                                                       html.escape(text))


def log_link(name: str, level: str, text: str) -> str:
    """Метка цветом уровня, подчёркнутая: видно, что жмётся, и не теряется роль."""
    return '<a href="%s%s/%s" style="color:%s;">%s</a>' % (
        LOG_SCHEME, level, quote(name), tokens.color(level), html.escape(text))


def finding_html(level: str, path: Path, text: str, extra: str = "") -> str:
    """Строка находки: тег уровня цветом роли, имя файла ссылкой, текст; `extra` — готовый html после текста."""
    role = level if level in TAG else "warning"
    if not path:
        link = ""
    elif Path(path).is_absolute():
        link = link_html(Path(path).as_uri(), html.escape(Path(path).name))
    else:                                   # неизвестно, где лежит, — без ссылки, но с именем
        link = html.escape(Path(path).name)
    return ('<span style="color:%s;">%s</span> %s: %s%s'
            % (tokens.color(role), TAG[role], link, html.escape(text), extra))


def reveal(path: str) -> None:
    """Проводник с выделенным файлом; файла нет — его папка, если она есть."""
    target = Path(path)
    if target.is_file():
        subprocess.Popen(["explorer", "/select,", str(target)])  # noqa: S603,S607
    elif target.parent.is_dir():
        os.startfile(str(target.parent))  # noqa: S606


class LinkText(PlainTextEdit):
    """Консоль, в которой имена файлов — ссылки (п. 10: жест — к видимому, ссылка видна).

    Ссылка на файл открывает проводник; ссылка `kr-log:` — сигнал `logRequested`
    (имя PBO, уровень): окно логов открывает тот, кто держит результаты;
    `kr-act:` — сигнал `actionRequested` (например, вернуть убранное).
    """

    logRequested = Signal(str, str)
    actionRequested = Signal(str)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # без слежения движение приходит только с зажатой кнопкой — рука над ссылкой не появлялась
        self.viewport().setMouseTracking(True)

    def mouseMoveEvent(self, event):
        super().mouseMoveEvent(event)
        anchor = self.anchorAt(event.position().toPoint())
        self.viewport().setCursor(Qt.PointingHandCursor if anchor else Qt.IBeamCursor)

    def mouseReleaseEvent(self, event):
        super().mouseReleaseEvent(event)
        if event.button() == Qt.LeftButton:
            anchor = self.anchorAt(event.position().toPoint())
            if anchor.startswith("file:"):
                reveal(QUrl(anchor).toLocalFile())
            elif anchor.startswith(LOG_SCHEME):
                level, _, name = anchor[len(LOG_SCHEME):].partition("/")
                self.logRequested.emit(unquote(name), level)
            elif anchor.startswith(ACT_SCHEME):
                self.actionRequested.emit(anchor[len(ACT_SCHEME):])


class LinkedPackingLog(PackingLog):
    """Таблица запаковки QTS, где [W: n] и [E: n] — ссылки на окно логов этого PBO.

    Копию QTS не правим (она синхронна с оригиналом): метки дорисовываем сами.
    """

    def _line(self, name: str) -> str:
        issues = self._issues.pop(name, None)
        try:
            out = super()._line(name)
        finally:
            if issues is not None:
                self._issues[name] = issues
        w, e = issues or (0, 0)
        if w:
            out += " " + log_link(name, "warning", "[W: %d]" % w)
        if e:
            out += " " + log_link(name, "error", "[E: %d]" % e)
        return out


class LogSearch(QWidget):
    """Поиск по журналу (юзер 25.10.2026): строка, «3 из 41», стрелки; все совпадения подсвечены.

    Без учёта регистра, по тому, что сейчас показано. Enter — следующее, Shift+Enter —
    предыдущее, Esc — очистить. Содержимое журнала сменилось — позвать `refresh()`.
    """

    def __init__(self, view: PlainTextEdit, placeholder: str, counter: str, nothing: str, parent=None):
        super().__init__(parent)
        self.view, self.counter, self.nothing = view, counter, nothing
        self.hits: list = []
        self.current = -1
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(tokens.SPACE_XS)
        self.edit = SearchLineEdit(self)
        self.edit.setPlaceholderText(placeholder)
        self.edit.setClearButtonEnabled(True)
        self.edit.textChanged.connect(lambda _t: self.refresh(move=True))
        self.edit.installEventFilter(self)
        row.addWidget(self.edit, 1)
        self.count = CaptionLabel("", self)
        row.addWidget(self.count)
        self.prev = TransparentToolButton(FluentIcon.UP, self)
        self.prev.clicked.connect(lambda: self.step(-1))
        row.addWidget(self.prev)
        self.next = TransparentToolButton(FluentIcon.DOWN, self)
        self.next.clicked.connect(lambda: self.step(1))
        row.addWidget(self.next)
        self._paint()

    def eventFilter(self, obj, event):
        if obj is self.edit and event.type() == QEvent.Type.KeyPress:
            if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                self.step(-1 if event.modifiers() & Qt.KeyboardModifier.ShiftModifier else 1)
                return True
            if event.key() == Qt.Key.Key_Escape and self.edit.text():
                self.edit.clear()
                return True
        return super().eventFilter(obj, event)

    def focus(self) -> None:
        self.edit.setFocus()
        self.edit.selectAll()

    def refresh(self, move: bool = False) -> None:
        """Найти всё заново; `move` — встать на первое совпадение."""
        text = self.edit.text()
        self.hits = []
        if text:
            doc = self.view.document()
            found = doc.find(text, 0)
            while not found.isNull():
                self.hits.append(QTextCursor(found))
                found = doc.find(text, found)
        if not self.hits:
            self.current = -1
        elif move or not 0 <= self.current < len(self.hits):
            self.current = 0
        self._paint()
        if move and self.hits:
            self._go()

    def step(self, delta: int) -> None:
        if not self.hits:
            return
        self.current = (self.current + delta) % len(self.hits)
        self._paint()
        self._go()

    def _go(self) -> None:
        self.view.setTextCursor(self.hits[self.current])
        self.view.ensureCursorVisible()

    def _paint(self) -> None:
        marks = []
        for i, hit in enumerate(self.hits):
            sel = QTextEdit.ExtraSelection()
            sel.cursor = hit
            color = QColor(tokens.color("warning"))
            color.setAlpha(200 if i == self.current else 70)
            sel.format.setBackground(color)
            marks.append(sel)
        self.view.setExtraSelections(marks)
        if not self.edit.text():
            self.count.setText("")
        elif self.hits:
            self.count.setText(self.counter.format(i=self.current + 1, n=len(self.hits)))
        else:
            self.count.setText(self.nothing)
        for button in (self.prev, self.next):
            button.setEnabled(len(self.hits) > 1)

