"""Модель перечня: места в файле, инициализатор Cfg (правило «массив целиком»), выборки."""

from __future__ import annotations

from iolistgen.model import CfgValue, DeviceCfg, SourceRef, column_letter, default_cfg
from iolistgen.validate import check_file
from pytests.helpers import DATA


def test_column_letters() -> None:
    assert [column_letter(n) for n in (1, 26, 27, 52, 703)] == ["A", "Z", "AA", "AZ", "AAA"]


def test_source_ref_location() -> None:
    ref = SourceRef(file="kns.xlsx", sheet="Перечень", row=12, col=3, header="Тип сигнала")
    assert ref.location() == "лист «Перечень», строка 12, колонка C «Тип сигнала»"
    assert ref.short() == "kns.xlsx:12"
    assert SourceRef(file="a.csv").location() == "файл"
    assert ref.cell(4, None).column_letter == "D"


def with_values(struct: str, values: dict[str, object]) -> DeviceCfg:
    base = default_cfg(struct)
    changed = tuple(
        item.model_copy(update={"value": values[item.path], "origin": "params"}) if item.path in values else item
        for item in base.values
    )
    return DeviceCfg(type_name=struct, values=changed)


def test_default_cfg_has_empty_initializer() -> None:
    assert default_cfg("ST_MotorCfg").initializer() == ""
    assert default_cfg("ST_MotorCfg").changed() == ()


def test_scalar_and_nested_struct_initializer() -> None:
    cfg = with_values("ST_MotorCfg", {"tMinStop": 30_000, "stVfd.rSpeedMin_pct": 30.0, "wPermitMask": 1})
    assert cfg.initializer() == "(tMinStop := T#30S, wPermitMask := 16#0001, stVfd := (rSpeedMin_pct := 30.0))"


def test_alarm_array_is_written_completely() -> None:
    cfg = with_values("ST_AnalogInputCfg", {"astAlarm[4].tOnDelay": 5000})
    text = cfg.initializer()
    elements = text.removeprefix("(astAlarm := [").removesuffix("])").split("), (")
    assert len(elements) == 8
    # элемент 0: приоритет из DUT устройства (High) пишется явно, иначе он стал бы Medium типа ST_AlarmCfg
    assert elements[0].strip("(") == "ePriority := PL.E_AlarmPriority.High"
    # элемент 4: приоритет DUT (Medium) совпадает с умолчанием ST_AlarmCfg — достаточно изменённого поля
    assert elements[4] == "tOnDelay := T#5S"
    assert elements[7].rstrip(")") == "ePriority := PL.E_AlarmPriority.None"


def test_limit_array_lists_every_element() -> None:
    cfg = with_values("ST_AnalogInputCfg", {"astLimit[3].xEnable": True, "astLimit[3].rSetpoint_eu": 0.5})
    assert cfg.initializer() == (
        "(astLimit := [(xEnable := FALSE), (xEnable := FALSE), (xEnable := FALSE), "
        "(xEnable := TRUE, rSetpoint_eu := 0.5)])"
    )


def test_namespace_can_be_omitted() -> None:
    cfg = with_values("ST_ValveCfg", {"eType": "SolenoidEto"})
    assert cfg.initializer(namespace="") == "(eType := E_ValveType.SolenoidEto)"


def test_cfg_value_helpers() -> None:
    item = CfgValue(path="tMinStop", st_type="TIME", value=30_000, default=0, origin="params")
    assert item.changed
    assert item.literal() == "T#30S"
    cfg = default_cfg("ST_DigitalInputCfg")
    assert cfg.value("xAlarmOnTrue") is True
    assert cfg.get("astAlarm[1].ePriority").value == "Medium"


def test_iolist_helpers() -> None:
    result = check_file(DATA / "kns_mini.csv")
    model = result.model
    assert model is not None
    assert model.source.format == "csv" and len(model.source.sha256) == 64
    assert [d.dev_no for d in model.devices_by_dev_no()][:3] == [1, 2, 3]
    assert model.device("p101").ident == "P101"
    assert len(model.modbus_signals()) == 7
    assert {s.tag for s in model.signals_of_type(model.signals[0].signal_type)} >= {"LT101"}
    pump = model.device("P101")
    assert pump.main.tag == "P101_RUN"
    assert pump.description == "Насос Н1"
    assert pump.link_power == "PWR1"
    assert pump.modbus_slave == ("RS485-1", 1)
    assert pump.spec.fb == "FB_MotorVfd"
    assert pump.alarm_id_base == 110
    modbus = model.device("TT101").signals[0].modbus
    assert modbus is not None and modbus.word_order is not None
    assert [s.tag for s in model.signals][:3] == ["LT101", "LS101", "LS102"]
    assert "params" in model.columns
