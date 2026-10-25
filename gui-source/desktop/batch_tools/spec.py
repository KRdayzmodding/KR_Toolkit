# -*- coding: utf-8 -*-
"""Три массовые тулзы — одно окно (window.BatchWindow), разные описания.

Окно само ничего не перегоняет: план — у командной строки (`--dry-run --json`),
работа — `--jobs-file … --json` (юзер 23.10.2026: «UI, который общается по CLI»).
Описание говорит окну, какую командную строку звать, что принимать
перетаскиванием и какие у тулзы настройки.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Tuple

SWITCH, SEGMENT, TEXT = "switch", "segment", "text"


@dataclass
class Option:
    key: str
    kind: str
    label: str                                  #: ключ текста
    desc: str = ""                              #: ключ текста пояснения
    default: object = None
    #: для сегмента: (значение, ключ текста)
    choices: Tuple[Tuple[str, str], ...] = ()
    #: значение → ключи командной строки
    args: Callable[[object], List[str]] = lambda value: []
    #: показывать ли строку при таких значениях (п. 51: видно то, что имеет смысл)
    visible: Callable[[Dict[str, object]], bool] = lambda opts: True
    #: доступна ли правка; иначе — ключ текста с причиной (п. 53)
    locked: Callable[[Dict[str, object]], Optional[str]] = lambda opts: None


def _flag(name: str) -> Callable[[object], List[str]]:
    return lambda value: [name] if value else []


def _value(name: str) -> Callable[[object], List[str]]:
    return lambda value: [name, str(value)]


DELETE = Option("delete_source", SWITCH, "opt.delete", "opt.delete.desc", False, args=_flag("--delete-source"))
OVERWRITE = Option("overwrite", SWITCH, "opt.overwrite", "opt.overwrite.desc", False, args=_flag("--overwrite"))


@dataclass
class ToolSpec:
    key: str                     #: texture_converter — имя файла состояния и папки копий
    cli: str                     #: подкоманда `python -m batch_kit` и имя командной строки Имя.exe
    exe: str                     #: TextureConverter → командная строка TextureConverter.exe рядом
    version_module: str          #: batch_kit.texture_version
    icon: str                    #: имя FluentIcon
    #: что берём перетаскиванием и в выборе файлов (папки — всегда)
    suffixes: Tuple[str, ...]
    options: List[Option] = field(default_factory=list)
    prefix: str = ""             #: префикс ключей текстов этой тулзы

    def args(self, values: Dict[str, object]) -> List[str]:
        out: List[str] = []
        for opt in self.options:
            out += opt.args(values.get(opt.key, opt.default))
        return out

    def defaults(self) -> Dict[str, object]:
        return {opt.key: opt.default for opt in self.options}


TEXTURES = ToolSpec(
    "texture_converter", "textures", "TextureConverter", "batch_kit.texture_version", "PHOTO",
    (".png", ".tga", ".dds", ".jpg", ".jpeg", ".paa", ".edds"),
    [Option("image_to", SEGMENT, "opt.image_to", "opt.image_to.desc", "paa",
            (("paa", "fmt.paa"), ("edds", "fmt.edds")), _value("--image-to")),
     Option("edds_format", SEGMENT, "opt.edds_format", "opt.edds_format.desc", "BGRA8",
            (("BGRA8", "fmt.bgra8"), ("DXT5", "fmt.dxt5"), ("DXT1", "fmt.dxt1")), _value("--edds-format"),
            visible=lambda opts: opts.get("image_to") == "edds"),
     Option("texture_to", SEGMENT, "opt.texture_to", "opt.texture_to.desc", "png",
            (("png", "fmt.png"), ("tga", "fmt.tga"), ("dds", "fmt.dds")), _value("--texture-to")),
     DELETE, OVERWRITE],
    "textures")

MODELS = ToolSpec(
    "model_converter", "models", "ModelConverter", "batch_kit.model_version", "IOT",
    (".p3d",),
    [DELETE,
     Option("suffix", TEXT, "opt.suffix", "opt.suffix.desc", "_mlod", args=_value("--suffix"),
            locked=lambda opts: "opt.suffix.locked" if opts.get("delete_source") else None),
     OVERWRITE],
    "models")

DEBIN = ToolSpec(
    "debinarizer", "debin", "DeBinarizer", "batch_kit.debin_version", "CODE",
    (".bin", ".cpp", ".hpp", ".rvmat", ".bisurf", ".cfg", ".sqm"),
    [DELETE, OVERWRITE],
    "debin")

#: распаковка PBO целиком — работой DeBinarizer и Model Converter (юзер 24.10.2026:
#: у каждой тулзы своё). Готовая папка не перезаписывается, поэтому без OVERWRITE
PBO = ToolSpec(
    "pbo_unpacker", "pbo", "PboUnpacker", "batch_kit.pbo_version", "ZIP_FOLDER",
    # .ebo принимается, чтобы отказ был виден в окне, а не молчаливый игнор
    (".pbo", ".ebo"),
    [Option("layout", SEGMENT, "opt.layout", "opt.layout.desc", "prefix",
            (("prefix", "layout.prefix"), ("flat", "layout.flat")), _value("--layout")),
     DELETE],
    "pbo")

#: ANM ⇄ TXA — только сам файл, без ASI и других ANM (юзер 24.10.2026)
ANM = ToolSpec(
    "anm_converter", "anm", "AnmConverter", "batch_kit.anm_version", "MOVIE",
    (".anm", ".txa"),
    [DELETE, OVERWRITE],
    "anm")

SPECS = {spec.key: spec for spec in (TEXTURES, MODELS, DEBIN, PBO, ANM)}
