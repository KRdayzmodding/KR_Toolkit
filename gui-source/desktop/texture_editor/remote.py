# -*- coding: utf-8 -*-
"""Работа [KR] Texture Editor — через командную строку TextureEditor.exe.

Окно само текстуры не читает, не правит и не пишет (юзер 24.10.2026: окно —
только показ, работа — в командной строке). Просмотр и Френель зовут
запущенный один раз `TextureEditor.exe serve`: ответ на ползунок должен быть
мгновенным, а запуск exe — сотни миллисекунд. Пакетные страницы (размер, SMDI
по папке) запускают свою команду с --json: так их можно остановить, и
просмотр на это время не встаёт.

Собранное окно зовёт exe рядом с собой, из исходников —
`python -m texture_editor_kit`.
"""
from __future__ import annotations

import atexit
import json
import os
import signal
import subprocess
import sys
import tempfile
import threading
from pathlib import Path
from typing import Callable, Dict, List, NamedTuple, Optional, Tuple

import numpy as np
from PySide6.QtCore import QThread, Signal

HERE = Path(__file__).resolve().parent
KITS = HERE.parents[1] / "kits"


class OpenError(ValueError):
    """Файл не открылся, и командная строка сказала почему."""


class EditError(ValueError):
    """Правка не сделана, и командная строка сказала почему."""


def cli_command() -> List[str]:
    if getattr(sys, "frozen", False):
        # поставка — одна папка: командная строка лежит рядом с окном
        return [str(Path(sys.executable).resolve().parent / "TextureEditor.exe")]
    return [sys.executable, "-m", "texture_editor_kit"]


def _cwd() -> Optional[str]:
    return str(KITS) if KITS.is_dir() else None


def _env() -> dict:
    return dict(os.environ, PYTHONIOENCODING="utf-8")


# ====================================================================== serve
class Client:
    """Один процесс serve на окно; запросы по одному, ответы по порядку."""

    KINDS = {"open": OpenError, "edit": EditError, "os": OSError}

    def __init__(self):
        self.proc: Optional[subprocess.Popen] = None
        self.stderr = None
        self.rid = 0
        self.lock = threading.Lock()

    def _start(self) -> None:
        self.stderr = tempfile.TemporaryFile()
        self.proc = subprocess.Popen(cli_command() + ["serve"], cwd=_cwd(), env=_env(),
                                     stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=self.stderr,
                                     creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))

    def _died(self) -> OSError:
        tail = ""
        if self.stderr is not None:
            self.stderr.seek(0)
            lines = self.stderr.read().decode("utf-8", "replace").strip().splitlines()
            tail = lines[-1] if lines else ""
        self.proc = None
        return OSError("%s не отвечает%s" % (Path(cli_command()[0]).name, ": " + tail if tail else ""))

    def _send(self, message: dict) -> None:
        self.proc.stdin.write((json.dumps(message, ensure_ascii=False) + "\n").encode("utf-8"))
        self.proc.stdin.flush()

    def call(self, op: str, progress: Optional[Callable[[float], None]] = None, **args) -> dict:
        # окно зовёт из своего потока; повторный вход (processEvents в ходе
        # сохранения) не ждёт — вторая операция посреди первой спутала бы ответы
        if not self.lock.acquire(blocking=False):
            raise EditError("занято: идёт предыдущая операция")
        try:
            if self.proc is None or self.proc.poll() is not None:
                self._start()
            self.rid += 1
            rid, stopped = self.rid, None
            try:
                self._send({"id": rid, "op": op, "args": args})
            except OSError:
                raise self._died() from None
            while True:
                line = self.proc.stdout.readline()
                if not line:
                    raise self._died()
                reply = json.loads(line)
                if "progress" in reply:
                    if progress is not None and stopped is None:
                        try:
                            progress(float(reply["progress"]))
                        except Exception as exc:  # noqa: BLE001 — человек отменил: сказать сервису
                            stopped = exc
                            self._send({"op": "cancel", "of": rid})
                    continue
                if reply.get("ok"):
                    if stopped is not None:
                        raise stopped                  # успел доделать — но человек отменял
                    return reply["result"]
                if stopped is not None:
                    raise stopped
                raise self.KINDS.get(reply.get("kind"), ValueError)(reply.get("error", ""))
        finally:
            self.lock.release()

    def close(self) -> None:
        if self.proc is not None and self.proc.poll() is None:
            try:
                self.proc.stdin.close()
                self.proc.wait(5)
            except (OSError, subprocess.TimeoutExpired):
                self.proc.kill()
        self.proc = None


_CLIENT: Optional[Client] = None
_INFO: Optional[dict] = None


def client() -> Client:
    global _CLIENT
    if _CLIENT is None:
        _CLIENT = Client()
        atexit.register(_CLIENT.close)
    return _CLIENT


def info() -> dict:
    """Постоянные командной строки: форматы, папки копий, материалы, размеры."""
    global _INFO
    if _INFO is None:
        _INFO = client().call("info")
    return _INFO


def _load(result: dict) -> np.ndarray:
    path = result["npy"]
    try:
        return np.load(path, allow_pickle=False)
    finally:
        try:
            os.remove(path)
        except OSError:
            pass


# ====================================================================== открытый файл
class Level(NamedTuple):
    width: int
    height: int
    packed: bool              #: лежал ли сжатым


class RemoteTexture:
    """Открытый файл: уровни и сведения; пиксели уровня — по требованию, один раз."""

    def __init__(self, meta: dict):
        self.handle = int(meta["handle"])
        self.path = Path(meta["path"])
        self.kind = meta["kind"]
        self.levels = [Level(int(w), int(h), bool(p)) for w, h, p in meta["levels"]]
        self.tags = dict(meta.get("tags") or {})
        self.file_size = int(meta["file_size"])
        self.blocky = bool(meta["blocky"])
        self.note = meta.get("note") or ""
        self._cache: Dict[int, np.ndarray] = {}
        self._reasons: Optional[dict] = None

    @property
    def width(self) -> int:
        return self.levels[0].width

    @property
    def height(self) -> int:
        return self.levels[0].height

    @property
    def size(self) -> tuple:
        return (self.width, self.height)

    def pixels(self, level: int = 0) -> np.ndarray:
        if level not in self._cache:
            self._cache[level] = _load(client().call("pixels", handle=self.handle, path=str(self.path),
                                                     level=level))
        return self._cache[level]

    def reasons(self) -> dict:
        """Почему правки неприменимы ({"smdi", "map"}) — один запрос на файл."""
        if self._reasons is None:
            self._reasons = client().call("reasons", path=str(self.path))
        return self._reasons

    def ref(self, level: int) -> dict:
        return {"handle": self.handle, "path": str(self.path), "level": level}


def open_texture(path) -> RemoteTexture:
    return RemoteTexture(client().call("open", path=str(path)))


def neighbours(path: Path) -> List[Path]:
    return [Path(p) for p in client().call("neighbours", path=str(path))["paths"]]


def save_as(texture: RemoteTexture, level: int, target: Path,
            progress: Optional[Callable[[float], None]] = None) -> None:
    client().call("save_as", progress=progress, target=str(target), **texture.ref(level))


# ====================================================================== правки
def smdi_reason(path: Path) -> Optional[str]:
    return client().call("reasons", path=str(path))["smdi"]


def map_edit_reason(path: Path) -> Optional[str]:
    return client().call("reasons", path=str(path))["map"]


def smdi_backup(path: Path) -> Optional[Path]:
    found = client().call("smdi_backup", path=str(path))["path"]
    return Path(found) if found else None


def run_smdi(path: Path, sp: float, keep_backup: bool, overwrite: bool) -> str:
    return client().call("run_smdi", path=str(path), sp=sp, keep_backup=keep_backup,
                         overwrite=overwrite)["state"]


def invert_green(path: Path) -> Path:
    return Path(client().call("invert_green", path=str(path))["path"])


def compose_smdi(texture: RemoteTexture, level: int, other: Optional[Path] = None,
                 constant: Optional[float] = None, open_is_intensity: bool = True) -> Path:
    return Path(client().call("compose_smdi", other=str(other) if other else None, constant=constant,
                              open_is_intensity=open_is_intensity, **texture.ref(level))["path"])


def adjust_smdi(texture: RemoteTexture, level: int, **settings) -> Path:
    return Path(client().call("adjust_smdi", **settings, **texture.ref(level))["path"])


def split_channels(texture: RemoteTexture, level: int) -> Tuple[List[Path], List[str]]:
    result = client().call("split_channels", **texture.ref(level))
    return [Path(p) for p in result["written"]], list(result["flat"])


# ====================================================================== списки пакетных страниц
def resize_collect(paths) -> List[Path]:
    return [Path(p) for p in client().call("resize_collect", paths=[str(p) for p in paths])["paths"]]


def scan_census(folder: Path) -> Tuple[int, int]:
    result = client().call("scan_census", folder=str(folder))
    return result["total"], result["todo"]


def scan_unfiltered(folder: Path) -> List[Path]:
    return [Path(p) for p in client().call("scan_unfiltered", folder=str(folder))["paths"]]


def scan_snapshot(folder: Path) -> list:
    """Снимок папки — как его отдаёт командная строка; окну он непрозрачен."""
    return client().call("scan_snapshot", folder=str(folder))["stamps"]


def scan_pending(folder: Path, now: float, before: list) -> Tuple[List[Path], list]:
    result = client().call("scan_pending", folder=str(folder), now=now, before=before or [])
    return [Path(p) for p in result["ready"]], result["stamps"]


# ====================================================================== Френель
def fresnel_material(name: str) -> Tuple[float, float]:
    result = client().call("fresnel_material", name=name)
    return result["n"], result["k"]


def fresnel_view(n: float, k: float, width: int, height: int, ramp_height: int, ball: int) -> dict:
    """Всё для перерисовки страницы: известный материал, полоса, шар, кривая, строка стейджа."""
    result = client().call("fresnel_view", n=n, k=k, width=width, height=height,
                           ramp_height=ramp_height, ball=ball)
    result["ramp"], result["ball"] = _load(result["ramp"]), _load(result["ball"])
    result["curve"] = np.asarray(result["curve"])
    return result


def fresnel_body(side: int, turn: float, tilt: float, level: float, power: float,
                 n: float, k: float, width: int, height: int) -> np.ndarray:
    return _load(client().call("fresnel_body", side=side, turn=turn, tilt=tilt, level=level, power=power,
                               n=n, k=k, width=width, height=height))


def fresnel_parse(text: str):
    found = client().call("fresnel_parse", text=text)["stage"]
    return tuple(found) if found is not None else None


def fresnel_read(path: str) -> dict:
    return client().call("fresnel_read", path=str(path))


def fresnel_save(n: float, k: float, width: int, height: int, target: Path) -> None:
    client().call("fresnel_save", n=n, k=k, width=width, height=height, target=str(target))


# ====================================================================== пакетные команды
class CliJob(QThread):
    """Одна пакетная команда (`resize`, `smdi`) с --json: события — сигналом по ходу."""

    event = Signal(dict)
    exited = Signal(int)

    def __init__(self, args: List[str], files: List[Path], parent=None):
        super().__init__(parent)
        self.args, self.files = args, [str(p) for p in files]
        self.proc: Optional[subprocess.Popen] = None

    def run(self) -> None:
        fd, jobs = tempfile.mkstemp(prefix="kr_texedit_", suffix=".json")
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(self.files, fh, ensure_ascii=False)
        flags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0) | getattr(subprocess, "CREATE_NO_WINDOW", 0)
        try:
            try:
                self.proc = subprocess.Popen(cli_command() + self.args + ["--jobs-file", jobs, "--json"],
                                             cwd=_cwd(), env=_env(), stdin=subprocess.DEVNULL,
                                             stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                             creationflags=flags)
            except OSError as exc:
                self.event.emit({"event": "problem", "text": str(exc)})
                self.exited.emit(-1)
                return
            for raw in self.proc.stdout:
                try:
                    self.event.emit(json.loads(raw.decode("utf-8")))
                except ValueError:
                    continue
            self.exited.emit(self.proc.wait())
        finally:
            try:
                os.remove(jobs)
            except OSError:
                pass

    def stop(self) -> None:
        """Мягкая остановка: Ctrl+Break — команда доделает текущий файл и выйдет."""
        if self.proc is not None and self.proc.poll() is None:
            try:
                os.kill(self.proc.pid, signal.CTRL_BREAK_EVENT)
            except (OSError, AttributeError):
                self.proc.terminate()
