# -*- coding: utf-8 -*-
"""Что запоминает окно [KR] Sound Converter: входы, куда класть, перезапись, размер окна.

Путь к файлу передаётся снаружи (свод правил интерфейсов, п. 67): тест работает
с копией и не трогает настройки человека.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

#: имя файла состояния; прежнее (до 24.10.2026) переносится копией — kr_state
STATE_NAME, OLD_NAME = "sound_converter.json", "sound_studio.json"


class Store:
    def __init__(self, path: Optional[Path] = None):
        from kr_state import state_file
        self.path = Path(path) if path is not None else state_file(STATE_NAME, OLD_NAME)
        self.inputs: List[str] = []
        #: "" — рядом с WAV, иначе папка для OGG
        self.out: str = ""
        self.out_folder: str = ""          # помним папку, даже когда выбрано «рядом»
        self.overwrite = False
        self.window: Dict[str, Any] = {}
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        self.inputs = [str(p) for p in data.get("inputs", [])]
        self.out = str(data.get("out", ""))
        self.out_folder = str(data.get("out_folder", self.out))
        self.overwrite = bool(data.get("overwrite", False))
        self.window = dict(data.get("window", {}))

    def save(self) -> None:
        data = {"inputs": self.inputs, "out": self.out, "out_folder": self.out_folder,
                "overwrite": self.overwrite, "window": self.window}
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_name(self.path.name + ".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
        os.replace(tmp, self.path)
