# -*- coding: utf-8 -*-
"""Настройки Imageset Editor и вопрос о несохранённых файлах (юзер 25.10.2026).

Настройки — как у Project Builder: строки «название, пояснение, контрол»,
пишутся в файл состояния на каждое изменение, кнопка внизу только закрывает.
"""
from __future__ import annotations

from typing import List, Optional

from PySide6.QtWidgets import QHBoxLayout, QVBoxLayout
from qfluentwidgets import BodyLabel, CaptionLabel, CompactSpinBox, MessageBoxBase, PushButton, SubtitleLabel, SwitchButton

import history
from qts_ui import tokens
from qts_ui.rows import setting_row, shrink
from qts_ui.theme import ThemedDialog
from texts import T


class SettingsDialog(ThemedDialog):
    def __init__(self, store, parent=None):
        super().__init__(parent)
        self.store = store
        self.setWindowTitle(T("settings.title"))
        outer = QVBoxLayout(self)
        outer.setContentsMargins(tokens.SPACE_L, tokens.SPACE_M, tokens.SPACE_L, tokens.SPACE_M)
        outer.setSpacing(0)

        # состояние «включено/выключено» — переключатель (п. 15)
        self.autosave = SwitchButton(self)
        self.autosave.setOnText(T("settings.on"))
        self.autosave.setOffText(T("settings.off"))
        self.autosave.setChecked(store.autosave)
        self.autosave.checkedChanged.connect(self._set_autosave)
        outer.addWidget(setting_row(T("settings.autosave"), T("settings.autosave.desc"), self.autosave))

        self.steps = CompactSpinBox(self)
        self.steps.setRange(history.LIMIT_MIN, history.LIMIT_MAX)
        self.steps.setValue(store.history)
        self.steps.valueChanged.connect(self._set_steps)
        outer.addWidget(setting_row(T("settings.history"),
                                    T("settings.history.desc", default=history.LIMIT_DEFAULT,
                                      max=history.LIMIT_MAX), self.steps))
        outer.addStretch(1)

        bottom = QHBoxLayout()
        bottom.addStretch(1)
        self.close_btn = PushButton(T("settings.close"), self)
        self.close_btn.setDefault(True)
        self.close_btn.clicked.connect(self.accept)
        bottom.addWidget(self.close_btn)
        outer.addSpacing(tokens.SPACE_M)
        outer.addLayout(bottom)
        # две строки: ширина — стандартная форма, высота — по содержимому, без пустого поля
        self.resize(tokens.WIN_M[0], self.sizeHint().height())

    def _set_autosave(self, on: bool) -> None:
        self.store.autosave = bool(on)
        self.store.save()

    def _set_steps(self, value: int) -> None:
        self.store.history = history.clamp(value)
        self.store.save()


class UnsavedBox(MessageBoxBase):
    """Закрытие с несохранёнными правками при выключенном автосохранении:
    «Сохранить» / «Не сохранять» / «Отмена». choice — "save", "discard" или None."""

    def __init__(self, names: List[str], parent):
        super().__init__(parent)
        self.choice: Optional[str] = None
        title = (T("unsaved.title.one", name=names[0]) if len(names) == 1
                 else T("unsaved.title.many", count=len(names)))
        self.viewLayout.addWidget(SubtitleLabel(title, self))
        if len(names) > 1:
            self.viewLayout.addWidget(shrink(BodyLabel("\n".join(names), self)))
        note = shrink(CaptionLabel(T("unsaved.note"), self))
        note.setTextColor(tokens.color("text_dim"), tokens.color("text_dim"))
        self.viewLayout.addWidget(note)
        self.widget.setMinimumWidth(440)
        # порядок как у диалогов библиотеки: главная кнопка слева, отказ справа (п. 20)
        self.yesButton.setText(T("unsaved.save"))
        self.discard = PushButton(T("unsaved.discard"), self.buttonGroup)
        self.buttonLayout.insertWidget(1, self.discard, 1)
        self.cancelButton.setText(T("dialog.cancel"))
        # свою связь — рядом с библиотечной, не вместо: голый disconnect() снимает и её
        # (окно обновлений так падало при закрытии, 25.10.2026); окно закрывает библиотека
        self.yesButton.clicked.connect(lambda: setattr(self, "choice", "save"))
        self.discard.clicked.connect(self._discard)

    def _discard(self) -> None:
        self.choice = "discard"
        self.accept()
