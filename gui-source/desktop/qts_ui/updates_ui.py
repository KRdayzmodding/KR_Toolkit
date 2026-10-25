# -*- coding: utf-8 -*-
r"""Окна обновления тулз — общие для всех окон [KR] DevToolkit.

Работу делает DevToolkit.exe (toolkit_kit, `update check | install | dismiss`):
окно только показывает (юзер 24.10.2026). Решения юзера: одно общее окно на
все тулзы, у которых вышла новая версия; устаревшая версия (ниже минимальной
или выбранная вручную старая) — предупреждение при каждом запуске, без
запрета работать. Вид — одобренный прототип.

В тулзе с окном — одна строка после показа главного окна:

    updates_ui.watch(window, "ProjectBuilder")

Установленный тулкит: <root>\tools\<тулза>\<версия>\<exe>, DevToolkit.exe —
запускалка в <root>. Из исходников — `python -m toolkit_kit`; установку и
источник для проверки задают KR_UPDATE_ROOT, KR_UPDATE_SOURCE, KR_UPDATE_KEY
(ключ принимается только из исходников).
"""
from __future__ import annotations

import html
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Callable, Dict, List, Optional

from PySide6.QtCore import QThread, QTimer, Qt, Signal
from PySide6.QtWidgets import QHBoxLayout, QVBoxLayout
from qfluentwidgets import (BodyLabel, CaptionLabel, FluentIcon, IconWidget, ListWidget, MessageBoxBase,
                            PrimaryPushButton, ProgressBar, PushButton, SubtitleLabel, TextBrowser)

from qts_ui import tokens
from qts_ui.theme import ThemedDialog

KITS = Path(__file__).resolve().parents[2] / "kits"

TEXT = {
    "title": "Обновление [KR] DevToolkit",
    "available": "Доступны обновления: %d",
    "note": "%s · скачать %s · ставится в фоне — открытые тулзы продолжают работать",
    "channel.main": "Основной канал",
    "channel.test": "Тестовый канал",
    "hint": "Все версии и откат — в лаунчере, вкладка «Версии».",
    "update": "Обновить",
    "later": "Позже",
    "hide": "Скрыть",
    "close": "Закрыть",
    "downloading": "Скачивание: %s %s — %s из %s",
    "done.title": "Обновлено: %d",
    "done.note": "Новые версии включатся при следующем запуске каждой тулзы.",
    "done.running": "%s сейчас открыт — работает прежняя версия %s.",
    "restart": "Перезапустить %s",
    "failed": "Не обновлено: %s",
    "outdated.title": "%s %s устарел",
    "outdated.pinned": "Эту версию вы выбрали сами на вкладке «Версии». Актуальная — %s.",
    "outdated.min": "Версия ниже поддерживаемой (%s). Причина от разработчиков: %s",
    "outdated.min.noreason": "Версия ниже поддерживаемой (%s).",
    "outdated.every": "Это окно будет появляться при каждом запуске, пока стоит %s.",
    "outdated.update": "Обновить до %s",
    "outdated.keep": "Продолжить с %s",
    "test": "тест",
    "mb": "%.1f МБ",
    "kb": "%d КБ",
}


def size_text(count: int) -> str:
    return TEXT["mb"] % (count / 1048576.0) if count >= 1048576 else TEXT["kb"] % max(1, round(count / 1024.0))


# ====================================================================== где установка
def install_root(exe: Optional[Path] = None) -> Optional[Path]:
    r"""<root>\tools\<тулза>\<версия>\<exe> → <root>; иначе (не установлено установщиком) — None."""
    exe = Path(exe or sys.executable).resolve()
    if len(exe.parents) > 3 and exe.parents[2].name.lower() == "tools":
        return exe.parents[3]
    return None


def tool_name(exe: Optional[Path] = None) -> str:
    """Имя тулзы по exe: ProjectBuilder_GUI.exe → ProjectBuilder."""
    stem = Path(exe or sys.executable).stem
    return stem[:-4] if stem.lower().endswith("_gui") else stem


def command() -> Optional[List[str]]:
    """Как звать DevToolkit.exe: запускалку установки или исходники; без установки — None."""
    if getattr(sys, "frozen", False):
        root = install_root()
        return [str(root / "DevToolkit.exe")] if root else None
    args = [sys.executable, "-m", "toolkit_kit"]
    return args if os.environ.get("KR_UPDATE_ROOT") else None


def _extra() -> List[str]:
    out = []
    for env, flag in (("KR_UPDATE_ROOT", "--root"), ("KR_UPDATE_SOURCE", "--source"), ("KR_UPDATE_KEY", "--public-key")):
        if os.environ.get(env):
            out += [flag, os.environ[env]]
    return out


class UpdateCall(QThread):
    """Один вызов `DevToolkit.exe update …`: события — по ходу, итог — списком."""

    event = Signal(dict)
    finished_events = Signal(list, int)

    def __init__(self, args: List[str], parent=None):
        super().__init__(parent)
        self.args = args

    def run(self) -> None:
        cmd = command()
        if cmd is None:
            self.finished_events.emit([{"event": "problem", "text": "тулкит не установлен установщиком"}], 1)
            return
        events = []
        try:
            proc = subprocess.Popen(cmd + ["update"] + self.args + ["--json"] + _extra(),
                                    cwd=str(KITS) if KITS.is_dir() else None, stdin=subprocess.DEVNULL,
                                    stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                    env=dict(os.environ, PYTHONIOENCODING="utf-8"),
                                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        except OSError as exc:
            self.finished_events.emit([{"event": "problem", "text": str(exc)}], 1)
            return
        for raw in proc.stdout:
            try:
                ev = json.loads(raw.decode("utf-8"))
            except ValueError:
                continue
            events.append(ev)
            self.event.emit(ev)
        self.finished_events.emit(events, proc.wait())


def report_from(events: List[dict]) -> Optional[dict]:
    """События check → {tools: {имя: …}, summary: {…}}; не ответил — None."""
    summary = next((e for e in events if e.get("event") == "summary"), None)
    if summary is None:
        return None
    return {"tools": {e["name"]: e for e in events if e.get("event") == "tool"}, "summary": summary}


# ====================================================================== что нового
def changes_html(entries: List[dict]) -> str:
    out = []
    for v in entries:
        tag = ' <span style="color:%s;">%s</span>' % (tokens.color("warning"), TEXT["test"]) \
            if v.get("channel") == "test" else ""
        out.append("<p style='margin:0 0 4px 0;'><b>%s</b> <span style='color:%s;'>· %s</span>%s</p>"
                   % (html.escape(v["version"]), tokens.color("text_dim"), html.escape(v.get("date", "")), tag))
        out.append("<ul style='margin-top:0;'>%s</ul>"
                   % "".join("<li>%s</li>" % html.escape(c) for c in v.get("changes", [])))
    return "".join(out)


class UpdateDialog(ThemedDialog):
    """Одно окно на все тулзы, у которых есть новая версия: слева список, справа что нового."""

    def __init__(self, tools: List[dict], channel: str, current: str = "", dismissable: bool = True,
                 parent=None):
        super().__init__(parent)
        self.tools, self.current, self.dismissable = tools, current, dismissable
        self.call: Optional[UpdateCall] = None
        self.restart_wanted = False
        self.setWindowTitle(TEXT["title"])
        self.resize(*tokens.WIN_L)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(tokens.SPACE_L, tokens.SPACE_M, tokens.SPACE_L, tokens.SPACE_M)
        outer.setSpacing(tokens.SPACE_S)
        self.title = SubtitleLabel(TEXT["available"] % len(tools), self)
        outer.addWidget(self.title)
        self.note = CaptionLabel(TEXT["note"] % (TEXT["channel." + channel],
                                                 size_text(sum(t.get("download", 0) for t in tools))), self)
        self.note.setWordWrap(True)
        self.note.setTextColor(tokens.color("text_dim"), tokens.color("text_dim"))
        outer.addWidget(self.note)

        body = QHBoxLayout()
        body.setSpacing(tokens.SPACE_M)
        self.list = ListWidget(self)
        self.list.setFixedWidth(250)
        for t in tools:
            self.list.addItem(self._row(t, ""))
        body.addWidget(self.list)
        self.view = TextBrowser(self)
        body.addWidget(self.view, 1)
        outer.addLayout(body, 1)
        self.list.currentRowChanged.connect(self._show)
        self.list.setCurrentRow(0)

        self.progress = ProgressBar(self)
        self.progress.setRange(0, 1000)
        self.progress.hide()
        outer.addWidget(self.progress)
        self.status = CaptionLabel(TEXT["hint"], self)
        self.status.setTextColor(tokens.color("text_dim"), tokens.color("text_dim"))
        foot = QHBoxLayout()
        foot.addWidget(self.status, 1)
        # порядок как у диалогов библиотеки: главная кнопка слева, отказ справа (п. 20)
        self.go = PrimaryPushButton(TEXT["update"], self)
        self.later = PushButton(TEXT["later"], self)
        # один обработчик на оба шага: «Обновить», после установки — «Перезапустить». Перецеплять
        # сигнал голым disconnect() нельзя — он снимает и связи библиотеки, и закрытие окна после
        # установки падало в shiboken (0xc0000005, юзер 25.10.2026: «выключается и не перезапускается»)
        self.installed = False
        self.go.clicked.connect(lambda: self._restart() if self.installed else self.start())
        self.later.clicked.connect(self._later)
        foot.addWidget(self.go)
        foot.addWidget(self.later)
        outer.addLayout(foot)
        self.go.setDefault(True)
        self.go.setFocus()

    @staticmethod
    def _row(tool: dict, mark: str) -> str:
        return "%s%s    %s → %s" % (mark + "  " if mark else "", tool["name"], tool.get("installed") or "—",
                                     tool["latest"])

    def _show(self, row: int) -> None:
        if 0 <= row < len(self.tools):
            self.view.setHtml(changes_html(self.tools[row].get("changes", [])))

    def _later(self) -> None:
        if self.call is None and self.dismissable:
            UpdateCall(["dismiss"], self.parent()).start()       # до следующей версии не спрашивать
        self.reject()

    # -------- установка
    def start(self) -> None:
        self.go.setEnabled(False)
        self.later.setText(TEXT["hide"])            # ставится в фоне — окно можно убрать
        self.progress.setValue(0)
        self.progress.show()
        self.total = {t["name"]: max(1, t.get("download", 0)) for t in self.tools}
        # не self.done: done() — метод QDialog, через него идут accept() и reject(); словарь на его
        # месте ронял закрытие окна после установки в shiboken (0xc0000005, юзер 25.10.2026)
        self.downloaded: Dict[str, int] = {}
        self.call = UpdateCall(["install"] + [t["name"] for t in self.tools], self)
        self.call.event.connect(self._event)
        self.call.finished_events.connect(self._finished)
        self.call.start()

    def _event(self, ev: dict) -> None:
        kind = ev.get("event")
        if kind == "progress":
            self.total[ev["tool"]] = max(1, int(ev["total"]))
            self.downloaded[ev["tool"]] = int(ev["done"])
            done, total = sum(self.downloaded.values()), sum(self.total.values())
            self.progress.setValue(int(1000 * done / max(1, total)))
            self.status.setText(TEXT["downloading"] % (ev["tool"], ev["version"], size_text(done), size_text(total)))
        elif kind == "installed":
            for row, t in enumerate(self.tools):
                if t["name"] == ev["tool"]:
                    self.list.item(row).setText(self._row(t, "✓"))

    def _finished(self, events: List[dict], code: int) -> None:
        # поток шлёт итог последней строкой run() и ещё не вышел: дождаться, прежде чем отпускать
        call, self.call = self.call, None
        if call is not None:
            call.wait()
        self.progress.hide()
        problem = next((e.get("text") for e in events if e.get("event") == "problem"), "")
        if code != 0:
            self.status.setText(TEXT["failed"] % (problem or code))
            self.status.setTextColor(tokens.color("error"), tokens.color("error"))
            self.go.setEnabled(True)
            self.later.setText(TEXT["close"])
            return
        self.title.setText(TEXT["done.title"] % len(self.tools))
        self.note.setText(TEXT["done.note"])
        self.later.setText(TEXT["close"])
        mine = next((t for t in self.tools if t["name"] == self.current), None)
        if mine is None:
            self.status.setText("")
            self.go.hide()
            return
        self.status.setText(TEXT["done.running"] % (mine["name"], mine.get("installed") or "—"))
        self.status.setTextColor(tokens.color("warning"), tokens.color("warning"))
        self.go.setText(TEXT["restart"] % mine["name"])
        self.go.setEnabled(True)
        self.installed = True

    def _restart(self) -> None:
        self.restart_wanted = True
        self.accept()

    def reject(self) -> None:
        # идёт установка — окно прячется, а установка доходит до конца
        if self.call is not None:
            self.hide()
            return
        super().reject()


# ====================================================================== устаревшая версия
class OutdatedBox(MessageBoxBase):
    """При каждом запуске тулзы, пока стоит устаревшая версия. Работать не мешает."""

    def __init__(self, tool: dict, parent):
        super().__init__(parent)
        head = QHBoxLayout()
        icon = IconWidget(FluentIcon.INFO, self)
        icon.setFixedSize(24, 24)
        head.addWidget(icon, 0, Qt.AlignTop)
        head.addWidget(SubtitleLabel(TEXT["outdated.title"] % (tool["name"], tool["installed"]), self), 1)
        self.viewLayout.addLayout(head)
        if tool.get("below_min"):
            why = (TEXT["outdated.min"] % (tool["min"], tool["min_reason"]) if tool.get("min_reason")
                   else TEXT["outdated.min.noreason"] % tool["min"])
        else:
            why = TEXT["outdated.pinned"] % tool["latest"]
        text = BodyLabel(why, self)
        text.setWordWrap(True)
        self.viewLayout.addWidget(text)
        hint = CaptionLabel(TEXT["outdated.every"] % tool["installed"], self)
        hint.setWordWrap(True)
        hint.setTextColor(tokens.color("text_dim"), tokens.color("text_dim"))
        self.viewLayout.addWidget(hint)
        self.widget.setMinimumWidth(440)
        self.yesButton.setText(TEXT["outdated.update"] % tool["latest"])
        self.cancelButton.setText(TEXT["outdated.keep"] % tool["installed"])


# ====================================================================== при запуске тулзы
def restart(tool: str, window) -> None:
    """Запустить тулзу заново через запускалку (уже новой версией) и закрыть это окно."""
    root = install_root()
    if root is not None:
        exe = root / ("DevToolkit_GUI.exe" if tool == "DevToolkit" else "%s_GUI.exe" % tool)
        subprocess.Popen([str(exe)], cwd=str(root), close_fds=True,
                         creationflags=getattr(subprocess, "DETACHED_PROCESS", 0))
    window.close()


def offer(report: dict, tool: str, window, on_done: Optional[Callable[[], None]] = None) -> None:
    """Что показать при запуске: «устарел» для этой тулзы, иначе общее окно новых версий."""
    me = report["tools"].get(tool)
    summary = report["summary"]
    if me is not None and me.get("warn") and me.get("latest"):
        box = OutdatedBox(me, window)
        if not box.exec():
            return
        targets, dismissable = [dict(me, changes=me.get("changes") or [])], False
    else:
        targets = [report["tools"][n] for n in summary.get("notify", []) if n in report["tools"]]
        dismissable = True
    if not targets:
        return
    dialog = UpdateDialog(targets, summary.get("channel", "main"), current=tool, dismissable=dismissable,
                          parent=window)
    dialog.exec()
    if dialog.restart_wanted:
        restart(tool, window)
    if on_done is not None:
        on_done()


def watch(window, tool: str) -> Optional[UpdateCall]:
    """После показа главного окна: проверить в фоне и, если есть что, показать — одно окно."""
    if command() is None:
        return None                         # не установлено установщиком (разработка) — молчим
    call = UpdateCall(["check"], window)

    def done(events: List[dict], _code: int) -> None:
        call.wait()
        report = report_from(events)
        if report is not None:
            # окно — из очереди событий, а не изнутри сигнала потока: модальный цикл внутри
            # сигнала, а потом перезапуск (закрытие окна-родителя потока) роняли тулзу в shiboken
            # (0xc0000005, юзер 25.10.2026: «выключается и не перезапускается»)
            QTimer.singleShot(0, lambda: offer(report, tool, window))
    call.finished_events.connect(done)
    call.start()
    window._update_watch = call             # держим поток живым, пока он идёт
    return call
