"""Разбор ячеек строки перечня в типизированные значения с сообщениями об ошибках.

Ошибка в ячейке не останавливает разбор: поле остаётся пустым, сообщение записывается, а
остальные проверки продолжаются. Так за один прогон видны все ошибки перечня.
"""

from __future__ import annotations

import datetime as dt
import difflib
import math
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import TypeVar

from iolistgen.diagnostics import DiagnosticBag
from iolistgen.enums import AlarmPriority, DeviceType, Role, SignalType
from iolistgen.identifiers import HOMOGLYPHS, identifier_key, to_identifier
from iolistgen.loaders.table import ColumnBinding, RawCell, RawRow, RawTable
from iolistgen.modbus import FUNCTIONS, ModbusType, WordOrder
from iolistgen.model import SourceRef
from iolistgen.stvalues import LiteralError, parse_int_literal, parse_seconds

E = TypeVar("E", bound=Enum)

_NUMBER_RE = re.compile(r"^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?$")
_GROUPED_RE = re.compile(r"^[+-]?\d{1,3}(?: \d{3})+(?:[.,]\d+)?$")
# Пробелы-разделители разрядов: неразрывный (Excel в русской Windows), узкий неразрывный, тонкий
_SPACES = str.maketrans({"\u00a0": " ", "\u202f": " ", "\u2009": " "})
# Знак минус U+2212 и тире перед числом — так минус приходит из Word, PDF и паспортов приборов
_MINUS_RE = re.compile(r"^[\u2212\u2012\u2013]\s*(?=[\d.,])")
_SIGN_SPACE_RE = re.compile(r"^([+-])\s+(?=[\d.,])")
# Ошибки формул Excel: #ЗНАЧ!, #VALUE!, #ДЕЛ/0!, #REF!, #N/A, #Н/Д, #ИМЯ? …
_EXCEL_ERROR_RE = re.compile(r"^#(?:[^\s]+[!?]|N/A|Н/Д)$", re.IGNORECASE)
# Excel хранит до 17 значащих цифр, а показывает 15: 0.1 + 0.2 → 0.30000000000000004 → 0.3
_EXCEL_DIGITS = 15


def normalize_number_text(text: str) -> str:
    """Текст числа: разделители разрядов → пробел, минус U+2212 и тире → «-», без пробела после знака."""
    value = text.translate(_SPACES).strip()
    value = _MINUS_RE.sub("-", value)
    return _SIGN_SPACE_RE.sub(r"\1", value)


def excel_float(value: float) -> float:
    """Число из ячейки XLSX без «хвоста» двоичного представления: как его показывает Excel."""
    return float(f"{value:.{_EXCEL_DIGITS}g}")


_PRIORITY_ALIASES = {
    "none": AlarmPriority.NONE,
    "нет": AlarmPriority.NONE,
    "0": AlarmPriority.NONE,
    "low": AlarmPriority.LOW,
    "низкий": AlarmPriority.LOW,
    "1": AlarmPriority.LOW,
    "medium": AlarmPriority.MEDIUM,
    "средний": AlarmPriority.MEDIUM,
    "2": AlarmPriority.MEDIUM,
    "high": AlarmPriority.HIGH,
    "высокий": AlarmPriority.HIGH,
    "3": AlarmPriority.HIGH,
    "critical": AlarmPriority.CRITICAL,
    "критический": AlarmPriority.CRITICAL,
    "4": AlarmPriority.CRITICAL,
}
_SIGNAL_ALIASES = {"MODBUS": SignalType.MB}
_WORD_ORDER_ALIASES = {"HL": WordOrder.HL, "ABCD": WordOrder.HL, "LH": WordOrder.LH, "CDAB": WordOrder.LH}


@dataclass(frozen=True)
class ParamText:
    """Присваивание из ``params`` до проверки пути: ``tMinStop`` = ``T#30S``."""

    path: str
    value: str
    source: SourceRef


@dataclass
class ModbusDraft:
    """Поля адреса Modbus строки (каждое может быть не задано или не разобрано)."""

    link: str = ""
    slave: int | None = None
    function: int | None = None
    register: int | None = None
    data_type: ModbusType | None = None
    bit: int | None = None
    word_order: WordOrder | None = None
    present: set[str] = field(default_factory=set)


@dataclass
class SignalDraft:
    """Строка перечня после разбора ячеек."""

    row: RawRow
    columns: dict[str, ColumnBinding]
    tag: str | None = None
    ident: str | None = None
    description: str | None = None
    signal_type: SignalType | None = None
    device_name: str | None = None
    device_explicit: bool = False
    device_type: DeviceType | None = None
    dev_no: int | None = None
    role: Role | None = None
    role_default: bool = False
    dev_desc: str | None = None
    range_min: float | None = None
    range_max: float | None = None
    units: str | None = None
    setpoints: dict[str, float] = field(default_factory=dict)
    delay_on_ms: int | None = None
    delay_off_ms: int | None = None
    alarm_priority: AlarmPriority | None = None
    hmi_group: str | None = None
    io_module: str | None = None
    io_channel: int | None = None
    modbus: ModbusDraft = field(default_factory=ModbusDraft)
    link_power: str | None = None
    link_fb: str | None = None
    params: list[ParamText] = field(default_factory=list)
    invalid: set[str] = field(default_factory=set)
    duplicate: bool = False

    @property
    def source(self) -> SourceRef:
        return self.row.source

    @property
    def line(self) -> int:
        return self.row.source.row or 0

    def has(self, name: str) -> bool:
        """В ячейке колонки что-то записано (даже если значение не разобрано)."""
        return name in self.row.cells

    def cell(self, name: str) -> SourceRef:
        """Ячейка колонки в этой строке; если колонки нет в файле — вся строка."""
        if name in self.row.cells:
            return self.row.cells[name].source
        binding = self.columns.get(name)
        if binding is not None:
            return self.row.source.cell(binding.index, binding.header)
        return self.row.source

    @property
    def device_key(self) -> str | None:
        if self.device_name is None:
            return None
        return identifier_key(to_identifier(self.device_name))

    @property
    def label(self) -> str:
        return self.tag or f"строка {self.line}"


class _Parser:
    """Разбор ячеек одной строки."""

    def __init__(self, draft: SignalDraft, bag: DiagnosticBag) -> None:
        self.draft = draft
        self.bag = bag

    def cell(self, name: str) -> RawCell | None:
        return self.draft.row.cells.get(name)

    def fail(self, name: str, code: str, message: str, hint: str) -> None:
        self.draft.invalid.add(name)
        self.bag.add(code, message, hint, source=self.draft.cell(name), tag=self.draft.tag)

    def text(self, name: str) -> str | None:
        cell = self.cell(name)
        if cell is None:
            return None
        value = " ".join(cell.text.split()) if name != "params" else cell.text
        return value or None

    def number(self, name: str) -> float | None:
        cell = self.cell(name)
        if cell is None:
            return None
        value = cell.value
        if isinstance(value, bool | dt.datetime | dt.date | dt.time):
            self.fail(
                name,
                "IOL007",
                f"«{cell.text}» — не число",
                "Excel мог превратить значение в дату или логическое: задайте ячейке числовой формат",
            )
            return None
        if isinstance(value, float):
            number = excel_float(value)
        elif isinstance(value, int):
            number = float(value)
        else:
            text = normalize_number_text(cell.text)
            if _GROUPED_RE.match(text):
                text = text.replace(" ", "")  # «1 000» — разряды через пробел
            if text.count(",") == 1 and "." not in text:
                text = text.replace(",", ".")
            if not _NUMBER_RE.match(text):
                self.fail_number(name, cell, "запишите число: 4.5 или 4,5")
                return None
            number = float(text)
        if not math.isfinite(number):
            self.fail(name, "IOL007", f"«{cell.text}» — не конечное число", "запишите конечное число")
            return None
        return number

    def fail_number(self, name: str, cell: RawCell, hint: str, what: str = "число") -> None:
        if _EXCEL_ERROR_RE.match(cell.text.strip()):
            self.fail(
                name,
                "IOL007",
                f"«{cell.text}» — ошибка формулы Excel, а не {what}",
                "исправьте формулу в книге или запишите значение",
            )
            return
        self.fail(name, "IOL007", f"«{cell.text}» — не {what}", hint)

    def integer(self, name: str, *, what: str = "целое число") -> int | None:
        cell = self.cell(name)
        if cell is None:
            return None
        value = cell.value
        if isinstance(value, bool):
            number = None
        elif isinstance(value, int):
            number = value
        elif isinstance(value, float):
            number = int(value) if value.is_integer() else None
        else:
            text = normalize_number_text(cell.text)
            if _GROUPED_RE.match(text):
                text = text.replace(" ", "")
            number = parse_int_literal(text)
            if number is None and re.fullmatch(r"[+-]?\d+[.,]0*", text):
                number = int(float(text.replace(",", ".")))
        if number is None:
            self.fail_number(name, cell, f"запишите {what}: 100, 16#64 или 0x64", what)
        return number

    def duration(self, name: str) -> int | None:
        cell = self.cell(name)
        if cell is None:
            return None
        value = cell.value
        if isinstance(value, dt.timedelta):
            value = value.total_seconds()  # ячейка Excel в формате [ч]:мм:сс
        elif isinstance(value, dt.time):
            value = value.hour * 3600 + value.minute * 60 + value.second + value.microsecond / 1e6
        elif isinstance(value, float):
            value = excel_float(value)
        elif isinstance(value, str) and _EXCEL_ERROR_RE.match(value.strip()):
            self.fail_number(name, cell, "", "длительность")
            return None
        try:
            return parse_seconds(value)
        except LiteralError as exc:
            self.fail(name, "IOL007", exc.message, exc.hint)
            return None

    def choice(
        self,
        name: str,
        enum: type[E],
        *,
        code: str,
        what: str,
        aliases: dict[str, E] | None = None,
        normalize: Callable[[str], str] = str.upper,
    ) -> E | None:
        cell = self.cell(name)
        if cell is None:
            return None
        text = cell.text.strip()
        # 1) как записано; 2) кириллица-двойник → латиница («АI» в русской раскладке);
        # 3) первое слово: пояснение после значения («AI 4–20 мА», «DI (сухой контакт)»)
        latin = "".join(HOMOGLYPHS.get(char, char) for char in text)
        for candidate in dict.fromkeys((text, latin, _FIRST_WORD_RE.split(latin, maxsplit=1)[0])):
            found = _lookup(enum, normalize(candidate), normalize, aliases)
            if found is not None:
                return found
        choices = [str(member.value) for member in enum]
        close = difflib.get_close_matches(cell.text.strip(), choices, n=1, cutoff=0.5)
        hint = f"допустимые значения: {', '.join(choices)}"
        if close:
            hint = f"возможно, {close[0]}; {hint}"
        self.fail(name, code, f"«{cell.text}» — неизвестный {what}", hint)
        return None


_FIRST_WORD_RE = re.compile(r"[\s(,;:]")


def _lookup(enum: type[E], key: str, normalize: Callable[[str], str], aliases: dict[str, E] | None) -> E | None:
    for member in enum:
        if normalize(str(member.value)) == key:
            return member
    if aliases and key in aliases:
        return aliases[key]
    return None


def _device_type_key(text: str) -> str:
    key = text.strip().casefold()
    for prefix in ("pl.", "fb_"):
        if key.startswith(prefix):
            key = key[len(prefix) :]
    return key


def parse_row(row: RawRow, columns: dict[str, ColumnBinding], bag: DiagnosticBag) -> SignalDraft:
    """Разобрать строку: все ячейки, кроме зависящих от типа устройства проверок."""
    draft = SignalDraft(row=row, columns=columns)
    parser = _Parser(draft, bag)
    draft.tag = parser.text("tag")
    if draft.tag is not None:
        draft.ident = to_identifier(draft.tag)
    draft.description = parser.text("description")
    draft.signal_type = parser.choice(
        "signal_type", SignalType, code="IOL202", what="тип сигнала", aliases=_SIGNAL_ALIASES
    )
    device = parser.text("device")
    draft.device_explicit = device is not None
    draft.device_name = device if device is not None else draft.tag
    draft.device_type = parser.choice(
        "device_type", DeviceType, code="IOL301", what="тип устройства", normalize=_device_type_key
    )
    draft.dev_no = parser.integer("dev_no", what="целый номер устройства")
    draft.role = parser.choice("role", Role, code="IOL304", what="роль")
    draft.dev_desc = parser.text("dev_desc")
    draft.range_min = parser.number("range_min")
    draft.range_max = parser.number("range_max")
    draft.units = parser.text("units")
    for name in ("sp_hh", "sp_h", "sp_l", "sp_ll"):
        value = parser.number(name)
        if value is not None:
            draft.setpoints[name[3:]] = value
    draft.delay_on_ms = parser.duration("delay_on_s")
    draft.delay_off_ms = parser.duration("delay_off_s")
    draft.alarm_priority = parser.choice(
        "alarm_priority",
        AlarmPriority,
        code="IOL007",
        what="приоритет тревоги",
        aliases={key.casefold(): value for key, value in _PRIORITY_ALIASES.items()},
        normalize=str.casefold,
    )
    draft.hmi_group = parser.text("hmi_group")
    draft.io_module = parser.text("io_module")
    draft.io_channel = parser.integer("io_channel", what="номер канала")
    if draft.io_channel is not None and draft.io_channel < 0:
        parser.fail("io_channel", "IOL007", f"номер канала {draft.io_channel} отрицателен", "укажите канал от 0")
        draft.io_channel = None
    _parse_modbus(parser, draft)
    draft.link_power = parser.text("link_power")
    draft.link_fb = parser.text("link_fb")
    draft.params = _split_params(parser, draft)
    return draft


def _parse_modbus(parser: _Parser, draft: SignalDraft) -> None:
    mb = draft.modbus
    mb.present = {
        name
        for name in ("mb_link", "mb_slave", "mb_func", "mb_reg", "mb_type", "mb_bit", "mb_order")
        if draft.has(name)
    }
    mb.link = parser.text("mb_link") or ""
    mb.slave = parser.integer("mb_slave", what="адрес слейва")
    function = parser.integer("mb_func", what="номер функции")
    if function is not None and function not in FUNCTIONS:
        codes = ", ".join(str(code) for code in FUNCTIONS)
        parser.fail(
            "mb_func",
            "IOL403",
            f"функция Modbus {function} не поддерживается",
            f"поддерживаются функции {codes}: чтение 1–4, запись 5, 6, 15, 16",
        )
        function = None
    mb.function = function
    mb.register = parser.integer("mb_reg", what="адрес регистра")
    mb.data_type = parser.choice("mb_type", ModbusType, code="IOL404", what="тип данных Modbus")
    mb.bit = parser.integer("mb_bit", what="номер бита")
    mb.word_order = parser.choice(
        "mb_order", WordOrder, code="IOL007", what="порядок слов", aliases=_WORD_ORDER_ALIASES
    )


def _split_params(parser: _Parser, draft: SignalDraft) -> list[ParamText]:
    cell = parser.cell("params")
    if cell is None:
        return []
    result: list[ParamText] = []
    pieces = [piece.strip() for piece in re.split(r"[;\n]", cell.text)]
    for piece in pieces:
        if not piece:
            continue
        path, sep, value = piece.partition("=")
        if not sep or not path.strip() or not value.strip():
            parser.fail(
                "params",
                "IOL501",
                f"«{piece}» — ожидается <путь>=<литерал ST>",
                "пример: tMinStop=T#30S; uiMaxStartsPerHour=6; stVfd.rSpeedMin_pct=30.0",
            )
            continue
        result.append(ParamText(path=path.strip(), value=value.strip(), source=cell.source))
    return result


def parse_table(table: RawTable, bag: DiagnosticBag) -> list[SignalDraft]:
    """Разобрать все строки таблицы."""
    columns = table.fields
    return [parse_row(row, columns, bag) for row in table.rows]
