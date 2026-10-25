# -*- coding: utf-8 -*-
"""Работа [KR] Imageset Editor — через командную строку ImagesetEditor.exe.

Окно само imageset не разбирает и не пишет, текстуры не декодирует и ссылки
не ищет (юзер 24.10.2026: окно — только показ, работа — в командной строке).
Здесь — вызовы `ImagesetEditor.exe … --json` и разбор их событий: собранное
окно зовёт exe рядом с собой, из исходников — `python -m texture_kit`.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import List, Optional, Tuple

HERE = Path(__file__).resolve().parent
KITS = HERE.parents[1] / "kits"

#: корень игровых путей для командной строки; тест подменяет (по умолчанию — P:\)
PROJECT_ROOT: Optional[str] = None


def cli_command() -> List[str]:
    if getattr(sys, "frozen", False):
        # поставка — одна папка: командная строка лежит рядом с окном
        return [str(Path(sys.executable).resolve().parent / "ImagesetEditor.exe")]
    return [sys.executable, "-m", "texture_kit"]


def _root_args() -> List[str]:
    return ["--project-root", PROJECT_ROOT] if PROJECT_ROOT else []


def call(args: List[str]) -> List[dict]:
    """Вызов командной строки: дождаться и вернуть события."""
    try:
        proc = subprocess.run(cli_command() + args + ["--json"], cwd=str(KITS) if KITS.is_dir() else None,
                              stdin=subprocess.DEVNULL, capture_output=True,
                              env=dict(os.environ, PYTHONIOENCODING="utf-8"),
                              creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except OSError as exc:
        return [{"event": "problem", "text": "%s: %s" % (cli_command()[0], exc)}]
    events = []
    for line in proc.stdout.decode("utf-8", "replace").splitlines():
        try:
            events.append(json.loads(line))
        except ValueError:
            continue
    if not events:
        tail = proc.stderr.decode("utf-8", "replace").strip().splitlines()
        events.append({"event": "problem", "text": tail[-1] if tail else "нет ответа от %s" % cli_command()[0]})
    return events


def _problem(events: List[dict]) -> str:
    return next((ev.get("text", "") for ev in events if ev.get("event") == "problem"), "") or \
        "нет ответа от %s" % cli_command()[0]


def read(path: Path) -> dict:
    """Imageset целиком (как событие imageset); не читается — ValueError с причиной."""
    events = call(["read", str(path)] + _root_args())
    for ev in events:
        if ev.get("event") == "imageset":
            return ev
    raise ValueError(_problem(events))


def write(path: Path, data: dict, backup_root: Optional[Path]) -> str:
    """Записать; прежний файл — копией в backup_root (если задан). Вернуть путь копии или ""."""
    fd, source = tempfile.mkstemp(prefix="kr_imageset_", suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False)
        args = ["write", str(path), "--from", source] + _root_args()
        if backup_root is not None:
            args += ["--backup-root", str(backup_root)]
        events = call(args)
    finally:
        try:
            os.remove(source)
        except OSError:
            pass
    for ev in events:
        if ev.get("event") == "saved":
            return ev.get("backup") or ""
    raise OSError(_problem(events))


def pixels(texture: Path):
    """Текстура как RGBA-массив numpy; не читается — None."""
    import numpy as np
    fd, out = tempfile.mkstemp(prefix="kr_pixels_", suffix=".npy")
    os.close(fd)
    try:
        events = call(["pixels", str(texture), "--out", out])
        if not any(ev.get("event") == "pixels" for ev in events):
            return None
        return np.load(out, allow_pickle=False)
    except (OSError, ValueError):
        return None
    finally:
        try:
            os.remove(out)
        except OSError:
            pass


def game_path(file: Path) -> Optional[str]:
    """Путь, по которому движок ищет файл; вне P: — None."""
    for ev in call(["game-path", str(file)] + _root_args()):
        if ev.get("event") == "path":
            return ev.get("game")
    return None


def refs(root: Path, set_name: str, sprite: Optional[str]) -> List[Tuple[str, int]]:
    """Файлы со ссылками на спрайт (sprite None — на любой спрайт сета) и их число."""
    args = ["refs", str(root), "--set", set_name]
    if sprite is not None:
        args += ["--sprite", sprite]
    return [(ev["file"], int(ev["count"])) for ev in call(args) if ev.get("event") == "ref"]


def to_edds(source: Path) -> Path:
    """Картинка → EDDS рядом с ней; прежний EDDS — копией в бэкап. Отказ — RuntimeError."""
    events = call(["edds", str(source), "--overwrite"])
    for ev in events:
        if ev.get("event") == "file" and ev.get("state") == "done":
            return Path(ev["out"])
    failed = next((ev.get("text") for ev in events if ev.get("event") == "file" and ev.get("text")), "")
    raise RuntimeError(failed or _problem(events))
