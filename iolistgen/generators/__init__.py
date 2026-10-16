"""Генераторы и плагины: протокол, опции, контекст, реестр.

Встроенные генераторы: ``st-codesys`` (ST для CODESYS), ``modbus-map`` (карта обмена Modbus),
``scada-csv`` (импорт тегов SCADA), ``alarm-list`` (список тревог), ``docs-table`` (перечень
сигналов). Имена ПЛК для всех — ``generators.plc.build_plc()``. Сторонние генераторы подключаются
плагинами через точки входа ``iolistgen.generators`` (docs/PLUGINS.md).
"""

from __future__ import annotations

from iolistgen.generators.base import (
    AUTO_GENERATED,
    DO_NOT_EDIT,
    GenerationError,
    Generator,
    GeneratorContext,
    GeneratorOption,
    OptionError,
    OptionValue,
    OutputFile,
    resolve_options,
)
from iolistgen.generators.registry import ENTRY_POINT_GROUP, GeneratorEntry, builtin_generators, discover

__all__ = [
    "AUTO_GENERATED",
    "DO_NOT_EDIT",
    "ENTRY_POINT_GROUP",
    "GenerationError",
    "Generator",
    "GeneratorContext",
    "GeneratorEntry",
    "GeneratorOption",
    "OptionError",
    "OptionValue",
    "OutputFile",
    "builtin_generators",
    "discover",
    "resolve_options",
]
