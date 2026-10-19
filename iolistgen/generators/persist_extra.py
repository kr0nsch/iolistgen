"""Энергонезависимые данные приложения в ``GVL_Persist``: опция ``persist_extra`` генератора ``st-codesys``.

Контракт plc-process-lib 18.3, правило 9: кроме Cfg и Retain устройств, в объекте Persistent Variables
живут данные самого приложения — задание оператора ПИД-регулятора (его Cmd лежит в обычном
``GVL_Hmi`` и при перезапуске теряется), уставки станции. Руками сгенерированный ``GVL_Persist`` не
правится: такие переменные перечисляются в файле проекта, генератор дописывает их после устройств
в том же порядке.

Формат файла — UTF-8, по объявлению ST на строку, как в списке переменных::

    // задание оператора регулятора уровня LIC101 (P-Q1)
    rLIC101SpOper_m : REAL := 2.0;   // м
    xStationAutoSaved : BOOL;

Пустые строки и строки-комментарии ``//`` пропускаются; комментарий в конце строки переносится в
``GVL_Persist``. Порядок постоянный: новые переменные — только в конец файла (правило 18.3.1),
переставлять и переименовывать прежние нельзя — сохранённые значения пропадут. Сверку с прошлой
генерацией делает ``persist_check`` (``st_codesys.check_persist``).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from iolistgen.generators.base import GenerationError
from iolistgen.identifiers import check_identifier

# имя : тип [:= значение] ; [// комментарий] — тип и значение без «;» (строковые литералы с «;» не поддержаны)
_DECL_RE = re.compile(
    r"^(?P<name>[^\s:]+)\s*:\s*(?P<type>[^:;]+?)\s*(?::=\s*(?P<init>[^;]+?)\s*)?;\s*(?://\s*(?P<comment>.*))?$"
)


@dataclass(frozen=True)
class ExtraVar:
    """Переменная данных приложения: имя, тип, начальное значение (текст ST), комментарий, строка файла."""

    name: str
    st_type: str
    init: str
    comment: str
    line: int

    @property
    def type_text(self) -> str:
        """Тип с инициализатором — как во втором операнде объявления: ``REAL := 2.0``."""
        return f"{self.st_type} := {self.init}" if self.init else self.st_type


def parse_persist_extra(text: str, source: str) -> tuple[ExtraVar, ...]:
    """Разобрать файл ``persist_extra``; ``GenerationError`` — ошибка с номером строки."""
    result: list[ExtraVar] = []
    seen: dict[str, ExtraVar] = {}
    for number, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("//"):
            continue
        where = f"persist_extra {source}, строка {number}"
        match = _DECL_RE.match(line)
        if match is None:
            raise GenerationError(
                f"{where}: «{line}» — ожидается объявление «имя : тип := значение; // комментарий», по одному на строку"
            )
        name = match["name"]
        problem = check_identifier(name)
        if problem is not None:
            raise GenerationError(f"{where}: {problem.message}; {problem.hint}")
        key = name.casefold()
        if key in seen:
            raise GenerationError(
                f"{where}: переменная {name} уже объявлена в строке {seen[key].line} (имена без учёта регистра)"
            )
        item = ExtraVar(
            name=name,
            st_type=" ".join(match["type"].split()),
            init=" ".join((match["init"] or "").split()),
            comment=(match["comment"] or "").strip(),
            line=number,
        )
        seen[key] = item
        result.append(item)
    return tuple(result)


def load_persist_extra(path: Path) -> tuple[ExtraVar, ...]:
    """Прочитать файл ``persist_extra`` (UTF-8, BOM допускается)."""
    try:
        text = path.read_text(encoding="utf-8-sig")
    except OSError as exc:
        raise GenerationError(f"persist_extra: не удалось прочитать {path} ({exc.strerror})") from exc
    except UnicodeDecodeError:
        raise GenerationError(f"persist_extra: {path} не в UTF-8") from None
    return parse_persist_extra(text, path.name)
