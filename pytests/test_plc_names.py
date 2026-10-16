"""Модель имён ПЛК: переменные GVL_IO, параметры вызовов, порядок вызовов, конфликты имён."""

from __future__ import annotations

from collections.abc import Callable

import pytest

from iolistgen.generators import GenerationError
from iolistgen.generators.plc import (
    RESERVED_WORDS,
    DeviceBinding,
    PlcModel,
    build_plc,
    channel_place,
    modbus_place,
    scale_text,
)
from iolistgen.model import IoList
from iolistgen.validate import CheckResult, check_file
from pytests.helpers import DATA, ai, di, motor_vfd, signal, valve

Check = Callable[..., CheckResult]


@pytest.fixture(scope="module")
def kns() -> IoList:
    result = check_file(DATA / "kns_mini.csv")
    assert result.model is not None
    return result.model


@pytest.fixture(scope="module")
def fixture_model() -> IoList:
    result = check_file(DATA / "gen_fixture.csv")
    assert result.model is not None, [item.render() for item in result.diagnostics]
    return result.model


def model_of(check_rows: Check, rows: list[dict[str, object]]) -> IoList:
    result = check_rows(rows)
    assert result.model is not None, [item.render() for item in result.errors]
    return result.model


def pins(binding: DeviceBinding) -> dict[str, str]:
    return {pin.pin: pin.expr for pin in binding.inputs}


def binding_of(plc: PlcModel, ident: str) -> DeviceBinding:
    return next(item for item in plc.devices if item.device.ident == ident)


def test_signal_variable_names(kns: IoList) -> None:
    plc = build_plc(kns)
    names = {var.signal.tag: (var.name, var.st_type) for var in plc.io_vars if var.signal is not None}
    assert names["LT101"] == ("rLT101_mA", "REAL")  # AI 4–20 мА
    assert names["LS101"] == ("xLS101", "BOOL")
    assert names["P101_RUN"] == ("xP101_RUN", "BOOL")
    assert names["P101_STW"] == ("wP101_STW", "WORD")
    assert names["P101_ACT"] == ("iP101_ACT", "INT")
    assert names["TT101"] == ("rTT101", "REAL")  # Modbus REAL без суффикса тока
    assert names["FCV101_OUT"] == ("rFCV101_OUT_mA", "REAL")  # AO позиционера — ток


def test_analog_without_current_has_no_ma_suffix(fixture_model: IoList) -> None:
    plc = build_plc(fixture_model)
    names = {var.signal.tag: var.name for var in plc.io_vars if var.signal is not None}
    assert names["TE201"] == "rTE201"  # eInput = Norm01
    assert names["P202_REF"] == "rP202_REF"  # AO задания ПЧ — через адаптер
    assert names["P202_ACT"] == "rP202_ACT"
    assert names["PT201"] == "iPT201"
    assert names["ES201"] == "xES201"


def test_sections_and_order(kns: IoList) -> None:
    plc = build_plc(kns)
    sections = [var.section for var in plc.io_vars]
    assert sections == sorted(
        sections, key=["hw_in", "hw_out", "mb_in", "mb_out", "mb_status", "vfd_in", "vfd_out"].index
    )
    hw_in = [var.name for var in plc.section("hw_in")]
    assert hw_in[:4] == ["rLT101_mA", "rPT101_mA", "rFT101_mA", "rZT101_mA"]  # модуль A1 каналы 1–4
    assert [var.name for var in plc.section("mb_status")] == [
        "xMbOk_RS485_1_S1",
        "xMbOk_RS485_1_S2",
        "xMbOk_RS485_2_S10",
    ]


def test_channel_order_is_natural(check_rows: Check) -> None:
    rows = [
        di("LS110", 1, io_module="D10", io_channel=1),
        di("LS102", 2, io_module="D2", io_channel=10),
        di("LS101", 3, io_module="D2", io_channel=2),
        di("LS120", 4),
    ]
    plc = build_plc(model_of(check_rows, rows))
    assert [var.name for var in plc.section("hw_in")] == ["xLS101", "xLS102", "xLS110", "xLS120"]


def test_device_names(kns: IoList) -> None:
    plc = build_plc(kns)
    p101 = binding_of(plc, "P101")
    assert (p101.instance, p101.cmd, p101.cfg, p101.retain) == ("fbP101", "stP101Cmd", "stP101Cfg", "stP101Retain")
    assert p101.fb_type == "PL.FB_MotorVfd" and p101.cmd_type == "PL.ST_MotorCmd"
    assert binding_of(plc, "LT101").retain is None
    assert p101.index_constant == "P101"


def test_namespace_option(kns: IoList) -> None:
    plc = build_plc(kns, namespace="")
    assert binding_of(plc, "LT101").fb_type == "FB_AnalogInput"


def test_call_order_puts_link_targets_first(kns: IoList) -> None:
    order = [binding.device.ident for binding in build_plc(kns).devices]
    assert order[:2] == ["PWR1", "ZT101"]
    rest = order[2:]
    numbers = {d.ident: d.dev_no for d in kns.devices}
    assert [numbers[name] for name in rest] == sorted(numbers[name] for name in rest)


def test_analog_pins(kns: IoList, fixture_model: IoList) -> None:
    plc = build_plc(kns)
    assert pins(binding_of(plc, "LT101")) == {
        "rIn": "GVL_IO.rLT101_mA",
        "xChannelFault": "FALSE",
        "stCmd": "GVL_Hmi.stLT101Cmd",
        "stCfg": "GVL_Persist.stLT101Cfg",
    }
    assert pins(binding_of(plc, "TT101"))["xChannelFault"] == "NOT GVL_IO.xMbOk_RS485_2_S10"
    fixture = build_plc(fixture_model)
    assert pins(binding_of(fixture, "LT201"))["xChannelFault"] == "GVL_IO.xLT201_CHF"
    assert pins(binding_of(fixture, "PT201"))["rIn"] == "INT_TO_REAL(GVL_IO.iPT201)"
    assert pins(binding_of(fixture, "ES201"))["xChannelFault"] == "NOT GVL_IO.xMbOk_RS485_1_S7"


def test_motor_pins_and_outputs(fixture_model: IoList) -> None:
    plc = build_plc(fixture_model)
    m201 = binding_of(plc, "M201")
    assert list(pins(m201)) == ["xFbRun", "xExtFault", "xLocal", "xPowerOk", "stCmd", "stCfg", "stRetain"]
    assert pins(m201)["xPowerOk"] == "GVL_Devices.fbPWR2.xValue"
    assert [(out.target, out.pin) for out in m201.outputs] == [
        ("GVL_IO.xM201_RUN", "xQRun"),
        ("GVL_IO.xM201_RST", "xQReset"),
    ]


def test_vfd_adapter_bindings(fixture_model: IoList) -> None:
    plc = build_plc(fixture_model)
    p201 = binding_of(plc, "P201")  # пуск по Modbus: главная строка VFD_CTW
    assert pins(p201)["xCommOk"] == "GVL_IO.xP201_CommOk"
    assert pins(p201)["xVfdRunning"] == "GVL_IO.xP201_VfdRun"
    assert pins(p201)["rSpeedAct_pct"] == "GVL_IO.rP201_SpeedAct_pct"
    assert [(out.target, out.pin) for out in p201.outputs] == [
        ("GVL_IO.xP201_VfdQRun", "xQRun"),
        ("GVL_IO.xP201_VfdQReset", "xQReset"),
        ("GVL_IO.rP201_SpeedRef_pct", "rSpeedRef_pct"),
    ]
    p202 = binding_of(plc, "P202")  # пуск проводом: CMD_RUN
    assert ("GVL_IO.xP202_RUN", "xQRun") in [(out.target, out.pin) for out in p202.outputs]
    assert "xP202_VfdQRun" not in [var.name for var in plc.io_vars]
    assert p201.notes and "адаптер" in p201.notes[0]


def test_valve_and_control_valve_pins(fixture_model: IoList) -> None:
    plc = build_plc(fixture_model)
    fv = pins(binding_of(plc, "FV201"))
    assert list(fv)[:6] == ["xZso", "xZsc", "xTorqueOpen", "xTorqueClose", "xExtFault", "xLocal"]
    xv = binding_of(plc, "XV201")
    assert [(out.target, out.pin) for out in xv.outputs] == [("GVL_IO.xXV201", "xQCoil")]
    cv = binding_of(plc, "FCV201")
    assert pins(cv)["rPosFb_pct"] == "GVL_Devices.fbZT201.rValue_pct"
    assert pins(cv)["xPosFbValid"] == "GVL_Devices.fbZT201.xValid"
    assert pins(cv)["xPositionerFault"] == "GVL_IO.xFCV201_POSF"
    assert [(out.target, out.pin) for out in cv.outputs] == [("GVL_IO.rFCV201_OUT_mA", "rOut_mA")]


def test_time_source_pin(kns: IoList) -> None:
    plc = build_plc(kns, time_source="GVL_Station.itfClock")
    for binding in plc.devices:
        names = [pin.pin for pin in binding.inputs]
        assert names[names.index("stCmd") - 1] == "itfTime"
        assert pins(binding)["itfTime"] == "GVL_Station.itfClock"


def test_case_insensitive_collision_is_reported(check_rows: Check) -> None:
    rows = [*motor_vfd("P101", 11), di("P101_COMMOK", 2, description="тег, совпадающий с переменной адаптера")]
    model = model_of(check_rows, rows)
    with pytest.raises(GenerationError, match="без учёта регистра"):
        build_plc(model)


def test_reserved_device_name(check_rows: Check) -> None:
    config = {"naming": {"tag_regex": "^[A-Z]+[0-9]*$", "device_regex": "^[A-Z]+[0-9]*$"}}
    result = check_rows([ai("LT", 1)], config=config)
    assert result.model is not None, [item.render() for item in result.errors]
    assert "LT" in RESERVED_WORDS
    with pytest.raises(GenerationError, match="ключевым словом"):
        build_plc(result.model)


def test_non_ascii_link_gets_short_name(check_rows: Check) -> None:
    rows = [
        ai(
            "TT301",
            1,
            signal_type="MB",
            mb_link="Линия 1",
            mb_slave=3,
            mb_func=4,
            mb_reg=0,
            mb_type="REAL",
            mb_order="HL",
        ),
        ai(
            "TT302",
            2,
            signal_type="MB",
            mb_link="RS485-2",
            mb_slave=3,
            mb_func=4,
            mb_reg=0,
            mb_type="REAL",
            mb_order="HL",
        ),
    ]
    plc = build_plc(model_of(check_rows, rows))
    names = [var.name for var in plc.section("mb_status")]
    assert names == ["xMbOk_RS485_2_S3", "xMbOk_L2_S3"] or sorted(names) == ["xMbOk_L2_S3", "xMbOk_RS485_2_S3"]
    status = next(var for var in plc.section("mb_status") if "L2" in var.name)
    assert "Линия 1" in status.comment


def test_signal_var_lookup_and_helpers(kns: IoList) -> None:
    plc = build_plc(kns)
    by_tag = {s.tag: s for s in kns.signals}
    assert plc.signal_var(by_tag["LS102"]).path == "GVL_IO.xLS102"
    assert scale_text(by_tag["LT101"]) == "0…5 м"
    assert channel_place(by_tag["LT101"]) == "A1.1"
    assert modbus_place(by_tag["TT101"]) == "RS485-2 · слейв 10 · FC4 3x 0 REAL LH"
    with pytest.raises(KeyError):
        plc.binding(kns.devices[0].model_copy(update={"ident": "NOPE"}))


def test_valve_helper_rows(check_rows: Check) -> None:
    rows = [*valve("FV301", 5), signal("FV301", "FLT", "FAULT", "DI")]
    plc = build_plc(model_of(check_rows, rows))
    assert pins(binding_of(plc, "FV301"))["xExtFault"] == "GVL_IO.xFV301_FLT"


def test_modbus_pv_with_chf_row_still_watches_comm(check_rows: Check) -> None:
    """PV по Modbus и бит отказа канала: при потере связи бит CHF замирает, поэтому OR NOT xMbOk.

    Без этого ФБ считал бы замёрзшее значение достоверным, пока нет связи со слейвом.
    """
    pv = {
        **ai("PT301", 5),
        "signal_type": "MB",
        "mb_link": "TCP-1",
        "mb_slave": 1,
        "mb_func": 4,
        "mb_reg": 0,
        "mb_type": "REAL",
        "mb_order": "HL",
    }
    chf = signal(
        "PT301", "CHF", "CHF", "MB", mb_link="TCP-1", mb_slave=1, mb_func=3, mb_reg=1000, mb_type="BOOL", mb_bit=0
    )
    hardwired = signal("PT302", "CHF", "CHF", "DI")
    pv2 = {**pv, "tag": "PT302", "dev_no": 6, "mb_reg": 2}
    plc = build_plc(model_of(check_rows, [pv, chf, pv2, hardwired]))
    assert pins(binding_of(plc, "PT301"))["xChannelFault"] == "GVL_IO.xPT301_CHF OR NOT GVL_IO.xMbOk_TCP_1_S1"
    assert pins(binding_of(plc, "PT302"))["xChannelFault"] == "GVL_IO.xPT302_CHF OR NOT GVL_IO.xMbOk_TCP_1_S1"
