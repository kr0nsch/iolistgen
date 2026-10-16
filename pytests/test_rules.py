"""Каждое правило проверки — срабатывание на неверном перечне и тишина на исправленном.

Таблица ``CASES`` покрывает все коды из ``RULES``: тест ``test_every_rule_has_case`` не даст
добавить правило без проверки.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path

import pytest

from iolistgen.diagnostics import RULES, Severity
from iolistgen.validate import CheckResult, check_file
from pytests.helpers import COLUMNS, Row, ai, config_from, di, motor_vfd, signal, valve, write_csv


@dataclass(frozen=True)
class Scenario:
    """Перечень для одного прогона: строки или «сырое» содержимое файла."""

    rows: Sequence[Row] = ()
    columns: Sequence[str] = COLUMNS
    config: dict[str, object] = field(default_factory=dict)
    raw: bytes | None = None


@dataclass(frozen=True)
class Case:
    bad: Scenario
    good: Scenario


def motor(device: str = "M201", dev_no: int = 31, **main: object) -> list[dict[str, object]]:
    """Двигатель прямого пуска: команда и ОС."""
    first: dict[str, object] = {
        "tag": f"{device}_RUN",
        "description": f"Двигатель {device}: работа",
        "signal_type": "DO",
        "device": device,
        "device_type": "Motor",
        "dev_no": dev_no,
        "role": "CMD_RUN",
    }
    first.update(main)
    return [first, signal(device, "FB", "RUN_FB", "DI")]


def vfd_with(index: int, **changes: object) -> list[dict[str, object]]:
    rows = motor_vfd()
    rows[index] = {**rows[index], **changes}
    return rows


def vfd_main(**changes: object) -> list[dict[str, object]]:
    return vfd_with(0, **changes)


def mb_ai(**changes: object) -> list[dict[str, object]]:
    row: dict[str, object] = {
        "tag": "TT101",
        "description": "Температура",
        "signal_type": "MB",
        "device_type": "AnalogInput",
        "dev_no": 7,
        "role": "PV",
        "range_min": -40,
        "range_max": 60,
        "units": "°C",
        "mb_link": "RS485-2",
        "mb_slave": 10,
        "mb_func": 4,
        "mb_reg": 0,
        "mb_type": "REAL",
        "mb_order": "HL",
    }
    row.update(changes)
    return [row]


def mb_di(**changes: object) -> list[dict[str, object]]:
    row: dict[str, object] = {
        "tag": "XS101",
        "description": "Состояние по Modbus",
        "signal_type": "MB",
        "device_type": "DigitalInput",
        "dev_no": 8,
        "role": "IN",
        "mb_slave": 5,
        "mb_func": 2,
        "mb_reg": 10,
        "mb_type": "BOOL",
    }
    row.update(changes)
    return [row]


def coil_valve(params: str = "eType=SolenoidEto") -> list[dict[str, object]]:
    return [
        {
            "tag": "XV101",
            "description": "Клапан промывки",
            "signal_type": "DO",
            "device_type": "Valve",
            "dev_no": 22,
            "role": "CMD_COIL",
            "params": params,
        }
    ]


def control_valve(link: str = "ZT101") -> list[dict[str, object]]:
    return [
        {
            "tag": "FCV101",
            "description": "Регулирующий клапан",
            "signal_type": "AO",
            "device_type": "ControlValve",
            "dev_no": 41,
            "role": "POS_OUT",
            "units": "%",
            "link_fb": link,
        },
        ai("ZT101", 42, units="%", range_max=100),
    ]


CSV_HEADER = ";".join(COLUMNS)
GOOD_LINE = "LT101;Уровень;AI;;AnalogInput;1;PV;;0;5;м" + ";" * (len(COLUMNS) - 11)

CASES: dict[str, Case] = {
    "IOL001": Case(
        Scenario(raw=f"{CSV_HEADER}\n{GOOD_LINE}\n".encode("cp1251")),
        Scenario(raw=f"{CSV_HEADER}\n{GOOD_LINE}\n".encode()),
    ),
    "IOL002": Case(
        Scenario(rows=[{"x": "LT101", "y": "Уровень"}], columns=("x", "y")),
        Scenario(rows=[ai()]),
    ),
    "IOL003": Case(
        Scenario(
            rows=[{k: v for k, v in ai().items() if k != "dev_no"}], columns=[c for c in COLUMNS if c != "dev_no"]
        ),
        Scenario(rows=[ai()]),
    ),
    "IOL004": Case(
        Scenario(rows=[ai()], columns=[*COLUMNS, "Тег"]),
        Scenario(rows=[ai()]),
    ),
    "IOL005": Case(
        Scenario(rows=[ai()], columns=[*COLUMNS, "Примечание"]),
        Scenario(rows=[ai()], columns=[*COLUMNS, "Примечание"], config={"input": {"ignore_columns": ["примечание"]}}),
    ),
    "IOL006": Case(
        Scenario(
            raw="tag;description;signal_type;device_type;dev_no;role\nLT101;Уровень;AI;AnalogInput;1;PV;лишнее\n".encode()
        ),
        Scenario(raw=b"tag;description;signal_type;device_type;dev_no;role\nLS101;Signal;DI;DigitalInput;1;IN\n"),
    ),
    "IOL007": Case(Scenario(rows=[ai(range_min="ноль")]), Scenario(rows=[ai(range_min="0,5")])),
    "IOL101": Case(Scenario(rows=[ai(), ai(tag="", dev_no=2)]), Scenario(rows=[ai(), ai("LT102", 2)])),
    "IOL102": Case(Scenario(rows=[ai("LТ101")]), Scenario(rows=[ai("LT101")])),
    "IOL103": Case(Scenario(rows=[ai(), ai("lt101", 2)]), Scenario(rows=[ai(), ai("LT102", 2)])),
    "IOL104": Case(
        Scenario(rows=[ai("Lt101")]),
        Scenario(rows=[ai("Lt101")], config={"naming": {"tag_regex": "^[A-Za-z]+[0-9]+$"}}),
    ),
    "IOL105": Case(
        Scenario(rows=[{**row, "device": "Р101"} for row in motor_vfd()]),
        Scenario(rows=motor_vfd()),
    ),
    "IOL106": Case(
        Scenario(rows=[{**row, "device": "PUMP_1"} for row in motor_vfd()]),
        Scenario(
            rows=[{**row, "device": "PUMP_1"} for row in motor_vfd()],
            config={"naming": {"device_regex": "^[A-Z0-9_]+$"}},
        ),
    ),
    "IOL107": Case(
        Scenario(rows=motor_vfd(), config={"naming": {"max_device_length": 3}}),
        Scenario(rows=motor_vfd(), config={"naming": {"max_device_length": 4}}),
    ),
    "IOL108": Case(Scenario(rows=vfd_with(2, device="p101")), Scenario(rows=motor_vfd())),
    "IOL201": Case(Scenario(rows=[ai(description="")]), Scenario(rows=[ai()])),
    "IOL202": Case(Scenario(rows=[ai(signal_type="AX")]), Scenario(rows=[ai()])),
    "IOL203": Case(Scenario(rows=[ai(range_min="", range_max="")]), Scenario(rows=[ai()])),
    "IOL204": Case(Scenario(rows=[ai(range_min=5, range_max=0)]), Scenario(rows=[ai()])),
    "IOL205": Case(Scenario(rows=[ai(range_max="")]), Scenario(rows=[ai()])),
    "IOL206": Case(Scenario(rows=[ai(units="")]), Scenario(rows=[ai()])),
    "IOL207": Case(Scenario(rows=vfd_with(4, units="")), Scenario(rows=motor_vfd())),
    "IOL208": Case(Scenario(rows=[ai(sp_h=2, sp_l=3)]), Scenario(rows=[ai(sp_h=4, sp_l=1)])),
    "IOL209": Case(Scenario(rows=[ai(sp_hh=6)]), Scenario(rows=[ai(sp_hh=4.5)])),
    "IOL210": Case(Scenario(rows=[di(sp_hh=1)]), Scenario(rows=[di()])),
    "IOL211": Case(Scenario(rows=[ai(delay_on_s=2)]), Scenario(rows=[ai(delay_on_s=2, sp_hh=4.5)])),
    "IOL212": Case(Scenario(rows=vfd_with(1, alarm_priority="High")), Scenario(rows=vfd_main(alarm_priority="High"))),
    "IOL301": Case(Scenario(rows=motor(device_type="Pump")), Scenario(rows=motor())),
    "IOL302": Case(Scenario(rows=[ai(device_type="")]), Scenario(rows=[ai()])),
    "IOL303": Case(Scenario(rows=vfd_with(1, device_type="Motor")), Scenario(rows=vfd_with(1, device_type="MotorVfd"))),
    "IOL304": Case(Scenario(rows=vfd_with(1, role="")), Scenario(rows=motor_vfd())),
    "IOL305": Case(Scenario(rows=vfd_with(1, role="PV")), Scenario(rows=motor_vfd())),
    "IOL306": Case(Scenario(rows=vfd_with(1, signal_type="AI")), Scenario(rows=motor_vfd())),
    "IOL307": Case(Scenario(rows=vfd_with(2, role="FAULT")), Scenario(rows=motor_vfd())),
    "IOL308": Case(Scenario(rows=motor_vfd()[:5]), Scenario(rows=motor_vfd())),
    "IOL309": Case(Scenario(rows=[ai(dev_no="")]), Scenario(rows=[ai()])),
    "IOL310": Case(Scenario(rows=[ai(dev_no=10000)]), Scenario(rows=[ai(dev_no=9999)])),
    "IOL311": Case(Scenario(rows=[ai(), ai("LT102", 1)]), Scenario(rows=[ai(), ai("LT102", 2)])),
    "IOL312": Case(Scenario(rows=[row for row in valve() if row["role"] != "CMD_CLOSE"]), Scenario(rows=valve())),
    "IOL313": Case(
        Scenario(rows=[*vfd_main(link_power="PWR9"), di("PWR1", 5)]),
        Scenario(rows=[*vfd_main(link_power="PWR1"), di("PWR1", 5)]),
    ),
    "IOL314": Case(
        Scenario(rows=[*vfd_main(link_power="LT101"), ai()]),
        Scenario(rows=[*vfd_main(link_power="PWR1"), di("PWR1", 5)]),
    ),
    "IOL315": Case(
        Scenario(rows=[*motor_vfd(), signal("P101", "FB", "RUN_FB", "DI")]),
        Scenario(rows=[*vfd_main(params="stVfd.xFbFromComm=FALSE"), signal("P101", "FB", "RUN_FB", "DI")]),
    ),
    "IOL316": Case(
        Scenario(rows=[*valve(), signal("FV101", "TQO", "TQO", "DI")]),
        Scenario(rows=[*valve(), signal("FV101", "TQO", "TQO", "DI"), signal("FV101", "TQC", "TQC", "DI")]),
    ),
    "IOL317": Case(
        Scenario(rows=[{"tag": "HL1", "description": "Лампа", "signal_type": "DO", "role": "AUX", "dev_no": 9}]),
        Scenario(rows=[{"tag": "HL1", "description": "Лампа", "signal_type": "DO", "role": "AUX"}]),
    ),
    "IOL401": Case(Scenario(rows=vfd_with(3, mb_reg="")), Scenario(rows=motor_vfd())),
    "IOL402": Case(Scenario(rows=[di(mb_slave=1)]), Scenario(rows=[di()])),
    "IOL403": Case(Scenario(rows=vfd_with(3, mb_func=7)), Scenario(rows=motor_vfd())),
    "IOL404": Case(Scenario(rows=mb_ai(mb_type="FLOAT")), Scenario(rows=mb_ai())),
    "IOL405": Case(Scenario(rows=vfd_with(3, mb_func=1)), Scenario(rows=motor_vfd())),
    "IOL406": Case(Scenario(rows=mb_ai(mb_reg=65535)), Scenario(rows=mb_ai(mb_reg=65534))),
    "IOL407": Case(Scenario(rows=mb_di(mb_func=3, mb_reg=7)), Scenario(rows=mb_di(mb_func=3, mb_reg=7, mb_bit=3))),
    "IOL408": Case(
        Scenario(rows=mb_ai(mb_order="")),
        Scenario(rows=mb_ai(mb_order=""), config={"modbus": {"default_word_order": "LH"}}),
    ),
    "IOL409": Case(Scenario(rows=vfd_with(4, mb_order="LH")), Scenario(rows=motor_vfd())),
    "IOL410": Case(Scenario(rows=vfd_with(5, mb_func=3)), Scenario(rows=motor_vfd())),
    "IOL411": Case(
        Scenario(rows=vfd_with(3, mb_type="REAL", mb_func=3, mb_order="HL", mb_reg=10)),
        Scenario(rows=motor_vfd()),
    ),
    "IOL412": Case(Scenario(rows=vfd_with(5, mb_reg=3, mb_func=6)), Scenario(rows=motor_vfd())),
    "IOL413": Case(Scenario(rows=mb_di(mb_slave=256)), Scenario(rows=mb_di(mb_slave=255))),
    "IOL414": Case(Scenario(rows=mb_di(mb_slave=250)), Scenario(rows=mb_di(mb_slave=247))),
    "IOL415": Case(Scenario(rows=vfd_with(4, mb_slave=2)), Scenario(rows=motor_vfd())),
    "IOL416": Case(
        Scenario(rows=mb_di(mb_slave=0)),
        Scenario(rows=mb_di(mb_slave=0), config={"severity": {"IOL416": "off"}}),
    ),
    "IOL417": Case(Scenario(rows=mb_ai(mb_link="Линия 2")), Scenario(rows=mb_ai(mb_link="RS485-2"))),
    "IOL501": Case(Scenario(rows=vfd_main(params="tMinStop")), Scenario(rows=vfd_main(params="tMinStop=T#30S"))),
    "IOL502": Case(Scenario(rows=vfd_main(params="tMinStopp=T#30S")), Scenario(rows=vfd_main(params="tMinStop=T#30S"))),
    "IOL503": Case(Scenario(rows=vfd_main(params="tMinStop=30")), Scenario(rows=vfd_main(params="tMinStop=T#30S"))),
    "IOL504": Case(Scenario(rows=vfd_main(params="udiAlarmIdBase=5")), Scenario(rows=motor_vfd())),
    "IOL505": Case(
        Scenario(rows=vfd_main(delay_on_s=7, params="tFbStart=T#5S")),
        Scenario(rows=vfd_main(delay_on_s=7)),
    ),
    "IOL506": Case(
        Scenario(rows=vfd_main(params="tMinStop=T#1S; TMINSTOP=T#2S")),
        Scenario(rows=vfd_main(params="tMinStop=T#1S")),
    ),
    "IOL507": Case(
        Scenario(rows=vfd_main(params="uiMaxStartsPerHour=31")),
        Scenario(rows=vfd_main(params="uiMaxStartsPerHour=6")),
    ),
    "IOL508": Case(
        Scenario(rows=motor(params="stVfd.rSpeedMin_pct=30.0")),
        Scenario(rows=vfd_main(params="stVfd.rSpeedMin_pct=30.0")),
    ),
    "IOL509": Case(Scenario(rows=coil_valve(params="")), Scenario(rows=coil_valve())),
    "IOL601": Case(
        Scenario(rows=[di(io_module="D1", io_channel=1), di("LS102", 3, io_module="d1", io_channel=1)]),
        Scenario(rows=[di(io_module="D1", io_channel=1), di("LS102", 3, io_module="D1", io_channel=2)]),
    ),
    "IOL602": Case(Scenario(rows=[di(io_module="D1")]), Scenario(rows=[di(io_module="D1", io_channel=1)])),
    "IOL603": Case(Scenario(rows=mb_di(io_module="D1", io_channel=1)), Scenario(rows=mb_di())),
}


@pytest.fixture
def run(tmp_path: Path) -> Callable[[Scenario], CheckResult]:
    counter = iter(range(1000))

    def execute(scenario: Scenario) -> CheckResult:
        path = tmp_path / f"case{next(counter)}.csv"
        if scenario.raw is not None:
            path.write_bytes(scenario.raw)
        else:
            write_csv(path, scenario.rows, scenario.columns)
        return check_file(path, config_from(scenario.config))

    return execute


def test_every_rule_has_case() -> None:
    assert set(CASES) == set(RULES)


@pytest.mark.parametrize("code", sorted(CASES))
def test_rule_fires_on_bad_list(code: str, run: Callable[[Scenario], CheckResult]) -> None:
    result = run(CASES[code].bad)
    found = [item for item in result.diagnostics if item.code == code]
    assert found, f"{code} не сработало; сообщения: {[d.render() for d in result.diagnostics]}"
    for item in found:
        assert item.severity is RULES[code].severity
        assert item.message
        assert item.source is not None
        if code not in ("IOL001", "IOL002"):
            assert item.source.row is not None, item.render()
        if RULES[code].severity is Severity.ERROR:
            assert not result.ok and result.model is None


@pytest.mark.parametrize("code", sorted(CASES))
def test_rule_silent_on_fixed_list(code: str, run: Callable[[Scenario], CheckResult]) -> None:
    result = run(CASES[code].good)
    assert code not in [item.code for item in result.diagnostics], [d.render() for d in result.diagnostics]


@pytest.mark.parametrize("code", sorted(CASES))
def test_hints_explain_the_fix(code: str, run: Callable[[Scenario], CheckResult]) -> None:
    result = run(CASES[code].bad)
    for item in result.diagnostics:
        if item.code == code:
            assert item.hint, f"{code}: нет подсказки «как исправить»: {item.message}"


def test_row_without_device_gets_device_hint(run: Callable[[Scenario], CheckResult]) -> None:
    """Забытый device у строки насоса: сообщение — про device, а не «не задан тип устройства»."""
    rows = motor()
    rows[1] = {**rows[1], "device": ""}  # M201_FB без device
    result = run(Scenario(rows=rows))
    found = [item for item in result.errors if item.code == "IOL302"]
    assert len(found) == 1
    assert "не указано устройство" in found[0].message
    assert "RUN_FB" in found[0].message
    assert "M201" in found[0].hint
    assert found[0].source is not None and found[0].source.header == "device"


def test_section_caption_row_hint(run: Callable[[Scenario], CheckResult]) -> None:
    result = run(Scenario(rows=[{"tag": "Насосная станция"}, ai()]))
    found = [item for item in result.errors if item.code == "IOL102"]
    assert len(found) == 1
    assert "#" in found[0].hint and "заголовок раздела" in found[0].hint
