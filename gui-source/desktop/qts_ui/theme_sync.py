# -*- coding: utf-8 -*-
"""Тема — за общим выбором: открытое окно перекрашивается сразу.

Решение юзера 27.10.2026: тему меняют на странице «Настройки» DevToolkit, и все
тулзы её подхватывают, не только те, что запустят после. Выбор лежит в
``%USERPROFILE%\\.kr_devtoolkit\\theme.json`` (``kr_state``); окно следит за
папкой — файл заменяется целиком, и слежение за самим файлом после замены
пропадает.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from PySide6.QtCore import QFileSystemWatcher, QObject, QTimer

import kr_state

#: в папке состояния пишут и другие тулзы — читаем выбор, когда запись утихла
SETTLE_MS = 150


def theme_of(name: str):
    from qfluentwidgets import Theme
    return {"auto": Theme.AUTO, "light": Theme.LIGHT, "dark": Theme.DARK}[name]


class ThemeFollower(QObject):
    def __init__(self, parent: QObject, root: Optional[Path] = None):
        super().__init__(parent)
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.setInterval(SETTLE_MS)
        self.timer.timeout.connect(self.apply)
        self.watcher = QFileSystemWatcher(self)
        self.watcher.directoryChanged.connect(lambda *_: self.timer.start())
        self.root = Path()
        self.watch(root)

    def watch(self, root: Optional[Path] = None) -> None:
        """Следить за папкой выбора (тест подменяет её на свою)."""
        if self.watcher.directories():
            self.watcher.removePaths(self.watcher.directories())
        self.root = Path(root or kr_state.STATE_DIR)
        try:
            self.root.mkdir(parents=True, exist_ok=True)
        except OSError:
            pass
        self.watcher.addPath(str(self.root))

    def apply(self) -> None:
        """Выбор из файла — в окна, если он не тот, что сейчас."""
        from qfluentwidgets import qconfig, setTheme
        wanted = theme_of(kr_state.theme_name(self.root))
        if qconfig.get(qconfig.themeMode) != wanted:
            setTheme(wanted)


def follow(app: QObject, root: Optional[Path] = None) -> ThemeFollower:
    """Подписать приложение на общий выбор темы; живёт, пока живёт `app`.

    Слежение одно на приложение: повторный вызов только меняет папку, иначе
    второе слежение перекрашивало бы окна по своему выбору поверх первого.
    """
    follower = app.findChild(ThemeFollower)
    if follower is None:
        return ThemeFollower(app, root)
    follower.watch(root)
    return follower
