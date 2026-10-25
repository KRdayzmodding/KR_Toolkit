# -*- coding: utf-8 -*-
"""Что запоминает окно массовой тулзы: входы, настройки, размер окна.

Файл — `%USERPROFILE%\\.kr_devtoolkit\\<тулза>.json`; путь передаётся снаружи
(свод правил интерфейсов, п. 67): тест работает с копией и не трогает
настройки человека.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional


class Store:
    def __init__(self, name: str, defaults: Dict[str, Any], path: Optional[Path] = None):
        from kr_state import state_file
        self.path = Path(path) if path is not None else state_file(name + ".json")
        self.inputs: List[str] = []
        self.options: Dict[str, Any] = dict(defaults)
        self.window: Dict[str, Any] = {}
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        self.inputs = [str(p) for p in data.get("inputs", [])]
        for key, value in dict(data.get("options", {})).items():
            # только известные и того же типа: старый файл не ломает окно
            if key in defaults and type(value) is type(defaults[key]):
                self.options[key] = value
        self.window = dict(data.get("window", {}))

    def save(self) -> None:
        data = {"inputs": self.inputs, "options": self.options, "window": self.window}
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_name(self.path.name + ".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
        os.replace(tmp, self.path)
