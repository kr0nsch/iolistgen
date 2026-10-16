"""Загрузчики перечня: CSV и XLSX дают одну и ту же таблицу ``RawTable``."""

from __future__ import annotations

from pathlib import Path

from iolistgen.config import InputConfig
from iolistgen.loaders.csv_loader import load_csv
from iolistgen.loaders.table import InputError, RawCell, RawRow, RawTable
from iolistgen.loaders.xlsx_loader import load_xlsx

CSV_SUFFIXES = (".csv", ".txt")
XLSX_SUFFIXES = (".xlsx", ".xlsm")

__all__ = ["InputError", "RawCell", "RawRow", "RawTable", "load_table"]


def load_table(path: Path, config: InputConfig, *, sheet: str | None = None) -> RawTable:
    """Прочитать перечень по расширению файла."""
    if path.is_dir():
        raise InputError(f"{path}: это каталог, а не файл перечня — укажите файл .csv или .xlsx")
    if not path.is_file():
        raise InputError(f"{path}: файл не найден")
    suffix = path.suffix.lower()
    if suffix in CSV_SUFFIXES:
        return load_csv(path, config)
    if suffix in XLSX_SUFFIXES:
        return load_xlsx(path, config, sheet=sheet)
    if suffix == ".xls":
        raise InputError(f"{path}: формат .xls не поддерживается — сохраните книгу как .xlsx")
    raise InputError(f"{path}: неподдерживаемый формат «{suffix or 'без расширения'}» — нужен .csv или .xlsx")
