"""Интерфейс ФБ библиотеки: раскладка Sts (контракт 4.6), входы и выходы, согласие с каталогом ролей."""

from __future__ import annotations

import pytest

from iolistgen.catalog import DEVICE_TYPES
from iolistgen.enums import DeviceType, Direction
from iolistgen.fbapi import ENUMS, FB_INTERFACES, STRUCTS, fb_inputs, fb_outputs, flat_fields, struct_size

# Таблица 4.6 контракта: байт и регистров у каждой Sts
STS_SIZES = {
    "ST_DeviceSts": 28,
    "ST_AnalogInputSts": 44,
    "ST_DigitalInputSts": 30,
    "ST_MotorSts": 68,
    "ST_ValveSts": 52,
    "ST_ControlValveSts": 52,
}


@pytest.mark.parametrize(("name", "size"), sorted(STS_SIZES.items()))
def test_sts_sizes_match_contract(name: str, size: int) -> None:
    assert struct_size(name) == size


@pytest.mark.parametrize("device_type", list(DeviceType))
def test_catalog_registers_match_layout(device_type: DeviceType) -> None:
    spec = DEVICE_TYPES[device_type]
    assert struct_size(spec.sts) // 2 == spec.sts_registers


@pytest.mark.parametrize("name", sorted(STS_SIZES))
def test_sts_has_only_16_and_32_bit_fields_aligned(name: str) -> None:
    for field in flat_fields(name):
        assert field.size in (2, 4), field.path
        if field.size == 4:
            assert field.offset % 4 == 0, f"{name}.{field.path} на смещении {field.offset}"


def test_motor_sts_offsets_match_contract_comments() -> None:
    offsets = {field.path: field.offset for field in flat_fields("ST_MotorSts")}
    assert offsets["eState"] == 28
    assert offsets["uiStartsLastHour"] == 38
    assert offsets["rRunTime_h"] == 40
    assert offsets["udiRunCurrent_s"] == 64


def test_valve_sts_reserve_keeps_alignment() -> None:
    offsets = {field.path: field.offset for field in flat_fields("ST_ValveSts")}
    assert offsets["wReserve"] == 38
    assert offsets["udiCycles"] == 40


def test_register_numbers() -> None:
    fields = {field.path: field for field in flat_fields("ST_AnalogInputSts")}
    assert fields["stCommon.wStatus"].register == 0
    assert fields["stCommon.eDevType"].register == 12
    assert fields["rValue_eu"].register == 14
    assert fields["rValue_eu"].registers == 2


def test_enum_fields_are_int_for_exchange() -> None:
    field = next(item for item in STRUCTS["ST_DeviceSts"] if item.name == "eMode")
    assert field.is_enum and field.scalar_type == "INT"
    assert dict(ENUMS["E_DeviceMode"])["OutOfService"] == 4


@pytest.mark.parametrize("device_type", list(DeviceType))
def test_role_pins_exist_on_fb(device_type: DeviceType) -> None:
    """Каждая роль с прямой привязкой указывает на настоящий вход или выход ФБ."""
    inputs = {item.name for item in fb_inputs(device_type)}
    outputs = {item.name for item in fb_outputs(device_type)}
    for role in DEVICE_TYPES[device_type].roles:
        if " " in role.pin:  # роли ПЧ через адаптер: «адаптер ПЧ ← xQRun, xQReset»
            continue
        pool = inputs if role.direction is Direction.IN else outputs
        assert role.pin in pool, f"{device_type.value}.{role.role.value} → {role.pin}"


def test_motor_vfd_inherits_motor_pins() -> None:
    names = [item.name for item in fb_inputs(DeviceType.MOTOR_VFD)]
    assert names[: len(FB_INTERFACES[DeviceType.MOTOR].inputs)] == [
        item.name for item in FB_INTERFACES[DeviceType.MOTOR].inputs
    ]
    assert "xCommOk" in names and "rSpeedAct_pct" in names
    outputs = [item.name for item in fb_outputs(DeviceType.MOTOR_VFD)]
    assert "xQRun" in outputs and "rSpeedRef_pct" in outputs


def test_common_sts_register_13_is_alarm_suppressed_mask() -> None:
    """1.0.0: бывший резерв — маска слотов, подавленных логикой (CONSUMERS G1); раскладка та же."""
    fields = {field.path: field for field in flat_fields("ST_DeviceSts")}
    assert fields["wAlmSuppressed"].offset == 26 and fields["wAlmSuppressed"].register == 13
    assert fields["wAlmShelved"].register == 10
    assert "wReserve" not in fields
    assert "Shelved" in fields["wAlmShelved"].field.description
    assert "SuppressedByDesign" in fields["wAlmSuppressed"].field.description


def test_alarm_event_reason_has_disabled() -> None:
    """1.0.0: закрывающее событие выключенной тревоги (CONSUMERS G2)."""
    assert dict(ENUMS["E_AlarmEventReason"])["Disabled"] == 11
    assert [value for _, value in ENUMS["E_AlarmEventReason"]] == list(range(12))
