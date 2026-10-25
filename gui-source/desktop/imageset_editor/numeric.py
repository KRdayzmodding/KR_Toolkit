# -*- coding: utf-8 -*-
"""Числовое поле с выражениями, как в Blender: «2048+256» → 2304.

Юзер 23.10.2026. Без стрелок (ни всплывающих, ни встроенных). Значение
применяется по Enter или при уходе из поля, а не на каждую нажатую клавишу:
иначе рамка на холсте прыгала бы, пока выражение не дописано.

Выражение считается разбором дерева, а не eval: допускаются только числа,
`+ - * / // %`, унарный минус и скобки. Результат округляется до целого.
"""
from __future__ import annotations

import ast
import operator
import re
from typing import Optional

from PySide6.QtGui import QValidator
from qfluentwidgets import SpinBox

_ALLOWED = re.compile(r"^[0-9+\-*/%().\s]*$")
_BIN = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
        ast.Div: operator.truediv, ast.FloorDiv: operator.floordiv, ast.Mod: operator.mod}
_UNARY = {ast.UAdd: operator.pos, ast.USub: operator.neg}


def evaluate(text: str) -> Optional[int]:
    """Значение выражения, округлённое до целого; None — не выражение."""
    text = text.strip()
    if not text or not _ALLOWED.match(text):
        return None
    try:
        tree = ast.parse(text, mode="eval")
    except SyntaxError:
        return None

    def walk(node):
        if isinstance(node, ast.Expression):
            return walk(node.body)
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            return node.value
        if isinstance(node, ast.BinOp) and type(node.op) in _BIN:
            return _BIN[type(node.op)](walk(node.left), walk(node.right))
        if isinstance(node, ast.UnaryOp) and type(node.op) in _UNARY:
            return _UNARY[type(node.op)](walk(node.operand))
        raise ValueError("не арифметика")

    try:
        return int(round(walk(tree)))
    except (ValueError, ZeroDivisionError, OverflowError):
        return None


class ExprSpinBox(SpinBox):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setSymbolVisible(False)
        self.setKeyboardTracking(False)          # значение — по Enter / уходу из поля

    def validate(self, text: str, pos: int):
        if not _ALLOWED.match(text):
            return QValidator.Invalid, text, pos
        value = evaluate(text)
        if value is None or not self.minimum() <= value <= self.maximum():
            return QValidator.Intermediate, text, pos        # дописывается — пускаем
        return QValidator.Acceptable, text, pos

    def valueFromText(self, text: str) -> int:
        value = evaluate(text)
        return self.value() if value is None else value

    def fixup(self, text: str) -> str:
        """Недописанное или вне пределов при уходе из поля — прежнее значение, не мусор."""
        value = evaluate(text)
        if value is None:
            return self.textFromValue(self.value())
        return self.textFromValue(max(self.minimum(), min(self.maximum(), value)))
