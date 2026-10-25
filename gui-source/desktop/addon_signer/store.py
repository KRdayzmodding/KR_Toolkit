# -*- coding: utf-8 -*-
"""Список ключей, пресеты папок и состояние окна [KR] Addon Signer.

Хранятся только пути: к ключам (`.biprivatekey`) и к папкам. Содержимое ключей
в файл не попадает.

Пресет (юзер 23.10.2026) — имя и список папок, которые надо просканировать.
Как набор в [KR] Project Builder: всегда есть рабочий список «без пресета» (имя — пустая
строка), сохранить его пресетом можно в любой момент.

Путь к файлу передаётся снаружи (свод правил интерфейсов, п. 67): тест работает
с копией и не трогает настройки человека.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

#: имя файла состояния; прежнее (до 24.10.2026) переносится копией — kr_state
STATE_NAME, OLD_NAME = "addon_signer.json", "sign_studio.json"

#: Имя рабочего списка «без пресета».
SCRATCH = ""


@dataclass
class Preset:
    name: str
    folders: List[str] = field(default_factory=list)


class Store:
    """Пишет на диск сразу при каждом изменении — терять список нельзя."""

    def __init__(self, path: Optional[Path] = None):
        from kr_state import state_file
        self.path = Path(path) if path is not None else state_file(STATE_NAME, OLD_NAME)
        self.keys: List[str] = []
        self.key: str = ""
        self.presets: List[Preset] = []
        self.current: str = SCRATCH
        self.window: Dict[str, Any] = {}
        #: выбор человека «подписывать / нет» там, где он отличается от умолчания:
        #: путь PBO → да/нет (умолчание — подписывать отсутствующие и устаревшие)
        self.choices: Dict[str, bool] = {}
        self._load()
        if self.find(SCRATCH) is None:
            self.presets.insert(0, Preset(SCRATCH))

    def _load(self) -> None:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        self.keys = [str(k) for k in data.get("keys", [])]
        self.key = str(data.get("key", ""))
        for raw in data.get("presets", []):
            self.presets.append(Preset(str(raw.get("name", "")),
                                       [str(f) for f in raw.get("folders", [])]))
        self.current = str(data.get("current", SCRATCH))
        self.window = dict(data.get("window", {}))
        self.choices = {str(k): bool(v) for k, v in dict(data.get("choices", {})).items()}

    def save(self) -> None:
        data = {"keys": self.keys, "key": self.key, "current": self.current,
                "presets": [{"name": p.name, "folders": p.folders} for p in self.presets],
                "window": self.window, "choices": self.choices}
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_name(self.path.name + ".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
        os.replace(tmp, self.path)

    # ------------------------------------------------------------------ ключи
    def add_key(self, path: str) -> None:
        if path not in self.keys:
            self.keys.append(path)
        self.key = path
        self.save()

    def remove_key(self, path: str) -> None:
        """Только из списка: файл ключа не трогается."""
        if path in self.keys:
            self.keys.remove(path)
        if self.key == path:
            self.key = self.keys[0] if self.keys else ""
        self.save()

    # ------------------------------------------------------------------ пресеты
    def find(self, name: str) -> Optional[Preset]:
        return next((p for p in self.presets if p.name == name), None)

    def scratch(self) -> Preset:
        return self.find(SCRATCH)

    def named(self) -> List[Preset]:
        return [p for p in self.presets if p.name != SCRATCH]

    def active(self) -> Preset:
        return self.find(self.current) or self.scratch()

    def create(self, name: str) -> Preset:
        made = Preset(name)
        self.presets.append(made)
        self.current = name
        self.save()
        return made

    def promote(self, name: str) -> Preset:
        """Рабочий список становится пресетом; рабочий список пустеет."""
        made = Preset(name, list(self.scratch().folders))
        self.scratch().folders = []
        self.presets.append(made)
        self.current = name
        self.save()
        return made

    def rename(self, old: str, new: str) -> None:
        preset = self.find(old)
        if preset is not None and old != SCRATCH:
            preset.name = new
            if self.current == old:
                self.current = new
            self.save()

    def delete(self, name: str) -> None:
        preset = self.find(name)
        if preset is not None and name != SCRATCH:
            self.presets.remove(preset)
            if self.current == name:
                self.current = SCRATCH
            self.save()
