"""Помощники тестов iolistgen: перечни из словарей строк, типовые устройства, коды сообщений."""

from __future__ import annotations

import csv
from collections.abc import Mapping, Sequence
from pathlib import Path

from iolistgen.config import Config, parse_config
from iolistgen.diagnostics import Diagnostic
from iolistgen.validate import CheckResult

DATA = Path(__file__).parent / "data"

COLUMNS: tuple[str, ...] = (
    "tag",
    "description",
    "signal_type",
    "device",
    "device_type",
    "dev_no",
    "role",
    "dev_desc",
    "range_min",
    "range_max",
    "units",
    "sp_hh",
    "sp_h",
    "sp_l",
    "sp_ll",
    "delay_on_s",
    "delay_off_s",
    "alarm_priority",
    "hmi_group",
    "io_module",
    "io_channel",
    "mb_link",
    "mb_slave",
    "mb_func",
    "mb_reg",
    "mb_type",
    "mb_bit",
    "mb_order",
    "link_power",
    "link_fb",
    "params",
)

Row = Mapping[str, object]


def write_csv(path: Path, rows: Sequence[Row], columns: Sequence[str] = COLUMNS, delimiter: str = ";") -> Path:
    """CSV в UTF-8 с заголовком ``columns`` (кавычки — где нужно, как у Excel)."""
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream, delimiter=delimiter, lineterminator="\n")
        writer.writerow(columns)
        for row in rows:
            unknown = set(row) - set(columns)
            assert not unknown, f"колонок нет в заголовке: {unknown}"
            writer.writerow(["" if row.get(name) is None else str(row.get(name)) for name in columns])
    return path


def ai(tag: str = "LT101", dev_no: int | str = 1, **extra: object) -> dict[str, object]:
    """Аналоговый вход 4–20 мА с диапазоном и единицами — корректная строка."""
    row: dict[str, object] = {
        "tag": tag,
        "description": f"Измерение {tag}",
        "signal_type": "AI",
        "device_type": "AnalogInput",
        "dev_no": dev_no,
        "role": "PV",
        "range_min": 0,
        "range_max": 5,
        "units": "м",
    }
    row.update(extra)
    return row


def di(tag: str = "LS101", dev_no: int | str = 2, **extra: object) -> dict[str, object]:
    """Дискретный вход — корректная строка."""
    row: dict[str, object] = {
        "tag": tag,
        "description": f"Сигнал {tag}",
        "signal_type": "DI",
        "device_type": "DigitalInput",
        "dev_no": dev_no,
        "role": "IN",
    }
    row.update(extra)
    return row


def pid(tag: str = "LIC101", dev_no: int | str = 41, **extra: object) -> dict[str, object]:
    """ПИД-регулятор: строка устройства без типа сигнала и роли, с диапазоном PV — корректная строка."""
    row: dict[str, object] = {
        "tag": tag,
        "description": f"Регулятор {tag}",
        "device_type": "Pid",
        "dev_no": dev_no,
        "range_min": 0,
        "range_max": 5,
        "units": "м",
    }
    row.update(extra)
    return row


def signal(device: str, suffix: str, role: str, signal_type: str, **extra: object) -> dict[str, object]:
    """Неглавная строка устройства."""
    row: dict[str, object] = {
        "tag": f"{device}_{suffix}",
        "description": f"{device}: {role}",
        "signal_type": signal_type,
        "device": device,
        "role": role,
    }
    row.update(extra)
    return row


def motor_vfd(device: str = "P101", dev_no: int = 11, slave: int = 1, base: int = 0) -> list[dict[str, object]]:
    """Насос с ПЧ: команда DO, авария и местное DI, слово состояния, задание и факт по Modbus."""
    main: dict[str, object] = {
        "tag": f"{device}_RUN",
        "description": f"Насос {device}: работа",
        "signal_type": "DO",
        "device": device,
        "device_type": "MotorVfd",
        "dev_no": dev_no,
        "role": "CMD_RUN",
    }
    mb = {"mb_link": "RS485-1", "mb_slave": slave}
    return [
        main,
        signal(device, "FLT", "FAULT", "DI"),
        signal(device, "LOC", "LOCAL", "DI"),
        signal(device, "STW", "VFD_STW", "MB", mb_func=3, mb_reg=base + 3, mb_type="WORD", **mb),
        signal(
            device,
            "ACT",
            "SPEED_ACT",
            "MB",
            mb_func=3,
            mb_reg=base + 4,
            mb_type="INT",
            units="Гц",
            range_min=0,
            range_max=50,
            **mb,
        ),
        signal(
            device,
            "REF",
            "SPEED_REF",
            "MB",
            mb_func=6,
            mb_reg=base + 1,
            mb_type="INT",
            units="Гц",
            range_min=0,
            range_max=50,
            **mb,
        ),
    ]


def valve(device: str = "FV101", dev_no: int = 21) -> list[dict[str, object]]:
    """Задвижка с электроприводом и концевиками."""
    return [
        {
            "tag": f"{device}_OPN",
            "description": f"Задвижка {device}: открыть",
            "signal_type": "DO",
            "device": device,
            "device_type": "Valve",
            "dev_no": dev_no,
            "role": "CMD_OPEN",
        },
        signal(device, "CLS", "CMD_CLOSE", "DO"),
        signal(device, "ZSO", "ZSO", "DI"),
        signal(device, "ZSC", "ZSC", "DI"),
    ]


def config_from(data: Mapping[str, object] | None = None) -> Config:
    return parse_config(dict(data or {}))


def codes(items: Sequence[Diagnostic] | CheckResult) -> list[str]:
    diagnostics = items.diagnostics if isinstance(items, CheckResult) else items
    return [item.code for item in diagnostics]
