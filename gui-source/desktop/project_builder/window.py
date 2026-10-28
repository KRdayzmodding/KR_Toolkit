# -*- coding: utf-8 -*-
"""Главное окно [KR] Project Builder — компактное, как у pboProject: что, куда, кнопка.

Решения юзера 22.10.2026:

* окно компактное; в главном только самое нужное — что паковать, куда, кнопка
  запаковки и главная опция. Всё прочее — отдельными окнами (настройки, логи);
* паковать можно несколько PBO разом, поэтому «что паковать» — список, куда
  перетаскиваются папки модов;
* цвет и стиль — KR QTS: qfluentwidgets, токены `qts_ui.tokens`, акцент DayZ.

Ход запаковки — таблицей в журнале, строки обновляются на месте
(`qts_ui.packing_log`, как в QTS): сколько PBO всего и что идёт сейчас видно
сразу. Состояние строк до запаковки («изменено: 7», «изменений нет») — тот же
план, что `--dry-run`: тулза сама смотрит, человек не гадает.
"""
from __future__ import annotations

import html
import os
import time
from pathlib import Path
from typing import Dict, List, Optional

from PySide6.QtCore import QEvent, Qt, QTimer
from PySide6.QtGui import QColor, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QAbstractItemView, QFileDialog, QGridLayout, QHBoxLayout, QStackedWidget,
    QTableWidgetItem, QVBoxLayout, QWidget)
from qfluentwidgets import (
    Action, BodyLabel, CaptionLabel, CheckBox, ComboBox, FluentIcon, LineEdit, MessageBox,
    PlainTextEdit, PrimaryPushButton, ProgressBar, PushButton, RoundMenu, StrongBodyLabel,
    TableWidget, ToolButton, TransparentPushButton, TransparentToolButton, qconfig)

from dialogs import LogsDialog, NameDialog, SettingsDialog
from links import LinkedPackingLog, LinkText, act_link, finding_html
from qts_ui import recolor, tokens
from qts_ui.columns import ProportionalColumns
from qts_ui.packing_log import FAIL, OK, PACKING
from qts_ui.resizer import Resizer
from qts_ui.rows import shrink
from qts_ui.frame import ToolWindow
from store import SCRATCH, BuildSet, Entry, Store, addons_dir, read_global_settings, write_global_settings
from texts import T
from worker import BuildWorker, Result, check_settings, settings_path

COL_PBO, COL_WHERE, COL_STATE = range(3)
#: доли ширины колонок по умолчанию (юзер 27.10.2026): имя PBO короткое, а в «Куда» —
#: путь, ему и место; «Состояние» — «запакован с ошибками: 3, в 17:05» целиком
COLUMN_SHARES = (0.25, 0.45, 0.30)
MIN = (520, 560)            # минимальный размер — он же размер первого запуска; +40 — своя шапка окна
LIST_H = 232                # высота списка по умолчанию: шапка и пять строк
LIST_MIN = 110
LIST_MAX = 900


class DropArea(QWidget):
    """Место «что паковать»: папки модов перетаскиваются сюда целиком (п. 49)."""

    def __init__(self, on_drop, parent=None):
        super().__init__(parent)
        self.on_drop = on_drop
        self.setAcceptDrops(True)

    @staticmethod
    def _folders(event) -> List[str]:
        data = event.mimeData()
        if not data.hasUrls():
            return []
        return [u.toLocalFile() for u in data.urls()
                if u.isLocalFile() and Path(u.toLocalFile()).is_dir()]

    def dragEnterEvent(self, event):
        if self._folders(event):
            event.acceptProposedAction()

    def dragMoveEvent(self, event):
        if self._folders(event):
            event.acceptProposedAction()

    def dropEvent(self, event):
        folders = self._folders(event)
        if folders:
            event.acceptProposedAction()
            self.on_drop(folders)


class MainWindow(ToolWindow):
    def __init__(self, store: Store, settings_file: Optional[Path] = None):
        super().__init__(FluentIcon.SEND, image="ProjectBuilder")              # своя шапка, как в QTS (qts_ui.frame)
        self.store = store
        # общий файл настроек — где его держит командная строка; тест даёт свой
        self.settings_file = Path(settings_file) if settings_file is not None else settings_path()
        self.worker: Optional[BuildWorker] = None
        self.states: Dict[int, tuple] = {}          # строка → (текст, роль)
        self.state_links: Dict[int, str] = {}       # строка → уровень: состояние — ссылка на логи
        #: PBO → (время, ссылка) последней запаковки за сеанс: тихая проверка «изменений нет» её не
        #: затирает, а дописывает (юзер 25.10.2026: «запакован в…» исчезало через секунды)
        self.packed_at: Dict[str, tuple] = {}
        self.last_run: List[dict] = []              # для окна логов
        self._planned_at = 0.0
        self._quiet = True
        self._started: Dict[int, float] = {}

        self.setWindowTitle(T("app.title"))
        self.setMinimumSize(*MIN)
        # первый запуск — минимальный размер; дальше — тот, в котором окно оставили
        # (правило юзера 22.10.2026, свод п. 87); сохраняется в closeEvent
        w, h = self.store.window.get("size", MIN)
        self.resize(max(w, MIN[0]), max(h, MIN[1]))
        self._build()
        self._fill_sets()
        # смена темы на лету: свои цвета перекрашиваем сами. Слот — метод окна:
        # Qt снимает подписку сам, когда окно удалено. Своя отписка по destroyed
        # обращалась к уже удалённому окну и печатала исключение при закрытии.
        qconfig.themeChanged.connect(self._on_theme_changed)

    # ================================================================== сборка окна
    def _build(self) -> None:
        root = QVBoxLayout(self.body)
        root.setContentsMargins(tokens.SPACE_M, tokens.SPACE_M, tokens.SPACE_M, tokens.SPACE_M)
        root.setSpacing(tokens.SPACE_S)

        # --- набор: глобальный контекст — строкой сверху, как пресет в QTS
        head = QHBoxLayout()
        head.setSpacing(tokens.SPACE_XS)
        head.addWidget(BodyLabel(T("set.label"), self))
        self.set_box = ComboBox(self)
        self.set_box.currentIndexChanged.connect(self._on_set_chosen)
        head.addWidget(self.set_box, 1)
        self.new_btn = TransparentToolButton(FluentIcon.ADD, self)
        self.new_btn.setToolTip(T("set.new"))
        self.new_btn.clicked.connect(self._new_set)
        head.addWidget(self.new_btn)
        self.rename_btn = TransparentToolButton(FluentIcon.EDIT, self)
        self.rename_btn.setToolTip(T("set.rename"))
        self.rename_btn.clicked.connect(self._rename_set)
        head.addWidget(self.rename_btn)
        self.delete_btn = TransparentToolButton(FluentIcon.DELETE, self)
        self.delete_btn.setToolTip(T("set.delete"))
        self.delete_btn.clicked.connect(self._delete_set)
        head.addWidget(self.delete_btn)
        root.addLayout(head)

        # --- что паковать
        what = QHBoxLayout()
        what.addWidget(StrongBodyLabel(T("what.title"), self))
        what.addStretch(1)
        self.count_label = CaptionLabel("", self)
        what.addWidget(self.count_label)
        self.all_btn = TransparentPushButton(T("what.all"), self)
        self.all_btn.clicked.connect(self._toggle_all)
        what.addWidget(self.all_btn)
        self.add_btn = TransparentToolButton(FluentIcon.FOLDER_ADD, self)
        self.add_btn.setToolTip(T("what.add"))
        self.add_btn.clicked.connect(self._pick_folders)
        what.addWidget(self.add_btn)
        # убрать — видимой кнопкой, а не только из меню правого клика (п. 47)
        # «минус», а не корзина: корзина над ним удаляет набор целиком
        self.remove_btn = TransparentToolButton(FluentIcon.REMOVE, self)
        self.remove_btn.setToolTip(T("what.remove"))
        self.remove_btn.clicked.connect(self._remove_selected)
        what.addWidget(self.remove_btn)
        root.addLayout(what)

        self.drop = DropArea(self._add_folders, self)
        dl = QVBoxLayout(self.drop)
        dl.setContentsMargins(0, 0, 0, 0)
        self.what_stack = QStackedWidget(self.drop)
        dl.addWidget(self.what_stack)
        # пусто: приглашение перетащить и обычный путь рядом (жест — ускоритель, п. 10)
        empty = QWidget(self.what_stack)
        el = QVBoxLayout(empty)
        el.addStretch(1)
        self.drop_label = shrink(BodyLabel(T("what.drop"), empty))
        self.drop_label.setAlignment(Qt.AlignCenter)
        el.addWidget(self.drop_label)
        pick_row = QHBoxLayout()
        pick_row.addStretch(1)
        self.pick_btn = PushButton(FluentIcon.FOLDER_ADD, T("what.pick"), empty)
        self.pick_btn.clicked.connect(self._pick_folders)
        pick_row.addWidget(self.pick_btn)
        pick_row.addStretch(1)
        el.addLayout(pick_row)
        el.addStretch(1)
        empty.setObjectName("dropZone")
        self.empty_zone = empty
        self._style_drop_zone()
        self.what_stack.addWidget(empty)
        self.table = TableWidget(self.what_stack)
        self.table.setColumnCount(3)
        self.table.setHorizontalHeaderLabels([T("col.pbo"), T("col.where"), T("col.state")])
        self.table.verticalHeader().hide()
        self.table.setBorderVisible(True)
        self.table.setBorderRadius(tokens.RADIUS_CARD)
        self.table.setWordWrap(False)
        self.table.setTextElideMode(Qt.ElideMiddle)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        # колонки тянутся мышью, с окном меняются пропорционально, выставленное помнится
        # (юзер 27.10.2026; прежнее «имя PBO важнее пути» от 22.10.2026 снято). Длинный путь
        # ужимается посередине, полный — в подсказке
        self.columns = ProportionalColumns(self.table, COLUMN_SHARES, self.store.window.get("columns"))
        self.columns.changed.connect(self._remember_columns)
        self._columns_save = QTimer(self)
        self._columns_save.setSingleShot(True)
        self._columns_save.setInterval(500)
        self._columns_save.timeout.connect(self.store.save)
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._row_menu)
        self.table.itemChanged.connect(self._on_item_changed)
        self.table.cellDoubleClicked.connect(lambda row, _c: self._change_source(row))
        self.table.cellClicked.connect(self._on_cell_clicked)
        self.table.setMouseTracking(True)
        self.table.cellEntered.connect(self._on_cell_entered)
        self.table.itemSelectionChanged.connect(self._sync)
        QShortcut(QKeySequence.Delete, self.table, activated=self._remove_selected,
                  context=Qt.WidgetWithChildrenShortcut)
        self.what_stack.addWidget(self.table)
        # Высоту списка задаёт ручка под ним (как в QTS): тянешь вверх — журналу
        # больше места; всё, что окно получает при растягивании, тоже уходит журналу.
        root.addWidget(self.drop)
        self.drop.setFixedHeight(int(self.store.window.get("list_h", LIST_H)))
        self.list_grip = Resizer(self.drop, default=LIST_H, minimum=LIST_MIN, maximum=LIST_MAX,
                                 apply=self._set_list_height, parent=self)
        self.list_grip.resized.connect(self._remember_list_height)
        root.addWidget(self.list_grip)

        # --- куда
        where = QHBoxLayout()
        where.setSpacing(tokens.SPACE_XS)
        where.addWidget(StrongBodyLabel(T("where.title"), self))
        self.where = LineEdit(self)
        self.where.setPlaceholderText(T("where.hint"))
        self.where.setClearButtonEnabled(True)
        self.where.editingFinished.connect(self._on_where_edited)
        where.addWidget(self.where, 1)
        self.where_btn = ToolButton(FluentIcon.FOLDER, self)
        self.where_btn.setToolTip(T("where.pick"))
        self.where_btn.clicked.connect(self._pick_where)
        where.addWidget(self.where_btn)
        root.addLayout(where)

        # --- опции запаковки (юзер 27.10.2026: бинаризация и «не останавливаться на
        # ошибках» — здесь, а не в настройках, как в главном окне pboProject).
        # «Использовать temp» — на этот запуск (выключенная навсегда замедлила бы
        # каждую сборку); остальные три — общие настройки сборки
        # (project_builder.json): их видят и командная строка, и QTS.
        values = read_global_settings(self.settings_file)
        options = QGridLayout()
        options.setHorizontalSpacing(tokens.SPACE_L)
        options.setVerticalSpacing(tokens.SPACE_XS)
        self.binarize = CheckBox(T("opt.binarize"), self)
        self.binarize.setToolTip(T("opt.binarize.tip"))
        self.binarize.setChecked(bool(values.get("binarize_models", True)))
        self.binarize.toggled.connect(lambda on: self._save_option("binarize_models", on))
        options.addWidget(self.binarize, 0, 0)
        self.rapify = CheckBox(T("opt.rapify"), self)
        self.rapify.setToolTip(T("opt.rapify.tip"))
        self.rapify.setChecked(bool(values.get("rapify", True)))
        self.rapify.toggled.connect(lambda on: self._save_option("rapify", on))
        options.addWidget(self.rapify, 0, 1)
        self.use_temp = CheckBox(T("opt.temp"), self)
        self.use_temp.setToolTip(T("opt.temp.tip"))
        self.use_temp.setChecked(True)
        options.addWidget(self.use_temp, 1, 0)
        self.force = CheckBox(T("opt.force"), self)
        self.force.setToolTip(T("opt.force.tip"))
        self.force.setChecked(bool(values.get("ignore_errors", False)))
        self.force.toggled.connect(lambda on: self._save_option("ignore_errors", on))
        options.addWidget(self.force, 1, 1)
        options.setColumnStretch(2, 1)
        root.addLayout(options)

        # --- журнал: таблица хода запаковки и итог (как в QTS)
        self.journal = LinkText(self)
        self.journal.setReadOnly(True)
        self.journal.setFont(tokens.mono_font())
        self.journal.setLineWrapMode(PlainTextEdit.LineWrapMode.NoWrap)
        self.journal.setMinimumHeight(110)
        tokens.apply_console(self.journal)
        self.journal.logRequested.connect(self._open_logs_for)
        self.journal.actionRequested.connect(self._on_journal_action)
        self.packing = LinkedPackingLog(self.journal)
        root.addWidget(self.journal, 1)

        self.progress = ProgressBar(self)
        root.addWidget(self.progress)
        self.progress_label = CaptionLabel("", self)
        root.addWidget(self.progress_label)

        # --- кнопки: одна первичная (п. 19)
        bottom = QHBoxLayout()
        bottom.setSpacing(tokens.SPACE_XS)
        self.settings_btn = PushButton(FluentIcon.SETTING, T("main.settings"), self)
        self.settings_btn.clicked.connect(self._open_settings)
        bottom.addWidget(self.settings_btn)
        self.logs_btn = PushButton(FluentIcon.DOCUMENT, T("main.logs"), self)
        self.logs_btn.clicked.connect(self._open_logs)
        bottom.addWidget(self.logs_btn)
        bottom.addStretch(1)
        self.stop_btn = PushButton(FluentIcon.CANCEL, T("main.stop"), self)
        self.stop_btn.clicked.connect(self._stop)
        bottom.addWidget(self.stop_btn)
        self.pack_btn = PrimaryPushButton(FluentIcon.SEND, T("main.pack.none"), self)
        self.pack_btn.setDefault(True)                       # Enter (п. 46)
        self.pack_btn.clicked.connect(self._start)
        bottom.addWidget(self.pack_btn)
        root.addLayout(bottom)

        QShortcut(QKeySequence("Ctrl+B"), self, activated=self._start)
        QShortcut(QKeySequence.Undo, self, activated=self._undo_remove)
        # убранное в последний раз: (набор, [(индекс, строка)]) — для «Вернуть»
        self._removed: Optional[tuple] = None

        # видимость — последней, когда иерархия собрана (п. 69)
        self.progress.setVisible(False)
        self.progress_label.setVisible(False)
        self.stop_btn.setVisible(False)

    # ================================================================== наборы
    def _active(self) -> Optional[BuildSet]:
        return self.store.active()

    def _fill_sets(self) -> None:
        """Первый пункт — рабочий список «без набора»: набор помощник, а не условие."""
        self.set_box.blockSignals(True)
        self.set_box.clear()
        self.set_box.addItem(T("set.scratch"), userData=SCRATCH)
        for named in self.store.named():
            self.set_box.addItem(named.name, userData=named.name)
        names = [SCRATCH] + [n.name for n in self.store.named()]
        current = self._active().name
        self.set_box.setCurrentIndex(names.index(current) if current in names else 0)
        self.set_box.blockSignals(False)
        self._show_set()

    def _on_set_chosen(self, index: int) -> None:
        name = self.set_box.itemData(index) if index >= 0 else SCRATCH
        name = name or SCRATCH
        if name != self.store.current:
            self.store.current = name
            self.store.save()
            self._show_set()

    def _new_set(self) -> Optional[BuildSet]:
        """На рабочем списке с модами — сохранить его как набор; иначе — новый пустой."""
        current = self._active()
        promote = current.name == SCRATCH and bool(current.entries)
        title = T("set.save.title") if promote else T("set.new.title")
        dlg = NameDialog(title, [x.name for x in self.store.named()], parent=self)
        if not dlg.exec():
            return None
        made = self.store.promote(dlg.name()) if promote else self.store.create(dlg.name())
        self._fill_sets()
        return made

    def _rename_set(self) -> None:
        current = self._active()
        if current.name == SCRATCH:
            return
        dlg = NameDialog(T("set.rename.title"), [x.name for x in self.store.named()],
                         current.name, parent=self)
        if dlg.exec() and dlg.name() != current.name:
            self.store.rename(current.name, dlg.name())
            self._fill_sets()

    def _delete_set(self) -> None:
        current = self._active()
        if current.name == SCRATCH:
            return
        # отмены у удаления нет — поэтому подтверждение (п. 56)
        box = MessageBox(T("set.delete.title", name=current.name), T("set.delete.text"), self)
        box.yesButton.setText(T("set.delete"))
        box.cancelButton.setText(T("dialog.cancel"))
        if box.exec():
            self.store.delete(current.name)
            self._fill_sets()

    def _show_set(self) -> None:
        current = self._active()
        # папка, сохранённая до правила Addons, — тоже к нему
        if current is not None and addons_dir(current.target_dir) != current.target_dir:
            current.target_dir = addons_dir(current.target_dir)
            self.store.save()
        self.states.clear()
        self.state_links.clear()
        self.where.blockSignals(True)
        self.where.setText(current.target_dir if current else "")
        self.where.setToolTip(current.target_dir if current else "")
        self.where.blockSignals(False)
        self._fill_table()
        if current is not None and current.entries:
            self._refresh_states()

    # ================================================================== список
    def _fill_table(self) -> None:
        current = self._active()
        entries = current.entries if current else []
        self.table.blockSignals(True)
        self.table.setRowCount(len(entries))
        for row, entry in enumerate(entries):
            item = QTableWidgetItem(entry.pbo_name())
            item.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            item.setCheckState(Qt.Checked if entry.enabled else Qt.Unchecked)
            tip = entry.source
            if entry.target:
                tip += "\n" + T("where.other", path=entry.target)
            item.setToolTip(tip)
            self.table.setItem(row, COL_PBO, item)
            self.table.setItem(row, COL_WHERE, QTableWidgetItem())
            self._paint_where(row)
            self.table.setItem(row, COL_STATE, QTableWidgetItem())
            self._paint_state(row)
        self.table.blockSignals(False)
        self.what_stack.setCurrentIndex(1 if entries else 0)
        self._sync()

    def _paint_where(self, row: int) -> None:
        """«по умолчанию» приглушённо или своя папка строки; подчёркнуто — жмётся."""
        current = self._active()
        item = self.table.item(row, COL_WHERE)
        if item is None or current is None:
            return
        entry = current.entries[row]
        own = bool(entry.target)
        item.setText(str(Path(entry.target).parent) if own else T("where.default"))
        item.setForeground(QColor(tokens.color("text" if own else "text_dim")))
        font = item.font()
        font.setUnderline(True)
        item.setFont(font)
        target = entry.pbo_path(current.target_dir)
        item.setToolTip(T("where.cell", path=str(target) if target else T("state.no_target")))

    def _paint_state(self, row: int) -> None:
        text, role = self.states.get(row, (T("state.unknown"), "text_dim"))
        item = self.table.item(row, COL_STATE)
        if item is None:
            return
        self.table.blockSignals(True)
        item.setText(text)
        item.setForeground(QColor(tokens.color(role)))
        # итог с находками — ссылка на окно логов: подчёркнут, как ссылка в журнале
        font = item.font()
        font.setUnderline(row in self.state_links)
        item.setFont(font)
        item.setToolTip(T("state.open_logs") if row in self.state_links else "")
        self.table.blockSignals(False)

    def _set_state(self, row: int, text: str, role: str, link: str = "") -> None:
        self.states[row] = (text, role)
        if link:
            self.state_links[row] = link
        else:
            self.state_links.pop(row, None)
        self._paint_state(row)

    def _on_cell_clicked(self, row: int, col: int) -> None:
        if col == COL_STATE and row in self.state_links:
            self._open_logs_for(self._name(row), self.state_links[row])
        elif col == COL_WHERE and not self._busy():
            self._own_target(row)

    def _on_cell_entered(self, row: int, col: int) -> None:
        link = (col == COL_STATE and row in self.state_links) or col == COL_WHERE
        self.table.viewport().setCursor(Qt.PointingHandCursor if link else Qt.ArrowCursor)

    def _on_item_changed(self, item: QTableWidgetItem) -> None:
        # меняем саму строку и кнопку, список не перестраиваем (п. 70)
        current = self._active()
        if item.column() != COL_PBO or current is None or item.row() >= len(current.entries):
            return
        current.entries[item.row()].enabled = item.checkState() == Qt.Checked
        self.store.save()
        self._sync()

    def _checked(self) -> List[int]:
        current = self._active()
        return [i for i, e in enumerate(current.entries) if e.enabled] if current else []

    def _ready(self) -> List[int]:
        """Отмеченные строки, которым есть куда паковать."""
        current = self._active()
        return [i for i in self._checked() if current.entries[i].pbo_path(current.target_dir)]

    def _busy(self) -> bool:
        return self.worker is not None

    def _sync(self) -> None:
        current = self._active()
        named = current.name != SCRATCH
        total = len(current.entries)
        checked = len(self._checked())
        self.count_label.setText(T("what.count", checked=checked, total=total) if total else "")
        # одна кнопка, надпись — по состоянию: что произойдёт по нажатию (п. 27)
        self.all_btn.setText(T("what.none") if total and checked == total else T("what.all"))
        self.all_btn.setVisible(bool(total))
        ready = len(self._ready())
        self.pack_btn.setText(T("main.pack", count=ready) if ready else T("main.pack.none"))
        busy = self._busy()
        self.pack_btn.setEnabled(bool(ready) and not busy)
        # настройки меняют уровни и temp под идущей сборкой — пока она идёт, закрыты;
        # тихая сверка «есть что паковать» короткая и не держит кнопку
        self.settings_btn.setEnabled(not (busy and not self._quiet))
        for w in (self.add_btn, self.pick_btn, self.where, self.where_btn, self.use_temp, self.all_btn,
                  self.binarize, self.rapify, self.force):
            w.setEnabled(not busy)
        self.drop.setAcceptDrops(not busy)
        self.rename_btn.setEnabled(named and not busy)
        self.delete_btn.setEnabled(named and not busy)
        self.set_box.setEnabled(not busy)
        self.remove_btn.setVisible(bool(total))
        self.remove_btn.setEnabled(bool(self._selected_rows()) and not busy)
        self.new_btn.setEnabled(not busy)
        # «+» на рабочем списке с модами сохраняет его как набор — подсказка говорит это
        self.new_btn.setToolTip(T("set.save") if not named and total else T("set.new"))

    def _list_room(self) -> int:
        """Сколько списку можно высоты: его нынешняя плюс то, что журнал может отдать.

        Журнал — растягиваемая часть окна; всё сверх его минимума свободно.
        Без этого ручка тянула список за пределы окна, и он наезжал на поля
        ниже (замечание юзера 22.10.2026).
        """
        slack = self.journal.height() - self.journal.minimumHeight()
        return self.drop.height() + max(0, slack)

    def _set_list_height(self, height: int) -> None:
        room = self._list_room() if self.isVisible() else LIST_MAX
        self.drop.setFixedHeight(max(LIST_MIN, min(height, room, LIST_MAX)))

    def _fit_list(self) -> None:
        """Окно стало меньше, чем нужно списку и журналу, — ужать список."""
        lay = self.layout()
        if lay is None or getattr(self, "drop", None) is None:
            return          # окно ещё не собрано: рамка шлёт resize из конструктора (багрепорт 25.10.2026)
        deficit = lay.minimumSize().height() - self.height()
        if deficit > 0 and self.drop.height() > LIST_MIN:
            self.drop.setFixedHeight(max(LIST_MIN, self.drop.height() - deficit))

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._fit_list()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        # сохранённая высота могла быть от окна побольше
        QTimer.singleShot(0, self._fit_list)

    def _remember_columns(self, shares: list) -> None:
        """Доли — в окно сразу, на диск — когда человек отпустил границу (пока тянет, их десятки)."""
        self.store.window["columns"] = [round(v, 4) for v in shares]
        self._columns_save.start()

    def _remember_list_height(self, height: int) -> None:
        self.store.window["list_h"] = height
        self.store.save()

    def _toggle_all(self) -> None:
        current = self._active()
        on = len(self._checked()) != len(current.entries)
        for entry in current.entries:
            entry.enabled = on
        self.store.save()
        self._fill_table()                  # кнопка вне списка — перестраивать можно (п. 70)

    # ------------------------------------------------------------------ правка
    def _pick_folders(self) -> None:
        current = self._active()
        start = str(Path(current.entries[-1].source).parent) if current and current.entries else "P:/"
        folder = QFileDialog.getExistingDirectory(self, T("dialog.pick.folder"), start)
        if folder:
            self._add_folders([folder])

    def _add_folders(self, folders: List[str]) -> None:
        if self._busy():
            return
        current = self._active()            # без набора — в рабочий список
        known = {Path(e.source) for e in current.entries}
        fresh = []
        for folder in folders:                # повтор внутри одного перетаскивания — тоже повтор
            if Path(folder) not in known:
                known.add(Path(folder))
                fresh.append(str(Path(folder)))
        if not fresh:
            return
        current.entries.extend(Entry(f) for f in fresh)
        self.store.save()
        self._fill_table()
        self._refresh_states()

    def _change_source(self, row: int) -> None:
        current = self._active()
        if current is None or self._busy():
            return
        entry = current.entries[row]
        folder = QFileDialog.getExistingDirectory(self, T("dialog.pick.folder"), entry.source)
        if folder:
            entry.source = str(Path(folder))
            self.store.save()
            self._fill_table()
            self._refresh_states()

    def _own_target(self, row: int) -> None:
        """Своя папка для этого PBO — то же правило Addons, что и у общей папки."""
        current = self._active()
        entry = current.entries[row]
        start = str(Path(entry.target).parent) if entry.target else (current.target_dir or entry.source)
        folder = QFileDialog.getExistingDirectory(self, T("dialog.pick.row_where"), start)
        if folder:
            entry.target = str(Path(addons_dir(str(Path(folder)))) / (Path(entry.source).name + ".pbo"))
            self.store.save()
            self._fill_table()
            self._refresh_states()

    def _set_target(self, row: int) -> None:
        current = self._active()
        current.entries[row].target = ""
        self.store.save()
        self._fill_table()
        self._refresh_states()

    def _selected_rows(self) -> List[int]:
        return sorted({i.row() for i in self.table.selectedIndexes()})

    def _remove_selected(self) -> None:
        self._remove(self._selected_rows())

    def _remove(self, rows: List[int]) -> None:
        current = self._active()
        rows = sorted(set(rows))
        if current is None or self._busy() or not rows:
            return
        # подтверждения нет — есть «Вернуть» (п. 56): ссылка в журнале и Ctrl+Z
        self._removed = (current.name, [(r, current.entries[r]) for r in rows])
        for row in reversed(rows):
            del current.entries[row]
        names = ", ".join(e.pbo_name() for _, e in self._removed[1])
        self.journal.appendHtml('<span style="color:%s;">%s</span> %s' % (
            tokens.color("text_dim"), html.escape(T("log.removed", names=names)),
            act_link("undo", T("log.undo"))))
        self._apply_list_change()

    def _undo_remove(self) -> None:
        """Вернуть убранное в последний раз — туда же, где строки стояли."""
        if self._removed is None or self._busy():
            return
        name, rows = self._removed
        target = self.store.find(name)
        self._removed = None
        if target is None:
            return
        for row, entry in rows:
            target.entries.insert(min(row, len(target.entries)), entry)
        if self.store.current != name:
            self.store.current = name
            self._fill_sets()
        self.journal.appendHtml('<span style="color:%s;">%s</span>' % (
            tokens.color("text_dim"),
            html.escape(T("log.restored", names=", ".join(e.pbo_name() for _, e in rows)))))
        self._apply_list_change()

    def _on_journal_action(self, action: str) -> None:
        if action == "undo":
            self._undo_remove()

    def _apply_list_change(self) -> None:
        self.store.save()
        self.states.clear()
        self.state_links.clear()
        self._fill_table()
        # выделение не переезжает на соседнюю строку: второй Delete убрал бы её
        self.table.clearSelection()
        self.table.setCurrentItem(None)
        self._refresh_states()

    def _pick_where(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, T("dialog.pick.where"), self.where.text())
        if folder:
            self.where.setText(str(Path(folder)))
            self._on_where_edited()

    def _on_where_edited(self) -> None:
        current = self._active()
        if current is None:
            return
        text = self.where.text().strip()
        # PBO кладём в Addons: выбрали сам @мод — в его Addons, есть она или нет (видно в поле)
        value = addons_dir(str(Path(text))) if text else ""
        if value != self.where.text():
            self.where.blockSignals(True)
            self.where.setText(value)
            self.where.blockSignals(False)
        if value != current.target_dir:
            current.target_dir = value
            self.where.setToolTip(value)
            self.store.save()
            self._sync()
            self._refresh_states()

    def _row_menu(self, pos) -> None:
        # правый клик дублирует видимые действия и даёт редкие (п. 47)
        row = self.table.rowAt(pos.y())
        current = self._active()
        if row < 0 or current is None:
            return
        entry = current.entries[row]
        rows = sorted({i.row() for i in self.table.selectedIndexes()} | {row})
        busy = self._busy()
        menu = RoundMenu(parent=self)

        def act(icon, text, slot, enabled=True):
            a = Action(icon, text, triggered=slot)
            a.setEnabled(enabled)
            menu.addAction(a)

        act(FluentIcon.FOLDER, T("row.change_source"), lambda: self._change_source(row), not busy)
        act(FluentIcon.SAVE_AS, T("row.own_target"), lambda: self._own_target(row), not busy)
        if entry.target:
            act(FluentIcon.SYNC, T("row.set_target"), lambda: self._set_target(row), not busy)
        menu.addSeparator()
        act(FluentIcon.FOLDER, T("row.open_source"), lambda: self._open(entry.source))
        target = entry.pbo_path(current.target_dir)
        act(FluentIcon.FOLDER, T("row.open_target"), lambda: self._open(str(target.parent)),
            bool(target) and target.parent.exists())
        log = self._log_for(row)
        act(FluentIcon.DOCUMENT, T("row.open_log"), lambda: self._open(str(log)),
            log is not None and log.exists())
        menu.addSeparator()
        act(FluentIcon.DELETE, T("row.remove"), lambda: self._remove(rows), not busy)
        menu.exec(self.table.viewport().mapToGlobal(pos))

    # ================================================================== запуск
    def _jobs(self, rows: List[int]) -> List[tuple]:
        current = self._active()
        return [(r, current.entries[r].source, str(current.entries[r].pbo_path(current.target_dir)))
                for r in rows]

    def _start(self) -> None:
        if self._busy():
            return
        rows = self._ready()
        if not rows:
            self.journal.appendHtml('<span style="color:%s;">%s</span>'
                                    % (tokens.color("warning"), T("log.nothing")))
            return
        current = self._active()
        self.last_run = []
        self._started = {}
        self.journal.clear()
        self.packing.start([current.entries[r].pbo_name() for r in rows])
        for row in rows:
            self._set_state(row, T("state.queued"), "text_dim")
        self._run(BuildWorker(self._jobs(rows), full=not self.use_temp.isChecked(),
                              settings_file=self.settings_file, parent=self), quiet=False, total=len(rows))

    def _refresh_states(self) -> None:
        """Тихий план по строкам — где есть что паковать."""
        current = self._active()
        if self._busy() or current is None or not current.entries:
            return
        rows = []
        for row, entry in enumerate(current.entries):
            if not Path(entry.source).is_dir():
                self._set_state(row, T("state.no_source"), "error")
            elif entry.pbo_path(current.target_dir) is None:
                self._set_state(row, T("state.no_target"), "warning")
            else:
                # прежнее состояние держим до ответа: «проверяю…» на каждом возвращении в окно мигало
                if row not in self.states:
                    self._set_state(row, T("state.checking"), "text_dim")
                rows.append(row)
        if rows:
            self._planned_at = time.monotonic()
            self._run(BuildWorker(self._jobs(rows), plan=True, settings_file=self.settings_file,
                                  parent=self), quiet=True, total=len(rows))

    def _run(self, worker: BuildWorker, *, quiet: bool, total: int) -> None:
        self.worker = worker
        self._quiet = quiet
        self._total = total
        self._done = {"ok": 0, "bad": 0}
        self._sync()
        if not quiet:
            self.progress.setRange(0, 0)
            self.progress.setVisible(True)
            self.progress_label.setVisible(True)
            self.stop_btn.setVisible(True)
            self.stop_btn.setEnabled(True)
        worker.entry_started.connect(self._on_started)
        worker.progress.connect(self._on_progress)
        worker.entry_finished.connect(self._on_finished)
        worker.all_finished.connect(self._on_all_finished)
        worker.start()

    def _stop(self) -> None:
        if self.worker is not None and not self._quiet:
            self.worker.stop()
            self.stop_btn.setEnabled(False)
            self.progress_label.setText(T("main.stopping"))

    def _name(self, row: int) -> str:
        current = self._active()
        return current.entries[row].pbo_name() if current else "?"

    def _on_started(self, row: int) -> None:
        if self._quiet:
            return
        self._started[row] = time.monotonic()
        self.packing.set_status(self._name(row), PACKING)
        self._set_state(row, T("state.building"), "warning")

    def _on_progress(self, row: int, stage: str, done: int, total: int) -> None:
        if self._quiet:
            return
        label = {"скан": T("stage.скан"), "копирование": T("stage.копирование"),
                 "сборка": T("stage.сборка"), "texHeaders": T("stage.texHeaders"),
                 "ссылки": T("stage.ссылки"), "упаковка": T("stage.упаковка"),
                 "подпись": T("stage.подпись")}.get(stage, stage)
        if total:
            self.progress.setRange(0, total)
            self.progress.setValue(done)
            self.progress_label.setText(T("progress.count", pbo=self._name(row), stage=label,
                                          done=done, total=total))
        else:
            self.progress.setRange(0, 0)
            self.progress_label.setText(T("progress.stage", pbo=self._name(row), stage=label))

    def _on_finished(self, row: int, report: Optional[Result], error: str) -> None:
        name = self._name(row)
        if self._quiet:
            self._plan_state(row, report, error)
            return
        ms = int((time.monotonic() - self._started.get(row, time.monotonic())) * 1000)
        log = report.log if report is not None and report.log else None
        if report is None and not error:           # остановлено
            self._set_state(row, T("state.unknown"), "text_dim")
            self.packing.set_status(name, FAIL, ms)
            return
        self.last_run.append({"row": row, "name": name, "report": report, "error": error,
                              "log": str(log) if log else ""})
        if report is None:
            self._done["bad"] += 1
            self._set_state(row, T("state.error"), "error", link="error")
            self.packing.set_status(name, FAIL, ms, errors=1)
            self._journal_errors([(None, error)])
            return
        warnings, errors = len(report.warnings), len(report.errors)
        if errors and not report.ok:
            self._done["bad"] += 1
            self._set_state(row, T("state.failed", count=errors), "error", link="error")
            self.packing.set_status(name, FAIL, ms, warnings, errors)
            self._journal_errors([(Path(report.source) / src, text) for src, text in report.errors])
        elif errors:
            # «игнорировать ошибки»: PBO собран, ошибки — в журнале и в логах
            self._done["ok"] += 1
            stamp = time.strftime("%H:%M")
            if report.packed:
                self.packed_at[name] = (stamp, "error")
            self._set_state(row, T("state.forced", count=errors, time=stamp), "error", link="error")
            self.packing.set_status(name, OK, ms, warnings, errors)
            self._journal_errors([(Path(report.source) / src, text) for src, text in report.errors])
        else:
            self._done["ok"] += 1
            stamp = time.strftime("%H:%M")
            link = "warning" if warnings else ""
            if report.packed:
                self.packed_at[name] = (stamp, link)
            self._set_state(row, T("state.built", time=stamp) if report.packed else T("state.same"),
                            "success", link=link)
            self.packing.set_status(name, OK, ms, warnings, 0)

    def _journal_errors(self, rows: List[tuple]) -> None:
        """Первые ошибки — сразу в журнал: «[ERROR] файл: где. В чём», имя — ссылка."""
        self._pending_errors = getattr(self, "_pending_errors", [])
        self._pending_errors += [finding_html("error", path, text) for path, text in rows[:3]]
        if len(rows) > 3:
            self._pending_errors.append(html.escape(T("log.more")))

    def _plan_state(self, row: int, report: Optional[Result], error: str) -> None:
        if report is None:
            self._set_state(row, T("state.error") if error else T("state.unknown"),
                            "error" if error else "text_dim")
        elif report.errors and not report.ok:
            self._set_state(row, T("state.failed", count=len(report.errors)), "error")
        elif not report.changed:
            packed = self.packed_at.get(self._name(row))
            if packed:
                self._set_state(row, T("state.clean_built", time=packed[0]), "success", link=packed[1])
            else:
                self._set_state(row, T("state.clean"), "success")
        elif report.never_built:
            self._set_state(row, T("state.never"), "warning")
        else:
            self._set_state(row, T("state.changed", count=report.changed),
                            "warning")

    def _on_all_finished(self, cancelled: bool) -> None:
        worker, self.worker = self.worker, None
        if worker is not None:
            worker.wait()
            worker.deleteLater()
        quiet = self._quiet
        self.progress.setVisible(False)
        self.progress_label.setVisible(False)
        self.stop_btn.setVisible(False)
        if not quiet:
            self.packing.stop()
            if cancelled:
                line, role = T("log.cancelled"), "warning"
            elif self._done["bad"]:
                line, role = T("log.done.bad", ok=self._done["ok"], total=self._total,
                               bad=self._done["bad"]), "error"
            else:
                line, role = T("log.done", ok=self._done["ok"], total=self._total), "success"
            body = ['<div style="color:%s;">%s</div>' % (tokens.color(role), html.escape(line))]
            body += ["<div>%s</div>" % e for e in getattr(self, "_pending_errors", [])]
            self._pending_errors = []
            self.journal.appendHtml("".join(body))
        self._sync()

    def _save_option(self, key: str, on: bool) -> None:
        """Опция главного окна — общая настройка сборки: пишется сразу, как в окне настроек."""
        values = read_global_settings(self.settings_file)
        values[key] = bool(on)
        problem = check_settings(values, self.settings_file)
        if problem:
            self.journal.appendHtml('<span style="color:%s;">%s</span>'
                                    % (tokens.color("error"), html.escape(T("settings.error", text=problem))))
            return
        write_global_settings(self.settings_file, values)
        self._refresh_states()

    # ================================================================== окна
    def _open_settings(self) -> None:
        SettingsDialog(self.settings_file, self, store=self.store).exec()
        # опции главного окна — те же настройки: вдруг их сменили не здесь (файл, QTS)
        values = read_global_settings(self.settings_file)
        for box, key, default in ((self.binarize, "binarize_models", True), (self.rapify, "rapify", True),
                                  (self.force, "ignore_errors", False)):
            box.blockSignals(True)
            box.setChecked(bool(values.get(key, default)))
            box.blockSignals(False)
        self._refresh_states()

    def _on_theme_changed(self, *_args) -> None:
        """Свои цвета, выданные при сборке, перекрасить под новую тему (п. 37)."""
        self._style_drop_zone()
        for row in range(self.table.rowCount()):
            self._paint_where(row)
            self._paint_state(row)
        # тема меняется и из DevToolkit: без этого в светлой журнал оставался тёмным (1,2–1,8:1)
        recolor.retint(self.journal.document())

    def _style_drop_zone(self) -> None:
        self.empty_zone.setStyleSheet("#dropZone{border:1px dashed %s;border-radius:%dpx;}"
                                      % (tokens.color("divider"), tokens.RADIUS_CARD))

    def _open_logs(self) -> None:
        LogsDialog(self.last_run, self).exec()

    def _open_logs_for(self, name: str, level: str) -> None:
        """Окно логов сразу на этом PBO и на его ошибках или предупреждениях."""
        LogsDialog(self.last_run, self, select=name, focus=level).exec()

    def _log_for(self, row: int) -> Optional[Path]:
        for item in self.last_run:
            if item["row"] == row and item["log"]:
                return Path(item["log"])
        return None

    def _open(self, path: str) -> None:
        if path and Path(path).exists():
            os.startfile(path)  # noqa: S606 — открыть папку или лог штатным приложением

    def changeEvent(self, event) -> None:
        super().changeEvent(event)
        # вернулся после правок в редакторе — освежить «есть что паковать»
        if event.type() == QEvent.ActivationChange and hasattr(self, "table") and self.isActiveWindow() \
                and time.monotonic() - self._planned_at > 5 and not self._busy():
            QTimer.singleShot(0, self._refresh_states)

    def keyPressEvent(self, event) -> None:
        # Esc — остановить запаковку, а не закрыть окно (п. 46)
        if event.key() == Qt.Key_Escape:
            self._stop()
            return
        super().keyPressEvent(event)

    def closeEvent(self, event) -> None:
        if self.worker is not None:
            self.worker.stop()
            self.worker.wait()
        self.store.window["size"] = [self.width(), self.height()]
        self.store.save()
        super().closeEvent(event)
