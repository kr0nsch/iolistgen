"""Настройки проекта: файл ``iolistgen.toml``.

Файл ищется рядом с перечнем и выше по каталогам до корня репозитория (каталог с ``.git``)
или задаётся явно (``--config``). Без файла действуют значения по умолчанию.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from iolistgen.columns import COLUMN_BY_NAME
from iolistgen.diagnostics import RULES, lowering_error
from iolistgen.modbus import WordOrder

if sys.version_info >= (3, 11):
    import tomllib
else:  # pragma: no cover - Python 3.10
    import tomli as tomllib

CONFIG_FILENAME = "iolistgen.toml"

# Правило по умолчанию — позиции в духе ГОСТ 21.208-2013 (буквенный код + номер: LT101, PT201,
# P101) и суффиксы сигналов через «_» (P101_RUN). Сверить с проектным стандартом обозначений.
DEFAULT_TAG_REGEX = r"^[A-Z]{1,4}[0-9]{1,4}[A-Z]?(_[A-Z0-9]+)*$"
DEFAULT_DEVICE_REGEX = r"^[A-Z]{1,4}[0-9]{1,4}[A-Z]?$"
DEFAULT_MAX_DEVICE_LENGTH = 24

SeverityLevel = Literal["error", "warning", "off"]


class ConfigError(Exception):
    """Файл настроек не читается или содержит недопустимые значения."""


class _Section(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class NamingConfig(_Section):
    """Правила имён: регулярные выражения для тегов и устройств."""

    tag_regex: str = DEFAULT_TAG_REGEX
    device_regex: str = DEFAULT_DEVICE_REGEX
    max_device_length: int = Field(default=DEFAULT_MAX_DEVICE_LENGTH, ge=1, le=128)

    @field_validator("tag_regex", "device_regex")
    @classmethod
    def _compiles(cls, value: str) -> str:
        try:
            re.compile(value)
        except re.error as exc:
            raise ValueError(f"регулярное выражение не компилируется: {exc}") from exc
        return value


class ModbusConfig(_Section):
    """Адресация Modbus в перечне."""

    address_base: Literal[0, 1] = 0
    default_word_order: WordOrder | None = None


class InputConfig(_Section):
    """Чтение файла перечня."""

    sheet: str | None = None
    encoding: str = "utf-8"
    delimiter: Literal[";", ",", "\t"] | None = None
    ignore_columns: tuple[str, ...] = ()
    column_aliases: dict[str, str] = {}
    header_search_rows: int = Field(default=30, ge=1, le=1000)

    @field_validator("encoding")
    @classmethod
    def _known_encoding(cls, value: str) -> str:
        try:
            "".encode(value)
        except LookupError as exc:
            raise ValueError(f"неизвестная кодировка «{value}»") from exc
        return value

    @field_validator("column_aliases")
    @classmethod
    def _known_columns(cls, value: dict[str, str]) -> dict[str, str]:
        unknown = sorted(name for name in value.values() if name not in COLUMN_BY_NAME)
        if unknown:
            raise ValueError(f"синонимы ссылаются на неизвестные колонки: {', '.join(unknown)}")
        return value


class Config(_Section):
    """Все настройки проекта."""

    naming: NamingConfig = NamingConfig()
    modbus: ModbusConfig = ModbusConfig()
    input: InputConfig = InputConfig()
    severity: dict[str, SeverityLevel] = {}
    generators: dict[str, dict[str, Any]] = {}
    path: str | None = Field(default=None, exclude=True)

    @field_validator("severity")
    @classmethod
    def _known_rules(cls, value: dict[str, SeverityLevel]) -> dict[str, SeverityLevel]:
        unknown = sorted(code for code in value if code not in RULES)
        if unknown:
            raise ValueError(f"нет таких правил: {', '.join(unknown)}")
        problems = [problem for code, level in sorted(value.items()) if (problem := lowering_error(code, level))]
        if problems:
            raise ValueError("; ".join(problems))
        return value


_ERROR_TEXTS = {
    "extra_forbidden": "неизвестный параметр",
    "literal_error": "недопустимое значение",
    "enum": "недопустимое значение",
    "int_parsing": "ожидается целое число",
    "int_type": "ожидается целое число",
    "string_type": "ожидается строка",
    "less_than_equal": "слишком большое значение",
    "greater_than_equal": "слишком маленькое значение",
    "dict_type": "ожидается таблица TOML",
}


def parse_config(data: dict[str, Any], source: str | None = None) -> Config:
    """Проверить словарь настроек (уже разобранный TOML)."""
    try:
        config = Config.model_validate(data)
    except ValidationError as exc:
        lines = []
        for error in exc.errors():
            location = ".".join(str(part) for part in error["loc"])
            text = _ERROR_TEXTS.get(error["type"], error["msg"])
            if error["type"] == "value_error":
                text = str(error["ctx"]["error"]) if "ctx" in error else error["msg"]
            lines.append(f"{location}: {text}")
        where = source or CONFIG_FILENAME
        raise ConfigError(f"{where}: " + "; ".join(lines)) from exc
    return config.model_copy(update={"path": source})


def load_config(path: Path) -> Config:
    """Прочитать ``iolistgen.toml``."""
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ConfigError(f"{path}: не удалось прочитать файл настроек ({exc.strerror})") from exc
    except UnicodeDecodeError as exc:
        raise ConfigError(f"{path}: файл настроек не в UTF-8") from exc
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"{path}: ошибка синтаксиса TOML: {exc}") from exc
    return parse_config(data, str(path))


def find_config(start: Path) -> Path | None:
    """``iolistgen.toml`` в каталоге перечня или выше — до корня репозитория (``.git``)."""
    directory = start if start.is_dir() else start.parent
    directory = directory.resolve()
    for candidate_dir in (directory, *directory.parents):
        candidate = candidate_dir / CONFIG_FILENAME
        if candidate.is_file():
            return candidate
        if (candidate_dir / ".git").exists():
            return None
    return None


def resolve_config(explicit: Path | None, list_path: Path | None, *, search: bool = True) -> Config:
    """Настройки для проверки: явный файл, найденный рядом с перечнем или значения по умолчанию."""
    if explicit is not None:
        return load_config(explicit)
    if search and list_path is not None:
        found = find_config(list_path)
        if found is not None:
            return load_config(found)
    return Config()
