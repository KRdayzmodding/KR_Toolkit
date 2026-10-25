# -*- coding: utf-8 -*-
"""Все строки окна [KR] Addon Signer — в одном месте (свод правил интерфейсов, п. 60)."""
from __future__ import annotations

from version import NAME as _NAME, VERSION as _VERSION

TEXT = {
    "app.title": "%s %s" % (_NAME, _VERSION),

    "key.label": "Ключ",
    "key.none": "Ключей нет — создайте или добавьте",
    "key.create": "Создать",
    "key.create.title": "Создать ключ",
    "key.add": "Добавить",
    "key.add.title": "Добавить ключ",
    "key.remove": "Убрать ключ из списка (файл не удаляется)",
    "key.created": "Созданы {prv} и {pub} в папке {folder}. {pub} кладут на сервер "
                   "в keys, {prv} никому не передают: им подписывают",
    "key.public": "{name} — публичный ключ (.bikey): подписывают приватным .biprivatekey",
    "key.unreadable": "Ключ не читается: {text}",
    "key.missing": "Файла ключа нет: {path}",

    "preset.label": "Пресет",
    "preset.scratch": "Без пресета",
    "preset.new": "Новый пресет",
    "preset.new.title": "Новый пресет",
    "preset.save.title": "Сохранить папки пресетом",
    "preset.new.prompt": "Название пресета",
    "preset.name.taken": "Пресет «{name}» уже есть",
    "preset.rename": "Переименовать пресет",
    "preset.rename.title": "Переименовать пресет",
    "preset.delete": "Удалить пресет",
    "preset.delete.title": "Удалить пресет «{name}»?",
    "preset.delete.text": "Удалится только список папок. Папки, PBO и подписи останутся",

    "folders.title": "Папки",
    "folders.add": "Добавить папку",
    "folders.remove": "Убрать папку из списка",
    "folders.drop": "Перетащите сюда папки с PBO —\nвложенные папки тоже просматриваются",
    "folders.pick": "Добавить папку",
    "folders.pick.title": "Папка с PBO",

    "pbo.title": "PBO",
    "pbo.all": "Отметить все",
    "pbo.none": "Снять все",
    "col.pbo": "PBO",
    "col.where": "Папка",
    "col.state": "Подпись",

    "state.ok": "подписан",
    "state.stale": "устарела",
    "state.missing": "нет подписи",
    "state.foreign": "другой ключ",
    "state.broken": "не читается",
    "state.checking": "проверка…",
    "state.no_key": "ключ не выбран",
    "state.tip.stale": "PBO изменился после подписи: {detail}",
    "state.tip.foreign": "Подпись верна, но сделана другим ключом с тем же именем. "
                         "Не перезаписывается: сломалась бы для серверов со старым .bikey",
    "state.tip.broken": "PBO не читается: {detail}",

    "summary.empty": "PBO не найдено",
    "summary.counts": "PBO: {total} · подписано {ok} · устарело {stale} · без подписи {missing}",
    "summary.foreign": " · другим ключом {foreign}",
    "summary.broken": " · не читается {broken}",
    "summary.signed": "Подписано: {count}.",
    "summary.backup": " Прежние подписи ({count}) — копией в {folder}",

    "main.rescan": "Проверить заново",
    "main.sign": "Подписать: {count}",
    "main.sign.none": "Всё подписано",
    "main.sign.nothing_chosen": "Ничего не отмечено",
    "main.sign.no_key": "Выберите ключ",
    "main.sign.empty": "Нет PBO",
    "progress.scan": "проверка подписей {done} из {total}",
    "progress.sign": "подпись {done} из {total}",

    "dialog.ok": "Готово",
    "dialog.cancel": "Отмена",
}


def T(key: str, **kw) -> str:
    """Текст по ключу. Неизвестный ключ — сам ключ: видно и ищется, а не падает."""
    text = TEXT.get(key, key)
    return text.format(**kw) if kw else text
