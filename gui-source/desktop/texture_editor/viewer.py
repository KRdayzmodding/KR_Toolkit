# -*- coding: utf-8 -*-
"""Вкладка «Просмотр текстуры» в ``texture_editor``.

Показывает PAA, EDDS, PNG, TGA, DDS и прочее, что читает Pillow. Набор возможностей
взят не с потолка, а с ванильного TexView: каналы по отдельности, мипы, зум,
и снизу — максимум, среднее и значение под курсором.

Чем отличается от обычного просмотрщика картинок. Служебные карты в RGB
бессмысленны: у ``_smdi`` красный залит белым, данные в зелёном и синем, у
``_as`` содержателен один зелёный. Поэтому переключение каналов здесь не
украшение, а основной способ смотреть.

Страница, а не окно: меню она отдаёт главному окну, а её сочетания клавиш
работают, только пока фокус внутри неё. Иначе стрелки в полях соседней
вкладки листали бы здесь мипы.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import List, Optional

import numpy as np
from PIL import Image

_HERE = Path(__file__).resolve().parent
_ROOT = _HERE.parents[1]
for _p in (str(_HERE), str(_ROOT), str(_HERE.parent)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from PySide6.QtCore import QSettings, Qt, Signal                     # noqa: E402
from PySide6.QtGui import QAction, QActionGroup, QColor, QKeySequence  # noqa: E402
from PySide6.QtWidgets import (                                      # noqa: E402
    QApplication, QButtonGroup, QFileDialog, QFormLayout, QHBoxLayout, QLabel,
    QStackedWidget, QVBoxLayout, QWidget,
)
from qfluentwidgets import (                                         # noqa: E402
    BodyLabel, CaptionLabel, ComboBox, DoubleSpinBox, PushButton, SimpleCardWidget,
    TogglePushButton,
)

import look                                                          # noqa: E402
import remote as te                                                  # noqa: E402
from qts_ui import tokens                                            # noqa: E402
from qts_ui.theme import ThemedDialog                                # noqa: E402
from canvas import Canvas                                            # noqa: E402

# --------------------------------------------------------------------------
# Текст — весь здесь
# --------------------------------------------------------------------------

TEXT = {
    "tab": "Просмотр текстуры",

    "open": "Открыть…",
    "reload": "Обновить",
    "save_as": "Сохранить как…",
    "next_file": "Следующий файл",
    "prev_file": "Предыдущий файл",
    "recent": "Недавние",
    "recent_empty": "Недавних пока нет",

    "menu_mip": "Мип",
    "mip_prev": "Крупнее",
    "mip_next": "Мельче",
    "mip_label": "Мип",
    "mip_item": "%d — %dx%d%s",
    "mip_packed": ", сжат",

    "menu_edit": "Правка",
    "smdi": "Прогнать фильтр SMDI…",
    "smdi_sp": "SpecularPower из rvmat:",
    "smdi_backup": "Сделать копию оригинала перед прогоном?",
    "smdi_exists": ("Копия этого файла уже лежит в %s.\n\n"
                    "Перезаписать её нынешним состоянием файла?"),
    "smdi_done": "Прогнан с sp=%g. Оригинал — в %s",
    "smdi_done_nobackup": "Прогнан с sp=%g, без копии",
    "smdi_skipped": "Уже прогнан — метка на месте, второй раз не трогаем",
    "smdi_refused": "Не прогнан: %s",
    "invert": "Инвертировать зелёный канал",
    "inverted": "Зелёный перевёрнут. Оригинал — в %s",
    "split": "Разложить каналы по файлам",

    "compose": "Собрать карту SMDI…",
    "compose_title": "Собрать карту SMDI",
    "compose_note": ("Зелёный канал карты — яркость блика, синий — его резкость.\n"
                     "Открытый файл пойдёт в один из них, второй возьмём рядом."),
    "compose_role": "Открытый файл — это",
    "role_intensity": "Яркость",
    "role_sharpness": "Резкость",
    "compose_second": "Второй канал",
    "second_file": "Файл",
    "second_value": "Число",
    "compose_pick": "Выбрать…",
    "compose_go": "Собрать",
    "composed": "Собрано: %s",
    "compose_nofile": "Не выбран файл второго канала",

    "adjust": "Поправить блик…",
    "adjust_title": "Поправить блик",
    "adjust_note": ("Яркость — насколько сильно блестит, резкость — насколько "
                    "узкий блик.\nУ ванильных карт яркость чаще всего около 8%."),
    "adjust_intensity": "Яркость",
    "adjust_sharpness": "Резкость",
    "keep": "Как есть",
    "multiply": "Умножить",
    "set_material": "Материал",
    "set_value": "Числом",
    "adjust_go": "Применить",
    "adjusted": "Блик поправлен. Оригинал — в %s",
    "split_done": "Записано рядом: %s",
    "split_flat": ". Однотонные каналы пропущены: %s",
    "split_nothing": "Писать нечего: все каналы однотонные",
    "edit_failed": "Правка не сделана",

    "menu_view": "Вид",
    "channel_label": "Показывать",
    "zoom_in": "Увеличить",
    "zoom_out": "Уменьшить",
    "zoom_fit": "Вписать",
    "zoom_actual": "Сто процентов",
    "grid": "Границы блоков DXT",
    "checker": "Шахматка под прозрачным",

    "ch_rgba": "RGBA",
    "ch_rgb": "RGB",
    "ch_alpha": "Альфа",
    "ch_r": "Канал R",
    "ch_g": "Канал G",
    "ch_b": "Канал B",

    "stat_max": "Макс.",
    "stat_avg": "Средн.",
    "stat_none": "—",
    "cursor": "%d, %d",
    "value": "%d, %d, %d   альфа %d",

    "empty": ("Откройте текстуру: PAA, EDDS, PNG, TGA или DDS.\n"
              "Файл можно просто перетащить в это окно."),
    "size_of": "%dx%d из %dx%d",
    "weight_kb": "%d КБ",
    "weight_mb": "%.1f МБ",
    "zoom_percent": "%d%%",
    "ready": "Готово",
    "open_title": "Открыть текстуру",
    "open_filter": "Текстуры (*.paa *.edds *.png *.tga *.dds *.bmp *.tif *.tiff *.jpg);;Все файлы (*)",
    "save_title": "Сохранить как",
    "saved": "Сохранено: %s",
    "packing": "Сжимаю %s…",
    "packing_cancel": "Отмена",
    "skipped": "Пропущено, не открывается: %s",
    "failed": "Не открылось",
    "save_failed": "Не сохранилось",
    "save_cancelled": "Сохранение отменено",
}

#: способы показа. Ключ, надпись, и какой канал вытащить в серый
CHANNELS = (
    ("rgba", "ch_rgba", None),
    ("rgb", "ch_rgb", None),
    ("alpha", "ch_alpha", 3),
    ("r", "ch_r", 0),
    ("g", "ch_g", 1),
    ("b", "ch_b", 2),
)

#: во что умеем сохранять. Порядок задаёт порядок фильтров в окне сохранения
WRITE_FORMATS = (("PAA", ".paa"), ("EDDS", ".edds"), ("PNG", ".png"),
                 ("TGA", ".tga"), ("DDS", ".dds"))
WRITE_SUFFIXES = tuple(ext for _, ext in WRITE_FORMATS)


def target_name(picked: Path, chosen: str) -> Path:
    """Куда на самом деле писать, по набранному имени и выбранному типу.

    Правило простое и без догадок:

    * расширения нет — берём выбранное в списке типов;
    * расширение знакомое — верим ему, список типов не спорит;
    * расширение незнакомое — оставляем его как часть имени и дописываем
      выбранное, получается ``имя.неизвестное.выбранное``. Так ничего не
      теряется: ни то, что человек набрал, ни то, что он выбрал.
    """
    if picked.suffix.lower() in WRITE_SUFFIXES:
        return picked
    return picked.with_name(picked.name.rstrip(".") + chosen)


MARGIN = 8
GAP = 8
SWATCH = 14           #: сторона квадратика с цветом
RECENT = 8            #: сколько файлов помнить


def _swatch_qss(colour: Optional[str]) -> str:
    """Квадратик цвета: заливка значением и рамка цвета темы."""
    fill = "background: %s; " % colour if colour else ""
    return "QLabel { %sborder: 1px solid %s; border-radius: 2px; }" % (fill, tokens.color("divider"))


def statistics(pixels: np.ndarray):
    """Максимум и среднее по каналам — то, что показывают внизу окна."""
    flat = pixels.reshape(-1, 4)
    return flat.max(axis=0), flat.mean(axis=0).round().astype(int)


def view_pixels(pixels: np.ndarray, mode: str) -> np.ndarray:
    """Что именно показать при выбранном способе.

    Одиночный канал показывается серым, а не окрашенным: глаз сравнивает
    яркости куда точнее, чем насыщенность одного тона, а нам тут важны именно
    значения.
    """
    if mode == "rgba":
        return pixels
    out = np.empty_like(pixels)
    out[..., 3] = 255
    if mode == "rgb":
        out[..., :3] = pixels[..., :3]
        return out
    index = dict(("%s" % key, channel) for key, _, channel in CHANNELS)[mode]
    grey = pixels[..., index]
    out[..., 0] = out[..., 1] = out[..., 2] = grey
    return out


# --------------------------------------------------------------------------
# Экраны сборки и правки карты SMDI
# --------------------------------------------------------------------------

#: на какой ширине переносится пояснение. Ширину окна задают контролы, а не
#: текст: окно, растянутое под самую длинную фразу, разъезжается от любой
#: правки формулировки
SCREEN = 460


def _note(text: str) -> QLabel:
    """Пояснение, которое переносится по словам и не тянет окно за собой."""
    label = BodyLabel(text)
    label.setWordWrap(True)
    label.setMinimumWidth(SCREEN - MARGIN * 4)
    label.setMaximumWidth(SCREEN)
    return label


class Choice(QWidget):
    """Ряд взаимоисключающих кнопок и поле, зависящее от выбранной.

    Сегмент, а не выпадающий список: вариантов два-три, они короткие, и выбор
    виден без раскрытия.

    Поля лежат стопкой в одном месте, а не появляются и исчезают: из-за этого
    ряд не меняет размер при переключении. Иначе кнопка уезжает из-под курсора
    ровно в тот момент, когда по ней собрались попасть второй раз.
    """

    def __init__(self, options, parent=None):
        super().__init__(parent)
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(GAP)
        self.group = QButtonGroup(self)
        self.group.setExclusive(True)
        self.stack = QStackedWidget()
        self.keys = []

        for index, (key, label, field) in enumerate(options):
            button = TogglePushButton(TEXT[label])
            button.setChecked(index == 0)
            self.group.addButton(button, index)
            row.addWidget(button)
            self.keys.append(key)
            self.stack.addWidget(field if field is not None else QWidget())
        row.addWidget(self.stack)
        row.addStretch(1)

        self.group.idToggled.connect(lambda *_: self._sync())
        self._sync()

    def _sync(self):
        self.stack.setCurrentIndex(max(0, self.group.checkedId()))

    def picked(self):
        return self.keys[self.group.checkedId()]


class ComposeDialog(ThemedDialog):
    """Собрать карту из открытого файла и второго источника."""

    def __init__(self, name: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle(TEXT["compose_title"])
        self.second_path: Optional[Path] = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(tokens.SPACE_L, tokens.SPACE_L, tokens.SPACE_L, tokens.SPACE_M)
        layout.setSpacing(GAP)
        layout.addWidget(_note(TEXT["compose_note"]))

        form = QFormLayout()
        form.setSpacing(GAP)
        self.role = Choice([("intensity", "role_intensity", None),
                            ("sharpness", "role_sharpness", None)])
        form.addRow(BodyLabel(TEXT["compose_role"]), self.role)

        self.pick_btn = PushButton(TEXT["compose_pick"])
        self.pick_btn.clicked.connect(self._pick)
        self.value = DoubleSpinBox()
        self.value.setRange(0.0, 1.0)
        self.value.setSingleStep(0.05)
        self.value.setDecimals(2)
        self.value.setValue(0.4)
        self.second = Choice([("file", "second_file", self.pick_btn),
                              ("value", "second_value", self.value)])
        form.addRow(BodyLabel(TEXT["compose_second"]), self.second)
        layout.addLayout(form)
        row, self.go = look.button_row(self, TEXT["compose_go"])
        layout.addLayout(row)

    def _pick(self):
        picked, _ = QFileDialog.getOpenFileName(
            self, TEXT["open_title"], "", TEXT["open_filter"])
        if picked:
            self.second_path = Path(picked)
            self.pick_btn.setText(self.second_path.name)

    def choice(self):
        """Что выбрано: файл или число, и в какой канал идёт открытый."""
        as_intensity = self.role.picked() == "intensity"
        if self.second.picked() == "file":
            return as_intensity, self.second_path, None
        return as_intensity, None, self.value.value()


class AdjustDialog(ThemedDialog):
    """Поправить яркость и резкость блика на открытой карте."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(TEXT["adjust_title"])

        layout = QVBoxLayout(self)
        layout.setContentsMargins(tokens.SPACE_L, tokens.SPACE_L, tokens.SPACE_L, tokens.SPACE_M)
        layout.setSpacing(GAP)
        layout.addWidget(_note(TEXT["adjust_note"]))

        form = QFormLayout()
        form.setSpacing(GAP)

        self.gain = DoubleSpinBox()
        self.gain.setRange(0.0, 10.0)
        self.gain.setSingleStep(0.1)
        self.gain.setValue(1.0)
        self.material = ComboBox()
        materials = te.info()["smdi_materials"]
        for name in sorted(materials):
            self.material.addItem("%s — %.0f%%" % (name, materials[name] * 100),
                                  userData=name)
        self.material.setCurrentIndex(
            self.material.findData(te.info()["smdi_default_material"]))
        self.intensity = Choice([("keep", "keep", None),
                                 ("gain", "multiply", self.gain),
                                 ("material", "set_material", self.material)])
        form.addRow(BodyLabel(TEXT["adjust_intensity"]), self.intensity)

        self.sharp_gain = DoubleSpinBox()
        self.sharp_gain.setRange(0.0, 10.0)
        self.sharp_gain.setSingleStep(0.1)
        self.sharp_gain.setValue(1.0)
        self.sharp_value = DoubleSpinBox()
        self.sharp_value.setRange(0.0, 1.0)
        self.sharp_value.setSingleStep(0.05)
        self.sharp_value.setDecimals(2)
        self.sharp_value.setValue(0.5)
        self.sharpness = Choice([("keep", "keep", None),
                                 ("gain", "multiply", self.sharp_gain),
                                 ("value", "set_value", self.sharp_value)])
        form.addRow(BodyLabel(TEXT["adjust_sharpness"]), self.sharpness)
        layout.addLayout(form)
        row, self.go = look.button_row(self, TEXT["adjust_go"])
        layout.addLayout(row)

    def settings(self) -> dict:
        """Что именно делать с каналами, словами кита."""
        out = {"intensity_gain": 1.0, "sharpness_gain": 1.0,
               "intensity_set": None, "sharpness_set": None}
        if self.intensity.picked() == "gain":
            out["intensity_gain"] = self.gain.value()
        elif self.intensity.picked() == "material":
            out["intensity_set"] = te.info()["smdi_materials"][self.material.currentData()]
        if self.sharpness.picked() == "gain":
            out["sharpness_gain"] = self.sharp_gain.value()
        elif self.sharpness.picked() == "value":
            out["sharpness_set"] = self.sharp_value.value()
        return out


class ViewerPage(QWidget):

    #: имя открытого файла — главное окно ставит его в заголовок
    caption_changed = Signal(str)
    #: вкладке нужно на передний план: открывают файл, пока видна другая
    wants_front = Signal()

    def __init__(self, path: Optional[str] = None, settings: Optional[QSettings] = None,
                 parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        # хранилище прежнее, «TextureViewer»: недавние файлы и sp переезжают
        # в общую тулзу вместе с человеком, а не теряются при обновлении
        self.settings = settings if settings is not None else QSettings("KR", "TextureViewer")

        self.texture: Optional[te.RemoteTexture] = None
        self.level = 0
        self.mode = "rgba"
        self.siblings: List[Path] = []

        self._build()
        self._sync()
        if path:
            self.load(Path(path))

    # ---------- сборка ----------

    def _build(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, MARGIN, 0, 0)
        layout.setSpacing(GAP)

        picker = QHBoxLayout()
        picker.setSpacing(GAP)
        self.channel_box = ComboBox()
        for key, label, _ in CHANNELS:
            self.channel_box.addItem(TEXT[label], userData=key)
        self.channel_box.currentIndexChanged.connect(self._channel_picked)
        self.mip_box = ComboBox()
        self.mip_box.setMinimumWidth(200)
        self.mip_box.currentIndexChanged.connect(self._mip_picked)
        picker.addWidget(BodyLabel(TEXT["channel_label"]))
        picker.addWidget(self.channel_box)
        picker.addSpacing(GAP)
        picker.addWidget(BodyLabel(TEXT["mip_label"]))
        picker.addWidget(self.mip_box)
        picker.addStretch(1)
        layout.addLayout(picker)

        self.canvas = Canvas()
        self.canvas.placeholder = TEXT["empty"]
        self.canvas.hovered.connect(self._hovered)
        self.canvas.scaled.connect(lambda _z: self._status())
        self.canvas.setFrameStyle = None
        layout.addWidget(self.canvas, 1)

        layout.addWidget(self._colours())
        # строка состояния своя у вкладки: размер, тип и зум относятся к
        # открытой текстуре и на соседних вкладках были бы чужими
        self._status_bar = look.StatusLine()
        layout.addWidget(self._status_bar)
        self._menus()
        self.statusBar().showMessage(TEXT["ready"])
        self.size_label = CaptionLabel()
        self.zoom_label = CaptionLabel()
        self.kind_label = CaptionLabel()
        for widget in (self.kind_label, self.size_label, self.zoom_label):
            self.statusBar().addPermanentWidget(widget)

    def statusBar(self) -> look.StatusLine:
        return self._status_bar

    def caption(self) -> str:
        """Имя открытого файла или пусто."""
        return self.texture.path.name if self.texture else ""

    def activate(self) -> None:
        """Вкладку открыли: фокус на картинку, чтобы сразу работали клавиши."""
        self.canvas.setFocus()

    def _colours(self) -> QWidget:
        """Три строки внизу: максимум, среднее и то, что под курсором."""
        frame = SimpleCardWidget()
        grid = QVBoxLayout(frame)
        grid.setContentsMargins(GAP, GAP // 2, GAP, GAP // 2)
        grid.setSpacing(2)
        self.swatches = {}
        self.readouts = {}
        for key, title in (("max", TEXT["stat_max"]), ("avg", TEXT["stat_avg"]),
                           ("cursor", "")):
            row = QHBoxLayout()
            row.setSpacing(GAP)
            swatch = QLabel()
            swatch.setFixedSize(SWATCH, SWATCH)
            swatch.setStyleSheet(_swatch_qss(None))
            caption = CaptionLabel(title)
            caption.setMinimumWidth(caption.fontMetrics().horizontalAdvance("00000000") + GAP)
            value = BodyLabel(TEXT["stat_none"])
            row.addWidget(swatch)
            row.addWidget(caption)
            row.addWidget(value, 1)
            grid.addLayout(row)
            self.swatches[key] = swatch
            self.readouts[key] = value
        self.readouts["cursor"].setText(TEXT["stat_none"])
        self.cursor_caption = caption
        return frame

    def _act(self, label: str, slot, shortcut=None, checkable: bool = False) -> QAction:
        """Действие вкладки. Сочетание работает, только пока фокус внутри неё."""
        action = QAction(TEXT[label], self, checkable=checkable)
        if shortcut is not None:
            action.setShortcut(shortcut)
        action.setShortcutContext(Qt.WidgetWithChildrenShortcut)
        action.triggered.connect(slot)
        self.addAction(action)
        return action

    def _menus(self) -> None:
        """Меню собираются здесь, а вешает их главное окно.

        ``file_actions`` — то, что вкладка кладёт в общее меню «Файл»: оно
        одно на всё приложение, а свои пункты вкладка показывает в нём, только
        пока открыта. ``menus`` — её собственные меню: (название, пункты),
        None — разделитель.
        """
        self.open_action = self._act("open", self.ask_open, QKeySequence.Open)
        # «Открыть» работает с любой вкладки: главное окно переключит на эту
        self.open_action.setShortcutContext(Qt.WindowShortcut)
        self.reload_action = self._act("reload", self.reload, QKeySequence.Refresh)
        self.save_action = self._act("save_as", self.ask_save,
                                     QKeySequence("Ctrl+Shift+S"))
        self.next_action = self._act("next_file", lambda: self.step(1),
                                     QKeySequence(Qt.Key_PageDown))
        self.prev_action = self._act("prev_file", lambda: self.step(-1),
                                     QKeySequence(Qt.Key_PageUp))
        self.recent_menu = look.Submenu(TEXT["recent"], TEXT["recent_empty"], self._recent_actions)
        self.file_actions = [self.reload_action, self.save_action, None,
                             self.next_action, self.prev_action, None,
                             self.recent_menu]

        self.smdi_action = self._act("smdi", self.run_smdi, QKeySequence("Ctrl+M"))
        self.invert_action = self._act("invert", self.invert_green,
                                       QKeySequence("Ctrl+I"))
        self.split_action = self._act("split", self.split_channels,
                                      QKeySequence("Ctrl+E"))
        self.compose_action = self._act("compose", self.compose_smdi)
        self.adjust_action = self._act("adjust", self.adjust_smdi)
        edit = [self.smdi_action, self.invert_action, self.split_action, None,
                self.compose_action, self.adjust_action]

        self.mip_prev_action = self._act("mip_prev", lambda: self.step_mip(-1),
                                         QKeySequence(Qt.Key_Up))
        self.mip_next_action = self._act("mip_next", lambda: self.step_mip(1),
                                         QKeySequence(Qt.Key_Down))
        mips = [self.mip_prev_action, self.mip_next_action]

        view = []
        group = QActionGroup(self)
        group.setExclusive(True)
        self.channel_actions = {}
        for key, label, _ in CHANNELS:
            action = self._act(label, lambda _c, k=key: self.set_mode(k),
                               checkable=True)
            group.addAction(action)
            view.append(action)
            self.channel_actions[key] = action
        self.channel_actions["rgba"].setChecked(True)
        view += [None,
                 self._act("zoom_in", lambda: self.zoom_by(1.25), QKeySequence.ZoomIn),
                 self._act("zoom_out", lambda: self.zoom_by(0.8), QKeySequence.ZoomOut),
                 self._act("zoom_fit", self.canvas.fit, QKeySequence("Ctrl+0")),
                 self._act("zoom_actual", self.canvas.actual, QKeySequence("Ctrl+1")),
                 None]
        self.checker_action = self._act("checker", self._redraw,
                                        QKeySequence("Ctrl+K"), checkable=True)
        self.grid_action = self._act("grid", self._redraw,
                                     QKeySequence("Ctrl+G"), checkable=True)
        view += [self.checker_action, self.grid_action]
        # (название, пункты): кнопками их ставит главное окно
        self.menus = [(TEXT["menu_edit"], edit), (TEXT["menu_mip"], mips), (TEXT["menu_view"], view)]

    # ---------- файлы ----------

    def load(self, path: Path, keep_view: bool = False) -> None:
        try:
            texture = te.open_texture(path)
        except (te.OpenError, OSError) as exc:
            look.warn(self, TEXT["failed"], str(exc))
            return
        self._adopt(texture, keep_view)

    def _adopt(self, texture, keep_view: bool = False) -> None:
        """Показать уже открытую текстуру."""
        self.texture = texture
        self.siblings = te.neighbours(texture.path)
        self.level = min(self.level if keep_view else 0, len(texture.levels) - 1)
        self.caption_changed.emit(texture.path.name)
        self._remember(texture.path)
        self._fill_mips()
        self._show(keep_view)
        self._sync()
        self.statusBar().showMessage(texture.note or TEXT["ready"])

    def open_path(self, path: Path) -> None:
        """Открыть файл, пришедший снаружи вкладки: из недавних, из командной
        строки, брошенный в окно."""
        self.wants_front.emit()
        self.load(path)

    def ask_open(self) -> None:
        self.wants_front.emit()
        start = str(self.texture.path.parent) if self.texture else ""
        picked, _ = QFileDialog.getOpenFileName(self, TEXT["open_title"], start,
                                                TEXT["open_filter"])
        if picked:
            self.load(Path(picked))

    def reload(self) -> None:
        """Перечитать с диска: художник пересохранил — жмём и смотрим."""
        if self.texture:
            self.load(self.texture.path, keep_view=True)

    def ask_save(self) -> None:
        if not self.texture:
            return
        dialog = QFileDialog(self, TEXT["save_title"], str(self.texture.path.parent))
        dialog.setAcceptMode(QFileDialog.AcceptSave)
        dialog.setNameFilters(["%s (*%s)" % pair for pair in WRITE_FORMATS])
        # имя без расширения: иначе, чтобы сохранить в другой формат, его
        # сперва пришлось бы стирать вручную
        dialog.selectFile(self.texture.path.stem)
        here = self.texture.path.suffix.lower()
        for label, ext in WRITE_FORMATS:
            if ext == here:
                dialog.selectNameFilter("%s (*%s)" % (label, ext))
                break
        if not dialog.exec() or not dialog.selectedFiles():
            return

        chosen = WRITE_FORMATS[0][1]
        for label, ext in WRITE_FORMATS:
            if dialog.selectedNameFilter() == "%s (*%s)" % (label, ext):
                chosen = ext
                break
        target = target_name(Path(dialog.selectedFiles()[0]), chosen)
        try:
            self._write(target)
        except Exception as exc:
            look.warn(self, TEXT["save_failed"], str(exc))
            return
        self.statusBar().showMessage(TEXT["saved"] % target.name)

    def _write(self, target: Path) -> None:
        """Записать показанный уровень в выбранный формат.

        Пишем из уже распакованных пикселей, а не перегоняем исходный файл:
        иначе сохранение PAA в PAA упиралось в упаковщик, который исходником
        принимает только png, tga и dds.

        Сохраняется тот уровень, что на экране, — какой размер показан в строке
        состояния, такой и получится.
        """
        # пишет TextureEditor.exe; ход показываем только у EDDS — он жмётся секундами
        progress = self._packing(target) if target.suffix.lower() == ".edds" else None
        te.save_as(self.texture, self.level, target, progress)

    def _packing(self, target: Path):
        """Показать ход сжатия. Крупный атлас жмётся секундами, и молчащее
        окно на это время читается как зависшее."""
        # быстрое сохранение обойдётся без окна: оно появится через 400 мс
        dialog = look.Progress(self, TEXT["packing"] % target.name, TEXT["packing_cancel"])

        def report(done: float) -> None:
            dialog.setValue(int(done * 100))
            QApplication.processEvents()
            if dialog.wasCanceled():
                raise te.EditError(TEXT["save_cancelled"])
        return report

    def step(self, delta: int) -> None:
        """Следующий или предыдущий файл той же папки.

        Нечитаемые пропускаем молча и идём дальше: при листании папки окно с
        сообщением на каждый чужой файл хуже, чем его отсутствие. О пропущенных
        говорим один раз в строке состояния.
        """
        if not self.texture or not self.siblings:
            return
        try:
            index = self.siblings.index(self.texture.path)
        except ValueError:
            return

        skipped = []
        for _ in range(len(self.siblings)):
            index = (index + delta) % len(self.siblings)
            candidate = self.siblings[index]
            if candidate == self.texture.path:
                break
            try:
                texture = te.open_texture(candidate)
            except (te.OpenError, OSError):
                skipped.append(candidate.name)
                continue
            self._adopt(texture, keep_view=texture.size == self.texture.size)
            if skipped:
                self.statusBar().showMessage(TEXT["skipped"] % ", ".join(skipped))
            return
        if skipped:
            self.statusBar().showMessage(TEXT["skipped"] % ", ".join(skipped))

    # ---------- правки ----------

    def run_smdi(self) -> None:
        """Прогон одного открытого файла через фильтр SMDI.

        Спрашиваем ровно то, что нельзя решить за человека: значение
        SpecularPower — оно берётся из rvmat и у каждого материала своё, — и
        судьбу резервной копии.
        """
        path = self.texture.path
        reason = te.smdi_reason(path)
        if reason is not None:
            look.warn(self, TEXT["edit_failed"], TEXT["smdi_refused"] % reason)
            return

        # значение целое: в rvmat так записано у 98% материалов, и дробная
        # часть в поле только мешала бы попадать по нужному числу
        sp, chosen = look.ask_int(
            self, TEXT["smdi"], TEXT["smdi_sp"],
            int(round(float(self.settings.value("sp", te.info()["default_sp"])))),
            1, 1000)
        if not chosen:
            return
        self.settings.setValue("sp", sp)

        answer = look.ask(self, TEXT["smdi"], TEXT["smdi_backup"], look.YES)
        if answer == look.CANCEL:
            return
        keep_backup = answer == look.YES

        overwrite = False
        existing = te.smdi_backup(path) if keep_backup else None
        if existing is not None:
            answer = look.ask(self, TEXT["smdi"], TEXT["smdi_exists"] % existing.parent.name,
                              look.NO)
            if answer == look.CANCEL:
                return
            overwrite = answer == look.YES

        try:
            state = te.run_smdi(path, sp, keep_backup, overwrite)
        except (te.EditError, OSError) as exc:
            look.warn(self, TEXT["edit_failed"], str(exc))
            return

        if state == "applied":
            self.statusBar().showMessage(
                TEXT["smdi_done"] % (sp, te.smdi_backup(path).parent.name)
                if keep_backup else TEXT["smdi_done_nobackup"] % sp)
        elif state == "skipped":
            self.statusBar().showMessage(TEXT["smdi_skipped"])
        else:
            self.statusBar().showMessage(TEXT["smdi_refused"] % state)
        self.reload()

    def invert_green(self) -> None:
        try:
            te.invert_green(self.texture.path)
        except (te.EditError, OSError) as exc:
            look.warn(self, TEXT["edit_failed"], str(exc))
            return
        message = TEXT["inverted"] % te.info()["backup_dir"]
        self.reload()
        self.statusBar().showMessage(message)

    def compose_smdi(self) -> None:
        """Собрать карту SMDI из открытого файла и второго источника.

        Пишем в новый файл рядом, а не поверх открытого: исходники нужны и
        дальше, а затирать их сборкой — потеря без отмены.
        """
        if not self.texture:
            return
        dialog = ComposeDialog(self.texture.path.name, self)
        if not dialog.exec():
            return
        as_intensity, second, value = dialog.choice()
        if second is None and value is None:
            look.warn(self, TEXT["edit_failed"], TEXT["compose_nofile"])
            return
        try:
            made = te.compose_smdi(self.texture, self.level,
                                   other=second, constant=value,
                                   open_is_intensity=as_intensity)
        except (te.EditError, OSError, ValueError) as exc:
            look.warn(self, TEXT["edit_failed"], str(exc))
            return
        self.siblings = te.neighbours(self.texture.path)
        self.statusBar().showMessage(TEXT["composed"] % made.name)

    def adjust_smdi(self) -> None:
        """Поправить блик на открытой карте."""
        if not self.texture:
            return
        dialog = AdjustDialog(self)
        if not dialog.exec():
            return
        try:
            te.adjust_smdi(self.texture, self.level, **dialog.settings())
        except (te.EditError, OSError, ValueError) as exc:
            look.warn(self, TEXT["edit_failed"], str(exc))
            return
        kept = self.texture.path.parent / te.info()["backup_dir"]
        self.load(self.texture.path)
        self.statusBar().showMessage(TEXT["adjusted"] % kept.name)

    def split_channels(self) -> None:
        """Каналы по отдельным файлам, одним нажатием и без вопросов."""
        try:
            written, flat = te.split_channels(self.texture, self.level)
        except (te.EditError, OSError) as exc:
            look.warn(self, TEXT["edit_failed"], str(exc))
            return
        self.siblings = te.neighbours(self.texture.path)
        message = TEXT["split_done"] % ", ".join(p.name for p in written)
        if flat:
            message += TEXT["split_flat"] % ", ".join(flat)
        if not written:
            message = TEXT["split_nothing"]
        self.statusBar().showMessage(message)

    # ---------- показ ----------

    def _show(self, keep_view: bool = False) -> None:
        if not self.texture:
            self.canvas.set_pixels(None)
            return
        pixels = self.texture.pixels(self.level)
        level = self.texture.levels[self.level]
        # мелкий уровень растягиваем до размера полной текстуры: переключая
        # мипы, смотрят что стало с деталями, а не как съехала рамка
        self.canvas.magnify = self.texture.width / max(level.width, 1)
        self.canvas.checker = self.checker_action.isChecked()
        self.canvas.show_grid = self.grid_action.isChecked() and self.texture.blocky
        self.canvas.set_pixels(view_pixels(pixels, self.mode), keep_view)
        self._statistics(pixels)
        self._status()

    def set_mode(self, mode: str) -> None:
        self.mode = mode
        self.channel_actions[mode].setChecked(True)
        index = self.channel_box.findData(mode)
        if index >= 0 and index != self.channel_box.currentIndex():
            self.channel_box.blockSignals(True)
            self.channel_box.setCurrentIndex(index)
            self.channel_box.blockSignals(False)
        self._show(keep_view=True)

    def step_mip(self, delta: int) -> None:
        if not self.texture:
            return
        level = max(0, min(len(self.texture.levels) - 1, self.level + delta))
        if level != self.level:
            self.level = level
            self.mip_box.setCurrentIndex(level)

    def zoom_by(self, factor: float) -> None:
        self.canvas.set_zoom(self.canvas.zoom() * factor)

    # ---------- строки со сведениями ----------

    def _statistics(self, pixels: np.ndarray) -> None:
        top, mean = statistics(pixels)
        for key, values in (("max", top), ("avg", mean)):
            self.readouts[key].setText("%d, %d, %d   альфа %d" % tuple(int(v) for v in values))
            self._paint_swatch(key, values)

    def _paint_swatch(self, key: str, values) -> None:
        colour = QColor(int(values[0]), int(values[1]), int(values[2]))
        self.swatches[key].setStyleSheet(_swatch_qss(colour.name()))

    def _hovered(self, x: int, y: int) -> None:
        level = self.texture.levels[self.level] if self.texture else None
        if level is not None and (x >= level.width or y >= level.height):
            x = -1                       # курсор остался от прошлого уровня
        if not self.texture or x < 0 or y < 0:
            self.cursor_caption.setText("")
            self.readouts["cursor"].setText(TEXT["stat_none"])
            self.swatches["cursor"].setStyleSheet(_swatch_qss(None))
            return
        value = self.texture.pixels(self.level)[y, x]
        self.cursor_caption.setText(TEXT["cursor"] % (x, y))
        self.readouts["cursor"].setText(TEXT["value"] % tuple(int(v) for v in value))
        self._paint_swatch("cursor", value)

    def _status(self) -> None:
        if not self.texture:
            for widget in (self.kind_label, self.size_label, self.zoom_label):
                widget.setText("")
            return
        level = self.texture.levels[self.level]
        self.size_label.setText(TEXT["size_of"] % (level.width, level.height,
                                                   self.texture.width, self.texture.height))
        weight = self.texture.file_size
        self.kind_label.setText("%s   %s" % (
            self.texture.kind,
            TEXT["weight_mb"] % (weight / 1048576.0) if weight >= 1048576
            else TEXT["weight_kb"] % round(weight / 1024.0)))
        self.zoom_label.setText(TEXT["zoom_percent"] % round(self.canvas.zoom() * 100))

    def _fill_mips(self) -> None:
        self.mip_box.blockSignals(True)
        self.mip_box.clear()
        for index, level in enumerate(self.texture.levels):
            self.mip_box.addItem(TEXT["mip_item"] % (
                index, level.width, level.height,
                TEXT["mip_packed"] if level.packed else ""))
        self.mip_box.setCurrentIndex(self.level)
        self.mip_box.blockSignals(False)

    def _sync(self) -> None:
        loaded = self.texture is not None
        for action in (self.reload_action, self.save_action, self.next_action,
                       self.prev_action, self.mip_prev_action, self.mip_next_action,
                       self.split_action):
            action.setEnabled(loaded)
        # фильтр SMDI применим не ко всякому файлу, и молчаливо отключённый
        # пункт объясняет это лучше, чем отказ после нажатия
        reasons = self.texture.reasons() if loaded else {}
        self.smdi_action.setEnabled(loaded and reasons.get("smdi") is None)
        # инверсия зелёного — правка карты нормалей; к форматам доставки
        # интерфейса она неприменима по существу, а не по нашей нехватке
        editable = loaded and reasons.get("map") is None
        self.invert_action.setEnabled(editable)
        self.compose_action.setEnabled(editable)
        # править блик можно только на том, что уже карта: собирать её из
        # самой себя бессмысленно, а молча испортить чужую текстуру — вредно
        self.adjust_action.setEnabled(
            editable and "_smdi" in self.texture.path.stem.lower())
        self.channel_box.setEnabled(loaded)
        self.mip_box.setEnabled(loaded and len(self.texture.levels) > 1)
        self.grid_action.setEnabled(loaded and self.texture.blocky)

    # ---------- недавние ----------

    def _remember(self, path: Path) -> None:
        recent = [str(path)] + [p for p in self._recent() if p != str(path)]
        self.settings.setValue("recent", recent[:RECENT])

    def _recent(self) -> List[str]:
        stored = self.settings.value("recent", []) or []
        return [p for p in stored if Path(p).exists()]

    def _recent_actions(self) -> List[QAction]:
        """Пункты подменю «Недавние» — свежие на каждое открытие меню."""
        actions = []
        for index, item in enumerate(self._recent(), 1):
            action = QAction("%d  %s" % (index, Path(item).name), self)
            action.triggered.connect(lambda _c=False, p=item: self.open_path(Path(p)))
            actions.append(action)
        return actions

    # ---------- мелкие обработчики ----------

    def _channel_picked(self, index: int) -> None:
        self.set_mode(self.channel_box.itemData(index))

    def _mip_picked(self, index: int) -> None:
        if self.texture and 0 <= index < len(self.texture.levels):
            self.level = index
            self._show(keep_view=True)

    def _redraw(self, _checked: bool = False) -> None:
        self._show(keep_view=True)

    # ---------- окно ----------

    def dragEnterEvent(self, event):
        urls = event.mimeData().urls()
        if len(urls) == 1:
            path = Path(urls[0].toLocalFile())
            if path.suffix.lower() in te.info()["read_suffixes"]:
                event.acceptProposedAction()

    def dropEvent(self, event):
        self.load(Path(event.mimeData().urls()[0].toLocalFile()))
