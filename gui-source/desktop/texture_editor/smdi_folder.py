# -*- coding: utf-8 -*-
"""Вкладка «Фильтр SMDI по папке» в ``texture_editor``.

Оболочка над ``kits/texture_kit/smdi_filter.py``. Что обрабатывать, выбирается
сегментом из трёх взаимоисключающих вариантов: то, что уже лежит в папке; то,
что в ней появится; и то и другое. Сегмент называет объём работы, кнопка —
само действие, поэтому надписи не дублируют друг друга.

Фильтр однократен по метке в png, поэтому слежение не зацикливается: файл,
который мы только что записали, метку несёт и в следующую проверку не попадёт.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

_HERE = Path(__file__).resolve().parent
_ROOT = _HERE.parents[1]
for _p in (str(_HERE), str(_ROOT), str(_HERE.parent)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from PySide6.QtCore import QEvent, QSettings, Qt, QThread, QTimer, Signal  # noqa: E402
from PySide6.QtGui import QColor, QKeySequence, QPalette, QShortcut          # noqa: E402
from PySide6.QtWidgets import (                                           # noqa: E402
    QFileDialog, QFormLayout, QHBoxLayout, QSizePolicy, QVBoxLayout, QWidget,
)
from qfluentwidgets import (                                              # noqa: E402
    BodyLabel, CaptionLabel, LineEdit, PlainTextEdit, PrimaryPushButton, ProgressBar,
    PushButton, SegmentedWidget, SpinBox, StrongBodyLabel,
)

import remote as te                                                        # noqa: E402

# --------------------------------------------------------------------------
# Режимы. Порядок как читают: сперва части, потом их сумма.
# --------------------------------------------------------------------------

EXISTING, INCOMING, BOTH = 0, 1, 2

# --------------------------------------------------------------------------
# Текст. Весь — здесь: правка формулировки не ищется по коду, а состав
# ключей проверяется тестом.
# --------------------------------------------------------------------------

TEXT = {
    "tab": "Фильтр SMDI по папке",

    "folder": "Папка",
    "folder_hint": "Папка с текстурами, например P:\\KR\\…\\data",
    "browse": "Обзор…",
    "browse_title": "Папка с текстурами",

    "sp": "Глубина подавления (sp)",
    "sp_note": "75 — как в TexView; больше — глуше блик",
    "sp_hint": ("Насколько сильно гасится блик на шершавых местах.\n"
                "75 — значение фильтра, который применяли руками в TexView."),

    "scope": "Обрабатывать",
    "scope_existing": "что есть",
    "scope_incoming": "что появится",
    "scope_both": "и то, и другое",
    "scope_existing_hint": "Все _smdi, которые уже лежат в папке.",
    "scope_incoming_hint": ("Каждый _smdi, который появится в папке\n"
                            "или будет пересохранён."),
    "scope_both_hint": "Сперва то, что лежит, потом всё, что появится.",

    "run_existing": "Прогнать",
    "run_incoming": "Следить",
    "run_both": "Прогнать и следить",
    "stop": "Остановить",

    "log": "Журнал прогона",
    "log_empty": ("Здесь появятся прогнанные файлы.\n"
                  "Выберите папку — и станет видно, сколько их ждёт прогона."),

    "state_nofolder": "Выберите папку с текстурами.",
    "state_gone": "Папка не найдена — выберите другую.",
    "state_idle": "Готово к работе.",
    "state_running": "Прогон: %d из %d",
    "state_watching": "Слежу за папкой — новые _smdi прогоняются сами.",

    "found": "%s — файлов _smdi: %d, к прогону: %d.",
    "found_none": "%s — файлов _smdi нет.",

    "done": "%s: готово",
    "skipped": "%s: уже прогнан",
    "refused": "%s: пропущен",
    "error_busy": "%s: файл занят другой программой — закройте её и повторите.",
    "error_denied": "%s: нет прав на запись — снимите с файла «только чтение».",
    "error": "%s: не прогнан — %s",

    "batch_done": "Прогон закончен: %d из %d.",
    "backup": "Оригиналы — в %s.",
    "batch_nothing": "Все _smdi в папке уже прогнаны.",
    "stopped": "Остановлено.",
}

# --------------------------------------------------------------------------
# Сетка и цвета. Каждое — одним набором на всё окно.
# --------------------------------------------------------------------------

#: надпись кнопки для каждого режима. Ключи названы буквально, а не собраны
#: из кусков: иначе формулировку не найти по коду
RUN_LABEL = {
    EXISTING: TEXT["run_existing"],
    INCOMING: TEXT["run_incoming"],
    BOTH: TEXT["run_both"],
}

MARGIN = 12     #: поле окна
GAP = 8         #: между соседними строками
SECTION = 16    #: между смысловыми блоками
SP_CHARS = 7    #: ширина поля числа — в знаках, а не в пикселях

#: роль -> (цвет на светлой теме, цвет на тёмной). Контраст к подложке темы
#: не ниже 4.5:1 — проверено измерением, см. tests/desktop/test_texture_studio_smdi.py
_COLORS = {
    "done": ("#2e7d32", "#7ee081"),
    "error": ("#c62828", "#ff9c94"),
}


def blend(front: QColor, back: QColor, share: float) -> QColor:
    """Подмешать подложку к цвету. Полупрозрачность тут не годится: журнал
    рисуется html-ом, а в нём цвет задаётся без альфы — она бы потерялась."""
    return QColor(
        round(front.red() * (1 - share) + back.red() * share),
        round(front.green() * (1 - share) + back.green() * share),
        round(front.blue() * (1 - share) + back.blue() * share),
    )


def role_color(palette: QPalette, role: str) -> QColor:
    """Цвет роли для текущей темы. Единственное место, где они названы."""
    if role == "muted":
        return blend(palette.color(QPalette.Text), palette.color(QPalette.Base), 0.45)
    light, dark = _COLORS[role]
    is_dark = palette.color(QPalette.Window).lightness() < 128
    return QColor(dark if is_dark else light)


# --------------------------------------------------------------------------
# Контролы
# --------------------------------------------------------------------------

class Segment(QWidget):
    """Сегмент: три коротких взаимоисключающих варианта, выбор виден без
    раскрытия. Тот же SegmentedWidget, что у остальных тулз; подсказка
    варианта — на нём самом."""

    changed = Signal(int)

    def __init__(self, options: List[Tuple[str, str]], parent=None):
        super().__init__(parent)
        box = QHBoxLayout(self)
        box.setContentsMargins(0, 0, 0, 0)
        self.bar = SegmentedWidget(self)
        self.bar.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self._current = EXISTING
        for index, (label, hint) in enumerate(options):
            self.bar.addItem(str(index), label, lambda *_, i=index: self._picked(i))
            self.bar.widget(str(index)).setToolTip(hint)
        box.addWidget(self.bar)
        box.addStretch(1)
        self.bar.setCurrentItem(str(EXISTING))

    def _picked(self, index: int) -> None:
        if index != self._current:
            self._current = index
            self.changed.emit(index)

    def current(self) -> int:
        return self._current

    def set_current(self, index: int) -> None:
        if 0 <= index < len(self.bar.items):
            self.bar.setCurrentItem(str(index))
            self._picked(index)

    def set_locked(self, locked: bool) -> None:
        """Во время работы выбор менять нельзя, но видеть его надо: выбранный
        сегмент остаётся живым, гаснут только остальные (п. 65)."""
        for key, item in self.bar.items.items():
            item.setEnabled(not locked or int(key) == self._current)


class SpBox(SpinBox):
    """Поле числа, которое не меняется от колеса под курсором: колесо листает
    окно, а не правит значение, на котором человек не стоял.

    Значение целое: в rvmat ``specularPower`` записан целым у 98% материалов,
    и дробная часть в поле только мешала бы попадать по нужному числу. Вьюер
    спрашивает его так же — у одной величины не должно быть двух видов."""

    def wheelEvent(self, event):
        if self.hasFocus():
            super().wheelEvent(event)
        else:
            event.ignore()


# --------------------------------------------------------------------------
# Работа
# --------------------------------------------------------------------------

def describe(exc: Exception) -> str:
    """Ключ текста ошибки: она обязана называть причину и следующий шаг, а не
    номер errno. Всё, чего не узнали, идёт с исходным текстом."""
    if getattr(exc, "winerror", None) == 32:
        return "busy"
    if isinstance(exc, PermissionError):
        return "denied"
    return str(exc)


class Batch(QThread):
    """Прогон списка файлов. Отдельный поток: окно должно оставаться живым,
    а журнал — наполняться по ходу, а не одним куском в конце."""

    file_done = Signal(str, str, str)   #: имя файла, состояние, пояснение
    step = Signal(int, int)             #: сделано, всего
    batch_done = Signal(int, int)       #: применено, всего

    def __init__(self, files: List[Path], root: Path, sp: float, parent=None):
        super().__init__(parent)
        self._files = list(files)
        self._root = root
        self._sp = sp
        self._cli: Optional[te.CliJob] = None
        self._stopping = False

    def stop(self) -> None:
        self._stopping = True
        if self._cli is not None:
            self._cli.stop()

    def run(self) -> None:
        """Фильтр гоняет TextureEditor.exe smdi; здесь — его события в сигналы окна."""
        done = {"applied": 0}
        self._cli = te.CliJob(["smdi", "--root", str(self._root), "--sp", str(self._sp)], self._files)
        self._cli.event.connect(lambda ev: self._event(ev, done))
        if not self._stopping:
            self._cli.run()                 # в этом же потоке: события идут по ходу
        self.batch_done.emit(done["applied"], len(self._files))

    def _event(self, ev: dict, done: dict) -> None:
        if ev.get("event") == "file":
            done["applied"] += ev["state"] == "applied"
            self.file_done.emit(ev["name"], ev["state"], ev.get("note") or "")
        elif ev.get("event") == "step":
            self.step.emit(int(ev["done"]), int(ev["total"]))
        elif ev.get("event") == "problem":
            self.file_done.emit("", "error", ev.get("text", ""))


# --------------------------------------------------------------------------
# Окно
# --------------------------------------------------------------------------

class SmdiPage(QWidget):

    POLL_MS = 2000        #: как часто заглядывать в папку при слежении
    COUNT_DELAY_MS = 400  #: пауза в наборе пути, после которой считаем файлы

    def __init__(self, folder: str = "", settings: QSettings | None = None,
                 parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)

        # хранилище передаётся снаружи, чтобы тест не писал в профиль человека
        self.settings = settings if settings is not None else QSettings("KR", "SmdiStudio")
        self.batch: Batch | None = None
        self.watching = False
        self.watch_after_batch = False
        self.seen: Dict[Path, Tuple[float, int]] = {}
        self.entries: List[Tuple[str, str]] = []   #: (роль, строка) — журнал
        self.counted: Path | None = None           #: папка, про которую уже сказано

        self._build()
        self._restore(folder)

        self.timer = QTimer(self)
        self.timer.setInterval(self.POLL_MS)
        self.timer.timeout.connect(self._poll)

        # путь набирают по букве, а пересчёт открывает файлы: считаем, когда
        # человек остановился
        self.count_timer = QTimer(self)
        self.count_timer.setSingleShot(True)
        self.count_timer.setInterval(self.COUNT_DELAY_MS)
        self.count_timer.timeout.connect(self._count)
        self.path_edit.textChanged.connect(self.count_timer.start)

        self.path_edit.setFocus()
        self._sync()
        self._count()

    # ---------- сборка ----------

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, MARGIN, 0, MARGIN)
        root.setSpacing(SECTION)

        form = QFormLayout()
        form.setSpacing(GAP)
        form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)

        self.path_edit = LineEdit()
        self.path_edit.setPlaceholderText(TEXT["folder_hint"])
        self.path_edit.setClearButtonEnabled(True)
        self.path_edit.textChanged.connect(self._sync)
        self.browse_btn = PushButton(TEXT["browse"])
        self.browse_btn.clicked.connect(self._browse)
        form.addRow(BodyLabel(TEXT["folder"]),
                    self._row(self.path_edit, self.browse_btn, stretch_first=True))

        self.sp_box = SpBox()
        self.sp_box.setRange(1, 1000)
        self.sp_box.setValue(int(round(te.info()["default_sp"])))
        self.sp_box.setToolTip(TEXT["sp_hint"])
        self.sp_box.setFocusPolicy(Qt.StrongFocus)
        self.sp_box.setMinimumWidth(
            self.fontMetrics().horizontalAdvance("0") * SP_CHARS)
        # пояснение видимое, а не спрятанное во всплывающую подсказку
        self.sp_note = CaptionLabel(TEXT["sp_note"])
        form.addRow(BodyLabel(TEXT["sp"]), self._row(self.sp_box, self.sp_note))

        self.scope = Segment([
            (TEXT["scope_existing"], TEXT["scope_existing_hint"]),
            (TEXT["scope_incoming"], TEXT["scope_incoming_hint"]),
            (TEXT["scope_both"], TEXT["scope_both_hint"]),
        ])
        self.scope.changed.connect(lambda _index: self._sync())
        form.addRow(BodyLabel(TEXT["scope"]), self.scope)
        root.addLayout(form)

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
        # высота как у строки состояния: тогда появление полосы не двигает
        # раскладку и не приходится анимировать скачок
        self.progress.setMaximumHeight(self.state.sizeHint().height())
        self.progress.hide()
        state_row = QHBoxLayout()
        state_row.setSpacing(GAP)
        state_row.addWidget(self.state, 2)
        state_row.addWidget(self.progress, 1)
        root.addLayout(state_row)

        # только внутри вкладки: иначе Enter на соседней запускал бы прогон
        for key, slot in ((Qt.Key_Return, self._enter), (Qt.Key_Enter, self._enter),
                          (Qt.Key_Escape, self._escape)):
            QShortcut(QKeySequence(key), self, slot,
                      context=Qt.WidgetWithChildrenShortcut)

    @staticmethod
    def _row(*widgets, stretch_first: bool = False) -> QWidget:
        """Строка контролов без собственных полей: отступы задаёт сетка окна."""
        box = QHBoxLayout()
        box.setContentsMargins(0, 0, 0, 0)
        box.setSpacing(GAP)
        for i, widget in enumerate(widgets):
            box.addWidget(widget, 1 if (stretch_first and i == 0) else 0)
        if not stretch_first:
            box.addStretch(1)
        holder = QWidget()
        holder.setLayout(box)
        return holder

    # ---------- состояние ----------

    def folder(self) -> Path:
        return Path(self.path_edit.text().strip().strip('"'))

    def folder_ok(self) -> bool:
        text = self.path_edit.text().strip()
        return bool(text) and self.folder().is_dir()

    def running(self) -> bool:
        return self.batch is not None and self.batch.isRunning()

    def busy(self) -> bool:
        return self.watching or self.running()

    def _sync(self) -> None:
        """Одно место, где считается, что доступно и что написано на кнопке."""
        busy = self.busy()
        self.run_btn.setText(
            TEXT["stop"] if busy else RUN_LABEL[self.scope.current()])
        self.run_btn.setEnabled(busy or self.folder_ok())

        # во время работы поля читаются и копируются, но не правятся
        self.path_edit.setReadOnly(busy)
        self.sp_box.setReadOnly(busy)
        self.sp_box.setSymbolVisible(not busy)       # стрелки правили бы и «только чтение»
        self.browse_btn.setEnabled(not busy)
        self.scope.set_locked(busy)

        if self.running():
            pass                                   # текст ставит _step
        elif self.watching:
            self.state.setText(TEXT["state_watching"])
        elif not self.path_edit.text().strip():
            self.state.setText(TEXT["state_nofolder"])
        elif not self.folder_ok():
            self.state.setText(TEXT["state_gone"])
        else:
            self.state.setText(TEXT["state_idle"])

    # ---------- действия ----------

    def _browse(self) -> None:
        picked = QFileDialog.getExistingDirectory(
            self, TEXT["browse_title"], self.path_edit.text().strip())
        if picked:
            self.path_edit.setText(str(Path(picked)))

    def _enter(self) -> None:
        if self.run_btn.isEnabled():
            self.run_btn.click()

    def _escape(self) -> None:
        """Esc отменяет работу. Вкладку он не закрывает: закрыть её нельзя, а
        закрыть по Esc всё приложение — слишком дорогая ошибка."""
        if self.busy():
            self._stop()

    def _remember(self) -> None:
        self.settings.setValue("folder", self.path_edit.text().strip())
        self.settings.setValue("sp", self.sp_box.value())
        self.settings.setValue("scope", self.scope.current())

    def _run_clicked(self) -> None:
        if self.busy():
            self._stop()
            return
        self._remember()
        scope = self.scope.current()
        self.watch_after_batch = scope == BOTH

        if scope == INCOMING:
            self._watch_on()
            return

        files = te.scan_unfiltered(self.folder())
        if files:
            self._batch_start(files)
        elif self.watch_after_batch:
            self._say("muted", TEXT["batch_nothing"])
            self.watch_after_batch = False
            self._watch_on()
        else:
            self._say("muted", TEXT["batch_nothing"])

    def _batch_start(self, files: List[Path]) -> None:
        self.progress.setRange(0, len(files))
        self.progress.setValue(0)
        self.progress.show()
        self.state.setText(TEXT["state_running"] % (0, len(files)))
        self.batch = Batch(files, self.folder(), self.sp_box.value(), self)
        self.batch.file_done.connect(self._file_done)
        self.batch.step.connect(self._step)
        self.batch.batch_done.connect(self._batch_end)
        self.batch.start()
        self._sync()

    def _watch_on(self) -> None:
        self.watching = True
        self.seen = te.scan_snapshot(self.folder())
        self.timer.start()
        self._sync()

    def _stop(self) -> None:
        self.watch_after_batch = False
        self.watching = False
        self.timer.stop()
        if self.running():
            self.batch.stop()
            self.batch.wait(5000)
        self.progress.hide()
        self._say("muted", TEXT["stopped"])
        self._sync()

    def _poll(self) -> None:
        if self.running():
            return
        if not self.folder_ok():
            self.state.setText(TEXT["state_gone"])
            return
        ready, self.seen = te.scan_pending(self.folder(), time.time(), self.seen)
        if ready:
            self._batch_start(ready)

    # ---------- отклик работы ----------

    def _file_done(self, name: str, state: str, detail: str) -> None:
        if state == "applied":
            self._say("done", TEXT["done"] % name)
        elif state == "skipped":
            self._say("muted", TEXT["skipped"] % name)
        elif state == "refused":
            self._say("muted", TEXT["refused"] % name)
        elif detail == "busy":
            self._say("error", TEXT["error_busy"] % name)
        elif detail == "denied":
            self._say("error", TEXT["error_denied"] % name)
        else:
            self._say("error", TEXT["error"] % (name, detail))

    def _step(self, done: int, total: int) -> None:
        self.progress.setValue(done)
        self.state.setText(TEXT["state_running"] % (done, total))

    def _batch_end(self, applied: int, total: int) -> None:
        self.progress.hide()
        if not self.watching:
            self._say("muted", TEXT["batch_done"] % (applied, total))
        if applied:
            # отмена возможна, и человек должен знать где: это единственное
            # место, где названа папка с оригиналами
            self._say("muted", TEXT["backup"] % te.info()["smdi_backup_dirname"])
        # снимок обновляем всегда: файлы, что мы сами переписали, не должны
        # выглядеть изменившимися для следующей проверки
        self.seen = te.scan_snapshot(self.folder())
        if self.watch_after_batch:
            self.watch_after_batch = False
            self._watch_on()
        else:
            self._sync()

    # ---------- журнал ----------

    def _count(self) -> None:
        """Сказать в журнал, что есть в выбранной папке. Повторно про ту же
        папку не говорим: иначе правка пути насорит одинаковыми строками."""
        if self.running() or not self.folder_ok():
            return
        folder = self.folder()
        if folder == self.counted:
            return
        self.counted = folder
        total, todo = te.scan_census(folder)
        if total:
            self._say("muted", TEXT["found"] % (folder, total, todo))
        else:
            self._say("muted", TEXT["found_none"] % folder)

    def _say(self, role: str, line: str) -> None:
        self.entries.append((role, line))
        self._append(role, line)

    def _append(self, role: str, line: str) -> None:
        color = role_color(self.palette(), role).name()
        self.log.appendHtml('<span style="color:%s">%s</span>' % (color, line))
        bar = self.log.verticalScrollBar()
        bar.setValue(bar.maximum())

    def _relog(self) -> None:
        """Перерисовать журнал в цветах новой темы: строки, выданные один раз,
        остались бы от старой."""
        self.log.clear()
        for role, line in self.entries:
            self._append(role, line)

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() in (QEvent.Type.PaletteChange,
                            QEvent.Type.ApplicationPaletteChange):
            self._relog()

    # ---------- окно ----------

    def dragEnterEvent(self, event):
        urls = event.mimeData().urls()
        if len(urls) == 1 and Path(urls[0].toLocalFile()).is_dir() and not self.busy():
            event.acceptProposedAction()

    def dropEvent(self, event):
        self.path_edit.setText(str(Path(event.mimeData().urls()[0].toLocalFile())))

    def shutdown(self) -> None:
        """Погасить работу и запомнить выбор. Зовёт главное окно при
        закрытии: вложенная вкладка своего closeEvent не получает."""
        self.timer.stop()
        if self.running():
            self.batch.stop()
            self.batch.wait(5000)
        self._remember()

    def activate(self) -> None:
        self.path_edit.setFocus()

    def closeEvent(self, event):
        self.shutdown()
        super().closeEvent(event)

    def _restore(self, folder: str) -> None:
        """Работа сама не начинается: помним, что обрабатывать, но запускает
        человек кнопкой."""
        self.path_edit.setText(folder or str(self.settings.value("folder", "")))
        try:
            self.sp_box.setValue(
                int(round(float(self.settings.value("sp", te.info()["default_sp"])))))
        except (TypeError, ValueError):
            self.sp_box.setValue(int(round(te.info()["default_sp"])))
        try:
            self.scope.set_current(int(self.settings.value("scope", EXISTING)))
        except (TypeError, ValueError):
            self.scope.set_current(EXISTING)

