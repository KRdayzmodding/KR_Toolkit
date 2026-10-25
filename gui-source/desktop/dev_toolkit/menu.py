# -*- coding: utf-8 -*-
"""Меню проводника — через командную строку DevToolkit.exe.

Окно реестр не трогает (юзер 24.10.2026: окно — только показ, работа — в
командной строке): здесь — запуск `DevToolkit.exe menu … --json` в фоне и
разбор его событий. Собранное окно зовёт exe рядом с собой, из исходников —
`python -m toolkit_kit`.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import List

from PySide6.QtCore import QThread, Signal

HERE = Path(__file__).resolve().parent
KITS = HERE.parents[1] / "kits"


def cli_command() -> List[str]:
    if getattr(sys, "frozen", False):
        # поставка — одна папка: командная строка лежит рядом с окном
        return [str(Path(sys.executable).resolve().parent / "DevToolkit.exe")]
    return [sys.executable, "-m", "toolkit_kit"]


class MenuCall(QThread):
    """Один вызов `menu …`: все события разом, когда процесс закончил (он короткий)."""

    done = Signal(list)

    def __init__(self, args: List[str], parent=None):
        super().__init__(parent)
        self.args = args

    def run(self) -> None:
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        try:
            proc = subprocess.run(cli_command() + ["menu"] + self.args + ["--json"],
                                  cwd=str(KITS) if KITS.is_dir() else None, stdin=subprocess.DEVNULL,
                                  capture_output=True, env=dict(os.environ, PYTHONIOENCODING="utf-8"),
                                  creationflags=flags)
        except OSError as exc:
            self.done.emit([{"event": "problem", "text": "%s: %s" % (cli_command()[0], exc)}])
            return
        events = []
        for line in proc.stdout.decode("utf-8", "replace").splitlines():
            try:
                events.append(json.loads(line))
            except ValueError:
                continue
        if not any(ev.get("event") == "done" for ev in events):
            text = proc.stderr.decode("utf-8", "replace").strip().splitlines()
            events.append({"event": "problem", "text": text[-1] if text else "нет ответа от %s" % cli_command()[0]})
        self.done.emit(events)
