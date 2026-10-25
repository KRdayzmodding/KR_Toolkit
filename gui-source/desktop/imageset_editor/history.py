# -*- coding: utf-8 -*-
"""История правок imageset между сессиями (заказ юзера 25.10.2026).

Каждый открытый файл держит свою историю: закрыли тулзу, открыли снова —
Ctrl+Z отменяет правки прошлой сессии. Хранится в папке состояния тулзы,
один файл истории на один imageset (по полному пути).

Шаг — состояние документа после правки. На диске первое состояние целиком,
дальше только разница с предыдущим: правка обычно трогает один спрайт, и
512 шагов большого сета не превращаются в мегабайты.

Состояние — тот же кортеж, что у Document._state(): спрайты по номерам,
порядок без группы, группы, текстуры, имя сета. Номера спрайтов в истории
свои, из прошлой сессии: сверка с файлом идёт по содержимому (shape), а не по
номерам.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Callable, List, Optional, Tuple

FORMAT = 1
#: шагов отмены на файл: по умолчанию и предел (юзер 25.10.2026)
LIMIT_DEFAULT, LIMIT_MIN, LIMIT_MAX = 50, 1, 512


def clamp(limit) -> int:
    try:
        value = int(limit)
    except (TypeError, ValueError):
        return LIMIT_DEFAULT
    return max(LIMIT_MIN, min(LIMIT_MAX, value))


def file_for(root: Path, path: Path) -> Path:
    """Файл истории imageset: имя — от полного пути, без учёта регистра (Windows)."""
    key = os.path.normcase(os.path.abspath(path))
    return Path(root) / (hashlib.sha1(key.encode("utf-8")).hexdigest()[:16] + ".json")


def shape(state) -> tuple:
    """Содержимое состояния без номеров спрайтов и без найденных на диске файлов текстур —
    им сверяется история с тем, что сейчас лежит в файле."""
    items, top, groups, textures, name = state
    return (tuple(tuple(items[i]) for i in top),
            tuple((n, tuple(tuple(items[i]) for i in ids)) for n, ids in groups),
            tuple((t[0], t[1]) for t in textures), name)


def trim(states: list, texts: list, index: int, clean: int, limit: int) -> Tuple[list, list, int, int]:
    """Оставить не больше limit шагов: последние, но так, чтобы текущий остался в окне.
    Сохранённое состояние, выпавшее из окна, — clean = -1 (файл считается изменённым)."""
    n = len(texts)
    start = max(0, n - limit)
    if index < start:
        start = index
    end = min(n, start + limit)
    clean = clean - start if start <= clean <= end else -1
    return states[start:end + 1], texts[start:end], index - start, clean


def _full(state) -> dict:
    items, top, groups, textures, name = state
    return {"items": {str(k): list(v) for k, v in items.items()}, "top": list(top),
            "groups": [[n, list(ids)] for n, ids in groups],
            "textures": [list(t) for t in textures], "name": name}


def _delta(prev, cur) -> dict:
    pi, pt, pg, px, pn = prev
    ci, ct, cg, cx, cn = cur
    d = {}
    changed = {str(k): list(v) for k, v in ci.items() if pi.get(k) != v}
    if changed:
        d["set"] = changed
    gone = [k for k in pi if k not in ci]
    if gone:
        d["del"] = gone
    if list(ct) != list(pt):
        d["top"] = list(ct)
    if [[n, list(i)] for n, i in cg] != [[n, list(i)] for n, i in pg]:
        d["groups"] = [[n, list(ids)] for n, ids in cg]
    if list(cx) != list(px):
        d["textures"] = [list(t) for t in cx]
    if cn != pn:
        d["name"] = cn
    return d


def encode(path: Path, states: list, texts: List[str], index: int, clean: int) -> dict:
    return {"format": FORMAT, "file": str(path), "index": index, "clean": clean,
            "base": _full(states[0]), "steps": [_delta(a, b) for a, b in zip(states, states[1:])],
            "texts": list(texts)}


def decode(data: dict, sprite: Callable, texture: Callable) -> Tuple[list, List[str], int, int]:
    """Обратно в состояния; неизвестный формат или битые данные — ValueError."""
    if not isinstance(data, dict) or data.get("format") != FORMAT:
        raise ValueError("формат истории")
    try:
        base = data["base"]
        state = ({int(k): sprite(*v) for k, v in base["items"].items()}, list(base["top"]),
                 [[n, list(ids)] for n, ids in base["groups"]],
                 [texture(*t) for t in base["textures"]], base["name"])
        states = [state]
        for d in data["steps"]:
            items, top, groups, textures, name = states[-1]
            items = dict(items)                   # неизменённые спрайты — общие с прошлым шагом
            for k in d.get("del", []):
                items.pop(int(k), None)
            for k, v in d.get("set", {}).items():
                items[int(k)] = sprite(*v)
            if "top" in d:
                top = list(d["top"])
            if "groups" in d:
                groups = [[n, list(ids)] for n, ids in d["groups"]]
            if "textures" in d:
                textures = [texture(*t) for t in d["textures"]]
            states.append((items, top, groups, textures, d.get("name", name)))
        texts = [str(t) for t in data["texts"]]
        index, clean = int(data["index"]), int(data["clean"])
        for s in states:                          # порядок ссылается только на свои спрайты
            if any(i not in s[0] for i in list(s[1]) + [i for _n, ids in s[2] for i in ids]):
                raise ValueError("спрайт вне состояния")
    except (KeyError, TypeError, AttributeError) as exc:
        raise ValueError("история повреждена: %s" % exc) from exc
    n = len(states) - 1
    if len(texts) != n or not 0 <= index <= n or not -1 <= clean <= n:
        raise ValueError("история повреждена: шаги не сходятся")
    return states, texts, index, clean


def read(file: Path) -> Optional[dict]:
    try:
        return json.loads(Path(file).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def write(file: Path, data: dict) -> None:
    file = Path(file)
    file.parent.mkdir(parents=True, exist_ok=True)
    tmp = file.with_name(file.name + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    os.replace(tmp, file)
