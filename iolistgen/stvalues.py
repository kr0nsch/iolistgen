"""Литералы ST: разбор значений из перечня и запись их в сгенерированный код.

Параметры Cfg в колонке ``params`` задаются литералами ST (контракт plc-process-lib, 20.1):
``T#30S``, ``30.0``, ``TRUE``, ``16#FFFF``, ``Motorized``. Модуль разбирает их в значения
Python и записывает обратно в каноническом виде, который принимает CODESYS 3.5.17:

| Тип ST | Значение Python | Канонический литерал |
|---|---|---|
| ``BOOL`` | ``bool`` | ``TRUE`` / ``FALSE`` |
| ``REAL`` | ``float`` | ``30.0``, ``0.05``, ``1.0E30`` |
| ``UINT``, ``UDINT`` | ``int`` | ``6`` |
| ``WORD`` | ``int`` | ``16#FFFF`` |
| ``TIME`` | ``int`` (миллисекунды) | ``T#1M30S``, ``T#500MS``, ``T#0S`` |
| перечисление | ``str`` (имя значения) | ``PL.E_ValveType.Motorized`` |
"""

from __future__ import annotations

import math
import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

ScalarKind = Literal["bool", "real", "int", "word", "time", "enum"]
StScalar = bool | int | float | str

REAL_MAX = 3.4028234663852886e38
TIME_MAX_MS = 2**32 - 1

_MS_PER_UNIT = {"d": 86_400_000, "h": 3_600_000, "m": 60_000, "s": 1000, "ms": 1}
_UNIT_ORDER = ("d", "h", "m", "s", "ms")

_TIME_RE = re.compile(r"^(?:T|TIME)#(.*)$", re.IGNORECASE)
_TIME_PART_RE = re.compile(r"(\d+(?:\.\d+)?)(ms|d|h|m|s)", re.IGNORECASE)
_TYPED_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)#(.+)$")
_DEC_INT_RE = re.compile(r"^[+-]?\d(?:_?\d)*$")
_BASED_INT_RE = re.compile(r"^(16|8|2)#([0-9A-Fa-f](?:_?[0-9A-Fa-f])*)$")
_REAL_RE = re.compile(r"^[+-]?(?:\d(?:_?\d)*(?:\.\d(?:_?\d)*)?|\.\d+)(?:[eE][+-]?\d+)?$")
_C_HEX_RE = re.compile(r"^0[xX]([0-9A-Fa-f]+)$")


class LiteralError(ValueError):
    """Значение нельзя разобрать как литерал нужного типа."""

    def __init__(self, message: str, hint: str = "") -> None:
        super().__init__(message)
        self.message = message
        self.hint = hint


@dataclass(frozen=True)
class StType:
    """Скалярный тип ST, который встречается в Cfg устройств библиотеки."""

    name: str
    kind: ScalarKind
    minimum: int | None = None
    maximum: int | None = None
    members: tuple[str, ...] = ()
    values: tuple[int, ...] = ()

    def parse(self, text: str) -> StScalar:
        """Разобрать литерал ST; ``LiteralError`` — если он не подходит к типу."""
        source = text.strip()
        if not source:
            raise LiteralError("пустое значение", f"укажите литерал {self.example()}")
        if self.kind == "time":
            return parse_time(source)
        if self.kind == "enum":
            return self._parse_enum(source)
        body = self._strip_type_prefix(source)
        if self.kind == "bool":
            return _parse_bool(body, source)
        if self.kind == "real":
            return parse_real(body, source)
        return self._parse_integer(body, source)

    def format(self, value: StScalar, namespace: str = "PL") -> str:
        """Записать значение каноническим литералом ST."""
        if self.kind == "bool":
            return "TRUE" if value else "FALSE"
        if self.kind == "real":
            return format_real(float(value))
        if self.kind == "time":
            return format_time(int(value))
        if self.kind == "word":
            return f"16#{int(value):04X}"
        if self.kind == "enum":
            prefix = f"{namespace}." if namespace else ""
            return f"{prefix}{self.name}.{value}"
        return str(int(value))

    def example(self) -> str:
        """Пример литерала для подсказок."""
        examples = {
            "bool": "TRUE или FALSE",
            "real": "30.0",
            "time": "T#30S",
            "word": "16#FFFF",
            "int": "6",
        }
        if self.kind == "enum":
            return " | ".join(self.members)
        return examples[self.kind]

    def describe(self) -> str:
        """Тип для справочника: имя и допустимые значения."""
        if self.kind == "enum":
            return f"{self.name}: {', '.join(self.members)}"
        if self.kind in ("int", "word") and self.maximum is not None:
            return f"{self.name} (0…{self.maximum})"
        return self.name

    def _strip_type_prefix(self, source: str) -> str:
        match = _TYPED_RE.match(source)
        if match is None:
            return source
        prefix = match.group(1).upper()
        if prefix != self.name:
            raise LiteralError(
                f"«{source}» — литерал типа {prefix}, а параметр имеет тип {self.name}",
                f"запишите значение типа {self.name}, например {self.example()}",
            )
        return match.group(2)

    def _parse_integer(self, body: str, source: str) -> int:
        number = parse_int_literal(body)
        if number is None:
            raise LiteralError(
                f"«{source}» — не целое число",
                f"запишите целое число типа {self.name}, например {self.example()}",
            )
        low = self.minimum if self.minimum is not None else 0
        high = self.maximum if self.maximum is not None else number
        if not low <= number <= high:
            raise LiteralError(
                f"{number} вне диапазона типа {self.name} ({low}…{high})",
                f"укажите значение от {low} до {high}",
            )
        return number

    def _parse_enum(self, source: str) -> str:
        name = source
        if "#" in name:
            name = name.split("#", 1)[1]
        name = name.rsplit(".", 1)[-1]
        qualifier = source[: len(source) - len(name)].rstrip(".#")
        if qualifier:
            type_name = qualifier.rsplit(".", 1)[-1]
            if type_name.casefold() != self.name.casefold():
                raise LiteralError(
                    f"«{source}» — значение перечисления {type_name}, а параметр имеет тип {self.name}",
                    f"допустимые значения: {', '.join(self.members)}",
                )
        for member in self.members:
            if member.casefold() == name.casefold():
                return member
        raise LiteralError(
            f"«{source}» — нет такого значения в {self.name}",
            f"допустимые значения: {', '.join(self.members)}",
        )


def enum_type(name: str, members: Sequence[tuple[str, int]]) -> StType:
    """Тип-перечисление с явными значениями."""
    return StType(
        name=name,
        kind="enum",
        members=tuple(member for member, _ in members),
        values=tuple(value for _, value in members),
    )


BOOL = StType("BOOL", "bool")
REAL = StType("REAL", "real")
TIME = StType("TIME", "time", 0, TIME_MAX_MS)
UINT = StType("UINT", "int", 0, 65_535)
UDINT = StType("UDINT", "int", 0, 2**32 - 1)
WORD = StType("WORD", "word", 0, 65_535)


def _parse_bool(body: str, source: str) -> bool:
    folded = body.casefold()
    if folded in ("true", "1"):
        return True
    if folded in ("false", "0"):
        return False
    raise LiteralError(f"«{source}» — не литерал BOOL", "запишите TRUE или FALSE")


def parse_int_literal(text: str) -> int | None:
    """Целое в записи ST (``6``, ``16#FF``, ``2#1010``) или C (``0x10``); ``None`` — не целое."""
    body = text.strip()
    if _DEC_INT_RE.match(body):
        return int(body.replace("_", ""))
    based = _BASED_INT_RE.match(body)
    if based is not None:
        digits = based.group(2).replace("_", "")
        base = int(based.group(1))
        try:
            return int(digits, base)
        except ValueError:
            return None
    c_hex = _C_HEX_RE.match(body)
    if c_hex is not None:
        return int(c_hex.group(1), 16)
    return None


def parse_real(body: str, source: str | None = None) -> float:
    """Литерал REAL: ``30``, ``30.0``, ``-1.5E3``. Десятичный разделитель — точка."""
    shown = source if source is not None else body
    if "," in body and _REAL_RE.match(body.replace(",", ".", 1)):
        raise LiteralError(
            f"«{shown}» — в литерале ST дробная часть отделяется точкой",
            f"запишите {body.replace(',', '.', 1)}",
        )
    if not _REAL_RE.match(body):
        raise LiteralError(f"«{shown}» — не число", "запишите число, например 30.0")
    value = float(body.replace("_", ""))
    if not math.isfinite(value) or abs(value) > REAL_MAX:
        raise LiteralError(f"«{shown}» — вне диапазона REAL", "укажите конечное число по модулю до 3.4E38")
    return value


def parse_time(source: str) -> int:
    """Литерал TIME (``T#1M30S``, ``TIME#500ms``) → миллисекунды."""
    match = _TIME_RE.match(source.strip())
    hint = "запишите длительность литералом TIME: T#30S, T#500MS, T#1M30S"
    if match is None:
        raise LiteralError(f"«{source}» — не литерал TIME", hint)
    body = match.group(1).replace("_", "")
    if body.startswith(("-", "+")):
        raise LiteralError(f"«{source}» — длительность со знаком не допускается", hint)
    position = 0
    total = 0.0
    last_rank = -1
    parts = list(_TIME_PART_RE.finditer(body))
    for index, part in enumerate(parts):
        unit = part.group(2).lower()
        rank = _UNIT_ORDER.index(unit)
        if part.start() != position or rank <= last_rank:
            raise LiteralError(f"«{source}» — неверный литерал TIME", hint)
        number = part.group(1)
        if "." in number and index != len(parts) - 1:
            raise LiteralError(f"«{source}» — дробной может быть только последняя часть", hint)
        total += float(number) * _MS_PER_UNIT[unit]
        position = part.end()
        last_rank = rank
    if not parts or position != len(body):
        raise LiteralError(f"«{source}» — неверный литерал TIME", hint)
    milliseconds = round(total)
    if abs(total - milliseconds) > 1e-6:
        raise LiteralError(f"«{source}» — TIME хранит целые миллисекунды", "округлите длительность до 1 мс")
    if milliseconds > TIME_MAX_MS:
        raise LiteralError(f"«{source}» — больше предела TIME (≈ 49 сут)", "уменьшите длительность")
    return milliseconds


_SECONDS_RE = re.compile(r"^(\d+(?:[.,]\d+)?)\s*(с|сек|s|мс|ms)?\.?$", re.IGNORECASE)


def parse_seconds(value: object) -> int:
    """Длительность из колонки задержки → мс.

    Допускается число секунд (``2``, ``0,5``, ``5 с``), миллисекунды с единицей (``500 мс``)
    или литерал TIME (``T#500MS``).
    """
    hint = "укажите число секунд (2, 0.5), «500 мс» или литерал TIME (T#500MS)"
    if isinstance(value, bool):
        raise LiteralError(f"«{value}» — не длительность", hint)
    if isinstance(value, int | float):
        seconds = float(value)
    else:
        text = str(value).strip()
        if _TIME_RE.match(text):
            return parse_time(text)
        if text.startswith("-"):
            raise LiteralError(f"задержка «{text}» отрицательна", "укажите задержку не меньше 0")
        match = _SECONDS_RE.match(text)
        if match is None:
            raise LiteralError(f"«{text}» — не длительность", hint)
        seconds = float(match.group(1).replace(",", "."))
        if (match.group(2) or "").casefold() in ("мс", "ms"):
            seconds /= 1000
    if not math.isfinite(seconds):
        raise LiteralError(f"«{value}» — не конечное число", "укажите число секунд")
    if seconds < 0:
        raise LiteralError(f"задержка {format_real(seconds)} с отрицательна", "укажите задержку не меньше 0")
    milliseconds = round(seconds * 1000)
    if abs(seconds * 1000 - milliseconds) > 1e-6:
        raise LiteralError(f"«{value}» — точнее 1 мс", "округлите задержку до 0.001 с")
    if milliseconds > TIME_MAX_MS:
        raise LiteralError(f"«{value}» — больше предела TIME (≈ 49 сут)", "уменьшите задержку")
    return milliseconds


def format_time(milliseconds: int) -> str:
    """Миллисекунды → канонический литерал TIME (``T#1M30S``)."""
    if milliseconds < 0:
        raise ValueError("TIME не бывает отрицательным")
    if milliseconds == 0:
        return "T#0S"
    rest = milliseconds
    parts: list[str] = []
    for unit in _UNIT_ORDER:
        count, rest = divmod(rest, _MS_PER_UNIT[unit])
        if count:
            parts.append(f"{count}{unit.upper()}")
    return "T#" + "".join(parts)


def format_real(value: float) -> str:
    """Число → литерал REAL: всегда с точкой, экспонента в виде ``1.0E30``."""
    if not math.isfinite(value):
        raise ValueError("REAL-литерал должен быть конечным")
    if value == 0:
        return "0.0"
    text = repr(float(value))
    if "e" in text:
        mantissa, exponent = text.split("e")
        if "." not in mantissa:
            mantissa += ".0"
        return f"{mantissa}E{int(exponent)}"
    if "." not in text:
        text += ".0"
    return text


def format_seconds(milliseconds: int) -> str:
    """Миллисекунды → секунды для таблиц документации (``2``, ``0.5``)."""
    seconds = milliseconds / 1000
    if seconds == int(seconds):
        return str(int(seconds))
    return f"{seconds:g}"
