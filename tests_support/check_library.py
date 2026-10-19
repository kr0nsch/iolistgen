#!/usr/bin/env python3
"""Сверка каталога iolistgen и заглушки plc-process-lib с исходниками выпущенной библиотеки.

Каталог пакета (``iolistgen/catalog.py``, ``iolistgen/fbapi.py``) и заглушка
``tests_support/pl_stub/`` написаны по контракту ``API.md``. Скрипт читает исходники самой
библиотеки (раскладка ``src/`` репозитория plc-process-lib, разбор — ``tools/codesys/stlayout.py``)
и сверяет с ними:

1. версию: ``library.version`` в ``tools/codesys/config.json`` библиотеки и закрепление в
   ``tools/codesys/config.json`` этого репозитория;
2. перечисления каталога — имена и значения по порядку;
3. структуры Cfg — поля по порядку, типы, границы массивов, значения по умолчанию (у массивов
   тревог — инициализаторы элементов);
4. структуры Cmd, Sts и Retain — поля по порядку, типы и начальные значения;
5. ФБ устройств — ``EXTENDS``, ``IMPLEMENTS``, ``VAR_INPUT``, ``VAR_OUTPUT`` (имена, типы, начальные
   значения), ``VAR_IN_OUT`` и ``VAR_IN_OUT CONSTANT``; вход ``itfTime`` базы ``FB_DeviceBase``;
6. константы ``GVL_Const`` таблицы 5.1 — состав, порядок, типы и значения;
7. полноту каталога: каждый ФБ устройства библиотеки (наследник ``FB_DeviceBase``) — тип
   устройства каталога, каждый DUT семейств устройств — в каталоге;
8. заглушку: каждый её DUT совпадает с DUT библиотеки (поля, типы, начальные значения, значения
   перечислений), у ФБ — те же публичные секции, константы и интерфейсы — те же объявления;
9. шаблоны текстов тревог пакета (``iolistgen/data/alarm_templates.csv``) с
   ``docs/alarm_templates.csv`` библиотеки — состав строк и тексты (исправленные строки — в
   ``TEMPLATE_FIXES`` с причиной).

Где библиотека: ключ ``--lib``, переменная ``PL_REPO`` (та же, что у ``build_from_repo`` в
``config.json``) или соседний каталог ``../plc-process-lib``. Тест ``pytests/test_library_source.py``
запускает те же проверки и пропускается, если исходников нет (CI без соседнего репозитория).

Коды выхода: 0 — расхождений нет, 1 — расхождения, 2 — исходники библиотеки не найдены.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT), str(ROOT / "tools"), str(ROOT / "tools" / "codesys")]

import stlayout as L  # noqa: E402
from iolistgen.catalog import (  # noqa: E402
    DEVICE_TYPES,
    GVL_CONST,
    LIBRARY_REF_VERSION,
    LIBRARY_TITLE,
    ST_TYPES,
    STRUCTS,
    FieldSpec,
)
from iolistgen.enums import DeviceType  # noqa: E402
from iolistgen.fbapi import ENUMS, FB_INTERFACES  # noqa: E402
from iolistgen.fbapi import STRUCTS as FB_STRUCTS  # noqa: E402
from iolistgen.stvalues import LiteralError, StType  # noqa: E402

STUB_DIR = ROOT / "tests_support" / "pl_stub"
LIBRARY_ENV = "PL_REPO"
DEFAULT_LIBRARY = ROOT.parent / "plc-process-lib"
LIBRARY_KEY = "plc-process-lib"
BUNDLED_TEMPLATES = ROOT / "iolistgen" / "data" / "alarm_templates.csv"
LIBRARY_TEMPLATES = Path("docs") / "alarm_templates.csv"
# Семейства DUT устройств (src/DUTs/<семейство>/): каждый тип из них должен быть в каталоге
DEVICE_FAMILIES = ("AnalogInput", "DigitalInput", "Motor", "Valve", "ControlValve", "Pid", "Common", "Alarm")
# DUT семейств, которые генератору не нужны: внутренние состояния и события журнала тревог
NOT_MODELLED = frozenset({"E_AlarmState", "ST_AlarmEvent", "U_RealBits", "E_AiSignalState"})
# Перечисления-индексы слотов тревог (каталог хранит их как StType индексов массивов astAlarm)
INDEX_ENUMS = ("E_AiAlarm", "E_DiAlarm", "E_MotorAlarm", "E_ValveAlarm", "E_CvAlarm", "E_PidAlarm")

Problems = list[str]


@dataclass
class Library:
    """Исходники библиотеки: объекты раскладки по имени, версия из её config.json."""

    root: Path
    objects: dict[str, L.StObject]
    version: str | None


def find_library(explicit: Path | None = None) -> Path | None:
    """Корень репозитория библиотеки (с ``src/``): ключ, ``PL_REPO`` или ``../plc-process-lib``."""
    candidates: list[Path] = []
    if explicit is not None:
        candidates.append(explicit)
    env = os.environ.get(LIBRARY_ENV)
    if env:
        candidates.append(Path(env) if Path(env).is_absolute() else ROOT / env)
    candidates.append(DEFAULT_LIBRARY)
    for candidate in candidates:
        if (candidate / "src" / "DUTs").is_dir():
            return candidate.resolve()
    return None


def scan(root: Path) -> dict[str, L.StObject]:
    result = L.scan(str(root), "src")
    if not result.ok:
        issues = "; ".join(issue.format() for issue in result.issues)
        raise SystemExit(f"check_library: раскладка {root} не читается: {issues}")
    return {obj.name: obj for obj in result.objects}


def load_library(root: Path) -> Library:
    version: str | None = None
    config = root / "tools" / "codesys" / "config.json"
    if config.is_file():
        data = json.loads(config.read_text(encoding="utf-8"))
        node = data.get("library", {}).get("version")
        version = str(node.get("default") if isinstance(node, dict) else node)
    return Library(root, scan(root), version)


# --- разбор объявлений ---------------------------------------------------------------------------


def norm(text: str | None) -> str:
    """Текст без комментариев и лишних пробелов: ``16#FFFF``, ``(ePriority:=E_AlarmPriority.High)``."""
    if not text:
        return ""
    flat = " ".join(L.strip_comments(text).split())
    return re.sub(r"\s*(:=|,|\(|\)|\[|\]|\.\.)\s*", r"\1", flat)


def members(obj: L.StObject) -> list[tuple[str, str, str]]:
    """Поля структуры: имя, тип, начальное значение (нормализованы)."""
    decl = L.parse_type_decl(obj.decl)
    if decl is None:
        return []
    return [(name, norm(m.type_text), norm(m.init_text)) for m in decl.members for name in m.name_list]


def enum_values(obj: L.StObject) -> list[tuple[str, int]]:
    decl = L.parse_type_decl(obj.decl)
    if decl is None or decl.kind != "enum":
        return []
    return [(name, int(value or "0")) for name, value, _ in decl.enum_values]


def var_blocks(obj: L.StObject) -> dict[str, list[tuple[str, str, str]]]:
    """Секции объявления POU или GVL: ``VAR_INPUT``, ``VAR_IN_OUT CONSTANT``… → (имя, тип, значение)."""
    blocks: dict[str, list[tuple[str, str, str]]] = {}
    for block in L.parse_var_blocks(obj.decl):
        key = " ".join([block.keyword, *block.modifiers])
        rows = blocks.setdefault(key, [])
        for decl in block.decls:
            rows += [(name, norm(decl.type_text), norm(decl.init_text)) for name in decl.name_list]
    return blocks


def library_constants(lib: Library) -> dict[str, int]:
    """Целые константы GVL_Const библиотеки — для границ массивов ``ARRAY[0..GVL_Const.X - 1]``."""
    values: dict[str, int] = {}
    gvl = lib.objects.get("GVL_Const")
    if gvl is None:
        return values
    for rows in var_blocks(gvl).values():
        for name, _, init in rows:
            if re.fullmatch(r"\d+", init):
                values[name] = int(init)
            elif re.fullmatch(r"16#[0-9A-Fa-f_]+", init):
                values[name] = int(init[3:].replace("_", ""), 16)
    return values


def eval_bound(text: str, constants: dict[str, int]) -> int:
    """Граница массива: число, ``GVL_Const.X`` и ``+``/``-`` между ними."""
    expr = re.sub(r"\b(?:GVL_Const\.)?([A-Z][A-Z0-9_]*)\b", lambda m: str(constants[m.group(1)]), text)
    if not re.fullmatch(r"[\d\s+\-]+", expr):
        raise ValueError(f"граница массива «{text}» не вычисляется")
    tokens = re.findall(r"\d+|[+-]", expr)
    total = int(tokens[0])
    for op, value in zip(tokens[1::2], tokens[2::2], strict=True):
        total = total + int(value) if op == "+" else total - int(value)
    return total


_ARRAY_RE = re.compile(r"^ARRAY\[(?P<low>[^\]]+?)\.\.(?P<high>[^\]]+)\]OF (?P<elem>\w+)$")


def array_type(type_text: str, constants: dict[str, int]) -> tuple[int, int, str] | None:
    match = _ARRAY_RE.match(type_text.replace("] OF", "]OF"))
    if match is None:
        return None
    return eval_bound(match["low"], constants), eval_bound(match["high"], constants), match["elem"]


def element_assignments(init: str) -> list[dict[str, str]]:
    """Инициализатор массива структур ``[(a:=1),(a:=2,b:=X)]`` → по словарю на элемент."""
    body = init.strip()
    if body.startswith("[") and body.endswith("]"):
        body = body[1:-1]
    result: list[dict[str, str]] = []
    for group in re.findall(r"\(([^()]*)\)", body):
        items: dict[str, str] = {}
        for part in group.split(","):
            name, _, value = part.partition(":=")
            items[name.strip()] = value.strip()
        result.append(items)
    return result


# --- проверки ------------------------------------------------------------------------------------


def check_version(lib: Library) -> Problems:
    problems: Problems = []
    if lib.version != LIBRARY_REF_VERSION:
        problems.append(
            f"версия: библиотека собирает {lib.version}, каталог iolistgen — {LIBRARY_REF_VERSION} "
            "(catalog.LIBRARY_REF_VERSION)"
        )
    config = json.loads((ROOT / "tools" / "codesys" / "config.json").read_text(encoding="utf-8"))
    pinned = config.get("libraries", {}).get(LIBRARY_KEY, {}).get("version")
    if pinned != LIBRARY_REF_VERSION:
        problems.append(
            f"config.json: libraries.{LIBRARY_KEY}.version = {pinned!r}, нужно закрепление {LIBRARY_REF_VERSION!r}"
        )
    return problems


def catalog_enums() -> dict[str, list[tuple[str, int]]]:
    """Все перечисления, которые знает iolistgen: fbapi, типы полей Cfg, индексы слотов тревог."""
    result: dict[str, list[tuple[str, int]]] = {name: list(values) for name, values in ENUMS.items()}
    for st_type in ST_TYPES.values():
        if st_type.kind == "enum":
            result[st_type.name] = list(zip(st_type.members, st_type.values, strict=True))
    for spec in DEVICE_TYPES.values():
        for field in STRUCTS[spec.cfg]:
            if field.index_enum is not None:
                enum = field.index_enum
                result.setdefault(enum.name, list(zip(enum.members, enum.values, strict=True)))
    return result


def check_enums(lib: Library) -> Problems:
    problems: Problems = []
    for name, expected in sorted(catalog_enums().items()):
        obj = lib.objects.get(name)
        if obj is None:
            problems.append(f"{name}: в библиотеке нет такого перечисления")
            continue
        actual = enum_values(obj)
        if actual != expected:
            problems.append(f"{name}: каталог {expected}, библиотека {actual}")
    return problems


def _expected_type(spec: FieldSpec) -> str:
    if spec.st_type is not None:
        return spec.st_type.name
    assert spec.struct is not None
    return spec.struct


def _parse_default(st_type: StType, text: str) -> object:
    if not text:
        return False if st_type.kind == "bool" else 0
    return st_type.parse(text)


def check_cfg_structs(lib: Library) -> Problems:
    problems: Problems = []
    constants = library_constants(lib)
    for name, specs in STRUCTS.items():
        obj = lib.objects.get(name)
        if obj is None:
            problems.append(f"{name}: в библиотеке нет такой структуры")
            continue
        fields = members(obj)
        if [f[0] for f in fields] != [spec.name for spec in specs]:
            problems.append(f"{name}: поля каталога {[s.name for s in specs]}, библиотеки {[f[0] for f in fields]}")
            continue
        for spec, (field, type_text, init) in zip(specs, fields, strict=True):
            where = f"{name}.{field}"
            if spec.array is not None:
                parsed = array_type(type_text, constants)
                if parsed != (spec.array[0], spec.array[1], spec.struct):
                    problems.append(
                        f"{where}: каталог ARRAY[{spec.array[0]}..{spec.array[1]}] OF {spec.struct}, "
                        f"библиотека {type_text}"
                    )
                    continue
                problems += _check_elements(where, spec, init)
                continue
            if type_text != _expected_type(spec):
                problems.append(f"{where}: тип каталога {_expected_type(spec)}, библиотеки {type_text}")
                continue
            if spec.st_type is None:
                if init:
                    problems.append(f"{where}: у вложенной структуры в библиотеке инициализатор {init}")
                continue
            try:
                actual = _parse_default(spec.st_type, init)
            except LiteralError as exc:
                problems.append(f"{where}: значение библиотеки «{init}» не разбирается ({exc.message})")
                continue
            expected = spec.default if spec.default is not None else _parse_default(spec.st_type, "")
            if actual != expected:
                problems.append(f"{where}: по умолчанию в каталоге {expected!r}, в библиотеке {actual!r} («{init}»)")
    return problems


def _check_elements(where: str, spec: FieldSpec, init: str) -> Problems:
    """Инициализатор массива структур: каталог хранит отличия элементов от умолчаний типа элемента."""
    assert spec.struct is not None and spec.array is not None
    element_fields = {field.name: field for field in STRUCTS[spec.struct]}
    expected = [dict(item) for item in spec.element_defaults]
    actual_text = element_assignments(init) if init else []
    actual: list[dict[str, object]] = []
    for items in actual_text:
        parsed: dict[str, object] = {}
        for key, value in items.items():
            field = element_fields.get(key)
            if field is None or field.st_type is None:
                return [f"{where}: в инициализаторе элемента неизвестное поле {key}"]
            parsed[key] = field.st_type.parse(value)
        actual.append(parsed)
    size = spec.array[1] - spec.array[0] + 1
    if actual and len(actual) != size:
        return [f"{where}: в инициализаторе библиотеки {len(actual)} элементов из {size}"]
    if actual != expected:
        return [f"{where}: элементы каталога {expected}, библиотеки {actual}"]
    return []


def check_fb_structs(lib: Library) -> Problems:
    problems: Problems = []
    for name, fields in FB_STRUCTS.items():
        obj = lib.objects.get(name)
        if obj is None:
            problems.append(f"{name}: в библиотеке нет такой структуры")
            continue
        expected = [(f.name, norm(f.st_type), norm(f.default)) for f in fields]
        actual = members(obj)
        if actual != expected:
            problems.append(f"{name}: каталог {expected}, библиотека {actual}")
    return problems


def _rows(fields: Iterable[object]) -> list[tuple[str, str, str]]:
    return [(f.name, norm(f.st_type), norm(f.default)) for f in fields]  # type: ignore[attr-defined]


def check_fb_interfaces(lib: Library) -> Problems:
    problems: Problems = []
    base = lib.objects.get("FB_DeviceBase")
    if base is None:
        return ["FB_DeviceBase: в библиотеке нет базы устройств"]
    base_inputs = var_blocks(base).get("VAR_INPUT", [])
    if [(name, type_text) for name, type_text, _ in base_inputs] != [("itfTime", "I_TimeSource")]:
        problems.append(f"FB_DeviceBase: VAR_INPUT {base_inputs}, каталог ждёт itfTime : I_TimeSource")
    for device_type, api in FB_INTERFACES.items():
        spec = DEVICE_TYPES[device_type]
        obj = lib.objects.get(api.fb)
        if obj is None or obj.header is None:
            problems.append(f"{api.fb}: в библиотеке нет такого ФБ")
            continue
        if obj.extends != [api.extends]:
            problems.append(f"{api.fb}: EXTENDS каталога {api.extends}, библиотеки {obj.extends}")
        implements = [api.implements] if api.implements else []
        if obj.implements != implements:
            problems.append(f"{api.fb}: IMPLEMENTS каталога {implements}, библиотеки {obj.implements}")
        blocks = var_blocks(obj)
        for key, fields in (("VAR_INPUT", api.inputs), ("VAR_OUTPUT", api.outputs)):
            if blocks.get(key, []) != _rows(fields):
                problems.append(f"{api.fb}: {key} каталога {_rows(fields)}, библиотеки {blocks.get(key, [])}")
        in_out = [(name, type_text) for name, type_text, _ in blocks.get("VAR_IN_OUT", [])]
        constant = [(name, type_text) for name, type_text, _ in blocks.get("VAR_IN_OUT CONSTANT", [])]
        if device_type is DeviceType.MOTOR_VFD:
            expected_in_out: list[tuple[str, str]] = []
            expected_constant: list[tuple[str, str]] = []
        else:
            expected_in_out = [("stCmd", spec.cmd)] + ([("stRetain", "ST_DeviceRetain")] if spec.has_retain else [])
            expected_constant = [("stCfg", spec.cfg)]
        if in_out != expected_in_out:
            problems.append(f"{api.fb}: VAR_IN_OUT каталога {expected_in_out}, библиотеки {in_out}")
        if constant != expected_constant:
            problems.append(f"{api.fb}: VAR_IN_OUT CONSTANT каталога {expected_constant}, библиотеки {constant}")
    return problems


def check_constants(lib: Library) -> Problems:
    gvl = lib.objects.get("GVL_Const")
    if gvl is None:
        return ["GVL_Const: в библиотеке нет списка констант"]
    blocks = [block for block in L.parse_var_blocks(gvl.decl) if block.keyword == "VAR_GLOBAL"]
    if not blocks:
        return ["GVL_Const: нет секции VAR_GLOBAL CONSTANT"]
    table = [(name, norm(d.type_text), norm(d.init_text)) for d in blocks[0].decls for name in d.name_list]
    expected = [(c.name, c.st_type, c.value) for c in GVL_CONST]
    if table != expected:
        missing = [row for row in table if row not in expected]
        extra = [row for row in expected if row not in table]
        return [f"GVL_Const (таблица 5.1): нет в каталоге {missing}; нет в библиотеке или иначе {extra}"]
    return []


def check_coverage(lib: Library) -> Problems:
    """Каждый ФБ устройства библиотеки и каждый DUT семейств устройств есть в каталоге."""
    problems: Problems = []
    modelled_fbs = {api.fb for api in FB_INTERFACES.values()}
    for name, obj in sorted(lib.objects.items()):
        if obj.kind == L.KIND_POU and obj.pou_kind == L.POU_FUNCTION_BLOCK and obj.subdir == "src":
            chain = obj.extends
            if chain and chain[0] in ("FB_DeviceBase", "FB_Motor") and name not in modelled_fbs:
                problems.append(f"{name}: ФБ устройства библиотеки без типа устройства в каталоге")
    known = set(catalog_enums()) | set(STRUCTS) | set(FB_STRUCTS)
    for name, obj in sorted(lib.objects.items()):
        if obj.kind != L.KIND_DUT or not obj.folder or obj.folder[0] not in DEVICE_FAMILIES:
            continue
        if name not in known and name not in NOT_MODELLED:
            problems.append(f"{name} (DUTs/{obj.folder[0]}): тип библиотеки не описан в каталоге")
    return problems


def check_stub(lib: Library, stub: dict[str, L.StObject]) -> Problems:
    problems: Problems = []
    for name, obj in sorted(stub.items()):
        original = lib.objects.get(name)
        if original is None:
            problems.append(f"заглушка: {name} — в библиотеке нет такого объекта")
            continue
        if obj.kind == L.KIND_DUT:
            if enum_values(obj) != enum_values(original) or members(obj) != members(original):
                problems.append(
                    f"заглушка: {name} отличается от библиотеки: {members(obj) or enum_values(obj)} — "
                    f"{members(original) or enum_values(original)}"
                )
        elif obj.kind == L.KIND_POU:
            if obj.extends != original.extends:
                problems.append(f"заглушка: {name}: EXTENDS {obj.extends}, в библиотеке {original.extends}")
            mine, theirs = var_blocks(obj), var_blocks(original)
            for key in ("VAR_INPUT", "VAR_OUTPUT", "VAR_IN_OUT", "VAR_IN_OUT CONSTANT"):
                if mine.get(key, []) != theirs.get(key, []):
                    problems.append(f"заглушка: {name}: {key} {mine.get(key, [])}, в библиотеке {theirs.get(key, [])}")
        elif obj.kind == L.KIND_GVL:
            declared = {row[0]: row for rows in var_blocks(original).values() for row in rows}
            for rows in var_blocks(obj).values():
                for row in rows:
                    if declared.get(row[0]) != row:
                        problems.append(f"заглушка: {name}.{row[0]} = {row}, в библиотеке {declared.get(row[0])}")
        elif obj.kind == L.KIND_ITF:
            if obj.extends != original.extends:
                problems.append(f"заглушка: {name}: EXTENDS {obj.extends}, в библиотеке {original.extends}")
            theirs_methods = {m.name: norm(m.decl) for m in original.methods}
            for method in obj.methods:
                if theirs_methods.get(method.name) != norm(method.decl):
                    problems.append(f"заглушка: {name}.{method.name} отличается от библиотеки")
    return problems


# Строки шаблонов, которые пакет исправляет относительно файла библиотеки: (тип, слот) → причина.
# В двух строках файла библиотеки 1.0.0 причина записана через запятую в колонке operator_action,
# а последствие с «;» сдвинулось в cause и consequence (на 7 колонок — 7 полей, ошибку не видно).
TEMPLATE_FIXES: dict[tuple[str, int], str] = {
    ("MotorVfd", 6): "в файле библиотеки 1.0.0 колонки сдвинуты: причина — в operator_action через запятую",
    ("Valve", 2): "в файле библиотеки 1.0.0 колонки сдвинуты: причина — в operator_action через запятую",
}


def read_templates(path: Path) -> dict[tuple[str, int], dict[str, str]]:
    lines = [line for line in path.read_text(encoding="utf-8-sig").splitlines() if not line.startswith("#")]
    rows = list(csv.DictReader(lines, delimiter=";"))
    return {(row["type"], int(row["slot"])): {k: (v or "").strip() for k, v in row.items()} for row in rows}


def _joined(fixed: dict[str, str]) -> tuple[str, str]:
    """Исправленная строка в раскладке файла библиотеки: (operator_action, cause + «;» + consequence)."""
    return f"{fixed['operator_action']}, {fixed['cause']}", fixed["consequence"]


def check_templates(lib: Library) -> Problems:
    library_file = lib.root / LIBRARY_TEMPLATES
    if not library_file.is_file():
        return [f"{LIBRARY_TEMPLATES}: в библиотеке нет файла шаблонов"]
    if not BUNDLED_TEMPLATES.is_file():
        return [f"{BUNDLED_TEMPLATES.relative_to(ROOT).as_posix()}: в пакете нет шаблонов"]
    theirs = read_templates(library_file)
    mine = read_templates(BUNDLED_TEMPLATES)
    problems: Problems = []
    if set(theirs) != set(mine):
        problems.append(f"шаблоны тревог: состав строк пакета {sorted(mine)} и библиотеки {sorted(theirs)} разный")
    for key in sorted(set(theirs) & set(mine)):
        same_key = (mine[key]["suffix"], mine[key]["text_ru"]) == (theirs[key]["suffix"], theirs[key]["text_ru"])
        if key in TEMPLATE_FIXES:
            if not same_key:
                problems.append(f"шаблоны тревог {key}: суффикс или текст отличаются от библиотеки")
            if mine[key] == theirs[key]:
                problems.append(f"шаблоны тревог {key}: исправление больше не нужно — уберите его из TEMPLATE_FIXES")
            action, consequence = _joined(mine[key])
            library_consequence = f"{theirs[key]['cause']}, {theirs[key]['consequence']}"
            if (action, consequence) != (theirs[key]["operator_action"], library_consequence):
                problems.append(f"шаблоны тревог {key}: исправление меняет не только разбиение колонок")
        elif mine[key] != theirs[key]:
            problems.append(f"шаблоны тревог {key}: пакет {mine[key]}, библиотека {theirs[key]}")
    return problems


# Проверки: ключ (для тестов и --only) → название и функция
CHECKS: dict[str, tuple[str, Callable[[Library], Problems]]] = {
    "version": ("версия", check_version),
    "enums": ("перечисления", check_enums),
    "cfg": ("структуры Cfg", check_cfg_structs),
    "cmd_sts_retain": ("структуры Cmd, Sts, Retain", check_fb_structs),
    "fb": ("ФБ устройств", check_fb_interfaces),
    "constants": ("константы GVL_Const", check_constants),
    "coverage": ("полнота каталога", check_coverage),
    "stub": ("заглушка", lambda lib: check_stub(lib, scan(STUB_DIR))),
    "templates": ("шаблоны текстов тревог", check_templates),
}


def run_checks(lib: Library, names: Sequence[str] | None = None) -> dict[str, Problems]:
    return {name: CHECKS[name][1](lib) for name in (names or list(CHECKS))}


def main(argv: Sequence[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):  # Windows по умолчанию пишет в консоль cp1251
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(
        prog="check_library.py",
        description="Сверка каталога iolistgen и заглушки plc-process-lib с исходниками библиотеки.",
    )
    parser.add_argument("--lib", type=Path, help=f"корень репозитория библиотеки ({LIBRARY_ENV}, ../{LIBRARY_TITLE})")
    args = parser.parse_args(argv)
    root = find_library(args.lib)
    if root is None:
        print(f"check_library: исходники {LIBRARY_TITLE} не найдены: --lib, {LIBRARY_ENV} или ../{LIBRARY_TITLE}")
        return 2
    lib = load_library(root)
    print(f"== {LIBRARY_TITLE} {lib.version}: {root}")
    failed = 0
    for name, problems in run_checks(lib).items():
        print(f"   {CHECKS[name][0]}: {'совпадает' if not problems else f'расхождений {len(problems)}'}")
        for problem in problems:
            print(f"     - {problem}")
        failed += len(problems)
    counts = (
        f"перечислений {len(catalog_enums())}, структур Cfg {len(STRUCTS)}, Cmd/Sts/Retain {len(FB_STRUCTS)}, "
        f"ФБ {len(FB_INTERFACES)}, констант {len(GVL_CONST)}, слотов тревог "
        f"{sum(len(spec.alarm_slots) for spec in DEVICE_TYPES.values())}"
    )
    print(f"check_library: сверено {counts}; расхождений {failed}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
