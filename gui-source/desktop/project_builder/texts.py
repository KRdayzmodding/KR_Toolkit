# -*- coding: utf-8 -*-
"""Все тексты окна сборки — в одном словаре (свод правил интерфейсов, пп. 25, 60, 66).

Ключи пишутся в коде буквально: `T("main.pack")`, а не собираются из кусков,
чтобы и поиск, и тест состава словаря их видели. Подстановки — через `{имя}`.
"""
from __future__ import annotations

from build_kit.version import NAME as _NAME, VERSION as _VERSION

TEXT = {
    "app.title": "%s %s" % (_NAME, _VERSION),

    "set.label": "Набор",
    "set.new": "Новый набор",
    "set.rename": "Переименовать набор",
    "set.delete": "Удалить набор",
    "set.new.title": "Новый набор",
    "set.new.prompt": "Название, например «Мебель»",
    "set.rename.title": "Переименовать набор",
    "set.name.taken": "Набор «{name}» уже есть",
    "set.delete.title": "Удалить набор «{name}»?",
    "set.delete.text": "Пропадёт только список. Моды и собранные PBO не пострадают. "
                       "Вернуть набор будет нельзя.",
    "set.scratch": "Без набора",
    "set.save": "Сохранить список как набор",
    "set.save.title": "Сохранить список как набор",

    "what.title": "Что паковать",
    "what.count": "отмечено {checked} из {total}",
    "what.drop": "Перетащи сюда папки модов — каждая станет PBO",
    "what.pick": "Выбрать папку…",
    "what.add": "Добавить папку",
    "what.all": "Выбрать все",
    "what.none": "Снять все",
    "what.remove": "Убрать выделенные строки из списка (Delete)",
    "col.pbo": "PBO",
    "col.where": "Куда",
    "col.state": "Состояние",

    "where.title": "Куда",
    "where.hint": "Папка мода или его Addons. PBO получат имена папок модов",
    "where.pick": "Выбрать папку",
    "where.other": "→ {path}",
    "where.default": "по умолчанию",
    "where.cell": "{path}\nЩелчок — своя папка для этого PBO",

    "opt.temp": "Использовать temp",
    "opt.temp.tip": "Повторная запаковка берёт неизменённое из temp и идёт быстро. Выключено — "
                    "всё собирается заново",
    "opt.binarize": "Бинаризировать модели",
    "opt.binarize.tip": "Модели переводятся из MLOD в ODOL. Выключено — модели и их model.cfg "
                        "кладутся в PBO как есть",
    "opt.rapify": "Рапифицировать текст",
    "opt.rapify.tip": "config.cpp, .rvmat и .bisurf переводятся в двоичный вид. Выключено — "
                      "кладутся текстом вместе с .h и .hpp",
    "opt.force": "Игнорировать ошибки",
    "opt.force.tip": "Ошибки и предупреждения остаются в отчёте, но мод пакуется. Файл, который "
                     "не собрался, в PBO не попадает. Остановит только ошибка config.cpp — "
                     "на ней останавливается и Addon Builder",

    "main.settings": "Настройки",
    "main.logs": "Логи",
    "main.pack": "Запаковать ({count})",
    "main.pack.none": "Запаковать",
    "main.stop": "Остановить",
    "main.stopping": "Останавливаю после текущей задачи…",

    "row.change_source": "Выбрать другую папку мода…",
    "row.own_target": "Своя папка для этого PBO…",
    "row.set_target": "Писать в папку по умолчанию",
    "row.open_source": "Открыть папку мода",
    "row.open_target": "Открыть папку PBO",
    "row.open_log": "Открыть лог",
    "row.remove": "Убрать из списка",

    "state.unknown": "—",
    "state.checking": "проверяю…",
    "state.never": "ещё не собирался",
    "state.clean": "изменений нет",
    "state.clean_built": "изменений нет · запакован в {time}",
    "state.changed": "изменено: {count}",
    "state.queued": "в очереди",
    "state.building": "запаковывается",
    "state.built": "запакован в {time}",
    "state.same": "не изменился",
    "state.failed": "ошибок: {count}",
    "state.forced": "запакован с ошибками: {count}, в {time}",
    "state.error": "не собран",
    "state.no_source": "нет папки мода",
    "state.no_target": "не указано, куда",
    "state.open_logs": "Открыть логи этого PBO",

    "stage.скан": "просмотр",
    "stage.копирование": "копирование",
    "stage.сборка": "сборка",
    "stage.texHeaders": "индекс текстур",
    "stage.ссылки": "проверка ссылок",
    "stage.упаковка": "запись PBO",
    "stage.подпись": "подпись PBO",
    "progress.stage": "{pbo}: {stage}",
    "progress.count": "{pbo}: {stage} {done} из {total}",

    "log.done": "Готово: без ошибок {ok} из {total}",
    "log.done.bad": "Готово: без ошибок {ok} из {total}, с ошибками {bad}",
    "log.cancelled": "Остановлено. Собранное лежит в temp, PBO не тронуты.",
    "log.more": "  …подробно — «Логи»",
    "log.removed": "Убрано из списка: {names}.",
    "log.undo": "Вернуть (Ctrl+Z)",
    "log.restored": "Возвращено в список: {names}.",
    "log.nothing": "Отметь хотя бы один мод и укажи, куда паковать",

    "logs.title": "Логи запаковки",
    "logs.empty": "Здесь будут логи после первой запаковки",
    "logs.full": "Полный лог",
    "logs.summary.ok": "{pbo}: без ошибок, предупреждений {warnings}",
    "logs.summary.bad": "{pbo}: ошибок {errors}, предупреждений {warnings}",
    "logs.summary.exc": "{pbo}: не собран — {text}",
    "logs.section.errors": "Ошибки",
    "logs.section.warnings": "Предупреждения",
    "logs.section.infos": "Сведения",
    "logs.mark": "Пометить на модели",
    "logs.search": "Поиск по логу (Ctrl+F)",
    "logs.search.count": "{i} из {n}",
    "logs.search.none": "не найдено",
    "logs.marked": "помечено: селекция {name}",
    "logs.mark_failed": "не помечено: {text}",
    "logs.section.decisions": "Решения тулзы",
    "logs.clean": "Ошибок и предупреждений нет. Полный список — «Полный лог».",
    "logs.no_file": "Файла лога нет: {path}",
    "logs.open_file": "Открыть файл",

    "settings.title": "Настройки",
    "settings.tab.build": "Сборка",
    "settings.tab.checks": "Проверки",
    "settings.tab.fixes": "Исправления",
    "fixes.note": "Что сборщик исправляет сам. «В PBO» — исходник не меняется. «В PBO и в "
                  "исходнике» — исходник тоже исправляется, прежний файл сохраняется в "
                  "temp\\.kr_backup. Исходник правится, только если PBO от этого не меняется.",
    "checks.note": "Ошибка останавливает запаковку, остальное только видно в отчёте. Общие для "
                   "всех модов; уровни в .kr_build.json мода дополняют эти.",
    "checks.all": "Все виды",
    "checks.all.default": "Вернуть по умолчанию",
    "checks.all.error": "Все — ошибки",
    "checks.all.warning": "Все — предупреждения",
    "checks.all.info": "Все — сведения",
    "checks.all.off": "Выключить все",
    "checks.all.confirm.title": "{action}?",
    "checks.all.confirm": "Уровни всех видов будут заменены. Файл, который собрать нельзя, "
                          "останется ошибкой.",
    "checks.all.apply": "Применить",
    "checks.locked_part": "Файл, который собрать нельзя вовсе, — ошибка при любом уровне",
    "checks.own": "Отдельно задано в файле настроек: {codes}",
    "checks.error": "Ошибка",
    "checks.warning": "Предупреждение",
    "checks.info": "Сведения",
    "checks.off": "Выключено",
    "settings.file": "Общие для всех модов. Настройки в .kr_build.json мода сильнее.",
    "settings.theme": "Тема оформления",
    "settings.theme.desc": "Системная — как в Windows",
    "settings.theme.auto": "Системная",
    "settings.theme.light": "Светлая",
    "settings.theme.dark": "Тёмная",
    "settings.odol.off": "Не действует: в главном окне выключено «Бинаризировать модели»",
    "settings.odol": "Версия моделей",
    "settings.odol.desc": "Модели запишутся в формате, который понимает эта версия игры",
    "settings.odol.55": "1.29 (v55)",
    "settings.odol.56": "1.30 (v56)",
    "settings.jobs": "Параллельная сборка",
    "settings.jobs.desc": "Сколько файлов собирается одновременно. 0 — по числу ядер процессора",
    "settings.temp": "Папка temp",
    "settings.temp.desc": "Готовые к упаковке файлы. Повторная запаковка берёт неизменённое "
                          "отсюда и идёт быстро",
    "settings.exclude": "Не класть в PBO",
    "settings.outside": "Игнорировать пути вне этого PBO",
    "settings.outside.desc": "Ссылки на другие моды и ваниль не проверяются, ссылки внутри "
                             "мода — всегда. Для сборки, когда нужных модов нет на P:",
    "settings.key": "Ключ подписи",
    "settings.key.desc": "Приватный ключ .biprivatekey. Его .bikey из той же папки кладут "
                         "на сервер в keys — им сервер проверяет подписи",
    "settings.key.pick": "Выбрать ключ",
    "settings.key.create": "Создать ключ",
    "settings.key.none": "не выбран",
    "settings.key.created": "Созданы {prv} и {pub} в папке {folder}. Приватный ключ "
                            "никому не передавать: им подписывают",
    "settings.key.public": "{name} — публичный ключ (.bikey): подписывают приватным "
                           ".biprivatekey",
    "settings.key.unreadable": "Ключ не читается: {text}",
    "settings.sign": "Подписывать PBO после запаковки",
    "settings.sign.desc": "Рядом с каждым PBO — подпись <pbo>.<ключ>.bisign",
    "settings.sign.need_key": "Рядом с каждым PBO — подпись <pbo>.<ключ>.bisign. "
                              "Сначала выберите или создайте ключ",
    "settings.on": "Да",
    "settings.off": "Нет",
    "settings.exclude.desc": "Маски через точку с запятой: *.psd; *.blend. "
                             "Добавляются к встроенному списку",
    "settings.error": "Не сохранено: {text}",
    "settings.close": "Закрыть",

    "dialog.ok": "Готово",
    "dialog.cancel": "Отмена",
    "dialog.pick.folder": "Папка мода",
    "dialog.pick.where": "Куда паковать",
    "dialog.pick.row_where": "Своя папка для этого PBO",
    "dialog.pick.temp": "Папка temp",
}


def T(key: str, **kw) -> str:
    """Текст по ключу. Неизвестный ключ — сам ключ: видно и ищется, а не падает."""
    text = TEXT.get(key, key)
    return text.format(**kw) if kw else text
