# -*- coding: utf-8 -*-
"""Все строки [KR] Imageset Editor — в одном месте (свод правил интерфейсов, п. 60)."""
from __future__ import annotations

from version import NAME as _NAME, VERSION as _VERSION

TEXT = {
    "app.title": "%s %s" % (_NAME, _VERSION),
    "app.titled": "{name} — %s %s" % (_NAME, _VERSION),

    "open": "Открыть",
    "open.title": "Открыть imageset",
    "empty": "Перетащите .imageset в окно или откройте его —\nкаждый файл откроется своей вкладкой",
    "tab.readonly": "только просмотр",
    "tab.readonly.tip": "Ванильный файл (P:\\gui) — только просмотр, переписать его нельзя",
    "tab.missing": "Файла больше нет: {path}",
    "tab.unreadable": "{path}: не читается. {text}",

    "sprites.search": "Поиск спрайта",
    "sprites.group": "группа {name}",

    "props.title": "Спрайт",
    "props.none": "Выберите спрайт в списке или на атласе",
    "props.name": "Имя",
    "props.pos": "Позиция",
    "props.size": "Размер",
    "props.flags": "Flags",
    "props.square": "Ширина = высота: высота недоступна и всегда равна ширине",
    "props.group": "Группа",
    "props.group.none": "—",

    "info.set": "Сет «{name}» · RefSize {w}×{h} · спрайтов {count}",
    "info.texture": "Текстура: {path}",
    "info.texture.missing": "Текстура не найдена: {path}",
    "info.saved": "Сохранено {time}",
    "info.backup": " · прежний файл — копией в {folder}",

    "zoom.fit": "Вписать",
    "undo.move": "Позиция «{name}»",
    "undo.size": "Размер «{name}»",

    "group.add": "Новая группа",
    "group.rename": "Переименовать группу",
    "group.delete": "Удалить группу",
    "group.prompt": "Имя группы",
    "group.taken": "Группа «{name}» уже есть",
    "group.delete.title": "Удалить группу «{name}»?",
    "group.delete.text": "В ней спрайтов: {count}. Куда их перенести? «—» — оставить без группы",

    "edit.hint": "Двойной щелчок по рамке — ручная правка: угол тянет две стороны, середина "
                 "двигает. Shift — пропорционально, Alt — шаг 32, Ctrl — прилипание к соседям "
                 "ближе 8. Esc — выйти. Обвести мышью — выделить несколько; несколько "
                 "двигаются сразу, без двойного щелчка",
    "edit.mode": "Ручная правка: {name}",

    "tex.title": "Текстуры",
    "tex.add": "Добавить текстуру (вторая обычно @2x — вдвое крупнее, те же координаты)",
    "tex.replace": "Заменить текстуру",
    "tex.remove": "Убрать текстуру",
    "tex.missing": "файл не найден",
    "tex.pick": "Текстура атласа",
    "tex.converting": "Перегоняю {name} в EDDS…",
    "tex.convert_failed": "Не перегнать в EDDS: {text}",
    "tex.outside_p": "текстура вне P: — в imageset записано только имя файла",

    "undo.rect": "Рамка «{name}»",
    "undo.group_move": "Сдвиг спрайтов: {count}",
    "undo.move_group": "Перенос спрайтов",
    "undo.group.add": "Группа «{name}»",
    "undo.group.rename": "Переименование группы «{name}»",
    "undo.group.delete": "Удаление группы «{name}»",
    "undo.tex.add": "Новая текстура",
    "undo.tex.replace": "Замена текстуры",
    "undo.tex.remove": "Текстура убрана",

    "set.title": "Имиджсет",
    "set.name": "Имя",
    "set.name.tip": "Имя сета (поле Name): им ссылаются set:ИМЯ image:… в layout, конфигах и "
                    "скриптах. С именем файла и текстуры совпадать не обязано",
    "set.refsize": "Система координат (RefSize): {w}×{h}",
    "set.refsize.tip": "Позиции и размеры спрайтов заданы в этих единицах, а не в пикселях "
                       "текстуры: у @2x текстура вдвое больше при тех же координатах",
    "sprite.add": "Новый спрайт: 128×128 в (0, 0) — в выбранную группу",
    "rename.set_chars": "«{name}»: в имени сета только латиница, цифры и подчёркивание — им "
                        "ссылаются set:ИМЯ",
    "undo.set.rename": "Имя сета «{name}»",
    "undo.sprite.add": "Новый спрайт",
    "undo.sprite.paste": "Вставка «{name}»",
    "undo.sprite.delete": "Удаление спрайтов: {count}",
    "sprites.title": "Спрайты",
    "rename.empty": "Имя не может быть пустым",
    "rename.chars": "«{name}»: в имени спрайта нельзя пробелы и кавычки — на него ссылаются "
                    "set:… image:ИМЯ; в имени группы нельзя кавычки и фигурные скобки",
    "rename.taken": "«{name}» уже есть",
    "rename.refs": "ссылок на старое имя «{old}» в {root}: {count} в файлах: {files} — "
                   "они не правились, наведите — список",
    "rename.refs.none": "ссылок на старое имя «{old}» в {root} нет",
    "undo.sprite.rename": "Переименование «{name}»",

    "dialog.ok": "Готово",
    "dialog.cancel": "Отмена",
}


def T(key: str, **kw) -> str:
    """Текст по ключу. Неизвестный ключ — сам ключ: видно и ищется, а не падает."""
    text = TEXT.get(key, key)
    return text.format(**kw) if kw else text
