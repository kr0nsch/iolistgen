"""Запись CSV генераторов: заголовок-комментарий, разделитель, детерминированный текст.

Первые строки файла — заголовок ``# AUTO-GENERATED …`` (опция ``comment_header``). Импорт,
который не понимает строк-комментариев (часть SCADA и Excel), получает файл без них:
``--set <генератор>.comment_header=false``. Кодировка — UTF-8 без BOM, переводы строк LF.
"""

from __future__ import annotations

import csv
import io
from collections.abc import Iterable, Mapping, Sequence

from iolistgen.generators.base import GeneratorContext, GeneratorOption

CsvValue = str | int | float | None

DELIMITER_OPTION = GeneratorOption("delimiter", "разделитель CSV", "choice", ";", (";", ",", "tab"))
COMMENT_OPTION = GeneratorOption(
    "comment_header", "строки «# AUTO-GENERATED …» в начале CSV (false — для импорта без комментариев)", "bool", True
)


def delimiter(ctx: GeneratorContext) -> str:
    value = ctx.str_option("delimiter")
    return "\t" if value == "tab" else value


def cell(value: CsvValue) -> str:
    """Значение ячейки: ``None`` — пусто, числа без «.0» у целых значений."""
    if value is None:
        return ""
    if isinstance(value, float):
        return str(int(value)) if value.is_integer() else repr(value)
    return str(value)


def render_csv(
    ctx: GeneratorContext,
    columns: Sequence[str],
    rows: Iterable[Mapping[str, CsvValue]],
    *,
    notes: Sequence[str] = (),
) -> str:
    """Текст CSV: заголовок-комментарий (с пояснениями ``notes``), строка колонок, строки."""
    buffer = io.StringIO()
    if ctx.bool_option("comment_header"):
        buffer.write(ctx.comment_header("hash"))
        for note in notes:
            buffer.write(f"# {note}\n")
    writer = csv.writer(buffer, delimiter=delimiter(ctx), lineterminator="\n", quoting=csv.QUOTE_MINIMAL)
    writer.writerow(columns)
    for row in rows:
        writer.writerow([cell(row.get(name)) for name in columns])
    return buffer.getvalue()
