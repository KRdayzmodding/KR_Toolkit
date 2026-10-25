# -*- coding: utf-8 -*-
"""Вкладка «Версии» лаунчера: канал обновлений, версия каждой тулзы, откат.

По одобренному прототипу (юзер 24.10.2026): сверху канал (основной/тестовый),
таблица тулз — что стоит и что с ней; под ней выбор версии выбранной тулзы и
что в этой версии нового; кнопка называет действие («Установить 0.4.0»,
«Откатиться на 0.3.2»), главная — «Обновить всё». Работу делает DevToolkit.exe
(`update check | list | install | channel`), страница только показывает.
"""
from __future__ import annotations

from typing import Callable, Dict, List, Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QAbstractItemView, QHBoxLayout, QHeaderView, QSizePolicy, QTableWidgetItem,
                               QVBoxLayout, QWidget)
from qfluentwidgets import (CaptionLabel, ComboBox, PrimaryPushButton, ProgressBar, PushButton,
                            SegmentedWidget, StrongBodyLabel, TableWidget, TextBrowser)

from qts_ui import tokens, updates_ui
from qts_ui.rows import shrink
from texts import T


def version_key(version: str) -> tuple:
    """Порядок semver — тот же, что у DevToolkit.exe (для надписи «установить»/«откатиться»)."""
    core, _, pre = version.partition("-")
    parts = tuple(int(x) for x in core.split("+")[0].split(".") if x.isdigit())
    ids = tuple((0, int(p), "") if p.isdigit() else (1, 0, p) for p in pre.split(".")) if pre else ()
    return parts + ((0, ids) if pre else (1, ()),)


class VersionsPage(QWidget):
    def __init__(self, on_report: Optional[Callable[[dict], None]] = None, parent=None):
        super().__init__(parent)
        #: лаунчеру — каждый свежий ответ check: версии на карточках и окно обновлений при запуске
        self.on_report = on_report
        self.report: Optional[dict] = None
        self.versions: Dict[str, List[dict]] = {}
        self.names: List[str] = []
        self.call: Optional[updates_ui.UpdateCall] = None
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, tokens.SPACE_XS, 0, 0)
        lay.setSpacing(tokens.SPACE_S)

        top = QHBoxLayout()
        text = QVBoxLayout()
        text.setSpacing(0)
        text.addWidget(StrongBodyLabel(T("versions.channel"), self))
        self.channel_note = shrink(CaptionLabel("", self))
        self.channel_note.setTextColor(tokens.color("text_dim"), tokens.color("text_dim"))
        text.addWidget(self.channel_note)
        top.addLayout(text, 1)
        self.channel = SegmentedWidget(self)
        self.channel.addItem("main", T("versions.main"), lambda *_: self._set_channel("main"))
        self.channel.addItem("test", T("versions.test"), lambda *_: self._set_channel("test"))
        self.channel.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        top.addWidget(self.channel, 0, Qt.AlignVCenter)
        lay.addLayout(top)

        # не установлено установщиком — страница называет причину и что делать (п. 50)
        self.empty = shrink(CaptionLabel(T("versions.not_installed"), self))
        self.empty.setWordWrap(True)
        lay.addWidget(self.empty)

        self.table = TableWidget(self)
        self.table.setColumnCount(3)
        self.table.setHorizontalHeaderLabels([T("versions.col.tool"), T("versions.col.installed"),
                                              T("versions.col.state")])
        self.table.verticalHeader().hide()
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.table.verticalHeader().setDefaultSectionSize(30)
        lay.addWidget(self.table)

        pick = QHBoxLayout()
        self.tool_label = StrongBodyLabel("", self)
        pick.addWidget(self.tool_label, 1)
        self.version = ComboBox(self)
        self.version.setMinimumWidth(240)
        pick.addWidget(self.version)
        lay.addLayout(pick)
        self.view = TextBrowser(self)
        self.view.setMinimumHeight(110)
        lay.addWidget(self.view, 1)

        self.progress = ProgressBar(self)
        self.progress.setRange(0, 1000)
        self.progress.hide()
        lay.addWidget(self.progress)
        self.status = shrink(CaptionLabel("", self))
        self.status.hide()
        lay.addWidget(self.status)
        foot = QHBoxLayout()
        self.install = PushButton("", self)
        self.install.clicked.connect(self._install)
        foot.addWidget(self.install)
        foot.addStretch(1)
        self.all = PrimaryPushButton("", self)
        self.all.clicked.connect(self._update_all)
        foot.addWidget(self.all)
        lay.addLayout(foot)

        self.table.currentCellChanged.connect(lambda row, *_: self._pick(row))
        self.version.currentIndexChanged.connect(lambda *_: self._version())
        self._show_installed(updates_ui.command() is not None)

    # ------------------------------------------------------------------ данные
    def _show_installed(self, installed: bool) -> None:
        self.empty.setVisible(not installed)
        for w in (self.channel, self.table, self.tool_label, self.version, self.view, self.install, self.all):
            w.setVisible(installed)

    def refresh(self, force: bool = False) -> None:
        """check, затем list — одним заходом; ответ — в таблицу и лаунчеру."""
        if updates_ui.command() is None or self.call is not None:
            return
        self._run(["check"] + (["--force"] if force else []), self._checked)

    def _run(self, args: List[str], done) -> None:
        self.call = updates_ui.UpdateCall(args, self)
        self.call.event.connect(self._event)
        self.call.finished_events.connect(lambda events, code: self._done(events, code, done))
        self.call.start()

    def _done(self, events: List[dict], code: int, then) -> None:
        self.call.wait()
        self.call = None
        then(events, code)

    def _checked(self, events: List[dict], code: int) -> None:
        report = updates_ui.report_from(events)
        if report is None:
            self._say(next((e.get("text") for e in events if e.get("event") == "problem"), ""), "error")
            return
        self.report = report
        self.names = sorted(report["tools"])
        self._run(["list"], self._listed)
        if self.on_report is not None:
            self.on_report(report)

    def _listed(self, events: List[dict], code: int) -> None:
        self.versions = {}
        for e in events:
            if e.get("event") == "version":
                self.versions.setdefault(e["tool"], []).append(e)
        self._fill()

    def _fill(self) -> None:
        summary = self.report["summary"]
        channel = summary.get("channel", "main")
        self.channel.blockSignals(True)
        self.channel.setCurrentItem(channel)
        self.channel.blockSignals(False)
        self.channel_note.setText(T("versions.main.note") if channel == "main" else T("versions.test.note"))
        row_was = max(0, self.table.currentRow())
        self.table.setRowCount(len(self.names))
        newer = []
        for row, name in enumerate(self.names):
            st = self.report["tools"][name]
            self.table.setItem(row, 0, QTableWidgetItem(st.get("title") or name))
            self.table.setItem(row, 1, QTableWidgetItem(st.get("installed") or "—"))
            if st.get("below_min"):
                state, color = T("versions.state.below") % st["min"], tokens.color("warning")
            elif st.get("pinned") and st.get("newer"):
                state, color = T("versions.state.pinned") % st["latest"], tokens.color("warning")
            elif st.get("newer"):
                state, color = T("versions.state.newer") % st["latest"], tokens.ACCENT
                newer.append(st)
            else:
                state, color = T("versions.state.current"), tokens.color("text_dim")
            item = QTableWidgetItem(state)
            item.setForeground(QColor(color))
            self.table.setItem(row, 2, item)
        self.table.setFixedHeight(32 + 30 * len(self.names) + 4)
        self.all.setText(T("versions.all") % (len(newer), updates_ui.size_text(sum(t.get("download", 0) for t in newer)))
                         if newer else T("versions.all.none"))
        self.all.setEnabled(bool(newer))
        self.table.selectRow(min(row_was, len(self.names) - 1))
        self._pick(self.table.currentRow())

    def _pick(self, row: int) -> None:
        if self.report is None or not 0 <= row < len(self.names):
            return
        name = self.names[row]
        self.tool_label.setText(T("versions.of") % (self.report["tools"][name].get("title") or name))
        self.version.blockSignals(True)
        self.version.clear()
        for v in self.versions.get(name, []):
            marks = [T(k) for k, on in (("versions.mark.installed", v["installed"]),
                                        ("versions.mark.latest", v["latest"]),
                                        ("versions.mark.test", v["channel"] == "test")) if on]
            self.version.addItem("%s — %s%s" % (v["version"], v["date"], " (%s)" % ", ".join(marks) if marks else ""),
                                 userData=v["version"])
        self.version.setCurrentIndex(0)
        self.version.blockSignals(False)
        self._version()

    def _version(self) -> None:
        row = self.table.currentRow()
        if self.report is None or not 0 <= row < len(self.names):
            return
        name = self.names[row]
        number = self.version.currentData()
        entry = [v for v in self.versions.get(name, []) if v["version"] == number]
        self.view.setHtml(updates_ui.changes_html(entry))
        have = self.report["tools"][name].get("installed")
        # кнопка называет то, что произойдёт (п. 27)
        if number is None or number == have:
            self.install.setText(T("versions.installed") % (have or "—"))
            self.install.setEnabled(False)
        else:
            older = bool(have) and version_key(number) < version_key(have)
            self.install.setText((T("versions.rollback") if older else T("versions.install")) % number)
            self.install.setEnabled(self.call is None)

    # ------------------------------------------------------------------ действия
    def _set_channel(self, channel: str) -> None:
        if self.call is not None:
            return
        self._run(["channel", channel], lambda events, code: self.refresh(force=True))

    def _install(self) -> None:
        row = self.table.currentRow()
        number = self.version.currentData()
        if self.call is not None or not 0 <= row < len(self.names) or number is None:
            return
        self.progress.setValue(0)
        self.progress.show()
        self.install.setEnabled(False)
        self.all.setEnabled(False)
        self._run(["install", "%s@%s" % (self.names[row], number)], self._installed)

    def _event(self, ev: dict) -> None:
        if ev.get("event") == "progress":
            self.progress.setValue(int(1000 * int(ev["done"]) / max(1, int(ev["total"]))))
            self._say(T("versions.downloading") % (ev["tool"], ev["version"]), "text_dim")

    def _installed(self, events: List[dict], code: int) -> None:
        self.progress.hide()
        done = next((e for e in events if e.get("event") == "installed"), None)
        if code != 0 or done is None:
            self._say(T("versions.failed") % next((e.get("text") for e in events if e.get("event") == "problem"), code),
                      "error")
        else:
            self._say((T("versions.done.pinned") if done["pinned"] else T("versions.done")) % (done["tool"], done["version"]),
                      "warning" if done["pinned"] else "success")
        self.refresh(force=True)

    def _update_all(self) -> None:
        if self.report is None:
            return
        tools = [st for st in self.report["tools"].values() if st.get("newer") and not st.get("pinned")]
        if not tools:
            return
        dialog = updates_ui.UpdateDialog(tools, self.report["summary"].get("channel", "main"), current="DevToolkit",
                                         dismissable=False, parent=self.window())
        dialog.exec()
        if dialog.restart_wanted:
            updates_ui.restart("DevToolkit", self.window())
            return
        self.refresh(force=True)

    def _say(self, text: str, role: str) -> None:
        self.status.setText(text)
        self.status.setTextColor(tokens.color(role), tokens.color(role))
        self.status.setVisible(bool(text))
