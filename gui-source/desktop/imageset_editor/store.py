# -*- coding: utf-8 -*-
"""Что запоминает [KR] Imageset Editor: открытые вкладки, активную, размер окна.

Как VSCode (юзер 23.10.2026): при следующем запуске открываются те же вкладки.
Файл, которого больше нет, просто не открывается — без ошибки на старте.

Путь к файлу передаётся снаружи (свод правил интерфейсов, п. 67): тест работает
с копией и не трогает настройки человека.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

#: имя файла состояния; прежнее (до 24.10.2026) переносится копией — kr_state
STATE_NAME, OLD_NAME = "imageset_editor.json", "imageset_studio.json"


class Store:
    def __init__(self, path: Optional[Path] = None):
        from kr_state import state_file
        self.path = Path(path) if path is not None else state_file(STATE_NAME, OLD_NAME)
        self.tabs: List[str] = []
        self.active: str = ""
        self.last_dir: str = ""
        self.window: Dict[str, Any] = {}
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        self.tabs = [str(p) for p in data.get("tabs", [])]
        self.active = str(data.get("active", ""))
        self.last_dir = str(data.get("last_dir", ""))
        self.window = dict(data.get("window", {}))

    def save(self) -> None:
        data = {"tabs": self.tabs, "active": self.active, "last_dir": self.last_dir,
                "window": self.window}
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_name(self.path.name + ".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
        os.replace(tmp, self.path)
