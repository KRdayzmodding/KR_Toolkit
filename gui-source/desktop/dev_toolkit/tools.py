# -*- coding: utf-8 -*-
r"""Тулзы, которые запускает лаунчер, и где лежат их exe.

Поставка — одна папка, все exe рядом и одна общая runtime (юзер 24.10.2026,
`desktop/build_bundle.py`):

    KR DevToolkit\DevToolkit_GUI.exe    — лаунчер
    KR DevToolkit\ProjectBuilder_GUI.exe …
    KR DevToolkit\runtime\versions.json — название, версия, коммит каждого exe

Лаунчер ищет тулзы рядом с собой, поэтому папку можно переносить целиком.
Из исходников — в `<репозиторий>\dist\KR DevToolkit`, из worktree — в dist
основного репозитория.
"""
from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

HERE = Path(__file__).resolve().parent
BUNDLE = "KR DevToolkit"
VERSIONS = Path("runtime") / "versions.json"


@dataclass(frozen=True)
class Tool:
    key: str
    #: exe в папке поставки
    exe: str
    #: имя значка FluentIcon
    icon: str
    #: раздел лаунчера: EDIT — сборка и редакторы, BATCH — массовая работа с файлами
    group: str


EDIT, BATCH = "edit", "batch"

#: юзер 24.10.2026: тулзы для массовой работы с файлами — отдельной областью
TOOLS = (
    Tool("build", "ProjectBuilder_GUI.exe", "SEND", EDIT),
    Tool("textures", "TextureEditor_GUI.exe", "PALETTE", EDIT),
    Tool("imageset", "ImagesetEditor_GUI.exe", "TILES", EDIT),
    Tool("texconv", "TextureConverter_GUI.exe", "PHOTO", BATCH),
    Tool("models", "ModelConverter_GUI.exe", "IOT", BATCH),
    Tool("debin", "DeBinarizer_GUI.exe", "CODE", BATCH),
    Tool("pbo", "PboUnpacker_GUI.exe", "ZIP_FOLDER", BATCH),
    Tool("anm", "AnmConverter_GUI.exe", "MOVIE", BATCH),
    Tool("sound", "SoundConverter_GUI.exe", "MUSIC", BATCH),
    Tool("sign", "AddonSigner_GUI.exe", "CERTIFICATE", BATCH),
)


def dist_root() -> Path:
    r"""Папка поставки: корень установки (<root>\tools\<тулза>\<версия>\ — запускалки в <root>),
    иначе — где лежит собранный лаунчер; из исходников — dist репозитория."""
    if getattr(sys, "frozen", False):
        from qts_ui.updates_ui import install_root
        return install_root() or Path(sys.executable).resolve().parent
    root = HERE.parents[1]
    for candidate in (root / "dist" / BUNDLE, root.parent.parent / "dist" / BUNDLE):   # worktree
        if candidate.is_dir():
            return candidate
    return root / "dist" / BUNDLE


def exe_path(tool: Tool, root: Optional[Path] = None) -> Path:
    return (root or dist_root()) / tool.exe


def launch(tool: Tool, root: Optional[Path] = None) -> Path:
    """Запустить отдельным процессом: закрытие лаунчера тулзу не закрывает."""
    exe = exe_path(tool, root)
    flags = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    subprocess.Popen([str(exe)], cwd=str(exe.parent), creationflags=flags, close_fds=True)
    return exe


def read_version(tool: Tool, root: Optional[Path] = None) -> Optional[dict]:
    """Версия из runtime\\versions.json (пишет сборщик): name, version, commit, built. Нет — None."""
    try:
        data = json.loads(((root or dist_root()) / VERSIONS).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    info = data.get(Path(tool.exe).stem) if isinstance(data, dict) else None
    return info if isinstance(info, dict) and info.get("version") else None


def available(root: Optional[Path] = None) -> List[Tool]:
    return [t for t in TOOLS if exe_path(t, root).is_file()]
