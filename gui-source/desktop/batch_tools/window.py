# -*- coding: utf-8 -*-
"""Окно массовой тулзы — [KR] Texture Converter, [KR] Model Converter, [KR] DeBinarizer.

Заказ юзера 24.10.2026: тулзы для массовой работы с файлами. Окно одно на три,
различия — в описании (spec.ToolSpec). Окно — оболочка над командной строкой
(`runner.CliRun`): план берёт у `--dry-run`, делает отмеченное через
`--jobs-file`. Оформление — как [KR] Sound Converter и [KR] Project Builder.
"""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Dict, List, Optional

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QAbstractItemView, QFileDialog, QGridLayout, QHBoxLayout, QHeaderView, QSizePolicy,
    QStackedWidget, QTableWidgetItem, QVBoxLayout, QWidget)
from qfluentwidgets import (
    BodyLabel, CaptionLabel, FluentIcon, LineEdit, ListWidget, PlainTextEdit, PrimaryPushButton,
    ProgressBar, PushButton, SegmentedWidget, StrongBodyLabel, SwitchButton, TableWidget,
    TransparentPushButton, TransparentToolButton, qconfig)

from qts_ui import tokens
from qts_ui.card import Card
from qts_ui.frame import ToolWindow
from qts_ui.rows import Columns, setting_row, shrink
from runner import CliRun, cli_command
from spec import SEGMENT, SWITCH, ToolSpec
from store import Store
from texts import T

COL_CHECK, COL_STATE, COL_SRC, COL_OUT = range(4)
MIN = (720, 800)                  # +40 — своя шапка окна; карточка настроек в четыре строки и таблица
INPUTS_H = 84
REPORT_H = 110
TABLE_MIN_H = 150                 # таблица не схлопывается в одну строку под карточкой настроек
STATE_TEXT = {"planned": "state.planned", "overwrite": "state.overwrite", "skipped": "state.skipped",
              "converted": "state.converted", "warning": "state.warning", "failed": "state.failed"}
ROLE = {"planned": "text", "overwrite": "warning", "skipped": "text_dim",
        "converted": "success", "warning": "warning", "failed": "error"}
CHECKABLE = ("planned", "overwrite")
#: ключи текстов по тулзам — буквально (п. 66)
INPUT_TEXTS = {"textures": ("textures.inputs", "textures.drop", "textures.pick"),
               "models": ("models.inputs", "models.drop", "models.pick"),
               "debin": ("debin.inputs", "debin.drop", "debin.pick"),
               "pbo": ("pbo.inputs", "pbo.drop", "pbo.pick"),
               "anm": ("anm.inputs", "anm.drop", "anm.pick")}


class BatchWindow(ToolWindow):
    def __init__(self, spec: ToolSpec, store: Store, name: str, version: str):
        super().__init__(getattr(FluentIcon, spec.icon), image=spec.exe)      # своя шапка, как в QTS (qts_ui.frame)
        self.spec = spec
        self.store = store
        self.run: Optional[CliRun] = None
        self.working = False
        self.rows: Dict[str, int] = {}               # исходник → строка таблицы
        self.files: List[dict] = []                  # события плана по порядку
        self.result: Optional[dict] = None
        self.problems: List[str] = []
        self.report_lines: List[str] = []
        self.step_text = ""
        self._done = 0
        self._jobs_file: Optional[str] = None
        self.setWindowTitle("%s %s" % (name, version))
        self.setMinimumSize(*MIN)
        w, h = self.store.window.get("size", MIN)
        self.resize(max(w, MIN[0]), max(h, MIN[1]))
        self.setAcceptDrops(True)                    # файлы и папки — перетаскиванием (п. 49)
        self._build()
        self._show_inputs()
        qconfig.themeChanged.connect(self._paint)

    # ================================================================== сборка окна
    def _build(self) -> None:
        title, drop_text, _ = INPUT_TEXTS[self.spec.prefix]
        root = QVBoxLayout(self.body)
        root.setContentsMargins(tokens.SPACE_M, tokens.SPACE_M, tokens.SPACE_M, tokens.SPACE_M)
        root.setSpacing(tokens.SPACE_S)

        head = QHBoxLayout()
        head.addWidget(StrongBodyLabel(T(title), self))
        head.addStretch(1)
        self.add_files = TransparentToolButton(FluentIcon.ADD, self)
        self.add_files.setToolTip(T("inputs.add_files"))
        self.add_files.clicked.connect(self._pick_files)
        head.addWidget(self.add_files)
        self.add_folder = TransparentToolButton(FluentIcon.FOLDER_ADD, self)
        self.add_folder.setToolTip(T("inputs.add_folder"))
        self.add_folder.clicked.connect(self._pick_folder)
        head.addWidget(self.add_folder)
        self.remove_btn = TransparentToolButton(FluentIcon.REMOVE, self)
        self.remove_btn.setToolTip(T("inputs.remove"))
        self.remove_btn.clicked.connect(self._remove_inputs)
        head.addWidget(self.remove_btn)
        root.addLayout(head)

        # куда перетаскивать — пунктирная зона, как «Что паковать» у Project Builder
        drop_zone = Card(self, dashed=True, padding=tokens.SPACE_XS)
        self.inputs_stack = QStackedWidget(drop_zone)
        self.inputs_stack.setFixedHeight(INPUTS_H)
        drop_zone.box.addWidget(self.inputs_stack)
        empty = QWidget(self.inputs_stack)
        el = QVBoxLayout(empty)
        el.addStretch(1)
        drop = shrink(BodyLabel(T(drop_text), empty))
        drop.setAlignment(Qt.AlignCenter)
        el.addWidget(drop)
        el.addStretch(1)
        self.inputs_stack.addWidget(empty)
        self.inputs = ListWidget(self.inputs_stack)
        self.inputs.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.inputs.setTextElideMode(Qt.ElideMiddle)
        self.inputs.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.inputs.itemSelectionChanged.connect(self._sync)
        QShortcut(QKeySequence.Delete, self.inputs, activated=self._remove_inputs,
                  context=Qt.WidgetShortcut)
        self.inputs_stack.addWidget(self.inputs)
        root.addWidget(drop_zone)

        # --- настройки тулзы: своя карточка, строки как во всех окнах — название и под ним
        # пояснение, контрол справа в слоте одной ширины (замечание юзера 25.10.2026: «мешанина»)
        root.addSpacing(tokens.SPACE_XS)
        root.addWidget(StrongBodyLabel(T("settings.title"), self))
        self.controls: Dict[str, QWidget] = {}
        self.option_rows: Dict[str, tuple] = {}
        rows = []
        for opt in self.spec.options:
            control = self._control(opt)
            row = setting_row(T(opt.label), T(opt.desc), control)
            rows.append(row)
            self.controls[opt.key] = control
            self.option_rows[opt.key] = (row, row.desc_label, control)
        settings_card = Card(self)
        self.option_columns = Columns(rows, settings_card)
        settings_card.box.addWidget(self.option_columns)
        root.addWidget(settings_card)
        root.addSpacing(tokens.SPACE_XS)

        th = QHBoxLayout()
        th.addWidget(StrongBodyLabel(T("files.title"), self))
        th.addStretch(1)
        self.all_btn = TransparentPushButton(T("files.all"), self)
        self.all_btn.clicked.connect(self._toggle_all)
        th.addWidget(self.all_btn)
        root.addLayout(th)
        self.table = TableWidget(self)
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["", T("col.state"), T("col.src"), T("col.out")])
        self.table.verticalHeader().hide()
        self.table.setBorderVisible(True)
        self.table.setBorderRadius(tokens.RADIUS_CARD)
        self.table.setWordWrap(False)
        self.table.setTextElideMode(Qt.ElideMiddle)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        hdr = self.table.horizontalHeader()
        for col in (COL_CHECK, COL_STATE):
            hdr.setSectionResizeMode(col, QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(COL_SRC, QHeaderView.Stretch)
        hdr.setSectionResizeMode(COL_OUT, QHeaderView.Stretch)
        self.table.itemChanged.connect(lambda item: self._sync() if item.column() == COL_CHECK else None)
        self.table.setMinimumHeight(TABLE_MIN_H)
        root.addWidget(self.table, 1)

        self.summary = shrink(CaptionLabel("", self))
        root.addWidget(self.summary)
        self.progress = ProgressBar(self)
        root.addWidget(self.progress)

        # отчёт: ошибки, предупреждения и что решено за человека — остаются до следующего действия (п. 58)
        self.report_title = StrongBodyLabel(T("report.title"), self)
        root.addWidget(self.report_title)
        self.report = PlainTextEdit(self)
        self.report.setReadOnly(True)
        self.report.setFixedHeight(REPORT_H)
        tokens.apply_console(self.report)
        root.addWidget(self.report)

        bottom = QHBoxLayout()
        bottom.addStretch(1)
        self.stop_btn = PushButton(FluentIcon.CANCEL, T("main.stop"), self)
        self.stop_btn.clicked.connect(self._stop)
        bottom.addWidget(self.stop_btn)
        self.run_btn = PrimaryPushButton(getattr(FluentIcon, self.spec.icon), T("main.run.none"), self)
        self.run_btn.setDefault(True)                         # Enter (п. 46)
        self.run_btn.clicked.connect(self._start)
        bottom.addWidget(self.run_btn)
        root.addLayout(bottom)

        self.progress.setVisible(False)
        self.stop_btn.setVisible(False)
        self._sync_options()

    def _control(self, opt) -> QWidget:
        value = self.store.options.get(opt.key, opt.default)
        if opt.kind == SWITCH:
            control = SwitchButton(self)
            control.setOnText(T("switch.on"))
            control.setOffText(T("switch.off"))
            control.setChecked(bool(value))
            control.checkedChanged.connect(lambda on, k=opt.key: self._set_option(k, bool(on)))
            return control
        if opt.kind == SEGMENT:
            control = SegmentedWidget(self)
            for choice, text in opt.choices:
                control.addItem(choice, T(text), lambda *_, k=opt.key, c=choice: self._set_option(k, c))
            control.setCurrentItem(str(value))
            control.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
            return control
        control = LineEdit(self)
        control.setText(str(value))
        control.setFixedWidth(140)
        control.editingFinished.connect(lambda k=opt.key, c=control: self._set_option(k, c.text().strip()))
        return control

    # ================================================================== настройки
    def _set_option(self, key: str, value) -> None:
        if self.store.options.get(key) == value:
            return
        self.store.options[key] = value
        self.store.save()
        self._sync_options()
        self._replan()

    def _sync_options(self) -> None:
        """Какие строки видны и какие закрыты — от значений (п. 51, 53)."""
        values = self.store.options
        shown = []
        for opt in self.spec.options:
            row, desc, control = self.option_rows[opt.key]
            if opt.visible(values):
                shown.append(row)
            why = opt.locked(values)
            desc.setText(T(why) if why else T(opt.desc))
            desc.setVisible(bool(desc.text()))
            control.setProperty("locked", bool(why))
        self.option_columns.set_active(shown)
        self._lock_controls()

    def _lock_controls(self) -> None:
        for key, control in self.controls.items():
            control.setEnabled(not self.working and not control.property("locked"))

    # ================================================================== входы
    def _show_inputs(self) -> None:
        self.inputs.clear()
        for path in self.store.inputs:
            self.inputs.addItem(path)
            self.inputs.item(self.inputs.count() - 1).setToolTip(path)
        self.inputs_stack.setCurrentIndex(1 if self.store.inputs else 0)
        self._replan()

    def add_inputs(self, paths: List[str]) -> None:
        known = {os.path.normcase(p) for p in self.store.inputs}
        for path in paths:
            path = str(Path(path))
            if os.path.normcase(path) not in known:
                known.add(os.path.normcase(path))
                self.store.inputs.append(path)
        self.store.save()
        self._show_inputs()

    def _pick_files(self) -> None:
        _, _, pick = INPUT_TEXTS[self.spec.prefix]
        masks = " ".join("*" + s for s in self.spec.suffixes)
        files, _ = QFileDialog.getOpenFileNames(self, T(pick), "", "%s (%s)" % (T(pick), masks))
        if files:
            self.add_inputs(files)

    def _pick_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, T("inputs.pick_folder"))
        if folder:
            self.add_inputs([folder])

    def _remove_inputs(self) -> None:
        rows = sorted({self.inputs.row(i) for i in self.inputs.selectedItems()}, reverse=True)
        if not rows or self.working:
            return
        for row in rows:
            del self.store.inputs[row]
        self.store.save()
        self._show_inputs()

    def dragEnterEvent(self, event):
        if not self.working and self._dropped(event):
            event.acceptProposedAction()

    dragMoveEvent = dragEnterEvent

    def dropEvent(self, event):
        paths = self._dropped(event)
        if paths and not self.working:
            event.acceptProposedAction()
            self.add_inputs(paths)

    def _dropped(self, event) -> List[str]:
        data = event.mimeData()
        if not data.hasUrls():
            return []
        out = []
        for url in data.urls():
            path = Path(url.toLocalFile()) if url.isLocalFile() else None
            if path and (path.is_dir() or path.suffix.lower() in self.spec.suffixes):
                out.append(str(path))
        return out

    # ================================================================== план и работа
    def busy(self) -> bool:
        return self.run is not None and self.run.isRunning()

    def _stop_run(self) -> None:
        if self.busy():
            self.run.stop()
            self.run.wait()
        self.run = None

    def _start_cli(self, args: List[str]) -> None:
        run = CliRun(cli_command(self.spec) + args, self)
        run.event.connect(self._on_event)
        run.failed.connect(self._on_failed)
        run.exited.connect(lambda code, r=run: QTimer.singleShot(0, lambda: self._on_exit(r)))
        self.run = run
        run.start()
        self._sync()

    def _replan(self) -> None:
        """План — у командной строки (`--dry-run`): что во что и что пропускается."""
        if self.working:
            return
        self._stop_run()
        self.files, self.rows, self.result, self.problems, self._done = [], {}, None, [], 0
        self.report_lines, self.step_text = [], ""
        self.table.setRowCount(0)
        self._show_report()
        if not self.store.inputs:
            self._sync()
            return
        self._start_cli([*self.store.inputs, *self.spec.args(self.store.options), "--dry-run", "--json"])

    def _on_failed(self, text: str) -> None:
        if self.sender() is self.run:
            self.problems.append(T("summary.cli_failed", text=text))
            self._sync()

    def _on_event(self, ev: dict) -> None:
        # события остановленного прогона ещё лежат в очереди — план удвоился бы
        sender = self.sender()
        if isinstance(sender, CliRun) and sender is not self.run:
            return
        kind = ev.get("event")
        if kind == "problem":
            self.problems.append(ev.get("text", ""))
            self._report("[ERROR] %s" % ev.get("text", ""))
        elif kind == "file":
            if self.working:
                self._done += 1
                self.step_text = ""
                self.progress.setValue(self._done)
                row = self.rows.get(ev.get("src"))
                if row is not None:
                    self._set_row_state(row, ev)
                    # итог строки — и в план: сделанное повторно не предлагается
                    self.files[row] = dict(self.files[row], state=ev.get("state", "failed"))
                self._report_file(ev)
            else:
                self._add_row(ev)
        elif kind == "step" and self.working:
            src = ev.get("src") or ""
            self.step_text = T("progress.step", done=self._done, total=self.progress.maximum(),
                               name=Path(src).name if src else "", text=ev.get("text", ""))
        elif kind == "note" and self.working:
            self._report(("· " if not ev.get("text", "").startswith("[") else "") + ev.get("text", ""))
        elif kind == "done" and self.working:
            self.result = ev
        self._sync()

    def _report_file(self, ev: dict) -> None:
        name = ev.get("src", "")
        if ev.get("state") == "failed":
            self._report("[ERROR] %s: %s" % (name, ev.get("text", "")))
        for warn in ev.get("warnings") or []:
            self._report("[WARNING] %s: %s" % (name, warn))

    def _report(self, line: str) -> None:
        self.report_lines.append(line)
        self.report.appendPlainText(line)
        self._show_report()

    def _show_report(self) -> None:
        if not self.report_lines:
            self.report.clear()
        shown = bool(self.report_lines)                # пустой отчёт места не занимает (п. 51)
        self.report_title.setVisible(shown)
        self.report.setVisible(shown)

    def _add_row(self, ev: dict) -> None:
        state = "skipped" if ev.get("state") == "skipped" else \
            "overwrite" if ev.get("overwrite") else "planned"
        ev = dict(ev, state=state)
        row = self.table.rowCount()
        self.table.blockSignals(True)
        self.table.insertRow(row)
        src = Path(ev["src"])
        check = QTableWidgetItem()
        self.table.setItem(row, COL_CHECK, check)
        item = QTableWidgetItem(self._short(src))
        item.setToolTip(str(src))
        self.table.setItem(row, COL_SRC, item)
        self.table.setItem(row, COL_OUT, self._out_item(ev))
        self.rows[ev["src"]] = row
        self.files.append(ev)
        self._set_row_state(row, ev)
        self.table.blockSignals(False)

    def _out_item(self, ev: dict) -> QTableWidgetItem:
        out = ev.get("out") or ""
        text = Path(out).name if out else ""
        if ev.get("state") == "skipped":
            text = ev.get("text", "")
        elif ev.get("text"):
            text = "%s · %s" % (text, ev["text"]) if text else ev["text"]
        item = QTableWidgetItem(text)
        item.setToolTip(out or ev.get("text", ""))
        return item

    def _short(self, path: Path) -> str:
        """Путь коротко — от добавленной папки; полный — в подсказке."""
        for raw in self.store.inputs:
            base = Path(raw)
            if base.is_dir():
                try:
                    return str(path.relative_to(base.parent))
                except ValueError:
                    continue
        return path.name

    def _set_row_state(self, row: int, ev: dict) -> None:
        state = ev["state"]
        if state == "converted" and ev.get("warnings"):
            state = "warning"
        item = QTableWidgetItem(T(STATE_TEXT[state]))
        item.setForeground(QColor(tokens.color(ROLE[state])))
        item.setData(Qt.UserRole, ROLE[state])
        tip = [ev.get("text", "")] if state == "failed" else []
        tip += ev.get("notes") or []
        tip += ["⚠ %s" % w for w in ev.get("warnings") or []]
        item.setToolTip("\n".join(t for t in tip if t))
        self.table.blockSignals(True)
        self.table.setItem(row, COL_STATE, item)
        if state in ("converted", "warning") and ev.get("out"):
            out = QTableWidgetItem(Path(ev["out"]).name + (T("out.deleted") if ev.get("deleted") else ""))
            out.setToolTip(ev["out"])
            self.table.setItem(row, COL_OUT, out)
        check = self.table.item(row, COL_CHECK)
        if state in CHECKABLE:
            check.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled | Qt.ItemIsUserCheckable)
            check.setCheckState(Qt.Checked)
        else:
            check.setData(Qt.CheckStateRole, None)
            check.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
        self.table.blockSignals(False)

    def _checked(self) -> List[dict]:
        out = []
        for ev in self.files:
            check = self.table.item(self.rows[ev["src"]], COL_CHECK)
            if ev["state"] in CHECKABLE and check.checkState() == Qt.Checked:
                out.append(ev)
        return out

    def _toggle_all(self) -> None:
        rows = [self.rows[e["src"]] for e in self.files if e["state"] in CHECKABLE]
        on = len(self._checked()) < len(rows)
        self.table.blockSignals(True)
        for row in rows:
            self.table.item(row, COL_CHECK).setCheckState(Qt.Checked if on else Qt.Unchecked)
        self.table.blockSignals(False)
        self._sync()

    def _start(self) -> None:
        chosen = self._checked()
        if not chosen or self.busy():
            return
        fd, path = tempfile.mkstemp(prefix="kr_%s_" % self.spec.key, suffix=".json")
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump([e["src"] for e in chosen], fh, ensure_ascii=False)
        self._jobs_file = path
        self.working = True
        self._done, self.result, self.problems = 0, None, []
        self.report_lines, self.step_text = [], ""
        self._show_report()
        self.progress.setMaximum(len(chosen))
        self.progress.setValue(0)
        self._start_cli(["--jobs-file", path, *self.spec.args(self.store.options), "--json"])

    def _stop(self) -> None:
        if self.busy():
            self.run.stop()

    def _on_exit(self, run: CliRun) -> None:
        if run is not self.run:
            return
        run.wait()
        self.run = None
        if self.working:
            self.working = False
            if self._jobs_file:
                try:
                    os.remove(self._jobs_file)
                except OSError:
                    pass
                self._jobs_file = None
        self._sync()

    # ================================================================== состояние окна
    def _sync(self) -> None:
        """Подписи кнопок и сводка — из состояния (п. 27); на время работы правки закрыты (п. 92)."""
        busy = self.busy()
        todo = sum(1 for e in self.files if e["state"] in CHECKABLE)
        chosen = len(self._checked()) if self.files else 0
        skipped = sum(1 for e in self.files if e["state"] == "skipped")
        if chosen:
            label, enabled = T("main.run", count=chosen), not busy
        elif todo:
            label, enabled = T("main.run.nothing_chosen"), False
        else:
            label, enabled = T("main.run.none"), False
        self.run_btn.setText(label)
        self.run_btn.setEnabled(enabled)
        self.all_btn.setText(T("files.none") if todo and chosen == todo else T("files.all"))
        self.all_btn.setEnabled(bool(todo) and not self.working)

        if self.working:
            text = self.step_text or T("progress", done=self._done, total=self.progress.maximum())
        elif busy:
            text = T("planning")
        elif self.result is not None:
            # итог не исчезает до следующего действия (п. 58)
            text = T("summary.done", converted=self.result.get("converted", 0),
                     skipped=self.result.get("skipped", 0), failed=self.result.get("failed", 0))
            if self.result.get("cancelled"):
                text += T("summary.stopped")
        elif self.files:
            text = T("summary.plan", total=len(self.files), todo=todo, skipped=skipped)
        else:
            text = T("summary.empty") if self.store.inputs else ""
        if self.problems and not busy and not self.report_lines:
            text += ("\n" if text else "") + T("summary.problem", text="; ".join(self.problems))
        self.summary.setText(text)
        self.progress.setVisible(self.working)
        self.stop_btn.setVisible(self.working)

        for widget in (self.add_files, self.add_folder, self.table):
            widget.setEnabled(not self.working)
        self._lock_controls()
        self.remove_btn.setEnabled(not self.working and bool(self.inputs.selectedItems()))

    def _paint(self, *_args) -> None:
        """Смена темы на лету: цвета состояний — заново из токенов (п. 37)."""
        for row in range(self.table.rowCount()):
            item = self.table.item(row, COL_STATE)
            if item is not None and item.data(Qt.UserRole):
                item.setForeground(QColor(tokens.color(item.data(Qt.UserRole))))
        tokens.apply_console(self.report)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:                       # Esc — закрыть (п. 46)
            self.close()
            return
        super().keyPressEvent(event)

    def closeEvent(self, event):
        self._stop_run()
        self.store.window["size"] = [self.width(), self.height()]
        self.store.save()
        super().closeEvent(event)
