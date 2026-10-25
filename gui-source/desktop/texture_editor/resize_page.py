# -*- coding: utf-8 -*-
"""Вкладка «Размер текстур» в ``texture_editor``.

Окно над ``resize.py``. Файлы собираются в список — бросить мышью, добавить
кнопкой, а можно передать в командной строке, как раньше их бросали на
TextureResizer.exe. Затем выбирается длинная сторона, и кнопка называет, что
будет: «Привести к 1024».

Журнал, цвета и поведение клавиш — те же, что у вкладки фильтра SMDI: две
вкладки пакетной работы не должны вести себя по-разному.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import List, NamedTuple, Optional, Tuple

_HERE = Path(__file__).resolve().parent
_ROOT = _HERE.parents[1]
for _p in (str(_HERE), str(_ROOT), str(_HERE.parent)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from PySide6.QtCore import QEvent, QSettings, Qt, QThread, Signal         # noqa: E402
from PySide6.QtGui import QKeySequence, QPalette, QShortcut              # noqa: E402
from PySide6.QtWidgets import (                                           # noqa: E402
    QAbstractItemView, QFileDialog, QFormLayout, QHBoxLayout, QStackedWidget, QVBoxLayout,
    QWidget,
)
from qfluentwidgets import (                                              # noqa: E402
    BodyLabel, CaptionLabel, CardWidget, ComboBox, ListWidget, PlainTextEdit,
    PrimaryPushButton, ProgressBar, PushButton, StrongBodyLabel,
)

import remote as te                                                        # noqa: E402
from smdi_folder import GAP, MARGIN, SECTION, role_color                  # noqa: E402

# --------------------------------------------------------------------------
# Текст. Весь — здесь.
# --------------------------------------------------------------------------

TEXT = {
    "tab": "Размер текстур",

    "files": "Файлы",
    "files_empty": ("Перетащите сюда текстуры или папку с ними.\n"
                    "PAA, PNG, TGA, DDS, JPG — обе стороны степенью двойки."),
    "add_files": "Добавить файлы…",
    "add_folder": "Добавить папку…",
    "remove": "Убрать выбранные",
    "clear": "Очистить список",
    "pick_files": "Текстуры",
    "pick_filter": "Текстуры (*.paa *.png *.tga *.dds *.jpg *.jpeg);;Все файлы (*)",
    "pick_folder": "Папка с текстурами",

    "side": "Длинная сторона",
    "side_note": "вторая — в той же пропорции",
    "side_item": "%d",

    "run": "Привести к %d",
    "stop": "Остановить",

    "log": "Журнал",
    "log_empty": "Здесь появится, что стало с каждым файлом.",

    "state_empty": "Добавьте текстуры.",
    "state_ready": "Файлов в списке: %d.",
    "state_running": "Обработано %d из %d",

    "done": "%s: %dx%d → %dx%d",
    "done_note": "%s: %dx%d → %dx%d — %s",
    "same": "%s: уже %dx%d",
    "refused": "%s: пропущен — %s",
    "error": "%s: не изменён — %s",
    "added_none": "Среди брошенного нет текстур, которые я умею менять.",

    "batch_done": "Готово: изменено %d, уже нужного размера %d, пропущено %d, ошибок %d.",
    "backup": "Оригиналы — в %s рядом с файлами.",
    "stopped": "Остановлено.",
}

#: какую сторону предлагать при первом запуске — чаще всего ужимают до неё
DEFAULT_SIDE = 2048


class Outcome(NamedTuple):
    """Чем кончилось для одного файла — из события TextureEditor.exe resize."""

    state: str                     #: done | same | refused | error
    old: Tuple[int, int] = (0, 0)
    new: Tuple[int, int] = (0, 0)
    note: str = ""


class Job(QThread):
    """Пакет в отдельном потоке: окно живое, журнал наполняется по ходу."""

    file_done = Signal(str, object)     #: имя файла, Outcome
    step = Signal(int, int)             #: сделано, всего
    batch_done = Signal(object)         #: счётчик состояний

    def __init__(self, files: List[Path], side: int, parent=None):
        super().__init__(parent)
        self._files = list(files)
        self._side = side
        self._cli: Optional[te.CliJob] = None
        self._stopping = False

    def stop(self) -> None:
        self._stopping = True
        if self._cli is not None:
            self._cli.stop()

    def run(self) -> None:
        """Размер меняет TextureEditor.exe resize; здесь — его события в сигналы окна."""
        counts = {"done": 0, "same": 0, "refused": 0, "error": 0}
        self._cli = te.CliJob(["resize", "--side", str(self._side)], self._files)
        self._cli.event.connect(lambda ev: self._event(ev, counts))
        if self._stopping:
            self.batch_done.emit(counts)
            return
        self._cli.run()                     # в этом же потоке: события идут по ходу
        self.batch_done.emit(counts)

    def _event(self, ev: dict, counts: dict) -> None:
        if ev.get("event") == "file":
            outcome = Outcome(ev["state"], tuple(ev.get("old") or (0, 0)), tuple(ev.get("new") or (0, 0)),
                              ev.get("note") or "")
            counts[outcome.state] = counts.get(outcome.state, 0) + 1
            self.file_done.emit(ev["name"], outcome)
        elif ev.get("event") == "step":
            self.step.emit(int(ev["done"]), int(ev["total"]))
        elif ev.get("event") == "problem":
            counts["error"] += 1
            self.file_done.emit("", Outcome("error", note=ev.get("text", "")))


class ResizePage(QWidget):

    def __init__(self, files: Optional[List[str]] = None,
                 settings: Optional[QSettings] = None, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.settings = settings if settings is not None else QSettings("KR", "TextureStudio")
        self.job: Optional[Job] = None
        self.files: List[Path] = []
        self.entries: List[Tuple[str, str]] = []   #: (роль, строка) — журнал

        self._build()
        self._restore()
        if files:
            self.add(files)
        self._sync()

    # ---------- сборка ----------

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, MARGIN, 0, MARGIN)
        root.setSpacing(SECTION)

        form = QFormLayout()
        form.setSpacing(GAP)
        form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)

        self.list = ListWidget()
        self.list.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.list.itemSelectionChanged.connect(self._sync)
        # пустой список сам говорит, что в него класть
        # пустое место — карточкой, как поле, куда бросать файлы: иначе оно не
        # читается как то, куда их класть
        self.empty = CardWidget()
        empty_layout = QVBoxLayout(self.empty)
        self.empty_label = BodyLabel(TEXT["files_empty"])
        self.empty_label.setAlignment(Qt.AlignCenter)
        self.empty_label.setWordWrap(True)
        empty_layout.addWidget(self.empty_label)
        self.stack = QStackedWidget()
        self.stack.addWidget(self.empty)
        self.stack.addWidget(self.list)

        self.add_files_btn = PushButton(TEXT["add_files"])
        self.add_files_btn.clicked.connect(self._pick_files)
        self.add_folder_btn = PushButton(TEXT["add_folder"])
        self.add_folder_btn.clicked.connect(self._pick_folder)
        self.remove_btn = PushButton(TEXT["remove"])
        self.remove_btn.clicked.connect(self._remove_selected)
        self.clear_btn = PushButton(TEXT["clear"])
        self.clear_btn.clicked.connect(self._clear)
        # кнопки столбиком сбоку, а не рядом под списком: в ряд четыре
        # надписи задавали ширину всей вкладки, и на широком шрифте она
        # вылезала за окно. Сверху — пополнить список, снизу — убрать из него
        buttons = QVBoxLayout()
        buttons.setSpacing(GAP)
        for button in (self.add_files_btn, self.add_folder_btn):
            buttons.addWidget(button)
        buttons.addStretch(1)
        for button in (self.remove_btn, self.clear_btn):
            buttons.addWidget(button)

        files = QHBoxLayout()
        files.setSpacing(GAP)
        files.addWidget(self.stack, 1)
        files.addLayout(buttons)
        holder = QWidget()
        holder.setLayout(files)
        files.setContentsMargins(0, 0, 0, 0)
        form.addRow(BodyLabel(TEXT["files"]), holder)

        # выпадающий список, а не сегмент: вариантов пять
        self.side_box = ComboBox()
        for side in te.info()["resize_sides"]:
            self.side_box.addItem(TEXT["side_item"] % side, userData=side)
        self.side_box.currentIndexChanged.connect(self._sync)
        side_row = QHBoxLayout()
        side_row.setSpacing(GAP)
        side_row.addWidget(self.side_box)
        side_row.addWidget(CaptionLabel(TEXT["side_note"]))
        side_row.addStretch(1)
        form.addRow(BodyLabel(TEXT["side"]), side_row)
        root.addLayout(form, 1)

        self.run_btn = PrimaryPushButton()
        self.run_btn.setDefault(True)
        self.run_btn.clicked.connect(self._run_clicked)
        run_row = QHBoxLayout()
        run_row.addStretch(1)
        run_row.addWidget(self.run_btn)
        root.addLayout(run_row)

        log_layout = QVBoxLayout()
        log_layout.setSpacing(GAP)
        log_layout.addWidget(StrongBodyLabel(TEXT["log"]))
        self.log = PlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setPlaceholderText(TEXT["log_empty"])
        log_layout.addWidget(self.log, 1)
        root.addLayout(log_layout, 1)

        self.state = BodyLabel()
        self.state.setWordWrap(True)
        self.progress = ProgressBar()
        self.progress.setTextVisible(False)
        self.progress.setMaximumHeight(self.state.sizeHint().height())
        self.progress.hide()
        state_row = QHBoxLayout()
        state_row.setSpacing(GAP)
        state_row.addWidget(self.state, 2)
        state_row.addWidget(self.progress, 1)
        root.addLayout(state_row)

        for key, slot in ((Qt.Key_Return, self._enter), (Qt.Key_Enter, self._enter),
                          (Qt.Key_Escape, self._escape)):
            QShortcut(QKeySequence(key), self, slot,
                      context=Qt.WidgetWithChildrenShortcut)
        QShortcut(QKeySequence.Delete, self.list, self._remove_selected,
                  context=Qt.WidgetShortcut)

    # ---------- состояние ----------

    def side(self) -> int:
        return int(self.side_box.currentData())

    def running(self) -> bool:
        return self.job is not None and self.job.isRunning()

    def _sync(self) -> None:
        """Одно место, где считается, что доступно и что написано на кнопке."""
        busy = self.running()
        self.run_btn.setText(TEXT["stop"] if busy else TEXT["run"] % self.side())
        self.run_btn.setEnabled(busy or bool(self.files))
        self.stack.setCurrentWidget(self.list if self.files else self.empty)
        for button in (self.add_files_btn, self.add_folder_btn):
            button.setEnabled(not busy)
        self.remove_btn.setEnabled(not busy and bool(self.list.selectedItems()))
        self.clear_btn.setEnabled(not busy and bool(self.files))
        self.side_box.setEnabled(not busy)
        if busy:
            return                                  # текст ставит _step
        if self.files:
            self.state.setText(TEXT["state_ready"] % len(self.files))
        else:
            self.state.setText(TEXT["state_empty"])

    # ---------- список ----------

    def add(self, paths) -> None:
        """Добавить файлы и папки. Уже стоящие в списке второй раз не встают."""
        found = te.resize_collect(paths)
        known = {str(p.resolve()).lower() for p in self.files}
        fresh = [p for p in found if str(p.resolve()).lower() not in known]
        if not found:
            self._say("muted", TEXT["added_none"])
        for path in fresh:
            self.files.append(path)
            self.list.addItem(str(path))
        self._sync()

    def _pick_files(self) -> None:
        start = str(self.files[-1].parent) if self.files else ""
        picked, _ = QFileDialog.getOpenFileNames(
            self, TEXT["pick_files"], start, TEXT["pick_filter"])
        if picked:
            self.add(picked)

    def _pick_folder(self) -> None:
        start = str(self.files[-1].parent) if self.files else ""
        picked = QFileDialog.getExistingDirectory(self, TEXT["pick_folder"], start)
        if picked:
            self.add([picked])

    def _remove_selected(self) -> None:
        if self.running():
            return
        rows = sorted((self.list.row(item) for item in self.list.selectedItems()),
                      reverse=True)
        for row in rows:
            self.list.takeItem(row)
            del self.files[row]
        self._sync()

    def _clear(self) -> None:
        self.list.clear()
        self.files = []
        self._sync()

    # ---------- работа ----------

    def _enter(self) -> None:
        if self.run_btn.isEnabled():
            self.run_btn.click()

    def _escape(self) -> None:
        if self.running():
            self._stop()

    def _run_clicked(self) -> None:
        if self.running():
            self._stop()
            return
        self.settings.setValue("resize_side", self.side())
        self.progress.setRange(0, len(self.files))
        self.progress.setValue(0)
        self.progress.show()
        self.state.setText(TEXT["state_running"] % (0, len(self.files)))
        self.job = Job(self.files, self.side(), self)
        self.job.file_done.connect(self._file_done)
        self.job.step.connect(self._step)
        self.job.batch_done.connect(self._batch_end)
        self.job.start()
        self._sync()

    def _stop(self) -> None:
        if self.running():
            self.job.stop()
            self.job.wait(10000)
        self.progress.hide()
        self._say("muted", TEXT["stopped"])
        self._sync()

    def _file_done(self, name: str, outcome) -> None:
        if outcome.state == "done":
            values = (name,) + outcome.old + outcome.new
            if outcome.note:
                self._say("done", TEXT["done_note"] % (values + (outcome.note,)))
            else:
                self._say("done", TEXT["done"] % values)
        elif outcome.state == "same":
            self._say("muted", TEXT["same"] % ((name,) + outcome.old))
        elif outcome.state == "refused":
            self._say("error", TEXT["refused"] % (name, outcome.note))
        else:
            self._say("error", TEXT["error"] % (name, outcome.note))

    def _step(self, done: int, total: int) -> None:
        self.progress.setValue(done)
        self.state.setText(TEXT["state_running"] % (done, total))

    def _batch_end(self, counts) -> None:
        self.progress.hide()
        self._say("muted", TEXT["batch_done"] % (
            counts["done"], counts["same"], counts["refused"], counts["error"]))
        if counts["done"]:
            # отмена возможна, и человек должен знать где
            self._say("muted", TEXT["backup"] % te.info()["backup_dir"])
        self.job = None
        self._sync()

    # ---------- журнал ----------

    def _say(self, role: str, line: str) -> None:
        self.entries.append((role, line))
        self._append(role, line)

    def _append(self, role: str, line: str) -> None:
        color = role_color(self.palette(), role).name()
        self.log.appendHtml('<span style="color:%s">%s</span>' % (color, line))
        bar = self.log.verticalScrollBar()
        bar.setValue(bar.maximum())

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() in (QEvent.Type.PaletteChange,
                            QEvent.Type.ApplicationPaletteChange):
            self.log.clear()
            for role, line in self.entries:
                self._append(role, line)

    # ---------- окно ----------

    def activate(self) -> None:
        if self.files:
            self.run_btn.setFocus()
        else:
            self.add_files_btn.setFocus()

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls() and not self.running():
            event.acceptProposedAction()

    def dropEvent(self, event):
        self.add([url.toLocalFile() for url in event.mimeData().urls()])

    def shutdown(self) -> None:
        if self.running():
            self.job.stop()
            self.job.wait(10000)
        self.settings.setValue("resize_side", self.side())

    def closeEvent(self, event):
        self.shutdown()
        super().closeEvent(event)

    def _restore(self) -> None:
        try:
            side = int(self.settings.value("resize_side", DEFAULT_SIDE))
        except (TypeError, ValueError):
            side = DEFAULT_SIDE
        index = self.side_box.findData(side)
        self.side_box.setCurrentIndex(index if index >= 0
                                      else self.side_box.findData(DEFAULT_SIDE))
