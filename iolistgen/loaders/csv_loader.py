"""Чтение перечня из CSV: UTF-8 (BOM допускается), разделитель «;» или «,» определяется сам.

Номер строки в сообщениях — номер физической строки файла, с которой начинается запись:
ячейка в кавычках может занимать несколько строк, и номер всё равно указывает на начало.
"""

from __future__ import annotations

import codecs
import csv
import hashlib
import io
from collections.abc import Iterator
from pathlib import Path

from iolistgen.columns import header_index, match_header
from iolistgen.config import InputConfig
from iolistgen.diagnostics import DiagnosticBag
from iolistgen.loaders.table import RawTable, build_table
from iolistgen.model import SourceRef

DELIMITERS = (";", ",", "\t")
_SNIFF_LINES = 30


def read_records(text: str, delimiter: str) -> Iterator[tuple[int, list[object]]]:
    """Записи CSV с номером первой физической строки каждой."""
    reader = csv.reader(io.StringIO(text, newline=""), delimiter=delimiter, quotechar='"', strict=False)
    consumed = 0
    for record in reader:
        start = consumed + 1
        consumed = reader.line_num
        yield start, list(record)


def detect_delimiter(text: str, aliases: dict[str, str] | None = None) -> str:
    """Разделитель, при котором строка заголовка даёт больше всего известных колонок.

    Так «;»-файл с десятичными запятыми в данных не принимается за «,»-файл: решает заголовок.
    Если заголовок не распознан ни с одним разделителем — самый частый символ первой строки.
    """
    index = header_index(aliases)
    lines = [line for line in text.splitlines() if line.strip() and not line.lstrip().startswith("#")]
    best = ""
    best_score = 0
    for line in lines[:_SNIFF_LINES]:
        for delimiter in DELIMITERS:
            cells = next(csv.reader([line], delimiter=delimiter), [])
            fields = {match_header(cell, index) for cell in cells}
            fields.discard(None)
            score = len(fields) if "tag" in fields else 0
            if score > best_score:
                best, best_score = delimiter, score
        if best_score >= 2:
            return best
    if best:
        return best
    first = lines[0] if lines else ""
    return max(DELIMITERS, key=lambda d: (first.count(d), d == ";"))


def load_csv(path: Path, config: InputConfig, *, display: str | None = None) -> RawTable:
    """Прочитать CSV-файл перечня."""
    data = path.read_bytes()
    name = display or str(path)
    sha256 = hashlib.sha256(data).hexdigest()
    bag = DiagnosticBag()
    codec = "utf-8-sig" if codecs.lookup(config.encoding).name == "utf-8" else config.encoding
    try:
        text = data.decode(codec)
    except UnicodeDecodeError as exc:
        line = data[: exc.start].count(b"\n") + 1
        bag.add(
            "IOL001",
            f"файл не в кодировке {config.encoding}: байт 0x{data[exc.start]:02X} в строке {line}",
            "сохраните перечень как «CSV UTF-8» (в Excel: «Сохранить как», тип «CSV UTF-8») "
            "или укажите кодировку: --encoding cp1251",
            source=SourceRef(file=name, row=line),
        )
        return RawTable(file=name, sheet=None, format="csv", sha256=sha256, diagnostics=bag)
    if not text.strip():
        bag.add(
            "IOL001", "файл пуст", "заполните перечень: строка заголовка и строки сигналов", source=SourceRef(file=name)
        )
        return RawTable(file=name, sheet=None, format="csv", sha256=sha256, diagnostics=bag)
    delimiter = config.delimiter or detect_delimiter(text, config.column_aliases)
    return build_table(
        file=name,
        sheet=None,
        fmt="csv",
        sha256=sha256,
        records=read_records(text, delimiter),
        config=config,
        bag=bag,
    )
