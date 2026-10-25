# -*- coding: utf-8 -*-
"""Вызов командной строки массовой тулзы из окна: процесс, события строками JSON, остановка.

Собранное окно зовёт `<Тулза>.exe` (командную строку) рядом с собой, из исходников —
`python -m batch_kit <подкоманда>`.
"""
from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
from pathlib import Path
from typing import List, Optional

from PySide6.QtCore import QThread, Signal

HERE = Path(__file__).resolve().parent
KITS = HERE.parents[1] / "kits"


def cli_command(spec) -> List[str]:
    if getattr(sys, "frozen", False):
        # поставка — одна папка: командная строка лежит рядом с окном
        return [str(Path(sys.executable).resolve().parent / ("%s.exe" % spec.exe))]
    return [sys.executable, "-m", "batch_kit", spec.cli]


class CliRun(QThread):
    """Один запуск командной строки; каждое событие — сигналом, в конце — код выхода."""

    event = Signal(object)
    failed = Signal(str)          # процесс не запустился или вывел не JSON
    exited = Signal(int)

    def __init__(self, command: List[str], parent=None):
        super().__init__(parent)
        self.command = command
        self.proc: Optional[subprocess.Popen] = None

    def run(self) -> None:
        env = dict(os.environ, PYTHONIOENCODING="utf-8")
        flags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0) | getattr(subprocess, "CREATE_NO_WINDOW", 0)
        try:
            self.proc = subprocess.Popen(self.command, cwd=str(KITS) if KITS.is_dir() else None,
                                         stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                         stderr=subprocess.DEVNULL, env=env, creationflags=flags)
        except OSError as exc:
            self.failed.emit(str(exc))
            self.exited.emit(-1)
            return
        for raw in self.proc.stdout:
            try:
                self.event.emit(json.loads(raw.decode("utf-8")))
            except ValueError:
                self.failed.emit(raw.decode("utf-8", "replace").strip())
        self.exited.emit(self.proc.wait())

    def stop(self) -> None:
        """Мягкая остановка: Ctrl+Break процессу — он доделает текущий файл и выйдет."""
        if self.proc is not None and self.proc.poll() is None:
            try:
                os.kill(self.proc.pid, signal.CTRL_BREAK_EVENT)
            except (OSError, AttributeError):
                self.proc.terminate()
