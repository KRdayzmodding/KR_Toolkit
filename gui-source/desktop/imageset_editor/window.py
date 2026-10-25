# -*- coding: utf-8 -*-
"""Главное окно [KR] Imageset Editor — вкладки, как в VSCode.

Заказ юзера 23.10.2026:

* каждый .imageset — своя вкладка; уже открытый файл не открывается второй раз,
  а показывается его вкладка;
* открыть — кнопкой, Ctrl+O или перетаскиванием в любую часть окна;
* окно помнит открытые вкладки и активную;
* автосохранение — при переключении вкладки и при потере фокуса окном (и при
  закрытии вкладки или окна).

Оформление — как у остальных тулз: своя шапка (qts_ui.frame), токены QTS.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from PySide6.QtCore import QEvent, QObject, Qt
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import QApplication, QFileDialog, QHBoxLayout, QStackedWidget, QVBoxLayout, QWidget
from qfluentwidgets import BodyLabel, FluentIcon, MessageBox, PushButton, TabBar, TransparentToolButton, qconfig

from document import Document
from editor import DocumentView
from texts import T
from qts_ui import tokens
from qts_ui.frame import ToolWindow
from qts_ui.rows import shrink
from store import Store

MIN = (900, 600)
SUFFIX = ".imageset"


def _key(path) -> str:
    return os.path.normcase(os.path.abspath(path))


class _DropAnywhere(QObject):
    """Перетаскивание .imageset на любой виджет окна (юзер: «в любую часть окна»).

    Дочерние виджеты (холст, список) перехватывают события перетаскивания раньше
    окна, поэтому ловим их на уровне приложения и смотрим, в каком окне цель.
    """

    def __init__(self, window):
        super().__init__(window)
        self.window = window

    def eventFilter(self, obj, event) -> bool:
        kind = event.type()
        if kind not in (QEvent.DragEnter, QEvent.DragMove, QEvent.Drop):
            return False
        if not isinstance(obj, QWidget) or obj.window() is not self.window:
            return False
        paths = self.window.dropped(event)
        if not paths:
            return False
        event.acceptProposedAction()
        if kind == QEvent.Drop:
            self.window.open_paths(paths)
        return True


class ImagesetWindow(ToolWindow):
    def __init__(self, store: Store):
        super().__init__(FluentIcon.TILES, image="ImagesetEditor")
        self.store = store
        self.docs: Dict[str, Tuple[Document, DocumentView]] = {}
        self.order: List[str] = []                      # ключи вкладок по порядку
        self.setWindowTitle(T("app.title"))
        self.setMinimumSize(*MIN)
        w, h = self.store.window.get("size", MIN)
        self.resize(max(w, MIN[0]), max(h, MIN[1]))
        self._build()
        # Qt отдаёт перетаскивание только виджетам с acceptDrops, поднимаясь от цели к
        # родителям; окно с ним — конец цепочки, и фильтр видит событие откуда угодно
        self.setAcceptDrops(True)
        self._drop = _DropAnywhere(self)
        QApplication.instance().installEventFilter(self._drop)
        qconfig.themeChanged.connect(self._repaint_theme)
        self._restore()

    # ================================================================== сборка окна
    def _build(self) -> None:
        root = QVBoxLayout(self.body)
        root.setContentsMargins(tokens.SPACE_M, tokens.SPACE_XS, tokens.SPACE_M, tokens.SPACE_M)
        root.setSpacing(0)
        top = QHBoxLayout()
        top.setSpacing(tokens.SPACE_XS)
        self.open_btn = TransparentToolButton(FluentIcon.FOLDER, self)
        self.open_btn.setToolTip(T("open") + " (Ctrl+O)")
        self.open_btn.clicked.connect(self.pick)
        top.addWidget(self.open_btn)
        self.tabs = TabBar(self)
        self.tabs.setAddButtonVisible(False)
        self.tabs.setTabsClosable(True)
        self.tabs.setTabMaximumWidth(260)
        self.tabs.currentChanged.connect(self._on_tab)
        self.tabs.tabCloseRequested.connect(self.close_tab)
        top.addWidget(self.tabs, 1)
        root.addLayout(top)

        self.stack = QStackedWidget(self)
        empty = QWidget(self.stack)
        el = QVBoxLayout(empty)
        el.addStretch(1)
        label = shrink(BodyLabel(T("empty"), empty))
        label.setAlignment(Qt.AlignCenter)
        el.addWidget(label)
        row = QHBoxLayout()
        row.addStretch(1)
        self.empty_open = PushButton(FluentIcon.FOLDER, T("open"), empty)
        self.empty_open.clicked.connect(self.pick)
        row.addWidget(self.empty_open)
        row.addStretch(1)
        el.addLayout(row)
        el.addStretch(1)
        self.stack.addWidget(empty)
        self.empty = empty
        root.addWidget(self.stack, 1)

        QShortcut(QKeySequence.Open, self, activated=self.pick)
        QShortcut(QKeySequence("Ctrl+W"), self, activated=lambda: self.close_tab(self.tabs.currentIndex()))
        QShortcut(QKeySequence.Save, self, activated=self.save_all)
        QShortcut(QKeySequence.Undo, self, activated=lambda: self._stack_do("undo"))
        QShortcut(QKeySequence.Redo, self, activated=lambda: self._stack_do("redo"))
        QShortcut(QKeySequence("Ctrl+Tab"), self, activated=lambda: self._step(1))
        QShortcut(QKeySequence("Ctrl+Shift+Tab"), self, activated=lambda: self._step(-1))

    # ================================================================== открытие
    @staticmethod
    def dropped(event) -> List[str]:
        data = event.mimeData()
        if not data.hasUrls():
            return []
        return [u.toLocalFile() for u in data.urls()
                if u.isLocalFile() and u.toLocalFile().lower().endswith(SUFFIX)]

    def pick(self) -> None:
        files, _ = QFileDialog.getOpenFileNames(self, T("open.title"), self.store.last_dir,
                                                "*" + SUFFIX)
        if files:
            self.store.last_dir = str(Path(files[0]).parent)
            self.open_paths(files)

    def open_paths(self, paths: List[str], quiet: bool = False) -> None:
        """Открыть файлы вкладками; открытый — просто показать. Ошибки — списком."""
        problems, last = [], None
        for path in paths:
            key = _key(path)
            if key in self.docs:
                last = key
                continue
            if not Path(path).is_file():
                if not quiet:
                    problems.append(T("tab.missing", path=path))
                continue
            try:
                # бэкапы — рядом с файлом состояния окна: тест с копией пишет к себе (п. 67)
                doc = Document(Path(path), backup_root=self.store.path.parent / "imageset_backup")
            except Exception as exc:  # noqa: BLE001 — чужой файл ломается как угодно
                problems.append(T("tab.unreadable", path=path, text=exc))
                continue
            view = DocumentView(doc, self.stack)
            self.stack.addWidget(view)
            self.docs[key] = (doc, view)
            self.order.append(key)
            # только просмотр — значком «глаз», а не текстом: текст обрезался во вкладке
            self.tabs.addTab(key, self._tab_text(doc), FluentIcon.VIEW if doc.readonly else FluentIcon.TILES)
            index = len(self.order) - 1
            tip = str(doc.path) + ("\n" + T("tab.readonly.tip") if doc.readonly else "")
            self.tabs.setTabToolTip(index, tip)
            doc.dirty_changed.connect(lambda _d, k=key: self._refresh_tab(k))
            last = key
        if last is not None:
            self.tabs.setCurrentIndex(self.order.index(last))
            self._on_tab(self.order.index(last))
        self._remember()
        if problems:
            box = MessageBox(T("open.title"), "\n".join(problems), self)
            box.yesButton.setText(T("dialog.ok"))
            box.cancelButton.hide()
            box.exec()

    def _restore(self) -> None:
        self.open_paths(self.store.tabs, quiet=True)
        if self.store.active and _key(self.store.active) in self.docs:
            index = self.order.index(_key(self.store.active))
            self.tabs.setCurrentIndex(index)
            self._on_tab(index)
        self._sync()

    # ================================================================== вкладки
    @staticmethod
    def _tab_text(doc: Document) -> str:
        return doc.path.name + (" ●" if doc.dirty else "")

    def _refresh_tab(self, key: str) -> None:
        if key in self.docs:
            self.tabs.setTabText(self.order.index(key), self._tab_text(self.docs[key][0]))

    def current(self) -> Optional[Document]:
        index = self.tabs.currentIndex()
        return self.docs[self.order[index]][0] if 0 <= index < len(self.order) else None

    def _on_tab(self, index: int) -> None:
        # автосохранение при переключении: сохраняем ту вкладку, с которой ушли
        shown = self.stack.currentWidget()
        for doc, view in self.docs.values():
            if view is shown and (index < 0 or index >= len(self.order)
                                  or self.docs[self.order[index]][1] is not view):
                doc.save()
        if 0 <= index < len(self.order):
            doc, view = self.docs[self.order[index]]
            self.stack.setCurrentWidget(view)
            self.setWindowTitle(T("app.titled", name=doc.path.name))
        self._sync()
        self._remember()

    def close_tab(self, index: int) -> None:
        if not 0 <= index < len(self.order):
            return
        key = self.order[index]
        doc, view = self.docs.pop(key)
        doc.save()
        self.order.pop(index)
        self.tabs.removeTab(index)
        self.stack.removeWidget(view)
        view.deleteLater()
        if self.order:
            self._on_tab(self.tabs.currentIndex())
        self._sync()
        self._remember()

    def _step(self, delta: int) -> None:
        if self.order:
            self.tabs.setCurrentIndex((self.tabs.currentIndex() + delta) % len(self.order))
            self._on_tab(self.tabs.currentIndex())

    def _stack_do(self, action: str) -> None:
        doc = self.current()
        if doc is not None:
            getattr(doc.undo, action)()

    def _sync(self) -> None:
        if not self.order:
            self.stack.setCurrentWidget(self.empty)
            self.setWindowTitle(T("app.title"))
        self.tabs.setVisible(bool(self.order))

    def _remember(self) -> None:
        self.store.tabs = [str(self.docs[k][0].path) for k in self.order]
        doc = self.current()
        self.store.active = str(doc.path) if doc else ""
        self.store.save()

    # ================================================================== автосохранение
    def save_all(self) -> None:
        for doc, _view in self.docs.values():
            doc.save()

    def changeEvent(self, event) -> None:
        # потеря фокуса окном — сохранить всё, как VSCode с autoSave onFocusChange
        if event.type() == QEvent.ActivationChange and not self.isActiveWindow():
            self.save_all()
        super().changeEvent(event)

    def _repaint_theme(self, *_args) -> None:
        for _doc, view in self.docs.values():
            view.repaint_theme()

    def closeEvent(self, event) -> None:
        self.save_all()
        self._remember()
        self.store.window["size"] = [self.width(), self.height()]
        self.store.save()
        QApplication.instance().removeEventFilter(self._drop)
        super().closeEvent(event)
