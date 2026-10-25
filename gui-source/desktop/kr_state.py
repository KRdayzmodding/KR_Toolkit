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


def theme_name() -> str:
    """Тема окон: одна на все тулзы, выбирается в настройках Project Builder и лежит
    в его файле наборов. По умолчанию тёмная (правило юзера 23.10.2026)."""
    for name in ("project_builder_sets.json", "build_sets.json"):    # новое имя, потом прежнее
        try:
            value = json.loads((STATE_DIR / name).read_text(encoding="utf-8")).get("window", {}).get("theme")
        except (OSError, ValueError, AttributeError):
            continue
        if value in ("auto", "light", "dark"):
            return value
    return "dark"
