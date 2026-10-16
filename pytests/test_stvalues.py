"""Литералы ST: разбор значений params и колонок задержки, канонические литералы."""

from __future__ import annotations

import pytest
from hypothesis import given
from hypothesis import strategies as st

from iolistgen.catalog import E_VALVE_TYPE
from iolistgen.stvalues import (
    BOOL,
    REAL,
    TIME,
    TIME_MAX_MS,
    UDINT,
    UINT,
    WORD,
    LiteralError,
    format_real,
    format_seconds,
    format_time,
    parse_int_literal,
    parse_seconds,
    parse_time,
)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("T#30S", 30_000),
        ("t#500ms", 500),
        ("TIME#1M30S", 90_000),
        ("T#1h_30m", 5_400_000),
        ("T#1.5S", 1500),
        ("T#2D", 172_800_000),
        ("T#0S", 0),
    ],
)
def test_parse_time(text: str, expected: int) -> None:
    assert parse_time(text) == expected


@pytest.mark.parametrize("text", ["30", "T#", "T#30X", "T#30S1H", "T#1.5S30MS", "T#-5S", "T#50D", "T#0.0005S"])
def test_parse_time_rejects(text: str) -> None:
    with pytest.raises(LiteralError) as info:
        parse_time(text)
    assert info.value.hint


@pytest.mark.parametrize(
    ("ms", "literal"),
    [
        (0, "T#0S"),
        (500, "T#500MS"),
        (30_000, "T#30S"),
        (90_000, "T#1M30S"),
        (3_600_000, "T#1H"),
        (86_401_001, "T#1D1S1MS"),
    ],
)
def test_format_time(ms: int, literal: str) -> None:
    assert format_time(ms) == literal


@given(st.integers(min_value=0, max_value=TIME_MAX_MS))
def test_time_literal_roundtrip(ms: int) -> None:
    assert parse_time(format_time(ms)) == ms


@pytest.mark.parametrize(
    ("value", "literal"),
    [
        (30.0, "30.0"),
        (0.05, "0.05"),
        (-1.5, "-1.5"),
        (0.0, "0.0"),
        (1e30, "1.0E30"),
        (1.5e-05, "1.5E-5"),
        (1e16, "1.0E16"),
    ],
)
def test_format_real(value: float, literal: str) -> None:
    assert format_real(value) == literal


@given(st.floats(min_value=-3.4e38, max_value=3.4e38, allow_nan=False, allow_infinity=False))
def test_real_literal_roundtrip(value: float) -> None:
    assert REAL.parse(format_real(value)) == value


def test_real_rejects_decimal_comma_with_hint() -> None:
    with pytest.raises(LiteralError) as info:
        REAL.parse("30,5")
    assert "30.5" in info.value.hint


@pytest.mark.parametrize("text", ["abc", "1e40", "nan", ""])
def test_real_rejects(text: str) -> None:
    with pytest.raises(LiteralError):
        REAL.parse(text)


def test_real_accepts_typed_literal_and_integers() -> None:
    assert REAL.parse("REAL#2.5") == 2.5
    assert REAL.parse("30") == 30.0
    with pytest.raises(LiteralError):
        REAL.parse("UINT#30")


@pytest.mark.parametrize(
    ("text", "expected"), [("6", 6), ("16#FF", 255), ("2#1010", 10), ("0x10", 16), ("1_000", 1000)]
)
def test_parse_int_literal(text: str, expected: int) -> None:
    assert parse_int_literal(text) == expected


def test_integer_types_check_range() -> None:
    assert UINT.parse("UINT#65535") == 65535
    with pytest.raises(LiteralError):
        UINT.parse("65536")
    with pytest.raises(LiteralError):
        UINT.parse("-1")
    assert UDINT.parse("4294967295") == 4_294_967_295
    with pytest.raises(LiteralError):
        UINT.parse("6.5")


def test_word_format_and_parse() -> None:
    assert WORD.parse("16#00FF") == 255
    assert WORD.format(255) == "16#00FF"
    assert WORD.format(0xFFFF) == "16#FFFF"


@pytest.mark.parametrize(("text", "expected"), [("TRUE", True), ("false", False), ("1", True), ("0", False)])
def test_bool(text: str, expected: bool) -> None:
    assert BOOL.parse(text) is expected
    assert BOOL.format(expected) == ("TRUE" if expected else "FALSE")


def test_bool_rejects() -> None:
    with pytest.raises(LiteralError):
        BOOL.parse("да")


@pytest.mark.parametrize(
    "text", ["Motorized", "motorized", "E_ValveType.Motorized", "PL.E_ValveType.Motorized", "E_ValveType#Motorized"]
)
def test_enum_forms(text: str) -> None:
    assert E_VALVE_TYPE.parse(text) == "Motorized"


def test_enum_errors_and_format() -> None:
    with pytest.raises(LiteralError) as info:
        E_VALVE_TYPE.parse("Pneumatic")
    assert "SolenoidEto" in info.value.hint
    with pytest.raises(LiteralError):
        E_VALVE_TYPE.parse("E_CvFaultAction.Hold")
    assert E_VALVE_TYPE.format("SolenoidEtc") == "PL.E_ValveType.SolenoidEtc"
    assert E_VALVE_TYPE.format("SolenoidEtc", namespace="") == "E_ValveType.SolenoidEtc"


@pytest.mark.parametrize(
    ("value", "expected"),
    [(2, 2000), (0.5, 500), ("0,5", 500), ("5 с", 5000), ("500 мс", 500), ("T#1M", 60_000), ("1.25s", 1250)],
)
def test_parse_seconds(value: object, expected: int) -> None:
    assert parse_seconds(value) == expected


@pytest.mark.parametrize("value", ["-1", "две", True, "1.0005", float("inf")])
def test_parse_seconds_rejects(value: object) -> None:
    with pytest.raises(LiteralError):
        parse_seconds(value)


def test_format_seconds() -> None:
    assert format_seconds(2000) == "2"
    assert format_seconds(500) == "0.5"


def test_types_describe_themselves() -> None:
    assert TIME.describe() == "TIME"
    assert UINT.describe() == "UINT (0…65535)"
    assert E_VALVE_TYPE.describe().startswith("E_ValveType: SolenoidEto")
    assert TIME.example() == "T#30S"
