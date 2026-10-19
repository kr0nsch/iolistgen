"""Каталог библиотеки: поля Cfg, пути params, роли устройств."""

from __future__ import annotations

import pytest

from iolistgen.catalog import (
    AI_LOWCUT_MAX_PCT,
    ALARM_SLOTS,
    DEVICE_TYPES,
    GVL_CONST_BY_NAME,
    LINK_COLUMNS,
    ROLE_DIRECTIONS,
    STARTS_WINDOW_MAX,
    STRUCTS,
    PathError,
    leaf_fields,
    link_owners,
    plain_defaults,
    resolve_path,
)
from iolistgen.enums import DeviceType, Direction, Role, SignalType


def test_leaf_fields_expand_arrays_and_structs() -> None:
    paths = [leaf.path for leaf in leaf_fields("ST_MotorCfg")]
    assert paths[0] == "xFbUsed"
    assert "stVfd.rSpeedMin_pct" in paths
    assert "astAlarm[7].tShelveMax" in paths
    assert len([p for p in paths if p.startswith("astAlarm[")]) == 8 * 4
    analog = {leaf.path: leaf for leaf in leaf_fields("ST_AnalogInputCfg")}
    assert analog["astLimit[3].rHyst_eu"].default == 0.0
    assert analog["astAlarm[0].ePriority"].default == "High"
    assert analog["astAlarm[4].ePriority"].default == "Medium"


def test_plain_defaults_ignore_dut_element_defaults() -> None:
    plain = plain_defaults("ST_AnalogInputCfg")
    assert plain["astAlarm[0].ePriority"] == "Medium"
    assert plain["tFailDelay"] == 2000


@pytest.mark.parametrize(
    ("struct", "text", "path"),
    [
        ("ST_MotorCfg", "tMinStop", "tMinStop"),
        ("ST_MotorCfg", "TMINSTOP", "tMinStop"),
        ("ST_MotorCfg", "stVfd.rSpeedMin_pct", "stVfd.rSpeedMin_pct"),
        ("ST_AnalogInputCfg", "astLimit[1].rHyst_eu", "astLimit[1].rHyst_eu"),
        ("ST_AnalogInputCfg", "astLimit[ HH ].rHyst_eu", "astLimit[0].rHyst_eu"),
        ("ST_AnalogInputCfg", "astLimit[PL.E_AiAlarm.LL].tOnDelay", "astLimit[3].tOnDelay"),
        ("ST_MotorCfg", "astAlarm[FailToStop].ePriority", "astAlarm[2].ePriority"),
    ],
)
def test_resolve_path(struct: str, text: str, path: str) -> None:
    assert resolve_path(struct, text).path == path


@pytest.mark.parametrize(
    ("struct", "text", "fragment"),
    [
        ("ST_MotorCfg", "tMinStopp", "нет поля"),
        ("ST_MotorCfg", "stVfd", "структура"),
        ("ST_MotorCfg", "stVfd.rSpeedMin", "нет поля"),
        ("ST_AnalogInputCfg", "astLimit.rHyst_eu", "нужен индекс"),
        ("ST_AnalogInputCfg", "astLimit[4].rHyst_eu", "вне границ"),
        ("ST_AnalogInputCfg", "astLimit[Failure].rHyst_eu", "вне границ"),
        ("ST_AnalogInputCfg", "astLimit[X].rHyst_eu", "неверный индекс"),
        ("ST_MotorCfg", "tMinStop[1]", "не массив"),
        ("ST_MotorCfg", "tMinStop.x", "скалярное"),
        ("ST_MotorCfg", "1abc", "неверный путь"),
    ],
)
def test_resolve_path_errors(struct: str, text: str, fragment: str) -> None:
    with pytest.raises(PathError) as info:
        resolve_path(struct, text)
    assert fragment in info.value.message


def test_unknown_field_suggests_close_name() -> None:
    with pytest.raises(PathError) as info:
        resolve_path("ST_MotorCfg", "tMinStopp")
    assert "tMinStop" in info.value.hint


def test_every_device_type_is_described() -> None:
    assert set(DEVICE_TYPES) == set(DeviceType)
    for spec in DEVICE_TYPES.values():
        assert spec.cfg in STRUCTS
        assert bool(spec.main_roles) == spec.has_io  # без сигналов (Pid) главная строка — строка устройства
        assert all(spec.role(role) is not None for role in spec.main_roles)
        assert len({slot.suffix for slot in spec.alarm_slots}) == len(spec.alarm_slots)


def test_pid_is_device_without_io() -> None:
    """Тип Pid (CONSUMERS G3): без ролей, с Retain, Sts 32 регистра, один слот тревоги PVF."""
    spec = DEVICE_TYPES[DeviceType.PID]
    assert not spec.has_io and spec.roles == () and spec.main_roles == ()
    assert (spec.fb, spec.cmd, spec.cfg, spec.sts) == ("FB_PID", "ST_PidCmd", "ST_PidCfg", "ST_PidSts")
    assert spec.has_retain and spec.sts_registers == 32
    assert [(slot.index, slot.member, slot.suffix) for slot in spec.alarm_slots] == [(0, "PvInvalid", "PVF")]
    assert spec.delay_on is None and spec.delay_off is None and spec.links == ()
    defaults = {leaf.path: leaf.default for leaf in leaf_fields("ST_PidCfg")}
    assert defaults["eAction"] == "Reverse" and defaults["rKp"] == 1.0 and defaults["tDtMax"] == 2000
    assert defaults["astAlarm[0].ePriority"] == "Medium" and defaults["astAlarm[1].ePriority"] == "None"
    assert resolve_path("ST_PidCfg", "astAlarm[PvInvalid].ePriority").path == "astAlarm[0].ePriority"


def test_alarm_slot_counts_match_library_constants() -> None:
    """Число слотов типа — константа <TYPE>_ALARM_COUNT библиотеки (у Motor слоты 6–7 только у ПЧ)."""
    counts = {
        DeviceType.ANALOG_INPUT: "AI_ALARM_COUNT",
        DeviceType.DIGITAL_INPUT: "DI_ALARM_COUNT",
        DeviceType.MOTOR_VFD: "MOT_ALARM_COUNT",
        DeviceType.VALVE: "VLV_ALARM_COUNT",
        DeviceType.CONTROL_VALVE: "CV_ALARM_COUNT",
        DeviceType.PID: "PID_ALARM_COUNT",
    }
    for device_type, name in counts.items():
        assert len(DEVICE_TYPES[device_type].alarm_slots) == int(GVL_CONST_BY_NAME[name].value), device_type
    assert ALARM_SLOTS == 8 and STARTS_WINDOW_MAX == 30 and AI_LOWCUT_MAX_PCT == 20.0


def test_roles_follow_contract_20_2() -> None:
    vfd = DEVICE_TYPES[DeviceType.MOTOR_VFD]
    assert {r.role for r in vfd.roles if r.required} == {Role.VFD_STW, Role.SPEED_REF, Role.SPEED_ACT}
    assert vfd.main_roles == (Role.CMD_RUN, Role.VFD_CTW)
    speed_ref = vfd.role(Role.SPEED_REF)
    assert speed_ref is not None and speed_ref.signal_types == {SignalType.MB, SignalType.AO}
    motor = DEVICE_TYPES[DeviceType.MOTOR]
    assert motor.role(Role.VFD_STW) is None
    assert DEVICE_TYPES[DeviceType.ANALOG_INPUT].single_signal_default is Role.PV
    assert DEVICE_TYPES[DeviceType.VALVE].single_signal_default is None


def test_role_directions_are_consistent() -> None:
    assert ROLE_DIRECTIONS[Role.PV] is Direction.IN
    assert ROLE_DIRECTIONS[Role.SPEED_REF] is Direction.OUT
    for spec in DEVICE_TYPES.values():
        for role in spec.roles:
            assert ROLE_DIRECTIONS[role.role] is role.direction


def test_links() -> None:
    assert set(LINK_COLUMNS) == {"link_power", "link_fb"}
    assert set(link_owners("link_power")) == {DeviceType.MOTOR, DeviceType.MOTOR_VFD, DeviceType.VALVE}
    assert link_owners("link_fb") == (DeviceType.CONTROL_VALVE,)
