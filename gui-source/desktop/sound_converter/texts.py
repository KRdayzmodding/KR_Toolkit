# -*- coding: utf-8 -*-
"""Все строки окна [KR] Sound Converter — в одном месте (свод правил интерфейсов, п. 60)."""
from __future__ import annotations

from sound_kit.version import NAME as _NAME, VERSION as _VERSION

TEXT = {
    "app.title": "%s %s" % (_NAME, _VERSION),

    "inputs.title": "Что перегнать",
    "inputs.add_files": "Добавить WAV",
    "inputs.add_folder": "Добавить папку",
    "inputs.remove": "Убрать из списка",
    "inputs.drop": "Перетащите сюда WAV-файлы или папки —\nвложенные папки тоже просматриваются",
    "inputs.pick_files": "WAV-файлы",
    "inputs.pick_folder": "Папка со звуками",

    "settings.title": "Настройки",
    "where.label": "Куда",
    "where.desc": "OGG — рядом с исходными WAV или в отдельную папку",
    "where.folder_row": "Папка для OGG",
    "where.next": "Рядом с WAV",
    "where.folder": "В папку",
    "where.hint": "Дерево папок сохранится",
    "where.pick": "Выбрать папку",
    "overwrite": "Перезаписывать готовые OGG",
    "overwrite.desc": "Прежние — копией в .kr_devtoolkit\\sound_backup",

    "wav.title": "Файлы",
    "wav.all": "Отметить все",
    "wav.none": "Снять все",
    "col.state": "Состояние",
    "col.wav": "WAV",
    "col.out": "Куда",

    "state.planned": "перегнать",
    "state.overwrite": "перезаписать",
    "state.skipped": "OGG уже есть",
    "state.converted": "перегнан",
    "state.failed": "ошибка",
    "state.converted.tip": "{kind}",

    "summary.empty": "WAV не найдено",
    "summary.plan": "WAV: {total} · перегнать {todo} · OGG уже есть {exists}",
    "summary.done": "Перегнано {converted}, пропущено {skipped}, ошибок {failed}",
    "summary.stopped": " · остановлено",
    "summary.backup": " · прежние OGG — копией в {folder}",
    "summary.problem": "Не взять: {text}",
    "summary.cli_failed": "Командная строка не отвечает: {text}",

    "main.convert": "Перегнать: {count}",
    "main.convert.none": "Нечего перегонять",
    "main.convert.nothing_chosen": "Ничего не отмечено",
    "main.convert.no_folder": "Укажите папку",
    "main.stop": "Остановить",
    "progress": "перегонка {done} из {total}",
    "planning": "смотрю, что перегнать…",

    "kind.mono": "моно",
    "kind.stereo": "стерео",
}


def T(key: str, **kw) -> str:
    """Текст по ключу. Неизвестный ключ — сам ключ: видно и ищется, а не падает."""
    text = TEXT.get(key, key)
    return text.format(**kw) if kw else text
