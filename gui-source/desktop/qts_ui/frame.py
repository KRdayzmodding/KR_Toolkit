# -*- coding: utf-8 -*-
"""Главное окно тулзы со своей шапкой — как у KR QTS.

Системная рамка Windows в тёмной теме остаётся белой и со значком по умолчанию
(замечание юзера 23.10.2026, снимок шапки [KR] Sound Converter). QTS строит
главное окно на FluentWindow: шапку рисует qfluentwidgets — в цвет темы, со
значком и названием. Здесь то же без навигации: FluentWidget, фон из токенов,
содержимое — в `self.body` под шапкой.

Значок, как в QTS (ui/main_window.py, _apply_icon): в шапке — под тему (фон
наш, известен точно), на панели задач и в Alt+Tab — серый 128, читаемый и на
светлом, и на тёмном чужом фоне.
"""
from __future__ import annotations

import sys


from PySide6.QtGui import QColor, QCursor, QGuiApplication, QIcon, QPalette
from PySide6.QtWidgets import QApplication, QVBoxLayout, QWidget
from qfluentwidgets import FluentIconBase, FluentWidget, qconfig

from qts_ui import tokens

#: размеры, которые реально запрашиваются: 16 — трей и системные места, 18 —
#: шапка FluentWidget, 32 — панель задач, 48/256 — проводник и Alt+Tab
_SIZES = (16, 18, 20, 24, 32, 48, 64, 128, 256)
#: серый значка вне окна — тот же, что у QTS (контраст ≥ 3:1 на всех четырёх фонах)
_OUTSIDE_GREY = 128


def tool_icon(icon: FluentIconBase, color: QColor) -> QIcon:
    """Значок тулзы одним цветом, отрисованный под каждый запрашиваемый размер."""
    src = icon.icon(color=color)
    out = QIcon()
    for size in _SIZES:
        out.addPixmap(src.pixmap(size, size))
    return out


class ToolWindow(FluentWidget):
    """Главное окно тулзы: своя шапка в цвет темы, значок, фон из токенов."""

    def __init__(self, icon: FluentIconBase, parent=None, image: str = "tool"):
        super().__init__(parent)
        self._icon = icon
        #: силуэт иконки приложения (kr_icons): у тулзы — знак и половина значка её карточки (25.10.2026), у DevToolkit — знак
        #: с половиной шестерёнки (юзер 24.10.2026). Нет файла — значок FluentIcon
        self._image = image
        # обе темы сразу: библиотека переключает фон сама (tokens — копия QTS, свой
        # «цвет для темы» туда не добавляем, берём таблицы как есть)
        self.setCustomBackgroundColor(QColor(tokens._LIGHT["window"]), QColor(tokens._DARK["window"]))
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, self.titleBar.height(), 0, 0)
        lay.setSpacing(0)
        self.body = QWidget(self)
        lay.addWidget(self.body)
        self.titleBar.raise_()
        self._apply_icon()
        self._paint_background()
        qconfig.themeChanged.connect(self._on_theme)
        self._centered = False

    def showEvent(self, event) -> None:
        # первый показ — по центру монитора; дальше окно стоит, где его оставили
        if not self._centered:
            self._centered = True
            self.center_on_screen()
        super().showEvent(event)

    def center_on_screen(self) -> None:
        """Центр окна — в центр рабочей области монитора, где сейчас курсор.

        Без этого место выбирает Windows своим каскадом, и окно открывается
        со сдвигом (замечание юзера 24.10.2026). Монитор — тот, где курсор:
        там человек только что щёлкнул по exe или по карточке лаунчера. Окно
        больше рабочей области прижимается к её левому верхнему углу, а не
        уезжает шапкой за край экрана.
        """
        screen = QGuiApplication.screenAt(QCursor.pos()) or self.screen() or QGuiApplication.primaryScreen()
        if screen is None:
            return
        area = screen.availableGeometry()
        frame = self.frameGeometry()
        frame.moveCenter(area.center())
        x = max(area.left(), min(frame.left(), area.right() - frame.width() + 1))
        y = max(area.top(), min(frame.top(), area.bottom() - frame.height() + 1))
        self.move(x, y)

    def _on_theme(self, *_args) -> None:
        self._apply_icon()
        self._paint_background()

    def _apply_icon(self) -> None:
        import kr_icons
        if kr_icons.available(self._image):
            outside = kr_icons.outside_icon(self._image)
            inside = kr_icons.app_icon(self._image, tokens.dark())
        else:
            outside = tool_icon(self._icon, QColor(_OUTSIDE_GREY, _OUTSIDE_GREY, _OUTSIDE_GREY))
            inside = tool_icon(self._icon, QColor(tokens.color("text")))
        self.setWindowIcon(outside)
        QApplication.instance().setWindowIcon(outside)
        # строго после setWindowIcon: оно само шлёт в шапку свою иконку по сигналу
        # windowIconChanged, и вариант под тему должен лечь поверх (так же в QTS)
        self.titleBar.setIcon(inside)

    def _paint_background(self) -> None:
        """Фон окна цветом темы и на уровне Windows: иначе до первой отрисовки
        система стирает окно белой кистью класса, и в тёмной теме мелькает белое
        (то же в QTS, MainWindow._paint_background)."""
        col = QColor(tokens.color("window"))
        pal = self.palette()
        pal.setColor(QPalette.ColorRole.Window, col)
        self.setPalette(pal)
        if sys.platform != "win32":
            return
        try:
            import ctypes
            from ctypes import wintypes
            user32, gdi32 = ctypes.windll.user32, ctypes.windll.gdi32
            gdi32.CreateSolidBrush.argtypes = [wintypes.COLORREF]
            gdi32.CreateSolidBrush.restype = wintypes.HANDLE
            brush = gdi32.CreateSolidBrush(col.blue() << 16 | col.green() << 8 | col.red())
            setter = getattr(user32, "SetClassLongPtrW", None) or user32.SetClassLongW
            setter.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_void_p]
            setter.restype = ctypes.c_void_p
            setter(int(self.winId()), -10, brush)              # GCLP_HBRBACKGROUND
        except (OSError, AttributeError):
            pass
