"""Реестр генераторов: встроенные и плагины из точек входа ``iolistgen.generators``.

Плагин — пакет Python с точкой входа в своём ``pyproject.toml``::

    [project.entry-points."iolistgen.generators"]
    scada-csv = "my_plugin.scada:ScadaCsvGenerator"

Объект точки входа — класс генератора (создаётся без аргументов) или готовый экземпляр.
Плагин, который не загрузился, не ломает остальные: ``iolistgen generate --list`` показывает
его с причиной ошибки.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from importlib import metadata

from iolistgen.generators.alarms import AlarmListGenerator
from iolistgen.generators.base import Generator
from iolistgen.generators.docs_table import DocsTableGenerator
from iolistgen.generators.modbus_map import ModbusMapGenerator
from iolistgen.generators.scada_csv import ScadaCsvGenerator
from iolistgen.generators.st_codesys import StCodesysGenerator

ENTRY_POINT_GROUP = "iolistgen.generators"
BUILTIN_ORIGIN = "встроенный"
NAME_RE = re.compile(r"^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$")


@dataclass(frozen=True)
class GeneratorEntry:
    """Генератор в реестре: объект или ошибка загрузки и откуда он взялся."""

    name: str
    origin: str
    generator: Generator | None = None
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.generator is not None


def builtin_generators() -> list[Generator]:
    """Встроенные генераторы пакета."""
    return [StCodesysGenerator(), ModbusMapGenerator(), ScadaCsvGenerator(), AlarmListGenerator(), DocsTableGenerator()]


def _check(candidate: object, expected_name: str | None) -> Generator:
    if isinstance(candidate, type):
        candidate = candidate()
    if not isinstance(candidate, Generator):
        raise TypeError("объект не соответствует протоколу Generator (name, description, options, generate)")
    if not isinstance(candidate.name, str) or not NAME_RE.match(candidate.name):
        raise TypeError(f"имя генератора «{candidate.name}» — нужны строчные латинские буквы, цифры и дефис")
    if expected_name is not None and candidate.name != expected_name:
        raise TypeError(f"точка входа «{expected_name}», а генератор называется «{candidate.name}»")
    return candidate


def _origin(entry_point: metadata.EntryPoint) -> str:
    dist = getattr(entry_point, "dist", None)  # у точек входа, созданных вручную, дистрибутива нет
    if dist is not None:
        return f"{dist.name} {dist.version}"
    return entry_point.value


def discover(*, entry_points: bool = True) -> dict[str, GeneratorEntry]:
    """Все генераторы по имени: сначала встроенные, затем плагины (дубли имён — ошибка плагина)."""
    entries: dict[str, GeneratorEntry] = {}
    for generator in builtin_generators():
        entries[generator.name] = GeneratorEntry(generator.name, BUILTIN_ORIGIN, _check(generator, None))
    if not entry_points:
        return entries
    for entry_point in sorted(metadata.entry_points(group=ENTRY_POINT_GROUP), key=lambda ep: ep.name):
        origin = _origin(entry_point)
        if entry_point.name in entries:
            owner = entries[entry_point.name].origin
            key = f"{entry_point.name} ({origin})"
            entries[key] = GeneratorEntry(
                entry_point.name, origin, error=f"имя уже занято генератором «{entry_point.name}» ({owner})"
            )
            continue
        try:
            generator = _check(entry_point.load(), entry_point.name)
        except Exception as exc:  # сломанный плагин не должен ломать остальные
            entries[entry_point.name] = GeneratorEntry(entry_point.name, origin, error=f"{type(exc).__name__}: {exc}")
            continue
        entries[entry_point.name] = GeneratorEntry(entry_point.name, origin, generator)
    return entries
