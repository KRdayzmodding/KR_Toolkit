# Скопировано из KR_ServerManager/ui/packing_log.py (рабочая копия на 22.10.2026, последний коммит QTS deba8ad) — общий визуальный язык с KR QTS.
# Править синхронно с оригиналом, а не молча здесь.
"""Таблица запаковки в журнале главной страницы.

Раньше про запаковку писалась одна строка на PBO по факту завершения: сколько
их всего и что происходит прямо сейчас, видно не было. Здесь список печатается
сразу целиком, а строки обновляются на месте по мере работы:

    kr_furniture_cfg.pbo ......... [ok]
    KR_FURNITURE.pbo ............. [packing] ..
    kr_proxy.pbo ................. [wait]

Обновление на месте, а не дописывание: иначе журнал за одну сборку разрастался
бы на десятки почти одинаковых строк.
"""
from __future__ import annotations

import html
import time

from PySide6.QtCore import QTimer
from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import QPlainTextEdit

from qts_ui import tokens

WAIT, PACKING, OK, FAIL = "wait", "packing", "ok", "fail"

# Роли, а не цвета: тон под текущую тему знает ui.tokens.
_ROLES = {WAIT: "muted", PACKING: "warning", OK: "success", FAIL: "error"}


def _color(status: str) -> str:
    return tokens.color(_ROLES.get(status, "muted"))
_MIN_WIDTH = 34      # до какой ширины тянуть точки, если имена короткие


def fmt_ms(ms: int) -> str:
    """Миллисекунды с отбивкой секунд: 13284 -> «13 284».

    Пробел перед последними тремя цифрами — по нему сразу читается, сколько
    это секунд, при этом единица измерения остаётся прежней.
    """
    return f"{ms // 1000} {ms % 1000:03d}" if ms >= 1000 else str(ms)

_TICK_MS = 200      # шаг счётчика у строки, которая пакуется прямо сейчас


class PackingLog:
    """Живая таблица запаковки внутри QPlainTextEdit.

    Строки переписываются через QTextCursor по номеру блока. Если в журнал
    между обновлениями что-то дописали (ошибка запуска, вывод пакера), таблица
    сдвинулась бы — на этот случай проверяем, что блок всё ещё наш, и при
    расхождении печатаем таблицу заново, а не портим чужой текст.
    """

    def __init__(self, view: QPlainTextEdit):
        self.view = view
        self._names: list[str] = []
        self._status: dict[str, str] = {}
        self._elapsed: dict[str, int] = {}   # имя -> мс, по завершении
        self._started: dict[str, float] = {}  # имя -> момент старта, для живого счётчика
        self._issues: dict[str, tuple[int, int]] = {}   # имя -> (warnings, errors)
        self._first_block = -1
        self._width = _MIN_WIDTH
        self._timer = QTimer(view)
        self._timer.setInterval(_TICK_MS)
        self._timer.timeout.connect(self._tick)

    # ------------------------------------------------------------- отрисовка

    def _line(self, name: str) -> str:
        status = self._status.get(name, WAIT)
        left = f"{name} ".ljust(self._width, ".")
        if status == PACKING:
            # живой счётчик вместо бегущих точек: он и показывает, что процесс
            # идёт, и сразу говорит, сколько уже длится
            started = self._started.get(name)
            ms = int((time.monotonic() - started) * 1000) if started else 0
        else:
            # длительность показываем и у ошибок: мгновенное падение (плохие
            # аргументы) и падение через полминуты (ошибка сборки) — разное
            ms = self._elapsed.get(name)
        tail = f" ({fmt_ms(ms)} ms)" if ms is not None else ""
        out = (f'<span style="color:{_color(status)};">'
               f'{html.escape(f"{left} [{status}]{tail}")}</span>')
        # предупреждения и ошибки — отдельным блоком и своими цветами; если их
        # нет, блока нет вовсе, чтобы не зашумлять чистые сборки
        w, e = self._issues.get(name, (0, 0))
        if w:
            out += f' <span style="color:{tokens.color("warning")};">[W: {w}]</span>'
        if e:
            out += f' <span style="color:{tokens.color("error")};">[E: {e}]</span>'
        return out

    def _render(self) -> None:
        """Переписывает таблицу на месте.

        Вся таблица живёт в одном текстовом блоке: appendHtml со вставками
        <br> не разбивает текст на блоки, а делает переносы внутри одного.
        Поэтому адресуемся к этому блоку и заменяем его целиком.
        """
        doc = self.view.document()
        if self._first_block < 0 or self._first_block >= doc.blockCount():
            return
        block = doc.findBlockByNumber(self._first_block)
        cursor = QTextCursor(block)
        cursor.beginEditBlock()
        cursor.select(QTextCursor.SelectionType.BlockUnderCursor)
        cursor.removeSelectedText()
        # BlockUnderCursor захватывает и разделитель перед блоком — возвращаем
        # его, иначе таблица прилипнет к предыдущей строке журнала. У самого
        # первого блока разделителя нет, и лишняя вставка сдвигала бы таблицу
        # вниз на каждой перерисовке.
        if self._first_block > 0:
            cursor.insertBlock()
        cursor.insertHtml("<br>".join(self._line(n) for n in self._names))
        cursor.endEditBlock()

    def _tick(self) -> None:
        self._render()

    # -------------------------------------------------------------- действия

    def names(self) -> list[str]:
        """Состав текущей таблицы — он же состав последней запаковки."""
        return list(self._names)

    def report(self) -> dict:
        """Состав и исход последней сборки — для отчёта внешнему управлению.

        Данные уже собраны здесь ради таблицы в журнале; отдельного учёта для
        отчёта заводить не надо, иначе они разойдутся при первой же правке.
        """
        items = []
        for name in self._names:
            w, e = self._issues.get(name, (0, 0))
            item = {"pbo": name, "status": self._status.get(name, "")}
            if name in self._elapsed:
                item["ms"] = self._elapsed[name]
            if w:
                item["warnings"] = w
            if e:
                item["errors"] = e
            items.append(item)
        return {"plan": list(self._names), "items": items}

    def busy(self) -> bool:
        """Идёт ли сборка прямо сейчас — что-то пакуется или ждёт очереди."""
        return any(s in (WAIT, PACKING) for s in self._status.values())

    def add(self, names: list[str]) -> None:
        """Дописывает строки к идущей сборке, сохраняя уже показанное."""
        fresh = [n for n in names if n not in self._status]
        if not fresh:
            return
        self._names += fresh
        self._status.update({n: WAIT for n in fresh})
        self._width = max(self._width, max(len(n) for n in fresh) + 2)
        self._render()

    def start(self, names: list[str]) -> None:
        """Печатает весь список сразу — сколько PBO предстоит собрать видно
        с самого начала, а не по мере готовности.

        Если сборка уже идёт, список дополняется, а не затирается. Таблица
        одна на всю программу: запуск сервера пакует устаревшие моды, а с
        страницы модов в это же время можно нажать «Запаковать». Затирание
        выглядело так, будто первая запаковка оборвалась, — хотя она шла.
        """
        if self.busy():
            self.add(names)
            return
        self.stop()
        self._names = list(names)
        self._status = {n: WAIT for n in names}
        self._elapsed = {}
        self._started = {}
        self._issues = {}
        if not names:
            return
        self._width = max(_MIN_WIDTH, max(len(n) for n in names) + 2)
        self.view.appendHtml("<br>".join(self._line(n) for n in self._names))
        # Индекс берём по факту вставки, а не предсказываем: в пустом документе
        # appendHtml пишет в уже существующий блок 0 и нового не создаёт. При
        # предсказании индекс уезжал на единицу, _render молча отсекался по
        # проверке границ, и таблица навсегда оставалась в [wait].
        self._first_block = self.view.document().blockCount() - 1

    def set_status(self, name: str, status: str, elapsed_ms: int = -1,
                   warnings: int = 0, errors: int = 0) -> None:
        if name not in self._status:
            return
        self._status[name] = status
        if elapsed_ms >= 0:
            self._elapsed[name] = elapsed_ms
        if warnings or errors:
            self._issues[name] = (warnings, errors)
        if status == PACKING:
            self._started[name] = time.monotonic()
            self._timer.start()
        elif not any(s == PACKING for s in self._status.values()):
            self._timer.stop()
        self._render()

    def stop(self) -> None:
        self._timer.stop()
        self._first_block = -1
