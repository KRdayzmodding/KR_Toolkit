# -*- coding: utf-8 -*-
"""Окна рядом с главным: название набора, настройки, логи запаковки.

Главное окно держит только самое нужное (что, куда, кнопка, одна опция), всё
редкое — здесь, отдельными окнами, как у pboProject. Оформление — KR QTS:
qfluentwidgets, токены `qts_ui.tokens`, строки `qts_ui.rows.setting_row`,
тёмная тема через `ThemedDialog` (обычный QDialog на тёмной теме светлый).
"""
from __future__ import annotations

import html
import os
from pathlib import Path
from typing import Callable, Dict, List, Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QStackedWidget, QVBoxLayout, QWidget
from qfluentwidgets import (
    Action, BodyLabel, CaptionLabel, CheckBox, CompactSpinBox, DropDownPushButton, FluentIcon,
    LineEdit, ListWidget, MessageBox, RoundMenu,
    MessageBoxBase, PlainTextEdit, PushButton, ScrollArea, SegmentedWidget,
    StrongBodyLabel,
    SubtitleLabel, SwitchButton,
    ToolButton)

import worker as pb

from qts_ui import tokens
from qts_ui.rows import setting_row, shrink
from qts_ui.theme import ThemedDialog
from links import LinkText, LogSearch, act_link, finding_html
from store import read_global_settings, write_global_settings
from texts import T


# ====================================================================== тема
THEMES = ("auto", "light", "dark")


def theme_name(store) -> str:
    """Тема окон всех тулз. По умолчанию тёмная (правило юзера 23.10.2026 для всех тулз)."""
    name = store.window.get("theme", "dark") if store is not None else "dark"
    return name if name in THEMES else "dark"


def apply_theme(name: str) -> None:
    """Тема на лету: виджеты библиотеки перекрашиваются сами, свои — по themeChanged."""
    from qfluentwidgets import Theme, setTheme
    setTheme({"auto": Theme.AUTO, "light": Theme.LIGHT, "dark": Theme.DARK}.get(name, Theme.AUTO))


# ====================================================================== название набора
class NameDialog(MessageBoxBase):
    """Название набора. Занятое имя — подсказка прямо под полем, окно не закрывается."""

    def __init__(self, title: str, taken: List[str], text: str = "", parent=None):
        super().__init__(parent)
        self.taken = set(taken) - {text}
        self.viewLayout.addWidget(SubtitleLabel(title, self))
        self.edit = LineEdit(self)
        self.edit.setPlaceholderText(T("set.new.prompt"))
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
        self.hint.setText(T("set.name.taken", name=name) if clash else "")
        self.hint.setTextColor(tokens.color("error"), tokens.color("error"))
        self.yesButton.setEnabled(bool(name) and not clash)


# ====================================================================== настройки
class SettingsDialog(ThemedDialog):
    """Общие настройки сборки — файл project_builder.json; пишется на каждое изменение."""

    def __init__(self, settings_file: Path, parent=None, store=None):
        super().__init__(parent)
        self.settings_file = Path(settings_file)
        #: хранилище окна — для темы: это настройка окна, а не сборки
        self.store = store
        self.setWindowTitle(T("settings.title"))
        #: проверки, исправления и умолчания — от командной строки, а не из китов
        self.catalog = pb.catalog(self.settings_file)
        values = {**self.catalog.defaults, **read_global_settings(self.settings_file)}

        outer = QVBoxLayout(self)
        outer.setContentsMargins(tokens.SPACE_L, tokens.SPACE_M, tokens.SPACE_L, tokens.SPACE_M)
        outer.setSpacing(tokens.SPACE_S)
        # Вкладки — сегментом, а не Pivot: у Pivot текст без рамки и не читается как
        # кнопка (замечание юзера 22.10.2026); сегмент — тот же вид, что у переключателя
        # темы рядом, один вид переключателя на окно.
        self.tabs = SegmentedWidget(self)
        self.pages = QStackedWidget(self)
        outer.addWidget(self.tabs, 0, Qt.AlignLeft)
        outer.addWidget(self.pages, 1)
        build_scroll, root = self._page()
        self.pages.addWidget(build_scroll)
        checks_page = QWidget(self)
        checks_root = QVBoxLayout(checks_page)
        checks_root.setContentsMargins(0, 0, 0, 0)
        checks_root.setSpacing(tokens.SPACE_S)
        self.pages.addWidget(checks_page)
        fixes_scroll, fixes_root = self._page()
        self.pages.addWidget(fixes_scroll)
        self.tabs.addItem("build", T("settings.tab.build"),
                          lambda: self.pages.setCurrentWidget(build_scroll))
        self.tabs.addItem("checks", T("settings.tab.checks"),
                          lambda: self.pages.setCurrentWidget(checks_page))
        self.tabs.addItem("fixes", T("settings.tab.fixes"),
                          lambda: self.pages.setCurrentWidget(fixes_scroll))
        self.tabs.setCurrentItem("build")
        # длинный путь без пробелов не переносится — он в подсказке, а не в строке
        note = shrink(CaptionLabel(T("settings.file"), self))
        note.setToolTip(str(self.settings_file))
        root.addWidget(note)

        self._rows = []
        if self.store is not None:
            # три коротких взаимоисключающих варианта — сегмент (п. 13), как в QTS
            self.theme = SegmentedWidget(self)
            self.theme.addItem("auto", T("settings.theme.auto"), lambda: self._set_theme("auto"))
            self.theme.addItem("light", T("settings.theme.light"), lambda: self._set_theme("light"))
            self.theme.addItem("dark", T("settings.theme.dark"), lambda: self._set_theme("dark"))
            self.theme.setCurrentItem(theme_name(self.store))
            self._add_row(root, setting_row(T("settings.theme"), T("settings.theme.desc"), self.theme))

        self.odol = SegmentedWidget(self)
        self.odol.addItem("55", T("settings.odol.55"), lambda: self._save("odol_version", 55))
        self.odol.addItem("56", T("settings.odol.56"), lambda: self._save("odol_version", 56))
        self.odol.setCurrentItem(str(values.get("odol_version", 56)))
        self._add_row(root, setting_row(T("settings.odol"), T("settings.odol.desc"), self.odol))

        self.jobs = CompactSpinBox(self)
        self.jobs.setRange(0, 128)
        self.jobs.setValue(int(values.get("jobs", 0)))
        self.jobs.valueChanged.connect(lambda v: self._save("jobs", v))
        self._add_row(root, setting_row(T("settings.jobs"), T("settings.jobs.desc"), self.jobs))

        temp_box = QWidget(self)
        tl = QHBoxLayout(temp_box)
        tl.setContentsMargins(0, 0, 0, 0)
        tl.setSpacing(tokens.SPACE_XS)
        self.temp = LineEdit(temp_box)
        self.temp.setText(str(values.get("temp", "")))
        self.temp.setMinimumWidth(220)
        self.temp.editingFinished.connect(lambda: self._save("temp", self.temp.text().strip()))
        tl.addWidget(self.temp, 1)
        pick = ToolButton(FluentIcon.FOLDER, temp_box)
        pick.setToolTip(T("dialog.pick.temp"))
        pick.clicked.connect(self._pick_temp)
        tl.addWidget(pick)
        self._add_row(root, setting_row(T("settings.temp"), T("settings.temp.desc"), temp_box))

        self.exclude = LineEdit(self)
        self.exclude.setText("; ".join(values.get("exclude", [])))
        self.exclude.setMinimumWidth(260)
        self.exclude.setClearButtonEnabled(True)
        self.exclude.editingFinished.connect(self._save_exclude)
        self._add_row(root, setting_row(T("settings.exclude"), T("settings.exclude.desc"), self.exclude))

        # выключатель с двумя состояниями — SwitchButton (п. 13), как в QTS
        self.outside = SwitchButton(self)
        self.outside.setOnText(T("settings.on"))
        self.outside.setOffText(T("settings.off"))
        self.outside.setChecked(bool(values.get("ignore_outside", False)))
        self.outside.checkedChanged.connect(lambda on: self._save("ignore_outside", bool(on)))
        self._add_row(root, setting_row(T("settings.outside"), T("settings.outside.desc"), self.outside))

        # подпись (юзер 23.10.2026): путь к ключу — как temp, поле и кнопки рядом;
        # «создать» и «выбрать» — действия, которые дают значение этой настройки
        key_box = QWidget(self)
        kl = QHBoxLayout(key_box)
        kl.setContentsMargins(0, 0, 0, 0)
        kl.setSpacing(tokens.SPACE_XS)
        self.key_path = LineEdit(key_box)
        self.key_path.setText(str(values.get("sign_key", "")))
        self.key_path.setPlaceholderText(T("settings.key.none"))
        self.key_path.setMinimumWidth(220)
        self.key_path.editingFinished.connect(lambda: self._set_key(self.key_path.text().strip()))
        kl.addWidget(self.key_path, 1)
        self.key_pick = PushButton(T("settings.key.pick"), key_box)
        self.key_pick.clicked.connect(self._pick_key)
        kl.addWidget(self.key_pick)
        self.key_create = PushButton(T("settings.key.create"), key_box)
        self.key_create.clicked.connect(self._create_key)
        kl.addWidget(self.key_create)
        self._add_row(root, setting_row(T("settings.key"), T("settings.key.desc"), key_box))

        self.sign = SwitchButton(self)
        self.sign.setOnText(T("settings.on"))
        self.sign.setOffText(T("settings.off"))
        self.sign.setChecked(bool(values.get("sign", False)))
        self.sign.checkedChanged.connect(lambda on: self._save("sign", bool(on)))
        self.sign_row = setting_row(T("settings.sign"), T("settings.sign.desc"), self.sign)
        self._add_row(root, self.sign_row)
        self._update_sign()

        root.addStretch(1)
        self._build_checks(checks_root, values.get("levels") or {})
        self._build_fixes(fixes_root, values.get("fixes") or {})

        self.error = shrink(CaptionLabel("", self))
        self.error.setTextColor(tokens.color("error"), tokens.color("error"))
        outer.addWidget(self.error)
        bottom = QHBoxLayout()
        bottom.addStretch(1)
        close = PushButton(T("settings.close"), self)
        close.clicked.connect(self.accept)
        bottom.addWidget(close)
        outer.addLayout(bottom)
        self.error.setVisible(False)
        # шире обычного: слева список групп проверок, справа строки с уровнем
        self.resize(*tokens.WIN_XL)

    def _page(self):
        """Страница вкладки — область прокрутки: только она отдаёт подписям с
        переносом настоящую ширину (прямо в окне строки разъезжались)."""
        scroll = ScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea{background:transparent;border:none;}")
        body = QWidget(scroll)
        body.setObjectName("settingsBody")
        body.setStyleSheet("QWidget#settingsBody{background:transparent;}")
        scroll.setWidget(body)
        root = QVBoxLayout(body)
        root.setContentsMargins(0, 0, tokens.SPACE_S, 0)
        # строки вплотную, как в сетке Columns у QTS: воздух уже есть внутри строки
        root.setSpacing(0)
        return scroll, root

    def _add_row(self, layout, row) -> None:
        self._rows.append(row)
        layout.addWidget(row)

    # ------------------------------------------------------------------ проверки
    def _build_checks(self, root, levels: Dict[str, str]) -> None:
        """Слева — все группы сразу с числом проверок, справа — проверки группы.

        Одним длинным списком 41 строка пряталась под прокруткой: на экране
        пять, остальные заметить невозможно (замечание юзера 22.10.2026). Список
        групп показывает всё целиком, и в группе не больше дюжины строк.
        Закреплённые проверки — только для чтения, с причиной (п. 53).
        """
        head = QHBoxLayout()
        note = shrink(CaptionLabel(T("checks.note"), self))
        head.addWidget(note, 1)
        # одна кнопка на все проверки разом; «по умолчанию» — один из её пунктов
        self.all_btn = DropDownPushButton(T("checks.all"), self)
        menu = RoundMenu(parent=self.all_btn)
        for value, label in ((None, T("checks.all.default")),
                             (pb.ERROR, T("checks.all.error")),
                             (pb.WARNING, T("checks.all.warning")),
                             (pb.INFO, T("checks.all.info")),
                             (pb.OFF, T("checks.all.off"))):
            menu.addAction(Action(label, triggered=lambda _=False, v=value, l=label:
                                  self._ask_apply_all(v, l)))
        self.all_btn.setMenu(menu)
        head.addWidget(self.all_btn)
        root.addLayout(head)

        body = QHBoxLayout()
        body.setSpacing(tokens.SPACE_M)
        root.addLayout(body, 1)
        self.group_list = ListWidget(self)
        self.group_list.setFixedWidth(260)
        body.addWidget(self.group_list)
        self.group_pages = QStackedWidget(self)
        body.addWidget(self.group_pages, 1)

        self.level_controls: Dict[str, SegmentedWidget] = {}
        self.groups: List[str] = []
        pages: Dict[str, QVBoxLayout] = {}
        for check in self.catalog.checks:
            if check.group not in pages:
                scroll, page_root = self._page()
                self.group_pages.addWidget(scroll)
                pages[check.group] = page_root
                self.groups.append(check.group)
            if check.locked:
                control = CaptionLabel(T("checks.locked"), self)
                control.setTextColor(tokens.color("text_dim"), tokens.color("text_dim"))
            else:
                control = SegmentedWidget(self)
                for value, label in ((pb.ERROR, T("checks.error")),
                                     (pb.WARNING, T("checks.warning")),
                                     (pb.INFO, T("checks.info")),
                                     (pb.OFF, T("checks.off"))):
                    control.addItem(value, label,
                                    lambda v=value, c=check.code: self._set_level(c, v))
                control.setCurrentItem(levels.get(check.code, check.default))
                self.level_controls[check.code] = control
            pages[check.group].addWidget(setting_row(check.title, check.desc, control))
        for page_root in pages.values():
            page_root.addStretch(1)
        for _ in self.groups:
            self.group_list.addItem("")
        self._label_groups(levels)
        self.group_list.currentRowChanged.connect(self.group_pages.setCurrentIndex)
        self.group_list.setCurrentRow(0)

    def _label_groups(self, levels: Dict[str, str]) -> None:
        """Подпись группы — с числом проверок и итогом: сколько изменено (п. 18)."""
        for row, group in enumerate(self.groups):
            codes = [c for c in self.catalog.checks if c.group == group]
            changed = sum(1 for c in codes if c.code in levels and levels[c.code] != c.default)
            text = T("checks.group", group=group, count=len(codes))
            if changed:
                text += T("checks.group.changed", count=changed)
            self.group_list.item(row).setText(text)

    # ------------------------------------------------------------------ исправления
    def _build_fixes(self, root, chosen: Dict[str, str]) -> None:
        """Строка — одно исправление, варианты — сегментом; рисуется из реестра китов.

        Исправлений мало, поэтому одна страница с заголовками групп, а не
        список групп, как у проверок. Выбора, которого пока нет, — строка
        только для чтения с причиной (п. 53).
        """
        note = shrink(CaptionLabel(T("fixes.note"), self))
        note.setWordWrap(True)
        root.addWidget(note)
        self.fix_controls: Dict[str, SegmentedWidget] = {}
        group = None
        # группы — в порядке первого появления: исправления разных китов идут вперемешку
        order = list(dict.fromkeys(f.group for f in self.catalog.fixes))
        for fix in sorted(self.catalog.fixes, key=lambda f: order.index(f.group)):
            if fix.group != group:
                group = fix.group
                head = StrongBodyLabel(group, self)
                head.setContentsMargins(0, tokens.SPACE_M, 0, tokens.SPACE_XS)
                root.addWidget(head)
            control = SegmentedWidget(self)
            for value, label in fix.options:
                # *_: щелчок передаёт свой аргумент (checked) — без него он затирал v
                # значением True, и настройка не сохранялась (юзер 23.10.2026)
                control.addItem(value, label,
                                lambda *_, v=value, c=fix.code: self._set_fix(c, v))
            control.setCurrentItem(chosen.get(fix.code, fix.default))
            desc = fix.desc
            if fix.locked:
                # выбор виден, но не нажимается; причина — в описании, где ей хватает ширины
                control.setEnabled(False)
                desc = "%s. %s" % (fix.desc, fix.locked)
            else:
                self.fix_controls[fix.code] = control
            root.addWidget(setting_row(fix.title, desc, control))
        root.addStretch(1)

    def _set_fix(self, code: str, value: str) -> None:
        chosen = dict(read_global_settings(self.settings_file).get("fixes") or {})
        if value == self.catalog.fix_by_code[code].default:
            chosen.pop(code, None)              # в файле — только отличия от реестра
        else:
            chosen[code] = value
        self._save("fixes", chosen)

    def _set_level(self, code: str, value: str) -> None:
        levels = dict(read_global_settings(self.settings_file).get("levels") or {})
        if value == self.catalog.check_by_code[code].default:
            levels.pop(code, None)              # в файле — только отличия от реестра
        else:
            levels[code] = value
        self._save("levels", levels)
        self._label_groups(read_global_settings(self.settings_file).get("levels") or {})

    def _ask_apply_all(self, value: Optional[str], label: str) -> None:
        """Перед заменой всех уровней — подтверждение: отменить её нечем (п. 56)."""
        box = MessageBox(T("checks.all.confirm.title", action=label), T("checks.all.confirm"), self)
        box.yesButton.setText(T("checks.all.apply"))
        box.cancelButton.setText(T("dialog.cancel"))
        if box.exec():
            self.apply_all(value)

    def apply_all(self, value: Optional[str]) -> None:
        """Все незакреплённые проверки — одним уровнем; None — уровни реестра."""
        levels = {}
        if value is not None:
            levels = {c.code: value for c in self.catalog.checks
                      if not c.locked and c.default != value}
        self._save("levels", levels)
        for code, control in self.level_controls.items():
            control.setCurrentItem(levels.get(code, self.catalog.check_by_code[code].default))
        self._label_groups(levels)

    def _set_theme(self, name: str) -> None:
        self.store.window["theme"] = name
        self.store.save()
        apply_theme(name)

    def _pick_temp(self) -> None:
        from PySide6.QtWidgets import QFileDialog
        folder = QFileDialog.getExistingDirectory(self, T("dialog.pick.temp"), self.temp.text())
        if folder:
            self.temp.setText(str(Path(folder)))
            self._save("temp", str(Path(folder)))

    # ------------------------------------------------------------------ подпись
    def _update_sign(self) -> None:
        """Без ключа подписывать нечем: выключатель только для чтения, причина — в пояснении (п. 53)."""
        has_key = bool(self.key_path.text().strip())
        self.sign.setEnabled(has_key)
        self.sign_row.desc_label.setText(T("settings.sign.desc") if has_key
                                         else T("settings.sign.need_key"))

    def _set_key(self, path: str) -> None:
        """Ключ меняется только на приватный и читаемый; пустое поле — подпись выключается."""
        if path:
            key = pb.key_info(path)
            if key.get("error"):
                self._show_error(T("settings.key.unreadable", text=key["error"]))
                return
            if not key.get("private"):
                self._show_error(T("settings.key.public", name=Path(path).name))
                return
        values = read_global_settings(self.settings_file)
        values["sign_key"] = path
        if not path:
            values["sign"] = False
        problem = pb.check_settings(values, self.settings_file)
        if problem:
            self._show_error(T("settings.error", text=problem))
            return
        write_global_settings(self.settings_file, values)
        self.error.setVisible(False)
        self.key_path.setText(path)
        if not path:
            self.sign.setChecked(False)
        self._update_sign()

    def _pick_key(self) -> None:
        from PySide6.QtWidgets import QFileDialog
        start = self.key_path.text().strip()
        path, _ = QFileDialog.getOpenFileName(self, T("settings.key.pick"),
                                              str(Path(start).parent) if start else "",
                                              "*.biprivatekey")
        if path:
            self._set_key(str(Path(path)))

    def _create_key(self) -> None:
        """Пара ключей: имя и папка — одним окном сохранения. Занятое имя — отказ:
        новый ключ под старым именем сломал бы все подписанные им PBO."""
        from PySide6.QtCore import Qt as _Qt
        from PySide6.QtWidgets import QApplication, QFileDialog
        start = self.key_path.text().strip()
        path, _ = QFileDialog.getSaveFileName(self, T("settings.key.create"),
                                              str(Path(start).parent) if start else "",
                                              "*.biprivatekey",
                                              options=QFileDialog.Option.DontConfirmOverwrite)
        if not path:
            return
        target = Path(path)
        name = target.name[:-len(".biprivatekey")] if target.name.lower().endswith(".biprivatekey") \
            else target.name
        QApplication.setOverrideCursor(_Qt.CursorShape.WaitCursor)
        try:
            prv, pub = pb.create_key(name, target.parent)
        except RuntimeError as exc:
            self._show_error(T("settings.error", text=exc))
            return
        finally:
            QApplication.restoreOverrideCursor()
        self._set_key(str(prv))
        if self.error.isHidden():
            box = MessageBox(T("settings.key.create"),
                             T("settings.key.created", prv=prv.name, pub=pub.name, folder=prv.parent),
                             self)
            box.yesButton.setText(T("dialog.ok"))
            box.cancelButton.hide()
            box.exec()

    def _show_error(self, text: str) -> None:
        self.error.setText(text)
        self.error.setVisible(True)

    def _save_exclude(self) -> None:
        masks = [m.strip() for m in self.exclude.text().replace(",", ";").split(";") if m.strip()]
        self._save("exclude", masks)

    def _save(self, key: str, value) -> None:
        values = read_global_settings(self.settings_file)
        values[key] = value
        problem = pb.check_settings(values, self.settings_file)
        if problem:
            self.error.setText(T("settings.error", text=problem))
            self.error.setVisible(True)
            return
        write_global_settings(self.settings_file, values)
        self.error.setVisible(False)


# ====================================================================== логи
#: ссылка под находкой, с отступом: в конце длинной строки её не видно без прокрутки вправо
_UNDER = "<br>" + "&nbsp;" * 7


class LogsDialog(ThemedDialog):
    """Логи последней запаковки: слева PBO, справа — ошибки и предупреждения.

    По умолчанию только то, что требует внимания (как окно логов pboProject в
    QTS): тысяча строк «пересобрано» прячет пару настоящих проблем. Полный лог —
    галкой, это тот же файл `<temp>\\<префикс>.kr_build.log`.
    """

    def __init__(self, items: List[dict], parent=None, select: str = "", focus: str = ""):
        """select — имя PBO, открыть сразу на нём; focus — "error"/"warning": к этому разделу."""
        super().__init__(parent)
        self.items = items
        self.focus = focus
        # «Пометить на модели»: что помечать (по номеру ссылки) и чем кончилось
        self._mark_targets: List[tuple] = []
        self._mark_state: Dict[tuple, tuple] = {}
        self.setWindowTitle(T("logs.title"))
        self.resize(*tokens.WIN_XL)
        root = QHBoxLayout(self)
        root.setContentsMargins(tokens.SPACE_M, tokens.SPACE_M, tokens.SPACE_M, tokens.SPACE_M)
        root.setSpacing(tokens.SPACE_M)

        self.list = ListWidget(self)
        self.list.setFixedWidth(240)
        root.addWidget(self.list)

        right = QVBoxLayout()
        right.setSpacing(tokens.SPACE_XS)
        root.addLayout(right, 1)
        head = QHBoxLayout()
        self.summary = shrink(StrongBodyLabel("", self))
        head.addWidget(self.summary, 1)
        self.full = CheckBox(T("logs.full"), self)
        self.full.stateChanged.connect(lambda _s: self._show())
        head.addWidget(self.full)
        self.open_btn = PushButton(FluentIcon.DOCUMENT, T("logs.open_file"), self)
        self.open_btn.clicked.connect(self._open_file)
        head.addWidget(self.open_btn)
        right.addLayout(head)
        self.view = LinkText(self)
        self.view.setReadOnly(True)
        self.view.setFont(tokens.mono_font())
        self.view.setLineWrapMode(PlainTextEdit.LineWrapMode.NoWrap)
        tokens.apply_console(self.view)
        self.view.actionRequested.connect(self._on_action)
        self.search = LogSearch(self.view, T("logs.search"), T("logs.search.count"), T("logs.search.none"), self)
        right.addWidget(self.search)
        right.addWidget(self.view, 1)
        from PySide6.QtGui import QKeySequence, QShortcut
        QShortcut(QKeySequence.StandardKey.Find, self, activated=self.search.focus)

        if not items:
            self.summary.setText(T("logs.empty"))
            self.full.setEnabled(False)
            self.open_btn.setEnabled(False)
            self.search.setEnabled(False)
            return
        for item in items:
            self.list.addItem(item["name"])
            row = self.list.item(self.list.count() - 1)
            row.setForeground(_qcolor(_role(item)))
        self.list.currentRowChanged.connect(lambda _r: self._show())
        chosen = [i for i, it in enumerate(items) if it["name"] == select]
        first_bad = next((i for i, it in enumerate(items) if _role(it) == "error"), 0)
        self.list.setCurrentRow(chosen[-1] if chosen else first_bad)

    def _current(self) -> Optional[dict]:
        row = self.list.currentRow()
        return self.items[row] if 0 <= row < len(self.items) else None

    def _show(self) -> None:
        self._fill()
        self.search.refresh()                     # другой PBO или полный лог — совпадения заново

    def _fill(self) -> None:
        item = self._current()
        if item is None:
            return
        report: Optional[pb.Result] = item.get("report")
        role = _role(item)
        if report is None:
            self.summary.setText(T("logs.summary.exc", pbo=item["name"], text=item.get("error", "")))
        elif report.errors:
            self.summary.setText(T("logs.summary.bad", pbo=item["name"], errors=len(report.errors),
                                   warnings=len(report.warnings)))
        else:
            self.summary.setText(T("logs.summary.ok", pbo=item["name"], warnings=len(report.warnings)))
        self.summary.setTextColor(tokens.color(role), tokens.color(role))
        log = item.get("log")
        self.open_btn.setEnabled(bool(log) and Path(log).exists())
        if self.full.isChecked():
            if log and Path(log).exists():
                self.view.setPlainText(Path(log).read_text(encoding="utf-8", errors="replace"))
            else:
                self.view.setPlainText(T("logs.no_file", path=log or "—"))
            return
        if report is None:
            self.view.setPlainText(item.get("error", ""))
            return
        parts: List[str] = []
        root = Path(report.source) if report.source else None
        self._mark_targets = []
        for title, rows, level in ((T("logs.section.errors"), report.errors, "error"),
                                   (T("logs.section.warnings"), report.warnings, "warning"),
                                   (T("logs.section.infos"), report.infos, "info")):
            if rows:
                parts.append('<span style="color:%s;"><b>%s (%d)</b></span>'
                             % (tokens.color(level), html.escape(title), len(rows)))
                # «[ERROR] файл: где. В чём» — имя файла ссылкой на папку исходника
                parts += [finding_html(level, (root / src) if root else Path(src), text,
                                       self._mark_html(report, root, (src, text)))
                          for src, text in rows]
                parts.append("")
        if report.decisions:
            parts.append("<b>%s</b>" % html.escape(T("logs.section.decisions")))
            parts += [html.escape(d) for d in report.decisions]
        if not report.errors and not report.warnings:
            parts.insert(0, '<span style="color:%s;">%s</span>'
                         % (tokens.color("success"), html.escape(T("logs.clean"))))
        self.view.clear()
        self.view.appendHtml("".join("<div>%s</div>" % (p or "&#8203;") for p in parts))
        self.view.moveCursor(self.view.textCursor().MoveOperation.Start)
        # пришли по [W: n] — предупреждения могут быть ниже длинного списка ошибок
        if self.focus == "warning" and report.errors and report.warnings:
            self._scroll_to(T("logs.section.warnings"))

    def _mark_html(self, report, root: Optional[Path], row: tuple) -> str:
        """Ссылка «Пометить на модели» у находки, которую командная строка умеет пометить; после — итог."""
        code = report.marks.get(row)
        if not code or root is None:
            return ""
        path = root / row[0]
        state = self._mark_state.get((str(path), code))
        if state and state[0]:
            return '%s<span style="color:%s;">%s</span>' % (
                _UNDER, tokens.color("success"), html.escape(T("logs.marked", name=state[0])))
        if state:
            return '%s<span style="color:%s;">%s</span>' % (
                _UNDER, tokens.color("error"), html.escape(T("logs.mark_failed", text=state[1])))
        self._mark_targets.append((path, code))
        return _UNDER + act_link("mark:%d" % (len(self._mark_targets) - 1), T("logs.mark"))

    def _on_action(self, action: str) -> None:
        if not action.startswith("mark:"):
            return
        from PySide6.QtWidgets import QApplication
        path, code = self._mark_targets[int(action[len("mark:"):])]
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            name, why = pb.mark(path, code, getattr(self.parent(), "settings_file", None))
        finally:
            QApplication.restoreOverrideCursor()
        self._mark_state[(str(path), code)] = (name, why)
        bar = self.view.verticalScrollBar()
        keep, self.focus = bar.value(), ""
        self._show()
        bar.setValue(keep)                        # строка с итогом остаётся там, где кликнули

    def _scroll_to(self, title: str) -> None:
        """Заголовок раздела — первой строкой видимой области."""
        doc = self.view.document()
        found = doc.find(title)
        if found.isNull():
            return
        bar = self.view.verticalScrollBar()
        bar.setValue(bar.maximum())                  # с конца назад: строка встаёт наверх
        self.view.setTextCursor(found)
        self.view.ensureCursorVisible()
        cursor = self.view.textCursor()
        cursor.clearSelection()
        self.view.setTextCursor(cursor)

    def _open_file(self) -> None:
        item = self._current()
        if item and item.get("log") and Path(item["log"]).exists():
            os.startfile(item["log"])  # noqa: S606


def _role(item: dict) -> str:
    report = item.get("report")
    if report is None or report.errors:
        return "error"
    return "warning" if report.warnings else "success"


def _qcolor(role: str):
    from PySide6.QtGui import QColor
    return QColor(tokens.color(role))
