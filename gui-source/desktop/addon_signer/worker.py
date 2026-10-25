# -*- coding: utf-8 -*-
"""Работа [KR] Addon Signer — через командную строку AddonSigner.exe.

Окно само PBO не читает и не подписывает (юзер 24.10.2026: окно — только
показ, работа — в командной строке). Здесь — запуск `AddonSigner.exe` и разбор
его событий: собранное окно зовёт exe рядом с собой, из исходников —
`python -m pbo_kit.signer_cli`. Память о проверках (по размеру и дате PBO и
подписи) живёт в файле, который ведёт сама командная строка.
"""
from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import List, Optional, Tuple

from PySide6.QtCore import QThread, Signal

HERE = Path(__file__).resolve().parent
KITS = HERE.parents[1] / "kits"

#: состояния подписи — те же слова, что отдаёт командная строка
OK, STALE, MISSING, FOREIGN, BROKEN = "ok", "stale", "missing", "foreign", "broken"
#: что кнопка «Подписать» подписывает заново
TO_SIGN = (MISSING, STALE)


def cli_command() -> List[str]:
    if getattr(sys, "frozen", False):
        # поставка — одна папка: командная строка лежит рядом с окном
        return [str(Path(sys.executable).resolve().parent / "AddonSigner.exe")]
    return [sys.executable, "-m", "pbo_kit.signer_cli"]


def _env() -> dict:
    return dict(os.environ, PYTHONIOENCODING="utf-8")


def _flags() -> int:
    return getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0) | getattr(subprocess, "CREATE_NO_WINDOW", 0)


def run_events(args: List[str]) -> List[dict]:
    """Короткий вызов (ключ, создание ключа): дождаться и вернуть события."""
    proc = subprocess.run(cli_command() + args + ["--json"], cwd=str(KITS) if KITS.is_dir() else None,
                          stdin=subprocess.DEVNULL, capture_output=True, env=_env(), creationflags=_flags())
    events = []
    for line in proc.stdout.decode("utf-8", "replace").splitlines():
        try:
            events.append(json.loads(line))
        except ValueError:
            continue
    return events


def key_info(path: str) -> dict:
    """{name, private, error}: error — "missing", текст ошибки или пусто."""
    for ev in run_events(["key-info", path]):
        if ev.get("event") == "key":
            return ev
    return {"name": "", "private": False, "error": "командная строка не ответила"}


def create_key(name: str, folder: Path) -> Tuple[Path, Path]:
    """Создать пару ключей; ошибка — RuntimeError с текстом от командной строки."""
    events = run_events(["create-key", name, str(folder)])
    for ev in events:
        if ev.get("event") == "created":
            return Path(ev["prv"]), Path(ev["pub"])
    problem = next((ev.get("text") for ev in events if ev.get("event") == "problem"), "")
    raise RuntimeError(problem or "командная строка не ответила")


def bisign_path(pbo: Path, key_name: str) -> Path:
    return Path(str(pbo) + "." + key_name + ".bisign")


def backup_dir(root: Optional[Path] = None) -> Path:
    """Папка для прежних подписей одного захода: `<root>\\<дата-время>`."""
    root = root or Path.home() / ".kr_devtoolkit" / "sign_backup"
    return root / time.strftime("%Y%m%d-%H%M%S")


class Job(QThread):
    """Одна работа командной строки: `scan` (найти и проверить) или `sign`."""

    found = Signal(list)                  # [str] — найденные PBO по порядку
    state = Signal(str, str, str)         # PBO, состояние, подробность
    signatures = Signal(str, list)        # PBO, имена ключей подписей (без выбранного ключа)
    progress = Signal(int, int)           # сделано, всего
    failed = Signal(str)                  # ключ не читается и подобное — до начала работы
    backed_up = Signal(str)               # копия прежней подписи

    def __init__(self, mode: str, cache_path: Optional[Path], key_path: str = "",
                 folders: Optional[List[str]] = None,
                 items: Optional[List[str]] = None,
                 backup: Optional[Path] = None, parent=None):
        super().__init__(parent)
        self.mode, self.cache_path, self.key_path = mode, cache_path, key_path
        self.folders = folders or []
        self.items = items or []
        self.backup = backup
        self.proc: Optional[subprocess.Popen] = None
        self._jobs_file: Optional[str] = None

    def _args(self) -> List[str]:
        args = [self.mode, "--json"]
        if self.key_path:
            args += ["--key", self.key_path]
        if self.cache_path:
            args += ["--cache", str(self.cache_path)]
        if self.mode == "scan":
            return args + list(self.folders)
        import tempfile
        fd, self._jobs_file = tempfile.mkstemp(prefix="kr_sign_", suffix=".json")
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(list(self.items), fh, ensure_ascii=False)
        args += ["--jobs-file", self._jobs_file]
        if self.backup:
            args += ["--backup", str(self.backup)]
        return args

    def run(self) -> None:
        if self.mode == "scan" and not self.folders:
            self.found.emit([])
            return
        try:
            self.proc = subprocess.Popen(cli_command() + self._args(),
                                         cwd=str(KITS) if KITS.is_dir() else None,
                                         stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                         stderr=subprocess.DEVNULL, env=_env(), creationflags=_flags())
        except OSError as exc:
            self.failed.emit(str(exc))
            return
        try:
            for raw in self.proc.stdout:
                try:
                    ev = json.loads(raw.decode("utf-8"))
                except ValueError:
                    continue
                kind = ev.get("event")
                if kind == "found":
                    self.found.emit(list(ev.get("pbos", [])))
                elif kind == "state":
                    self.state.emit(ev["pbo"], ev["state"], ev.get("detail", ""))
                elif kind == "signatures":
                    self.signatures.emit(ev["pbo"], list(ev.get("names", [])))
                elif kind == "progress":
                    self.progress.emit(int(ev.get("done", 0)), int(ev.get("total", 0)))
                elif kind == "backed_up":
                    self.backed_up.emit(ev["path"])
                elif kind == "problem":
                    self.failed.emit(ev.get("text", ""))
            self.proc.wait()
        finally:
            if self._jobs_file:
                try:
                    os.remove(self._jobs_file)
                except OSError:
                    pass

    def requestInterruption(self) -> None:                             # noqa: N802 — как у QThread
        """Мягкая остановка: Ctrl+Break процессу — он доделает текущий PBO и выйдет."""
        super().requestInterruption()
        if self.proc is not None and self.proc.poll() is None:
            try:
                os.kill(self.proc.pid, signal.CTRL_BREAK_EVENT)
            except (OSError, AttributeError):
                self.proc.terminate()
