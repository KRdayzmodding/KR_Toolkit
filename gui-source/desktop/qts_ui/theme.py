# Скопировано из KR_ServerManager/ui/theme.py (рабочая копия на 22.10.2026, последний коммит QTS deba8ad).
# Взята только часть без иконки приложения (та завязана на файлы QTS). Править синхронно с оригиналом.
"""Общая тёмная/светлая тема для самописных диалогов.

qfluentwidgets красит под текущую Theme только свои собственные окна
(MessageBox/MessageBoxBase вызывают FluentStyleSheet.DIALOG.apply() у себя
в __init__) — обычный QDialog остаётся с системным (светлым) фоном даже при
включённой тёмной теме, а дочерние BodyLabel/CaptionLabel всё равно красятся
в светлый текст глобальной таблицей стилей — получается светлый текст на
светлом фоне, нечитаемо. Все свои диалоги в приложении наследуются от
ThemedDialog вместо голого QDialog, чтобы получать тот же фон/цвет текста,
что и у MessageBox.
"""
from __future__ import annotations

from PySide6.QtWidgets import QDialog, QWizard
from qfluentwidgets import FluentStyleSheet, isDarkTheme, setCustomStyleSheet

_LIGHT_BG = "white"
_DARK_BG = "rgb(43, 43, 43)"


def link_color() -> str:
    """Цвет ссылки под текущую тему: оба тона того же оранжевого семейства,
    что и акцент приложения, и оба дают 5.3 к одному."""
    return "#e08a3c" if isDarkTheme() else "#a3571a"


def link_html(url: str, text: str = "") -> str:
    """Ссылка с явным цветом. Через таблицу стилей QLabel цвет ссылки задать
    нельзя — Qt красит её сам, пока цвет не указан прямо в теге."""
    return f'<a href="{url}" style="color:{link_color()};">{text or url}</a>'


def _page_qss(bg: str) -> str:
    return (f"QWizardPage{{background-color:{bg};}}"
            f"QWizardPage QGroupBox{{background-color:transparent;}}")


class ThemedDialog(QDialog):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        FluentStyleSheet.DIALOG.apply(self)


class ThemedWizard(QWizard):
    """QWizard — тоже QDialog в Qt, поэтому тот же DIALOG.qss красит фон окна;
    страницы приходится красить отдельно (см. _page_qss)."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setWizardStyle(QWizard.WizardStyle.ClassicStyle)
        FluentStyleSheet.DIALOG.apply(self)
        setCustomStyleSheet(self, _page_qss(_LIGHT_BG), _page_qss(_DARK_BG))
