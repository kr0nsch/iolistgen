"""Адреса Modbus: длины типов, маски битов и поиск пересечений (в том числе property-based)."""

from __future__ import annotations

import random

from hypothesis import given, settings
from hypothesis import strategies as st

from iolistgen.modbus import (
    FULL_REGISTER_MASK,
    FUNCTIONS,
    Access,
    ModbusSpace,
    ModbusType,
    Span,
    describe_area,
    find_overlaps,
    span_length,
    span_mask,
)
from iolistgen.model import ModbusAddress


def address(function: int, register: int, data_type: str, bit: int | None = None, slave: int = 1) -> ModbusAddress:
    return ModbusAddress(slave=slave, function=function, address=register, data_type=ModbusType(data_type), bit=bit)


def span(item: ModbusAddress) -> Span:
    return Span(key=(item.link.casefold(), item.slave, item.space), start=item.address, end=item.end, mask=item.mask)


def test_type_lengths() -> None:
    assert [t.words for t in (ModbusType.INT, ModbusType.REAL, ModbusType.LREAL)] == [1, 2, 4]
    assert ModbusType.BOOL.bits == 1
    assert ModbusType.DWORD.bits == 32
    assert ModbusType.REAL.is_numeric and not ModbusType.WORD.is_numeric
    assert ModbusType.WORD.is_bitstring and not ModbusType.REAL.is_bitstring


def test_function_table() -> None:
    assert FUNCTIONS[3].space is ModbusSpace.HOLDING_REGISTERS and FUNCTIONS[3].access is Access.READ
    assert FUNCTIONS[6].space is ModbusSpace.HOLDING_REGISTERS and FUNCTIONS[6].single
    assert FUNCTIONS[2].space is ModbusSpace.DISCRETE_INPUTS
    assert {f.space for f in FUNCTIONS.values() if f.access is Access.WRITE} == {
        ModbusSpace.COILS,
        ModbusSpace.HOLDING_REGISTERS,
    }


def test_masks_and_lengths() -> None:
    assert span_mask(ModbusSpace.COILS, ModbusType.BOOL, None) == 1
    assert span_mask(ModbusSpace.HOLDING_REGISTERS, ModbusType.BOOL, 3) == 8
    assert span_mask(ModbusSpace.HOLDING_REGISTERS, ModbusType.REAL, None) == FULL_REGISTER_MASK
    assert span_length(ModbusSpace.INPUT_REGISTERS, ModbusType.LREAL) == 4
    assert span_length(ModbusSpace.COILS, ModbusType.BOOL) == 1


def test_address_properties_and_description() -> None:
    real = address(3, 100, "REAL")
    assert (real.length, real.end, real.access) == (2, 101, Access.READ)
    assert real.describe() == "регистры хранения 100…101 (REAL), слейв 1"
    flag = ModbusAddress(link="RS485-1", slave=2, function=3, address=7, data_type=ModbusType.BOOL, bit=3)
    assert flag.describe() == "регистры хранения 7, бит 3, слейв 2, линия RS485-1"
    assert describe_area(ModbusSpace.COILS, 5, ModbusType.BOOL, None) == "катушки 5"
    assert describe_area(ModbusSpace.INPUT_REGISTERS, 4, ModbusType.INT, None) == "входные регистры 4 (INT)"


def test_overlap_examples() -> None:
    items = [
        address(3, 100, "REAL"),  # 100..101
        address(3, 101, "WORD"),  # пересекается с REAL
        address(16, 102, "INT"),  # то же пространство, свободно
        address(4, 100, "REAL"),  # входные регистры — другое пространство
        address(3, 102, "BOOL", bit=0),  # бит регистра 102 — пересекается с INT 102
        address(3, 103, "BOOL", bit=1),
        address(3, 103, "BOOL", bit=2),  # другой бит того же регистра — не пересечение
        address(3, 103, "BOOL", bit=2, slave=2),  # другой слейв
        address(1, 103, "BOOL"),  # катушки — своё пространство
        address(5, 103, "BOOL"),  # та же катушка — пересечение с FC1
    ]
    assert find_overlaps([span(item) for item in items]) == [(0, 1), (2, 4), (8, 9)]


def test_same_bit_overlaps() -> None:
    items = [address(3, 10, "BOOL", bit=4), address(6, 10, "BOOL", bit=4)]
    assert find_overlaps([span(item) for item in items]) == [(0, 1)]


def test_link_separates_slaves() -> None:
    first = ModbusAddress(link="COM1", slave=1, function=3, address=0, data_type=ModbusType.INT)
    second = ModbusAddress(link="COM2", slave=1, function=3, address=0, data_type=ModbusType.INT)
    third = ModbusAddress(link="com1", slave=1, function=3, address=0, data_type=ModbusType.INT)
    assert find_overlaps([span(first), span(second), span(third)]) == [(0, 2)]


def brute_force(items: list[ModbusAddress]) -> list[tuple[int, int]]:
    """Эталон: множество занятых битов каждого сигнала и попарное сравнение."""
    units: list[set[tuple[object, int, int]]] = []
    for item in items:
        key = (item.link.casefold(), item.slave, item.space)
        occupied: set[tuple[object, int, int]] = set()
        for register in range(item.address, item.end + 1):
            for bit in range(16):
                if item.mask & (1 << bit):
                    occupied.add((key, register, bit))
        units.append(occupied)
    return [(i, j) for i in range(len(items)) for j in range(i + 1, len(items)) if units[i] & units[j]]


@st.composite
def modbus_addresses(draw: st.DrawFn) -> ModbusAddress:
    function = draw(st.sampled_from(sorted(FUNCTIONS)))
    info = FUNCTIONS[function]
    if info.space.is_bits:
        data_type, bit = ModbusType.BOOL, None
    else:
        choices = [t for t in ModbusType if not (info.single and t.words > 1)]
        data_type = draw(st.sampled_from(choices))
        bit = draw(st.integers(0, 15)) if data_type is ModbusType.BOOL else None
    return ModbusAddress(
        link=draw(st.sampled_from(["", "RS485-1", "rs485-1"])),
        slave=draw(st.integers(1, 2)),
        function=function,
        address=draw(st.integers(0, 24)),
        data_type=data_type,
        bit=bit,
    )


@settings(max_examples=400, deadline=None)
@given(st.lists(modbus_addresses(), max_size=25))
def test_overlaps_match_brute_force(items: list[ModbusAddress]) -> None:
    assert find_overlaps([span(item) for item in items]) == brute_force(items)


@settings(max_examples=200, deadline=None)
@given(st.lists(modbus_addresses(), min_size=2, max_size=12), st.randoms(use_true_random=False))
def test_overlaps_do_not_depend_on_order(items: list[ModbusAddress], rng: random.Random) -> None:
    order = list(range(len(items)))
    rng.shuffle(order)
    shuffled = [items[i] for i in order]
    pairs = {tuple(sorted((order[i], order[j]))) for i, j in find_overlaps([span(item) for item in shuffled])}
    assert pairs == set(brute_force(items))


@given(st.integers(0, 65_535 - 3), st.sampled_from(list(ModbusType)))
def test_end_is_start_plus_length(start: int, data_type: ModbusType) -> None:
    function = 3
    bit = 0 if data_type is ModbusType.BOOL else None
    item = ModbusAddress(slave=1, function=function, address=start, data_type=data_type, bit=bit)
    assert item.end - item.address + 1 == item.length == data_type.words
