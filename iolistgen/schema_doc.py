"""Справочник схемы перечня: колонки, типы устройств, роли, параметры Cfg, Modbus, правила.

Один источник истины — каталоги пакета (``columns``, ``catalog``, ``modbus``, ``diagnostics``).
Из них печатается ``iolistgen schema`` и обновляются генерируемые блоки ``docs/schema.md``
(между маркерами ``<!-- BEGIN iolistgen:<раздел> -->`` и ``<!-- END iolistgen:<раздел> -->``)::

    python -m iolistgen.schema_doc docs/schema.md          # обновить блоки
    python -m iolistgen.schema_doc docs/schema.md --check  # только проверить (для CI)
"""

from __future__ import annotations

import argparse
import re
import sys
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

from iolistgen.catalog import (
    ALARM_SLOTS,
    AUX_SIGNAL_TYPES,
    AUX_TITLE,
    DEVICE_TYPES,
    LIBRARY_NAMESPACE,
    LIBRARY_VERSION,
    LINK_COLUMNS,
    STRUCTS,
    FieldSpec,
    leaf_fields,
)
from iolistgen.columns import COLUMNS, REQUIRED_COLUMNS
from iolistgen.diagnostics import GROUPS, RULES
from iolistgen.enums import DeviceType, Role, SignalType
from iolistgen.modbus import FUNCTIONS, ModbusType
from iolistgen.stvalues import StType, format_real, format_time

_LEVELS = {"signal": "строка", "device": "главная строка", "identity": "любая строка устройства"}


def _cell(text: str) -> str:
    return text.replace("|", "\\|")


def columns_table() -> str:
    lines = [
        "| Колонка | Заголовок и синонимы | Где читается | Обязательна | Значение | Назначение |",
        "|---|---|---|---|---|---|",
    ]
    for spec in COLUMNS:
        name = f"`{spec.name}`" + (" ★" if spec.name in REQUIRED_COLUMNS else "")
        aliases = ", ".join([f"«{spec.title}»", *(f"«{alias}»" for alias in spec.aliases)])
        lines.append(
            f"| {name} | {_cell(aliases)} | {_LEVELS[spec.level]} | {_cell(spec.required)} | "
            f"{_cell(spec.value)} | {_cell(spec.description)} |"
        )
    lines.append("")
    lines.append("★ — колонка должна быть в заголовке файла (её отсутствие — одна ошибка IOL003 на весь файл).")
    return "\n".join(lines)


def _delay(path: str | None) -> str:
    return f"`{path}`" if path else "—"


def device_types_table() -> str:
    lines = [
        "| Тип устройства | ФБ | Cmd, Cfg, Sts | Регистров Sts | Retain | Главная роль | Задержка вкл. | "
        "Задержка откл. | Ссылки |",
        "|---|---|---|---:|---|---|---|---|---|",
    ]
    for spec in DEVICE_TYPES.values():
        main = " или ".join(f"`{role.value}`" for role in spec.main_roles) or "строка устройства без сигнала"
        links = ", ".join(f"`{link.column}`" for link in spec.links) or "—"
        lines.append(
            f"| `{spec.device_type.value}` | `{LIBRARY_NAMESPACE}.{spec.fb}` | `{spec.cmd}`, `{spec.cfg}`, "
            f"`{spec.sts}` | {spec.sts_registers} | {'да' if spec.has_retain else 'нет'} | {main} | "
            f"{_delay(spec.delay_on)} | {_delay(spec.delay_off)} | {links} |"
        )
    return "\n".join(lines)


def roles_table() -> str:
    lines = [
        "| Тип устройства | Роль | Сигнал | Типы данных MB | Вход/выход ФБ | Обязательна | Назначение |",
        "|---|---|---|---|---|---|---|",
    ]
    for spec in DEVICE_TYPES.values():
        for index, role in enumerate(spec.roles):
            device = f"`{spec.device_type.value}`" if index == 0 else ""
            types = ", ".join(t.value for t in SignalType if t in role.signal_types)
            mb_types = (
                ", ".join(t.value for t in ModbusType if t in role.mb_types)
                if SignalType.MB in role.signal_types
                else "—"
            )
            if role.main and role.role in spec.main_roles and len(spec.main_roles) > 1:
                required = "главная (одна из форм)"
            elif role.main:
                required = "главная, да"
            else:
                required = "да" if role.required else "нет"
            title = role.title + (f"; {role.note}" if role.note else "")
            lines.append(
                f"| {device} | `{role.role.value}` | {types} | {_cell(mb_types)} | `{_cell(role.pin)}` "
                f"({role.direction.label}) | {required} | {_cell(title)} |"
            )
    for spec in DEVICE_TYPES.values():
        if not spec.has_io:
            lines.append(
                f"| `{spec.device_type.value}` | — | — | — | — | — | сигналов ввода-вывода нет: строка устройства без "
                "`signal_type` и `role`; привязки ФБ (`rPv_eu`, `xPvValid`, `xTrack`, `rOutAct_pct`) пишет логика "
                "станции |"
            )
    aux_types = ", ".join(t.value for t in SignalType if t in AUX_SIGNAL_TYPES)
    lines.append(
        f"| любой; без устройства | `{Role.AUX.value}` | {aux_types} | все | — (нет) | нет, строк сколько угодно | "
        f"{_cell(AUX_TITLE)}; читает и пишет код приложения |"
    )
    return "\n".join(lines)


def alarm_slots_table() -> str:
    lines = ["| Тип устройства | Слот | Код тревоги | Тревога | Приоритет по умолчанию |", "|---|---:|---|---|---|"]
    for spec in DEVICE_TYPES.values():
        defaults = {leaf.path: leaf.default for leaf in leaf_fields(spec.cfg)}
        for index, slot in enumerate(spec.alarm_slots):
            device = f"`{spec.device_type.value}`" if index == 0 else ""
            priority = defaults[f"astAlarm[{slot.index}].ePriority"]
            lines.append(f"| {device} | {slot.index} | `<DEV>.{slot.suffix}` | {slot.title} | {priority} |")
    return "\n".join(lines)


def _format_default(st_type: StType, value: object) -> str:
    if st_type.kind == "time":
        return format_time(int(str(value)))
    if st_type.kind == "real":
        return format_real(float(str(value)))
    if st_type.kind == "bool":
        return "TRUE" if value is True else "FALSE"
    if st_type.kind == "word":
        return f"16#{int(str(value)):04X}"
    return str(value)


def _source_of(device_type: DeviceType, path: str) -> str:
    """Как задаётся поле: колонкой, генератором или params."""
    if path == "udiAlarmIdBase":
        return "генератор: `dev_no` · 10"
    managed: dict[DeviceType, dict[str, str]] = {
        DeviceType.ANALOG_INPUT: {
            "eInput": "params; PV по Modbus: `REAL` → Eng, целое → Raw",
            "rRangeLo_eu": "колонка `range_min`",
            "rRangeHi_eu": "колонка `range_max`",
            "astLimit[i].xEnable": "колонки `sp_hh`, `sp_h`, `sp_l`, `sp_ll`",
            "astLimit[i].rSetpoint_eu": "колонки `sp_hh`, `sp_h`, `sp_l`, `sp_ll`",
            "astLimit[i].tOnDelay": "колонка `delay_on_s` (все включённые уставки) или params",
            "astLimit[i].tOffDelay": "колонка `delay_off_s` или params",
            "astAlarm[i].ePriority": "колонка `alarm_priority` (слоты 0–3) или params",
        },
        DeviceType.DIGITAL_INPUT: {
            "tOnDelay": "колонка `delay_on_s` или params",
            "tOffDelay": "колонка `delay_off_s` или params",
            "astAlarm[i].ePriority": "колонка `alarm_priority` (слот 0 State) или params",
        },
        DeviceType.MOTOR: {
            "xFbUsed": "params; нет строки `RUN_FB` → FALSE",
            "tFbStart": "колонка `delay_on_s` или params",
            "tFbStop": "колонка `delay_off_s` или params",
            "astAlarm[i].ePriority": "колонка `alarm_priority` (слоты Medium) или params",
        },
        DeviceType.VALVE: {
            "eType": "params; CMD_OPEN + CMD_CLOSE → Motorized, CMD_COIL — SolenoidEto или SolenoidEtc",
            "xZsoUsed": "params; нет строки `ZSO` → FALSE",
            "xZscUsed": "params; нет строки `ZSC` → FALSE",
            "xTorqueUsed": "params; есть `TQO`/`TQC` → TRUE",
            "tTravel": "колонка `delay_on_s` или params",
            "astAlarm[i].ePriority": "колонка `alarm_priority` (слоты Medium) или params",
        },
        DeviceType.CONTROL_VALVE: {
            "xFbUsed": "params; задан `link_fb` → TRUE",
            "tDev": "колонка `delay_on_s` или params",
            "astAlarm[i].ePriority": "колонка `alarm_priority` (слоты Medium) или params",
        },
        DeviceType.PID: {
            "rPvMin_eu": "колонка `range_min` или params",
            "rPvMax_eu": "колонка `range_max` или params",
            "rSpMin_eu": "params; задан диапазон PV → `range_min`",
            "rSpMax_eu": "params; задан диапазон PV → `range_max`",
            "astAlarm[i].ePriority": "колонка `alarm_priority` (слот 0 PvInvalid) или params",
        },
    }
    managed[DeviceType.MOTOR_VFD] = {
        **managed[DeviceType.MOTOR],
        "xFbUsed": "params; нет `RUN_FB` и `stVfd.xFbFromComm = FALSE` → FALSE",
    }
    return managed[device_type].get(path, "params")


def _struct_rows(device_type: DeviceType, struct: str, prefix: str = "") -> list[tuple[str, str, str, str]]:
    rows: list[tuple[str, str, str, str]] = []
    for spec in STRUCTS[struct]:
        rows.extend(_field_rows(device_type, spec, prefix))
    return rows


def _field_rows(device_type: DeviceType, spec: FieldSpec, prefix: str) -> list[tuple[str, str, str, str]]:
    path = f"{prefix}{spec.name}"
    if spec.st_type is not None:
        default = _format_default(spec.st_type, spec.default)
        return [(path, spec.st_type.describe(), default, spec.description)]
    assert spec.struct is not None
    if spec.array is None:
        return _struct_rows(device_type, spec.struct, f"{path}.")
    low, high = spec.array
    rows: list[tuple[str, str, str, str]] = []
    for inner in STRUCTS[spec.struct]:
        assert inner.st_type is not None
        element = f"{path}[i].{inner.name}"
        if spec.element_defaults and inner.name in spec.element_defaults[0]:
            values = [str(defaults.get(inner.name, inner.default)) for defaults in spec.element_defaults]
            default = ", ".join(values)
        else:
            default = _format_default(inner.st_type, inner.default)
        description = f"{inner.description}; i = {low}…{high}"
        if spec.index_enum is not None:
            description += f" или имя {spec.index_enum.name}"
        rows.append((element, inner.st_type.describe(), default, description))
    return rows


def params_tables() -> str:
    parts: list[str] = []
    for spec in DEVICE_TYPES.values():
        parts.append(f"#### `{spec.device_type.value}` — `{LIBRARY_NAMESPACE}.{spec.cfg}`")
        parts.append("")
        parts.append("| Поле | Тип | По умолчанию | Описание | Как задаётся |")
        parts.append("|---|---|---|---|---|")
        for path, st_type, default, description in _struct_rows(spec.device_type, spec.cfg):
            if spec.device_type is DeviceType.MOTOR and path.startswith("stVfd."):
                continue
            source = _source_of(spec.device_type, path)
            parts.append(f"| `{path}` | {_cell(st_type)} | `{default}` | {_cell(description)} | {source} |")
        parts.append("")
    return "\n".join(parts).rstrip("\n")


def modbus_tables() -> str:
    lines = ["| Функция | Название | Пространство | Обмен | Значений за запрос |", "|---|---|---|---|---|"]
    for info in FUNCTIONS.values():
        access = "чтение" if info.access.value == "read" else "запись"
        count = "одно" if info.single else "одно или несколько"
        lines.append(f"| {info.code} | {info.name} | {info.space.prefix} {info.space.label} | {access} | {count} |")
    lines += ["", "| Тип данных | Регистров | Порядок слов `mb_order` | Где допустим |", "|---|---:|---|---|"]
    for data_type in ModbusType:
        if data_type is ModbusType.BOOL:
            lines.append("| `BOOL` | бит | — | катушки и дискретные входы; бит регистра (`mb_bit` 0…15) |")
            continue
        order = "HL или LH" if data_type.words > 1 else "—"
        lines.append(f"| `{data_type.value}` | {data_type.words} | {order} | регистры хранения и входные |")
    return "\n".join(lines)


def rules_table() -> str:
    lines = ["| Код | Уровень | Ослабить | Группа | Проверка |", "|---|---|---|---|---|"]
    for rule in RULES.values():
        adjustable = "да" if rule.adjustable else "нет"
        lines.append(f"| `{rule.code}` | {rule.severity.label} | {adjustable} | {rule.group} | {_cell(rule.title)} |")
    return "\n".join(lines)


def links_table() -> str:
    lines = ["| Колонка | У каких устройств | Ссылается на | Привязка |", "|---|---|---|---|"]
    for column, link in LINK_COLUMNS.items():
        owners = ", ".join(f"`{t.value}`" for t, spec in DEVICE_TYPES.items() if link in spec.links)
        lines.append(f"| `{column}` | {owners} | `{link.target.value}` | {_cell(link.title)} |")
    return "\n".join(lines)


SECTIONS: dict[str, tuple[str, Callable[[], str]]] = {
    "columns": ("Колонки перечня", columns_table),
    "device-types": ("Типы устройств", device_types_table),
    "roles": ("Роли сигналов", roles_table),
    "links": ("Ссылки на другие устройства", links_table),
    "alarms": ("Слоты тревог", alarm_slots_table),
    "params": ("Параметры Cfg (колонка params)", params_tables),
    "modbus": ("Modbus: функции и типы данных", modbus_tables),
    "rules": ("Правила проверки", rules_table),
}


def render_reference(sections: Sequence[str] | None = None) -> str:
    """Справочник схемы в Markdown (вывод ``iolistgen schema``)."""
    names = list(sections) if sections else list(SECTIONS)
    parts = [
        "# Схема перечня сигналов iolistgen",
        "",
        f"Библиотека устройств: plc-process-lib {LIBRARY_VERSION}, пространство имён `{LIBRARY_NAMESPACE}`. "
        "Подробное описание с примерами — `docs/schema.md`.",
        "",
    ]
    for name in names:
        title, render = SECTIONS[name]
        parts += [f"## {title}", "", render(), ""]
    return "\n".join(parts).rstrip("\n") + "\n"


def schema_json() -> dict[str, Any]:
    """Схема для программ: колонки, типы устройств и роли, поля Cfg, правила."""
    return {
        "library_namespace": LIBRARY_NAMESPACE,
        "alarm_slots": ALARM_SLOTS,
        "columns": [
            {
                "name": spec.name,
                "title": spec.title,
                "aliases": list(spec.aliases),
                "level": spec.level,
                "required": spec.required,
                "required_header": spec.name in REQUIRED_COLUMNS,
                "value": spec.value,
                "description": spec.description,
            }
            for spec in COLUMNS
        ],
        "device_types": [
            {
                "name": spec.device_type.value,
                "fb": spec.fb,
                "cmd": spec.cmd,
                "cfg": spec.cfg,
                "sts": spec.sts,
                "sts_registers": spec.sts_registers,
                "has_retain": spec.has_retain,
                "main_roles": [role.value for role in spec.main_roles],
                "has_io": spec.has_io,
                "delay_on": spec.delay_on,
                "delay_off": spec.delay_off,
                "links": [link.column for link in spec.links],
                "roles": [
                    {
                        "role": role.role.value,
                        "title": role.title,
                        "signal_types": sorted(t.value for t in role.signal_types),
                        "mb_types": sorted(t.value for t in role.mb_types),
                        "direction": role.direction.value,
                        "pin": role.pin,
                        "required": role.required,
                        "main": role.main,
                    }
                    for role in spec.roles
                ],
                "alarm_slots": [
                    {"index": slot.index, "member": slot.member, "suffix": slot.suffix, "title": slot.title}
                    for slot in spec.alarm_slots
                ],
                "cfg_fields": [
                    {"path": leaf.path, "type": leaf.st_type.name, "default": leaf.default}
                    for leaf in leaf_fields(spec.cfg)
                ],
            }
            for spec in DEVICE_TYPES.values()
        ],
        "modbus_functions": [
            {"code": info.code, "name": info.name, "space": info.space.value, "access": info.access.value}
            for info in FUNCTIONS.values()
        ],
        "modbus_types": [{"name": t.value, "words": t.words} for t in ModbusType],
        "aux_role": {
            "role": Role.AUX.value,
            "title": AUX_TITLE,
            "signal_types": sorted(t.value for t in AUX_SIGNAL_TYPES),
            "device_types": "любой; без устройства — простой сигнал",
        },
        "rules": [
            {
                "code": rule.code,
                "severity": rule.severity.value,
                "adjustable": rule.adjustable,
                "group": rule.group,
                "title": rule.title,
            }
            for rule in RULES.values()
        ],
        "rule_groups": GROUPS,
    }


_BLOCK_RE = re.compile(
    r"(<!-- BEGIN iolistgen:(?P<name>[a-z-]+) -->\n)(?P<body>.*?)(<!-- END iolistgen:(?P=name) -->)",
    re.DOTALL,
)


def update_document(text: str) -> str:
    """Заменить генерируемые блоки документа актуальными таблицами."""

    def replace(match: re.Match[str]) -> str:
        name = match.group("name")
        if name not in SECTIONS:
            raise KeyError(f"неизвестный раздел справочника: {name}")
        return f"{match.group(1)}{SECTIONS[name][1]()}\n{match.group(4)}"

    return _BLOCK_RE.sub(replace, text)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m iolistgen.schema_doc",
        description="Обновить генерируемые блоки справочника схемы в Markdown-документе.",
    )
    parser.add_argument("document", type=Path, help="документ с маркерами <!-- BEGIN iolistgen:<раздел> -->")
    parser.add_argument("--check", action="store_true", help="только проверить, что блоки актуальны")
    args = parser.parse_args(argv)
    path: Path = args.document
    text = path.read_text(encoding="utf-8")
    updated = update_document(text)
    if args.check:
        if updated != text:
            print(f"{path}: генерируемые блоки устарели — запустите python -m iolistgen.schema_doc {path}")
            return 1
        return 0
    if updated != text:
        path.write_bytes(updated.encode("utf-8"))
        print(f"{path}: обновлено")
    return 0


if __name__ == "__main__":
    sys.exit(main())
