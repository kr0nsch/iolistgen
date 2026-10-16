"""Адресация Modbus: функции, адресные пространства, типы данных и поиск пересечений.

ПЛК в строках MB перечня — master: адрес относится к памяти слейва. Пространства Modbus
(катушки, дискретные входы, входные регистры, регистры хранения) не пересекаются между собой,
поэтому пересечения ищутся внутри ключа «линия, слейв, пространство». Регистр — 16 бит;
сигнал BOOL в регистре занимает один бит (колонка ``mb_bit``), 32-битные типы — два регистра,
64-битные — четыре.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Hashable, Sequence
from dataclasses import dataclass
from enum import Enum

REGISTER_BITS = 16
FULL_REGISTER_MASK = (1 << REGISTER_BITS) - 1
ADDRESS_MAX = 65_535


class ModbusSpace(str, Enum):
    """Адресное пространство Modbus."""

    COILS = "coils"
    DISCRETE_INPUTS = "discrete_inputs"
    INPUT_REGISTERS = "input_registers"
    HOLDING_REGISTERS = "holding_registers"

    @property
    def label(self) -> str:
        return _SPACE_TITLES[self]

    @property
    def prefix(self) -> str:
        """Префикс в нотации Modicon: 0x, 1x, 3x, 4x."""
        return _SPACE_PREFIXES[self]

    @property
    def is_bits(self) -> bool:
        return self in (ModbusSpace.COILS, ModbusSpace.DISCRETE_INPUTS)


_SPACE_TITLES = {
    ModbusSpace.COILS: "катушки",
    ModbusSpace.DISCRETE_INPUTS: "дискретные входы",
    ModbusSpace.INPUT_REGISTERS: "входные регистры",
    ModbusSpace.HOLDING_REGISTERS: "регистры хранения",
}
_SPACE_PREFIXES = {
    ModbusSpace.COILS: "0x",
    ModbusSpace.DISCRETE_INPUTS: "1x",
    ModbusSpace.INPUT_REGISTERS: "3x",
    ModbusSpace.HOLDING_REGISTERS: "4x",
}


class Access(str, Enum):
    """Направление обмена с точки зрения ПЛК-master."""

    READ = "read"
    WRITE = "write"


@dataclass(frozen=True)
class FunctionInfo:
    """Функция Modbus, которую поддерживает перечень."""

    code: int
    name: str
    space: ModbusSpace
    access: Access
    single: bool

    @property
    def label(self) -> str:
        return f"FC{self.code} {self.name}"


FUNCTIONS: dict[int, FunctionInfo] = {
    info.code: info
    for info in (
        FunctionInfo(1, "Read Coils", ModbusSpace.COILS, Access.READ, single=False),
        FunctionInfo(2, "Read Discrete Inputs", ModbusSpace.DISCRETE_INPUTS, Access.READ, single=False),
        FunctionInfo(3, "Read Holding Registers", ModbusSpace.HOLDING_REGISTERS, Access.READ, single=False),
        FunctionInfo(4, "Read Input Registers", ModbusSpace.INPUT_REGISTERS, Access.READ, single=False),
        FunctionInfo(5, "Write Single Coil", ModbusSpace.COILS, Access.WRITE, single=True),
        FunctionInfo(6, "Write Single Register", ModbusSpace.HOLDING_REGISTERS, Access.WRITE, single=True),
        FunctionInfo(15, "Write Multiple Coils", ModbusSpace.COILS, Access.WRITE, single=False),
        FunctionInfo(16, "Write Multiple Registers", ModbusSpace.HOLDING_REGISTERS, Access.WRITE, single=False),
    )
}


class ModbusType(str, Enum):
    """Тип данных значения в памяти слейва."""

    BOOL = "BOOL"
    INT = "INT"
    UINT = "UINT"
    WORD = "WORD"
    DINT = "DINT"
    UDINT = "UDINT"
    DWORD = "DWORD"
    REAL = "REAL"
    LINT = "LINT"
    ULINT = "ULINT"
    LWORD = "LWORD"
    LREAL = "LREAL"

    @property
    def words(self) -> int:
        """Число 16-битных регистров (BOOL — один бит одного регистра)."""
        return _TYPE_WORDS[self]

    @property
    def bits(self) -> int:
        return 1 if self is ModbusType.BOOL else self.words * REGISTER_BITS

    @property
    def is_numeric(self) -> bool:
        """Число, которое можно масштабировать (аналоговое значение)."""
        return self in _NUMERIC

    @property
    def is_bitstring(self) -> bool:
        """Слово битов: слово управления или состояния."""
        return self in _BITSTRINGS

    @property
    def is_float(self) -> bool:
        return self in (ModbusType.REAL, ModbusType.LREAL)


_TYPE_WORDS = {
    ModbusType.BOOL: 1,
    ModbusType.INT: 1,
    ModbusType.UINT: 1,
    ModbusType.WORD: 1,
    ModbusType.DINT: 2,
    ModbusType.UDINT: 2,
    ModbusType.DWORD: 2,
    ModbusType.REAL: 2,
    ModbusType.LINT: 4,
    ModbusType.ULINT: 4,
    ModbusType.LWORD: 4,
    ModbusType.LREAL: 4,
}
_NUMERIC = frozenset(
    {
        ModbusType.INT,
        ModbusType.UINT,
        ModbusType.DINT,
        ModbusType.UDINT,
        ModbusType.REAL,
        ModbusType.LINT,
        ModbusType.ULINT,
        ModbusType.LREAL,
    }
)
_BITSTRINGS = frozenset({ModbusType.WORD, ModbusType.DWORD, ModbusType.LWORD, ModbusType.UINT, ModbusType.INT})


class WordOrder(str, Enum):
    """Порядок 16-битных слов многорегистровых значений."""

    HL = "HL"
    LH = "LH"

    @property
    def label(self) -> str:
        return "старшее слово первым" if self is WordOrder.HL else "младшее слово первым"


@dataclass(frozen=True)
class Span:
    """Занятая сигналом область памяти слейва.

    ``key`` — линия, слейв и пространство; ``start``…``end`` — адреса (включительно);
    ``mask`` — занятые биты каждого адреса: весь регистр, один бит регистра или одна катушка.
    """

    key: Hashable
    start: int
    end: int
    mask: int


def span_mask(space: ModbusSpace, data_type: ModbusType, bit: int | None) -> int:
    """Маска занятых битов одного адреса."""
    if space.is_bits:
        return 1
    if data_type is ModbusType.BOOL and bit is not None:
        return 1 << bit
    return FULL_REGISTER_MASK


def span_length(space: ModbusSpace, data_type: ModbusType) -> int:
    """Сколько адресов занимает значение: катушек или регистров."""
    if space.is_bits:
        return 1
    return data_type.words


def find_overlaps(spans: Sequence[Span]) -> list[tuple[int, int]]:
    """Пары индексов ``(i, j)``, ``i < j``, у которых занятые области пересекаются.

    Внутри ключа области сортируются по началу; для каждой проверяются только «активные»
    области, которые ещё не закончились. Сложность — O(n log n + число пересечений).
    """
    groups: defaultdict[Hashable, list[int]] = defaultdict(list)
    for index, span in enumerate(spans):
        groups[span.key].append(index)
    pairs: list[tuple[int, int]] = []
    for indices in groups.values():
        indices.sort(key=lambda i: (spans[i].start, i))
        active: list[int] = []
        for current in indices:
            start = spans[current].start
            active = [other for other in active if spans[other].end >= start]
            for other in active:
                if spans[other].mask & spans[current].mask:
                    pairs.append((min(other, current), max(other, current)))
            active.append(current)
    pairs.sort()
    return pairs


def describe_area(space: ModbusSpace, register: int, data_type: ModbusType, bit: int | None) -> str:
    """Область для сообщений: «регистры хранения 100…101 (REAL)», «регистр хранения 7, бит 3»."""
    if space.is_bits:
        return f"{space.label} {register}"
    if data_type is ModbusType.BOOL and bit is not None:
        return f"{space.label} {register}, бит {bit}"
    end = register + data_type.words - 1
    area = f"{register}…{end}" if end != register else f"{register}"
    return f"{space.label} {area} ({data_type.value})"
