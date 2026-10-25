# -*- coding: utf-8 -*-
"""Содержимое вкладки: слева дерево спрайтов, свойства и текстуры, справа атлас.

Решения юзера 23.10.2026:
* иерархия: группы сворачиваются, в них спрайты; спрайты без группы — после групп;
* группы создаются и удаляются; спрайты переносятся между группами перетаскиванием;
  удаление группы со спрайтами спрашивает, куда их деть («—» — без группы);
* свойства спрайта — на одной стороне со списком;
* текстуры атласа заменяются и добавляются (вторая — обычно @2x);
* одиночный щелчок — выбор и правка числами, двойной — ручная правка рамки.
"""
from __future__ import annotations

import time
from pathlib import Path
from typing import Dict, List, Optional

from PySide6.QtCore import QItemSelectionModel, QRect, Qt, QThread, QTimer, Signal
from PySide6.QtGui import QKeySequence, QPixmap, QShortcut
from PySide6.QtWidgets import (QAbstractItemView, QApplication, QFileDialog, QHBoxLayout, QLabel,
                               QSizePolicy, QSplitter, QTreeWidgetItem, QVBoxLayout, QWidget)
from qfluentwidgets import (BodyLabel, CaptionLabel, ComboBox, FluentIcon, LineEdit,
                            MessageBox, MessageBoxBase, SearchLineEdit, SimpleCardWidget, StrongBodyLabel,
                            SubtitleLabel,
                            ToolButton, TransparentTogglePushButton, TransparentToolButton, TreeWidget)

import worker as ie
from canvas import AtlasCanvas
from document import DEFAULT_MPIX, Document, Sprite, Texture
from numeric import ExprSpinBox
from qts_ui import tokens
from qts_ui.rows import shrink
from texts import T

ROLE = Qt.UserRole + 1            # ("g", индекс группы) или ("s", id спрайта)
PREVIEW = 88
MAX_COORD = 16384
NO_GROUP = "—"
#: новый спрайт — квадрат этой стороны в (0, 0) (юзер 23.10.2026)
NEW_SIZE = 128
#: скопированный спрайт — общий на все вкладки: копировать из одного сета в другой
_CLIPBOARD = None
#: что берём на роль текстуры атласа; не-EDDS перегоняется в EDDS рядом с ним
TEXTURE_FILTER = "*.edds *.png *.tga *.dds *.bmp *.tif *.tiff"


# ====================================================================== диалоги
class NameDialog(MessageBoxBase):
    """Имя группы. Занятое — подсказка под полем, окно не закрывается."""

    def __init__(self, title: str, taken: List[str], text: str = "", parent=None):
        super().__init__(parent)
        self.taken = {t.lower() for t in taken} - {text.lower()}
        self.viewLayout.addWidget(SubtitleLabel(title, self))
        self.edit = LineEdit(self)
        self.edit.setPlaceholderText(T("group.prompt"))
        self.edit.setText(text)
        self.edit.setMinimumWidth(300)
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
        clash = name.lower() in self.taken
        self.hint.setText(T("group.taken", name=name) if clash else "")
        self.hint.setTextColor(tokens.color("error"), tokens.color("error"))
        self.yesButton.setEnabled(bool(name) and not clash)


class DeleteGroupDialog(MessageBoxBase):
    """Удаление группы со спрайтами: куда их деть. По умолчанию «—» — без группы."""

    def __init__(self, name: str, count: int, others: List[str], parent=None):
        super().__init__(parent)
        self.viewLayout.addWidget(SubtitleLabel(T("group.delete.title", name=name), self))
        self.viewLayout.addWidget(shrink(BodyLabel(T("group.delete.text", count=count), self)))
        self.target = ComboBox(self)
        self.target.addItem(NO_GROUP)
        for other in others:
            self.target.addItem(other)
        self.target.setCurrentIndex(0)
        self.viewLayout.addWidget(self.target)
        self.yesButton.setText(T("group.delete"))
        self.cancelButton.setText(T("dialog.cancel"))

    def choice(self) -> Optional[str]:
        """Имя группы назначения или None — оставить без группы."""
        return None if self.target.currentIndex() <= 0 else self.target.currentText()


class _Convert(QThread):
    """Картинка → EDDS рядом с ней. Атлас 1024 — секунды, окно на это время не стоит."""

    finished_ok = Signal(str)
    failed = Signal(str)

    def __init__(self, source: Path, parent=None):
        super().__init__(parent)
        self.source = source

    def run(self) -> None:
        try:
            self.finished_ok.emit(str(ie.to_edds(self.source)))
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(str(exc))


# ====================================================================== ссылки на спрайт
class RefScan(QThread):
    """Поиск ссылок — ImagesetEditor.exe refs, в фоне: обход проекта идёт секундами."""

    done = Signal(list)

    def __init__(self, root: Path, set_name: str, sprite: Optional[str], parent=None):
        super().__init__(parent)
        self.root, self.set_name, self.sprite = root, set_name, sprite

    def run(self) -> None:
        self.done.emit(ie.refs(self.root, self.set_name, self.sprite))


# ====================================================================== дерево
class SpriteTree(TreeWidget):
    """Дерево групп и спрайтов. Перетаскивание спрайтов между группами — не руками
    Qt, а сигналом: перенос делает документ (с отменой), дерево потом строится заново."""

    move_requested = Signal(list, object, object)     # [id], индекс группы | None, id «перед» | None

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setHeaderHidden(True)
        self.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.setDragDropMode(QAbstractItemView.InternalMove)
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDropIndicatorShown(True)

    def dragged(self) -> List[int]:
        return [it.data(0, ROLE)[1] for it in self.selectedItems() if it.data(0, ROLE)[0] == "s"]

    def dropEvent(self, event) -> None:
        sids = self.dragged()
        event.setDropAction(Qt.IgnoreAction)
        event.accept()
        if not sids:
            return
        target_item = self.itemAt(event.position().toPoint())
        if target_item is None:
            self.move_requested.emit(sids, None, None)            # в пустое место — без группы
            return
        kind, value = target_item.data(0, ROLE)
        if kind == "g":
            self.move_requested.emit(sids, value, None)           # на группу — в её конец
            return
        parent = target_item.parent()
        group = parent.data(0, ROLE)[1] if parent is not None else None
        if value in sids:
            return
        self.move_requested.emit(sids, group, value)              # на спрайт — перед ним, в его группу


# ====================================================================== вкладка
class DocumentView(QWidget):
    def __init__(self, doc: Document, parent=None):
        super().__init__(parent)
        self.doc = doc
        self.items: Dict[int, QTreeWidgetItem] = {}
        self.collapsed: set = set()
        self.current: Optional[int] = None
        self._filling = False
        self._convert: Optional[_Convert] = None
        self._renaming = None                 # строка дерева, имя которой сейчас правят
        self._square_off = set()              # спрайты, у которых «=» выключили руками
        self._refs = None

        root = QHBoxLayout(self)
        root.setContentsMargins(0, tokens.SPACE_XS, 0, 0)
        split = QSplitter(Qt.Horizontal, self)
        root.addWidget(split)

        # --- левая колонка, от общего к частному (юзер 23.10.2026): сам имиджсет, его
        # группы и спрайты, выбранный спрайт. Карточками: без рамки не было видно, где
        # кончается один блок и начинается другой
        left = QWidget(split)
        column = QVBoxLayout(left)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(tokens.SPACE_S)

        # 1. имиджсет: имя сета (им ссылаются set:ИМЯ), система координат, текстуры
        setc = self._card(left)
        sl = setc.layout()
        sl.addWidget(StrongBodyLabel(T("set.title"), setc))
        nrow = QHBoxLayout()
        nrow.addWidget(CaptionLabel(T("set.name"), setc))
        self.set_name = LineEdit(setc)
        self.set_name.setToolTip(T("set.name.tip"))
        self.set_name.editingFinished.connect(self._on_set_name)
        nrow.addWidget(self.set_name, 1)
        sl.addLayout(nrow)
        self.ref_size = CaptionLabel("", setc)
        self.ref_size.setToolTip(T("set.refsize.tip"))
        sl.addWidget(self.ref_size)
        head = QHBoxLayout()
        head.addWidget(CaptionLabel(T("tex.title"), setc), 1)
        self.tex_add = TransparentToolButton(FluentIcon.ADD, setc)
        self.tex_add.setToolTip(T("tex.add"))
        self.tex_add.clicked.connect(lambda: self._pick_texture(None))
        head.addWidget(self.tex_add)
        sl.addLayout(head)
        self.tex_box = QVBoxLayout()
        self.tex_box.setSpacing(tokens.SPACE_XXS)
        sl.addLayout(self.tex_box)
        column.addWidget(setc)

        # 2. группы и спрайты
        top = self._card(left)
        tl = top.layout()
        tl.addWidget(StrongBodyLabel(T("sprites.title"), top))
        self.search = SearchLineEdit(top)
        self.search.setPlaceholderText(T("sprites.search"))
        self.search.textChanged.connect(lambda _t: self._fill())
        tl.addWidget(self.search)
        self.tree = SpriteTree(top)
        self.tree.currentItemChanged.connect(self._on_tree)
        self.tree.itemSelectionChanged.connect(self._on_tree_selection)
        self.tree.itemCollapsed.connect(lambda it: self._remember_fold(it, True))
        self.tree.itemExpanded.connect(lambda it: self._remember_fold(it, False))
        self.tree.move_requested.connect(self._on_move)
        # двойной щелчок по группе или спрайту — правка имени прямо в строке
        self.tree.setExpandsOnDoubleClick(False)
        self.tree.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tree.itemDoubleClicked.connect(self._start_rename)
        self.tree.itemChanged.connect(self._on_renamed)
        self.tree.itemDelegate().closeEditor.connect(lambda *_: QTimer.singleShot(0, self._end_rename))
        tl.addWidget(self.tree, 1)
        gbar = QHBoxLayout()
        gbar.setSpacing(tokens.SPACE_XXS)
        self.sprite_add = TransparentToolButton(FluentIcon.ADD, top)
        self.sprite_add.setToolTip(T("sprite.add"))
        self.sprite_add.clicked.connect(self._add_sprite)
        self.group_add = TransparentToolButton(FluentIcon.FOLDER_ADD, top)
        self.group_add.setToolTip(T("group.add"))
        self.group_add.clicked.connect(self._add_group)
        self.group_rename = TransparentToolButton(FluentIcon.EDIT, top)
        self.group_rename.setToolTip(T("group.rename"))
        self.group_rename.clicked.connect(self._rename_group)
        self.group_delete = TransparentToolButton(FluentIcon.DELETE, top)
        self.group_delete.setToolTip(T("group.delete"))
        self.group_delete.clicked.connect(self._delete_group)
        for b in (self.sprite_add, self.group_add, self.group_rename, self.group_delete):
            gbar.addWidget(b)
        gbar.addStretch(1)
        tl.addLayout(gbar)
        column.addWidget(top, 1)                 # всё лишнее место колонки — дереву

        # 3. выбранный спрайт
        props = self._card(left)
        pl = props.layout()
        # без заголовка и имени: имя видно в дереве; превью — наверх (юзер 23.10.2026)
        prow = QHBoxLayout()
        self.preview = QLabel(props)
        self.preview.setFixedSize(PREVIEW, PREVIEW)
        self.preview.setAlignment(Qt.AlignCenter)
        prow.addWidget(self.preview)
        self.flags = shrink(CaptionLabel("", props))
        prow.addWidget(self.flags, 1, Qt.AlignTop)
        pl.addLayout(prow)
        self.spins = {}
        # позиция и размер — каждая своей строкой: в одну строку поля в колонке
        # обрезались до одной цифры
        grid = QVBoxLayout()
        grid.setSpacing(tokens.SPACE_S)
        for label_key, fields in (("props.pos", ("x", "y")), ("props.size", ("width", "height"))):
            col = QHBoxLayout()
            label = CaptionLabel(T(label_key), props)
            label.setFixedWidth(64)
            col.addWidget(label)
            line = QHBoxLayout()
            for field in fields:
                if field == "y":
                    line.addSpacing(40)                     # поля y и высоты — одна колонка
                if field == "height":
                    # «=» между шириной и высотой: высота недоступна и равна ширине
                    # (юзер 23.10.2026, как замок пропорций в редакторах)
                    self.square = TransparentTogglePushButton("=", props)
                    # 40 px: уже — библиотечные отступы сплющивают знак в «:»; свой
                    # стиль не ставим — он перебивает акцент включённого состояния
                    self.square.setFixedWidth(40)
                    self.square.setToolTip(T("props.square"))
                    self.square.toggled.connect(self._on_square)
                    line.addWidget(self.square)
                # без стрелок, с выражениями как в Blender: «2048+256» (numeric.py)
                spin = ExprSpinBox(props)
                spin.setRange(0 if field in ("x", "y") else 1, MAX_COORD)
                spin.valueChanged.connect(lambda v, f=field: self._on_spin(f, v))
                self.spins[field] = spin
                line.addWidget(spin)
            col.addLayout(line, 1)
            grid.addLayout(col)
        pl.addLayout(grid)
        grow = QHBoxLayout()
        glabel = CaptionLabel(T("props.group"), props)
        glabel.setFixedWidth(64)
        grow.addWidget(glabel)
        self.group_box = ComboBox(props)
        self.group_box.currentIndexChanged.connect(self._on_group_box)
        grow.addWidget(self.group_box, 1)
        pl.addLayout(grow)
        column.addWidget(props)
        left.setMinimumWidth(320)
        split.addWidget(left)

        # --- атлас
        center = QWidget(split)
        cl = QVBoxLayout(center)
        cl.setContentsMargins(0, 0, 0, 0)
        cl.setSpacing(tokens.SPACE_XXS)
        bar = QHBoxLayout()
        # подсказка про ручную правку — здесь, над атласом: в левой колонке её обрезало
        self.mode_label = shrink(CaptionLabel("", center))
        bar.addWidget(self.mode_label, 1)
        self.fit_btn = TransparentToolButton(FluentIcon.FIT_PAGE, center)
        self.fit_btn.setToolTip(T("zoom.fit"))
        bar.addWidget(self.fit_btn)
        cl.addLayout(bar)
        self.canvas = AtlasCanvas(center)
        self.canvas.sprite_clicked.connect(lambda sid, add: self.select(sid, add=add))
        self.canvas.edit_changed.connect(self._on_edit_mode)
        self.canvas.rect_live.connect(self._on_rect_live)
        self.canvas.rect_committed.connect(self._on_rect_commit)
        self.canvas.band_selected.connect(self._on_band)
        self.canvas.rects_committed.connect(
            lambda rects: self.doc.set_rects(rects, T("undo.group_move", count=len(rects))))
        self.fit_btn.clicked.connect(self.canvas.fit)
        cl.addWidget(self.canvas, 1)
        split.addWidget(center)
        split.setStretchFactor(1, 1)
        split.setSizes([340, 800])

        self.info = shrink(CaptionLabel("", self))
        cl.addWidget(self.info)

        doc.changed.connect(self._on_changed)
        doc.textures_changed.connect(self._on_textures)
        doc.saved.connect(self._on_saved)
        self.canvas.show_doc(doc)
        self._fill()
        self._fill_textures()
        self._show_props()
        # что стало с историей прошлых сессий — тулза говорит, что решила сама (принцип 13)
        if doc.history_dropped:
            self._show_info(T("history.dropped"), error=True)
        elif doc.history_restored:
            self._show_info(T("history.restored", count=doc.history_restored))
        else:
            self._show_info()
        self._sync_buttons()
        self._on_edit_mode(None)
        self._show_set()
        for widget in (self.canvas, self.tree):
            QShortcut(QKeySequence.Copy, widget, activated=self.copy_sprite, context=Qt.WidgetWithChildrenShortcut)
            QShortcut(QKeySequence.Paste, widget, activated=self.paste_sprite,
                      context=Qt.WidgetWithChildrenShortcut)
            QShortcut(QKeySequence.Delete, widget, activated=self.delete_sprite,
                      context=Qt.WidgetWithChildrenShortcut)

    def _card(self, parent) -> SimpleCardWidget:
        card = SimpleCardWidget(parent)
        lay = QVBoxLayout(card)
        lay.setContentsMargins(tokens.SPACE_S, tokens.SPACE_S, tokens.SPACE_S, tokens.SPACE_S)
        lay.setSpacing(tokens.SPACE_XS)
        return card

    # ================================================================== дерево
    def _fill(self) -> None:
        """Дерево из документа: группы (свёрнутые — как были), потом спрайты без группы."""
        needle = self.search.text().strip().lower()
        keep = set(self.selected_sids()) if self.tree.topLevelItemCount() else set()
        self._filling = True
        self.tree.clear()
        self.items = {}

        def sprite_item(sid):
            item = QTreeWidgetItem([self.doc.sprite(sid).name])
            item.setData(0, ROLE, ("s", sid))
            item.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled
                          | (Qt.ItemIsDragEnabled | Qt.ItemIsEditable if not self.doc.readonly
                             else Qt.NoItemFlags))
            self.items[sid] = item
            return item

        for gi, (name, ids) in enumerate(self.doc.groups):
            shown = [sid for sid in ids if not needle or needle in self.doc.sprite(sid).name.lower()]
            if needle and not shown:
                continue
            group = QTreeWidgetItem(["%s  (%d)" % (name, len(ids))])
            group.setData(0, ROLE, ("g", gi))
            group.setIcon(0, FluentIcon.FOLDER.icon())
            group.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled | Qt.ItemIsDropEnabled
                           | (Qt.ItemIsEditable if not self.doc.readonly else Qt.NoItemFlags))
            self.tree.addTopLevelItem(group)
            for sid in shown:
                group.addChild(sprite_item(sid))
            group.setExpanded(bool(needle) or name not in self.collapsed)
        for sid in self.doc.top:
            if not needle or needle in self.doc.sprite(sid).name.lower():
                self.tree.addTopLevelItem(sprite_item(sid))
        # выделение переживает перестройку дерева — всё, а не только главный
        for sid in keep | ({self.current} if self.current is not None else set()):
            if sid in self.items:
                self.items[sid].setSelected(True)
        if self.current in self.items:
            self.tree.setCurrentItem(self.items[self.current], 0, QItemSelectionModel.NoUpdate)
        self._filling = False
        self.canvas.select(self.current, [k for k in keep if k in self.doc.items])

    # ------------------------------------------------------------------ имена
    def _start_rename(self, item, _column) -> None:
        """Двойной щелчок по группе или спрайту — правка имени в строке. У группы в
        строке ещё и число спрайтов — на время правки показываем голое имя."""
        if self.doc.readonly or item is None:
            return
        kind, value = item.data(0, ROLE)
        self._renaming = item
        self._filling = True
        item.setText(0, self.doc.groups[value][0] if kind == "g" else self.doc.sprite(value).name)
        self._filling = False
        self.tree.editItem(item, 0)

    def _on_renamed(self, item, _column) -> None:
        if self._filling or item is not self._renaming:
            return
        kind, value = item.data(0, ROLE)
        name = item.text(0).strip()
        self._renaming = None
        # перестройка дерева — не изнутри его собственного сигнала (свод, п. 70)
        QTimer.singleShot(0, lambda: self._apply_rename(kind, value, name))

    def _end_rename(self) -> None:
        if self._renaming is not None:
            self._renaming = None
            self._fill()                       # отменили правку — вернуть счётчик группы

    def _apply_rename(self, kind: str, value: int, name: str) -> None:
        if kind == "g":
            old = self.doc.groups[value][0]
            problem = self.doc.name_problem(name, group=value) if name != old else ""
        else:
            old = self.doc.sprite(value).name
            problem = self.doc.name_problem(name, sid=value) if name != old else ""
        if problem:
            key = {"empty": "rename.empty", "chars": "rename.chars", "taken": "rename.taken"}[problem]
            self._show_info(T(key, name=name), error=True)
        elif name != old:
            if kind == "g":
                if old in self.collapsed:
                    self.collapsed.discard(old)
                    self.collapsed.add(name)
                self.doc.rename_group(value, name, T("undo.group.rename", name=name))
            else:
                self.doc.rename_sprite(value, name, T("undo.sprite.rename", name=name))
                self._scan_refs(old)
        self._fill()

    def _scan_refs(self, old: str, whole_set: bool = False) -> None:
        """Ссылки на старое имя спрайта в проекте (P:\\<верхняя папка>) — в фоне. Не правим,
        но говорим, что сломалось бы: молча ломать ссылки нельзя (принцип 13)."""
        root = self.doc.refs_root
        if root is None:
            return
        set_name, sprite = (old, None) if whole_set else (self.doc.name, old)
        self._refs = RefScan(root, set_name, sprite, self)
        self._refs.done.connect(lambda found, o=old, r=root: self._refs_found(o, r, found))
        self._refs.start()

    def _refs_found(self, old: str, root: Path, found: list) -> None:
        if not found:
            self._show_info(T("rename.refs.none", old=old, root=root))
            return
        total = sum(n for _f, n in found)
        self._show_info(T("rename.refs", old=old, count=total, files=len(found), root=root), error=True)
        self.info.setToolTip("\n".join("%s — %d" % (f, n) for f, n in found[:40]))

    def _remember_fold(self, item, collapsed: bool) -> None:
        if self._filling:
            return
        kind, gi = item.data(0, ROLE)
        if kind == "g" and gi < len(self.doc.groups):
            name = self.doc.groups[gi][0]
            (self.collapsed.add if collapsed else self.collapsed.discard)(name)

    def _on_tree(self, item, _prev) -> None:
        """Текущая строка сменилась щелчком в дереве. Выделение здесь не трогаем: его
        решает само дерево (Ctrl, Shift) уже после этого сигнала — назначенное здесь
        оно тут же перекрывало, и Ctrl+щелчок снимал всё. Холст — в _on_tree_selection."""
        if self._filling or item is None:
            return
        kind, value = item.data(0, ROLE)
        if kind == "s":
            self.current = value
            self._show_props()
        self._sync_buttons()

    def selected_sids(self) -> List[int]:
        return [it.data(0, ROLE)[1] for it in self.tree.selectedItems() if it.data(0, ROLE)[0] == "s"]

    def select(self, sid, add: bool = False, only=None) -> None:
        """Выбрать спрайт. `add` (Ctrl+щелчок на холсте) — добавить к выделенным или
        снять; иначе выделен только он. `only` — выделить ровно эти (после вставки).
        Выделение одно на дерево и холст — подсвечено одинаково (юзер 23.10.2026)."""
        if sid not in self.doc.items:
            return
        self._filling = True
        if only is not None:
            self.tree.clearSelection()
            for k in only:
                if k in self.items:
                    self.items[k].setSelected(True)
            if sid in self.items:
                self.tree.setCurrentItem(self.items[sid], 0, QItemSelectionModel.NoUpdate)
        elif sid in self.items:
            # явная команда выделения: по умолчанию дерево в режиме «много» ДОБАВЛЯЛО
            # строку к выделенным, и после вставки выделены были старый и новый
            mode = QItemSelectionModel.Toggle if add else QItemSelectionModel.ClearAndSelect
            self.tree.setCurrentItem(self.items[sid], 0, mode | QItemSelectionModel.Rows)
        self._filling = False
        marked = self.selected_sids()
        if add and sid not in marked:              # Ctrl+щелчок снял выделение с главного
            sid = marked[-1] if marked else None
        self.current = sid
        self.canvas.select(sid, marked)
        self._show_props()
        self._sync_buttons()

    def _on_band(self, sids: List[int], add: bool) -> None:
        """Обвели мышью: выделить всех под рамкой (с Ctrl — добавить к выделенным)."""
        if add:
            sids = list(dict.fromkeys(self.selected_sids() + sids))
        if sids:
            self.select(sids[-1], only=sids)
        elif not add:
            self.tree.clearSelection()

    def _on_tree_selection(self) -> None:
        """Выделение в дереве устоялось — то же на холсте. Сняли главный (Ctrl+щелчок) —
        главным становится последний из оставшихся."""
        if self._filling:
            return
        marked = self.selected_sids()
        if self.current not in marked:
            self.current = marked[-1] if marked else None
            self._show_props()
        self.canvas.select(self.current, marked)
        self._sync_buttons()

    def _selected_group(self) -> Optional[int]:
        item = self.tree.currentItem()
        if item is None:
            return None
        kind, value = item.data(0, ROLE)
        return value if kind == "g" else None

    def _sync_buttons(self) -> None:
        editable = not self.doc.readonly
        group = self._selected_group()
        self.sprite_add.setEnabled(editable)
        self.set_name.setReadOnly(not editable)
        self.group_add.setEnabled(editable)
        self.group_rename.setEnabled(editable and group is not None)
        self.group_delete.setEnabled(editable and group is not None)
        self.tex_add.setEnabled(editable)

    # ================================================================== сет
    def _show_set(self) -> None:
        if not self.set_name.hasFocus():
            self.set_name.setText(self.doc.name)
        self.ref_size.setText(T("set.refsize", w=self.doc.data.width, h=self.doc.data.height))

    def _on_set_name(self) -> None:
        name = self.set_name.text().strip()
        old = self.doc.name
        if name == old:
            return
        problem = self.doc.set_problem(name)
        if problem:
            self.set_name.setText(old)
            self._show_info(T("rename.empty" if problem == "empty" else "rename.set_chars", name=name),
                            error=True)
            return
        self.doc.set_name(name, T("undo.set.rename", name=name))
        self._scan_refs(old, whole_set=True)

    # ================================================================== спрайты: создать, копировать, удалить
    def _target_group(self) -> Optional[int]:
        """Куда класть новый спрайт: выбранная группа или группа выбранного спрайта."""
        group = self._selected_group()
        if group is None and self.current is not None:
            group = self.doc.group_of(self.current)
        return group

    def _add_sprite(self) -> None:
        """Новый спрайт: квадрат 128x128 в (0, 0), имя пустое — сразу правится в дереве."""
        sid = self.doc.add_sprite(Sprite("", 0, 0, NEW_SIZE, NEW_SIZE), self._target_group(),
                                  T("undo.sprite.add"))
        if sid is not None:
            self.select(sid)
            QTimer.singleShot(0, lambda: self._start_rename(self.items.get(sid), 0))

    def copy_sprite(self) -> None:
        global _CLIPBOARD
        sids = self.selected_sids() or ([self.current] if self.current is not None else [])
        if sids:
            _CLIPBOARD = [self.doc.sprite(sid) for sid in sids]

    def paste_sprite(self) -> None:
        """Вставка под указателем мыши: середина копии (или общей рамки нескольких) — у
        курсора, взаимное расположение сохраняется. Имя — копируемое с припиской 1
        (занято — 2, 3…), группа — та же, что у выбранного. Выделены после — только новые."""
        if not _CLIPBOARD or self.doc.readonly:
            return
        left = min(s.x for s in _CLIPBOARD)
        top = min(s.y for s in _CLIPBOARD)
        right = max(s.x + s.width for s in _CLIPBOARD)
        bottom = max(s.y + s.height for s in _CLIPBOARD)
        at = self.canvas.cursor_scene_pos()
        dx = int(round(at.x() - (left + right) / 2))
        dy = int(round(at.y() - (top + bottom) / 2))
        dx, dy = max(dx, -left), max(dy, -top)         # левее и выше атласа не выносим
        group, after, made = self._target_group(), self.current, []
        for src in _CLIPBOARD:
            sprite = src._replace(name=self.doc.unique_name(src.name), x=src.x + dx, y=src.y + dy)
            sid = self.doc.add_sprite(sprite, group, T("undo.sprite.paste", name=sprite.name), after=after)
            if sid is not None:
                made.append(sid)
                after = sid
        if made:
            self.select(made[-1], only=made)

    def delete_sprite(self) -> None:
        sids = self.selected_sids()
        if not sids and self.current is not None:
            sids = [self.current]
        if sids and not self.doc.readonly:
            self.doc.delete_sprites(sids, T("undo.sprite.delete", count=len(sids)))

    # ================================================================== группы
    def _add_group(self) -> None:
        dlg = NameDialog(T("group.add"), self.doc.group_names(), parent=self.window())
        if dlg.exec():
            self.doc.add_group(dlg.name(), T("undo.group.add", name=dlg.name()))

    def _rename_group(self) -> None:
        gi = self._selected_group()
        if gi is None:
            return
        old = self.doc.groups[gi][0]
        dlg = NameDialog(T("group.rename"), self.doc.group_names(), old, parent=self.window())
        if dlg.exec() and dlg.name() != old:
            if old in self.collapsed:
                self.collapsed.discard(old)
                self.collapsed.add(dlg.name())
            self.doc.rename_group(gi, dlg.name(), T("undo.group.rename", name=dlg.name()))

    def _delete_group(self) -> None:
        gi = self._selected_group()
        if gi is None:
            return
        name, ids = self.doc.groups[gi]
        target = None
        if ids:
            others = [n for i, n in enumerate(self.doc.group_names()) if i != gi]
            dlg = DeleteGroupDialog(name, len(ids), others, parent=self.window())
            if not dlg.exec():
                return
            chosen = dlg.choice()
            # индекс — до удаления группы: документ переносит, а потом удаляет
            target = None if chosen is None else self.doc.group_names().index(chosen)
        self.doc.delete_group(gi, target, T("undo.group.delete", name=name))

    def _on_move(self, sids: List[int], group, before) -> None:
        self.doc.move(sids, group, before, T("undo.move_group"))

    def _on_group_box(self, index: int) -> None:
        if self._filling or self.current is None:
            return
        target = None if index <= 0 else index - 1
        if target != self.doc.group_of(self.current):
            self.doc.move([self.current], target, None, T("undo.move_group"))

    # ================================================================== свойства
    def _show_props(self) -> None:
        sid = self.current
        has = sid is not None and sid in self.doc.items
        editable = has and not self.doc.readonly
        if has:
            sprite = self.doc.sprite(sid)
            self.square.blockSignals(True)
            self.square.setChecked(sprite.width == sprite.height and sid not in self._square_off)
            self.square.blockSignals(False)
        for field, spin in self.spins.items():
            spin.setEnabled(editable and not (field == "height" and self.square.isChecked()))
        self.square.setEnabled(editable)
        self.group_box.setEnabled(editable)
        self._filling = True
        self.group_box.clear()
        self.group_box.addItem(NO_GROUP)
        for name in self.doc.group_names():
            self.group_box.addItem(name)
        if not has:
            self.flags.setText(T("props.none"))
            self.preview.clear()
            self._filling = False
            return
        sprite = self.doc.sprite(sid)
        for field, spin in self.spins.items():
            spin.blockSignals(True)
            spin.setValue(int(getattr(sprite, field)))
            spin.blockSignals(False)
        group = self.doc.group_of(sid)
        self.group_box.setCurrentIndex(0 if group is None else group + 1)
        self._filling = False
        self.flags.setText("%s: %s" % (T("props.flags"), sprite.flags))
        self._show_preview(sprite)

    def _show_preview(self, sprite) -> None:
        image = self.doc.image()
        if image is None:
            self.preview.clear()
            return
        sx, sy = image.width() / self.doc.data.width, image.height() / self.doc.data.height
        rect = QRect(int(round(sprite.x * sx)), int(round(sprite.y * sy)),
                     max(1, int(round(sprite.width * sx))), max(1, int(round(sprite.height * sy))))
        pix = QPixmap.fromImage(image.copy(rect))
        if pix.width() > PREVIEW or pix.height() > PREVIEW:
            pix = pix.scaled(PREVIEW, PREVIEW, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        else:
            # мелкий спрайт (угол рамки 10x10) — крупнее целым шагом, без размытия
            step = max(1, min(PREVIEW // pix.width(), PREVIEW // pix.height()))
            pix = pix.scaled(pix.width() * step, pix.height() * step, Qt.KeepAspectRatio,
                             Qt.FastTransformation)
        self.preview.setPixmap(pix)

    def _on_spin(self, field: str, value: int) -> None:
        if self.current is None:
            return
        sprite = self.doc.sprite(self.current)
        text = T("undo.move" if field in ("x", "y") else "undo.size", name=sprite.name)
        fields = {field: value}
        if field == "width" and self.square.isChecked():
            fields["height"] = value                   # w = h: одна правка на обе стороны
        self.doc.edit(self.current, text, **fields)

    def _on_square(self, on: bool) -> None:
        """Включили «=»: высота выключается и сразу становится равной ширине у
        выбранного спрайта. Других спрайтов это не касается, пока их не правят."""
        self.spins["height"].setEnabled(not on and self.current is not None and not self.doc.readonly)
        if self.current is not None:
            (self._square_off.discard if on else self._square_off.add)(self.current)
        if on and self.current is not None:
            sprite = self.doc.sprite(self.current)
            if sprite.height != sprite.width:
                self.doc.edit(self.current, T("undo.size", name=sprite.name), height=sprite.width)

    # ================================================================== ручная правка
    def _on_edit_mode(self, sid) -> None:
        if sid is not None:
            self.mode_label.setText(T("edit.mode", name=self.doc.sprite(sid).name))
            self.mode_label.setTextColor(tokens.ACCENT, tokens.ACCENT)
        else:
            self.mode_label.setText("" if self.doc.readonly else T("edit.hint"))
            self.mode_label.setTextColor(tokens.color("text_dim"), tokens.color("text_dim"))

    def _on_rect_live(self, sid, rect) -> None:
        if sid != self.current:
            return
        for field, value in zip(("x", "y", "width", "height"), rect):
            spin = self.spins[field]
            spin.blockSignals(True)
            spin.setValue(int(value))
            spin.blockSignals(False)

    def _on_rect_commit(self, sid, rect) -> None:
        self.doc.set_rect(sid, rect, T("undo.rect", name=self.doc.sprite(sid).name))

    # ================================================================== документ
    def _on_changed(self, sid) -> None:
        if sid is None:                       # поменялась раскладка: группы, перенос, вставка, отмена
            self.canvas.sync(self.doc)
            if self.current not in self.doc.items:
                self.current = None
            self._show_set()
            self._fill()
            self._show_props()
            self._sync_buttons()
            return
        self.canvas.update_sprite(sid, self.doc.sprite(sid))
        if sid == self.current:
            self._show_props()

    # ================================================================== текстуры
    def _fill_textures(self) -> None:
        while self.tex_box.count():
            row = self.tex_box.takeAt(0)
            if row.layout():
                while row.layout().count():
                    w = row.layout().takeAt(0).widget()
                    if w:
                        w.deleteLater()
            elif row.widget():
                row.widget().deleteLater()
        for index, texture in enumerate(self.doc.textures):
            line = QHBoxLayout()
            found = self.doc.texture_path(index)
            label = CaptionLabel("%d. %s" % (index + 1, Path(texture.path).name), self)
            label.setToolTip("%s\n%s" % (texture.path, found or T("tex.missing")))
            if found is None:
                label.setTextColor(tokens.color("error"), tokens.color("error"))
            line.addWidget(label, 1)
            replace = ToolButton(FluentIcon.SYNC, self)
            replace.setToolTip(T("tex.replace"))
            replace.clicked.connect(lambda _=False, i=index: self._pick_texture(i))
            replace.setEnabled(not self.doc.readonly)
            line.addWidget(replace)
            remove = ToolButton(FluentIcon.REMOVE, self)
            remove.setToolTip(T("tex.remove"))
            remove.clicked.connect(lambda _=False, i=index: self._remove_texture(i))
            remove.setEnabled(not self.doc.readonly and len(self.doc.textures) > 1)
            line.addWidget(remove)
            self.tex_box.addLayout(line)

    def _pick_texture(self, index: Optional[int]) -> None:
        """Заменить текстуру `index` или добавить новую. Не-EDDS — перегоняем в EDDS рядом."""
        start = str(self.doc.texture_path(index or 0).parent) if self.doc.texture_path(index or 0) \
            else str(self.doc.path.parent)
        path, _ = QFileDialog.getOpenFileName(self, T("tex.pick"), start, TEXTURE_FILTER)
        if not path:
            return
        source = Path(path)
        if source.suffix.lower() == ".edds":
            self._use_texture(index, source)
            return
        QApplication.setOverrideCursor(Qt.WaitCursor)
        self.info.setText(T("tex.converting", name=source.name))
        self._convert = _Convert(source, self)
        self._convert.finished_ok.connect(lambda out, i=index: self._converted(i, Path(out)))
        self._convert.failed.connect(self._convert_failed)
        self._convert.start()

    def _converted(self, index: Optional[int], out: Path) -> None:
        QApplication.restoreOverrideCursor()
        self._use_texture(index, out)

    def _convert_failed(self, text: str) -> None:
        QApplication.restoreOverrideCursor()
        box = MessageBox(T("tex.pick"), T("tex.convert_failed", text=text), self.window())
        box.yesButton.setText(T("dialog.ok"))
        box.cancelButton.hide()
        box.exec()
        self._show_info()

    def _use_texture(self, index: Optional[int], file: Path) -> None:
        path = ie.game_path(file)
        note = ""
        if path is None:
            path = file.name               # вне P: — движок найдёт только по имени рядом
            note = T("tex.outside_p")
        if index is None:
            mpix = (self.doc.textures[-1].mpix + 1) if self.doc.textures else DEFAULT_MPIX
            self.doc.set_texture(None, Texture(path, mpix, str(file)), T("undo.tex.add"))
        else:
            self.doc.set_texture(index, Texture(path, self.doc.textures[index].mpix, str(file)),
                                 T("undo.tex.replace"))
        self._show_info(note)

    def _remove_texture(self, index: int) -> None:
        self.doc.set_texture(index, None, T("undo.tex.remove"))

    def _on_textures(self) -> None:
        self._fill_textures()
        self.canvas.show_doc(self.doc)
        if self.current is not None:
            self.canvas.select(self.current)
        self._show_props()
        self._show_info()

    # ================================================================== строка внизу
    def _show_info(self, extra: str = "", error: bool = False) -> None:
        d = self.doc.data
        text = T("info.set", name=self.doc.name, w=d.width, h=d.height, count=len(self.doc.items))
        if extra:
            text += " · " + extra
        self.info.setText(text)
        self.info.setToolTip("")
        role = "warning" if error else "text_dim"
        self.info.setTextColor(tokens.color(role), tokens.color(role))

    def _on_saved(self, backup: str) -> None:
        text = T("info.saved", time=time.strftime("%H:%M:%S"))
        if backup:
            text += T("info.backup", folder=backup)
        self._show_info(text)

    def repaint_theme(self) -> None:
        self.canvas.repaint_theme()
