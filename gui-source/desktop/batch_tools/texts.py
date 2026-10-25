# -*- coding: utf-8 -*-
"""Все строки окон массовых тулз — в одном месте (свод правил интерфейсов, п. 60).

Ключи буквальные (п. 66): у каждой тулзы свои — textures.*, models.*, debin.*.
"""
from __future__ import annotations

TEXT = {
    # --- по тулзам
    "textures.inputs": "Картинки и текстуры",
    "textures.drop": "Перетащите сюда картинки (png, tga, dds, jpg), текстуры (paa, edds)\n"
                     "или папки — вложенные папки тоже просматриваются",
    "textures.pick": "Картинки и текстуры",
    "models.inputs": "Модели",
    "models.drop": "Перетащите сюда P3D или папки с ними —\nвложенные папки тоже просматриваются",
    "models.pick": "Модели P3D",
    "debin.inputs": "Бинарные файлы",
    "debin.drop": "Перетащите сюда config.bin, .rvmat и другие бинарные файлы\n"
                  "или папки — вложенные папки тоже просматриваются",
    "debin.pick": "Бинарные файлы",
    "pbo.inputs": "PBO",
    "pbo.drop": "Перетащите сюда PBO или папки с ними —\n"
                "каждый распакуется в папку рядом: конфиги текстом, P3D в MLOD, model.cfg",
    "pbo.pick": "PBO",
    "anm.inputs": "Анимации",
    "anm.drop": "Перетащите сюда ANM, TXA или папки с ними —\n"
                "ANM станет TXA, TXA станет ANM; только сам файл, без ASI и других ANM",
    "anm.pick": "Анимации ANM и TXA",

    # --- общее
    "inputs.add_files": "Добавить файлы",
    "inputs.add_folder": "Добавить папку",
    "inputs.remove": "Убрать из списка",
    "inputs.pick_folder": "Папка",

    "opt.delete": "Удалять исходник",
    "opt.delete.desc": "Насовсем, после того как результат записан",
    "opt.overwrite": "Перезаписывать готовые результаты",
    "opt.overwrite.desc": "Прежние — копией в .kr_devtoolkit\\backup",
    "opt.image_to": "Картинки →",
    "opt.image_to.desc": "PAA — для моделей и материалов, EDDS — для интерфейса",
    "opt.edds_format": "Сжатие EDDS",
    "opt.edds_format.desc": "BGRA8 — без потерь, DXT — меньше файл",
    "opt.texture_to": "PAA и EDDS →",
    "opt.texture_to.desc": "Во что распаковывать текстуры",
    "opt.suffix": "Суффикс MLOD",
    "opt.suffix.desc": "x.p3d → x_mlod.p3d; пусто — на место ODOL, а ODOL копией в backup",
    "opt.suffix.locked": "Исходник удаляется — MLOD ложится на его место",
    "opt.layout": "Раскладка",
    "opt.layout.desc": "По префиксу: x\\KR\\мод\\…, как видит движок; в папку PBO: файлы прямо в x\\",
    "layout.prefix": "По префиксу",
    "layout.flat": "В папку PBO",
    "fmt.paa": "PAA", "fmt.edds": "EDDS", "fmt.png": "PNG", "fmt.tga": "TGA", "fmt.dds": "DDS",
    "fmt.bgra8": "BGRA8", "fmt.dxt5": "DXT5", "fmt.dxt1": "DXT1",
    "switch.on": "Да", "switch.off": "Нет",

    "settings.title": "Настройки",
    "files.title": "Файлы",
    "files.all": "Отметить все",
    "files.none": "Снять все",
    "col.state": "Состояние",
    "col.src": "Файл",
    "col.out": "Результат",
    "out.deleted": " · исходник удалён",

    "state.planned": "сделать",
    "state.overwrite": "перезаписать",
    "state.skipped": "пропуск",
    "state.converted": "готово",
    "state.warning": "готово, смотреть",
    "state.failed": "ошибка",

    "summary.empty": "Подходящих файлов не найдено",
    "summary.plan": "Файлов: {total} · сделать {todo} · пропуск {skipped}",
    "summary.done": "Сделано {converted}, пропущено {skipped}, ошибок {failed}",
    "summary.stopped": " · остановлено",
    "summary.problem": "Не взять: {text}",
    "summary.cli_failed": "Командная строка не отвечает: {text}",

    "report.title": "Отчёт",

    "main.run": "Обработать: {count}",
    "main.run.none": "Нечего обрабатывать",
    "main.run.nothing_chosen": "Ничего не отмечено",
    "main.stop": "Остановить",
    "progress": "{done} из {total}",
    "progress.step": "{done} из {total} · {name}: {text}",
    "planning": "смотрю, что обработать…",
}


def T(key: str, **kw) -> str:
    """Текст по ключу. Неизвестный ключ — сам ключ: видно и ищется, а не падает."""
    text = TEXT.get(key, key)
    return text.format(**kw) if kw else text
