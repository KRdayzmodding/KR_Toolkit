# -*- coding: utf-8 -*-
"""Открытый imageset: данные, правки с отменой, сохранение.

Спрайт адресуется постоянным номером (id), а не местом в списке: его таскают
между группами, и место меняется. Раскладка — спрайты без группы (`top`) и
группы со своими списками id. Порядок сохраняется при записи.

Правка — команда в QUndoStack (Ctrl+Z / Ctrl+Y). Правка одного спрайта числами
склеивается в одну команду; всё остальное (перенос, группы, текстуры, правка
рамки мышью) — снимок состояния до и после. «Изменён» — стек не в чистом
состоянии. Сохраняет окно — само (автосохранение, как в VSCode) или по Ctrl+S,
если автосохранение выключено в настройках.

История отмены переживает перезапуск (history.py): при открытии она
восстанавливается, если файл на диске совпадает с одним из её шагов, — на
этот шаг; иначе (файл правили снаружи) отбрасывается, и окно об этом пишет.
Шагов в стеке — не больше настройки (по умолчанию 50, до 512).

Перед первой записью за сессию прежний файл уходит копией в папку бэкапов
(принцип 17). Ванильные файлы (P:\\gui, P:\\DZ, P:\\scripts) — только просмотр
(принцип 19).

Читает, пишет и декодирует текстуру ImagesetEditor.exe (worker.py); здесь —
только модель правок окна.
"""
from __future__ import annotations

from pathlib import Path
from typing import Dict, List, NamedTuple, Optional, Tuple

import numpy as np
from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QImage, QUndoCommand, QUndoStack

import history
import worker as ie

BACKUP_ROOT = Path.home() / ".kr_devtoolkit" / "imageset_backup"
#: mpix первой текстуры нового сета
DEFAULT_MPIX = 1


class Sprite(NamedTuple):
    """Прямоугольник в координатах RefSize."""

    name: str
    x: int
    y: int
    width: int
    height: int
    flags: str = "0"


class Texture(NamedTuple):
    """Атлас: путь, как записан в imageset, mpix и файл на диске, где он нашёлся."""

    path: str
    mpix: int = DEFAULT_MPIX
    file: Optional[str] = None


class SetInfo(NamedTuple):
    width: int                     #: RefSize — система координат спрайтов
    height: int


def _sprite(d: dict) -> Sprite:
    return Sprite(d["name"], int(d["x"]), int(d["y"]), int(d["width"]), int(d["height"]), str(d.get("flags", "0")))


class Document(QObject):
    changed = Signal(object)          # id правленного спрайта; None — поменялась раскладка
    textures_changed = Signal()
    dirty_changed = Signal(bool)
    saved = Signal(str)               # путь копии прежнего файла ("" — копии не было)

    def __init__(self, path: Path, backup_root: Path = BACKUP_ROOT, parent=None,
                 history_root: Optional[Path] = None, history_limit: int = history.LIMIT_DEFAULT):
        super().__init__(parent)
        self.path = Path(path)
        raw = ie.read(self.path)                        # ошибку отдаём вызывающему
        self.data = SetInfo(int(raw["width"]), int(raw["height"]))
        #: как записан файл (переводы строк, пустой блок групп) — вернуть при записи как было
        self._format = {k: raw[k] for k in ("newline", "final_newline", "groups_block")}
        self.items: Dict[int, Sprite] = {}
        self.top: List[int] = []
        self.groups: List[List] = []                    # [имя, [id…]]
        for sprite in raw["sprites"]:
            self.top.append(self._new_id(_sprite(sprite)))
        for group in raw["groups"]:
            self.groups.append([group["name"], [self._new_id(_sprite(s)) for s in group["sprites"]]])
        self.textures: List[Texture] = [Texture(t["path"], int(t["mpix"]), t.get("file")) for t in raw["textures"]]
        #: имя сета — поле Name; им ссылаются `set:ИМЯ image:…`, с именем файла не обязано совпадать
        self.name: str = raw["name"]
        self.readonly = bool(raw["vanilla"]) or not raw["writable"]
        #: где искать ссылки на спрайты (верхняя папка проекта на P:) или None
        self.refs_root: Optional[Path] = Path(raw["refs_root"]) if raw.get("refs_root") else None
        self.backup_root = backup_root
        self.backup: Optional[Path] = None
        self.undo = QUndoStack(self)
        self.undo.setUndoLimit(history.clamp(history_limit))
        # метод, а не лямбда: связь с методом Qt снимает сам, когда документ удаляют, а лямбду
        # стек дёргал из своего деструктора уже после документа (Signal source has been deleted)
        self.undo.cleanChanged.connect(self._on_clean)
        self._image: Optional[QImage] = None
        self._quiet = False                             # восстановление истории — без перерисовок
        #: файл истории; None — без истории (только просмотр или не задана папка)
        self.history_file = (history.file_for(history_root, self.path)
                             if history_root is not None and not self.readonly else None)
        #: шагов истории, восстановленных из прошлой сессии; history_dropped — была, но не подошла
        self.history_restored = 0
        self.history_dropped = False
        if self.history_file is not None:
            self._load_history()

    def _new_id(self, sprite: Sprite) -> int:
        # номер только растёт: номер удалённого спрайта не достаётся новому, и холст
        # не путает его рамку со старой
        self._next_id = getattr(self, "_next_id", 0) + 1
        self.items[self._next_id] = sprite
        return self._next_id

    def _on_clean(self, clean: bool) -> None:
        self.dirty_changed.emit(not clean)

    # ------------------------------------------------------------------ чтение
    @property
    def dirty(self) -> bool:
        return not self.undo.isClean()

    def ids(self) -> List[int]:
        """Все спрайты по порядку файла: сначала без группы, потом по группам."""
        return list(self.top) + [sid for _name, ids in self.groups for sid in ids]

    def sprite(self, sid: int) -> Sprite:
        return self.items[sid]

    def group_of(self, sid: int) -> Optional[int]:
        """Индекс группы спрайта или None — без группы."""
        for gi, (_name, ids) in enumerate(self.groups):
            if sid in ids:
                return gi
        return None

    def group_names(self) -> List[str]:
        return [name for name, _ids in self.groups]

    def build(self) -> dict:
        """Imageset для записи — в том виде, в каком его отдаёт и принимает командная строка."""
        return dict(self._format, name=self.name, width=self.data.width, height=self.data.height,
                    textures=[{"path": t.path, "mpix": t.mpix} for t in self.textures],
                    sprites=[self.items[sid]._asdict() for sid in self.top],
                    groups=[{"name": name, "sprites": [self.items[sid]._asdict() for sid in ids]}
                            for name, ids in self.groups])

    # ------------------------------------------------------------------ снимки состояния
    def _state(self):
        return (dict(self.items), list(self.top), [[n, list(i)] for n, i in self.groups],
                list(self.textures), self.name)

    def _restore(self, state) -> None:
        items, top, groups, textures, name = state
        textures_moved = textures != self.textures
        self.name = name
        self.items, self.top = dict(items), list(top)
        self.groups = [[n, list(i)] for n, i in groups]
        self.textures = list(textures)
        if textures_moved:
            self._image = None
            if not self._quiet:
                self.textures_changed.emit()
        if not self._quiet:
            self.changed.emit(None)

    def _change(self, text: str, mutate) -> None:
        """Правка раскладки снимком: состояние до, правка, состояние после."""
        if self.readonly:
            return
        before = self._state()
        mutate()
        after = self._state()
        if after != before:
            self.undo.push(_Snapshot(self, before, after, text))

    # ------------------------------------------------------------------ правки
    def edit(self, sid: int, text: str, **fields) -> None:
        """Поля одного спрайта (числами) — подряд идущие правки склеиваются."""
        if self.readonly:
            return
        old = self.items[sid]
        new = old._replace(**fields)
        if new != old:
            self.undo.push(_SetSprite(self, sid, old, new, text))

    def set_rect(self, sid: int, rect: Tuple[int, int, int, int], text: str) -> None:
        """Рамка целиком (правка мышью) — одной командой на весь жест, без склейки
        с соседним жестом: каждый отменяется отдельно."""
        if self.readonly:
            return
        x, y, w, h = rect
        old = self.items[sid]
        new = old._replace(x=x, y=y, width=w, height=h)
        if new != old:
            self.undo.push(_SetRect(self, sid, old, new, text))

    def name_problem(self, name: str, sid: Optional[int] = None, group: Optional[int] = None) -> str:
        """Почему имя не годится ("" — годится). Спрайт: без пробелов и кавычек — на него
        ссылаются `set:… image:ИМЯ`; группа может с пробелами (в ваниле «Rebuilding Group»).
        Имена не повторяются (без учёта регистра)."""
        if not name:
            return "empty"
        if any(c in name for c in '"{}') or (sid is not None and any(c.isspace() for c in name)):
            return "chars"
        if sid is not None:
            taken = {self.items[k].name.lower() for k in self.items if k != sid}
        else:
            taken = {n.lower() for i, n in enumerate(self.group_names()) if i != group}
        return "taken" if name.lower() in taken else ""

    def set_problem(self, name: str) -> str:
        """Почему имя сета не годится ("" — годится): им ссылаются `set:ИМЯ`, поэтому
        только буквы, цифры и подчёркивание."""
        if not name:
            return "empty"
        if not all(c.isalnum() or c == "_" for c in name) or not name.isascii():
            return "set_chars"
        return ""

    def set_name(self, name: str, text: str) -> None:
        def mutate():
            self.name = name
        self._change(text, mutate)

    def unique_name(self, base: str) -> str:
        """Имя копии: base1, base2… — первое свободное (без учёта регистра)."""
        taken = {s.name.lower() for s in self.items.values()}
        n = 1
        while ("%s%d" % (base, n)).lower() in taken:
            n += 1
        return "%s%d" % (base, n)

    def add_sprite(self, sprite: Sprite, group: Optional[int], text: str,
                   after: Optional[int] = None) -> Optional[int]:
        """Новый спрайт в группу `group` (None — без группы), сразу за `after` или в конец."""
        if self.readonly:
            return None
        made = []

        def mutate():
            sid = self._new_id(sprite)
            dest = self.top if group is None else self.groups[group][1]
            at = dest.index(after) + 1 if after in dest else len(dest)
            dest.insert(at, sid)
            made.append(sid)
        self._change(text, mutate)
        return made[0] if made else None

    def delete_sprites(self, sids: List[int], text: str) -> None:
        def mutate():
            for sid in sids:
                gi = self.group_of(sid)
                (self.top if gi is None else self.groups[gi][1]).remove(sid)
                del self.items[sid]
        self._change(text, mutate)

    def rename_sprite(self, sid: int, name: str, text: str) -> None:
        def mutate():
            self.items[sid] = self.items[sid]._replace(name=name)
        self._change(text, mutate)

    def set_rects(self, rects, text: str) -> None:
        """Рамки нескольких спрайтов (сдвиг группы мышью) — одной отменой."""
        def mutate():
            for sid, (x, y, w, h) in rects.items():
                self.items[sid] = self.items[sid]._replace(x=x, y=y, width=w, height=h)
        self._change(text, mutate)

    def add_group(self, name: str, text: str) -> None:
        self._change(text, lambda: self.groups.append([name, []]))

    def rename_group(self, gi: int, name: str, text: str) -> None:
        def mutate():
            self.groups[gi][0] = name
        self._change(text, mutate)

    def delete_group(self, gi: int, target: Optional[int], text: str) -> None:
        """Удалить группу; её спрайты — в группу `target` или без группы (None)."""
        def mutate():
            moving = self.groups[gi][1]
            dest = None if target is None else self.groups[target][1]
            (self.top if dest is None else dest).extend(moving)
            del self.groups[gi]
        self._change(text, mutate)

    def move(self, sids: List[int], target: Optional[int], before: Optional[int], text: str) -> None:
        """Перенести спрайты в группу `target` (None — без группы) перед спрайтом `before`
        (None — в конец). Порядок переносимых сохраняется."""
        def mutate():
            for sid in sids:
                lst = self.top if self.group_of(sid) is None else self.groups[self.group_of(sid)][1]
                lst.remove(sid)
            dest = self.top if target is None else self.groups[target][1]
            at = dest.index(before) if before in dest else len(dest)
            dest[at:at] = sids
        self._change(text, mutate)

    def set_texture(self, index: Optional[int], texture: Optional[Texture], text: str) -> None:
        """Заменить текстуру `index`, добавить (index None) или убрать (texture None)."""
        def mutate():
            if index is None:
                self.textures.append(texture)
            elif texture is None:
                del self.textures[index]
            else:
                self.textures[index] = texture
        self._change(text, mutate)
        self._image = None
        self.textures_changed.emit()

    def _put(self, sid: int, sprite: Sprite) -> None:
        self.items[sid] = sprite
        self.changed.emit(sid)

    # ------------------------------------------------------------------ сохранение
    def save(self) -> bool:
        """Записать, если есть что; прежний файл — копией, один раз за сессию."""
        if self.readonly or not self.dirty:
            return False
        # копия прежнего файла — только при первой записи за сессию
        copied = ie.write(self.path, self.build(), self.backup_root if self.backup is None else None)
        if copied:
            self.backup = Path(copied)
        self.undo.setClean()
        self.save_history()                   # сохранённый шаг — опора сверки при следующем открытии
        self.saved.emit(copied)
        return True

    # ------------------------------------------------------------------ история между сессиями
    def _history(self):
        """Все шаги стека состояниями: от текущего назад и вперёд по командам."""
        n, index = self.undo.count(), self.undo.index()
        states = [None] * (n + 1)
        states[index] = self._state()
        for j in range(index - 1, -1, -1):
            states[j] = self.undo.command(j).backward(states[j + 1])
        for j in range(index, n):
            states[j + 1] = self.undo.command(j).forward(states[j])
        return states, [self.undo.command(j).text() for j in range(n)], index, self.undo.cleanIndex()

    def save_history(self) -> bool:
        """Записать историю на диск (пустая — убрать файл). Не вышло — тихо: это удобство,
        а не данные, и падать из-за него посреди работы нельзя."""
        if self.history_file is None:
            return False
        try:
            if self.undo.count() == 0:
                if self.history_file.exists():
                    self.history_file.unlink()
                return True
            history.write(self.history_file, history.encode(self.path, *self._history()))
            return True
        except OSError:
            return False

    def _load_history(self) -> None:
        data = history.read(self.history_file)
        if data is None:
            return
        try:
            states, texts, index, clean = history.decode(data, Sprite, Texture)
        except ValueError:
            states = None
        # файл на диске — какой шаг истории: сохранённый, текущий, иначе любой с конца
        want = history.shape(self._state())
        found = None
        if states is not None:
            order = [k for k in (clean, index) if 0 <= k < len(states)] + list(range(len(states) - 1, -1, -1))
            found = next((k for k in order if history.shape(states[k]) == want), None)
        if found is None:
            # файл правили вне редактора (или история битая) — она к нему больше не относится
            self.history_dropped = True
            try:
                self.history_file.unlink()
            except OSError:
                pass
            return
        # текстуры — как нашлись на диске сейчас, а не в прошлой сессии
        files = {t.path: t.file for t in self.textures}
        states = [(i, t, g, [x._replace(file=files.get(x.path, x.file)) for x in tex], n)
                  for i, t, g, tex, n in states]
        states, texts, index, clean = history.trim(states, texts, found, found, self.undo.undoLimit())
        self._import(states, texts, index, clean, self.undo.undoLimit())
        self.history_restored = len(texts)

    def _import(self, states, texts, index: int, clean: int, limit: int) -> None:
        """Собрать стек заново из состояний: стоим на index, сохранён clean (-1 — нигде)."""
        self._quiet = True
        try:
            self.undo.clear()
            self.undo.setUndoLimit(limit)             # Qt меняет предел только у пустого стека
            self._restore(states[-1])
            for j, text in enumerate(texts):
                self.undo.push(_Snapshot(self, states[j], states[j + 1], text))
            if 0 <= clean <= len(texts):
                self.undo.setIndex(clean)
                self.undo.setClean()
            else:
                self.undo.resetClean()
            self.undo.setIndex(index)
        finally:
            self._quiet = False
        self._next_id = max([getattr(self, "_next_id", 0)] + [k for s in states for k in s[0]])
        self._image = None
        self.textures_changed.emit()
        self.changed.emit(None)

    def set_history_limit(self, limit: int) -> None:
        """Новый предел шагов — сразу для открытого файла: лишние старые шаги уходят."""
        limit = history.clamp(limit)
        if limit == self.undo.undoLimit():
            return
        if self.undo.count() == 0:
            self.undo.setUndoLimit(limit)
            return
        self._import(*history.trim(*self._history(), limit), limit)

    # ------------------------------------------------------------------ текстура
    def texture_path(self, index: int = 0) -> Optional[Path]:
        if index >= len(self.textures) or not self.textures[index].file:
            return None
        path = Path(self.textures[index].file)
        return path if path.is_file() else None

    def image(self) -> Optional[QImage]:
        """Первая текстура как QImage (RGBA). Нет файла или не читается — None."""
        if self._image is None:
            path = self.texture_path()
            if path is None:
                return None
            pixels = ie.pixels(path)
            if pixels is None:
                return None
            pixels = np.ascontiguousarray(pixels)
            h, w = pixels.shape[:2]
            self._image = QImage(pixels.data, w, h, w * 4, QImage.Format_RGBA8888).copy()
        return self._image


class _SetSprite(QUndoCommand):
    """Замена одного спрайта; подряд идущие правки того же поля склеиваются."""

    ID = 1

    def __init__(self, doc: Document, sid: int, old, new, text: str):
        super().__init__(text)
        self.doc, self.sid, self.old, self.new = doc, sid, old, new

    def id(self) -> int:
        return self.ID

    def mergeWith(self, other) -> bool:
        if other.sid != self.sid or other.text() != self.text():
            return False
        self.new = other.new
        return True

    def redo(self) -> None:
        self.doc._put(self.sid, self.new)

    def undo(self) -> None:
        self.doc._put(self.sid, self.old)

    # состояние до и после — для истории на диске, документ не трогают
    def forward(self, state):
        items = dict(state[0])
        items[self.sid] = self.new
        return (items,) + tuple(state[1:])

    def backward(self, state):
        items = dict(state[0])
        items[self.sid] = self.old
        return (items,) + tuple(state[1:])


class _Snapshot(QUndoCommand):
    """Правка раскладки: всё состояние до и после."""

    def __init__(self, doc: Document, before, after, text: str):
        super().__init__(text)
        self.doc, self.before, self.after = doc, before, after
        self._first = True

    def redo(self) -> None:
        if self._first:                       # правка уже сделана — при push не повторяем
            self._first = False
            if not self.doc._quiet:
                self.doc.changed.emit(None)
            return
        self.doc._restore(self.after)

    def undo(self) -> None:
        self.doc._restore(self.before)

    def forward(self, _state):
        return self.after

    def backward(self, _state):
        return self.before


class _SetRect(_SetSprite):
    """Рамка жестом мыши — не склеивается."""

    def id(self) -> int:
        return -1
