"""Генераторы ``scada-csv`` и ``alarm-list``: теги SCADA, узлы OPC UA, тревоги, шаблоны текстов."""

from __future__ import annotations

import csv
import io
from pathlib import Path

import pytest

from iolistgen.catalog import DEVICE_TYPES
from iolistgen.enums import DeviceType
from iolistgen.generators import GenerationError
from iolistgen.generators.alarms import (
    ALARM_COLUMNS,
    AlarmListGenerator,
    alarm_rows,
    bundled_templates,
    load_templates,
    sentence_part,
    slot_possible,
)
from iolistgen.generators.scada_csv import POINTS, TAG_COLUMNS, ScadaCsvGenerator
from iolistgen.model import IoList
from pytests.genhelp import FIXTURE, KNS, load, run


@pytest.fixture(scope="module")
def kns() -> IoList:
    return load(KNS)


@pytest.fixture(scope="module")
def fixture_model() -> IoList:
    return load(FIXTURE)


def read_csv(path: Path, delimiter: str = ";") -> list[dict[str, str]]:
    lines = [line for line in path.read_text(encoding="utf-8").splitlines() if not line.startswith("#")]
    return list(csv.DictReader(io.StringIO("\n".join(lines)), delimiter=delimiter))


def test_scada_tags(tmp_path: Path, fixture_model: IoList) -> None:
    run(ScadaCsvGenerator(), fixture_model, tmp_path)
    rows = read_csv(tmp_path / "scada/scada_tags.csv")
    assert list(rows[0]) == list(TAG_COLUMNS)
    tags = [row["tag"] for row in rows]
    assert len(tags) == len(set(tags))
    by_tag = {row["tag"]: row for row in rows}
    value = by_tag["LT201.Value"]
    assert (value["data_type"], value["access"], value["units"], value["eng_min"], value["eng_max"]) == (
        "REAL",
        "R",
        "м",
        "0",
        "4",
    )
    assert (value["alarm_hh"], value["alarm_h"], value["alarm_l"], value["alarm_ll"]) == ("3.6", "3.2", "0.8", "0.4")
    assert value["plc_path"] == "Application.GVL_Devices.fbLT201.stSts.rValue_eu"
    assert value["opcua_node_id"] == (
        "ns=4;s=|var|CODESYS Control Win V3.Application.GVL_Devices.fbLT201.stSts.rValue_eu"
    )
    start = by_tag["M201.Cmd.Start"]
    assert (start["access"], start["data_type"], start["plc_path"]) == (
        "RW",
        "BOOL",
        "Application.GVL_Hmi.stM201Cmd.xStart",
    )
    assert by_tag["LS201.Value"]["plc_path"] == "Application.GVL_Devices.fbLS201.xValue"
    assert by_tag["P201.SpeedRef"]["units"] == "%"
    assert by_tag["P201.Mode"]["data_type"] == "INT"  # перечисление — INT
    assert "FV201.Cmd.Stop" in by_tag  # задвижка с приводом — стоп есть
    assert "XV201.Cmd.Stop" not in by_tag  # у соленоида стопа нет
    assert "M201.SpeedRef" not in by_tag  # у двигателя без ПЧ задания скорости нет


def test_scada_options(tmp_path: Path, kns: IoList) -> None:
    options = {
        "separator": "_",
        "commands": False,
        "diagnostics": False,
        "opcua_device": "",
        "application": "",
        "alarms_csv": "",
        "comment_header": False,
        "delimiter": "tab",
    }
    ctx = run(ScadaCsvGenerator(), kns, tmp_path, options)
    assert len(ctx.outputs) == 1
    text = (tmp_path / "scada/scada_tags.csv").read_text(encoding="utf-8")
    assert text.startswith("tag\tdescription\t")
    rows = read_csv(tmp_path / "scada/scada_tags.csv", "\t")
    assert all(row["access"] == "R" for row in rows)
    assert all(not row["opcua_node_id"] for row in rows)
    assert {row["tag"] for row in rows} >= {"LT101_Value", "P101_State"}
    assert not any(row["tag"].endswith("_Mode") for row in rows)
    lt = next(row for row in rows if row["tag"] == "LT101_Value")
    assert lt["plc_path"] == "GVL_Devices.fbLT101.stSts.rValue_eu"


@pytest.mark.parametrize("device_type", list(DeviceType))
def test_scada_points_resolve(device_type: DeviceType) -> None:
    """Каждый тег SCADA ссылается на настоящее поле Sts, выход ФБ или поле Cmd."""
    from iolistgen.generators.scada_csv import _output_field, _struct_field

    spec = DEVICE_TYPES[device_type]
    for point in POINTS[device_type]:
        if point.source == "sts":
            _struct_field(spec.sts, point.path)
        elif point.source == "cmd":
            _struct_field(spec.cmd, point.path)
        else:
            _output_field(device_type, point.path)


def test_scada_alarms(tmp_path: Path, kns: IoList) -> None:
    run(ScadaCsvGenerator(), kns, tmp_path)
    rows = read_csv(tmp_path / "scada/scada_alarms.csv")
    hh = next(row for row in rows if row["code"] == "LT101.HH")
    assert (hh["id"], hh["bit"], hh["active_tag"], hh["unack_tag"], hh["ack_tag"]) == (
        "10",
        "0",
        "LT101.AlmActive",
        "LT101.AlmUnack",
        "LT101.Cmd.AckReq",
    )
    assert hh["priority"] == "High" and hh["setpoint"] == "4.5" and hh["delay_s"] == "2"


def test_alarm_list(tmp_path: Path, kns: IoList) -> None:
    run(AlarmListGenerator(), kns, tmp_path)
    rows = read_csv(tmp_path / "docs/alarms.csv")
    assert list(rows[0]) == list(ALARM_COLUMNS)
    codes = [row["code"] for row in rows]
    ids = [int(row["id"]) for row in rows]
    assert ids == sorted(ids) and len(set(ids)) == len(ids)
    assert "LT101.HH" in codes and "P101.COM" in codes
    assert "P101.ILK" not in codes  # InterlockTrip по умолчанию выключен (None)
    assert not any(code.startswith("XV101.") for code in codes)  # соленоид без концевиков и аварии
    assert "TT101.OOR" not in codes  # Modbus REAL (Eng) — без NE 43
    assert "PWR1.FAIL" not in codes  # нет строки CHF — отказа канала не бывает
    lt_h = next(row for row in rows if row["code"] == "LT101.H")
    assert lt_h["priority"] == "Medium"  # колонка High, H — на ступень ниже
    assert lt_h["text_ru"] == "Уровень в приёмном резервуаре: высокое значение"  # шаблон библиотеки
    assert lt_h["operator_action"] == "Проверить процесс и режим работы оборудования"


def test_alarm_options(tmp_path: Path, kns: IoList) -> None:
    run(AlarmListGenerator(), kns, tmp_path, {"include_disabled": True, "only_possible": False})
    codes = [row["code"] for row in read_csv(tmp_path / "docs/alarms.csv")]
    assert "P101.ILK" in codes and "XV101.FTO" in codes


def test_slot_possible_rules(fixture_model: IoList) -> None:
    devices = {device.ident: device for device in fixture_model.devices}

    def possible(ident: str, suffix: str) -> bool:
        device = devices[ident]
        slot = next(item for item in device.spec.alarm_slots if item.suffix == suffix)
        return slot_possible(device, slot)

    assert possible("M201", "FTS") and possible("M201", "EXT")
    assert possible("P202", "FTS")  # ОС проводом (xFbFromComm = FALSE, есть RUN_FB)
    assert possible("FV201", "TRQ") and possible("FV201", "FTC") and possible("FV201", "BLS")
    assert possible("XV201", "FTC") and not possible("XV201", "FTO") and not possible("XV201", "BLS")
    assert possible("XV201", "PLS")
    assert possible("FCV201", "POS") and possible("FCV201", "DEV")
    assert possible("LS201", "FAIL") and possible("ES201", "FAIL")  # строка CHF и Modbus
    assert not possible("TE201", "OOR")  # Norm01


def test_alarm_templates(tmp_path: Path, kns: IoList) -> None:
    path = tmp_path / "alarm_templates.csv"
    path.write_text(
        "type;slot;suffix;text_ru;operator_action;cause\n"
        "AnalogInput;0;HH;уровень выше аварийного;Проверить насосы;приток больше откачки\n"
        "Motor;6;COM;нет связи с ПЧ;Проверить линию RS-485;\n",
        encoding="utf-8",
    )
    templates = load_templates(path)
    rows = {row.code: row for row in alarm_rows(kns, templates)}
    assert rows["LT101.HH"].text == "Уровень в приёмном резервуаре: уровень выше аварийного"
    assert rows["LT101.HH"].operator_action == "Проверить насосы"
    assert rows["LT101.HH"].cause == "приток больше откачки"
    assert rows["P101.COM"].text == "Насос Н1: нет связи с ПЧ"  # MotorVfd берёт шаблоны Motor
    assert rows["LT101.H"].operator_action == ""  # шаблона нет — встроенный текст
    run(AlarmListGenerator(), kns, tmp_path / "out", {"templates": str(path)})
    assert "Проверить насосы" in (tmp_path / "out/docs/alarms.csv").read_text(encoding="utf-8")


@pytest.mark.parametrize(
    ("content", "fragment"),
    [
        ("", "пуст"),
        ("type;suffix\nMotor;FTS\n", "нет колонок"),
        ("type;slot;text_ru\nMotor;x;текст\n", "slot — не число"),
    ],
)
def test_alarm_template_errors(tmp_path: Path, content: str, fragment: str) -> None:
    path = tmp_path / "t.csv"
    path.write_text(content, encoding="utf-8")
    with pytest.raises(GenerationError, match=fragment):
        load_templates(path)
    with pytest.raises(GenerationError, match="не удалось прочитать"):
        load_templates(tmp_path / "missing.csv")


def test_bundled_templates_cover_every_slot() -> None:
    """Шаблоны библиотеки в пакете (CONSUMERS G5): текст и действие оператора у каждого слота каждого типа."""
    templates = bundled_templates()
    for spec in DEVICE_TYPES.values():
        keys = (
            ("motorvfd", "motor") if spec.device_type is DeviceType.MOTOR_VFD else (spec.device_type.value.casefold(),)
        )
        for slot in spec.alarm_slots:
            template = next((templates[(key, slot.index)] for key in keys if (key, slot.index) in templates), None)
            assert template is not None, f"{spec.device_type.value} {slot.index}"
            assert template.text and template.operator_action, f"{spec.device_type.value} {slot.index}"
            assert template.cause and template.consequence, f"{spec.device_type.value} {slot.index}"
    assert ("motor", 6) not in templates and ("motorvfd", 6) in templates  # слоты ПЧ — свои строки MotorVfd
    assert ("pid", 0) in templates


def test_default_texts_come_from_library_templates(kns: IoList, tmp_path: Path) -> None:
    rows = {row.code: row for row in alarm_rows(kns, bundled_templates())}
    assert rows["LT101.HH"].text == "Уровень в приёмном резервуаре: аварийно высокое значение"
    assert rows["LT101.HH"].operator_action.startswith("Проверить процесс по месту")
    run(AlarmListGenerator(), kns, tmp_path / "default")
    text = (tmp_path / "default/docs/alarms.csv").read_text(encoding="utf-8")
    assert "аварийно высокое значение" in text and "Проверить процесс по месту" in text
    run(AlarmListGenerator(), kns, tmp_path / "none", {"templates": "none"})
    plain = (tmp_path / "none/docs/alarms.csv").read_text(encoding="utf-8")
    assert "верхний аварийный предел" in plain and "Проверить процесс" not in plain


def test_vfd_comm_loss_template_is_split_into_columns() -> None:
    """Строка COM файла библиотеки 1.0.0 со сдвигом колонок исправлена в копии пакета (TEMPLATE_FIXES)."""
    template = bundled_templates()[("motorvfd", 6)]
    assert template.operator_action == "Проверить линию связи, питание и сетевые настройки ПЧ"
    assert template.cause == "Нет обмена с ПЧ дольше tCommLoss при поданном питании"
    assert template.consequence.startswith("Поведение ПЧ задаёт его сторожевой таймер связи")


def test_sentence_part_keeps_abbreviations() -> None:
    assert sentence_part("Аварийно высокое значение") == "аварийно высокое значение"
    assert sentence_part("NE 43: отказ") == "NE 43: отказ"
    assert sentence_part("ПЧ не готов") == "ПЧ не готов"
