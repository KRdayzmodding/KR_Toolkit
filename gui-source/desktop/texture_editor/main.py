# -*- coding: utf-8 -*-
"""Текстуры: python desktop/texture_editor/main.py [файл | папка | файлы…]

Одно окно на всю работу с текстурами. Раньше это были три отдельные
программы — просмотр, фильтр SMDI по папке и подбор Френеля — и консольная
утилита смены размера. Теперь это вкладки, и возможности у них прежние:
переделка поменяла вход, а не то, что за ним.

Что делает аргумент командной строки, так же как бросок файлов на exe:

* один файл — открыть его на вкладке просмотра;
* папка — поставить её во вкладку фильтра SMDI, как делал smdi.exe;
* несколько файлов — положить их в список смены размера, как их бросали на
  TextureResizer.exe.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import List, Optional

_HERE = Path(__file__).resolve().parent
_ROOT = _HERE.parents[1]
for _p in (str(_HERE), str(_ROOT), str(_HERE.parent), str(_ROOT / "kits")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from PySide6.QtCore import QObject, Signal                                # noqa: E402
from PySide6.QtGui import QAction, QKeySequence                           # noqa: E402
from PySide6.QtWidgets import (                                           # noqa: E402
    QApplication, QFrame, QHBoxLayout, QScrollArea, QSizePolicy, QStackedWidget, QVBoxLayout,
)
from qfluentwidgets import FluentIcon, SegmentedWidget                    # noqa: E402

import fresnel_page                                                       # noqa: E402
import look                                                               # noqa: E402
import resize_page                                                        # noqa: E402
import smdi_folder                                                        # noqa: E402
import viewer                                                             # noqa: E402
from qts_ui import tokens                                                 # noqa: E402
from qts_ui.frame import ToolWindow                                       # noqa: E402

from version import NAME, VERSION                                          # noqa: E402

TEXT = {
    "title": "%s %s" % (NAME, VERSION),
    "titled": "%%s — %s %s" % (NAME, VERSION),
    "menu_file": "Файл",
    "quit": "Выход",
}

#: стартовый размер окна: при нём ни одна вкладка не прокручивается. На
#: экране меньше окно ужимается до рабочей области, а вкладки прокручиваются
WINDOW = (1000, 860)

#: на сколько рамка окна выше и шире его содержимого — запас, пока окно не
#: показано и настоящую рамку не спросить (шапка своя, она в высоте окна)
FRAME = (16, 8)


class Tabs(QObject):
    """Вкладки сегментом (п. 90: рамка с кнопками читается как нажимаемое) и
    стопка страниц под ним. Интерфейс — как у QTabWidget, чтобы окно и тесты
    говорили о вкладках прежними словами."""

    currentChanged = Signal(int)

    def __init__(self, parent):
        super().__init__(parent)
        self.bar = SegmentedWidget(parent)
        self.bar.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.stack = QStackedWidget(parent)
        self._titles = []

    def addTab(self, widget, title: str) -> None:                     # noqa: N802
        index = len(self._titles)
        self._titles.append(title)
        self.stack.addWidget(widget)
        self.bar.addItem(str(index), title, lambda *_, i=index: self.setCurrentIndex(i))
        if index == 0:
            self.bar.setCurrentItem("0")

    def count(self) -> int:
        return len(self._titles)

    def tabText(self, index: int) -> str:                              # noqa: N802
        return self._titles[index]

    def currentIndex(self) -> int:                                     # noqa: N802
        return self.stack.currentIndex()

    def currentWidget(self):                                           # noqa: N802
        return self.stack.currentWidget()

    def setCurrentIndex(self, index: int) -> None:                     # noqa: N802
        self.bar.setCurrentItem(str(index))
        if index != self.stack.currentIndex():
            self.stack.setCurrentIndex(index)
            self.currentChanged.emit(index)


class Window(ToolWindow):
    """Главное окно: своя шапка (как у QTS и остальных тулз), вкладки, меню.

    Хранилища настроек у вкладок прежние, по одному на бывшую программу.
    Так недавние файлы, папка фильтра и крутилки Френеля переезжают в общее
    окно вместе с человеком. Тест передаёт свои, чтобы не трогать настоящие.
    """

    def __init__(self, argv: Optional[List[str]] = None,
                 settings: Optional[dict] = None):
        super().__init__(FluentIcon.PALETTE, image="TextureEditor")
        settings = settings or {}
        paths = [Path(a) for a in (argv or [])]
        one_file = paths[0] if len(paths) == 1 and paths[0].is_file() else None
        one_folder = paths[0] if len(paths) == 1 and paths[0].is_dir() else None
        many = [str(p) for p in paths] if len(paths) > 1 else None

        self.viewer = viewer.ViewerPage(str(one_file) if one_file else None,
                                        settings.get("viewer"))
        self.smdi = smdi_folder.SmdiPage(str(one_folder) if one_folder else "",
                                         settings.get("smdi"))
        self.resize_page = resize_page.ResizePage(many, settings.get("resize"))
        self.fresnel = fresnel_page.FresnelPage(settings.get("fresnel"))
        self.pages = [self.viewer, self.smdi, self.resize_page, self.fresnel]

        self.tabs = Tabs(self.body)
        for page, title in ((self.viewer, viewer.TEXT["tab"]),
                            (self.smdi, smdi_folder.TEXT["tab"]),
                            (self.resize_page, resize_page.TEXT["tab"]),
                            (self.fresnel, fresnel_page.TEXT["tab"])):
            self.tabs.addTab(_scrolled(page), title)

        root = QVBoxLayout(self.body)
        root.setContentsMargins(tokens.SPACE_M, tokens.SPACE_XS, tokens.SPACE_M, tokens.SPACE_XS)
        root.setSpacing(tokens.SPACE_XS)
        self.top = QHBoxLayout()
        self.top.setSpacing(tokens.SPACE_XXS)
        self.top.addWidget(self.tabs.bar)
        self.top.addStretch(1)
        root.addLayout(self.top)
        root.addWidget(self.tabs.stack, 1)

        self._menus()
        self.viewer.caption_changed.connect(lambda _name: self._title())
        self.viewer.wants_front.connect(lambda: self.show_page(self.viewer))
        self.tabs.currentChanged.connect(self._tab_changed)

        if one_folder:
            self.show_page(self.smdi)
        elif many:
            self.show_page(self.resize_page)
        self._tab_changed(self.tabs.currentIndex())

    def page(self):
        """Открытая вкладка — сама страница, а не прокрутка вокруг неё."""
        return self.pages[self.tabs.currentIndex()]

    def show_page(self, page) -> None:
        self.tabs.setCurrentIndex(self.pages.index(page))

    def _menus(self) -> None:
        """Меню — кнопками справа от вкладок: строки меню у окна со своей шапкой
        нет. «Открыть…» и «Выход» есть всегда — открыть текстуру можно с любой
        вкладки; остальные пункты просмотра и его меню «Правка», «Мип», «Вид»
        видны, только пока открыта его вкладка."""
        # действие живёт во вкладке, а сочетание должно работать и на соседних:
        # вешаем его ещё и на окно, которое видно всегда
        self.addAction(self.viewer.open_action)
        self.quit_action = QAction(TEXT["quit"], self)
        self.quit_action.setShortcut(QKeySequence.Quit)
        self.quit_action.triggered.connect(self.close)
        self.addAction(self.quit_action)
        self.viewer_file_actions = [a for a in self.viewer.file_actions if isinstance(a, QAction)]
        file_items = ([self.viewer.open_action, None] + list(self.viewer.file_actions)
                      + [None, self.quit_action])
        self.file_button = look.menu_button(TEXT["menu_file"], file_items, self.body)
        self.viewer_menus = [look.menu_button(title, items, self.body)
                             for title, items in self.viewer.menus]
        self.menu_buttons = [self.file_button] + self.viewer_menus
        for button in self.menu_buttons:
            self.top.addWidget(button)

    def _tab_changed(self, _index: int) -> None:
        on_viewer = self.page() is self.viewer
        for action in self.viewer_file_actions:
            action.setVisible(on_viewer)
        self.viewer.recent_menu.visible = on_viewer
        for button in self.viewer_menus:
            button.setVisible(on_viewer)
        self._title()
        self.page().activate()

    def _title(self) -> None:
        name = self.viewer.caption()
        if self.page() is self.viewer and name:
            self.setWindowTitle(TEXT["titled"] % name)
        else:
            self.setWindowTitle(TEXT["title"])

    def closeEvent(self, event) -> None:
        # вложенные вкладки своего closeEvent не получают: гасим работу и
        # сохраняем выбор сами
        for page in self.pages:
            if hasattr(page, "shutdown"):
                page.shutdown()
        _save_size(self)
        super().closeEvent(event)


def _scrolled(page) -> QScrollArea:
    """Вкладка в прокрутке. Пока места хватает, она тянется как обычно; не
    хватает — прокручивается, а не распирает окно выше экрана. Самой высокой
    вышла вкладка Френеля: с меню и вкладками ей нужно больше, чем есть на
    экране 1366x768 за вычетом панели задач."""
    area = QScrollArea()
    area.setWidgetResizable(True)
    area.setFrameShape(QFrame.NoFrame)
    area.setWidget(page)
    return area


def start_size(available, remembered=None) -> tuple:
    """Стартовый размер: тот, в котором окно оставили (п. 87), иначе ``WINDOW``;
    в любом случае не больше рабочей области экрана."""
    width, height = remembered or WINDOW
    return (min(width, available[0] - FRAME[0]),
            min(height, available[1] - FRAME[1]))


#: размер окна — в общем файле состояния тулз (правило юзера 23.10.2026)
STATE_NAME = "texture_editor.json"


def _state_file():
    from kr_state import state_file
    return state_file(STATE_NAME)


def _remembered_size():
    import json
    try:
        size = json.loads(_state_file().read_text(encoding="utf-8")).get("size")
        return (int(size[0]), int(size[1])) if size else None
    except (OSError, ValueError, TypeError, IndexError, AttributeError):
        return None


def _save_size(window) -> None:
    """Размер — только у окна, открытого main(): тесты в настоящий файл не пишут (п. 67)."""
    if getattr(window, "remember_size", False):
        import json
        path = _state_file()
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps({"size": [window.width(), window.height()]}), encoding="utf-8")
        except OSError:
            pass


def main(argv=None) -> int:
    argv = list(sys.argv if argv is None else argv)
    app = QApplication(argv)
    from kr_state import theme_name
    look.setup_theme(app, theme_name())
    window = Window(argv[1:])
    window.remember_size = True
    window.resize(*start_size(app.primaryScreen().availableGeometry().size().toTuple(),
                              _remembered_size()))
    window.show()
    # обновления: проверка в фоне, одно окно на все новые версии; устаревшая — предупреждение
    from qts_ui import updates_ui
    updates_ui.watch(window, "TextureEditor")
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
