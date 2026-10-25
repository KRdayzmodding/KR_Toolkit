# -*- coding: utf-8 -*-
"""Окно [KR] Sound Converter — WAV → OGG без сборки.

Заказ юзера 23.10.2026: перегнать звук отдельно от [KR] Project Builder. Окно — оболочка
над командной строкой SoundKit (`runner.CliRun`): план берёт у `--dry-run`,
перегоняет отмеченное через `--jobs-file`. Оформление — как [KR] Project Builder и [KR] Addon Signer.
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
    QAbstractItemView, QFileDialog, QHBoxLayout, QHeaderView, QSizePolicy, QStackedWidget,
    QTableWidgetItem, QVBoxLayout, QWidget)
from qfluentwidgets import (
    BodyLabel, CaptionLabel, FluentIcon, LineEdit, ListWidget, PrimaryPushButton, ProgressBar,
    PushButton, SegmentedWidget, StrongBodyLabel, SwitchButton, TableWidget, ToolButton,
    TransparentPushButton, TransparentToolButton, qconfig)

from qts_ui import tokens
from qts_ui.card import Card
from qts_ui.rows import Columns, setting_row, shrink
from qts_ui.frame import ToolWindow
from runner import CliRun
from store import Store
from texts import T

COL_CHECK, COL_STATE, COL_WAV, COL_OUT = range(4)
MIN = (640, 720)                  # +40 — своя шапка окна; карточка настроек и таблица
INPUTS_H = 96
TABLE_MIN_H = 150                 # таблица не схлопывается в одну строку под карточкой настроек
PATH_ROLE = Qt.UserRole + 1
#: состояние строки → ключ текста (буквально, п. 66) и роль цвета
STATE_TEXT = {"planned": "state.planned", "overwrite": "state.overwrite", "skipped": "state.skipped",
              "converted": "state.converted", "failed": "state.failed"}
ROLE = {"planned": "text", "overwrite": "warning", "skipped": "text_dim",
        "converted": "success", "failed": "error"}
CHECKABLE = ("planned", "overwrite")


class SoundWindow(ToolWindow):
    def __init__(self, store: Store):
        super().__init__(FluentIcon.MUSIC, image="SoundConverter")              # своя шапка, как в QTS (qts_ui.frame)
        self.store = store
        self.run: Optional[CliRun] = None
        self.converting = False
        self.rows: Dict[str, int] = {}               # WAV → строка таблицы
        self.files: List[dict] = []                  # события плана по порядку
        self.result: Optional[dict] = None
        self.problems: List[str] = []
        self._done = 0
        self._jobs_file: Optional[str] = None
        self.setWindowTitle(T("app.title"))
        self.setMinimumSize(*MIN)
        w, h = self.store.window.get("size", MIN)
        self.resize(max(w, MIN[0]), max(h, MIN[1]))
        self.setAcceptDrops(True)                    # файлы и папки — перетаскиванием (п. 49)
        self._build()
        self._show_inputs()
        qconfig.themeChanged.connect(self._paint)

    # ================================================================== сборка окна
    def _build(self) -> None:
        root = QVBoxLayout(self.body)
        root.setContentsMargins(tokens.SPACE_M, tokens.SPACE_M, tokens.SPACE_M, tokens.SPACE_M)
        root.setSpacing(tokens.SPACE_S)

        head = QHBoxLayout()
        head.addWidget(StrongBodyLabel(T("inputs.title"), self))
        head.addStretch(1)
        self.add_files = TransparentToolButton(FluentIcon.MUSIC, self)
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
        drop = shrink(BodyLabel(T("inputs.drop"), empty))
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

        # --- настройки — своя карточка, строки как во всех окнах (замечание юзера 25.10.2026)
        # куда: два варианта — сегмент (п. 13); папка — отдельной строкой, только при «в папку»
        self.where = SegmentedWidget(self)
        self.where.addItem("next", T("where.next"), lambda *_: self._set_where(False))
        self.where.addItem("folder", T("where.folder"), lambda *_: self._set_where(True))
        # по размеру вариантов: растянутый сегмент читался как поле
        self.where.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        folder_box = QWidget(self)
        fb = QHBoxLayout(folder_box)
        fb.setContentsMargins(0, 0, 0, 0)
        fb.setSpacing(tokens.SPACE_XS)
        self.out_edit = LineEdit(folder_box)
        self.out_edit.setPlaceholderText(T("where.pick"))
        self.out_edit.setMinimumWidth(240)
        self.out_edit.setText(self.store.out_folder)
        self.out_edit.editingFinished.connect(self._on_out_edited)
        fb.addWidget(self.out_edit, 1)
        self.out_pick = ToolButton(FluentIcon.FOLDER, folder_box)
        self.out_pick.setToolTip(T("where.pick"))
        self.out_pick.clicked.connect(self._pick_out)
        fb.addWidget(self.out_pick)
        self.overwrite = SwitchButton(self)
        self.overwrite.setOnText("Да")
        self.overwrite.setOffText("Нет")
        self.overwrite.setChecked(self.store.overwrite)
        self.overwrite.checkedChanged.connect(self._set_overwrite)
        self.where_row = setting_row(T("where.label"), T("where.desc"), self.where)
        self.folder_row = setting_row(T("where.folder_row"), T("where.hint"), folder_box)
        self.overwrite_row = setting_row(T("overwrite"), T("overwrite.desc"), self.overwrite)
        root.addSpacing(tokens.SPACE_XS)
        root.addWidget(StrongBodyLabel(T("settings.title"), self))
        settings_card = Card(self)
        self.option_columns = Columns([self.where_row, self.folder_row, self.overwrite_row], settings_card)
        settings_card.box.addWidget(self.option_columns)
        root.addWidget(settings_card)
        root.addSpacing(tokens.SPACE_XS)

        th = QHBoxLayout()
        th.addWidget(StrongBodyLabel(T("wav.title"), self))
        th.addStretch(1)
        self.all_btn = TransparentPushButton(T("wav.all"), self)
        self.all_btn.clicked.connect(self._toggle_all)
        th.addWidget(self.all_btn)
        root.addLayout(th)
        self.table = TableWidget(self)
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["", T("col.state"), T("col.wav"), T("col.out")])
        self.table.verticalHeader().hide()
        self.table.setBorderVisible(True)
        self.table.setBorderRadius(tokens.RADIUS_CARD)
        self.table.setWordWrap(False)
        self.table.setTextElideMode(Qt.ElideMiddle)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        hdr = self.table.horizontalHeader()
        for col in (COL_CHECK, COL_STATE, COL_WAV):
            hdr.setSectionResizeMode(col, QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(COL_OUT, QHeaderView.Stretch)
        self.table.itemChanged.connect(lambda item: self._sync() if item.column() == COL_CHECK else None)
        self.table.setMinimumHeight(TABLE_MIN_H)
        root.addWidget(self.table, 1)

        self.summary = shrink(CaptionLabel("", self))
        root.addWidget(self.summary)
        self.progress = ProgressBar(self)
        root.addWidget(self.progress)

        bottom = QHBoxLayout()
        bottom.addStretch(1)
        self.stop_btn = PushButton(FluentIcon.CANCEL, T("main.stop"), self)
        self.stop_btn.clicked.connect(self._stop)
        bottom.addWidget(self.stop_btn)
        self.convert_btn = PrimaryPushButton(FluentIcon.MUSIC, T("main.convert.none"), self)
        self.convert_btn.setDefault(True)                     # Enter (п. 46)
        self.convert_btn.clicked.connect(self._start)
        bottom.addWidget(self.convert_btn)
        root.addLayout(bottom)

        self.where.setCurrentItem("folder" if self.store.out else "next")
        self.progress.setVisible(False)
        self.stop_btn.setVisible(False)
        self._sync_where()

    # ================================================================== входы
    def _show_inputs(self) -> None:
        self.inputs.clear()
        for path in self.store.inputs:
            self.inputs.addItem(path)
            self.inputs.item(self.inputs.count() - 1).setToolTip(path)
        self.inputs_stack.setCurrentIndex(1 if self.store.inputs else 0)
        self._replan()

    def _add_inputs(self, paths: List[str]) -> None:
        known = {os.path.normcase(p) for p in self.store.inputs}
        for path in paths:
            path = str(Path(path))
            if os.path.normcase(path) not in known:
                known.add(os.path.normcase(path))
                self.store.inputs.append(path)
        self.store.save()
        self._show_inputs()

    def _pick_files(self) -> None:
        files, _ = QFileDialog.getOpenFileNames(self, T("inputs.pick_files"), "", "*.wav")
        if files:
            self._add_inputs(files)

    def _pick_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, T("inputs.pick_folder"))
        if folder:
            self._add_inputs([folder])

    def _remove_inputs(self) -> None:
        rows = sorted({self.inputs.row(i) for i in self.inputs.selectedItems()}, reverse=True)
        if not rows or self.converting:
            return
        for row in rows:
            del self.store.inputs[row]
        self.store.save()
        self._show_inputs()

    def dragEnterEvent(self, event):
        if not self.converting and self._dropped(event):
            event.acceptProposedAction()

    dragMoveEvent = dragEnterEvent

    def dropEvent(self, event):
        paths = self._dropped(event)
        if paths and not self.converting:
            event.acceptProposedAction()
            self._add_inputs(paths)

    @staticmethod
    def _dropped(event) -> List[str]:
        data = event.mimeData()
        if not data.hasUrls():
            return []
        out = []
        for url in data.urls():
            path = Path(url.toLocalFile()) if url.isLocalFile() else None
            if path and (path.is_dir() or path.suffix.lower() == ".wav"):
                out.append(str(path))
        return out

    # ================================================================== куда
    def _set_where(self, folder: bool) -> None:
        self.store.out = self.out_edit.text().strip() if folder else ""
        self.store.save()
        self._sync_where()
        self._replan()

    def _sync_where(self) -> None:
        folder = self.where.currentRouteKey() == "folder"
        self.option_columns.set_active([self.where_row] + ([self.folder_row] if folder else []) + [self.overwrite_row])

    def _on_out_edited(self) -> None:
        text = self.out_edit.text().strip()
        folder = self.where.currentRouteKey() == "folder"
        if text == self.store.out_folder and (not folder or text == self.store.out):
            return
        self.store.out_folder = text
        if folder:
            self.store.out = text
        self.store.save()
        self._replan()

    def _pick_out(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, T("where.pick"), self.out_edit.text())
        if folder:
            self.out_edit.setText(str(Path(folder)))
            self._on_out_edited()

    def _set_overwrite(self, on: bool) -> None:
        self.store.overwrite = bool(on)
        self.store.save()
        self._replan()

    def _out_args(self) -> List[str]:
        args = ["--out", self.store.out] if self.store.out else []
        return args + (["--overwrite"] if self.store.overwrite else [])

    # ================================================================== план и перегонка
    def busy(self) -> bool:
        return self.run is not None and self.run.isRunning()

    def _stop_run(self) -> None:
        if self.busy():
            self.run.stop()
            self.run.wait()
        self.run = None

    def _start_cli(self, args: List[str]) -> None:
        run = CliRun(args, self)
        run.event.connect(self._on_event)
        run.failed.connect(lambda text: self.problems.append(T("summary.cli_failed", text=text)))
        run.exited.connect(lambda code, r=run: QTimer.singleShot(0, lambda: self._on_exit(r)))
        self.run = run
        run.start()
        self._sync()

    def _replan(self) -> None:
        """План — у командной строки (`--dry-run`): что во что перегонится и что уже есть."""
        if self.converting:
            return
        self._stop_run()
        self.files, self.rows, self.result, self.problems, self._done = [], {}, None, [], 0
        self.table.setRowCount(0)
        if not self.store.inputs or (self.where.currentRouteKey() == "folder" and not self.store.out):
            self._sync()
            return
        self._start_cli(["ogg", *self.store.inputs, *self._out_args(), "--dry-run", "--json"])

    def _on_event(self, ev: dict) -> None:
        kind = ev.get("event")
        if kind == "problem":
            self.problems.append(ev.get("text", ""))
        elif kind == "file":
            if self.converting:
                self._done += 1
                self.progress.setValue(self._done)
                row = self.rows.get(ev.get("src"))
                if row is not None:
                    self._set_row_state(row, ev)
            else:
                self._add_row(ev)
        elif kind == "done" and self.converting:
            self.result = ev
        self._sync()

    def _add_row(self, ev: dict) -> None:
        state = "skipped" if ev.get("state") == "skipped" else \
            "overwrite" if ev.get("overwrite") else "planned"
        ev = dict(ev, state=state)
        row = self.table.rowCount()
        self.table.blockSignals(True)
        self.table.insertRow(row)
        src, out = Path(ev["src"]), Path(ev["out"])
        check = QTableWidgetItem()
        check.setData(PATH_ROLE, ev["src"])
        self.table.setItem(row, COL_CHECK, check)
        item = QTableWidgetItem(src.name)
        item.setToolTip(str(src))
        self.table.setItem(row, COL_WAV, item)
        item = QTableWidgetItem(self._where_text(src, out))
        item.setToolTip(str(out))
        self.table.setItem(row, COL_OUT, item)
        self.rows[ev["src"]] = row
        self.files.append(ev)
        self._set_row_state(row, ev)
        self.table.blockSignals(False)

    def _where_text(self, src: Path, out: Path) -> str:
        """Папка OGG коротко: от добавленной папки (или от папки назначения), полная — в подсказке."""
        bases = [Path(self.store.out)] if self.store.out else             [Path(p).parent for p in self.store.inputs if Path(p).is_dir()]
        for base in bases:
            try:
                rel = out.parent.relative_to(base)
            except ValueError:
                continue
            return str(rel) if str(rel) != "." else base.name
        return str(out.parent)

    def _set_row_state(self, row: int, ev: dict) -> None:
        state = ev["state"]
        item = QTableWidgetItem(T(STATE_TEXT[state]))
        item.setForeground(QColor(tokens.color(ROLE[state])))
        item.setData(Qt.UserRole, ROLE[state])
        if state == "failed":
            item.setToolTip(ev.get("text", ""))
        elif state == "converted":
            item.setToolTip("%s, %d Гц, %d kbps" % (T("kind.mono") if ev.get("channels") == 1
                                                     else T("kind.stereo"), ev.get("rate", 0),
                                                     ev.get("kbps", 0)))
        self.table.blockSignals(True)
        self.table.setItem(row, COL_STATE, item)
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
        fd, path = tempfile.mkstemp(prefix="krsound_", suffix=".json")
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump([{"src": e["src"], "out": e["out"]} for e in chosen], fh, ensure_ascii=False)
        self._jobs_file = path
        self.converting = True
        self._done, self.result, self.problems = 0, None, []
        self.progress.setMaximum(len(chosen))
        self.progress.setValue(0)
        self._start_cli(["ogg", "--jobs-file", path, "--json"]
                        + (["--overwrite"] if self.store.overwrite else []))

    def _stop(self) -> None:
        if self.busy():
            self.run.stop()

    def _on_exit(self, run: CliRun) -> None:
        if run is not self.run:
            return
        run.wait()
        self.run = None
        if self.converting:
            self.converting = False
            if self._jobs_file:
                try:
                    os.remove(self._jobs_file)
                except OSError:
                    pass
                self._jobs_file = None
        self._sync()

    # ================================================================== состояние окна
    def _sync(self) -> None:
        """Подписи кнопок и сводка — из состояния (п. 27); на время перегонки правки закрыты (п. 92)."""
        busy = self.busy()
        todo = sum(1 for e in self.files if e["state"] in CHECKABLE)
        chosen = len(self._checked()) if self.files else 0
        exists = sum(1 for e in self.files if e["state"] == "skipped")
        folder_missing = self.where.currentRouteKey() == "folder" and not self.store.out
        if folder_missing:
            label, enabled = T("main.convert.no_folder"), False
        elif chosen:
            label, enabled = T("main.convert", count=chosen), not busy
        elif todo:
            label, enabled = T("main.convert.nothing_chosen"), False
        else:
            label, enabled = T("main.convert.none"), False
        self.convert_btn.setText(label)
        self.convert_btn.setEnabled(enabled)
        self.all_btn.setText(T("wav.none") if todo and chosen == todo else T("wav.all"))
        self.all_btn.setEnabled(bool(todo) and not self.converting)

        if self.converting:
            text = T("progress", done=self._done, total=self.progress.maximum())
        elif busy:
            text = T("planning")
        elif self.result is not None:
            # итог не исчезает до следующего действия (п. 58)
            text = T("summary.done", converted=self.result.get("converted", 0),
                     skipped=self.result.get("skipped", 0), failed=self.result.get("failed", 0))
            if self.result.get("cancelled"):
                text += T("summary.stopped")
            if self.result.get("backup"):
                text += T("summary.backup", folder=self.result["backup"])
        elif self.files:
            text = T("summary.plan", total=len(self.files), todo=todo, exists=exists)
        else:
            text = T("summary.empty") if self.store.inputs else ""
        if self.problems and not busy:
            text += ("\n" if text else "") + T("summary.problem", text="; ".join(self.problems))
        self.summary.setText(text)
        self.progress.setVisible(self.converting)
        self.stop_btn.setVisible(self.converting)

        locked = self.converting
        for widget in (self.add_files, self.add_folder, self.where, self.out_edit, self.out_pick,
                       self.overwrite, self.table):
            widget.setEnabled(not locked)
        self.remove_btn.setEnabled(not locked and bool(self.inputs.selectedItems()))

    def _paint(self, *_args) -> None:
        """Смена темы на лету: цвета состояний — заново из токенов (п. 37)."""
        for row in range(self.table.rowCount()):
            item = self.table.item(row, COL_STATE)
            if item is not None and item.data(Qt.UserRole):
                item.setForeground(QColor(tokens.color(item.data(Qt.UserRole))))

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
