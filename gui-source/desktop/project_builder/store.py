# -*- coding: utf-8 -*-
"""Сохранённые наборы PBO под запаковку и общие настройки сборки.

Набор (решение юзера 22.10.2026) — имя, одна папка «куда» и список папок
модов. Набор — помощник, а не условие (там же): всегда есть рабочий список
«без набора» (имя — пустая строка), паковать можно прямо из него, а
сохранить его как набор — когда захочется. PBO получает имя папки мода, как у pboProject; если одной строке нужна
другая цель (серверная часть мода — в свой @мод), у неё своё поле `target`.

Путь к файлу передаётся снаружи (свод правил интерфейсов, п. 67): тест и разовый
скрипт работают с копией и не трогают настройки человека.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

#: имя файла состояния; прежнее (до 24.10.2026) переносится копией — kr_state
STATE_NAME, OLD_NAME = "project_builder_sets.json", "build_sets.json"

#: Имя рабочего списка «без набора».
SCRATCH = ""


#: Правило Addons — то же, что у командной строки (build_kit.targets.addons_dir);
#: окну оно нужно, чтобы показать, куда ляжет PBO. Совпадение держит тест.
ADDONS = "Addons"


def addons_dir(folder: str) -> str:
    """Куда реально пакуем, если выбрана папка `folder`."""
    if not folder:
        return ""
    path = Path(folder)
    if path.name.lower() == ADDONS.lower():
        return str(path)
    try:
        found = next((c for c in path.iterdir()
                      if c.is_dir() and c.name.lower() == ADDONS.lower()), None)
    except OSError:                                  # папки ещё нет или нет доступа
        found = None
    return str(found or path / ADDONS)


@dataclass
class Entry:
    source: str
    enabled: bool = True
    #: Полный путь к PBO, если у строки своя цель; пусто — папка набора.
    target: str = ""

    def pbo_name(self) -> str:
        return Path(self.target).name if self.target else Path(self.source).name + ".pbo"

    def pbo_path(self, target_dir: str) -> Optional[Path]:
        if self.target:
            return Path(self.target)
        if not target_dir:
            return None
        return Path(target_dir) / (Path(self.source).name + ".pbo")


@dataclass
class BuildSet:
    name: str
    target_dir: str = ""
    entries: List[Entry] = field(default_factory=list)


class Store:
    """Наборы на диске. Пишет сразу при каждом изменении — терять список нельзя."""

    def __init__(self, path: Optional[Path] = None):
        from kr_state import state_file
        self.path = Path(path) if path is not None else state_file(STATE_NAME, OLD_NAME)
        self.sets: List[BuildSet] = []
        self.current: str = ""
        self.window: Dict[str, Any] = {}
        self._load()
        self._ensure_scratch()

    # ------------------------------------------------------------------ диск
    def _load(self) -> None:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        for raw in data.get("sets", []):
            target_dir = str(raw.get("target_dir", ""))
            entries = []
            for e in raw.get("entries", []):
                source = str(e.get("source", ""))
                target = str(e.get("target", ""))
                # прежний формат: у каждой строки полный путь к PBO. Папку набора
                # берём у первой строки, а у совпадающих с ней свою цель снимаем.
                if target and not target_dir:
                    target_dir = str(Path(target).parent)
                if target and Path(target).parent == Path(target_dir) \
                        and Path(target).stem == Path(source).name:
                    target = ""
                entries.append(Entry(source, bool(e.get("enabled", True)), target))
            self.sets.append(BuildSet(str(raw.get("name", "")), target_dir, entries))
        self.current = str(data.get("current", ""))
        self.window = dict(data.get("window", {}))

    def _ensure_scratch(self) -> None:
        if self.find(SCRATCH) is None:
            self.sets.insert(0, BuildSet(SCRATCH))

    def save(self) -> None:
        data = {"sets": [{"name": s.name, "target_dir": s.target_dir,
                          "entries": [{"source": e.source, "enabled": e.enabled, "target": e.target}
                                      for e in s.entries]}
                         for s in self.sets],
                "current": self.current, "window": self.window}
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_name(self.path.name + ".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
        os.replace(tmp, self.path)

    # ------------------------------------------------------------------ наборы
    def find(self, name: str) -> Optional[BuildSet]:
        return next((s for s in self.sets if s.name == name), None)

    def scratch(self) -> BuildSet:
        return self.find(SCRATCH)

    def named(self) -> List[BuildSet]:
        return [s for s in self.sets if s.name != SCRATCH]

    def active(self) -> BuildSet:
        """Открытый набор; нет такого — рабочий список «без набора»."""
        return self.find(self.current) or self.scratch()

    def create(self, name: str) -> BuildSet:
        made = BuildSet(name)
        self.sets.append(made)
        self.current = name
        self.save()
        return made

    def rename(self, old: str, new: str) -> None:
        found = self.find(old)
        if found is not None:
            found.name = new
            if self.current == old:
                self.current = new
            self.save()

    def delete(self, name: str) -> None:
        if name == SCRATCH:
            return
        self.sets = [s for s in self.sets if s.name != name]
        if self.current == name:
            self.current = SCRATCH
        self.save()

    def promote(self, name: str) -> BuildSet:
        """Рабочий список — в именованный набор; рабочий список становится пустым."""
        scratch = self.scratch()
        made = BuildSet(name, scratch.target_dir, scratch.entries)
        self.sets.append(made)
        scratch.entries = []
        self.current = name
        self.save()
        return made


def read_global_settings(path: Path) -> Dict[str, Any]:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    except FileNotFoundError:
        return {}
    return data if isinstance(data, dict) else {}


def write_global_settings(path: Path, values: Dict[str, Any]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(values, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, path)
