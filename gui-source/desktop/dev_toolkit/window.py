# -*- coding: utf-8 -*-
"""Окно лаунчера: по карточке на тулзу — значок, название, что делает; щелчок — запуск.

Заказ юзера 23.10.2026: лаунчер, из которого запускаются наши тулзы с окном.
Несобранная тулза видна, но карточка неактивна, а в пояснении — где её exe
должен лежать (п. 53: причина видна, а не просто серая строка).

24.10.2026: тулзы массовой работы с файлами — отдельным разделом; вторая
страница — пункты контекстного меню проводника (PBO, P3D, BIN) и их настройки.
Страница, а не отдельное окно (п. 12); настраивается редко, поэтому не на
одном экране с ежедневным запуском (п. 6).

Реестр окно само не пишет: пункты меню включает DevToolkit.exe (menu.py).
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Optional

from PySide6.QtCore import QEasingCurve, QEvent, Qt, QVariantAnimation
from PySide6.QtGui import QPainter
from PySide6.QtWidgets import QGridLayout, QHBoxLayout, QSizePolicy, QStackedWidget, QVBoxLayout, QWidget
from qfluentwidgets import (BodyLabel, CaptionLabel, CardWidget, FluentIcon, IconWidget, LineEdit,
                            SegmentedWidget, StrongBodyLabel, SwitchButton)

import kr_state
from menu import MenuCall
from qts_ui import updates_ui
from versions_page import VersionsPage
from qts_ui import tokens
from qts_ui.rows import shrink
from qts_ui.frame import ToolWindow
from texts import T
from qfluentwidgets import qconfig, themeColor
from tools import BATCH, EDIT, TOOLS, Tool, dist_root, exe_path, launch, read_version

MIN = (520, 780)            # минимальный размер — он же размер первого запуска: карточки целиком

#: ключ тулзы → ключи названия и описания; буквально, не из кусков (п. 66)
TITLES = {"build": ("tool.build", "tool.build.desc"),
          "sign": ("tool.sign", "tool.sign.desc"),
          "textures": ("tool.textures", "tool.textures.desc"),
          "sound": ("tool.sound", "tool.sound.desc"),
          "imageset": ("tool.imageset", "tool.imageset.desc"),
          "texconv": ("tool.texconv", "tool.texconv.desc"),
          "models": ("tool.models", "tool.models.desc"),
          "debin": ("tool.debin", "tool.debin.desc"),
          "pbo": ("tool.pbo", "tool.pbo.desc"),
          "anm": ("tool.anm", "tool.anm.desc")}
GROUPS = ((EDIT, "group.edit"), (BATCH, "group.batch"))
SHELL_TEXTS = {"pbo": ("shell.pbo", "shell.pbo.desc"),
               "p3d": ("shell.p3d", "shell.p3d.desc"),
               "bin": ("shell.bin", "shell.bin.desc")}
#: тулзы в «Открыть с помощью» (заказ юзера 27.10.2026) — одним переключателем: какая
#: тулза станет программой по умолчанию, человек выбирает в самом «Открыть с помощью»
OPEN_TEXTS = {"open": ("shell.open", "shell.open.desc")}
THEME_TEXTS = {"auto": "theme.auto", "light": "theme.light", "dark": "theme.dark"}
#: как работают пункты, пока человек не выбрал своё (те же, что у DevToolkit.exe)
SHELL_DEFAULTS = {"delete_source": False, "suffix": "_mlod", "layout": "prefix"}


class LauncherWindow(ToolWindow):
    def __init__(self, root: Optional[Path] = None, state_file: Optional[Path] = None,
                 shell_base: str = ""):
        super().__init__(FluentIcon.DEVELOPER_TOOLS, image="dev_toolkit")              # своя шапка, как в QTS (qts_ui.frame)
        self.root = root or dist_root()
        self.shell_base = shell_base                              # тест подменяет ключ реестра
        self._menu_calls: List[tuple] = []                        # очередь вызовов DevToolkit.exe menu
        self._menu_job: Optional[MenuCall] = None
        from kr_state import state_file as _state
        self.state_file = Path(state_file) if state_file is not None else _state("dev_toolkit.json", "launcher.json")
        state = self._state()
        self.shell_settings = dict(SHELL_DEFAULTS, **{k: v for k, v in dict(state.get("shell", {})).items()
                                                      if k in SHELL_DEFAULTS})
        self.setWindowTitle(T("app.title"))
        self.setMinimumSize(*MIN)
        # первый запуск — минимальный размер; дальше — тот, в котором окно оставили (п. 87)
        w, h = state.get("size", MIN)
        self.resize(max(w, MIN[0]), max(h, MIN[1]))
        self._build()
        self.refresh()
        self._refresh_shell(announce=True)
        # тему сменили в другой тулзе — окно перекрасит слежение, а выбор на сегменте — здесь
        qconfig.themeChanged.connect(self._sync_theme)

    def _state(self) -> dict:
        try:
            return dict(json.loads(self.state_file.read_text(encoding="utf-8")))
        except (OSError, ValueError, TypeError):
            return {}

    def _save_state(self, **changes) -> None:
        state = self._state()
        state.update(changes)
        try:
            self.state_file.parent.mkdir(parents=True, exist_ok=True)
            self.state_file.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
        except OSError:
            pass

    # ================================================================== сборка
    def _build(self) -> None:
        root = QVBoxLayout(self.body)
        root.setContentsMargins(tokens.SPACE_L, tokens.SPACE_M, tokens.SPACE_L, tokens.SPACE_M)
        root.setSpacing(tokens.SPACE_S)
        # вкладки — сегментом: рамка с кнопками читается как нажимаемое (п. 90)
        self.pages_switch = SegmentedWidget(self)
        self.pages_switch.addItem("tools", T("page.tools"), lambda *_: self.pages.setCurrentIndex(0))
        self.pages_switch.addItem("shell", T("page.shell"), lambda *_: self.pages.setCurrentIndex(1))
        self.pages_switch.addItem("versions", T("page.versions"), lambda *_: self.pages.setCurrentIndex(2))
        self.pages_switch.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        root.addWidget(self.pages_switch, 0, Qt.AlignLeft)
        self.pages = QStackedWidget(self)
        self.pages.addWidget(self._tools_page())
        self.pages.addWidget(self._shell_page())
        # проверка обновлений лаунчера — та же, что у вкладки: одна на запуск
        self.update_report: Optional[dict] = None
        self._offered = False
        self.versions = VersionsPage(on_report=self._on_update_report, parent=self)
        self.pages.addWidget(self.versions)
        root.addWidget(self.pages, 1)
        self.pages_switch.setCurrentItem("tools")

        # строка внизу — только когда есть что сказать: тулза не запустилась или
        # пункты меню переписаны под новую папку. «Запущено» и путь к поставке
        # не показываем (юзер 24.10.2026): запуск видно и так, путь — в подсказке карточки
        self.status = shrink(CaptionLabel("", self))
        self.status.hide()
        root.addWidget(self.status)

    def _tools_page(self) -> QWidget:
        page = QWidget(self)
        lay = QVBoxLayout(page)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(tokens.SPACE_XS)
        self.rows: Dict[str, CardWidget] = {}
        for group, title in GROUPS:
            head = StrongBodyLabel(T(title), page)
            lay.addSpacing(tokens.SPACE_XS)
            lay.addWidget(head)
            for tool in TOOLS:
                if tool.group == group:
                    row = self._row(tool, page)
                    self.rows[tool.key] = row
                    lay.addWidget(row)
        lay.addStretch(1)
        return page

    def _row(self, tool: Tool, parent: QWidget) -> CardWidget:
        """Карточка тулзы — сама кнопка запуска (юзер 23.10.2026: «Открыть» лишняя).

        Значок, название и что делает. Щелчок, Enter или пробел на карточке в
        фокусе — запуск. Своя, а не setting_row: та рассчитана на страницу с
        прокруткой и в обычном окне обрезала пояснение.
        """
        title, desc = TITLES[tool.key]
        card = CardWidget(parent)
        # высота по содержимому: лишнее место окна уходит вниз, а не в карточки
        card.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        card.setCursor(Qt.PointingHandCursor)
        card.setFocusPolicy(Qt.StrongFocus)
        lay = QHBoxLayout(card)
        lay.setContentsMargins(tokens.SPACE_M, tokens.SPACE_XS, tokens.SPACE_M, tokens.SPACE_XS)
        lay.setSpacing(tokens.SPACE_M)
        icon = IconWidget(getattr(FluentIcon, tool.icon), card)
        icon.setFixedSize(24, 24)
        lay.addWidget(icon, 0, Qt.AlignVCenter)
        text = QVBoxLayout()
        text.setSpacing(tokens.SPACE_XXS)
        card.title_label = StrongBodyLabel(T(title), card)
        text.addWidget(card.title_label)
        # одной строкой, без переноса: перенос резервировал вторую строку под пустоту
        card.desc_label = CaptionLabel(T(desc), card)
        text.addWidget(card.desc_label)
        lay.addLayout(text, 1)
        # версию отдаёт сама тулза — сборщик пишет её в runtime\versions.json
        card.version_label = CaptionLabel("", card)
        lay.addWidget(card.version_label, 0, Qt.AlignVCenter)
        card.launch_bar = LaunchBar(card)
        card.clicked.connect(lambda t=tool: self._open(t))
        return card

    def _shell_page(self) -> QWidget:
        page = QWidget(self)
        lay = QVBoxLayout(page)
        lay.setContentsMargins(0, tokens.SPACE_XS, 0, 0)
        lay.setSpacing(tokens.SPACE_S)
        # тема одна на все тулзы, открытые окна подхватывают её сразу (решение юзера 27.10.2026)
        look = QGridLayout()
        look.setHorizontalSpacing(tokens.SPACE_S)
        look.setColumnStretch(0, 1)
        self.shell_switches: Dict[str, SwitchButton] = {}
        self.shell_descs: Dict[str, CaptionLabel] = {}
        self.theme_seg = SegmentedWidget(page)
        for name, text in THEME_TEXTS.items():
            self.theme_seg.addItem(name, T(text), lambda *_, n=name: self._set_theme(n))
        self.theme_seg.setCurrentItem(kr_state.theme_name())
        self.theme_seg.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self._setting(look, 0, page, T("theme"), T("theme.desc"), "theme", self.theme_seg)
        lay.addLayout(look)
        lay.addWidget(StrongBodyLabel(T("shell.head"), page))
        grid = QGridLayout()
        grid.setHorizontalSpacing(tokens.SPACE_S)
        grid.setVerticalSpacing(tokens.SPACE_XXS)
        grid.setColumnStretch(0, 1)
        # переключатель — состояние системы: пункт есть в меню или нет (п. 15)
        for row, (key, (title, desc)) in enumerate(SHELL_TEXTS.items()):
            switch = self._switch(page)
            switch.setEnabled(False)                         # до ответа DevToolkit.exe состояние неизвестно
            switch.checkedChanged.connect(lambda on, k=key: self._toggle_entry(k, bool(on)))
            self._setting(grid, row, page, T(title), T(desc), key, switch)
            self.shell_switches[key] = switch
        lay.addLayout(grid)

        lay.addSpacing(tokens.SPACE_XS)
        lay.addWidget(StrongBodyLabel(T("open.head"), page))
        opens = QGridLayout()
        opens.setHorizontalSpacing(tokens.SPACE_S)
        opens.setVerticalSpacing(tokens.SPACE_XXS)
        opens.setColumnStretch(0, 1)
        for row, (key, (title, desc)) in enumerate(OPEN_TEXTS.items()):
            switch = self._switch(page)
            switch.setEnabled(False)
            switch.checkedChanged.connect(lambda on, k=key: self._toggle_entry(k, bool(on)))
            self._setting(opens, row, page, T(title), T(desc), key, switch)
            self.shell_switches[key] = switch
        lay.addLayout(opens)

        lay.addSpacing(tokens.SPACE_XS)
        lay.addWidget(StrongBodyLabel(T("shell.how"), page))
        how = QGridLayout()
        how.setHorizontalSpacing(tokens.SPACE_S)
        how.setVerticalSpacing(tokens.SPACE_XXS)
        how.setColumnStretch(0, 1)
        self.delete_switch = self._switch(page)
        self.delete_switch.setChecked(bool(self.shell_settings["delete_source"]))
        self.delete_switch.checkedChanged.connect(lambda on: self._set_shell("delete_source", bool(on)))
        self._setting(how, 0, page, T("shell.delete"), T("shell.delete.desc"), "delete", self.delete_switch)
        self.suffix_edit = LineEdit(page)
        self.suffix_edit.setFixedWidth(140)
        self.suffix_edit.setText(str(self.shell_settings["suffix"]))
        self.suffix_edit.editingFinished.connect(lambda: self._set_shell("suffix", self.suffix_edit.text().strip()))
        self._setting(how, 1, page, T("shell.suffix"), T("shell.suffix.desc"), "suffix", self.suffix_edit)
        # два варианта — сегмент (п. 13); по умолчанию по префиксу (юзер 24.10.2026)
        self.layout_seg = SegmentedWidget(page)
        self.layout_seg.addItem("prefix", T("layout.prefix"), lambda *_: self._set_shell("layout", "prefix"))
        self.layout_seg.addItem("flat", T("layout.flat"), lambda *_: self._set_shell("layout", "flat"))
        self.layout_seg.setCurrentItem(str(self.shell_settings["layout"]))
        self.layout_seg.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self._setting(how, 2, page, T("shell.layout"), T("shell.layout.desc"), "layout", self.layout_seg)
        lay.addLayout(how)
        lay.addStretch(1)
        return page

    def _setting(self, grid: QGridLayout, index: int, parent: QWidget, title: str, desc: str, key: str,
                 control: QWidget) -> None:
        """Строка настройки: название, под ним пояснение, контрол справа на обе строки.

        Ячейками сетки, а не вложенной колонкой: вложенная неверно считала высоту
        перенесённого пояснения и отрывала его от названия.
        """
        row = index * 3
        grid.setRowMinimumHeight(row + 2, tokens.SPACE_XS)        # воздух до следующей настройки
        grid.addWidget(BodyLabel(title, parent), row, 0)
        label = shrink(CaptionLabel(desc, parent))
        label.setTextColor(*tokens.pair("text_dim"))
        label.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        grid.addWidget(label, row + 1, 0)
        grid.addWidget(control, row, 1, 2, 1, Qt.AlignRight | Qt.AlignVCenter)
        self.shell_descs[key] = label

    def _switch(self, parent: QWidget) -> SwitchButton:
        switch = SwitchButton(parent)
        switch.setOnText(T("switch.on"))
        switch.setOffText(T("switch.off"))
        return switch

    # ================================================================== тулзы
    def refresh(self) -> None:
        """Какие тулзы собраны — заново при каждом показе: exe могли пересобрать."""
        for tool in TOOLS:
            exe = exe_path(tool, self.root)
            built = exe.is_file()
            # несобранная: карточка неактивна, причина — в её пояснении (п. 53)
            self.rows[tool.key].setEnabled(built)
            self.rows[tool.key].setToolTip(str(exe))
            # путь внутри папки сборок: полный растянул бы окно, он — в подсказке
            desc = T(TITLES[tool.key][1]) if built else T("tool.missing", path=tool.exe)
            self.rows[tool.key].desc_label.setText(desc)
            self.rows[tool.key].desc_label.setToolTip("" if built else str(exe))
            self._show_version(tool)

    def _show_version(self, tool: Tool) -> None:
        """Название и версия: из проверки обновлений, если она уже ответила, иначе из
        versions.json поставки; нет ни того ни другого — запасное название."""
        card = self.rows[tool.key]
        st = (self.update_report or {}).get("tools", {}).get(updates_ui.tool_name(Path(tool.exe)))
        if st and st.get("installed"):
            card.title_label.setText(st.get("title") or T(TITLES[tool.key][0]))
            if st.get("warn"):
                text, colors = T("version.outdated") % st["installed"], tokens.pair("warning")
            elif st.get("newer"):
                text, colors = T("version.newer") % (st["installed"], st["latest"]), (tokens.ACCENT,) * 2
            else:
                text, colors = st["installed"], tokens.pair("text_dim")
            card.version_label.setText(text)
            card.version_label.setToolTip("")
            card.version_label.setTextColor(*colors)
            return
        info = read_version(tool, self.root)
        card.title_label.setText((info or {}).get("name") or T(TITLES[tool.key][0]))
        if info:
            card.version_label.setText(info["version"])
            card.version_label.setToolTip(T("version.tip", commit=info.get("commit") or "?",
                                            built=info.get("built") or "?"))
        else:
            card.version_label.setText(T("version.none") if exe_path(tool, self.root).is_file() else "")
            card.version_label.setToolTip(T("version.none.tip"))
        card.version_label.setTextColor(*tokens.pair("text_dim"))

    def _open(self, tool: Tool) -> None:
        card = self.rows[tool.key]
        name = card.title_label.text()                         # имя, которое отдала сама тулза
        card.launch_bar.start()                                # щелчок принят — до того, как окно тулзы появится
        try:
            launch(tool, self.root)
        except OSError as exc:
            card.launch_bar.cancel()
            self._say(T("tool.failed", name=name, text=exc), "error")
            self.refresh()
            return
        self._say("", "text_dim")                          # прежнее сообщение больше не к месту

    def _say(self, text: str, role: str) -> None:
        self.status.setText(text)
        self.status.setTextColor(*tokens.pair(role))
        self.status.setVisible(bool(text))

    # ================================================================== меню проводника
    def _refresh_shell(self, announce: bool = False) -> None:
        """Включённые пункты — под текущие настройки и папку; переключатели — по ответу."""
        self._menu("refresh", announce=announce)
        locked = bool(self.shell_settings["delete_source"])
        self.suffix_edit.setEnabled(not locked)
        self.shell_descs["suffix"].setText(T("shell.suffix.locked") if locked else T("shell.suffix.desc"))

    def _menu(self, action: str, keys: tuple = (), announce: bool = False) -> None:
        """Вызов DevToolkit.exe menu — в фоне и по одному: два щелчка подряд не пишут реестр разом."""
        args = [action, *keys, "--root", str(self.root), "--suffix", str(self.shell_settings["suffix"]),
                "--layout", str(self.shell_settings["layout"])]
        if self.shell_settings["delete_source"]:
            args.append("--delete-source")
        if self.shell_base:
            args += ["--base", self.shell_base]
        self._menu_calls.append((args, announce))
        self._next_menu_call()

    def _next_menu_call(self) -> None:
        if self._menu_job is not None or not self._menu_calls:
            return
        args, announce = self._menu_calls.pop(0)
        self._menu_job = MenuCall(args, self)
        self._menu_job.done.connect(lambda events, a=announce: self._menu_done(events, a))
        self._menu_job.start()

    def menu_idle(self) -> bool:
        return self._menu_job is None and not self._menu_calls

    def _menu_done(self, events: list, announce: bool) -> None:
        self._menu_job.wait()
        self._menu_job = None
        titles = {ev["key"]: ev.get("title", ev["key"]) for ev in events if ev.get("event") == "entry"}
        for ev in events:
            kind = ev.get("event")
            if kind == "entry" and ev.get("key") in self.shell_switches:
                key = ev["key"]
                switch = self.shell_switches[key]
                switch.blockSignals(True)
                switch.setChecked(bool(ev.get("on")))
                switch.blockSignals(False)
                missing = not ev.get("available")
                # нет программы в поставке — включить нельзя, причина видна (п. 53)
                switch.setEnabled(not missing or switch.isChecked())
                self.shell_descs[key].setText(
                    T("shell.missing", path=ev.get("cli", "")) if missing else T({**SHELL_TEXTS, **OPEN_TEXTS}[key][1]))
            elif kind == "refreshed" and announce:
                # решение за человека — вслух (принцип 13): поставку перенесли, пункты вели в никуда
                self._say(T("shell.refreshed", path=self.root,
                            names=", ".join(titles.get(k, k) for k in ev.get("keys", []))), "text_dim")
            elif kind == "problem":
                self._say(T("shell.failed", text=ev.get("text", "")), "error")
        self._next_menu_call()

    def _sync_theme(self, *_args) -> None:
        name = kr_state.theme_name()
        if self.theme_seg.currentRouteKey() != name:
            self.theme_seg.blockSignals(True)
            self.theme_seg.setCurrentItem(name)
            self.theme_seg.blockSignals(False)

    def _set_theme(self, name: str) -> None:
        """Сразу у себя и в общий выбор — остальные окна перекрасятся по нему сами."""
        from qfluentwidgets import setTheme
        from qts_ui.theme_sync import theme_of
        kr_state.set_theme(name)
        setTheme(theme_of(name))

    def _toggle_entry(self, key: str, on: bool) -> None:
        self._menu("on" if on else "off", (key,))

    def _set_shell(self, key: str, value) -> None:
        if self.shell_settings.get(key) == value:
            return
        self.shell_settings[key] = value
        self._save_state(shell=self.shell_settings)
        self._refresh_shell()

    # ================================================================== окно
    def showEvent(self, event):
        self.refresh()
        super().showEvent(event)
        if self.update_report is None:
            self.versions.refresh()            # первая проверка за запуск; ответ — в _on_update_report

    def _on_update_report(self, report: dict) -> None:
        """Свежий ответ проверки: версии на карточках, а при запуске — одно окно обновлений."""
        self.update_report = report
        self.refresh()
        if not self._offered:
            self._offered = True
            updates_ui.offer(report, "DevToolkit", self, on_done=lambda: self.versions.refresh(force=True))

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:                       # Esc — закрыть (п. 46)
            self.close()
            return
        if event.key() in (Qt.Key_Return, Qt.Key_Enter, Qt.Key_Space):
            # Enter или пробел — запуск карточки в фокусе (п. 46)
            for key, card in self.rows.items():
                if card.hasFocus() and card.isEnabled():
                    self._open(next(t for t in TOOLS if t.key == key))
                    return
        super().keyPressEvent(event)

    def closeEvent(self, event):
        if self.versions.call is not None:      # вызов DevToolkit.exe короткий — дождаться
            self.versions.call.wait()
        # вызов DevToolkit.exe короткий — дождаться, а не рвать поток на ходу
        self._menu_calls.clear()
        if self._menu_job is not None:
            self._menu_job.wait()
        self._save_state(size=[self.width(), self.height()])
        super().closeEvent(event)


class LaunchBar(QWidget):
    """Тонкая полоска внизу карточки: щелчок принят, тулза запускается (юзер 25.10.2026).

    Неточная — заполняется за DURATION и гаснет. Окно тулзы появляется через
    секунду-две, и без отклика казалось, что щелчок не дошёл.
    """

    DURATION = 2000
    HEIGHT = 2

    def __init__(self, card: QWidget):
        super().__init__(card)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.part = 0.0
        self.anim = QVariantAnimation(self)
        self.anim.setStartValue(0.0)
        self.anim.setEndValue(1.0)
        self.anim.setDuration(self.DURATION)
        self.anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.anim.valueChanged.connect(self._step)
        self.anim.finished.connect(self.hide)
        card.installEventFilter(self)
        self.hide()

    def eventFilter(self, obj, event):
        if obj is self.parentWidget() and event.type() == QEvent.Type.Resize:
            self._place()
        return False

    def _place(self) -> None:
        card = self.parentWidget()
        inset = tokens.RADIUS_CARD           # по скруглению карточки: полоска не вылезает за углы
        self.setGeometry(inset, card.height() - self.HEIGHT - 1, max(0, card.width() - 2 * inset), self.HEIGHT)

    def start(self) -> None:
        self._place()
        self.anim.stop()
        self.part = 0.0
        self.show()
        self.raise_()
        self.anim.start()

    def cancel(self) -> None:
        self.anim.stop()
        self.hide()

    def _step(self, value) -> None:
        self.part = float(value)
        self.update()

    def paintEvent(self, e):        # имя метода задаёт Qt
        painter = QPainter(self)
        painter.fillRect(0, 0, int(self.width() * self.part), self.height(), themeColor())

