"""Уровни правил в iolistgen.toml: структурные правила не ослабляются, остальные — без падений.

Структурное правило отбрасывает данные, без которых не строится модель (нет тега, роли, типа
устройства, адреса Modbus). Если бы его можно было отключить, перечень «без ошибок» дошёл бы до
модели с дырами: ``AssertionError`` вместо сообщения или код ПЛК без привязки.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest

from iolistgen.config import ConfigError, parse_config
from iolistgen.diagnostics import RULES, DiagnosticBag, Severity
from iolistgen.generators.plc import build_plc
from iolistgen.validate import CheckResult
from pytests.helpers import ai, di, motor_vfd

ADJUSTABLE_ERRORS = sorted(code for code, rule in RULES.items() if rule.severity is Severity.ERROR and rule.adjustable)
FIXED = sorted(code for code, rule in RULES.items() if not rule.adjustable)


def test_structural_rules_are_marked() -> None:
    # правила, без которых модель не строится или строится с дырами
    for code in ("IOL101", "IOL201", "IOL202", "IOL302", "IOL304", "IOL309", "IOL401", "IOL413"):
        assert not RULES[code].adjustable, code
    # проектные правила и проверки CheckConfig ослабить можно
    for code in ("IOL104", "IOL106", "IOL107", "IOL208", "IOL412", "IOL416", "IOL507", "IOL601"):
        assert RULES[code].adjustable, code
    # предупреждения всегда настраиваются
    assert all(rule.adjustable for rule in RULES.values() if rule.severity is Severity.WARNING)


@pytest.mark.parametrize("code", FIXED)
@pytest.mark.parametrize("level", ["warning", "off"])
def test_fixed_rule_cannot_be_lowered(code: str, level: str) -> None:
    with pytest.raises(ConfigError, match=f"{code}.*нельзя ослабить"):
        parse_config({"severity": {code: level}}, source="iolistgen.toml")


@pytest.mark.parametrize("code", FIXED)
def test_fixed_rule_may_be_restated_as_error(code: str) -> None:
    assert parse_config({"severity": {code: "error"}}).severity == {code: "error"}


def test_finalize_ignores_override_of_fixed_rule() -> None:
    bag = DiagnosticBag()
    bag.add("IOL201", "нет описания", "опишите")
    bag.add("IOL104", "тег не по правилу", "переименуйте")
    items = bag.finalize({"IOL201": "off", "IOL104": "warning"})
    assert [(item.code, item.severity) for item in items] == [
        ("IOL104", Severity.WARNING),
        ("IOL201", Severity.ERROR),
    ]


def test_missing_description_with_severity_override_is_config_error(tmp_path: Path) -> None:
    """Раньше: ``[severity] IOL201 = "off"`` и пустое описание → AssertionError при сборке модели."""
    with pytest.raises(ConfigError):
        parse_config({"severity": {"IOL201": "off"}})


@pytest.mark.parametrize("code", ADJUSTABLE_ERRORS)
def test_adjustable_errors_never_crash_model(code: str, check_rows: Callable[..., CheckResult]) -> None:
    """Любое ослабляемое правило, отключённое на перечне, где оно срабатывает, не ломает модель."""
    from pytests.test_rules import CASES

    scenario = CASES[code].bad
    if scenario.raw is not None:
        pytest.skip("сценарий — сырой файл")
    config = {**scenario.config, "severity": {code: "off"}}
    result = check_rows(scenario.rows, config=config, columns=scenario.columns)
    assert code not in [item.code for item in result.diagnostics]
    if result.ok:
        assert result.model is not None
        build_plc(result.model)  # имена и привязки строятся без исключений


def test_slave_zero_is_adjustable_for_modbus_tcp(check_rows: Callable[..., CheckResult]) -> None:
    """Unit ID 0 — обычный адрес для Modbus TCP: правило IOL416 можно ослабить, адрес сохраняется."""
    row = {
        "tag": "XS101",
        "description": "Состояние по Modbus TCP",
        "signal_type": "MB",
        "device_type": "DigitalInput",
        "dev_no": 8,
        "role": "IN",
        "mb_link": "ETH1",
        "mb_slave": 0,
        "mb_func": 2,
        "mb_reg": 10,
        "mb_type": "BOOL",
    }
    strict = check_rows([row])
    assert [item.code for item in strict.errors] == ["IOL416"]
    relaxed = check_rows([row], config={"severity": {"IOL416": "warning"}})
    assert relaxed.ok and relaxed.model is not None
    address = relaxed.model.signals[0].modbus
    assert address is not None and address.slave == 0
    plc = build_plc(relaxed.model)
    assert "xMbOk_ETH1_S0" in [var.name for var in plc.io_vars]


def test_slave_outside_byte_is_structural(check_rows: Callable[..., CheckResult]) -> None:
    row = {**di("XS101", 8), "signal_type": "MB", "mb_slave": 256, "mb_func": 2, "mb_reg": 1, "mb_type": "BOOL"}
    result = check_rows([row])
    assert "IOL413" in [item.code for item in result.errors]
    assert not RULES["IOL413"].adjustable


def test_downgraded_overlap_still_generates(check_rows: Callable[..., CheckResult]) -> None:
    rows = motor_vfd()
    rows[5] = {**rows[5], "mb_reg": 3, "mb_func": 6}  # задание пишет регистр слова состояния
    result = check_rows([*rows, ai()], config={"severity": {"IOL412": "warning"}})
    assert result.ok and result.model is not None
    assert "IOL412" in [item.code for item in result.warnings]
