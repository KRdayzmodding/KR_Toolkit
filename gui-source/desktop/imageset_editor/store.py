# -*- coding: utf-8 -*-
"""Что запоминает Imageset Editor: открытые вкладки, активную, размер окна и настройки
(автосохранение, шагов отмены — юзер 25.10.2026).

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

import history

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
        #: сохранять само (вкладка, уход из окна, закрытие); выключено — Ctrl+S и вопрос при закрытии.
        #: По умолчанию выключено (юзер 25.10.2026)
        self.autosave: bool = False
        #: шагов отмены на файл, они же — история между сессиями
        self.history: int = history.LIMIT_DEFAULT
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        self.tabs = [str(p) for p in data.get("tabs", [])]
        self.active = str(data.get("active", ""))
        self.last_dir = str(data.get("last_dir", ""))
        self.window = dict(data.get("window", {}))
        self.autosave = bool(data.get("autosave", False))
        self.history = history.clamp(data.get("history", history.LIMIT_DEFAULT))

    def save(self) -> None:
        data = {"tabs": self.tabs, "active": self.active, "last_dir": self.last_dir,
                "window": self.window, "autosave": self.autosave, "history": self.history}
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_name(self.path.name + ".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
        os.replace(tmp, self.path)
