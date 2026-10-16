"""Таблица перечня из файла: строка заголовка, привязка колонок, ячейки с координатами.

Загрузчики CSV и XLSX отдают сюда записи ``(номер строки, значения ячеек)``. Здесь ищется
строка заголовка (первая строка с колонкой ``tag`` в пределах ``input.header_search_rows``),
заголовки сопоставляются с колонками схемы, а каждая ячейка получает место в файле:
номер строки, номер и букву колонки, текст заголовка.

SHA-256 перечня считается по содержимому таблицы — строке заголовка и строкам данных, — а не
по байтам файла: пересохранение книги Excel без правок, титул, пустые строки и строки-комментарии
его не меняют, поэтому не меняются и заголовки сгенерированных файлов.
"""

from __future__ import annotations

import datetime as dt
import hashlib
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from typing import Literal

from iolistgen.columns import (
    COLUMN_BY_NAME,
    NUMERIC_COLUMNS,
    REQUIRED_COLUMNS,
    header_index,
    match_header,
    normalize_header,
)
from iolistgen.config import InputConfig
from iolistgen.diagnostics import DiagnosticBag
from iolistgen.model import SourceRef, column_letter

FileFormat = Literal["csv", "xlsx"]


class InputError(Exception):
    """Файл перечня нельзя открыть: нет файла или неподдерживаемый формат."""


@dataclass(frozen=True)
class RawCell:
    """Непустая ячейка: значение как в файле (CSV — строка, XLSX — число, строка, дата)."""

    value: object
    source: SourceRef

    @property
    def text(self) -> str:
        return cell_text(self.value)


def cell_text(value: object) -> str:
    """Значение ячейки как текст: ``12.0`` из XLSX → ``12``, ``True`` → ``TRUE``."""
    if value is None:
        return ""
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    if isinstance(value, dt.datetime | dt.date | dt.time):
        return value.isoformat()
    return str(value).strip()


def is_empty(value: object) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


_DASHES = frozenset("-\u2010\u2011\u2012\u2013\u2014\u2015\u2212")  # дефис, тире, знак минус


def is_dash(value: object) -> bool:
    """Ячейка из одних тире («—», «–», «-»): в таблицах так пишут «нет значения»."""
    return isinstance(value, str) and bool(value.strip()) and all(char in _DASHES for char in value.strip())


@dataclass(frozen=True)
class ColumnBinding:
    """Колонка файла: номер (с 1), текст заголовка и колонка схемы (``None`` — неизвестная).

    ``skipped`` — значения не читаются вовсе: колонка в ``input.ignore_columns`` или повтор.
    """

    index: int
    header: str
    field: str | None
    skipped: bool = False

    @property
    def letter(self) -> str:
        return column_letter(self.index)


@dataclass
class RawRow:
    """Строка данных: непустые ячейки известных колонок и прочие непустые ячейки."""

    source: SourceRef
    cells: dict[str, RawCell]
    extra: dict[str, RawCell]


@dataclass
class RawTable:
    """Таблица перечня после чтения файла."""

    file: str
    sheet: str | None
    format: FileFormat
    sha256: str
    header_row: int | None = None
    columns: list[ColumnBinding] = field(default_factory=list)
    rows: list[RawRow] = field(default_factory=list)
    diagnostics: DiagnosticBag = field(default_factory=DiagnosticBag)

    @property
    def fields(self) -> dict[str, ColumnBinding]:
        """Колонка схемы → колонка файла (первая, если колонка повторяется)."""
        result: dict[str, ColumnBinding] = {}
        for binding in self.columns:
            if binding.field is not None and binding.field not in result:
                result[binding.field] = binding
        return result

    def has_column(self, name: str) -> bool:
        return name in self.fields

    def file_source(self) -> SourceRef:
        return SourceRef(file=self.file, sheet=self.sheet)


def _is_comment(values: Sequence[object]) -> bool:
    for value in values:
        if is_empty(value):
            continue
        return isinstance(value, str) and value.lstrip().startswith("#")
    return False


def looks_like_header(values: Sequence[object], index: dict[str, str]) -> bool:
    """Строка — заголовок: в ней есть колонка ``tag`` и ещё хотя бы одна колонка схемы."""
    fields = {match_header(cell_text(value), index) for value in values if not is_empty(value)}
    fields.discard(None)
    return "tag" in fields and len(fields) >= 2


def build_table(
    *,
    file: str,
    sheet: str | None,
    fmt: FileFormat,
    sha256: str,
    records: Iterable[tuple[int, Sequence[object]]],
    config: InputConfig,
    bag: DiagnosticBag | None = None,
) -> RawTable:
    """Найти заголовок, привязать колонки и собрать строки данных."""
    table = RawTable(file=file, sheet=sheet, format=fmt, sha256=sha256)
    if bag is not None:
        table.diagnostics = bag
    index = header_index(config.column_aliases)
    ignored = {normalize_header(name) for name in config.ignore_columns}
    digest = hashlib.sha256()
    iterator = iter(records)
    scanned = 0
    for row_no, values in iterator:
        if all(is_empty(value) for value in values) or _is_comment(values):
            continue
        if looks_like_header(values, index):
            table.header_row = row_no
            table.columns = _bind_columns(table, row_no, values, index, ignored)
            digest.update(_canonical(values))
            break
        scanned += 1
        if scanned >= config.header_search_rows:
            break
    if table.header_row is None:
        known = ", ".join(spec.name for spec in COLUMN_BY_NAME.values() if spec.name in REQUIRED_COLUMNS)
        table.diagnostics.add(
            "IOL002",
            f"не найдена строка заголовка в первых {config.header_search_rows} строках",
            f"первая строка таблицы — заголовки колонок, среди них tag («Тег»); обязательные колонки: {known}; "
            "свои названия колонок («Позиция по схеме») — в [input] column_aliases файла iolistgen.toml",
            source=table.file_source(),
        )
        return table
    _check_required(table)
    width = len(table.columns)
    # В CSV с разделителем «;» ячейка params без кавычек распадается на несколько: если params —
    # последняя колонка, хвост строки — продолжение params (его разделитель — тоже «;»)
    params_last = fmt == "csv" and width > 0 and table.columns[-1].field == "params"
    reported_extra: set[int] = set()
    for row_no, values in iterator:
        if all(is_empty(value) for value in values) or _is_comment(values):
            continue
        digest.update(_canonical(values))
        row_source = SourceRef(file=file, sheet=sheet, row=row_no)
        cells: dict[str, RawCell] = {}
        extra: dict[str, RawCell] = {}
        if params_last and len(values) > width and not is_empty(values[width - 1]):
            tail = [cell_text(value) for value in values[width - 1 :] if not is_empty(value)]
            values = [*values[: width - 1], "; ".join(tail)]
        for position, value in enumerate(values, start=1):
            if is_empty(value):
                continue
            if position > width:
                if position not in reported_extra:
                    reported_extra.add(position)
                    table.diagnostics.add(
                        "IOL006",
                        f"в колонке {column_letter(position)} есть значения, но нет заголовка",
                        "добавьте заголовок колонки или очистите её",
                        source=row_source.cell(position, None),
                    )
                continue
            binding = table.columns[position - 1]
            if binding.skipped or (binding.field in NUMERIC_COLUMNS and is_dash(value)):
                continue
            cell = RawCell(value, row_source.cell(position, binding.header or None))
            if binding.field is None:
                if binding.header:
                    extra[binding.header] = cell
                elif position not in reported_extra:
                    reported_extra.add(position)
                    table.diagnostics.add(
                        "IOL006",
                        f"в колонке {binding.letter} есть значения, но нет заголовка",
                        "добавьте заголовок колонки или очистите её",
                        source=cell.source,
                    )
                continue
            if binding.field in cells:
                continue
            cells[binding.field] = cell
        table.rows.append(RawRow(source=row_source, cells=cells, extra=extra))
    table.sha256 = digest.hexdigest()
    return table


def _canonical(values: Sequence[object]) -> bytes:
    """Строка таблицы для SHA-256: тексты ячеек без пустого хвоста, разделитель — U+001F."""
    texts = [cell_text(value) for value in values]
    while texts and not texts[-1]:
        texts.pop()
    return ("\x1f".join(texts) + "\n").encode("utf-8")


def _bind_columns(
    table: RawTable,
    row_no: int,
    values: Sequence[object],
    index: dict[str, str],
    ignored: set[str],
) -> list[ColumnBinding]:
    bindings: list[ColumnBinding] = []
    seen: dict[str, ColumnBinding] = {}
    for position, value in enumerate(values, start=1):
        header = cell_text(value)
        source = SourceRef(file=table.file, sheet=table.sheet, row=row_no, col=position, header=header or None)
        if header and normalize_header(header) in ignored:
            bindings.append(ColumnBinding(index=position, header=header, field=None, skipped=True))
            continue
        name = match_header(header, index) if header else None
        if name is not None and name in seen:
            first = seen[name]
            table.diagnostics.add(
                "IOL004",
                f"колонка {name} повторяется: «{first.header}» ({first.letter}) и «{header}» "
                f"({column_letter(position)})",
                "оставьте одну колонку: значения повтора не читаются",
                source=source,
            )
            bindings.append(ColumnBinding(index=position, header=header, field=None, skipped=True))
            continue
        if header and name is None:
            table.diagnostics.add(
                "IOL005",
                f"неизвестная колонка «{header}»: значения не проверяются",
                "переименуйте по схеме (iolistgen schema), добавьте синоним в [input] column_aliases "
                "или внесите колонку в [input] ignore_columns",
                source=source,
            )
        binding = ColumnBinding(index=position, header=header, field=name)
        if name is not None:
            seen[name] = binding
        bindings.append(binding)
    return bindings


def _check_required(table: RawTable) -> None:
    present = table.fields
    for name in REQUIRED_COLUMNS:
        if name in present:
            continue
        spec = COLUMN_BY_NAME[name]
        table.diagnostics.add(
            "IOL003",
            f"нет обязательной колонки {name} («{spec.title}»)",
            f"добавьте колонку {name}: {spec.description}",
            source=SourceRef(file=table.file, sheet=table.sheet, row=table.header_row),
        )
