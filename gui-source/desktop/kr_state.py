# -*- coding: utf-8 -*-
r"""Файлы состояния окон в %USERPROFILE%\.kr_devtoolkit и перенос прежних имён.

24.10.2026 файлы переименованы по названиям тулз (юзер: «krbuild вместо
projectBuilder вызывает путаницу»). Смена конвенции идёт с миграцией (принцип
18): если нового файла ещё нет, а прежний есть — прежний копируется под новое
имя. Прежний остаётся на месте — для старой сборки, если её запустят.

Копирование — при запуске окна (state_file зовут из конструктора), а не при
импорте модуля: иначе тесты писали бы в настоящую папку человека.
"""
from __future__ import annotations

import json
import os
import shutil
from pathlib import Path
from typing import Optional

STATE_DIR = Path.home() / ".kr_devtoolkit"


def state_file(name: str, old: Optional[str] = None, root: Optional[Path] = None) -> Path:
    """Путь к файлу состояния `name`; прежний `old` переносится копией, если нового нет."""
    root = root or STATE_DIR
    new = root / name
    if old and not new.exists() and (root / old).exists():
        try:
            root.mkdir(parents=True, exist_ok=True)
            shutil.copy2(root / old, new)
        except OSError:
            pass                                  # не перенесли — начнём с чистого, не падаем
    return new


THEMES = ("auto", "light", "dark")

#: Тема окон — одна на все тулзы, своим файлом (решение юзера 27.10.2026): выбирается
#: на странице «Настройки» DevToolkit (и в настройках Project Builder — та же), окна
#: следят за файлом и перекрашиваются сразу (qts_ui.theme_sync).
THEME_FILE = "theme.json"


def _read_theme(path: Path) -> Optional[str]:
    try:
        value = json.loads(path.read_text(encoding="utf-8")).get("theme")
    except (OSError, ValueError, AttributeError):
        return None
    return value if value in THEMES else None


def theme_name(root: Optional[Path] = None) -> str:
    """Выбранная тема. По умолчанию тёмная (правило юзера 23.10.2026).

    До 27.10.2026 тема жила в файле наборов Project Builder; своего файла нет —
    выбор берётся оттуда (принцип 18), пока человек не выберет тему заново.
    Чтение ничего не пишет: окна читают тему при каждой записи в папку состояния.
    """
    root = root or STATE_DIR
    value = _read_theme(root / THEME_FILE)
    if value is not None:
        return value
    for name in ("project_builder_sets.json", "build_sets.json"):    # новое имя, потом прежнее
        try:
            old = json.loads((root / name).read_text(encoding="utf-8")).get("window", {}).get("theme")
        except (OSError, ValueError, AttributeError):
            continue
        if old in THEMES:
            return old
    return "dark"


def set_theme(name: str, root: Optional[Path] = None) -> None:
    """Записать выбор; открытые окна подхватят его сами."""
    if name not in THEMES:
        raise ValueError("тема %r, бывает: %s" % (name, ", ".join(THEMES)))
    root = root or STATE_DIR
    path = root / THEME_FILE
    tmp = path.with_name(path.name + ".kr_tmp")
    try:
        root.mkdir(parents=True, exist_ok=True)
        tmp.write_text(json.dumps({"theme": name}), encoding="utf-8")
        os.replace(tmp, path)
    except OSError:
        pass                                      # не записали — окно уже перекрашено, не падаем
