"""Роль AUX: сигнал без входа и выхода ФБ — лампа, сирена, реле, регистр, который читает адаптер.

Такие сигналы — часть перечня: у них есть канал или адрес Modbus, их нужно видеть в ``GVL_IO``,
в карте обмена (пересечения адресов), в импорте SCADA и в документации. Экземпляра ФБ, Cmd,
Cfg и тревог у них нет; читает и пишет их код приложения.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from iolistgen.enums import Role
from iolistgen.generators.docs_table import DocsTableGenerator
from iolistgen.generators.modbus_map import ModbusMapGenerator
from iolistgen.generators.plc import build_plc
from iolistgen.generators.scada_csv import ScadaCsvGenerator
from iolistgen.generators.st_codesys import StCodesysGenerator
from iolistgen.model import IoList
from iolistgen.validate import CheckResult
from pytests.genhelp import lint_layout, run, texts
from pytests.helpers import ai, codes, motor_vfd, signal


def lamp(tag: str = "HL1", channel: int = 5, **extra: object) -> dict[str, object]:
    row: dict[str, object] = {
        "tag": tag,
        "description": f"Лампа «Авария» {tag}",
        "signal_type": "DO",
        "role": "AUX",
        "hmi_group": "Шкаф",
        "io_module": "Q1",
        "io_channel": channel,
    }
    row.update(extra)
    return row


def fault_code(device: str = "P101", reg: int = 103, **extra: object) -> dict[str, object]:
    row = signal(
        device,
        "FCODE",
        "AUX",
        "MB",
        description=f"Насос {device}: код аварии ПЧ",
        mb_link="RS485-1",
        mb_slave=1,
        mb_func=3,
        mb_reg=reg,
        mb_type="UINT",
    )
    row.update(extra)
    return row


def aux_list() -> list[dict[str, object]]:
    return [*motor_vfd(), fault_code(), ai(), lamp(), lamp("HA1", 6, description="Сирена")]


def checked(check_rows: Callable[..., CheckResult], rows: list[dict[str, object]]) -> IoList:
    result = check_rows(rows)
    assert result.ok, [item.render() for item in result.diagnostics]
    assert result.diagnostics == [], [item.render() for item in result.diagnostics]
    assert result.model is not None
    return result.model


def test_standalone_and_attached_aux_validate(check_rows: Callable[..., CheckResult]) -> None:
    result = check_rows(aux_list())
    model = checked(check_rows, aux_list())
    lamp_signal = next(s for s in model.signals if s.tag == "HL1")
    assert lamp_signal.device is None and lamp_signal.role is Role.AUX and not lamp_signal.is_main
    pump = model.device("P101")
    assert [s.tag for s in pump.signals if s.role is Role.AUX] == ["P101_FCODE"]
    assert next(s for s in model.signals if s.tag == "P101_FCODE").device == "P101"
    # сигнал без ФБ — не устройство
    assert [d.ident for d in model.devices] == ["P101", "LT101"]
    assert result.stats.devices == 2 and result.stats.signals == 10
    assert [s.tag for s in model.plain_signals()] == ["HL1", "HA1"]


def test_aux_register_takes_part_in_overlap_check(check_rows: Callable[..., CheckResult]) -> None:
    rows = [*motor_vfd(), fault_code(reg=3)]  # регистр слова состояния
    assert "IOL412" in codes(check_rows(rows))


def test_aux_channel_takes_part_in_channel_check(check_rows: Callable[..., CheckResult]) -> None:
    rows = [lamp(), lamp("HA1", 5)]
    assert "IOL601" in codes(check_rows(rows))


def test_several_aux_rows_in_one_device(check_rows: Callable[..., CheckResult]) -> None:
    rows = [*motor_vfd(), fault_code(), fault_code(reg=104, tag="P101_FPWR", description="Мощность ПЧ")]
    model = checked(check_rows, rows)
    assert len([s for s in model.device("P101").signals if s.role is Role.AUX]) == 2


def test_device_columns_on_standalone_aux_warn(check_rows: Callable[..., CheckResult]) -> None:
    result = check_rows([lamp(dev_no=7, alarm_priority="High", params="tMinStop=T#1S")])
    found = [item for item in result.diagnostics if item.code == "IOL317"]
    assert {item.source.header for item in found if item.source is not None} == {
        "dev_no",
        "alarm_priority",
        "params",
    }
    assert result.ok  # предупреждения: генерация возможна


def test_group_of_aux_rows_needs_device_type(check_rows: Callable[..., CheckResult]) -> None:
    rows = [lamp(device="PANEL1"), lamp("HA1", 6, device="PANEL1")]
    result = check_rows(rows)
    found = [item for item in result.errors if item.code == "IOL302"]
    assert found and "AUX" in found[0].hint


def test_aux_without_role_is_not_guessed(check_rows: Callable[..., CheckResult]) -> None:
    result = check_rows([lamp(role="")])
    assert "IOL302" in codes(result)


def test_plc_names_and_bindings(check_rows: Callable[..., CheckResult]) -> None:
    model = checked(check_rows, aux_list())
    plc = build_plc(model)
    names = {var.name: var for var in plc.io_vars}
    assert names["xHL1"].section == "hw_out" and names["xHL1"].st_type == "BOOL"
    assert names["uiP101_FCODE"].section == "mb_in"
    assert "без ФБ" in names["xHL1"].comment
    pump = plc.binding(model.device("P101"))
    assert all("FCODE" not in pin.expr for pin in pump.inputs)
    assert any("GVL_IO.uiP101_FCODE" in note for note in pump.notes)


def test_st_codesys_with_aux(tmp_path: Path, check_rows: Callable[..., CheckResult]) -> None:
    model = checked(check_rows, aux_list())
    run(StCodesysGenerator(), model, tmp_path, {"persist_check": False})
    files = texts(tmp_path)
    gvl_io = files["src/GVLs/Generated/GVL_IO.gvl.st"]
    assert "    xHL1 : BOOL;" in gvl_io and "    uiP101_FCODE : UINT;" in gvl_io
    impl = files["src/POUs/Generated/PRG_Devices/PRG_Devices.impl.st"]
    assert "GVL_IO.uiP101_FCODE" in impl  # в комментарии блока P101
    assert "fbHL1" not in files["src/GVLs/Generated/GVL_Devices.gvl.st"]
    findings, _ = lint_layout(tmp_path)
    assert findings == []


def test_modbus_map_scada_and_docs_with_aux(tmp_path: Path, check_rows: Callable[..., CheckResult]) -> None:
    model = checked(check_rows, aux_list())
    run(ModbusMapGenerator(), model, tmp_path)
    run(ScadaCsvGenerator(), model, tmp_path)
    run(DocsTableGenerator(), model, tmp_path)
    files = texts(tmp_path)
    master = [line for line in files["docs/modbus_master_map.csv"].splitlines() if "P101_FCODE" in line]
    assert len(master) == 1 and ";AUX;" in master[0] and ";P101;" in master[0]
    tags = files["scada/scada_tags.csv"].splitlines()
    lamp_tag = next(line for line in tags if line.startswith("HL1;"))
    assert "Application.GVL_IO.xHL1" in lamp_tag and ";R;" in lamp_tag
    assert any(line.startswith("P101.FCODE;") or line.startswith("P101_FCODE;") for line in tags)
    signal_list = files["docs/signal_list.md"]
    assert "## Сигналы без ФБ" in signal_list
    assert "`HL1`" in signal_list and "`GVL_IO.xHL1`" in signal_list


def test_plain_signal_is_not_subject_to_device_name_rules(check_rows: Callable[..., CheckResult]) -> None:
    """Простой сигнал — не устройство: правило длины имени устройства (IOL107) к нему не относится."""
    result = check_rows([lamp("HL9999_VERY_LONG_LAMP_NAME_X")], config={"naming": {"max_device_length": 8}})
    assert result.diagnostics == [], [item.render() for item in result.diagnostics]
