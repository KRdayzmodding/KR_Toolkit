# -*- coding: utf-8 -*-
"""Журнал перекрашивается под новую тему.

Строки журнала пишутся HTML-ом с цветом роли, взятым в момент записи
(tokens: «задним числом Qt их не перекрасит»). Пока тема менялась только в
настройках самой тулзы, с этим жили. С 28.10.2026 тема — общая и меняется из
DevToolkit на лету, и в светлой теме журнал оставался в тёмных цветах:
зелёный «Готово» 1,8:1, жёлтое предупреждение 1,2:1 против нормы 4,5:1
(жалоба юзера 28.10.2026: «не все хорошо читается»).

Перекраска — по ролям: цвет, совпадающий с ролью другой темы, становится той
же ролью текущей. Чужие цвета (не из tokens) не трогаются.
"""
from __future__ import annotations

from PySide6.QtGui import QColor, QTextCursor, QTextDocument, QTextFormat

from . import tokens


def _role_map() -> dict:
    """Цвет роли в другой теме → цвет той же роли в текущей."""
    now, other = (tokens._DARK, tokens._LIGHT) if tokens.dark() else (tokens._LIGHT, tokens._DARK)
    out = {}
    for role, value in other.items():
        out.setdefault(QColor(value).name(), QColor(now[role]))
    return out


def retint(document: QTextDocument) -> int:
    """Цвета ролей прежней темы в документе — на текущую. Возвращает число перекрашенных кусков."""
    mapping = _role_map()
    changed = []
    block = document.begin()
    while block.isValid():
        it = block.begin()
        while not it.atEnd():
            frag = it.fragment()
            if frag.isValid():
                fmt = frag.charFormat()
                if fmt.hasProperty(QTextFormat.Property.ForegroundBrush):
                    new = mapping.get(fmt.foreground().color().name())
                    if new is not None:
                        changed.append((frag.position(), frag.length(), new))
            it += 1
        block = block.next()
    cursor = QTextCursor(document)
    cursor.beginEditBlock()
    for position, length, color in changed:
        cursor.setPosition(position)
        cursor.setPosition(position + length, QTextCursor.KeepAnchor)
        fmt = cursor.charFormat()
        fmt.setForeground(color)
        cursor.mergeCharFormat(fmt)
    cursor.endEditBlock()
    return len(changed)
