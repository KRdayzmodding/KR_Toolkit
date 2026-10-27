# -*- coding: utf-8 -*-
"""Работа [KR] Project Builder — через командную строку ProjectBuilder.exe.

Окно само не собирает и не читает реестры проверок (юзер 24.10.2026: окно —
только показ, работа — в командной строке). Здесь — запуск `ProjectBuilder.exe`
с --json и разбор его событий: собранное окно зовёт exe рядом с собой, из
исходников — `python -m build_kit`.

Сборки набора идут одним процессом по очереди (--jobs-file): внутри сборки
параллелит её собственный пул, две сборки разом делили бы ядра.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from PySide6.QtCore import QThread, Signal

HERE = Path(__file__).resolve().parent
KITS = HERE.parents[1] / "kits"

#: уровни проверок — те же слова, что отдаёт командная строка
ERROR, WARNING, INFO, OFF = "error", "warning", "info", "off"


def cli_command() -> List[str]:
    if getattr(sys, "frozen", False):
        # поставка — одна папка: командная строка лежит рядом с окном
        return [str(Path(sys.executable).resolve().parent / "ProjectBuilder.exe")]
    return [sys.executable, "-m", "build_kit"]


def _env() -> dict:
    return dict(os.environ, PYTHONIOENCODING="utf-8")


def _cwd() -> Optional[str]:
    return str(KITS) if KITS.is_dir() else None


def call(args: List[str]) -> List[dict]:
    """Короткий вызов (каталог, проверка настроек, ключ): дождаться и вернуть события."""
    try:
        proc = subprocess.run(cli_command() + args + ["--json"], cwd=_cwd(), stdin=subprocess.DEVNULL,
                              capture_output=True, env=_env(),
                              creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except OSError as exc:
        return [{"event": "problem", "text": "%s: %s" % (cli_command()[0], exc)}]
    events = []
    for line in proc.stdout.decode("utf-8", "replace").splitlines():
        try:
            events.append(json.loads(line))
        except ValueError:
            continue
    if not events:
        tail = proc.stderr.decode("utf-8", "replace").strip().splitlines()
        events.append({"event": "problem", "text": tail[-1] if tail else "нет ответа от %s" % cli_command()[0]})
    return events


def _settings_args(settings_file: Optional[Path]) -> List[str]:
    return ["--settings-file", str(settings_file)] if settings_file else []


# ====================================================================== каталог
@dataclass(frozen=True)
class CheckInfo:
    """Вид проблем (27.10.2026): уровень задаётся ему, а не каждой проверке."""
    code: str
    group: str
    title: str
    desc: str
    default: str
    locked: bool = False
    #: коды проверок вида и те из них, что всегда ошибка
    codes: Tuple[str, ...] = ()
    locked_codes: Tuple[str, ...] = ()


@dataclass(frozen=True)
class FixInfo:
    code: str
    group: str
    title: str
    desc: str
    options: Tuple[Tuple[str, str], ...]
    default: str
    locked: str = ""


@dataclass
class Catalog:
    """Что умеет сборщик: умолчания настроек, проверки, исправления, где лежат файлы."""

    defaults: Dict[str, object] = field(default_factory=dict)
    files: Dict[str, str] = field(default_factory=dict)
    checks: List[CheckInfo] = field(default_factory=list)
    fixes: List[FixInfo] = field(default_factory=list)
    problem: str = ""

    @property
    def check_by_code(self) -> Dict[str, CheckInfo]:
        return {c.code: c for c in self.checks}

    @property
    def fix_by_code(self) -> Dict[str, FixInfo]:
        return {f.code: f for f in self.fixes}


_CATALOG: Dict[str, Catalog] = {}


def catalog(settings_file: Optional[Path] = None) -> Catalog:
    """Каталог — один вызов на сеанс: реестры проверок за время работы окна не меняются."""
    key = str(settings_file or "")
    if key in _CATALOG:
        return _CATALOG[key]
    cat = Catalog()
    for ev in call(["--list"] + _settings_args(settings_file)):
        kind = ev.get("event")
        if kind == "defaults":
            cat.defaults, cat.files = dict(ev.get("values") or {}), dict(ev.get("files") or {})
        elif kind == "check":
            cat.checks.append(CheckInfo(ev["code"], ev["group"], ev["title"], ev.get("desc", ""),
                                        ev["default"], bool(ev.get("locked")),
                                        tuple(ev.get("codes") or ()),
                                        tuple(ev.get("locked_codes") or ())))
        elif kind == "fix":
            cat.fixes.append(FixInfo(ev["code"], ev["group"], ev["title"], ev.get("desc", ""),
                                     tuple(tuple(o) for o in ev.get("options", [])), ev["default"],
                                     ev.get("locked") or ""))
        elif kind == "problem":
            cat.problem = ev.get("text", "")
    if not cat.problem and not cat.defaults:
        cat.problem = "нет ответа от %s" % cli_command()[0]
    if not cat.problem:
        _CATALOG[key] = cat
    return cat


def settings_path() -> Path:
    """Общий файл настроек — где его держит командная строка."""
    files = catalog().files
    return Path(files["settings"]) if files.get("settings") else \
        Path.home() / ".kr_devtoolkit" / "project_builder.json"


def check_settings(values: dict, settings_file: Optional[Path]) -> str:
    """Пусто — значения годятся; иначе текст отказа от командной строки."""
    for ev in call(["--check-settings", json.dumps(values, ensure_ascii=False)] + _settings_args(settings_file)):
        if ev.get("event") == "checked":
            return "" if ev.get("ok") else ev.get("text", "")
        if ev.get("event") == "problem":
            return ev.get("text", "")
    return "нет ответа от %s" % cli_command()[0]


def key_info(path: str) -> dict:
    """{name, private, error}."""
    for ev in call(["--key-info", path]):
        if ev.get("event") == "key":
            return ev
        if ev.get("event") == "problem":
            return {"name": "", "private": False, "error": ev.get("text", "")}
    return {"name": "", "private": False, "error": "нет ответа от %s" % cli_command()[0]}


def mark(path: Path, code: str, settings_file: Optional[Path] = None) -> Tuple[str, str]:
    """Пометить находку на модели селекцией error_NN: (имя селекции, "") или ("", почему нет)."""
    events = call(["--mark", str(path), code] + _settings_args(settings_file))
    for ev in events:
        if ev.get("event") == "marked":
            return ev.get("selection", ""), ""
    problem = next((ev.get("text") for ev in events if ev.get("event") == "problem"), "")
    return "", problem or "нет ответа от %s" % cli_command()[0]


def create_key(name: str, folder: Path) -> Tuple[Path, Path]:
    """Пара ключей; отказ — RuntimeError с текстом от командной строки."""
    events = call(["--create-key", name, str(folder)])
    for ev in events:
        if ev.get("event") == "created":
            return Path(ev["prv"]), Path(ev["pub"])
    problem = next((ev.get("text") for ev in events if ev.get("event") == "problem"), "")
    raise RuntimeError(problem or "нет ответа от %s" % cli_command()[0])


# ====================================================================== сборка
@dataclass
class Result:
    """Итог одного мода — из событий командной строки (finding, decision, done)."""

    source: str
    errors: List[Tuple[str, str]] = field(default_factory=list)
    warnings: List[Tuple[str, str]] = field(default_factory=list)
    infos: List[Tuple[str, str]] = field(default_factory=list)
    #: находки, которые командная строка умеет пометить на модели: (файл, текст) → код
    marks: Dict[Tuple[str, str], str] = field(default_factory=dict)
    decisions: List[str] = field(default_factory=list)
    ok: bool = False
    packed: bool = False
    log: str = ""
    rebuilt: int = 0
    deleted: int = 0
    unchanged: int = 0
    #: только у плана: сколько пересобралось бы и не собирался ли мод ни разу
    changed: int = 0
    never_built: bool = False


def _finding(ev: dict) -> Tuple[str, str]:
    """Находка как в отчёте: место дерева конфига командная строка отдаёт отдельно — вернуть в текст."""
    text = ev.get("text", "")
    if ev.get("where"):
        text = "%s. %s" % (ev["where"], text)
    return ev.get("file") or "", text


class BuildWorker(QThread):
    """`jobs` — список (строка таблицы, исходник, PBO). `plan=True` — только план."""

    entry_started = Signal(int)
    progress = Signal(int, str, int, int)          # строка, этап, сделано, всего
    entry_finished = Signal(int, object, str)      # строка, Result или None, текст ошибки
    all_finished = Signal(bool)                    # остановлено ли

    def __init__(self, jobs: List[tuple], *, plan: bool = False, full: bool = False,
                 settings_file: Optional[Path] = None, parent=None):
        super().__init__(parent)
        self.jobs = jobs
        self.plan = plan
        self.full = full
        self.settings_file = settings_file
        self.proc: Optional[subprocess.Popen] = None
        self._stopped = False

    def stop(self) -> None:
        """Мягкая остановка: «stop» в stdin — сборка остановится между задачами, PBO не пишется."""
        self._stopped = True
        proc = self.proc
        if proc is not None and proc.poll() is None and proc.stdin is not None:
            try:
                proc.stdin.write(b"stop\n")
                proc.stdin.flush()
            except OSError:
                pass

    def _args(self, jobs_file: str) -> List[str]:
        args = ["--jobs-file", jobs_file, "--json"] + _settings_args(self.settings_file)
        if self.plan:
            args.append("--dry-run")
        if self.full:
            args.append("--full")
        return args

    def run(self) -> None:
        fd, jobs_file = tempfile.mkstemp(prefix="kr_build_", suffix=".json")
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump([{"source": str(source), "target": str(target) if target else None}
                       for _row, source, target in self.jobs], fh, ensure_ascii=False)
        rows = [row for row, _source, _target in self.jobs]
        index, current, cancelled = -1, None, False
        stderr = tempfile.TemporaryFile()
        try:
            try:
                self.proc = subprocess.Popen(
                    cli_command() + self._args(jobs_file), cwd=_cwd(), stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE, stderr=stderr, env=_env(),
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            except OSError as exc:
                for row in rows:
                    self.entry_finished.emit(row, None, "%s: %s" % (cli_command()[0], exc))
                self.all_finished.emit(False)
                return
            if self._stopped:
                self.stop()
            for raw in self.proc.stdout:
                try:
                    ev = json.loads(raw.decode("utf-8"))
                except ValueError:
                    continue
                kind = ev.get("event")
                if kind == "start":
                    index += 1
                    if index >= len(rows):
                        break
                    current = Result(source=ev.get("source") or "")
                    self.entry_started.emit(rows[index])
                elif current is None:
                    continue
                elif kind == "stage":
                    self.progress.emit(rows[index], ev.get("name", ""), int(ev.get("done") or 0),
                                       int(ev.get("total") or 0))
                elif kind == "decision":
                    current.decisions.append(ev.get("text", ""))
                elif kind == "finding":
                    row = _finding(ev)
                    {"error": current.errors, "info": current.infos}.get(ev.get("level"), current.warnings).append(row)
                    if ev.get("mark") and ev.get("code"):
                        current.marks[row] = ev["code"]
                elif kind == "refused":
                    self.entry_finished.emit(rows[index], None, ev.get("text", ""))
                    current = None
                elif kind == "done":
                    if ev.get("cancelled"):
                        self.entry_finished.emit(rows[index], None, "")
                        cancelled = True
                    else:
                        current.ok, current.packed = bool(ev.get("ok")), bool(ev.get("packed"))
                        current.log = ev.get("log") or ""
                        current.rebuilt, current.deleted = int(ev.get("rebuilt") or 0), int(ev.get("deleted") or 0)
                        current.unchanged = int(ev.get("unchanged") or 0)
                        current.changed = int(ev.get("changed") or 0)
                        current.never_built = bool(ev.get("never_built"))
                        self.entry_finished.emit(rows[index], current, "")
                    current = None
            code = self.proc.wait()
            if current is not None or (index < len(rows) - 1 and not cancelled and not self._stopped):
                # процесс кончился посреди работы — сказать, а не молчать
                stderr.seek(0)
                tail = stderr.read().decode("utf-8", "replace").strip().splitlines()
                text = tail[-1] if tail else "%s завершился с кодом %s" % (Path(cli_command()[0]).name, code)
                start = index if current is not None else index + 1
                for row in rows[max(start, 0):]:
                    self.entry_finished.emit(row, None, text)
            self.all_finished.emit(cancelled or self._stopped)
        finally:
            stderr.close()
            try:
                os.remove(jobs_file)
            except OSError:
                pass
