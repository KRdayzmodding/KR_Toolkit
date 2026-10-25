# -*- coding: utf-8 -*-
"""Главное окно [KR] Addon Signer — подписи PBO по папкам.

Заказ юзера 23.10.2026:

* создавать ключи; список ключей — выпадающим списком, в него добавляются и
  новые, и существующие;
* в окно добавляются папки; тулза находит в них PBO и смотрит, есть ли подпись
  выбранным ключом и сходится ли она с текущим PBO;
* кнопка внизу подписывает то, что без подписи, и обновляет устаревшее;
* пресеты хранят списки папок.

Оформление — как [KR] Project Builder: qfluentwidgets, токены `qts_ui.tokens`.
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Dict, List, Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QAbstractItemView, QApplication, QFileDialog, QHBoxLayout, QHeaderView, QStackedWidget,
    QTableWidgetItem, QVBoxLayout, QWidget)
from qfluentwidgets import (
    BodyLabel, CaptionLabel, ComboBox, FluentIcon, LineEdit, ListWidget, MessageBox,
    MessageBoxBase, PrimaryPushButton, ProgressBar, PushButton, StrongBodyLabel, SubtitleLabel,
    TableWidget, TransparentPushButton, TransparentToolButton, qconfig)

from qts_ui import tokens
from qts_ui.rows import shrink
from qts_ui.frame import ToolWindow
from store import SCRATCH, Store
from texts import T
import worker as sg
from worker import Job

#: порядок столбцов — решение юзера 23.10.2026: галка, подпись, PBO, папка
COL_CHECK, COL_STATE, COL_PBO, COL_WHERE = range(4)
#: ключ сортировки — в своей роли: текст подписи сортировал бы по алфавиту
SORT_ROLE = Qt.UserRole + 1
PATH_ROLE = Qt.UserRole + 2
#: порядок состояний при сортировке: сначала то, что требует действия
STATE_ORDER = {sg.MISSING: 0, sg.STALE: 1, sg.FOREIGN: 2, sg.BROKEN: 3, sg.OK: 4}
#: что можно отметить к подписи: подписанное верно переподписывать незачем, битое — нечем
CHECKABLE = (sg.MISSING, sg.STALE, sg.FOREIGN)
MIN = (620, 660)            # минимальный размер — он же размер первого запуска
FOLDERS_H = 96              # список папок: три строки, остальное — таблице PBO
#: состояние → роль цвета
ROLE = {sg.OK: "success", sg.STALE: "warning", sg.MISSING: "text_dim",
        sg.FOREIGN: "info", sg.BROKEN: "error"}
#: состояние → ключ текста; ключи буквально, не из кусков (п. 66)
STATE_TEXT = {sg.OK: "state.ok", sg.STALE: "state.stale", sg.MISSING: "state.missing",
              sg.FOREIGN: "state.foreign", sg.BROKEN: "state.broken"}


class SortItem(QTableWidgetItem):
    """Ячейка, которая сортируется по своему ключу (SORT_ROLE), а не по тексту."""

    def _key(self):
        if self.column() == COL_CHECK:
            # отмеченные, потом неотмеченные, потом без галки; внутри — по состоянию
            checkable = bool(self.flags() & Qt.ItemIsUserCheckable)
            on = checkable and self.checkState() == Qt.Checked
            return (0 if on else 1 if checkable else 2, self.data(SORT_ROLE) or 0)
        return self.data(SORT_ROLE)

    def __lt__(self, other):
        mine, theirs = self._key(), other._key() if isinstance(other, SortItem) else None
        if mine is not None and theirs is not None:
            return mine < theirs
        return super().__lt__(other)


class NameDialog(MessageBoxBase):
    """Название пресета. Занятое имя — подсказка прямо под полем, окно не закрывается."""

    def __init__(self, title: str, taken: List[str], text: str = "", parent=None):
        super().__init__(parent)
        self.taken = set(taken) - {text}
        self.viewLayout.addWidget(SubtitleLabel(title, self))
        self.edit = LineEdit(self)
        self.edit.setPlaceholderText(T("preset.new.prompt"))
        self.edit.setText(text)
        self.edit.setMinimumWidth(320)
        self.edit.textChanged.connect(self._check)
        self.viewLayout.addWidget(self.edit)
        self.hint = CaptionLabel("", self)
        self.viewLayout.addWidget(self.hint)
        self.yesButton.setText(T("dialog.ok"))
        self.cancelButton.setText(T("dialog.cancel"))
        self._check()
        self.edit.setFocus()

    def name(self) -> str:
        return self.edit.text().strip()

    def _check(self) -> None:
        name = self.name()
        clash = name in self.taken
        self.hint.setText(T("preset.name.taken", name=name) if clash else "")
        self.hint.setTextColor(tokens.color("error"), tokens.color("error"))
        self.yesButton.setEnabled(bool(name) and not clash)


class MainWindow(ToolWindow):
    def __init__(self, store: Store):
        super().__init__(FluentIcon.CERTIFICATE, image="AddonSigner")              # своя шапка, как в QTS (qts_ui.frame)
        self.store = store
        # память о проверках — рядом с файлом окна: тест с копией не трогает настоящую
        from kr_state import state_file
        # файл ведёт командная строка; окно только говорит ей, где он
        self.cache_path = state_file("addon_signer_cache.json", "sign_studio_cache.json",
                                     root=store.path.parent)
        #: PBO → имена ключей подписей рядом (когда ключ не выбран)
        self.found_signatures: dict = {}
        self.job: Optional[Job] = None
        self.signing = False
        self.pbos: List[str] = []
        # строки сортируются — поэтому всё по пути PBO, а не по номеру строки
        self.states: Dict[str, tuple] = {}            # PBO → (состояние, подробность)
        self.rows: Dict[str, QTableWidgetItem] = {}   # PBO → его ячейка-галка (номер строки — .row())
        self._backups: List[str] = []
        self._signed = 0

        self.setWindowTitle(T("app.title"))
        self.setMinimumSize(*MIN)
        # первый запуск — минимальный размер; дальше — тот, в котором окно оставили (п. 87)
        w, h = self.store.window.get("size", MIN)
        self.resize(max(w, MIN[0]), max(h, MIN[1]))
        self.setAcceptDrops(True)                    # папки — перетаскиванием (п. 49)
        self._build()
        self._fill_keys()
        self._fill_presets()
        qconfig.themeChanged.connect(self._paint_states)

    # ================================================================== сборка окна
    def _build(self) -> None:
        root = QVBoxLayout(self.body)
        root.setContentsMargins(tokens.SPACE_M, tokens.SPACE_M, tokens.SPACE_M, tokens.SPACE_M)
        root.setSpacing(tokens.SPACE_S)

        # --- ключ: от него зависят все состояния — строкой сверху (п. 7)
        head = QHBoxLayout()
        head.setSpacing(tokens.SPACE_XS)
        head.addWidget(self._label(T("key.label")))
        self.key_box = ComboBox(self)
        self.key_box.currentIndexChanged.connect(self._on_key_chosen)
        head.addWidget(self.key_box, 1)
        self.key_create = PushButton(FluentIcon.ADD, T("key.create"), self)
        self.key_create.clicked.connect(self._create_key)
        head.addWidget(self.key_create)
        self.key_add = PushButton(FluentIcon.FOLDER_ADD, T("key.add"), self)
        self.key_add.clicked.connect(self._add_key)
        head.addWidget(self.key_add)
        self.key_remove = TransparentToolButton(FluentIcon.REMOVE, self)
        self.key_remove.setToolTip(T("key.remove"))
        self.key_remove.clicked.connect(self._remove_key)
        head.addWidget(self.key_remove)
        root.addLayout(head)
        self.key_error = shrink(CaptionLabel("", self))
        root.addWidget(self.key_error)

        # --- пресет
        pre = QHBoxLayout()
        pre.setSpacing(tokens.SPACE_XS)
        pre.addWidget(self._label(T("preset.label")))
        self.preset_box = ComboBox(self)
        self.preset_box.currentIndexChanged.connect(self._on_preset_chosen)
        pre.addWidget(self.preset_box, 1)
        self.preset_new = TransparentToolButton(FluentIcon.ADD, self)
        self.preset_new.setToolTip(T("preset.new"))
        self.preset_new.clicked.connect(self._new_preset)
        pre.addWidget(self.preset_new)
        self.preset_rename = TransparentToolButton(FluentIcon.EDIT, self)
        self.preset_rename.setToolTip(T("preset.rename"))
        self.preset_rename.clicked.connect(self._rename_preset)
        pre.addWidget(self.preset_rename)
        self.preset_delete = TransparentToolButton(FluentIcon.DELETE, self)
        self.preset_delete.setToolTip(T("preset.delete"))
        self.preset_delete.clicked.connect(self._delete_preset)
        pre.addWidget(self.preset_delete)
        root.addLayout(pre)

        # --- папки
        fh = QHBoxLayout()
        fh.addWidget(StrongBodyLabel(T("folders.title"), self))
        fh.addStretch(1)
        self.folder_add = TransparentToolButton(FluentIcon.FOLDER_ADD, self)
        self.folder_add.setToolTip(T("folders.add"))
        self.folder_add.clicked.connect(self._pick_folder)
        fh.addWidget(self.folder_add)
        self.folder_remove = TransparentToolButton(FluentIcon.REMOVE, self)
        self.folder_remove.setToolTip(T("folders.remove"))
        self.folder_remove.clicked.connect(self._remove_folders)
        fh.addWidget(self.folder_remove)
        root.addLayout(fh)
        self.folder_stack = QStackedWidget(self)
        self.folder_stack.setFixedHeight(FOLDERS_H)
        # пусто: приглашение перетащить и обычный путь рядом (жест — ускоритель, п. 10)
        empty = QWidget(self.folder_stack)
        el = QVBoxLayout(empty)
        el.addStretch(1)
        drop = shrink(BodyLabel(T("folders.drop"), empty))
        drop.setAlignment(Qt.AlignCenter)
        el.addWidget(drop)
        pick_row = QHBoxLayout()
        pick_row.addStretch(1)
        self.folder_pick = PushButton(FluentIcon.FOLDER_ADD, T("folders.pick"), empty)
        self.folder_pick.clicked.connect(self._pick_folder)
        pick_row.addWidget(self.folder_pick)
        pick_row.addStretch(1)
        el.addLayout(pick_row)
        el.addStretch(1)
        self.folder_stack.addWidget(empty)
        self.folder_list = ListWidget(self.folder_stack)
        self.folder_list.setSelectionMode(QAbstractItemView.ExtendedSelection)
        # длинный путь ужимается посередине, полный — в подсказке; без прокрутки вбок
        self.folder_list.setTextElideMode(Qt.ElideMiddle)
        self.folder_list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.folder_list.itemSelectionChanged.connect(self._sync)
        QShortcut(QKeySequence.Delete, self.folder_list, activated=self._remove_folders,
                  context=Qt.WidgetShortcut)
        self.folder_stack.addWidget(self.folder_list)
        root.addWidget(self.folder_stack)

        # --- PBO и их подписи
        th = QHBoxLayout()
        th.addWidget(StrongBodyLabel(T("pbo.title"), self))
        th.addStretch(1)
        self.all_btn = TransparentPushButton(T("pbo.all"), self)
        self.all_btn.clicked.connect(self._toggle_all)
        th.addWidget(self.all_btn)
        root.addLayout(th)
        self.table = TableWidget(self)
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["", T("col.state"), T("col.pbo"), T("col.where")])
        self.table.verticalHeader().hide()
        self.table.setBorderVisible(True)
        self.table.setBorderRadius(tokens.RADIUS_CARD)
        self.table.setWordWrap(False)
        self.table.setTextElideMode(Qt.ElideMiddle)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        hdr = self.table.horizontalHeader()
        hdr.setSectionResizeMode(COL_CHECK, QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(COL_STATE, QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(COL_PBO, QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(COL_WHERE, QHeaderView.Stretch)
        # заголовок — сортировка (юзер 23.10.2026); выбранная запоминается
        column, order = self.store.window.get("sort", [COL_PBO, 0])
        hdr.setSortIndicator(int(column), Qt.SortOrder(int(order)))
        hdr.sortIndicatorChanged.connect(self._remember_sort)
        self.table.setSortingEnabled(True)
        self.table.itemChanged.connect(self._on_item_changed)
        # двойной щелчок — открыть объект: папку PBO с выделенным файлом (п. 45)
        self.table.cellDoubleClicked.connect(lambda row, _c: self._show_in_folder(row))
        root.addWidget(self.table, 1)

        self.summary = shrink(CaptionLabel("", self))
        root.addWidget(self.summary)
        self.progress = ProgressBar(self)
        root.addWidget(self.progress)

        # --- кнопки: одна первичная (п. 19)
        bottom = QHBoxLayout()
        bottom.setSpacing(tokens.SPACE_XS)
        self.rescan_btn = PushButton(FluentIcon.SYNC, T("main.rescan"), self)
        self.rescan_btn.clicked.connect(self._rescan)
        bottom.addWidget(self.rescan_btn)
        bottom.addStretch(1)
        self.sign_btn = PrimaryPushButton(FluentIcon.CERTIFICATE, T("main.sign.empty"), self)
        self.sign_btn.setDefault(True)                       # Enter (п. 46)
        self.sign_btn.clicked.connect(self._start_sign)
        bottom.addWidget(self.sign_btn)
        root.addLayout(bottom)

        # видимость — последней, когда иерархия собрана (п. 69)
        self.key_error.setVisible(False)
        self.progress.setVisible(False)

    def _label(self, text: str) -> BodyLabel:
        label = BodyLabel(text, self)
        label.setFixedWidth(60)                               # «Ключ» и «Пресет» — одной колонкой
        return label

    # ================================================================== ключи
    def _fill_keys(self) -> None:
        self.key_box.blockSignals(True)
        self.key_box.clear()
        names = [self._key_name(p) for p in self.store.keys]
        for path, name in zip(self.store.keys, names):
            # имя ключа; папка — только когда имена совпадают, полный путь — в подсказке
            text = "%s — %s" % (name, Path(path).parent) if names.count(name) > 1 else name
            self.key_box.addItem(text, userData=path)
        if not self.store.keys:
            self.key_box.setPlaceholderText(T("key.none"))
        if self.store.key in self.store.keys:
            self.key_box.setCurrentIndex(self.store.keys.index(self.store.key))
        else:
            self.key_box.setCurrentIndex(-1)
        self.key_box.setToolTip(self.store.key)
        self.key_box.blockSignals(False)
        self._check_key()

    @staticmethod
    def _key_name(path: str) -> str:
        name = Path(path).name
        return name[:-len(".biprivatekey")] if name.lower().endswith(".biprivatekey") else Path(path).stem

    def _check_key(self) -> None:
        """Выбранный ключ на месте и приватный — иначе причина строкой под ним (п. 26)."""
        problem = ""
        path = self.store.key
        if path:
            info = sg.key_info(path)
            if info.get("error") == "missing":
                problem = T("key.missing", path=path)
            elif info.get("error"):
                problem = T("key.unreadable", text=info["error"])
            elif not info.get("private"):
                problem = T("key.public", name=Path(path).name)
        self.key_error.setText(problem)
        self.key_error.setTextColor(tokens.color("error"), tokens.color("error"))
        self.key_error.setVisible(bool(problem))
        self._key_ok = bool(path) and not problem

    def _on_key_chosen(self, index: int) -> None:
        path = self.key_box.itemData(index) if index >= 0 else ""
        if path and path != self.store.key:
            self.store.key = path
            self.store.save()
            self.key_box.setToolTip(path)
            self._check_key()
            self._rescan()

    def _take_key(self, path: str) -> bool:
        """Только читаемый приватный ключ попадает в список."""
        info = sg.key_info(path)
        if info.get("error"):
            self._error(T("key.unreadable", text=info["error"]))
            return False
        if not info.get("private"):
            self._error(T("key.public", name=Path(path).name))
            return False
        self.store.add_key(path)
        self._fill_keys()
        self._rescan()
        return True

    def _add_key(self) -> None:
        start = str(Path(self.store.key).parent) if self.store.key else ""
        path, _ = QFileDialog.getOpenFileName(self, T("key.add.title"), start, "*.biprivatekey")
        if path:
            self._take_key(str(Path(path)))

    def _create_key(self) -> None:
        """Имя и папка — одним окном сохранения. Занятое имя — отказ: новый ключ под
        старым именем сломал бы все подписанные им PBO."""
        start = str(Path(self.store.key).parent) if self.store.key else ""
        path, _ = QFileDialog.getSaveFileName(self, T("key.create.title"), start, "*.biprivatekey",
                                              options=QFileDialog.Option.DontConfirmOverwrite)
        if not path:
            return
        target = Path(path)
        name = target.name[:-len(".biprivatekey")] if target.name.lower().endswith(".biprivatekey") \
            else target.name
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            prv, pub = sg.create_key(name, target.parent)
        except RuntimeError as exc:
            self._error(str(exc))
            return
        finally:
            QApplication.restoreOverrideCursor()
        if self._take_key(str(prv)):
            box = MessageBox(T("key.create.title"),
                             T("key.created", prv=prv.name, pub=pub.name, folder=prv.parent), self)
            box.yesButton.setText(T("dialog.ok"))
            box.cancelButton.hide()
            box.exec()

    def _remove_key(self) -> None:
        if self.store.key:
            self.store.remove_key(self.store.key)
            self._fill_keys()
            self._rescan()

    def _error(self, text: str) -> None:
        box = MessageBox(T("app.title"), text, self)
        box.yesButton.setText(T("dialog.ok"))
        box.cancelButton.hide()
        box.exec()

    # ================================================================== пресеты
    def _fill_presets(self) -> None:
        """Первый пункт — рабочий список «без пресета»: пресет помощник, а не условие."""
        self.preset_box.blockSignals(True)
        self.preset_box.clear()
        self.preset_box.addItem(T("preset.scratch"), userData=SCRATCH)
        for named in self.store.named():
            self.preset_box.addItem(named.name, userData=named.name)
        names = [SCRATCH] + [n.name for n in self.store.named()]
        current = self.store.active().name
        self.preset_box.setCurrentIndex(names.index(current) if current in names else 0)
        self.preset_box.blockSignals(False)
        self._show_preset()

    def _on_preset_chosen(self, index: int) -> None:
        name = (self.preset_box.itemData(index) if index >= 0 else SCRATCH) or SCRATCH
        if name != self.store.current:
            self.store.current = name
            self.store.save()
            self._show_preset()

    def _new_preset(self) -> None:
        """На рабочем списке с папками — сохранить его пресетом; иначе — новый пустой."""
        current = self.store.active()
        promote = current.name == SCRATCH and bool(current.folders)
        dlg = NameDialog(T("preset.save.title") if promote else T("preset.new.title"),
                         [p.name for p in self.store.named()], parent=self)
        if dlg.exec():
            (self.store.promote if promote else self.store.create)(dlg.name())
            self._fill_presets()

    def _rename_preset(self) -> None:
        current = self.store.active()
        if current.name == SCRATCH:
            return
        dlg = NameDialog(T("preset.rename.title"), [p.name for p in self.store.named()],
                         current.name, parent=self)
        if dlg.exec() and dlg.name() != current.name:
            self.store.rename(current.name, dlg.name())
            self._fill_presets()

    def _delete_preset(self) -> None:
        current = self.store.active()
        if current.name == SCRATCH:
            return
        # отмены у удаления нет — поэтому подтверждение (п. 56)
        box = MessageBox(T("preset.delete.title", name=current.name), T("preset.delete.text"), self)
        box.yesButton.setText(T("preset.delete"))
        box.cancelButton.setText(T("dialog.cancel"))
        if box.exec():
            self.store.delete(current.name)
            self._fill_presets()

    def _show_preset(self) -> None:
        folders = self.store.active().folders
        self.folder_list.clear()
        for folder in folders:
            self.folder_list.addItem(folder)
            self.folder_list.item(self.folder_list.count() - 1).setToolTip(folder)
        self.folder_stack.setCurrentIndex(1 if folders else 0)
        self._rescan()

    # ================================================================== папки
    def _add_folders(self, folders: List[str]) -> None:
        preset = self.store.active()
        known = {os.path.normcase(f) for f in preset.folders}
        added = []
        for folder in folders:
            folder = str(Path(folder))
            if os.path.normcase(folder) not in known:
                known.add(os.path.normcase(folder))
                added.append(folder)
        if added:
            preset.folders.extend(added)
            self.store.save()
            self._show_preset()

    def _pick_folder(self) -> None:
        folders = self.store.active().folders
        folder = QFileDialog.getExistingDirectory(self, T("folders.pick.title"),
                                                  folders[-1] if folders else "")
        if folder:
            self._add_folders([folder])

    def _remove_folders(self) -> None:
        rows = sorted({self.folder_list.row(i) for i in self.folder_list.selectedItems()},
                      reverse=True)
        if not rows or self.signing:
            return
        preset = self.store.active()
        for row in rows:
            del preset.folders[row]
        self.store.save()
        self._show_preset()

    def dragEnterEvent(self, event):
        if not self.signing and self._dropped(event):
            event.acceptProposedAction()

    def dragMoveEvent(self, event):
        if not self.signing and self._dropped(event):
            event.acceptProposedAction()

    def dropEvent(self, event):
        folders = self._dropped(event)
        if folders and not self.signing:
            event.acceptProposedAction()
            self._add_folders(folders)

    @staticmethod
    def _dropped(event) -> List[str]:
        data = event.mimeData()
        if not data.hasUrls():
            return []
        return [u.toLocalFile() for u in data.urls()
                if u.isLocalFile() and Path(u.toLocalFile()).is_dir()]

    # ================================================================== проверка
    def _stop_job(self) -> None:
        if self.job is not None and self.job.isRunning():
            self.job.requestInterruption()
            self.job.wait()
        self.job = None

    def _rescan(self) -> None:
        """Заново найти PBO и проверить подписи. Неизменённое берётся из памяти."""
        if self.signing:
            return
        self._stop_job()
        self._signed, self._backups = 0, []
        self.pbos, self.states, self.rows = [], {}, {}
        self.table.setRowCount(0)
        self.found_signatures = {}
        job = Job("scan", self.cache_path, key_path=self.store.key if self._key_ok else "",
                  folders=list(self.store.active().folders), parent=self)
        job.found.connect(self._on_found)
        job.signatures.connect(self._on_signatures)
        self._run(job)

    def _run(self, job: Job) -> None:
        job.state.connect(self._on_state)
        job.progress.connect(self._on_progress)
        job.backed_up.connect(self._backups.append)
        job.finished.connect(lambda j=job: self._on_finished(j))
        self.job = job
        self.progress.setValue(0)
        self._sync()
        job.start()

    def _on_signatures(self, path: str, names: list) -> None:
        """Без выбранного ключа строка показывает, чьи подписи лежат рядом."""
        self.found_signatures[path] = names
        if path in self.rows:
            self.table.setSortingEnabled(False)
            self.table.blockSignals(True)
            self._set_state(path, None, "")
            self.table.blockSignals(False)
            self.table.setSortingEnabled(True)

    def _on_found(self, pbos: List[str]) -> None:
        self.pbos = pbos
        folders = [Path(f) for f in self.store.active().folders]
        self.table.setSortingEnabled(False)               # иначе строки разъезжаются на вставке
        self.table.blockSignals(True)
        self.table.setRowCount(len(pbos))
        for row, path in enumerate(pbos):
            p = Path(path)
            check = SortItem()
            check.setData(PATH_ROLE, path)
            self.table.setItem(row, COL_CHECK, check)
            self.rows[path] = check
            item = SortItem(p.name)
            item.setData(SORT_ROLE, p.name.lower())
            item.setToolTip(path)
            self.table.setItem(row, COL_PBO, item)
            where = self._relative(p.parent, folders)
            item = SortItem(where)
            item.setData(SORT_ROLE, where.lower())
            item.setToolTip(str(p.parent))
            self.table.setItem(row, COL_WHERE, item)
            self._set_state(path, None, "")
        self.table.blockSignals(False)
        self.table.setSortingEnabled(True)
        self._sync()

    @staticmethod
    def _relative(parent: Path, folders: List[Path]) -> str:
        """Папка PBO относительно добавленной, без Addons: «@мод», «@мод\\server».

        Addons в пути есть всегда, человеку он ничего не говорит (юзер 23.10.2026).
        Если от пути ничего не осталось — имя ближайшей папки выше, не Addons.
        """
        for folder in folders:
            try:
                rest = parent.relative_to(folder)
            except ValueError:
                continue
            parts = [part for part in (folder.name,) + rest.parts
                     if part != "." and part.lower() != "addons"]
            if parts:
                return str(Path(*parts))
            break
        for up in (parent,) + tuple(parent.parents):
            if up.name and up.name.lower() != "addons":
                return up.name
        return str(parent)

    def _on_state(self, path: str, state: str, detail: str) -> None:
        if path in self.rows:
            self.states[path] = (state, detail)
            self.table.setSortingEnabled(False)
            self.table.blockSignals(True)
            self._set_state(path, state, detail)
            self.table.blockSignals(False)
            self.table.setSortingEnabled(True)
            self._sync()

    def _default_choice(self, state: str) -> bool:
        return state in sg.TO_SIGN

    def _set_state(self, path: str, state: Optional[str], detail: str) -> None:
        """Ячейки подписи и галки одной строки. Вызывать с выключенной сортировкой."""
        row = self.rows[path].row()
        if state is None:
            text = T("state.checking") if self._key_ok else T("state.no_key")
            role, tip, order = "text_dim", "", len(STATE_ORDER)
            if not self._key_ok:
                found = self.found_signatures.get(path, [])
                text = ", ".join(found) if found else T("state.no_key")
        else:
            text, role, order = T(STATE_TEXT[state]), ROLE[state], STATE_ORDER[state]
            tip = {sg.STALE: T("state.tip.stale", detail=detail),
                   sg.FOREIGN: T("state.tip.foreign"),
                   sg.BROKEN: T("state.tip.broken", detail=detail)}.get(state, "")
        item = SortItem(text)
        item.setForeground(QColor(tokens.color(role)))
        item.setData(Qt.UserRole, role)
        item.setData(SORT_ROLE, order)
        item.setToolTip(tip)
        self.table.setItem(row, COL_STATE, item)

        check = self.rows[path]
        checkable = self._key_ok and state in CHECKABLE
        flags = Qt.ItemIsSelectable | Qt.ItemIsEnabled
        if checkable:
            flags |= Qt.ItemIsUserCheckable
            on = self.store.choices.get(path, self._default_choice(state))
            check.setCheckState(Qt.Checked if on else Qt.Unchecked)
        else:
            check.setData(Qt.CheckStateRole, None)     # нечего выбирать — и галки нет
        check.setFlags(flags)
        check.setData(SORT_ROLE, order)

    def _on_item_changed(self, item: QTableWidgetItem) -> None:
        """Галка: выбор человека запоминается, если отличается от умолчания."""
        if item.column() != COL_CHECK:
            return
        path = item.data(PATH_ROLE)
        state = self.states.get(path, (None, ""))[0]
        if path is None or state not in CHECKABLE:
            return
        on = item.checkState() == Qt.Checked
        if on == self._default_choice(state):
            self.store.choices.pop(path, None)
        else:
            self.store.choices[path] = on
        self.store.save()
        self._sync()

    def _checked(self) -> List[str]:
        return [path for path in self.pbos
                if self.states.get(path, (None,))[0] in CHECKABLE
                and self.rows[path].checkState() == Qt.Checked]

    def _toggle_all(self) -> None:
        """Отметить все, что можно подписать; если все уже отмечены — снять."""
        paths = [p for p in self.pbos if self.states.get(p, (None,))[0] in CHECKABLE]
        on = len(self._checked()) < len(paths)
        self.table.setSortingEnabled(False)
        self.table.blockSignals(True)
        for path in paths:
            self.rows[path].setCheckState(Qt.Checked if on else Qt.Unchecked)
            if on == self._default_choice(self.states[path][0]):
                self.store.choices.pop(path, None)
            else:
                self.store.choices[path] = on
        self.table.blockSignals(False)
        self.table.setSortingEnabled(True)
        self.table.viewport().update()
        self.store.save()
        self._sync()

    def _remember_sort(self, column: int, order) -> None:
        self.store.window["sort"] = [column, int(order.value) if hasattr(order, "value") else int(order)]

    def _paint_states(self, *_args) -> None:
        """Смена темы на лету: цвета состояний — заново из токенов (п. 37)."""
        for row in range(self.table.rowCount()):
            item = self.table.item(row, COL_STATE)
            if item is not None and item.data(Qt.UserRole):
                item.setForeground(QColor(tokens.color(item.data(Qt.UserRole))))

    def _on_progress(self, done: int, total: int) -> None:
        self.progress.setMaximum(max(total, 1))
        self.progress.setValue(done)

    def _on_finished(self, job: Job) -> None:
        if job is not self.job:
            return
        self.job = None
        if self.signing:
            self.signing = False
        self._sync()

    # ================================================================== подпись
    def _start_sign(self) -> None:
        items = self._checked()
        if not items or self.busy() or not self._key_ok:
            return
        self.signing = True
        self._signed, self._backups = len(items), []
        job = Job("sign", self.cache_path, key_path=self.store.key, items=items,
                  backup=sg.backup_dir(), parent=self)
        self._backup_root = job.backup
        self._run(job)

    def busy(self) -> bool:
        return self.job is not None and self.job.isRunning()

    # ================================================================== состояние окна
    def _sync(self) -> None:
        """Подписи кнопок и сводка — из состояния (п. 27); на время подписи правки закрыты (п. 92)."""
        busy = self.busy()
        counts = {s: 0 for s in (sg.OK, sg.STALE, sg.MISSING, sg.FOREIGN, sg.BROKEN)}
        for state, _detail in self.states.values():
            counts[state] += 1
        checkable = sum(counts[s] for s in CHECKABLE)
        chosen = len(self._checked())
        if not self.pbos:
            label, enabled = T("main.sign.empty"), False
        elif not self._key_ok:
            label, enabled = T("main.sign.no_key"), False
        elif chosen:
            label, enabled = T("main.sign", count=chosen), not busy
        elif counts[sg.STALE] + counts[sg.MISSING]:
            label, enabled = T("main.sign.nothing_chosen"), False
        else:
            label, enabled = T("main.sign.none"), False
        self.sign_btn.setText(label)
        self.sign_btn.setEnabled(enabled)
        self.all_btn.setText(T("pbo.none") if checkable and chosen == checkable else T("pbo.all"))
        self.all_btn.setEnabled(bool(checkable) and not self.signing)

        text = T("summary.empty") if not self.pbos else T(
            "summary.counts", total=len(self.pbos), ok=counts[sg.OK], stale=counts[sg.STALE],
            missing=counts[sg.MISSING])
        if counts[sg.FOREIGN]:
            text += T("summary.foreign", foreign=counts[sg.FOREIGN])
        if counts[sg.BROKEN]:
            text += T("summary.broken", broken=counts[sg.BROKEN])
        if self._signed and not busy:
            # итог подписи не исчезает до следующего действия (п. 58)
            text = T("summary.signed", count=self._signed) + " " + text
            if self._backups:
                text += T("summary.backup", count=len(self._backups), folder=self._backup_root)
        if busy:
            total = self.progress.maximum()
            text = T("progress.sign" if self.signing else "progress.scan",
                     done=self.progress.value(), total=total)
        self.summary.setText(text)
        self.progress.setVisible(busy)

        locked = self.signing
        for widget in (self.key_box, self.key_create, self.key_add, self.key_remove,
                       self.preset_box, self.preset_new, self.preset_delete, self.preset_rename,
                       self.folder_add, self.folder_pick, self.rescan_btn, self.table):
            widget.setEnabled(not locked)
        named = self.store.active().name != SCRATCH
        self.preset_rename.setEnabled(not locked and named)
        self.preset_delete.setEnabled(not locked and named)
        self.key_remove.setEnabled(not locked and bool(self.store.key))
        self.folder_remove.setEnabled(not locked and bool(self.folder_list.selectedItems()))

    def _show_in_folder(self, row: int) -> None:
        item = self.table.item(row, COL_CHECK)
        path = item.data(PATH_ROLE) if item is not None else None
        if path:
            subprocess.Popen(["explorer", "/select,", os.path.normpath(path)])

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:                       # Esc — закрыть (п. 46)
            self.close()
            return
        super().keyPressEvent(event)

    def closeEvent(self, event):
        self._stop_job()
        self.store.window["size"] = [self.width(), self.height()]
        self.store.save()
        super().closeEvent(event)
