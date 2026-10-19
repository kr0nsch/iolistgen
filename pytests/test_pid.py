"""Тип устройства Pid: ПИД-регулятор без сигналов ввода-вывода (plc-process-lib 1.0.0, CONSUMERS G3).

В перечне — строка устройства без ``signal_type`` и ``role``: ``device_type = Pid``, ``dev_no``,
диапазон PV и ``params``; в составе устройства допустимы только сигналы AUX. Генераторы дают
экземпляр ``PL.FB_PID``, Cmd в ``GVL_Hmi``, Cfg и Retain в ``GVL_Persist`` по ``dev_no``, блок Sts в
карте slave, теги SCADA и тревогу слота 0 ``PVF``. Вызова в ``PRG_Devices`` нет: привязки ФБ пишет
логика станции (контракт 17.3), генератор оставляет образец вызова в комментарии.
"""

from __future__ import annotations

import csv
from collections.abc import Callable
from pathlib import Path

import pytest

from iolistgen.enums import DeviceType
from iolistgen.generators.alarms import AlarmListGenerator
from iolistgen.generators.docs_table import DocsTableGenerator
from iolistgen.generators.modbus_map import ModbusMapGenerator
from iolistgen.generators.plc import build_plc
from iolistgen.generators.scada_csv import ScadaCsvGenerator
from iolistgen.generators.st_codesys import StCodesysGenerator, check_persist
from iolistgen.model import IoList
from iolistgen.validate import CheckResult
from pytests.genhelp import lint_layout, run, texts
from pytests.helpers import ai, codes, pid, signal

Check = Callable[..., CheckResult]


def model_of(check_rows: Check, rows: list[dict[str, object]]) -> IoList:
    result = check_rows(rows)
    assert result.diagnostics == [], [item.render() for item in result.diagnostics]
    assert result.model is not None
    return result.model


def loop() -> list[dict[str, object]]:
    """Уровнемер и регулятор уровня с сигналом AUX (индикатор задания на щите)."""
    return [
        ai(),
        pid(params="eAction=Direct; xUseOutAct=TRUE; rSpMax_eu=3.5"),
        signal(
            "LIC101", "SPI", "AUX", "AO", description="Задание на индикатор щита", units="м", range_min=0, range_max=5
        ),
    ]


# --- перечень ------------------------------------------------------------------------------------


def test_pid_row_is_device_without_signal(check_rows: Check) -> None:
    model = model_of(check_rows, loop())
    device = model.device("LIC101")
    assert device.device_type is DeviceType.PID and device.dev_no == 41
    assert device.main_role is None
    assert [s.tag for s in device.signals] == ["LIC101_SPI"]  # строка устройства — не сигнал
    assert [s.tag for s in model.signals] == ["LT101", "LIC101_SPI"]
    assert (device.units, device.range_min, device.range_max) == ("м", 0.0, 5.0)
    cfg = device.cfg
    assert cfg.value("rPvMin_eu") == 0.0 and cfg.value("rPvMax_eu") == 5.0
    assert cfg.get("rPvMax_eu").origin == "column"
    assert cfg.value("rSpMin_eu") == 0.0 and cfg.get("rSpMin_eu").origin == "inferred"
    assert cfg.value("rSpMax_eu") == 3.5 and cfg.get("rSpMax_eu").origin == "params"
    assert cfg.value("eAction") == "Direct" and cfg.value("udiAlarmIdBase") == 410


def test_stats_count_signals_without_device_rows(check_rows: Check) -> None:
    result = check_rows(loop())
    assert result.stats.signals == 2 and result.stats.devices == 2


@pytest.mark.parametrize(
    ("changes", "code"),
    [
        ({"signal_type": "AI"}, "IOL304"),  # тип сигнала у строки регулятора
        ({"role": "PV"}, "IOL305"),  # роль ввода-вывода у Pid
        ({"delay_on_s": 5}, "IOL211"),
        ({"delay_off_s": 5}, "IOL211"),
        ({"sp_hh": 4}, "IOL210"),
        ({"link_power": "LT101"}, "IOL314"),
        ({"range_min": 5, "range_max": 0}, "IOL204"),
        ({"mb_slave": 1}, "IOL402"),
        ({"io_module": "A1", "io_channel": 1}, "IOL603"),
        ({"params": "rPvMin_eu=1.0"}, "IOL505"),  # диапазон PV уже задан колонкой range_min
        ({"params": "rKp=0.0"}, "IOL507"),
    ],
)
def test_pid_row_errors(check_rows: Check, changes: dict[str, object], code: str) -> None:
    result = check_rows([ai(), {**pid(), **changes}])
    assert code in codes(result), [item.render() for item in result.diagnostics]


def test_second_device_row_and_missing_device_row(check_rows: Check) -> None:
    twice = check_rows([pid(), pid("LIC101_B", device="LIC101", dev_no="")])
    assert "IOL307" in codes(twice)
    only_aux = check_rows([signal("LIC101", "SPI", "AUX", "AO", device_type="Pid", dev_no=41, units="м")])
    assert "IOL308" in codes(only_aux)


def test_missing_signal_type_is_error_except_device_row(check_rows: Check) -> None:
    result = check_rows([ai(signal_type="")])
    assert codes(result) == ["IOL202"]
    assert result.model is None
    assert codes(check_rows([pid()])) == []


def test_without_pv_range_warns(check_rows: Check) -> None:
    result = check_rows([pid(range_min="", range_max="", units="")])
    assert codes(result) == ["IOL213"]
    assert result.model is not None
    assert result.model.device("LIC101").cfg.value("rPvMax_eu") == 100.0


@pytest.mark.parametrize(
    ("params", "bit"),
    [
        ("rKp=-1.0", "PID_CFG_KP"),
        ("rTi_s=-1.0", "PID_CFG_TI_TD"),
        ("rTd_s=5.0; rDFilterN=1.0", "PID_CFG_DFILTER"),
        ("rTt_s=-0.5", "PID_CFG_TT"),
        ("rSpMin_eu=4.0; rSpMax_eu=3.0", "PID_CFG_SP_RANGE"),
        ("rOutMin_pct=50.0; rOutMax_pct=40.0", "PID_CFG_OUT_RANGE"),
        ("rOutMax_pct=120.0", "PID_CFG_OUT_RANGE"),
        ("rDeadband_pct=11.0", "PID_CFG_DEADBAND"),
        ("rOutRate_pctps=-2.0", "PID_CFG_RATES"),
        ("tSample=T#2S", "PID_CFG_SAMPLE"),
        ("tDtMax=T#0S", "PID_CFG_SAMPLE"),
        ("rOutMin_pct=20.0; rSafeOut_pct=10.0", "PID_CFG_PV_FAIL"),
    ],
)
def test_check_config_mirror(check_rows: Check, params: str, bit: str) -> None:
    result = check_rows([pid(params=params)])
    messages = [item.message for item in result.diagnostics if item.code == "IOL507"]
    assert any(message.startswith(bit) for message in messages), [item.render() for item in result.diagnostics]


def test_check_config_accepts_typical_loop(check_rows: Check) -> None:
    params = "eAction=Direct; rKp=2.0; rTi_s=120.0; rTd_s=10.0; rDFilterN=8.0; tSample=T#100MS; rDeadband_pct=1.0"
    assert codes(check_rows([pid(params=params)])) == []


def test_pid_range_from_params_without_columns(check_rows: Check) -> None:
    model = model_of(check_rows, [pid(range_min="", range_max="", params="rPvMin_eu=-1.0; rPvMax_eu=1.0")])
    cfg = model.device("LIC101").cfg
    assert (cfg.value("rPvMin_eu"), cfg.value("rPvMax_eu")) == (-1.0, 1.0)
    assert (cfg.value("rSpMin_eu"), cfg.value("rSpMax_eu")) == (0.0, 100.0)  # не выводятся из params


# --- генераторы ----------------------------------------------------------------------------------


def test_st_codesys_declares_pid_without_call(check_rows: Check, tmp_path: Path) -> None:
    model = model_of(check_rows, loop())
    run(StCodesysGenerator(), model, tmp_path)
    files = texts(tmp_path)
    gvl = "src/GVLs/Generated/"
    assert "fbLIC101 : PL.FB_PID;" in files[gvl + "GVL_Devices.gvl.st"]
    assert "stLIC101Cmd : PL.ST_PidCmd;" in files[gvl + "GVL_Hmi.gvl.st"]
    assert "LIC101 : UINT := 41;" in files[gvl + "GVL_DevIdx.gvl.st"]
    persist = files[gvl + "GVL_Persist.pvl.st"]
    assert (
        persist.index("stLT101Cfg")
        < persist.index("stLIC101Cfg : PL.ST_PidCfg")
        < persist.index("stLIC101Retain : PL.ST_DeviceRetain")
    )
    assert "eAction := PL.E_PidAction.Direct" in persist and "rPvMax_eu := 5.0" in persist
    assert "stLIC101Cfg : PL.ST_PidCfg" in files[gvl + "GVL_CfgProject.gvl.st"]
    apply = files["src/POUs/Generated/PRG_ApplyProjectCfg/PRG_ApplyProjectCfg.impl.st"]
    assert "GVL_Persist.stLIC101Cfg := GVL_CfgProject.stLIC101Cfg;" in apply
    body = files["src/POUs/Generated/PRG_Devices/PRG_Devices.impl.st"]
    code = [line for line in body.splitlines() if not line.lstrip().startswith("//")]
    assert not any("fbLIC101" in line for line in code)  # вызова нет
    assert "// GVL_Devices.fbLIC101(" in body and "//     stRetain := GVL_Persist.stLIC101Retain);" in body
    assert "GVL_IO.rLIC101_SPI" in body  # сигнал AUX упомянут комментарием
    assert "rLIC101_SPI : REAL;" in files[gvl + "GVL_IO.gvl.st"]
    findings, _ = lint_layout(tmp_path)
    assert findings == []


def test_time_source_goes_to_sample_call(check_rows: Check, tmp_path: Path) -> None:
    model = model_of(check_rows, loop())
    run(StCodesysGenerator(), model, tmp_path, {"time_source": "GVL_App.itfClock"})
    body = texts(tmp_path)["src/POUs/Generated/PRG_Devices/PRG_Devices.impl.st"]
    assert "//     itfTime  := GVL_App.itfClock);" in body


def test_binding_is_not_called(check_rows: Check) -> None:
    plc = build_plc(model_of(check_rows, loop()))
    binding = next(b for b in plc.devices if b.device.ident == "LIC101")
    assert not binding.called and binding.outputs == ()
    assert binding.retain == "stLIC101Retain" and binding.fb_type == "PL.FB_PID"


def test_persist_check_covers_pid(check_rows: Check, tmp_path: Path) -> None:
    model = model_of(check_rows, loop())
    run(StCodesysGenerator(), model, tmp_path)
    previous = texts(tmp_path)["src/GVLs/Generated/GVL_Persist.pvl.st"]
    renamed = model_of(check_rows, [ai(), pid("LIC102")])
    messages = check_persist(previous, build_plc(renamed))
    assert any("dev_no 41 был у LIC101, теперь у LIC102" in message for message in messages)
    assert any("GVL_Persist.stLIC101Retain удалена" in message for message in messages)


def test_modbus_slave_block_of_pid(check_rows: Check, tmp_path: Path) -> None:
    run(ModbusMapGenerator(), model_of(check_rows, loop()), tmp_path)
    with (tmp_path / "docs" / "modbus_slave_map.csv").open(encoding="utf-8") as stream:
        rows = list(csv.DictReader((line for line in stream if not line.startswith("#")), delimiter=";"))
    block = [row for row in rows if row["device"] == "LIC101"]
    assert len(block) == 14 + 9  # stCommon и девять REAL
    registers = {row["field"]: (int(row["offset"]), row["units"]) for row in block}
    assert registers["stSts.stCommon.wAlmSuppressed"] == (13, "")
    assert registers["stSts.rPv_eu"] == (18, "м")
    assert registers["stSts.rDt_ms"] == (30, "мс")


def test_scada_tags_of_pid(check_rows: Check, tmp_path: Path) -> None:
    run(ScadaCsvGenerator(), model_of(check_rows, loop()), tmp_path)
    with (tmp_path / "scada" / "scada_tags.csv").open(encoding="utf-8") as stream:
        rows = {
            row["tag"]: row
            for row in csv.DictReader((line for line in stream if not line.startswith("#")), delimiter=";")
        }
    assert rows["LIC101.Pv"]["plc_path"] == "Application.GVL_Devices.fbLIC101.stSts.rPv_eu"
    assert (rows["LIC101.Sp"]["units"], rows["LIC101.Sp"]["eng_min"], rows["LIC101.Sp"]["eng_max"]) == ("м", "0", "5")
    assert rows["LIC101.Cmd.Sp"]["access"] == "RW"
    assert rows["LIC101.Cmd.ManualOut"]["plc_path"] == "Application.GVL_Hmi.stLIC101Cmd.rManualOut_pct"
    assert rows["LIC101.SatHigh"]["data_type"] == "BOOL"
    assert rows["LIC101.AlmSuppressed"]["plc_path"].endswith("stSts.stCommon.wAlmSuppressed")
    assert rows["LIC101_SPI"]["plc_path"] == "Application.GVL_IO.rLIC101_SPI"


def test_alarm_slot_pvf(check_rows: Check, tmp_path: Path) -> None:
    run(AlarmListGenerator(), model_of(check_rows, loop()), tmp_path)
    text = (tmp_path / "docs" / "alarms.csv").read_text(encoding="utf-8")
    line = next(line for line in text.splitlines() if "LIC101.PVF" in line)
    assert line.startswith("410;LIC101.PVF;LIC101;0;Medium;")


def test_alarm_priority_column_and_none(check_rows: Check, tmp_path: Path) -> None:
    model = model_of(check_rows, [ai(), pid(alarm_priority="None")])
    assert model.device("LIC101").cfg.value("astAlarm[0].ePriority") == "None"
    run(AlarmListGenerator(), model, tmp_path)
    assert "LIC101.PVF" not in (tmp_path / "docs" / "alarms.csv").read_text(encoding="utf-8")


def test_docs_table_device_without_signals(check_rows: Check, tmp_path: Path) -> None:
    run(DocsTableGenerator(), model_of(check_rows, [ai(), pid()]), tmp_path)
    text = (tmp_path / "docs" / "signal_list.md").read_text(encoding="utf-8")
    assert "| 41 | `LIC101` | Pid | `PL.FB_PID` | Регулятор LIC101 | 0 |" in text
    assert "сигналов ввода-вывода нет: вызов ФБ — в логике станции; диапазон PV 0…5 м" in text
